from __future__ import annotations

from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Dict, List

from edge.execution.state_machine import TrackedOrder


class ExecutionWallLedger:
    """
    SQLite Write-Ahead Logging (WAL) persistent institutional trade ledger recording:
      - Order lifecycle transitions (`orders` table)
      - Execution fills, fees, latency metrics, and slippage (`fills` table)
      - Pre-trade risk rejections and circuit breaker/Kill-Switch events (`risk_events` table)
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_wal_schema()

    def _init_wal_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")
            cur.execute("PRAGMA temp_store=MEMORY;")
            cur.execute("PRAGMA mmap_size=67108864;")  # 64MB mmap for fast edge I/O
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    client_order_id TEXT PRIMARY KEY,
                    exchange_order_id TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    filled_quantity REAL NOT NULL,
                    avg_fill_price REAL NOT NULL,
                    reference_mid_price REAL NOT NULL,
                    fee_usd REAL NOT NULL,
                    slippage_bps REAL NOT NULL,
                    ack_latency_us REAL NOT NULL,
                    reason TEXT,
                    created_ts_ns INTEGER NOT NULL,
                    updated_ts_ns INTEGER NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fills (
                    fill_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_order_id TEXT NOT NULL,
                    exchange_order_id TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    fill_price REAL NOT NULL,
                    fill_qty REAL NOT NULL,
                    fee_usd REAL NOT NULL,
                    realized_pnl_usd REAL NOT NULL,
                    slippage_bps REAL NOT NULL,
                    latency_us REAL NOT NULL,
                    ts_ns INTEGER NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS risk_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    symbol TEXT,
                    code TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    equity_usd REAL NOT NULL,
                    drawdown_pct REAL NOT NULL,
                    ts_ns INTEGER NOT NULL
                );
                """
            )
            self._conn.commit()

    def upsert_order(self, order: TrackedOrder) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO orders (
                    client_order_id, exchange_order_id, symbol, side, order_type, state,
                    price, quantity, filled_quantity, avg_fill_price, reference_mid_price,
                    fee_usd, slippage_bps, ack_latency_us, reason, created_ts_ns, updated_ts_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_order_id) DO UPDATE SET
                    exchange_order_id=excluded.exchange_order_id,
                    state=excluded.state,
                    filled_quantity=excluded.filled_quantity,
                    avg_fill_price=excluded.avg_fill_price,
                    fee_usd=excluded.fee_usd,
                    slippage_bps=excluded.slippage_bps,
                    ack_latency_us=excluded.ack_latency_us,
                    reason=excluded.reason,
                    updated_ts_ns=excluded.updated_ts_ns;
                """,
                (
                    order.client_order_id,
                    order.exchange_order_id,
                    order.symbol,
                    order.side,
                    order.order_type,
                    order.state.value,
                    order.price,
                    order.quantity,
                    order.filled_quantity,
                    order.avg_fill_price,
                    order.reference_mid_price,
                    order.fee_usd,
                    order.slippage_bps,
                    order.ack_latency_us,
                    order.reason,
                    order.created_ts_ns,
                    order.updated_ts_ns,
                ),
            )
            self._conn.commit()

    def record_fill(
        self,
        order: TrackedOrder,
        fill_price: float,
        fill_qty: float,
        fee_usd: float,
        realized_pnl_usd: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO fills (
                    client_order_id, exchange_order_id, symbol, side,
                    fill_price, fill_qty, fee_usd, realized_pnl_usd,
                    slippage_bps, latency_us, ts_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    order.client_order_id,
                    order.exchange_order_id,
                    order.symbol,
                    order.side,
                    fill_price,
                    fill_qty,
                    fee_usd,
                    realized_pnl_usd,
                    order.slippage_bps,
                    order.ack_latency_us,
                    time.time_ns(),
                ),
            )
            self._conn.commit()

    def record_risk_event(
        self,
        event_type: str,
        symbol: str,
        code: str,
        reason: str,
        equity_usd: float,
        drawdown_pct: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO risk_events (
                    event_type, symbol, code, reason, equity_usd, drawdown_pct, ts_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    event_type,
                    symbol,
                    code,
                    reason,
                    equity_usd,
                    drawdown_pct,
                    time.time_ns(),
                ),
            )
            self._conn.commit()

    def get_recent_fills(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM fills ORDER BY fill_id DESC LIMIT ?;",
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_recent_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM orders ORDER BY updated_ts_ns DESC LIMIT ?;",
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
