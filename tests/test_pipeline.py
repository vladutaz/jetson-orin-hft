from __future__ import annotations

import asyncio
import base64
from pathlib import Path
import time
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from edge.bus.schema import MarketDepthEvent
from edge.bus.zmq_bus import SharedMemoryL2Ring
from edge.config import load_settings
from edge.execution.ledger import ExecutionWallLedger
from edge.execution.risk import EngineMode, PreTradeRiskGatekeeper
from edge.execution.router import SmartOrderRouter
from edge.execution.state_machine import (
    InvalidOrderTransitionError,
    OrderState,
    OrderStateMachine,
)
from edge.gateway.auth import GatewayAuthenticator
from edge.gateway.delta import TelemetryDeltaCompressor, apply_dict_delta
from edge.gateway.jetson_telemetry import JetsonOrinTelemetryReader
from edge.ingestion.news_scraper import TensorRTFinancialSentimentScorer
from edge.ingestion.orderbook import (
    BookParityError,
    BufferedDepthDelta,
    LocalL2OrderBook,
    SequenceGapError,
)
from edge.prediction.features import FeaturePipeline
from edge.prediction.trt_engine import TensorRTAlphaEngine


def test_l2_orderbook_delta_reconstruction_and_gap_detection() -> None:
    book = LocalL2OrderBook("binance_futures", "BTCUSDT", max_depth=10)

    # Buffer deltas before REST snapshot arrives
    d1 = BufferedDepthDelta(
        U=100,
        u=105,
        pu=99,
        bids=[(89990.0, 2.5)],
        asks=[(90000.0, 1.8)],
        exchange_ts_ns=time.time_ns(),
    )
    assert book.buffer_ws_delta(d1) is None

    # Apply snapshot at u=102; d1 spans [100, 105] so it must be reconciled
    snap_ev = book.apply_snapshot(
        last_update_id=102,
        bids=[(89985.0, 1.0), (89980.0, 3.0)],
        asks=[(90005.0, 2.0), (90010.0, 4.0)],
    )
    assert book.initialized is True
    assert book.last_update_id == 105
    assert snap_ev.bids[0] == (89990.0, 2.5)
    assert snap_ev.asks[0] == (90000.0, 1.8)
    assert snap_ev.parity_valid is True

    # Apply next valid sequenced delta (pu == 105)
    d2 = BufferedDepthDelta(
        U=106,
        u=108,
        pu=105,
        bids=[(89995.0, 1.2)],
        asks=[(90000.0, 0.0)],  # Remove 90000 ask level
        exchange_ts_ns=time.time_ns(),
    )
    ev2 = book.buffer_ws_delta(d2)
    assert ev2 is not None
    assert ev2.bids[0] == (89995.0, 1.2)
    assert ev2.asks[0] == (90005.0, 2.0)

    # Trigger SequenceGapError when `pu` does not match `last_update_id`
    bad_delta = BufferedDepthDelta(
        U=120,
        u=125,
        pu=119,
        bids=[(89996.0, 1.0)],
        asks=[],
        exchange_ts_ns=time.time_ns(),
    )
    with pytest.raises(SequenceGapError):
        book.buffer_ws_delta(bad_delta)
    assert book.initialized is False

    # Crossed book must raise BookParityError
    with pytest.raises(BookParityError):
        book.apply_snapshot(
            last_update_id=200,
            bids=[(90010.0, 1.0)],
            asks=[(90000.0, 1.0)],
        )


def test_shared_memory_ring_and_binary_serialization() -> None:
    ring = SharedMemoryL2Ring(name="/jetson_test_ring", slot_count=32, create=True)
    try:
        ev = MarketDepthEvent(
            exchange="binance_futures",
            symbol="BTCUSDT",
            sequence_id=555,
            exchange_ts_ns=time.time_ns(),
            ingest_ts_ns=time.time_ns(),
            bids=[(89990.0, 2.0), (89985.0, 4.0)],
            asks=[(90000.0, 1.5), (90005.0, 3.0)],
            last_trade_px=89995.0,
            last_trade_qty=0.5,
            last_trade_is_buyer_maker=False,
            parity_valid=True,
        )
        raw = ev.to_bytes()
        decoded = MarketDepthEvent.from_bytes(raw)
        assert decoded.symbol == "BTCUSDT"
        assert decoded.sequence_id == 555
        assert decoded.bids[0] == (89990.0, 2.0)

        slot_idx = ring.write_depth_event(ev)
        assert slot_idx == 0
        shm_snap = ring.read_latest()
        assert shm_snap is not None
        assert shm_snap["symbol"] == "BTCUSDT"
        assert shm_snap["best_bid_px"] == 89990.0
        assert shm_snap["best_ask_px"] == 90000.0
    finally:
        ring.close(unlink=True)


