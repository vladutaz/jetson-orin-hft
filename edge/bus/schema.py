from __future__ import annotations

import struct
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Tuple
import msgpack


# Fixed C-struct binary layout for Shared Memory zero-copy L2 Top-of-Book slot (128 bytes aligned)
# Fields:
#   seq_id (uint64)
#   exchange_ts_ns (uint64)
#   ingest_ts_ns (uint64)
#   symbol_bytes (16s)
#   exchange_bytes (16s)
#   best_bid_px (double), best_bid_qty (double)
#   best_ask_px (double), best_ask_qty (double)
#   mid_px (double), micro_px (double)
#   spread_bps (double), book_imbalance (double)
#   last_trade_px (double), last_trade_qty (double)
SHM_SLOT_STRUCT = struct.Struct("<QQQ16s16sdddddddddd")
SHM_SLOT_SIZE = SHM_SLOT_STRUCT.size  # 136 bytes


@dataclass
class MarketDepthEvent:
    """
    Topic 1: market.depth.<symbol>
    Binary-serialized L2 order book snapshot + latest trade print.
    """
    exchange: str
    symbol: str
    sequence_id: int
    exchange_ts_ns: int
    ingest_ts_ns: int
    bids: List[Tuple[float, float]]  # Top N sorted descending [(price, qty), ...]
    asks: List[Tuple[float, float]]  # Top N sorted ascending [(price, qty), ...]
    last_trade_px: float = 0.0
    last_trade_qty: float = 0.0
    last_trade_is_buyer_maker: bool = False
    parity_valid: bool = True

    def to_bytes(self) -> bytes:
        payload = (
            1,  # schema version
            self.exchange,
            self.symbol,
            self.sequence_id,
            self.exchange_ts_ns,
            self.ingest_ts_ns,
            self.bids,
            self.asks,
            self.last_trade_px,
            self.last_trade_qty,
            self.last_trade_is_buyer_maker,
            self.parity_valid,
        )
        return msgpack.packb(payload, use_bin_type=True)

    @classmethod
    def from_bytes(cls, raw: bytes) -> MarketDepthEvent:
        unpacked = msgpack.unpackb(raw, raw=False)
        _, exch, sym, seq, ex_ts, in_ts, bids, asks, lt_px, lt_qty, lt_bm, parity = unpacked
        return cls(
            exchange=exch,
            symbol=sym,
            sequence_id=int(seq),
            exchange_ts_ns=int(ex_ts),
            ingest_ts_ns=int(in_ts),
            bids=[(float(p), float(q)) for p, q in bids],
            asks=[(float(p), float(q)) for p, q in asks],
            last_trade_px=float(lt_px),
            last_trade_qty=float(lt_qty),
            last_trade_is_buyer_maker=bool(lt_bm),
            parity_valid=bool(parity),
        )

    def pack_shm_slot(self) -> bytes:
        bid_px, bid_qty = self.bids[0] if self.bids else (0.0, 0.0)
        ask_px, ask_qty = self.asks[0] if self.asks else (0.0, 0.0)
        mid = 0.5 * (bid_px + ask_px) if (bid_px > 0.0 and ask_px > 0.0) else 0.0
        denom = bid_qty + ask_qty
        micro = ((bid_px * ask_qty) + (ask_px * bid_qty)) / denom if denom > 0.0 else mid
        spread_bps = ((ask_px - bid_px) / mid) * 10000.0 if mid > 0.0 else 0.0
        imbalance = (bid_qty - ask_qty) / denom if denom > 0.0 else 0.0
        return SHM_SLOT_STRUCT.pack(
            self.sequence_id,
            self.exchange_ts_ns,
            self.ingest_ts_ns,
            self.symbol.encode("ascii")[:16].ljust(16, b"\x00"),
            self.exchange.encode("ascii")[:16].ljust(16, b"\x00"),
            bid_px,
            bid_qty,
            ask_px,
            ask_qty,
            mid,
            micro,
            spread_bps,
            imbalance,
            self.last_trade_px,
            self.last_trade_qty,
        )

    @staticmethod
    def unpack_shm_slot(buf: bytes) -> Dict[str, Any]:
        (
            seq_id,
            ex_ts,
            in_ts,
            sym_b,
            ex_b,
            bid_px,
            bid_qty,
            ask_px,
            ask_qty,
            mid,
            micro,
            spread_bps,
            imbalance,
            lt_px,
            lt_qty,
        ) = SHM_SLOT_STRUCT.unpack(buf[:SHM_SLOT_SIZE])
        return {
            "sequence_id": seq_id,
            "exchange_ts_ns": ex_ts,
            "ingest_ts_ns": in_ts,
            "symbol": sym_b.rstrip(b"\x00").decode("ascii", errors="replace"),
            "exchange": ex_b.rstrip(b"\x00").decode("ascii", errors="replace"),
            "best_bid_px": bid_px,
            "best_bid_qty": bid_qty,
            "best_ask_px": ask_px,
            "best_ask_qty": ask_qty,
            "mid_px": mid,
            "micro_px": micro,
            "spread_bps": spread_bps,
            "book_imbalance": imbalance,
            "last_trade_px": lt_px,
            "last_trade_qty": lt_qty,
        }


