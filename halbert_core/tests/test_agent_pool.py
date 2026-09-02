# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the agent terminal pool (Plan B: B6)."""

import asyncio
import time

import pytest

from halbert_core.streaming.agent_pool import TerminalPool, _BoundedBlockOutput
from halbert_core.streaming.session_manager import TerminalSessionManager, AtCapacityError


class FakePTY:
    def __init__(self, command="bash", alive=True):
        self.command = command
        self._alive = alive
        self.pid = 12345
        self.exit_code = None
        self.killed = False
        self._buffer = b""
        self.last_output_at = 0.0
        self._written = []

    async def spawn(self):
        return self.pid

    def is_alive(self):
        return self._alive and not self.killed

    def kill(self):
        self.killed = True
        self._alive = False

    def get_buffer(self):
        return self._buffer

    async def write_stdin(self, data):
        self._written.append(data)

    def resize(self, cols, rows):
        pass

    async def attach(self, maxsize=0):
        q = asyncio.Queue()
        q.put_nowait(("__replay__", self._buffer))
        return q

    def detach(self, q):
        pass


def _make_manager_with_pool(cap=3, max_sessions=8):
    m = TerminalSessionManager(
        max_sessions=max_sessions,
        kind_caps={"user": 3, "agent-pool": cap, "oneshot": 2},
    )
    pool = TerminalPool(m, cap=cap)
    return m, pool


# ---------------------------------------------------------------------------
# acquire
# ---------------------------------------------------------------------------

class TestAcquire:
    @pytest.mark.asyncio
    async def test_acquire_spawns_new_session(self):
        m, pool = _make_manager_with_pool()
        sid, session = await pool.acquire()
        assert sid is not None
        assert session is not None
        assert m._kinds[sid] == "agent-pool"
        m.kill(sid)

    @pytest.mark.asyncio
    async def test_acquire_reuses_idle_session(self):
        m, pool = _make_manager_with_pool()
        sid1, _ = await pool.acquire()
        pool.release(sid1)
        sid2, session2 = await pool.acquire()
        assert sid2 == sid1  # reused
        m.kill(sid1)

    @pytest.mark.asyncio
    async def test_acquire_returns_none_at_cap(self):
        m, pool = _make_manager_with_pool(cap=2)
        # Acquire all cap sessions
        sid1, _ = await pool.acquire()
        sid2, _ = await pool.acquire()
        # Both busy — should return None
        result = await pool.acquire()
        assert result is None
        m.kill(sid1)
        m.kill(sid2)

    @pytest.mark.asyncio
    async def test_acquire_after_release_at_cap(self):
        m, pool = _make_manager_with_pool(cap=1)
        sid1, _ = await pool.acquire()
        # At cap and busy
        assert await pool.acquire() is None
        # Release and acquire again
        pool.release(sid1)
        sid2, _ = await pool.acquire()
        assert sid2 == sid1
        m.kill(sid1)


# ---------------------------------------------------------------------------
# release
# ---------------------------------------------------------------------------

class TestRelease:
    @pytest.mark.asyncio
    async def test_release_marks_session_not_busy(self):
        m, pool = _make_manager_with_pool()
        sid, _ = await pool.acquire()
        assert m._block_open[sid] is True
        pool.release(sid)
        assert m._block_open[sid] is False
        m.kill(sid)

    @pytest.mark.asyncio
    async def test_release_unknown_session_noop(self):
        m, pool = _make_manager_with_pool()
        pool.release("nope")  # should not raise


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------

class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_kills_all_pool_sessions(self):
        m, pool = _make_manager_with_pool(cap=3)
        sid1, _ = await pool.acquire()
        sid2, _ = await pool.acquire()
        await pool.shutdown()
        assert sid1 not in m._sessions
        assert sid2 not in m._sessions

    @pytest.mark.asyncio
    async def test_shutdown_with_no_sessions(self):
        m, pool = _make_manager_with_pool()
        await pool.shutdown()  # should not raise


# ---------------------------------------------------------------------------
# Pool session tracking
# ---------------------------------------------------------------------------

class TestPoolTracking:
    @pytest.mark.asyncio
    async def test_pool_tracks_owned_sessions(self):
        m, pool = _make_manager_with_pool()
        sid, _ = await pool.acquire()
        assert sid in pool._sessions
        m.kill(sid)

    @pytest.mark.asyncio
    async def test_pool_remove_on_kill(self):
        m, pool = _make_manager_with_pool()
        sid, _ = await pool.acquire()
        pool._evict(sid)
        m.kill(sid)
        assert sid not in pool._sessions


# ---------------------------------------------------------------------------
# run_block (integration with real PTY)
# ---------------------------------------------------------------------------

