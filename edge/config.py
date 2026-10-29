from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import yaml


@dataclass(frozen=True)
class InstrumentLimit:
    max_order_notional_usd: float
    max_position_notional_usd: float
    tick_size: float
    lot_size: float


@dataclass(frozen=True)
class SystemConfig:
    node_id: str = "jetson-orin-agx-01"
    environment: str = "production"
    watchdog_device: str = "/dev/watchdog"
    watchdog_interval_sec: int = 5
    cpu_cores_ingest: List[int] = field(default_factory=lambda: [0, 1, 2, 3])
    cpu_cores_engine: List[int] = field(default_factory=lambda: [4, 5, 6, 7])
    cpu_cores_bridge: List[int] = field(default_factory=lambda: [8, 9])


@dataclass(frozen=True)
class IPCConfig:
    pub_market_endpoint: str = "ipc:///tmp/jetson_market.ipc"
    pub_signals_endpoint: str = "ipc:///tmp/jetson_signals.ipc"
    pub_execution_endpoint: str = "ipc:///tmp/jetson_execution.ipc"
    pub_telemetry_endpoint: str = "ipc:///tmp/jetson_telemetry.ipc"
    cmd_router_endpoint: str = "ipc:///tmp/jetson_cmd_router.ipc"
    shm_segment_name: str = "/jetson_l2_ring"
    shm_slot_count: int = 1024

    def resolved_endpoint(self, endpoint: str) -> str:
        """
        Uses Unix Domain IPC sockets on Linux/Jetson L4T and maps deterministically
        to loopback TCP ports on Windows development hosts where ipc:// is unsupported.
        """
        if sys.platform != "win32" or not endpoint.startswith("ipc://"):
            return endpoint
        port_map = {
            "ipc:///tmp/jetson_market.ipc": "tcp://127.0.0.1:19501",
            "ipc:///tmp/jetson_signals.ipc": "tcp://127.0.0.1:19502",
            "ipc:///tmp/jetson_execution.ipc": "tcp://127.0.0.1:19503",
            "ipc:///tmp/jetson_telemetry.ipc": "tcp://127.0.0.1:19504",
            "ipc:///tmp/jetson_cmd_router.ipc": "tcp://127.0.0.1:19505",
        }
        return port_map.get(endpoint, "tcp://127.0.0.1:19599")


@dataclass(frozen=True)
class IngestionConfig:
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    binance_enabled: bool = True
    binance_ws_url: str = "wss://fstream.binance.com/stream"
    binance_rest_snapshot_url: str = "https://fapi.binance.com/fapi/v1/depth"
    bybit_enabled: bool = True
    bybit_ws_url: str = "wss://stream.bybit.com/v5/public/linear"
    coinbase_enabled: bool = True
    coinbase_ws_url: str = "wss://advanced-trade-ws.coinbase.com"
    coinbase_product_ids: List[str] = field(default_factory=lambda: ["BTC-USD", "ETH-USD", "SOL-USD"])
    depth_levels: int = 50
    news_poll_interval_sec: float = 2.0
    rate_limit_capacity: float = 30.0
    rate_limit_refill_per_sec: float = 5.0
    news_feeds: List[str] = field(default_factory=list)
    proxies: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PredictionConfig:
    feature_window_ticks: int = 256
    vpin_bucket_volume: float = 50.0
    vpin_num_buckets: int = 50
    vwap_horizons_sec: List[float] = field(default_factory=lambda: [1.0, 5.0, 30.0, 300.0])
    trt_alpha_engine_path: str = "/opt/jetson-hft/models/alpha_tft_fp16.engine"
    trt_sentiment_engine_path: str = "/opt/jetson-hft/models/finbert_int8.engine"
    precision: str = "FP16"
    dla_core: int = -1


@dataclass(frozen=True)
class RiskConfig:
    initial_equity_usd: float = 250000.0
    max_daily_drawdown_pct: float = 0.03
    max_stale_book_ms: float = 150.0
    max_fat_finger_bps: float = 75.0
    max_slippage_bps: float = 15.0
    min_signal_confidence: float = 0.58
    instrument_limits: Dict[str, InstrumentLimit] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionConfig:
    exchange: str = "binance_futures"
    rest_base_url: str = "https://fapi.binance.com"
    ws_api_url: str = "wss://ws-fapi.binance.com/ws-fapi/v1"
    api_key_env: str = "JETSON_EXCHANGE_API_KEY"
    ed25519_privkey_env: str = "JETSON_ED25519_PRIVATE_KEY_PEM"
    sor_maker_chase_interval_ms: int = 40
    sor_max_chase_attempts: int = 6
    ledger_sqlite_path: str = "data/jetson_execution_ledger.db"
    paper_trading: bool = False


