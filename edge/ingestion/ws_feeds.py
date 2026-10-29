from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable, Dict, List
import aiohttp
import websockets

from edge.bus.schema import MarketDepthEvent
from edge.config import IngestionConfig
from edge.ingestion.orderbook import (
    BookParityError,
    BufferedDepthDelta,
    LocalL2OrderBook,
    SequenceGapError,
)

logger = logging.getLogger(__name__)

DepthCallback = Callable[[MarketDepthEvent], Awaitable[None]]


class BinanceFuturesFeedHandler:
    """
    Binance USD-M Futures L2 Order Book (`@depth@100ms` / `@depth@0ms`) and `@aggTrade`
    WebSocket handler with REST `/fapi/v1/depth` snapshot synchronization and automatic
    gap recovery on `U`/`u`/`pu` discontinuity.
    """

    def __init__(self, config: IngestionConfig, on_depth: DepthCallback) -> None:
        self.config = config
        self.on_depth = on_depth
        self.books: Dict[str, LocalL2OrderBook] = {
            sym: LocalL2OrderBook("binance_futures", sym, max_depth=config.depth_levels)
            for sym in config.symbols
        }
        self._running = False

    async def _fetch_snapshot(self, session: aiohttp.ClientSession, symbol: str) -> None:
        url = f"{self.config.binance_rest_snapshot_url}?symbol={symbol}&limit=1000"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
            resp.raise_for_status()
            data = await resp.json()
            last_u = int(data["lastUpdateId"])
            bids = [(float(p), float(q)) for p, q in data.get("bids", [])]
            asks = [(float(p), float(q)) for p, q in data.get("asks", [])]
            ex_ts_ns = int(data.get("T", time.time() * 1000)) * 1_000_000
            book = self.books[symbol]
            event = book.apply_snapshot(last_u, bids, asks, ex_ts_ns)
            await self.on_depth(event)
            logger.info("[BinanceFutures:%s] Synchronized L2 snapshot at u=%d", symbol, last_u)

    async def run(self) -> None:
        self._running = True
        streams = []
        for sym in self.config.symbols:
            s_lower = sym.lower()
            streams.append(f"{s_lower}@depth@100ms")
            streams.append(f"{s_lower}@aggTrade")
        ws_url = f"{self.config.binance_ws_url}?streams={'/'.join(streams)}"

        backoff = 1.0
        async with aiohttp.ClientSession() as http_session:
            while self._running:
                try:
                    for book in self.books.values():
                        book.reset_for_resync()

                    async with websockets.connect(
                        ws_url,
                        ping_interval=15,
                        ping_timeout=10,
                        max_queue=4096,
                        compression=None,
                    ) as ws:
                        backoff = 1.0
                        # Kick off initial snapshot synchronization concurrently after first buffered deltas arrive
                        sync_tasks = {
                            sym: asyncio.create_task(self._delayed_snapshot(http_session, sym, 0.25))
                            for sym in self.config.symbols
                        }

                        async for raw_msg in ws:
                            if not self._running:
                                break
                            msg = json.loads(raw_msg)
                            payload = msg.get("data", msg)
                            event_type = payload.get("e")
                            symbol = payload.get("s")
                            if not symbol or symbol not in self.books:
                                continue

                            book = self.books[symbol]
                            if event_type == "aggTrade":
                                book.record_trade(
                                    price=float(payload["p"]),
                                    qty=float(payload["q"]),
                                    is_buyer_maker=bool(payload["m"]),
                                    exchange_ts_ns=int(payload["T"]) * 1_000_000,
                                )
                            elif event_type == "depthUpdate":
                                delta = BufferedDepthDelta(
                                    U=int(payload["U"]),
                                    u=int(payload["u"]),
                                    pu=int(payload.get("pu", 0)),
                                    bids=[(float(p), float(q)) for p, q in payload.get("b", [])],
                                    asks=[(float(p), float(q)) for p, q in payload.get("a", [])],
                                    exchange_ts_ns=int(payload.get("T", payload.get("E", 0))) * 1_000_000,
                                )
                                try:
                                    depth_ev = book.buffer_ws_delta(delta)
                                    if depth_ev is not None:
                                        await self.on_depth(depth_ev)
                                except (SequenceGapError, BookParityError) as gap_err:
                                    logger.warning("%s -> triggering immediate resync", gap_err)
                                    if symbol not in sync_tasks or sync_tasks[symbol].done():
                                        sync_tasks[symbol] = asyncio.create_task(
                                            self._delayed_snapshot(http_session, symbol, 0.05)
                                        )
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("[BinanceFutures] WebSocket disconnected: %s. Reconnecting in %.1fs", exc, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, 15.0)

    async def _delayed_snapshot(self, session: aiohttp.ClientSession, symbol: str, delay: float) -> None:
        await asyncio.sleep(delay)
        await self._fetch_snapshot(session, symbol)

    def stop(self) -> None:
        self._running = False