class TestRunBlock:
    @pytest.mark.asyncio
    async def test_run_block_echo(self):
        m, pool = _make_manager_with_pool(cap=3)
        result = await pool.run_block("echo hello", timeout=5.0)
        assert result is not None
        assert result["exit_code"] == 0
        assert b"hello" in result["output_head"].encode() or "hello" in result["output_head"]
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_run_block_exit_code(self):
        m, pool = _make_manager_with_pool(cap=3)
        result = await pool.run_block("exit 7", timeout=5.0)
        assert result is not None
        assert result["exit_code"] == 7
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_run_block_has_block_id(self):
        m, pool = _make_manager_with_pool(cap=3)
        result = await pool.run_block("echo test", timeout=5.0)
        assert result is not None
        assert "block_id" in result
        assert result["block_id"]
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_run_block_has_session_id(self):
        m, pool = _make_manager_with_pool(cap=3)
        result = await pool.run_block("echo test", timeout=5.0)
        assert result is not None
        assert "session_id" in result
        assert result["session_id"]
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_run_block_has_duration(self):
        m, pool = _make_manager_with_pool(cap=3)
        result = await pool.run_block("echo test", timeout=5.0)
        assert result is not None
        assert "duration" in result
        assert result["duration"] >= 0.0
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_run_block_timeout(self):
        m, pool = _make_manager_with_pool(cap=3)
        result = await pool.run_block("sleep 30", timeout=1.0)
        assert result is not None
        # Should have timed out — exit code is non-zero
        assert result["exit_code"] != 0
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_run_block_releases_session(self):
        m, pool = _make_manager_with_pool(cap=1)
        result = await pool.run_block("echo test", timeout=5.0)
        assert result is not None
        # After run_block, the session should be released (not busy)
        sid = result["session_id"]
        assert m._block_open.get(sid) is False
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_run_block_cwd(self):
        m, pool = _make_manager_with_pool(cap=3)
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await pool.run_block("pwd", cwd=tmpdir, timeout=5.0)
            assert result is not None
            assert result["exit_code"] == 0
            assert tmpdir in result["output_head"] or tmpdir in result.get("output_tail", "")
        await pool.shutdown()


# ---------------------------------------------------------------------------
# Resource safety (R04-F3, R04-F4)
# ---------------------------------------------------------------------------

class TestPoolDoesNotLeakBusySlots:
    """R04-F3. acquire() marks a session busy; the reaper then exempts an
    agent-pool session with an open block. So every path out of run_block has
    to clear the flag, or the slot is busy forever AND immune to the reaper —
    three of those and a cap-3 pool is dead for the life of the process."""

    async def _pool_that_fails_at(self, step):
        m, pool = _make_manager_with_pool(cap=3)
        sid, session = await pool.acquire()
        m.set_block_open(sid, False)  # undo; run_block acquires its own

        real_attach = session.attach

        async def boom_attach(maxsize=0):
            raise OSError("fanout queue unavailable")

        async def never_replays(maxsize=0):
            return asyncio.Queue()  # nothing to get -> the 5s replay wait times out

        async def boom_write(data):
            raise BrokenPipeError("shell went away")

        if step == "attach":
            session.attach = boom_attach
        elif step == "replay":
            session.attach = never_replays
        elif step == "write":
            session.attach = real_attach
            session.write_stdin = boom_write
        return m, pool, sid

    @pytest.mark.asyncio
    @pytest.mark.parametrize("step", ["attach", "write"])
    async def test_a_failure_before_the_drain_loop_releases_the_slot(self, step):
        m, pool, sid = await self._pool_that_fails_at(step)

        with pytest.raises(Exception):
            await pool.run_block("echo hi", timeout=5.0)

        assert m._block_open.get(sid) is not True, (
            f"failure at {step} left the pool slot permanently busy"
        )
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_a_slot_released_by_an_error_can_be_acquired_again(self):
        m, pool, sid = await self._pool_that_fails_at("attach")
        with pytest.raises(Exception):
            await pool.run_block("echo hi", timeout=5.0)

        again = await pool.acquire()
        assert again is not None, "the pool could not reuse the released slot"
        await pool.shutdown()


class TestBlockOutputIsBounded:
    """R04-F4. block_output accumulated every byte the command produced and
    only cut it down to a 20-line head and a 4 KiB tail after completion, so
    `cat` on a large file was held whole in memory (~800 MB reproduced by the
    review). The bound has to apply as the bytes arrive, which is a property
    of the accumulator, not of the returned result."""

    def test_the_accumulator_keeps_both_ends_and_drops_the_middle(self):
        acc = _BoundedBlockOutput(head_cap=10, tail_cap=10)
        acc.extend(b"HEAD______")
        acc.extend(b"x" * 1000)
        acc.extend(b"______TAIL")

        assert len(acc) == 20, "the accumulator grew past its caps"
        assert acc.dropped == 1000
        out = acc.bytes()
        assert out.startswith(b"HEAD______")
        assert out.endswith(b"______TAIL")
        assert b"1000 bytes elided" in out

    def test_output_under_the_cap_is_kept_whole_and_unmarked(self):
        acc = _BoundedBlockOutput(head_cap=10, tail_cap=10)
        acc.extend(b"short")
        assert acc.dropped == 0
        assert acc.bytes() == b"short"
        assert len(acc) == 5

    def test_a_chunk_straddling_the_head_cap_is_split_not_lost(self):
        acc = _BoundedBlockOutput(head_cap=4, tail_cap=100)
        acc.extend(b"abcdefgh")
        assert acc.dropped == 0
        assert acc.bytes() == b"abcdefgh"

    def test_peak_retention_is_capped_no_matter_how_much_arrives(self):
        acc = _BoundedBlockOutput(head_cap=1024, tail_cap=1024)
        for _ in range(4096):
            acc.extend(b"y" * 1024)  # 4 MiB through a 2 KiB accumulator
        assert len(acc) <= 2048

    @pytest.mark.asyncio
    async def test_head_and_tail_still_come_from_the_right_ends(self):
        m, pool = _make_manager_with_pool(cap=3)
        result = await pool.run_block(
            "echo FIRSTLINE; for i in $(seq 1 2000); do echo padding-$i; done; echo LASTLINE",
            timeout=60.0,
        )
        assert result is not None
        assert "FIRSTLINE" in result["output_head"]
        assert "LASTLINE" in result["output_tail"]
        await pool.shutdown()