@dataclass
class SentimentEvent:
    """
    Alternative Data / NLP Sentiment payload emitted on `signals.sentiment`.
    """
    source: str
    headline: str
    symbols: List[str]
    sentiment_score: float  # -1.0 to +1.0
    confidence: float       # 0.0 to 1.0
    inference_latency_ms: float
    published_ts_ns: int
    emitted_ts_ns: int

    def to_bytes(self) -> bytes:
        return msgpack.packb(asdict(self), use_bin_type=True)

    @classmethod
    def from_bytes(cls, raw: bytes) -> SentimentEvent:
        data = msgpack.unpackb(raw, raw=False)
        return cls(**data)


@dataclass
class AlphaSignalEvent:
    """
    Topic 2: signals.alpha
    Hardware-accelerated TensorRT prediction and online microstructure feature vector.
    """
    symbol: str
    exchange: str
    sequence_id: int
    exchange_ts_ns: int
    signal_ts_ns: int
    position_target: float         # -1.0 (max short) to +1.0 (max long)
    confidence: float              # 0.0 to 1.0
    stop_loss_scalar_bps: float    # Dynamic stop distance in bps
    predicted_vol_bps: float       # Predicted horizon volatility in bps
    ofi: float                     # Order Flow Imbalance
    vpin: float                    # Volume-Synchronized Probability of Informed Trading
    micro_price: float             # Volume-weighted top-of-book micro-price
    mid_price: float               # Top-of-book mid-price
    spread_bps: float              # Bid-Ask spread in bps
    depth_skew: float              # Multi-level L2 book depth skew
    realized_vol_bps: float        # Online realized volatility in bps
    vwap_1s: float
    vwap_5s: float
    vwap_30s: float
    vwap_300s: float
    sentiment_score: float         # Latest fused NLP sentiment polarity (-1.0 to +1.0)
    trt_inference_us: float        # TensorRT execution latency in microseconds

    def to_bytes(self) -> bytes:
        return msgpack.packb(asdict(self), use_bin_type=True)

    @classmethod
    def from_bytes(cls, raw: bytes) -> AlphaSignalEvent:
        data = msgpack.unpackb(raw, raw=False)
        return cls(**data)


@dataclass
class ExecutionEvent:
    """
    Topic 3: engine.execution
    Order lifecycle transitions, fills, cancellations, rejections, and risk events.
    """
    event_type: str        # ORDER_STATE, FILL, RISK_REJECT, CIRCUIT_BREAKER, KILL_SWITCH
    client_order_id: str
    exchange_order_id: str
    symbol: str
    side: str              # BUY or SELL
    order_type: str        # LIMIT_POST_ONLY, MARKET, CANCEL
    state: str             # PENDING_NEW, NEW, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED
    price: float
    quantity: float
    filled_quantity: float
    avg_fill_price: float
    fee_usd: float
    slippage_bps: float
    latency_us: float
    reason: str
    ts_ns: int

    def to_bytes(self) -> bytes:
        return msgpack.packb(asdict(self), use_bin_type=True)

    @classmethod
    def from_bytes(cls, raw: bytes) -> ExecutionEvent:
        data = msgpack.unpackb(raw, raw=False)
        return cls(**data)


@dataclass
class MobileTelemetryPayload:
    """
    Topic 4: telemetry.mobile
    Full state snapshot before 10Hz delta compression for mobile clients.
    """
    seq: int
    ts_ms: int
    engine_state: str  # ACTIVE, HALTED, CIRCUIT_BREAKER_TRIPPED
    equity_usd: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    daily_drawdown_pct: float
    daily_sharpe: float
    win_rate_pct: float
    margin_utilization_pct: float
    hardware: Dict[str, Any] = field(default_factory=dict)
    positions: Dict[str, Any] = field(default_factory=dict)
    signals: Dict[str, Any] = field(default_factory=dict)
    orderbooks: Dict[str, Any] = field(default_factory=dict)
    candles: Dict[str, Any] = field(default_factory=dict)
    active_orders: List[Dict[str, Any]] = field(default_factory=list)
    recent_fills: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_bytes(self) -> bytes:
        return msgpack.packb(self.to_dict(), use_bin_type=True)

    @classmethod
    def from_bytes(cls, raw: bytes) -> MobileTelemetryPayload:
        data = msgpack.unpackb(raw, raw=False)
        return cls(**data)