def test_nlp_sentiment_and_tensorrt_feature_pipeline() -> None:
    settings = load_settings()
    scorer = TensorRTFinancialSentimentScorer(settings.prediction)

    bull_score, bull_conf, syms, lat_ms = scorer.score_headline(
        "SEC approves institutional Bitcoin ETF with record inflows and surge",
        ["BTCUSDT", "ETHUSDT"],
    )
    assert bull_score > 0.25
    assert bull_conf > 0.4
    assert "BTCUSDT" in syms
    assert lat_ms < 15.0  # Must execute in <15ms

    bear_score, _, _, _ = scorer.score_headline(
        "Major exchange suffers exploit hack and insolvency lawsuit",
        ["BTCUSDT"],
    )
    assert bear_score < -0.25

    pipeline = FeaturePipeline(window_ticks=64, vpin_bucket_volume=10.0, vpin_num_buckets=10)
    trt_engine = TensorRTAlphaEngine(settings.prediction)
    try:
        now_ns = time.time_ns()
        for i in range(10):
            ev = MarketDepthEvent(
                exchange="binance_futures",
                symbol="BTCUSDT",
                sequence_id=1000 + i,
                exchange_ts_ns=now_ns + i * 50_000_000,
                ingest_ts_ns=now_ns + i * 50_000_000,
                bids=[(90000.0 + i * 2.0, 3.5 + i * 0.2), (89995.0, 2.0)],
                asks=[(90002.0 + i * 2.0, 1.0), (90005.0, 1.5)],
                last_trade_px=90001.5 + i * 2.0,
                last_trade_qty=2.5,
                last_trade_is_buyer_maker=False,
                parity_valid=True,
            )
            feats = pipeline.process(ev, sentiment_score=bull_score)
            pred = trt_engine.infer(feats)
            assert -1.0 <= pred.position_target <= 1.0
            assert 0.0 < pred.confidence <= 1.0
            assert pred.stop_loss_scalar_bps >= 8.0
            assert pred.predicted_vol_bps >= 2.0
    finally:
        trt_engine.close()


def test_risk_gates_sor_and_kill_switch(tmp_path: Path) -> None:
    asyncio.run(_async_test_risk_gates_sor_and_kill_switch(tmp_path))


async def _async_test_risk_gates_sor_and_kill_switch(tmp_path: Path) -> None:
    settings = load_settings()
    gate = PreTradeRiskGatekeeper(settings.risk)
    now_ns = time.time_ns()

    # 1. Valid order passes
    ok_res = gate.validate_order(
        symbol="BTCUSDT",
        side="BUY",
        order_price=89995.0,
        order_qty=0.2,
        mid_price=90000.0,
        spread_bps=1.5,
        book_exchange_ts_ns=now_ns - 20_000_000,  # 20ms old
        now_ts_ns=now_ns,
    )
    assert ok_res.allowed is True

    # 2. Stale feed (>150ms) rejected
    stale_res = gate.validate_order(
        symbol="BTCUSDT",
        side="BUY",
        order_price=89995.0,
        order_qty=0.2,
        mid_price=90000.0,
        spread_bps=1.5,
        book_exchange_ts_ns=now_ns - 250_000_000,  # 250ms old > 150ms limit
        now_ts_ns=now_ns,
    )
    assert stale_res.allowed is False
    assert stale_res.code == "STALE_FEED"

    # 3. Fat-finger (>75 bps from mid) rejected
    ff_res = gate.validate_order(
        symbol="BTCUSDT",
        side="BUY",
        order_price=91500.0,
        order_qty=0.2,
        mid_price=90000.0,
        spread_bps=1.5,
        book_exchange_ts_ns=now_ns,
        now_ts_ns=now_ns,
    )
    assert ff_res.allowed is False
    assert ff_res.code == "FAT_FINGER"

    # 4. Max single order notional rejected
    size_res = gate.validate_order(
        symbol="BTCUSDT",
        side="BUY",
        order_price=90000.0,
        order_qty=1.0,  # $90,000 > $50,000 limit
        mid_price=90000.0,
        spread_bps=1.5,
        book_exchange_ts_ns=now_ns,
        now_ts_ns=now_ns,
    )
    assert size_res.allowed is False
    assert size_res.code == "MAX_ORDER_SIZE"

    # 5. Deterministic State Machine & Smart Order Router + Kill-Switch test
    sm = OrderStateMachine()
    db_file = tmp_path / "test_ledger.db"
    ledger = ExecutionWallLedger(db_file)
    emitted_events = []

    async def on_exec(ev):
        emitted_events.append(ev)

    router = SmartOrderRouter(
        exec_config=settings.execution,
        risk_config=settings.risk,
        risk_gate=gate,
        state_machine=sm,
        ledger=ledger,
        on_execution_event=on_exec,
    )

    book_ev = MarketDepthEvent(
        exchange="binance_futures",
        symbol="BTCUSDT",
        sequence_id=10,
        exchange_ts_ns=time.time_ns(),
        ingest_ts_ns=time.time_ns(),
        bids=[(89999.0, 3.0)],
        asks=[(90001.0, 3.0)],
        last_trade_px=90000.0,
        last_trade_qty=0.5,
        parity_valid=True,
    )
    router.update_book(book_ev)

    filled_ord = await router.execute_smart_maker_order("BTCUSDT", "BUY", 0.25)
    assert filled_ord is not None
    assert filled_ord.state == OrderState.FILLED
    assert gate.positions["BTCUSDT"].quantity == pytest.approx(0.25)

    # Verify illegal transition from terminal FILLED raises InvalidOrderTransitionError
    with pytest.raises(InvalidOrderTransitionError):
        sm.transition(filled_ord.client_order_id, OrderState.CANCELED)

    # Execute Emergency Kill-Switch flatten
    closed_orders = await router.flatten_all_positions("TEST_BIOMETRIC_KILL_SWITCH")
    assert len(closed_orders) == 1
    assert gate.mode == EngineMode.HALTED
    assert gate.positions["BTCUSDT"].quantity == pytest.approx(0.0)
    assert len(ledger.get_recent_fills()) >= 2

    await router.close()
    ledger.close()


