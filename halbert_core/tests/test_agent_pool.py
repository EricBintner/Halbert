# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the agent terminal pool (Plan B: B6)."""

import asyncio
import time

import pytest

from halbert_core.streaming.agent_pool import TerminalPool
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
