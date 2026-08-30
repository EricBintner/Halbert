# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Circular audio ring buffer — 10s rolling PCM memory.

Platform-split design (per architecture review finding H5):

- **Desktop (Tauri):** The ring buffer lives in Rust (``src-tauri/src/audio_buffer.rs``)
  for lock-free, GIL-free operation. Python reads from a loopback TCP socket.
  The ``RustRingBufferReader`` class here is the Python-side socket reader.

- **Headless Linux:** A single-producer ``asyncio.Queue`` feeds multiple async
  consumers that read overlapping slices. Uses ``array.array('h')`` for the
  rolling window (not ``collections.deque`` — deque is unsafe for overlapping
  multi-consumer reads under GIL contention).

Both paths expose the same ``AudioRingBuffer`` interface so the pipeline
coordinator doesn't care which platform it's on.

Frame format: 16kHz, 16-bit, mono PCM (``array.array('h')``).
10 seconds = 160000 samples = 320000 bytes.
"""

from __future__ import annotations

import asyncio
import logging
import struct
from array import array
from dataclasses import dataclass
from typing import AsyncIterator, Optional

logger = logging.getLogger("halbert.audio.buffer")

# 16kHz * 10s = 160000 samples (16-bit signed = 320000 bytes)
DEFAULT_BUFFER_SAMPLES = 160_000
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1


@dataclass
class AudioChunk:
    """A chunk of PCM audio with metadata."""
    pcm: bytes          # raw 16-bit mono PCM
    samples: int        # number of samples in this chunk
    source: str = ""    # 'local_mic', 'wyoming_satellite', 'frigate_rtsp', 'dashboard'
    area_id: str = ""   # spatial context (room)
    timestamp: float = 0.0


class AsyncRingBuffer:
    """Async-safe rolling PCM buffer for headless Linux.

    Single producer (ingress thread) writes chunks. Multiple async consumers
    read overlapping 1-second windows for the ambient track, or 32ms frames
    for the speech track.

    Uses ``array.array('h')`` for the rolling window — not ``collections.deque``,
    which is unsafe for overlapping multi-consumer slice reads under GIL
    contention (finding H5).
    """

    def __init__(self, capacity_samples: int = DEFAULT_BUFFER_SAMPLES):
        self._capacity = capacity_samples
        self._buf: array[int] = array('h', [0] * capacity_samples)
        self._write_pos = 0
        self._filled = 0  # how many samples have been written (capped at capacity)
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Event()
        self._total_written = 0  # monotonic counter for consumer positioning

    async def write(self, pcm: bytes) -> None:
        """Write raw 16-bit PCM bytes into the ring buffer."""
        # Unpack 16-bit signed samples
        n = len(pcm) // SAMPLE_WIDTH
        samples = struct.unpack(f'<{n}h', pcm)

        async with self._lock:
            for s in samples:
                self._buf[self._write_pos] = s
                self._write_pos = (self._write_pos + 1) % self._capacity
            self._filled = min(self._filled + n, self._capacity)
            self._total_written += n
            self._not_empty.set()

    async def read_window(self, num_samples: int) -> bytes:
        """Read the most recent N samples as raw PCM bytes.

        Returns fewer samples if the buffer hasn't filled yet.
        """
        async with self._lock:
            available = min(num_samples, self._filled)
            if available == 0:
                return b''

            start = (self._write_pos - available) % self._capacity
            if start + available <= self._capacity:
                # Contiguous read
                chunk = self._buf[start:start + available]
            else:
                # Wraparound read
                first = self._capacity - start
                chunk = self._buf[start:] + self._buf[:available - first]

            return struct.pack(f'<{len(chunk)}h', *chunk)

    async def read_last_seconds(self, seconds: float) -> bytes:
        """Read the last N seconds of audio."""
        num = int(seconds * SAMPLE_RATE)
        return await self.read_window(num)

    @property
    def filled_samples(self) -> int:
        """How many samples are currently in the buffer."""
        return self._filled

    @property
    def total_written(self) -> int:
        """Monotonic counter of total samples ever written."""
        return self._total_written


class ChunkQueue:
    """Async queue for passing AudioChunks from ingress to consumers.

    Used by the pipeline coordinator to distribute chunks to the speech
    track (VAD/ASR) and ambient track (audio tagger) simultaneously.
    """

    def __init__(self, maxsize: int = 100):
        self._queue: asyncio.Queue[AudioChunk] = asyncio.Queue(maxsize=maxsize)

    async def put(self, chunk: AudioChunk) -> None:
        """Put a chunk into the queue. Drops oldest if full."""
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await self._queue.put(chunk)

    def put_nowait(self, chunk: AudioChunk) -> None:
        """Non-async put. Drops oldest if full."""
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self._queue.put_nowait(chunk)

    async def get(self) -> AudioChunk:
        """Get the next chunk."""
        return await self._queue.get()

    def qsize(self) -> int:
        return self._queue.qsize()


# Convenience factory
def create_buffer() -> tuple[AsyncRingBuffer, ChunkQueue]:
    """Create a ring buffer + chunk queue pair for the pipeline."""
    return AsyncRingBuffer(), ChunkQueue()
