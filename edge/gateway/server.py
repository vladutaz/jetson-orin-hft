from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from typing import Any, Dict, Optional, Set
import websockets
from websockets.server import WebSocketServerProtocol

from edge.bus.schema import ExecutionEvent, MobileTelemetryPayload
from edge.bus.zmq_bus import ZMQMessageBus
from edge.config import PlatformSettings, load_settings
from edge.gateway.auth import GatewayAuthenticator
from edge.gateway.delta import TelemetryDeltaCompressor
from edge.gateway.jetson_telemetry import (
    HardwareWatchdogFeeder,
    JetsonOrinTelemetryReader,
)

logger = logging.getLogger("jetson.gateway")


class MobileTelemetryGatewayServer:
    """
    Layer 5 Secure Edge Telemetry & Command Gateway (`jetson-bridge.service`):
      - Binds a TLS 1.3 / mTLS WebSocket server reachable via LAN, WireGuard VPN, or Tailscale.
      - Supports an optional outbound encrypted WebSocket Relay connection so mobile clients
        can connect without opening inbound router ports or requiring a static IP.
      - Authenticates mobile clients via Ed25519 cryptographic challenge-response and short-lived JWTs.
      - Broadcasts 10Hz delta-compressed telemetry (`TELEMETRY_FULL` / `TELEMETRY_DELTA`) fused with
        live Jetson Orin hardware metrics (GPU temp, CPU load, LPDDR5 RAM, INA3221 power Watts).
      - Routes priority Biometric Kill-Switch (`EMERGENCY_FLATTEN`) and manual order commands
        directly to the trading engine over ZeroMQ IPC.
    """

    def __init__(self, settings: PlatformSettings) -> None:
        self.settings = settings
        self.bus = ZMQMessageBus(settings.ipc)
        self.telemetry_sub = self.bus.create_subscriber(
            settings.ipc.pub_telemetry_endpoint,
            topics=["telemetry.mobile"],
            bind=False,
        )
        self.exec_sub = self.bus.create_subscriber(
            settings.ipc.pub_execution_endpoint,
            topics=["engine.execution"],
            bind=False,
        )
        self.cmd_push = self.bus.create_command_pusher(settings.ipc.cmd_router_endpoint)
        self.auth = GatewayAuthenticator(settings.gateway)
        self.hw_reader = JetsonOrinTelemetryReader()
        self.watchdog = HardwareWatchdogFeeder(settings.system.watchdog_device)

        self._clients: Set[WebSocketServerProtocol] = set()
        self._client_compressors: Dict[WebSocketServerProtocol, TelemetryDeltaCompressor] = {}
        self._authenticated_clients: Dict[WebSocketServerProtocol, str] = {}
        self._latest_state: Dict[str, Any] = {}
        self._running = False

    async def handle_client(self, ws: WebSocketServerProtocol) -> None:
        self._clients.add(ws)
        self._client_compressors[ws] = TelemetryDeltaCompressor(full_sync_interval=60)
        device_id = f"mobile-{id(ws)}"
        nonce = self.auth.issue_challenge(device_id)
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "AUTH_CHALLENGE",
                        "device_id": device_id,
                        "nonce": nonce,
                        "node_id": self.settings.system.node_id,
                    }
                )
            )
            async for raw_msg in ws:
                msg = json.loads(raw_msg)
                mtype = msg.get("type", "")

                if mtype == "PING":
                    client_ts = float(msg.get("ts_ms", time.time() * 1000))
                    rtt = max(0.2, (time.time() * 1000) - client_ts)
                    self.hw_reader.snapshot(network_ping_ms=rtt)
                    await ws.send(json.dumps({"type": "PONG", "ts_ms": int(time.time() * 1000)}))
                    continue

                if mtype == "AUTH_RESPONSE":
                    dev_id = str(msg.get("device_id", device_id))
                    sig = str(msg.get("signature", ""))
                    pub = msg.get("public_key")
                    resp_nonce = str(msg.get("nonce", nonce))
                    token = self.auth.verify_challenge_and_issue_jwt(dev_id, resp_nonce, sig, pub)
                    if token:
                        self._authenticated_clients[ws] = dev_id
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "AUTH_OK",
                                    "jwt": token,
                                    "ttl_sec": self.settings.gateway.jwt_ttl_seconds,
                                }
                            )
                        )
                        if self._latest_state:
                            frame = self._client_compressors[ws].encode_frame(self._latest_state)
                            await ws.send(json.dumps(frame))
                    else:
                        await ws.send(json.dumps({"type": "AUTH_ERR", "reason": "Invalid Ed25519 signature"}))
                    continue

                # Verify JWT on privileged control actions (Kill-Switch & Manual Orders)
                jwt_token = str(msg.get("jwt", ""))
                claims = self.auth.verify_jwt(jwt_token) if jwt_token else None
                if ws not in self._authenticated_clients and claims is None:
                    await ws.send(json.dumps({"type": "ERROR", "reason": "Unauthorized client session"}))
                    continue

                if mtype == "EMERGENCY_FLATTEN":
                    if not msg.get("biometric_verified", False):
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "KILL_SWITCH_REJECTED",
                                    "reason": "Biometric confirmation flag required",
                                }
                            )
                        )
                        continue
                    cmd_payload = {
                        "action": "EMERGENCY_FLATTEN",
                        "device_id": self._authenticated_clients.get(ws, device_id),
                        "ts_ms": int(time.time() * 1000),
                    }
                    await self.cmd_push.send(json.dumps(cmd_payload).encode("utf-8"))
                    await ws.send(
                        json.dumps(
                            {
                                "type": "KILL_SWITCH_ACK",
                                "state": "HALTED",
                                "ts_ms": int(time.time() * 1000),
                            }
                        )
                    )
                elif mtype == "RESUME_TRADING":
                    await self.cmd_push.send(
                        json.dumps({"action": "RESUME_TRADING"}).encode("utf-8")
                    )
                elif mtype == "MANUAL_ORDER":
                    cmd_payload = {
                        "action": "MANUAL_ORDER",
                        "symbol": msg["symbol"],
                        "side": msg["side"],
                        "quantity": float(msg["quantity"]),
                        "order_type": msg.get("order_type", "LIMIT_POST_ONLY"),
                    }
                    await self.cmd_push.send(json.dumps(cmd_payload).encode("utf-8"))
                elif mtype == "CANCEL_ORDER":
                    cmd_payload = {
                        "action": "CANCEL_ORDER",
                        "client_order_id": msg["client_order_id"],
                    }
                    await self.cmd_push.send(json.dumps(cmd_payload).encode("utf-8"))
        except websockets.ConnectionClosed:
            pass
        except Exception as exc:
            logger.debug("Client connection handler closed: %s", exc)
        finally:
            self._clients.discard(ws)
            self._client_compressors.pop(ws, None)
            self._authenticated_clients.pop(ws, None)

    async def _telemetry_broadcast_loop(self) -> None:
        min_interval = 1.0 / max(1.0, self.settings.gateway.broadcast_hz)
        last_sent_ts = 0.0
        async for _, payload in self.bus.iter_messages(self.telemetry_sub):
            if not self._running:
                break
            now = time.monotonic()
            if (now - last_sent_ts) < (min_interval * 0.85):
                continue
            last_sent_ts = now

            telem = MobileTelemetryPayload.from_bytes(payload)
            state_dict = telem.to_dict()
            state_dict["hardware"] = self.hw_reader.snapshot()
            self._latest_state = state_dict

            if not self._clients:
                continue

            dead_clients = []
            for ws in list(self._clients):
                compressor = self._client_compressors.get(ws)
                if compressor is None:
                    continue
                try:
                    frame = compressor.encode_frame(state_dict)
                    await ws.send(json.dumps(frame))
                except Exception:
                    dead_clients.append(ws)

            for dead in dead_clients:
                self._clients.discard(dead)
                self._client_compressors.pop(dead, None)
                self._authenticated_clients.pop(dead, None)

    async def _execution_event_forwarder(self) -> None:
        async for _, payload in self.bus.iter_messages(self.exec_sub):
            if not self._running:
                break
            ev = ExecutionEvent.from_bytes(payload)
            packet = json.dumps(
                {
                    "type": "EXECUTION_EVENT",
                    "event": {
                        "event_type": ev.event_type,
                        "client_order_id": ev.client_order_id,
                        "symbol": ev.symbol,
                        "side": ev.side,
                        "order_type": ev.order_type,
                        "state": ev.state,
                        "price": ev.price,
                        "quantity": ev.quantity,
                        "filled_quantity": ev.filled_quantity,
                        "avg_fill_price": ev.avg_fill_price,
                        "slippage_bps": round(ev.slippage_bps, 2),
                        "latency_us": round(ev.latency_us, 1),
                        "reason": ev.reason,
                        "ts_ms": ev.ts_ns // 1_000_000,
                    },
                }
            )
            for ws in list(self._clients):
                try:
                    await ws.send(packet)
                except Exception:
                    pass

    async def _outbound_relay_loop(self) -> None:
        relay_url = self.settings.gateway.relay_outbound_url
        if not relay_url:
            return
        compressor = TelemetryDeltaCompressor(full_sync_interval=60)
        backoff = 1.0
        while self._running:
            try:
                async with websockets.connect(relay_url, ping_interval=15) as relay_ws:
                    backoff = 1.0
                    logger.info("Connected to outbound cloud relay: %s", relay_url)
                    while self._running:
                        if self._latest_state:
                            frame = compressor.encode_frame(self._latest_state)
                            await relay_ws.send(json.dumps(frame))
                        await asyncio.sleep(1.0 / max(1.0, self.settings.gateway.broadcast_hz))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Outbound relay disconnected (%s), retrying in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 15.0)

    async def _watchdog_loop(self) -> None:
        self.watchdog.open()
        interval = max(1, self.settings.system.watchdog_interval_sec)
        try:
            while self._running:
                self.watchdog.pet()
                await asyncio.sleep(interval)
        finally:
            self.watchdog.close_magic()

    async def run(self) -> None:
        if hasattr(os, "sched_setaffinity") and self.settings.system.cpu_cores_bridge:
            try:
                os.sched_setaffinity(0, set(self.settings.system.cpu_cores_bridge))
            except Exception:
                pass

        self._running = True
        ssl_ctx = self.auth.build_tls13_context()
        proto = "wss" if ssl_ctx else "ws"
        logger.info(
            "Starting MobileTelemetryGatewayServer on %s://%s:%d (Hz=%.1f)",
            proto,
            self.settings.gateway.bind_host,
            self.settings.gateway.bind_port,
            self.settings.gateway.broadcast_hz,
        )

        async with websockets.serve(
            self.handle_client,
            self.settings.gateway.bind_host,
            self.settings.gateway.bind_port,
            ssl=ssl_ctx,
            ping_interval=15,
            ping_timeout=10,
            max_queue=512,
        ):
            await asyncio.gather(
                self._telemetry_broadcast_loop(),
                self._execution_event_forwarder(),
                self._outbound_relay_loop(),
                self._watchdog_loop(),
            )

    def shutdown(self) -> None:
        self._running = False
        self.bus.close_all()


async def _async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    settings = load_settings()
    server = MobileTelemetryGatewayServer(settings)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, server.shutdown)
        except NotImplementedError:
            pass
    await server.run()


if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass
    asyncio.run(_async_main())
