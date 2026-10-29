from __future__ import annotations

import time
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from edge.bus.schema import MarketDepthEvent


class SequenceGapError(Exception):
    """Raised when an L2 sequence gap (`U`, `u`, `pu`) is detected requiring snapshot resync."""


class BookParityError(Exception):
    """Raised when local L2 order book fails crossed-book or checksum parity validation."""


@dataclass
class BufferedDepthDelta:
    U: int  # First update ID in event
    u: int  # Final update ID in event
    pu: int  # Previous final update ID (`pu` on Binance Futures / Bybit sequence)
    bids: List[Tuple[float, float]]
    asks: List[Tuple[float, float]]
    exchange_ts_ns: int
    checksum: Optional[int] = None


class LocalL2OrderBook:
    """
    Deterministic Local L2 Order Book with sequence buffering, delta reconstruction,
    Binance Futures (`U`, `u`, `pu`) / Bybit sequence validation, and CRC32/crossed-book parity checks.
    """

    def __init__(self, exchange: str, symbol: str, max_depth: int = 50) -> None:
        self.exchange = exchange
        self.symbol = symbol
        self.max_depth = max_depth
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        self.last_update_id: int = 0
        self.initialized: bool = False
        self.delta_buffer: List[BufferedDepthDelta] = []
        self.last_trade_px: float = 0.0
        self.last_trade_qty: float = 0.0
        self.last_trade_is_buyer_maker: bool = False
        self.last_exchange_ts_ns: int = 0
        self.resync_count: int = 0

    def reset_for_resync(self) -> None:
        self.bids.clear()
        self.asks.clear()
        self.last_update_id = 0
        self.initialized = False
        self.resync_count += 1

    def buffer_ws_delta(self, delta: BufferedDepthDelta) -> Optional[MarketDepthEvent]:
        """
        Buffers incoming WebSocket delta messages while waiting for REST snapshot initialization,
        or applies immediately if the book is already synchronized.
        """
        if not self.initialized:
            self.delta_buffer.append(delta)
            # Cap pre-snapshot buffer to prevent unbounded memory growth
            if len(self.delta_buffer) > 2000:
                self.delta_buffer = self.delta_buffer[-1000:]
            return None

        self._apply_sequenced_delta(delta)
        return self.to_depth_event()

    def apply_snapshot(
        self,
        last_update_id: int,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        exchange_ts_ns: Optional[int] = None,
    ) -> MarketDepthEvent:
        """
        Initializes the order book from a REST/WS snapshot and replays buffered deltas
        following standard institutional sequence reconciliation rules:
          1. Drop buffered events where `u < lastUpdateId`.
          2. First processed event must satisfy `U <= lastUpdateId` and `u >= lastUpdateId`
             (or `U <= lastUpdateId + 1` on spot/linear venues).
          3. Subsequent events must satisfy `pu == prev_u` (or `U == prev_u + 1`).
        """
        self.bids = {float(p): float(q) for p, q in bids if float(q) > 0.0}
        self.asks = {float(p): float(q) for p, q in asks if float(q) > 0.0}
        self.last_update_id = int(last_update_id)
        self.last_exchange_ts_ns = exchange_ts_ns or time.time_ns()
        self.initialized = True

        pending = list(self.delta_buffer)
        self.delta_buffer.clear()

        first_applied = False
        for delta in pending:
            if delta.u <= self.last_update_id:
                continue
            if not first_applied:
                if delta.U <= self.last_update_id + 1 <= delta.u:
                    self._apply_price_levels(delta.bids, delta.asks)
                    self.last_update_id = delta.u
                    self.last_exchange_ts_ns = delta.exchange_ts_ns
                    first_applied = True
                elif delta.U > self.last_update_id + 1:
                    self.reset_for_resync()
                    raise SequenceGapError(
                        f"[{self.exchange}:{self.symbol}] Snapshot gap: snapshot={self.last_update_id}, first delta U={delta.U}"
                    )
            else:
                self._apply_sequenced_delta(delta)

        self.validate_parity()
        return self.to_depth_event()

    def _apply_sequenced_delta(self, delta: BufferedDepthDelta) -> None:
        if delta.u <= self.last_update_id:
            return

        # Verify sequence continuity via `pu` (Binance Futures) or `U == last_update_id + 1`
        if delta.pu > 0:
            if delta.pu != self.last_update_id:
                self.reset_for_resync()
                raise SequenceGapError(
                    f"[{self.exchange}:{self.symbol}] Sequence gap detected: expected pu={self.last_update_id}, got pu={delta.pu} (U={delta.U}, u={delta.u})"
                )
        else:
            if delta.U > self.last_update_id + 1:
                self.reset_for_resync()
                raise SequenceGapError(
                    f"[{self.exchange}:{self.symbol}] Sequence range gap: last_u={self.last_update_id}, delta U={delta.U}"
                )

        self._apply_price_levels(delta.bids, delta.asks)
        self.last_update_id = delta.u
        self.last_exchange_ts_ns = delta.exchange_ts_ns

        if delta.checksum is not None:
            computed = self.compute_crc32_checksum()
            if computed != (delta.checksum & 0xFFFFFFFF):
                self.reset_for_resync()
                raise BookParityError(
                    f"[{self.exchange}:{self.symbol}] CRC32 mismatch: expected={delta.checksum}, computed={computed}"
                )

        self.validate_parity()

    def _apply_price_levels(
        self,
        bid_updates: List[Tuple[float, float]],
        ask_updates: List[Tuple[float, float]],
    ) -> None:
        for px, qty in bid_updates:
            if qty <= 0.0:
                self.bids.pop(px, None)
            else:
                self.bids[px] = qty

        for px, qty in ask_updates:
            if qty <= 0.0:
                self.asks.pop(px, None)
            else:
                self.asks[px] = qty

    def record_trade(self, price: float, qty: float, is_buyer_maker: bool, exchange_ts_ns: int) -> None:
        self.last_trade_px = price
        self.last_trade_qty = qty
        self.last_trade_is_buyer_maker = is_buyer_maker
        if exchange_ts_ns > self.last_exchange_ts_ns:
            self.last_exchange_ts_ns = exchange_ts_ns

    def top_bids(self, depth: Optional[int] = None) -> List[Tuple[float, float]]:
        limit = depth or self.max_depth
        sorted_bids = sorted(self.bids.items(), key=lambda x: x[0], reverse=True)
        if len(sorted_bids) > self.max_depth * 2:
            # Prune deep out-of-range levels to keep dictionary lookup O(1) fast
            self.bids = dict(sorted_bids[: self.max_depth * 2])
        return sorted_bids[:limit]

    def top_asks(self, depth: Optional[int] = None) -> List[Tuple[float, float]]:
        limit = depth or self.max_depth
        sorted_asks = sorted(self.asks.items(), key=lambda x: x[0])
        if len(sorted_asks) > self.max_depth * 2:
            self.asks = dict(sorted_asks[: self.max_depth * 2])
        return sorted_asks[:limit]

    def validate_parity(self) -> bool:
        if not self.bids or not self.asks:
            raise BookParityError(f"[{self.exchange}:{self.symbol}] Empty bid or ask side in order book")
        best_bid = max(self.bids.keys())
        best_ask = min(self.asks.keys())
        if best_bid >= best_ask:
            self.reset_for_resync()
            raise BookParityError(
                f"[{self.exchange}:{self.symbol}] Crossed order book detected: best_bid={best_bid} >= best_ask={best_ask}"
            )
        return True

    def compute_crc32_checksum(self) -> int:
        """
        Computes standard top-10 interleaved bid/ask CRC32 checksum.
        """
        bids_10 = self.top_bids(10)
        asks_10 = self.top_asks(10)
        parts: List[str] = []
        for i in range(max(len(bids_10), len(asks_10))):
            if i < len(bids_10):
                parts.append(f"{bids_10[i][0]:g}:{bids_10[i][1]:g}")
            if i < len(asks_10):
                parts.append(f"{asks_10[i][0]:g}:{asks_10[i][1]:g}")
        payload = ":".join(parts).encode("ascii")
        return zlib.crc32(payload) & 0xFFFFFFFF

    def to_depth_event(self) -> MarketDepthEvent:
        now_ns = time.time_ns()
        bids = self.top_bids(self.max_depth)
        asks = self.top_asks(self.max_depth)
        parity_ok = bool(bids and asks and bids[0][0] < asks[0][0])
        return MarketDepthEvent(
            exchange=self.exchange,
            symbol=self.symbol,
            sequence_id=self.last_update_id,
            exchange_ts_ns=self.last_exchange_ts_ns or now_ns,
            ingest_ts_ns=now_ns,
            bids=bids,
            asks=asks,
            last_trade_px=self.last_trade_px or (0.5 * (bids[0][0] + asks[0][0]) if parity_ok else 0.0),
            last_trade_qty=self.last_trade_qty,
            last_trade_is_buyer_maker=self.last_trade_is_buyer_maker,
            parity_valid=parity_ok,
        )