class BybitLinearFeedHandler:
    """
    Bybit V5 Linear Perpetuals WebSocket handler (`orderbook.50.<symbol>` & `publicTrade.<symbol>`)
    supporting automatic snapshot/delta reconciliation via sequence `u` and `seq`.
    """

    def __init__(self, config: IngestionConfig, on_depth: DepthCallback) -> None:
        self.config = config
        self.on_depth = on_depth
        self.books: Dict[str, LocalL2OrderBook] = {
            sym: LocalL2OrderBook("bybit_linear", sym, max_depth=config.depth_levels)
            for sym in config.symbols
        }
        self._running = False

    async def run(self) -> None:
        self._running = True
        backoff = 1.0
        args = []
        for sym in self.config.symbols:
            args.append(f"orderbook.50.{sym}")
            args.append(f"publicTrade.{sym}")

        while self._running:
            try:
                async with websockets.connect(
                    self.config.bybit_ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    max_queue=4096,
                    compression=None,
                ) as ws:
                    backoff = 1.0
                    sub_req = {"op": "subscribe", "args": args}
                    await ws.send(json.dumps(sub_req))

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        msg = json.loads(raw_msg)
                        topic = msg.get("topic", "")
                        msg_type = msg.get("type", "")
                        ts_ns = int(msg.get("ts", time.time() * 1000)) * 1_000_000

                        if topic.startswith("publicTrade."):
                            sym = topic.split(".")[-1]
                            book = self.books.get(sym)
                            if book:
                                for tr in msg.get("data", []):
                                    book.record_trade(
                                        price=float(tr["p"]),
                                        qty=float(tr["v"]),
                                        is_buyer_maker=(tr.get("S") == "Sell"),
                                        exchange_ts_ns=int(tr.get("T", ts_ns // 1_000_000)) * 1_000_000,
                                    )
                        elif topic.startswith("orderbook."):
                            data = msg.get("data", {})
                            sym = data.get("s")
                            if not sym or sym not in self.books:
                                continue
                            book = self.books[sym]
                            u_seq = int(data.get("u", 0))
                            bids = [(float(p), float(q)) for p, q in data.get("b", [])]
                            asks = [(float(p), float(q)) for p, q in data.get("a", [])]

                            if msg_type == "snapshot" or u_seq == 1 or not book.initialized:
                                ev = book.apply_snapshot(u_seq, bids, asks, ts_ns)
                                await self.on_depth(ev)
                            else:
                                delta = BufferedDepthDelta(
                                    U=u_seq,
                                    u=u_seq,
                                    pu=book.last_update_id,
                                    bids=bids,
                                    asks=asks,
                                    exchange_ts_ns=ts_ns,
                                )
                                try:
                                    ev = book.buffer_ws_delta(delta)
                                    if ev is not None:
                                        await self.on_depth(ev)
                                except (SequenceGapError, BookParityError) as err:
                                    logger.warning("[Bybit:%s] %s -> re-subscribing", sym, err)
                                    await ws.send(
                                        json.dumps({"op": "unsubscribe", "args": [f"orderbook.50.{sym}"]})
                                    )
                                    await ws.send(
                                        json.dumps({"op": "subscribe", "args": [f"orderbook.50.{sym}"]})
                                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[BybitLinear] WebSocket error: %s. Reconnecting in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 15.0)

    def stop(self) -> None:
        self._running = False


class CoinbaseAdvancedFeedHandler:
    """
    Coinbase Advanced Trade WebSocket handler (`level2` and `market_trades` channels).
    Normalizes `BTC-USD` product IDs to canonical `BTCUSDT` symbols for cross-venue alpha fusion.
    """

    def __init__(self, config: IngestionConfig, on_depth: DepthCallback) -> None:
        self.config = config
        self.on_depth = on_depth
        self.product_map = {pid: pid.replace("-USD", "USDT") for pid in config.coinbase_product_ids}
        self.books: Dict[str, LocalL2OrderBook] = {
            canon: LocalL2OrderBook("coinbase_advanced", canon, max_depth=config.depth_levels)
            for canon in self.product_map.values()
        }
        self._running = False

    async def run(self) -> None:
        self._running = True
        backoff = 1.0
        while self._running:
            try:
                async with websockets.connect(
                    self.config.coinbase_ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    max_queue=4096,
                    max_size=16 * 1024 * 1024,
                ) as ws:
                    backoff = 1.0
                    await ws.send(
                        json.dumps(
                            {
                                "type": "subscribe",
                                "product_ids": self.config.coinbase_product_ids,
                                "channel": "level2",
                            }
                        )
                    )
                    await ws.send(
                        json.dumps(
                            {
                                "type": "subscribe",
                                "product_ids": self.config.coinbase_product_ids,
                                "channel": "market_trades",
                            }
                        )
                    )

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        msg = json.loads(raw_msg)
                        channel = msg.get("channel")
                        seq_num = int(msg.get("sequence_num", 0))
                        ts_ns = time.time_ns()

                        if channel == "market_trades":
                            for ev in msg.get("events", []):
                                for tr in ev.get("trades", []):
                                    canon = self.product_map.get(tr.get("product_id", ""))
                                    if canon and canon in self.books:
                                        self.books[canon].record_trade(
                                            price=float(tr["price"]),
                                            qty=float(tr["size"]),
                                            is_buyer_maker=(tr.get("side") == "SELL"),
                                            exchange_ts_ns=ts_ns,
                                        )
                        elif channel == "l2_data":
                            for ev in msg.get("events", []):
                                pid = ev.get("product_id", "")
                                canon = self.product_map.get(pid)
                                if not canon or canon not in self.books:
                                    continue
                                book = self.books[canon]
                                ev_type = ev.get("type")
                                bids: List[ tuple[float, float] ] = []
                                asks: List[ tuple[float, float] ] = []
                                for upd in ev.get("updates", []):
                                    px = float(upd["price_level"])
                                    qty = float(upd["new_quantity"])
                                    if upd.get("side") == "bid":
                                        bids.append((px, qty))
                                    else:
                                        asks.append((px, qty))

                                if ev_type == "snapshot" or not book.initialized:
                                    depth_ev = book.apply_snapshot(seq_num, bids, asks, ts_ns)
                                    await self.on_depth(depth_ev)
                                else:
                                    delta = BufferedDepthDelta(
                                        U=seq_num,
                                        u=seq_num,
                                        pu=book.last_update_id,
                                        bids=bids,
                                        asks=asks,
                                        exchange_ts_ns=ts_ns,
                                    )
                                    try:
                                        depth_ev = book.buffer_ws_delta(delta)
                                        if depth_ev is not None:
                                            await self.on_depth(depth_ev)
                                    except (SequenceGapError, BookParityError) as gap_err:
                                        logger.warning("[Coinbase:%s] %s", canon, gap_err)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[CoinbaseAdvanced] WebSocket error: %s. Reconnecting in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 15.0)

    def stop(self) -> None:
        self._running = False