@dataclass(frozen=True)
class GatewayConfig:
    bind_host: str = "0.0.0.0"
    bind_port: int = 8443
    tls_cert_path: str = "config/certs/server.crt"
    tls_key_path: str = "config/certs/server.key"
    mtls_ca_path: str = "config/certs/client_ca.crt"
    relay_outbound_url: str = ""
    broadcast_hz: float = 10.0
    jwt_ttl_seconds: int = 900
    authorized_mobile_pubkeys: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PlatformSettings:
    system: SystemConfig
    ipc: IPCConfig
    ingestion: IngestionConfig
    prediction: PredictionConfig
    risk: RiskConfig
    execution: ExecutionConfig
    gateway: GatewayConfig


def load_settings(config_path: Optional[ str | Path ] = None) -> PlatformSettings:
    if config_path is None:
        config_path = os.environ.get(
            "JETSON_CONFIG_PATH",
            str(Path(__file__).resolve().parent.parent / "config" / "settings.yaml"),
        )
    path = Path(config_path)
    if not path.exists():
        default_limits = {
            "BTCUSDT": InstrumentLimit(50000.0, 150000.0, 0.10, 0.001),
            "ETHUSDT": InstrumentLimit(35000.0, 100000.0, 0.01, 0.01),
            "SOLUSDT": InstrumentLimit(25000.0, 75000.0, 0.01, 0.1),
        }
        return PlatformSettings(
            system=SystemConfig(),
            ipc=IPCConfig(),
            ingestion=IngestionConfig(),
            prediction=PredictionConfig(),
            risk=RiskConfig(instrument_limits=default_limits),
            execution=ExecutionConfig(),
            gateway=GatewayConfig(),
        )

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    sys_raw = raw.get("system", {})
    ipc_raw = raw.get("ipc", {})
    ing_raw = raw.get("ingestion", {})
    ex_raw = ing_raw.get("exchanges", {})
    news_raw = ing_raw.get("news_scraper", {})
    pred_raw = raw.get("prediction", {})
    risk_raw = raw.get("risk", {})
    exec_raw = raw.get("execution", {})
    gw_raw = raw.get("gateway", {})

    limits: Dict[str, InstrumentLimit] = {}
    for sym, l_cfg in risk_raw.get("instrument_limits", {}).items():
        limits[sym] = InstrumentLimit(
            max_order_notional_usd=float(l_cfg["max_order_notional_usd"]),
            max_position_notional_usd=float(l_cfg["max_position_notional_usd"]),
            tick_size=float(l_cfg["tick_size"]),
            lot_size=float(l_cfg["lot_size"]),
        )

    return PlatformSettings(
        system=SystemConfig(
            node_id=sys_raw.get("node_id", "jetson-orin-agx-01"),
            environment=sys_raw.get("environment", "production"),
            watchdog_device=sys_raw.get("watchdog_device", "/dev/watchdog"),
            watchdog_interval_sec=int(sys_raw.get("watchdog_interval_sec", 5)),
            cpu_cores_ingest=list(sys_raw.get("cpu_cores_ingest", [0, 1, 2, 3])),
            cpu_cores_engine=list(sys_raw.get("cpu_cores_engine", [4, 5, 6, 7])),
            cpu_cores_bridge=list(sys_raw.get("cpu_cores_bridge", [8, 9])),
        ),
        ipc=IPCConfig(
            pub_market_endpoint=ipc_raw.get("pub_market_endpoint", "ipc:///tmp/jetson_market.ipc"),
            pub_signals_endpoint=ipc_raw.get("pub_signals_endpoint", "ipc:///tmp/jetson_signals.ipc"),
            pub_execution_endpoint=ipc_raw.get("pub_execution_endpoint", "ipc:///tmp/jetson_execution.ipc"),
            pub_telemetry_endpoint=ipc_raw.get("pub_telemetry_endpoint", "ipc:///tmp/jetson_telemetry.ipc"),
            cmd_router_endpoint=ipc_raw.get("cmd_router_endpoint", "ipc:///tmp/jetson_cmd_router.ipc"),
            shm_segment_name=ipc_raw.get("shm_segment_name", "/jetson_l2_ring"),
            shm_slot_count=int(ipc_raw.get("shm_slot_count", 1024)),
        ),
        ingestion=IngestionConfig(
            symbols=list(ing_raw.get("symbols", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])),
            binance_enabled=bool(ex_raw.get("binance_futures", {}).get("enabled", True)),
            binance_ws_url=ex_raw.get("binance_futures", {}).get("ws_url", "wss://fstream.binance.com/stream"),
            binance_rest_snapshot_url=ex_raw.get("binance_futures", {}).get(
                "rest_snapshot_url", "https://fapi.binance.com/fapi/v1/depth"
            ),
            bybit_enabled=bool(ex_raw.get("bybit_linear", {}).get("enabled", True)),
            bybit_ws_url=ex_raw.get("bybit_linear", {}).get("ws_url", "wss://stream.bybit.com/v5/public/linear"),
            coinbase_enabled=bool(ex_raw.get("coinbase_advanced", {}).get("enabled", True)),
            coinbase_ws_url=ex_raw.get("coinbase_advanced", {}).get(
                "ws_url", "wss://advanced-trade-ws.coinbase.com"
            ),
            coinbase_product_ids=list(
                ex_raw.get("coinbase_advanced", {}).get("product_ids", ["BTC-USD", "ETH-USD", "SOL-USD"])
            ),
            depth_levels=int(ex_raw.get("binance_futures", {}).get("depth_levels", 50)),
            news_poll_interval_sec=float(news_raw.get("poll_interval_sec", 2.0)),
            rate_limit_capacity=float(news_raw.get("rate_limit_capacity", 30.0)),
            rate_limit_refill_per_sec=float(news_raw.get("rate_limit_refill_per_sec", 5.0)),
            news_feeds=list(news_raw.get("feeds", [])),
            proxies=list(news_raw.get("proxies", [])),
        ),
        prediction=PredictionConfig(
            feature_window_ticks=int(pred_raw.get("feature_window_ticks", 256)),
            vpin_bucket_volume=float(pred_raw.get("vpin_bucket_volume", 50.0)),
            vpin_num_buckets=int(pred_raw.get("vpin_num_buckets", 50)),
            vwap_horizons_sec=[float(x) for x in pred_raw.get("vwap_horizons_sec", [1.0, 5.0, 30.0, 300.0])],
            trt_alpha_engine_path=pred_raw.get(
                "trt_alpha_engine_path", "/opt/jetson-hft/models/alpha_tft_fp16.engine"
            ),
            trt_sentiment_engine_path=pred_raw.get(
                "trt_sentiment_engine_path", "/opt/jetson-hft/models/finbert_int8.engine"
            ),
            precision=pred_raw.get("precision", "FP16"),
            dla_core=int(pred_raw.get("dla_core", -1)),
        ),
        risk=RiskConfig(
            initial_equity_usd=float(risk_raw.get("initial_equity_usd", 250000.0)),
            max_daily_drawdown_pct=float(risk_raw.get("max_daily_drawdown_pct", 0.03)),
            max_stale_book_ms=float(risk_raw.get("max_stale_book_ms", 150.0)),
            max_fat_finger_bps=float(risk_raw.get("max_fat_finger_bps", 75.0)),
            max_slippage_bps=float(risk_raw.get("max_slippage_bps", 15.0)),
            min_signal_confidence=float(risk_raw.get("min_signal_confidence", 0.58)),
            instrument_limits=limits,
        ),
        execution=ExecutionConfig(
            exchange=exec_raw.get("exchange", "binance_futures"),
            rest_base_url=exec_raw.get("rest_base_url", "https://fapi.binance.com"),
            ws_api_url=exec_raw.get("ws_api_url", "wss://ws-fapi.binance.com/ws-fapi/v1"),
            api_key_env=exec_raw.get("api_key_env", "JETSON_EXCHANGE_API_KEY"),
            ed25519_privkey_env=exec_raw.get("ed25519_privkey_env", "JETSON_ED25519_PRIVATE_KEY_PEM"),
            sor_maker_chase_interval_ms=int(exec_raw.get("sor_maker_chase_interval_ms", 40)),
            sor_max_chase_attempts=int(exec_raw.get("sor_max_chase_attempts", 6)),
            ledger_sqlite_path=exec_raw.get("ledger_sqlite_path", "data/jetson_execution_ledger.db"),
            paper_trading=bool(exec_raw.get("paper_trading", False)),
        ),
        gateway=GatewayConfig(
            bind_host=gw_raw.get("bind_host", "0.0.0.0"),
            bind_port=int(gw_raw.get("bind_port", 8443)),
            tls_cert_path=gw_raw.get("tls_cert_path", "config/certs/server.crt"),
            tls_key_path=gw_raw.get("tls_key_path", "config/certs/server.key"),
            mtls_ca_path=gw_raw.get("mtls_ca_path", "config/certs/client_ca.crt"),
            relay_outbound_url=gw_raw.get("relay_outbound_url", ""),
            broadcast_hz=float(gw_raw.get("broadcast_hz", 10.0)),
            jwt_ttl_seconds=int(gw_raw.get("jwt_ttl_seconds", 900)),
            authorized_mobile_pubkeys=dict(gw_raw.get("authorized_mobile_pubkeys", {})),
        ),
    )
