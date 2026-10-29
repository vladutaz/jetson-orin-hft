from __future__ import annotations

import asyncio
import logging
from multiprocessing import shared_memory
from pathlib import Path
import struct
from typing import AsyncIterator, Dict, List, Optional, Tuple

import zmq
import zmq.asyncio

from edge.bus.schema import MarketDepthEvent, SHM_SLOT_SIZE
from edge.config import IPCConfig

logger = logging.getLogger(__name__)


class SharedMemoryL2Ring:
    """
    POSIX Shared Memory (`shm_open` via `multiprocessing.shared_memory`) zero-copy
    lock-free ring buffer & symbol index for ultra-low-latency top-of-book access
    between the ingestion process and the TensorRT inference process.

    Memory Layout:
      Header (64 bytes):
        - magic (uint32): 0x4A455453 ('JETS')
        - version (uint32): 1
        - slot_count (uint32)
        - write_cursor (uint64)
      Slots (slot_count * SHM_SLOT_SIZE bytes):
        - Each slot stores a binary-packed SHM_SLOT_STRUCT (136 bytes).
    """

    HEADER_STRUCT = struct.Struct("<IIIQ44x")  # 64 bytes
    MAGIC = 0x4A455453

    def __init__(self, name: str = "/jetson_l2_ring", slot_count: int = 1024, create: bool = False) -> None:
        self.clean_name = name.lstrip("/")
        self.slot_count = slot_count
        self.total_size = self.HEADER_STRUCT.size + (slot_count * SHM_SLOT_SIZE)
        self._shm: Optional[shared_memory.SharedMemory] = None
        self._symbol_slot_map: Dict[str, int] = {}

        try:
            if create:
                try:
                    existing = shared_memory.SharedMemory(name=self.clean_name, create=False)
                    existing.close()
                    existing.unlink()
                except FileNotFoundError:
                    pass
                self._shm = shared_memory.SharedMemory(name=self.clean_name, create=True, size=self.total_size)
                self._write_header(0)
            else:
                self._shm = shared_memory.SharedMemory(name=self.clean_name, create=False)
        except FileNotFoundError:
            # Automatically create if reader starts before writer
            self._shm = shared_memory.SharedMemory(name=self.clean_name, create=True, size=self.total_size)
            self._write_header(0)

    def _write_header(self, write_cursor: int) -> None:
        if self._shm is None:
            return
        self.HEADER_STRUCT.pack_into(
            self._shm.buf,
            0,
            self.MAGIC,
            1,
            self.slot_count,
            write_cursor,
        )

    def _read_header(self) -> Tuple[int, int, int, int]:
        if self._shm is None:
            return (0, 0, 0, 0)
        return self.HEADER_STRUCT.unpack_from(self._shm.buf, 0)

    def write_depth_event(self, event: MarketDepthEvent) -> int:
        """
        Writes the latest L2 top-of-book event into the ring buffer and updates the atomic write cursor.
        """
        if self._shm is None:
            return -1
        _, _, slot_count, cursor = self._read_header()
        if slot_count <= 0:
            slot_count = self.slot_count
        slot_idx = cursor % slot_count
        offset = self.HEADER_STRUCT.size + (slot_idx * SHM_SLOT_SIZE)
        packed = event.pack_shm_slot()
        self._shm.buf[offset : offset + SHM_SLOT_SIZE] = packed
        next_cursor = cursor + 1
        self._write_header(next_cursor)
        self._symbol_slot_map[event.symbol] = slot_idx
        return slot_idx

    def read_latest(self) -> Optional[Dict[str, object]]:
        """
        Reads the most recently written slot from POSIX shared memory without blocking.
        """
        if self._shm is None:
            return None
        magic, _, slot_count, cursor = self._read_header()
        if magic != self.MAGIC or cursor == 0 or slot_count == 0:
            return None
        slot_idx = (cursor - 1) % slot_count
        offset = self.HEADER_STRUCT.size + (slot_idx * SHM_SLOT_SIZE)
        raw_bytes = bytes(self._shm.buf[offset : offset + SHM_SLOT_SIZE])
        return MarketDepthEvent.unpack_shm_slot(raw_bytes)

    def close(self, unlink: bool = False) -> None:
        if self._shm is not None:
            try:
                self._shm.close()
                if unlink:
                    self._shm.unlink()
            except Exception:
                pass
            self._shm = None


