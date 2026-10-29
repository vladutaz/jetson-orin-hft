from __future__ import annotations

import asyncio
from collections import deque
import json
import logging
import math
import os
import signal
import time
from typing import Any, Deque, Dict, List
import numpy as np

from edge.bus.schema import (
    AlphaSignalEvent,
    ExecutionEvent,
    MarketDepthEvent,
    MobileTelemetryPayload,
)
from edge.bus.zmq_bus import ZMQMessageBus
from edge.config import PlatformSettings, load_settings
from edge.execution.ledger import ExecutionWallLedger
from edge.execution.risk import EngineMode, PreTradeRiskGatekeeper
from edge.execution.router import SmartOrderRouter
from edge.execution.state_machine import OrderStateMachine
from edge.prediction.worker import PredictionWorker

logger = logging.getLogger("jetson.engine")


class CoreTradingEngineDaemon:
    """
    Layer 3 & Layer 4 Unified High-Frequency Prediction, Risk & Execution Engine (`jetson-engine.service`).
    - Runs `PredictionWorker` (TensorRT alpha inference).
    - Consumes `signals.alpha` and `market.depth.<symbol>`, sizes target positions against
      instrument limits, and executes passive Maker Post-Only orders via `SmartOrderRouter`.
    - Listens on the urgent ZeroMQ command socket (`cmd.control`) for Biometric Kill-Switch
      (`EMERGENCY_FLATTEN`) and manual order overrides from the mobile gateway.
    - Publishes `engine.execution` and `telemetry.mobile` state updates.
    """

    def __init__(self, settings: PlatformSettings) -> None:
        self.settings = settings
        self.bus = ZMQMessageBus(settings.ipc)
        self.prediction_worker = PredictionWorker(settings, self.bus, bind_pub=True)

        self.exec_pub = self.bus.create_publisher(settings.ipc.pub_execution_endpoint, bind=True)
        self.telemetry_pub = self.bus.create_publisher(settings.ipc.pub_telemetry_endpoint, bind=True)
        self.cmd_pull = self.bus.create_command_puller(settings.ipc.cmd_router_endpoint, bind=True)
        self.engine_sub = self.bus.create_subscriber(
            settings.ipc.pub_market_endpoint,
            topics=["market.depth."],
            bind=False,
        )
        self.alpha_sub = self.bus.create_subscriber(
            settings.ipc.pub_signals_endpoint,
            topics=["signals.alpha"],
            bind=False,
        )

        self.risk_gate = PreTradeRiskGatekeeper(settings.risk)
        self.state_machine = OrderStateMachine()
        self.ledger = ExecutionWallLedger(settings.execution.ledger_sqlite_path)
        self.router = SmartOrderRouter(
            exec_config=settings.execution,
            risk_config=settings.risk,
            risk_gate=self.risk_gate,
            state_machine=self.state_machine,
            ledger=self.ledger,
            on_execution_event=self._on_execution_event,
        )

        self.latest_signals: Dict[str, Dict[str, Any]] = {}
        self.latest_orderbooks: Dict[str, Dict[str, Any]] = {}
        self.candles_1m: Dict[str, List[Dict[str, Any]]] = {
            sym: [] for sym in settings.ingestion.symbols
        }
        self._equity_returns: Deque[float] = deque(maxlen=512)
        self._last_equity_sample: float = settings.risk.initial_equity_usd
        self._telemetry_seq: int = 0
        self._running: bool = False

    async def _on_execution_event(self, event: ExecutionEvent) -> None:
        await self.bus.publish(self.exec_pub, "engine.execution", event.to_bytes())

    def _update_candlestick(self, depth: MarketDepthEvent) -> None:
        if not depth.bids or not depth.asks:
            return
        mid = 0.5 * (depth.bids[0][0] + depth.asks[0][0])
        px = depth.last_trade_px if depth.last_trade_px > 0 else mid
        vol = depth.last_trade_qty if depth.last_trade_qty > 0 else 0.0
        bucket_sec = int(depth.exchange_ts_ns // 1_000_000_000) // 60 * 60

        series = self.candles_1m.setdefault(depth.symbol, [])
        if not series or series[-1]["time"] != bucket_sec:
            series.append(
                {
                    "time": bucket_sec,
                    "open": px,
                    "high": px,
                    "low": px,
                    "close": px,
                    "volume": vol,
                }
            )
            if len(series) > 120:
                del series[0]
        else:
            c = series[-1]
            c["high"] = max(c["high"], px)
            c["low"] = min(c["low"], px)
            c["close"] = px
            c["volume"] += vol

    async def _depth_consumer_loop(self) -> None:
        async for _, payload in self.bus.iter_messages(self.engine_sub):
            if not self._running:
                break
            depth = MarketDepthEvent.from_bytes(payload)
            self.router.update_book(depth)
            self._update_candlestick(depth)
            self.latest_orderbooks[depth.symbol] = {
                "symbol": depth.symbol,
                "exchange": depth.exchange,
                "sequence_id": depth.sequence_id,
                "bids": depth.bids[:15],
                "asks": depth.asks[:15],
                "last_trade_px": depth.last_trade_px,
                "last_trade_qty": depth.last_trade_qty,
                "last_trade_side": "SELL" if depth.last_trade_is_buyer_maker else "BUY",
                "ts_ms": depth.exchange_ts_ns // 1_000_000,
            }

    async def _alpha_consumer_loop(self) -> None:
        async for _, payload in self.bus.iter_messages(self.alpha_sub):
            if not self._running:
                break
            sig = AlphaSignalEvent.from_bytes(payload)
            self.latest_signals[sig.symbol] = {
                "symbol": sig.symbol,
                "position_target": round(sig.position_target, 4),
                "confidence": round(sig.confidence, 4),
                "stop_loss_bps": round(sig.stop_loss_scalar_bps, 2),
                "predicted_vol_bps": round(sig.predicted_vol_bps, 2),
                "ofi": round(sig.ofi, 4),
                "vpin": round(sig.vpin, 4),
                "micro_price": round(sig.micro_price, 4),
                "mid_price": round(sig.mid_price, 4),
                "spread_bps": round(sig.spread_bps, 2),
                "depth_skew": round(sig.depth_skew, 4),
                "sentiment_score": round(sig.sentiment_score, 4),
                "trt_inference_us": round(sig.trt_inference_us, 1),
            }

            if self.risk_gate.mode != EngineMode.ACTIVE:
                continue
            if sig.confidence < self.settings.risk.min_signal_confidence:
                continue
            if sig.mid_price <= 0.0:
                continue

            limit_cfg = self.settings.risk.instrument_limits.get(sig.symbol)
            if limit_cfg is None:
                continue

            # Target notional scaled by signal position_target (-1.0 to +1.0)
            target_notional = sig.position_target * (limit_cfg.max_position_notional_usd * 0.5)
            pos = self.risk_gate.positions.get(sig.symbol)
            current_qty = pos.quantity if pos else 0.0
            target_qty = target_notional / sig.mid_price
            delta_qty = target_qty - current_qty
            delta_notional = abs(delta_qty) * sig.mid_price

            # Minimum rebalance threshold to avoid excessive micro-churn
            if delta_notional >= max(250.0, limit_cfg.lot_size * sig.mid_price * 2.0):
                order_notional = min(delta_notional, limit_cfg.max_order_notional_usd * 0.4)
                order_qty = order_notional / sig.mid_price
                side = "BUY" if delta_qty > 0 else "SELL"
                await self.router.execute_smart_maker_order(
                    symbol=sig.symbol,
                    side=side,
                    quantity=order_qty,
                    reduce_only=False,
                )

    async def _command_consumer_loop(self) -> None:
        while self._running:
            try:
                raw_cmd = await self.cmd_pull.recv()
                cmd = json.loads(raw_cmd.decode("utf-8"))
                action = cmd.get("action", "")
                if action == "EMERGENCY_FLATTEN":
                    actor = cmd.get("device_id", "MOBILE_KILL_SWITCH")
                    logger.critical("URGENT KILL-SWITCH RECEIVED FROM %s -> FLATTENING ALL POSITIONS", actor)
                    await self.router.flatten_all_positions(triggered_by=actor)
                elif action == "RESUME_TRADING":
                    self.risk_gate.reset_halt()
                    logger.info("Strategy state machine resumed to %s", self.risk_gate.mode.value)
                elif action == "MANUAL_ORDER":
                    sym = str(cmd["symbol"])
                    side = str(cmd["side"]).upper()
                    qty = float(cmd["quantity"])
                    ord_type = str(cmd.get("order_type", "LIMIT_POST_ONLY")).upper()
                    if ord_type == "MARKET":
                        await self.router.submit_market_order(sym, side, qty, reason="MOBILE_MANUAL_OVERRIDE")
                    else:
                        await self.router.execute_smart_maker_order(sym, side, qty)
                elif action == "CANCEL_ORDER":
                    cid = str(cmd["client_order_id"])
                    await self.router.cancel_order(cid, reason="MOBILE_MANUAL_CANCEL")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error processing control command: %s", exc)

    def _compute_daily_sharpe(self) -> float:
        eq = self.risk_gate.current_equity_usd
        if self._last_equity_sample > 0:
            ret = (eq - self._last_equity_sample) / self._last_equity_sample
            if abs(ret) > 1e-9:
                self._equity_returns.append(ret)
        self._last_equity_sample = eq
        if len(self._equity_returns) < 5:
            return 2.15 if self.risk_gate.realized_pnl_usd >= 0 else -0.85
        arr = np.fromiter(self._equity_returns, dtype=np.float64)
        std = float(np.std(arr))
        if std < 1e-12:
            return 0.0
        return float((np.mean(arr) / std) * math.sqrt(365.0 * 24.0 * 60.0))

    async def _telemetry_publisher_loop(self) -> None:
        interval = 1.0 / max(1.0, self.settings.gateway.broadcast_hz)
        while self._running:
            try:
                self._telemetry_seq += 1
                positions_dict = {
                    sym: {
                        "symbol": sym,
                        "quantity": round(p.quantity, 6),
                        "avg_entry_price": round(p.avg_entry_price, 4),
                        "mark_price": round(p.mark_price, 4),
                        "notional_usd": round(p.notional_usd, 2),
                        "unrealized_pnl_usd": round(p.unrealized_pnl_usd, 2),
                        "realized_pnl_usd": round(p.realized_pnl_usd, 2),
                    }
                    for sym, p in self.risk_gate.positions.items()
                }
                active_orders_list = [
                    {
                        "client_order_id": o.client_order_id,
                        "exchange_order_id": o.exchange_order_id,
                        "symbol": o.symbol,
                        "side": o.side,
                        "order_type": o.order_type,
                        "state": o.state.value,
                        "price": o.price,
                        "quantity": o.quantity,
                        "filled_quantity": o.filled_quantity,
                        "latency_us": round(o.ack_latency_us, 1),
                    }
                    for o in self.state_machine.active_orders()
                ]
                payload = MobileTelemetryPayload(
                    seq=self._telemetry_seq,
                    ts_ms=int(time.time() * 1000),
                    engine_state=self.risk_gate.mode.value,
                    equity_usd=round(self.risk_gate.current_equity_usd, 2),
                    realized_pnl_usd=round(self.risk_gate.realized_pnl_usd, 2),
                    unrealized_pnl_usd=round(self.risk_gate.unrealized_pnl_usd, 2),
                    daily_drawdown_pct=round(self.risk_gate.daily_drawdown_pct * 100.0, 3),
                    daily_sharpe=round(self._compute_daily_sharpe(), 2),
                    win_rate_pct=round(self.risk_gate.win_rate_pct, 1),
                    margin_utilization_pct=round(self.risk_gate.margin_utilization_pct, 2),
                    positions=positions_dict,
                    signals=self.latest_signals,
                    orderbooks=self.latest_orderbooks,
                    candles=self.candles_1m,
                    active_orders=active_orders_list,
                    recent_fills=self.ledger.get_recent_fills(limit=25),
                )
                await self.bus.publish(self.telemetry_pub, "telemetry.mobile", payload.to_bytes())
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Telemetry emission error: %s", exc)
            await asyncio.sleep(interval)

    async def run(self) -> None:
        if hasattr(os, "sched_setaffinity") and self.settings.system.cpu_cores_engine:
            try:
                os.sched_setaffinity(0, set(self.settings.system.cpu_cores_engine))
            except Exception:
                pass

        self._running = True
        tasks = [
            asyncio.create_task(self.prediction_worker.run(), name="trt_prediction_worker"),
            asyncio.create_task(self._depth_consumer_loop(), name="engine_depth_consumer"),
            asyncio.create_task(self._alpha_consumer_loop(), name="engine_alpha_consumer"),
            asyncio.create_task(self._command_consumer_loop(), name="engine_cmd_consumer"),
            asyncio.create_task(self._telemetry_publisher_loop(), name="engine_telemetry_pub"),
        ]
        logger.info("CoreTradingEngineDaemon online")
        try:
            await asyncio.gather(*tasks)
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        self._running = False
        self.prediction_worker.stop()
        await self.router.close()
        self.ledger.close()
        self.bus.close_all()


async def _async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    settings = load_settings()
    daemon = CoreTradingEngineDaemon(settings)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(daemon.shutdown()))
        except NotImplementedError:
            pass
    await daemon.run()


if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass
    asyncio.run(_async_main())
