from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time
from typing import Dict, Optional, Tuple

from edge.config import InstrumentLimit, RiskConfig


class EngineMode(str, Enum):
    ACTIVE = "ACTIVE"
    CIRCUIT_BREAKER_TRIPPED = "CIRCUIT_BREAKER_TRIPPED"
    HALTED = "HALTED"  # Triggered by Emergency Kill-Switch


@dataclass
class PositionState:
    symbol: str
    quantity: float = 0.0          # Signed: >0 Long, <0 Short
    avg_entry_price: float = 0.0
    mark_price: float = 0.0
    unrealized_pnl_usd: float = 0.0
    realized_pnl_usd: float = 0.0

    @property
    def notional_usd(self) -> float:
        ref_px = self.mark_price if self.mark_price > 0.0 else self.avg_entry_price
        return abs(self.quantity) * ref_px

    def update_mark(self, mark_px: float) -> None:
        if mark_px <= 0.0:
            return
        self.mark_price = mark_px
        if self.quantity != 0.0 and self.avg_entry_price > 0.0:
            self.unrealized_pnl_usd = (mark_px - self.avg_entry_price) * self.quantity
        else:
            self.unrealized_pnl_usd = 0.0

    def apply_fill(self, side: str, fill_qty: float, fill_px: float, fee_usd: float = 0.0) -> float:
        """
        Updates position quantity, average entry price, and realized PnL on an order fill.
        Returns the realized PnL delta (net of fee) from this fill.
        """
        signed_fill = fill_qty if side.upper() == "BUY" else -fill_qty
        realized_delta = -fee_usd

        if self.quantity == 0.0:
            self.quantity = signed_fill
            self.avg_entry_price = fill_px
        elif (self.quantity > 0 and signed_fill > 0) or (self.quantity < 0 and signed_fill < 0):
            # Increasing existing position
            total_qty = abs(self.quantity) + abs(signed_fill)
            self.avg_entry_price = (
                (abs(self.quantity) * self.avg_entry_price) + (abs(signed_fill) * fill_px)
            ) / total_qty
            self.quantity += signed_fill
        else:
            # Reducing, closing, or flipping position
            closed_qty = min(abs(self.quantity), abs(signed_fill))
            direction = 1.0 if self.quantity > 0 else -1.0
            realized_delta += closed_qty * (fill_px - self.avg_entry_price) * direction
            remaining_signed = self.quantity + signed_fill
            if abs(remaining_signed) < 1e-12:
                self.quantity = 0.0
                self.avg_entry_price = 0.0
            elif (remaining_signed > 0) != (self.quantity > 0):
                # Position flipped direction
                self.quantity = remaining_signed
                self.avg_entry_price = fill_px
            else:
                self.quantity = remaining_signed

        self.realized_pnl_usd += realized_delta
        self.update_mark(fill_px)
        return realized_delta


@dataclass(frozen=True)
class PreTradeCheckResult:
    allowed: bool
    reason: str
    code: str  # OK, HALTED, CIRCUIT_BREAKER, STALE_FEED, MAX_ORDER_SIZE, MAX_POSITION, FAT_FINGER, SLIPPAGE