def _ensure_ipc_dir(endpoint: str) -> None:
    if endpoint.startswith("ipc://"):
        sock_path = Path(endpoint.replace("ipc://", ""))
        sock_path.parent.mkdir(parents=True, exist_ok=True)


class ZMQMessageBus:
    """
    High-throughput asynchronous ZeroMQ IPC message bus supporting:
      - Topic 1: `market.depth.<symbol>`
      - Topic 2: `signals.alpha` & `signals.sentiment`
      - Topic 3: `engine.execution`
      - Topic 4: `telemetry.mobile`
      - Command channel: `cmd.control` (Kill-Switch, Manual Orders, Risk Resets)
    """

    def __init__(self, ipc_config: IPCConfig) -> None:
        self.config = ipc_config
        self.ctx = zmq.asyncio.Context.instance()
        self._publishers: Dict[str, zmq.asyncio.Socket] = {}
        self._subscribers: List[zmq.asyncio.Socket] = []

    def create_publisher(self, endpoint: str, bind: bool = True) -> zmq.asyncio.Socket:
        resolved = self.config.resolved_endpoint(endpoint)
        if resolved in self._publishers:
            return self._publishers[resolved]

        _ensure_ipc_dir(resolved)
        sock = self.ctx.socket(zmq.PUB)
        sock.setsockopt(zmq.SNDHWM, 10000)
        sock.setsockopt(zmq.LINGER, 0)
        sock.setsockopt(zmq.TCP_KEEPALIVE, 1)
        if bind:
            sock.bind(resolved)
        else:
            sock.connect(resolved)
        self._publishers[resolved] = sock
        logger.info("ZMQ Publisher initialized on %s (bind=%s)", resolved, bind)
        return sock

    def create_subscriber(self, endpoint: str, topics: List[str], bind: bool = False) -> zmq.asyncio.Socket:
        resolved = self.config.resolved_endpoint(endpoint)
        _ensure_ipc_dir(resolved)
        sock = self.ctx.socket(zmq.SUB)
        sock.setsockopt(zmq.RCVHWM, 10000)
        sock.setsockopt(zmq.LINGER, 0)
        if bind:
            sock.bind(resolved)
        else:
            sock.connect(resolved)
        for topic in topics:
            sock.setsockopt(zmq.SUBSCRIBE, topic.encode("utf-8"))
        self._subscribers.append(sock)
        logger.info("ZMQ Subscriber connected to %s for topics=%s", resolved, topics)
        return sock

    def create_command_pusher(self, endpoint: Optional[str] = None) -> zmq.asyncio.Socket:
        target = endpoint or self.config.cmd_router_endpoint
        resolved = self.config.resolved_endpoint(target)
        _ensure_ipc_dir(resolved)
        sock = self.ctx.socket(zmq.PUSH)
        sock.setsockopt(zmq.SNDHWM, 1000)
        sock.setsockopt(zmq.LINGER, 100)
        sock.connect(resolved)
        self._subscribers.append(sock)
        return sock

    def create_command_puller(self, endpoint: Optional[str] = None, bind: bool = True) -> zmq.asyncio.Socket:
        target = endpoint or self.config.cmd_router_endpoint
        resolved = self.config.resolved_endpoint(target)
        _ensure_ipc_dir(resolved)
        sock = self.ctx.socket(zmq.PULL)
        sock.setsockopt(zmq.RCVHWM, 1000)
        sock.setsockopt(zmq.LINGER, 0)
        if bind:
            sock.bind(resolved)
        else:
            sock.connect(resolved)
        self._subscribers.append(sock)
        return sock

    @staticmethod
    async def publish(sock: zmq.asyncio.Socket, topic: str, payload: bytes) -> None:
        await sock.send_multipart([topic.encode("utf-8"), payload], flags=zmq.DONTWAIT)

    @staticmethod
    async def iter_messages(sock: zmq.asyncio.Socket) -> AsyncIterator[Tuple[str, bytes]]:
        while True:
            frames = await sock.recv_multipart()
            if len(frames) >= 2:
                yield frames[0].decode("utf-8", errors="replace"), frames[1]

    def close_all(self) -> None:
        for sock in self._publishers.values():
            try:
                sock.close(0)
            except Exception:
                pass
        for sock in self._subscribers:
            try:
                sock.close(0)
            except Exception:
                pass
        self._publishers.clear()
        self._subscribers.clear()
