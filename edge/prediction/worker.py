from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict

from edge.bus.schema import AlphaSignalEvent, MarketDepthEvent, SentimentEvent
from edge.bus.zmq_bus import ZMQMessageBus
from edge.config import PlatformSettings
from edge.prediction.features import FeaturePipeline
from edge.prediction.trt_engine import TensorRTAlphaEngine

logger = logging.getLogger("jetson.prediction")


class PredictionWorker:
    """
    Layer 3 Hardware-Accelerated Prediction Worker.
    Subscribes to `market.depth.<symbol>` and `signals.sentiment` on the local ZeroMQ bus,
    maintains online microstructure features (OFI, VPIN, Micro-price, Multi-horizon VWAP,
    Book Depth Skew, Realized Volatility), executes TensorRT inference in unified memory,
    and publishes `AlphaSignalEvent` on `signals.alpha`.
    """

    def __init__(self, settings: PlatformSettings, bus: ZMQMessageBus, bind_pub: bool = True) -> None:
        self.settings = settings
        self.bus = bus
        self.market_sub = self.bus.create_subscriber(
            settings.ipc.pub_market_endpoint,
            topics=["market.depth.", "signals.sentiment"],
            bind=False,
        )
        self.signals_pub = self.bus.create_publisher(
            settings.ipc.pub_signals_endpoint,
            bind=bind_pub,
        )
        self.pipeline = FeaturePipeline(
            window_ticks=settings.prediction.feature_window_ticks,
            vpin_bucket_volume=settings.prediction.vpin_bucket_volume,
            vpin_num_buckets=settings.prediction.vpin_num_buckets,
        )
        self.trt_engine = TensorRTAlphaEngine(settings.prediction)
        self.latest_sentiment: Dict[str, float] = {sym: 0.0 for sym in settings.ingestion.symbols}
        self._running = False

    def process_depth_Sync(self, depth_event: MarketDepthEvent) -> AlphaSignalEvent:
        """
        Synchronous single-tick feature extraction + TensorRT inference pipeline.
        Used both by the async ZeroMQ worker loop and deterministic unit/integration tests.
        """
        sentiment = self.latest_sentiment.get(depth_event.symbol, 0.0)
        feats = self.pipeline.process(depth_event, sentiment_score=sentiment)
        pred = self.trt_engine.infer(feats)
        return AlphaSignalEvent(
            symbol=depth_event.symbol,
            exchange=depth_event.exchange,
            sequence_id=depth_event.sequence_id,
            exchange_ts_ns=depth_event.exchange_ts_ns,
            signal_ts_ns=time.time_ns(),
            position_target=pred.position_target,
            confidence=pred.confidence,
            stop_loss_scalar_bps=pred.stop_loss_scalar_bps,
            predicted_vol_bps=pred.predicted_vol_bps,
            ofi=feats.ofi,
            vpin=feats.vpin,
            micro_price=feats.micro_price,
            mid_price=feats.mid_price,
            spread_bps=feats.spread_bps,
            depth_skew=feats.depth_skew,
            realized_vol_bps=feats.realized_vol_bps,
            vwap_1s=feats.vwap_1s,
            vwap_5s=feats.vwap_5s,
            vwap_30s=feats.vwap_30s,
            vwap_300s=feats.vwap_300s,
            sentiment_score=sentiment,
            trt_inference_us=pred.inference_latency_us,
        )

    async def run(self) -> None:
        self._running = True
        logger.info("PredictionWorker listening on %s", self.settings.ipc.pub_market_endpoint)
        try:
            async for topic, payload in self.bus.iter_messages(self.market_sub):
                if not self._running:
                    break
                if topic == "signals.sentiment":
                    sent = SentimentEvent.from_bytes(payload)
                    for sym in sent.symbols:
                        # Exponentially weight incoming NLP sentiment scores
                        prev = self.latest_sentiment.get(sym, 0.0)
                        self.latest_sentiment[sym] = 0.6 * prev + 0.4 * sent.sentiment_score
                elif topic.startswith("market.depth."):
                    depth_ev = MarketDepthEvent.from_bytes(payload)
                    if not depth_ev.parity_valid:
                        continue
                    alpha_ev = self.process_depth_Sync(depth_ev)
                    await self.bus.publish(self.signals_pub, "signals.alpha", alpha_ev.to_bytes())
        except asyncio.CancelledError:
            pass
        finally:
            self.trt_engine.close()

    def stop(self) -> None:
        self._running = False
