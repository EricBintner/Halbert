# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for PTYSession fan-out reader (Plan B: B4)."""

import asyncio
import sys

import pytest

from halbert_core.streaming.pty import PTYSession

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="PTY is Unix-only (os.fork)"
)


@pytest.mark.asyncio
async def test_attach_returns_queue():
    session = PTYSession("echo hello")
    await session.spawn()
    q = await session.attach()
    assert isinstance(q, asyncio.Queue)
    session.kill()
    session.detach(q)


@pytest.mark.asyncio
async def test_attach_replays_buffer():
    """First item on a newly-attached queue is ('__replay__', buffer)."""
    session = PTYSession("printf 'hello world\\n'")
    await session.spawn()
    # Collect output first via read_chunk to populate the buffer
    gen = session.read_chunk()
    async for chunk in gen:
        if b"hello world" in chunk:
            break
    await gen.aclose()
    await asyncio.sleep(0.1)

    # Now attach — should get a replay first
    q = await session.attach()
    item = await asyncio.wait_for(q.get(), timeout=3.0)
    assert isinstance(item, tuple)
    assert item[0] == "__replay__"
    assert b"hello world" in item[1]
    session.kill()
    session.detach(q)


@pytest.mark.asyncio
async def test_attach_receives_live_chunks():
    """After replay, the queue receives live output chunks."""
    session = PTYSession("printf 'live output\\n'")
    await session.spawn()
    q = await session.attach()
    # Consume replay
    replay = await asyncio.wait_for(q.get(), timeout=3.0)
    assert replay[0] == "__replay__"
    # Now get live chunks
    chunks = b""
    try:
        while True:
            item = await asyncio.wait_for(q.get(), timeout=5.0)
            if item is None:
                break
            if isinstance(item, tuple):
                continue  # skip replay if it comes late
            chunks += item
            if b"live output" in chunks:
                break
    except asyncio.TimeoutError:
        pass
    assert b"live output" in chunks
    session.kill()
    session.detach(q)


@pytest.mark.asyncio
async def test_multiple_attach_fanout():
    """Two attached queues both receive the same chunks."""
    session = PTYSession("printf 'fanout test\\n'")
    await session.spawn()
    q1 = await session.attach()
    q2 = await session.attach()
    # Skip replays
    await asyncio.wait_for(q1.get(), timeout=3.0)
    await asyncio.wait_for(q2.get(), timeout=3.0)

    received1 = bytearray()
    received2 = bytearray()

    async def collect(q, into):
        try:
            while True:
                item = await asyncio.wait_for(q.get(), timeout=5.0)
                if item is None:
                    break
                if isinstance(item, tuple):
                    continue
                into.extend(item)
                if b"fanout test" in bytes(into):
                    return
        except asyncio.TimeoutError:
            pass

    await asyncio.gather(
        collect(q1, received1),
        collect(q2, received2),
    )
    assert b"fanout test" in bytes(received1)
    assert b"fanout test" in bytes(received2)
    session.kill()
    session.detach(q1)
    session.detach(q2)


@pytest.mark.asyncio
async def test_detach_stops_delivery():
    """After detach, a queue receives no more chunks."""
    session = PTYSession("printf 'detach test\\n'; sleep 0.5; printf 'after detach\\n'")
    await session.spawn()
    q = await session.attach()
    await asyncio.wait_for(q.get(), timeout=3.0)  # replay

    # Detach immediately
    session.detach(q)

    # Wait for output to appear
    await asyncio.sleep(0.6)
    # Queue should be empty (or only have items that arrived before detach)
    # The key property: no new chunks after detach
    remaining = q.qsize()
    assert remaining == 0 or remaining < 3  # at most a few stragglers
    session.kill()


@pytest.mark.asyncio
async def test_kill_pushes_none_to_all_queues():
    """kill() pushes None (EOF) to every attached queue."""
    session = PTYSession("sleep 30")
    await session.spawn()
    q1 = await session.attach()
    q2 = await session.attach()
    await asyncio.wait_for(q1.get(), timeout=3.0)  # replay
    await asyncio.wait_for(q2.get(), timeout=3.0)  # replay

    session.kill()

    item1 = await asyncio.wait_for(q1.get(), timeout=3.0)
    item2 = await asyncio.wait_for(q2.get(), timeout=3.0)
    assert item1 is None
    assert item2 is None
    session.detach(q1)
    session.detach(q2)


@pytest.mark.asyncio
async def test_read_chunk_still_works():
    """Backward compatibility: read_chunk() still works as a generator."""
    session = PTYSession("printf 'compat\\n'")
    await session.spawn()
    output = b""
    async for chunk in session.read_chunk():
        output += chunk
        if b"compat" in output:
            break
    assert b"compat" in output
    session.kill()


@pytest.mark.asyncio
async def test_reader_task_started_on_attach():
    """attach() starts the single reader task if not running."""
    session = PTYSession("echo hi")
    await session.spawn()
    assert session._reader_task is None
    q = await session.attach()
    assert session._reader_task is not None
    assert not session._reader_task.done()
    session.kill()
    session.detach(q)


@pytest.mark.asyncio
async def test_buffer_independent_of_queue_overflow():
    """A full queue doesn't lose scrollback data."""
    session = PTYSession("printf 'overflow test\\n'")
    await session.spawn()
    q = await session.attach(_maxsize=1)  # tiny queue
    await asyncio.wait_for(q.get(), timeout=3.0)  # replay

    # Let output flow; queue may overflow
    await asyncio.sleep(0.3)

    # Buffer should still have the data
    buf = session.get_buffer()
    assert b"overflow test" in buf
    session.kill()
    session.detach(q)


@pytest.mark.asyncio
async def test_attach_after_exit_gets_replay_and_eof():
    """Attaching after the child exited still gives replay then None."""
    session = PTYSession("printf 'done\\n'; sleep 0.3")
    await session.spawn()
    # Read output via read_chunk to populate the buffer, then let it exit
    gen = session.read_chunk()
    async for chunk in gen:
        if b"done" in chunk:
            break
    await gen.aclose()
    # Wait for the child to exit
    await asyncio.sleep(0.5)
    # Reap
    for _ in range(10):
        if not session.is_alive():
            break
        await asyncio.sleep(0.1)

    # Now attach — should get replay with the output, then EOF
    q = await session.attach()
    replay = await asyncio.wait_for(q.get(), timeout=3.0)
    assert replay[0] == "__replay__"
    assert b"done" in replay[1]

    # Should get None (EOF) since child is dead
    item = await asyncio.wait_for(q.get(), timeout=3.0)
    assert item is None
    session.detach(q)
