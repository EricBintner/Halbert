# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the audio ring buffer."""

import asyncio
import struct
import pytest

from halbert_core.audio.buffer import AsyncRingBuffer, ChunkQueue, AudioChunk


def _make_pcm(num_samples: int, value: int = 1000) -> bytes:
    """Generate PCM bytes with a known sample value."""
    return struct.pack(f'<{num_samples}h', *([value] * num_samples))


@pytest.mark.asyncio
async def test_ring_buffer_write_and_read():
    """Write PCM, read it back."""
    buf = AsyncRingBuffer(capacity_samples=1600)  # 0.1s at 16kHz
    pcm = _make_pcm(800, value=500)
    await buf.write(pcm)

    # Read last 0.05s (800 samples)
    result = await buf.read_window(800)
    samples = struct.unpack(f'<{len(result)//2}h', result)
    assert all(s == 500 for s in samples)
    assert len(samples) == 800


@pytest.mark.asyncio
async def test_ring_buffer_wraparound():
    """Buffer wraps around correctly when overfilled."""
    buf = AsyncRingBuffer(capacity_samples=800)  # small buffer
    # Write 1600 samples (2x capacity) — should keep last 800
    await buf.write(_make_pcm(800, value=100))
    await buf.write(_make_pcm(800, value=200))

    assert buf.filled_samples == 800
    result = await buf.read_window(800)
    samples = struct.unpack(f'<{len(result)//2}h', result)
    # Last 800 samples should all be value=200
    assert all(s == 200 for s in samples)


@pytest.mark.asyncio
async def test_ring_buffer_read_more_than_filled():
    """Reading more than available returns only what's filled."""
    buf = AsyncRingBuffer(capacity_samples=1600)
    await buf.write(_make_pcm(400, value=300))

    result = await buf.read_window(800)
    samples = struct.unpack(f'<{len(result)//2}h', result)
    assert len(samples) == 400
    assert all(s == 300 for s in samples)


@pytest.mark.asyncio
async def test_ring_buffer_empty_read():
    """Reading from empty buffer returns empty bytes."""
    buf = AsyncRingBuffer(capacity_samples=1600)
    result = await buf.read_window(800)
    assert result == b''


@pytest.mark.asyncio
async def test_read_last_seconds():
    """read_last_seconds converts correctly."""
    buf = AsyncRingBuffer(capacity_samples=16000)  # 1s at 16kHz
    await buf.write(_make_pcm(16000, value=999))

    # Read last 0.5s
    result = await buf.read_last_seconds(0.5)
    samples = struct.unpack(f'<{len(result)//2}h', result)
    assert len(samples) == 8000
    assert all(s == 999 for s in samples)


@pytest.mark.asyncio
async def test_chunk_queue_basic():
    """Chunk queue put/get."""
    q = ChunkQueue(maxsize=10)
    chunk = AudioChunk(pcm=b'\x00\x01', samples=1, source="test")
    await q.put(chunk)

    result = await q.get()
    assert result.source == "test"
    assert result.samples == 1


@pytest.mark.asyncio
async def test_chunk_queue_drops_oldest_when_full():
    """Queue drops oldest when full."""
    q = ChunkQueue(maxsize=2)
    c1 = AudioChunk(pcm=b'\x00', samples=0, source="first")
    c2 = AudioChunk(pcm=b'\x00', samples=0, source="second")
    c3 = AudioChunk(pcm=b'\x00', samples=0, source="third")

    q.put_nowait(c1)
    q.put_nowait(c2)
    q.put_nowait(c3)  # should drop c1

    first = await q.get()
    assert first.source == "second"
    second = await q.get()
    assert second.source == "third"