def test_gateway_auth_delta_compression_and_telemetry() -> None:
    settings = load_settings()
    auth = GatewayAuthenticator(settings.gateway)
    priv = Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pub_b64 = base64.b64encode(pub_raw).decode("ascii")

    device_id = "iphone-16-pro-operator"
    nonce = auth.issue_challenge(device_id)
    sig_bytes = priv.sign(f"{device_id}:{nonce}".encode("ascii"))
    sig_b64 = base64.b64encode(sig_bytes).decode("ascii")

    jwt_token = auth.verify_challenge_and_issue_jwt(device_id, nonce, sig_b64, pub_b64)
    assert jwt_token is not None
    claims = auth.verify_jwt(jwt_token)
    assert claims is not None
    assert claims["sub"] == device_id

    compressor = TelemetryDeltaCompressor(full_sync_interval=10)
    state_1 = {"seq": 1, "equity_usd": 250000.0, "positions": {"BTCUSDT": {"qty": 0.5}}}
    f1 = compressor.encode_frame(state_1)
    assert f1["type"] == "TELEMETRY_FULL"

    state_2 = {"seq": 2, "equity_usd": 250120.0, "positions": {"BTCUSDT": {"qty": 0.5}}}
    f2 = compressor.encode_frame(state_2)
    assert f2["type"] == "TELEMETRY_DELTA"
    assert "positions" not in f2["delta"]  # Unchanged subtree omitted
    reconstructed = apply_dict_delta(state_1, f2["delta"])
    assert reconstructed == state_2

    hw = JetsonOrinTelemetryReader().snapshot(network_ping_ms=2.1)
    assert "gpu_temp_c" in hw
    assert "power_watts" in hw


def test_zmq_ipc_bus_and_prediction_worker_end_to_end() -> None:
    from edge.bus.zmq_bus import ZMQMessageBus
    from edge.prediction.worker import PredictionWorker

    settings = load_settings()
    bus = ZMQMessageBus(settings.ipc)
    worker = PredictionWorker(settings, bus, bind_pub=False)
    try:
        ev = MarketDepthEvent(
            exchange="binance_futures",
            symbol="ETHUSDT",
            sequence_id=9001,
            exchange_ts_ns=time.time_ns(),
            ingest_ts_ns=time.time_ns(),
            bids=[(3100.0, 12.5), (3099.5, 8.0)],
            asks=[(3100.5, 4.2), (3101.0, 6.0)],
            last_trade_px=3100.5,
            last_trade_qty=1.8,
            last_trade_is_buyer_maker=False,
            parity_valid=True,
        )
        alpha = worker.process_depth_Sync(ev)
        raw_alpha = alpha.to_bytes()
        decoded_alpha = alpha.from_bytes(raw_alpha)
        assert decoded_alpha.symbol == "ETHUSDT"
        assert decoded_alpha.sequence_id == 9001
        assert decoded_alpha.micro_price > 3100.0
        assert decoded_alpha.trt_inference_us > 0.0
    finally:
        worker.stop()
        worker.trt_engine.close()
        bus.close_all()

