from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Dict, List, Optional, Set


class OrderState(str, Enum):
    PENDING_NEW = "PENDING_NEW"
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


VALID_STATE_TRANSITIONS: Dict[OrderState, Set[OrderState]] = {
    OrderState.PENDING_NEW: {
        OrderState.NEW,
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELED,
        OrderState.REJECTED,
    },
    OrderState.NEW: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELED,
        OrderState.REJECTED,
    },
    OrderState.PARTIALLY_FILLED: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELED,
    },
    OrderState.FILLED: set(),
    OrderState.CANCELED: set(),
    OrderState.REJECTED: set(),
}


class InvalidOrderTransitionError(Exception):
    """Raised when an invalid deterministic order state transition is attempted."""


@dataclass
class TrackedOrder:
    client_order_id: str
    symbol: str
    side: str                  # BUY or SELL
    order_type: str            # LIMIT_POST_ONLY, MARKET
    price: float
    quantity: float
    reference_mid_price: float
    created_ts_ns: int = field(default_factory=time.time_ns)
    updated_ts_ns: int = field(default_factory=time.time_ns)
    exchange_order_id: str = ""
    state: OrderState = OrderState.PENDING_NEW
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    fee_usd: float = 0.0
    slippage_bps: float = 0.0
    ack_latency_us: float = 0.0
    reason: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.state in (OrderState.FILLED, OrderState.CANCELED, OrderState.REJECTED)

    @property
    def remaining_quantity(self) -> float:
        return max(0.0, self.quantity - self.filled_quantity)


class OrderStateMachine:
    """
    Deterministic Order Lifecycle State Machine tracking all active and historical orders:
      `PENDING_NEW` -> `NEW` -> `PARTIALLY_FILLED` -> `FILLED` / `CANCELED` / `REJECTED`
    """

    def __init__(self) -> None:
        self._orders: Dict[str, TrackedOrder] = {}

    def create_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        price: float,
        quantity: float,
        reference_mid_price: float,
    ) -> TrackedOrder:
        order = TrackedOrder(
            client_order_id=client_order_id,
            symbol=symbol,
            side=side.upper(),
            order_type=order_type,
            price=price,
            quantity=quantity,
            reference_mid_price=reference_mid_price,
        )
        self._orders[client_order_id] = order
        return order

    def transition(
        self,
        client_order_id: str,
        target_state: OrderState,
        exchange_order_id: Optional[str] = None,
        fill_qty_delta: float = 0.0,
        fill_price: float = 0.0,
        fee_delta_usd: float = 0.0,
        reason: str = "",
    ) -> TrackedOrder:
        order = self._orders.get(client_order_id)
        if order is None:
            raise KeyError(f"Unknown client_order_id: {client_order_id}")

        allowed = VALID_STATE_TRANSITIONS.get(order.state, set())
        if target_state not in allowed:
            raise InvalidOrderTransitionError(
                f"Illegal order transition for {client_order_id}: {order.state.value} -> {target_state.value}"
            )

        now_ns = time.time_ns()
        if order.state == OrderState.PENDING_NEW and order.ack_latency_us == 0.0:
            order.ack_latency_us = (now_ns - order.created_ts_ns) / 1000.0

        if exchange_order_id:
            order.exchange_order_id = exchange_order_id

        if fill_qty_delta > 0.0 and fill_price > 0.0:
            prev_notional = order.filled_quantity * order.avg_fill_price
            new_total_qty = order.filled_quantity + fill_qty_delta
            order.avg_fill_price = (prev_notional + (fill_qty_delta * fill_price)) / new_total_qty
            order.filled_quantity = new_total_qty
            order.fee_usd += fee_delta_usd
            if order.reference_mid_price > 0.0:
                direction = 1.0 if order.side == "BUY" else -1.0
                order.slippage_bps = (
                    ((order.avg_fill_price - order.reference_mid_price) / order.reference_mid_price)
                    * 10000.0
                    * direction
                )

        order.state = target_state
        order.updated_ts_ns = now_ns
        if reason:
            order.reason = reason
        return order

    def get_order(self, client_order_id: str) -> Optional[TrackedOrder]:
        return self._orders.get(client_order_id)

    def active_orders(self, symbol: Optional[str] = None) -> List[TrackedOrder]:
        return [
            o
            for o in self._orders.values()
            if not o.is_terminal and (symbol is None or o.symbol == symbol)
        ]

    def prune_terminal_orders(self, max_retained: int = 500) -> None:
        terminals = [o for o in self._orders.values() if o.is_terminal]
        if len(terminals) > max_retained:
            terminals.sort(key=lambda x: x.updated_ts_ns)
            for old in terminals[: len(terminals) - max_retained]:
                self._orders.pop(old.client_order_id, None)
