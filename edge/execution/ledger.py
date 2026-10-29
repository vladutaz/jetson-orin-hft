from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Dict, List

from edge.execution.state_machine import TrackedOrder


class ExecutionWallLedger:
    """
    SQLite Write-Ahead Logging (WAL) persistent institutional trade & portfolio ledger recording:
      - Order lifecycle transitions (`orders` table)
      - Execution fills, fees, latency metrics, and slippage (`fills` table)
      - Pre-trade risk rejections and circuit breaker/Kill-Switch events (`risk_events` table)
      - Saved invested stocks & status tracking (`invested_stocks` table)
      - Country macroeconomic & tax rates (`country_macro_state` table)
      - Real-time stock status, CPI, inflation & tax change notifications (`portfolio_notifications` table)
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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS invested_stocks (
                    ticker TEXT PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    country_code TEXT NOT NULL,
                    shares REAL NOT NULL,
                    avg_buy_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    currency TEXT NOT NULL,
                    sector TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sentiment_score REAL NOT NULL,
                    last_catalyst_headline TEXT NOT NULL,
                    last_catalyst_source TEXT NOT NULL,
                    updated_ts_ms INTEGER NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS country_macro_state (
                    country_code TEXT PRIMARY KEY,
                    country_name TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    inflation_rate_yoy_pct REAL NOT NULL,
                    cpi_index_yoy_pct REAL NOT NULL,
                    cpi_mom_pct REAL NOT NULL,
                    central_bank_rate_pct REAL NOT NULL,
                    corporate_tax_rate_pct REAL NOT NULL,
                    capital_gains_tax_pct REAL NOT NULL,
                    last_updated_source TEXT NOT NULL,
                    updated_ts_ms INTEGER NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolio_notifications (
                    notification_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    country_code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    source TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    previous_value REAL NOT NULL,
                    new_value REAL NOT NULL,
                    affected_tickers_json TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            self._conn.commit()

    def upsert_order(self, order: TrackedOrder) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO orders ("
                "client_order_id, exchange_order_id, symbol, side, order_type, state, "
                "price, quantity, filled_quantity, avg_fill_price, reference_mid_price, "
                "fee_usd, slippage_bps, ack_latency_us, reason, created_ts_ns, updated_ts_ns"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
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

    def upsert_invested_stock(self, stock_dict: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO invested_stocks ("
                "ticker, company_name, country_code, shares, avg_buy_price, current_price, "
                "currency, sector, status, sentiment_score, last_catalyst_headline, "
                "last_catalyst_source, updated_ts_ms"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (
                    stock_dict["ticker"],
                    stock_dict["company_name"],
                    stock_dict["country_code"],
                    stock_dict["shares"],
                    stock_dict["avg_buy_price"],
                    stock_dict["current_price"],
                    stock_dict["currency"],
                    stock_dict["sector"],
                    stock_dict["status"],
                    stock_dict["sentiment_score"],
                    stock_dict["last_catalyst_headline"],
                    stock_dict["last_catalyst_source"],
                    stock_dict["updated_ts_ms"],
                ),
            )
            self._conn.commit()

    def delete_invested_stock(self, ticker: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM invested_stocks WHERE ticker = ?;", (ticker,))
            self._conn.commit()

    def load_invested_stocks_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM invested_stocks ORDER BY ticker ASC;")
            return [dict(row) for row in cur.fetchall()]

    def upsert_country_macro(self, macro_dict: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO country_macro_state ("
                "country_code, country_name, currency, inflation_rate_yoy_pct, "
                "cpi_index_yoy_pct, cpi_mom_pct, central_bank_rate_pct, "
                "corporate_tax_rate_pct, capital_gains_tax_pct, last_updated_source, updated_ts_ms"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (
                    macro_dict["country_code"],
                    macro_dict["country_name"],
                    macro_dict["currency"],
                    macro_dict["inflation_rate_yoy_pct"],
                    macro_dict["cpi_index_yoy_pct"],
                    macro_dict["cpi_mom_pct"],
                    macro_dict["central_bank_rate_pct"],
                    macro_dict["corporate_tax_rate_pct"],
                    macro_dict["capital_gains_tax_pct"],
                    macro_dict["last_updated_source"],
                    macro_dict["updated_ts_ms"],
                ),
            )
            self._conn.commit()

    def load_country_macro_all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM country_macro_state;")
            return {row["country_code"]: dict(row) for row in cur.fetchall()}

    def insert_portfolio_notification(self, notif_dict: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO portfolio_notifications ("
                "notification_id, category, severity, ticker, country_code, title, "
                "message, source, metric_name, previous_value, new_value, "
                "affected_tickers_json, ts_ms, acknowledged"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (
                    notif_dict["notification_id"],
                    notif_dict["category"],
                    notif_dict["severity"],
                    notif_dict["ticker"],
                    notif_dict["country_code"],
                    notif_dict["title"],
                    notif_dict["message"],
                    notif_dict["source"],
                    notif_dict["metric_name"],
                    notif_dict["previous_value"],
                    notif_dict["new_value"],
                    json.dumps(notif_dict.get("affected_tickers", [])),
                    notif_dict["ts_ms"],
                    1 if notif_dict.get("acknowledged") else 0,
                ),
            )
            self._conn.commit()

    def get_portfolio_notifications(self, limit: int = 40) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM portfolio_notifications ORDER BY ts_ms DESC LIMIT ?;",
                (limit,),
            )
            rows = []
            for r in cur.fetchall():
                d = dict(r)
                d["affected_tickers"] = json.loads(d.pop("affected_tickers_json", "[]"))
                d["acknowledged"] = bool(d["acknowledged"])
                rows.append(d)
            return rows

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
