from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import List

from edge.bus.schema import MarketDepthEvent, SentimentEvent
from edge.bus.zmq_bus import SharedMemoryL2Ring, ZMQMessageBus
from edge.config import PlatformSettings, load_settings
from edge.ingestion.news_scraper import AlternativeDataNewsScraper
from edge.ingestion.ws_feeds import (
    BinanceFuturesFeedHandler,
    BybitLinearFeedHandler,
    CoinbaseAdvancedFeedHandler,
)

logger = logging.getLogger("jetson.ingest")


def pin_cpu_cores(cores: List[int]) -> None:
    if hasattr(os, "sched_setaffinity") and cores:
        try:
            os.sched_setaffinity(0, set(cores))
            logger.info("Pinned ingestion process to CPU cores: %s", cores)
        except Exception as exc:
            logger.warning("Could not set CPU core affinity: %s", exc)


class IngestionDaemon:
    """
    Layer 1 Master Ingestion Daemon (`jetson-ingest.service`).
    Runs multi-venue WebSocket L2 feed handlers and the NLP news scraper concurrently,
    writing L2 top-of-book updates directly to POSIX shared memory and ZeroMQ IPC topics.
    """

    def __init__(self, settings: PlatformSettings) -> None:
        self.settings = settings
        self.bus = ZMQMessageBus(settings.ipc)
        self.market_pub = self.bus.create_publisher(settings.ipc.pub_market_endpoint, bind=True)
        self.shm_ring = SharedMemoryL2Ring(
            name=settings.ipc.shm_segment_name,
            slot_count=settings.ipc.shm_slot_count,
            create=True,
        )
        self.binance = BinanceFuturesFeedHandler(settings.ingestion, self.on_market_depth)
        self.bybit = BybitLinearFeedHandler(settings.ingestion, self.on_market_depth)
        self.coinbase = CoinbaseAdvancedFeedHandler(settings.ingestion, self.on_market_depth)
        self.scraper = AlternativeDataNewsScraper(
            settings.ingestion, settings.prediction, self.on_sentiment
        )

    async def on_market_depth(self, event: MarketDepthEvent) -> None:
        self.shm_ring.write_depth_event(event)
        topic = f"market.depth.{event.symbol}"
        await self.bus.publish(self.market_pub, topic, event.to_bytes())

    async def on_sentiment(self, event: SentimentEvent) -> None:
        await self.bus.publish(self.market_pub, "signals.sentiment", event.to_bytes())

    async def run(self) -> None:
        pin_cpu_cores(self.settings.system.cpu_cores_ingest)
        tasks = []
        if self.settings.ingestion.binance_enabled:
            tasks.append(asyncio.create_task(self.binance.run(), name="binance_l2"))
        if self.settings.ingestion.bybit_enabled:
            tasks.append(asyncio.create_task(self.bybit.run(), name="bybit_l2"))
        if self.settings.ingestion.coinbase_enabled:
            tasks.append(asyncio.create_task(self.coinbase.run(), name="coinbase_l2"))
        tasks.append(asyncio.create_task(self.scraper.run(), name="news_scraper"))

        logger.info("IngestionDaemon active with %d concurrent workers", len(tasks))
        try:
            await asyncio.gather(*tasks)
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self.binance.stop()
        self.bybit.stop()
        self.coinbase.stop()
        self.scraper.stop()
        self.shm_ring.close(unlink=False)
        self.bus.close_all()


async def _async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    settings = load_settings()
    daemon = IngestionDaemon(settings)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, daemon.shutdown)
        except NotImplementedError:
            pass
    await daemon.run()


if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass
    asyncio.run(_async_main())