class PreTradeRiskGatekeeper:
    """
    Institutional Pre-Trade Risk Engine with stateful Daily Drawdown Circuit Breaker,
    150ms Stale Feed Detector, Per-Instrument Order & Position Limits, and Fat-Finger / Slippage Filters.
    """

    def __init__(self, config: RiskConfig) -> None:
        self.config = config
        self.mode: EngineMode = EngineMode.ACTIVE
        self.high_water_equity_usd: float = config.initial_equity_usd
        self.day_start_equity_usd: float = config.initial_equity_usd
        self.positions: Dict[str, PositionState] = {
            sym: PositionState(symbol=sym) for sym in config.instrument_limits.keys()
        }
        self.total_trades: int = 0
        self.winning_trades: int = 0

    @property
    def realized_pnl_usd(self) -> float:
        return sum(p.realized_pnl_usd for p in self.positions.values())

    @property
    def unrealized_pnl_usd(self) -> float:
        return sum(p.unrealized_pnl_usd for p in self.positions.values())

    @property
    def current_equity_usd(self) -> float:
        return self.day_start_equity_usd + self.realized_pnl_usd + self.unrealized_pnl_usd

    @property
    def daily_drawdown_pct(self) -> float:
        if self.day_start_equity_usd <= 0.0:
            return 0.0
        net_change = self.current_equity_usd - self.day_start_equity_usd
        return max(0.0, -net_change / self.day_start_equity_usd)

    @property
    def margin_utilization_pct(self) -> float:
        eq = max(1.0, self.current_equity_usd)
        gross_notional = sum(p.notional_usd for p in self.positions.values())
        return (gross_notional / eq) * 100.0

    @property
    def win_rate_pct(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100.0

    def trigger_kill_switch(self) -> None:
        self.mode = EngineMode.HALTED

    def reset_halt(self) -> None:
        if self.daily_drawdown_pct < self.config.max_daily_drawdown_pct:
            self.mode = EngineMode.ACTIVE

    def evaluate_circuit_breaker(self) -> bool:
        """
        Trips the circuit breaker if daily loss exceeds `max_daily_drawdown_pct` (3.0%).
        Returns True if the circuit breaker is currently tripped.
        """
        if self.daily_drawdown_pct >= self.config.max_daily_drawdown_pct:
            if self.mode == EngineMode.ACTIVE:
                self.mode = EngineMode.CIRCUIT_BREAKER_TRIPPED
            return True
        return self.mode == EngineMode.CIRCUIT_BREAKER_TRIPPED

    def validate_order(
        self,
        symbol: str,
        side: str,
        order_price: float,
        order_qty: float,
        mid_price: float,
        spread_bps: float,
        book_exchange_ts_ns: int,
        now_ts_ns: Optional[int] = None,
        reduce_only: bool = False,
    ) -> PreTradeCheckResult:
        """
        Executes all pre-trade risk gate checks synchronously in <5 microseconds.
        """
        # 1. Kill-Switch / Halted Gate
        if self.mode == EngineMode.HALTED and not reduce_only:
            return PreTradeCheckResult(False, "Strategy state machine is HALTED by Kill-Switch", "HALTED")

        # 2. Daily Drawdown Circuit Breaker Gate (3.0% hard stop)
        if self.evaluate_circuit_breaker() and not reduce_only:
            return PreTradeCheckResult(
                False,
                f"Daily drawdown circuit breaker tripped ({self.daily_drawdown_pct * 100:.2f}% >= {self.config.max_daily_drawdown_pct * 100:.2f}%)",
                "CIRCUIT_BREAKER",
            )

        # 3. Stale Feed Detector Gate (>150ms order book age rejected)
        now_ns = now_ts_ns if now_ts_ns is not None else time.time_ns()
        feed_age_ms = (now_ns - book_exchange_ts_ns) / 1_000_000.0
        if feed_age_ms > self.config.max_stale_book_ms and not reduce_only:
            return PreTradeCheckResult(
                False,
                f"Stale L2 market data feed ({feed_age_ms:.1f}ms > {self.config.max_stale_book_ms:.1f}ms)",
                "STALE_FEED",
            )

        # 4. Instrument Lookup
        limit: Optional[InstrumentLimit] = self.config.instrument_limits.get(symbol)
        if limit is None:
            return PreTradeCheckResult(False, f"Unconfigured instrument {symbol}", "UNCONFIGURED_SYMBOL")

        if order_price <= 0.0 or order_qty <= 0.0 or mid_price <= 0.0:
            return PreTradeCheckResult(False, "Invalid non-positive price or quantity", "INVALID_PARAMS")

        # 5. Fat-Finger Filter Gate (checks limit price distance against mid-price)
        dist_bps = abs(order_price - mid_price) / mid_price * 10000.0
        if dist_bps > self.config.max_fat_finger_bps and not reduce_only:
            return PreTradeCheckResult(
                False,
                f"Fat-finger filter triggered: limit distance {dist_bps:.1f} bps > {self.config.max_fat_finger_bps:.1f} bps",
                "FAT_FINGER",
            )

        # 6. Slippage & Spread Filter Gate
        if spread_bps > self.config.max_slippage_bps * 2.0 and not reduce_only:
            return PreTradeCheckResult(
                False,
                f"Spread/slippage filter triggered: spread {spread_bps:.1f} bps exceeds threshold",
                "SLIPPAGE",
            )

        # 7. Maximum Single Order Notional Gate
        order_notional = order_price * order_qty
        if order_notional > limit.max_order_notional_usd and not reduce_only:
            return PreTradeCheckResult(
                False,
                f"Order notional ${order_notional:,.2f} exceeds max order limit ${limit.max_order_notional_usd:,.2f}",
                "MAX_ORDER_SIZE",
            )

        # 8. Maximum Position Notional Limit Gate
        pos = self.positions.setdefault(symbol, PositionState(symbol=symbol))
        signed_order_qty = order_qty if side.upper() == "BUY" else -order_qty
        projected_qty = pos.quantity + signed_order_qty
        projected_notional = abs(projected_qty) * mid_price
        if projected_notional > limit.max_position_notional_usd and not reduce_only:
            return PreTradeCheckResult(
                False,
                f"Projected position notional ${projected_notional:,.2f} exceeds max position limit ${limit.max_position_notional_usd:,.2f}",
                "MAX_POSITION",
            )

        return PreTradeCheckResult(True, "Pre-trade risk checks passed", "OK")

    def on_fill(self, symbol: str, side: str, fill_qty: float, fill_px: float, fee_usd: float = 0.0) -> Tuple[float, bool]:
        pos = self.positions.setdefault(symbol, PositionState(symbol=symbol))
        realized_delta = pos.apply_fill(side, fill_qty, fill_px, fee_usd)
        if abs(realized_delta) > 1e-6:
            self.total_trades += 1
            if realized_delta > 0:
                self.winning_trades += 1
        tripped = self.evaluate_circuit_breaker()
        return realized_delta, tripped
