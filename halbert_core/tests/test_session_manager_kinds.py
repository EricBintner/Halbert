# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for session manager kinds, caps, and TTLs (Plan B: B5)."""

import time

import pytest

from halbert_core.streaming.session_manager import (
    TerminalSessionManager,
    AtCapacityError,
)


class FakePTY:
    def __init__(self, command="echo", alive=True, exit_code=None):
        self.command = command
        self._alive = alive
        self.exit_code = exit_code
        self.pid = 12345 if alive else None
        self.killed = False
        self._buffer = b"some output"
        self.last_output_at = 0.0

    async def spawn(self):
        return self.pid

    def is_alive(self):
        return self._alive and not self.killed

    def kill(self):
        self.killed = True
        self._alive = False

    def get_buffer(self):
        return self._buffer


def _make_manager(**kwargs):
    m = TerminalSessionManager(**kwargs)
    return m


def _inject(m, sid, kind="oneshot", alive=True, watched=True):
    m._sessions[sid] = FakePTY(alive=alive)
    m._last_activity[sid] = time.monotonic()
    m._kinds[sid] = kind
    m._watched[sid] = watched
    m._attach_counts[sid] = 0
    m._block_open[sid] = False


# ---------------------------------------------------------------------------
# Per-kind caps
# ---------------------------------------------------------------------------

class TestKindCaps:
    @pytest.mark.asyncio
    async def test_spawn_with_kind_user(self):
        m = _make_manager(max_sessions=8)
        sid = await m.spawn("bash", kind="user")
        assert m._kinds[sid] == "user"

    @pytest.mark.asyncio
    async def test_spawn_with_kind_agent_pool(self):
        m = _make_manager(max_sessions=8)
        sid = await m.spawn("bash", kind="agent-pool")
        assert m._kinds[sid] == "agent-pool"

    @pytest.mark.asyncio
    async def test_spawn_with_kind_oneshot(self):
        m = _make_manager(max_sessions=8)
        sid = await m.spawn("echo hi", kind="oneshot")
        assert m._kinds[sid] == "oneshot"

    @pytest.mark.asyncio
    async def test_default_kind_is_oneshot(self):
        m = _make_manager(max_sessions=8)
        sid = await m.spawn("echo hi")
        assert m._kinds[sid] == "oneshot"

    @pytest.mark.asyncio
    async def test_per_kind_cap_user(self):
        m = _make_manager(max_sessions=8, kind_caps={"user": 2, "agent-pool": 3, "oneshot": 2})
        await m.spawn("bash", kind="user")
        await m.spawn("bash", kind="user")
        with pytest.raises(AtCapacityError):
            await m.spawn("bash", kind="user")

    @pytest.mark.asyncio
    async def test_per_kind_cap_agent_pool(self):
        m = _make_manager(max_sessions=8, kind_caps={"user": 3, "agent-pool": 2, "oneshot": 2})
        await m.spawn("bash", kind="agent-pool")
        await m.spawn("bash", kind="agent-pool")
        with pytest.raises(AtCapacityError):
            await m.spawn("bash", kind="agent-pool")

    @pytest.mark.asyncio
    async def test_per_kind_cap_independent(self):
        """Hitting the user cap doesn't block agent-pool spawns."""
        m = _make_manager(max_sessions=8, kind_caps={"user": 1, "agent-pool": 3, "oneshot": 2})
        await m.spawn("bash", kind="user")
        # user cap is full, but agent-pool should still work
        sid = await m.spawn("bash", kind="agent-pool")
        assert m._kinds[sid] == "agent-pool"

    @pytest.mark.asyncio
    async def test_total_cap_still_enforced(self):
        """Total cap is enforced even if per-kind caps would allow more."""
        m = _make_manager(max_sessions=2, kind_caps={"user": 3, "agent-pool": 3, "oneshot": 3})
        await m.spawn("bash", kind="user")
        await m.spawn("bash", kind="agent-pool")
        with pytest.raises(AtCapacityError):
            await m.spawn("bash", kind="oneshot")


# ---------------------------------------------------------------------------
# Watched flag
# ---------------------------------------------------------------------------

class TestWatched:
    @pytest.mark.asyncio
    async def test_spawn_watched_default_true(self):
        m = _make_manager(max_sessions=8)
        sid = await m.spawn("bash", kind="user")
        assert m._watched[sid] is True

    @pytest.mark.asyncio
    async def test_spawn_watched_false(self):
        m = _make_manager(max_sessions=8)
        sid = await m.spawn("bash", kind="user", watched=False)
        assert m._watched[sid] is False


# ---------------------------------------------------------------------------
# Attach client / detach client
# ---------------------------------------------------------------------------

class TestAttachDetach:
    def test_attach_client_increments(self):
        m = _make_manager(max_sessions=8)
        _inject(m, "s1", kind="user")
        m.attach_client("s1")
        assert m._attach_counts["s1"] == 1
        m.attach_client("s1")
        assert m._attach_counts["s1"] == 2

    def test_detach_client_decrements(self):
        m = _make_manager(max_sessions=8)
        _inject(m, "s1", kind="user")
        m.attach_client("s1")
        m.attach_client("s1")
        m.detach_client("s1")
        assert m._attach_counts["s1"] == 1
        m.detach_client("s1")
        assert m._attach_counts["s1"] == 0

    def test_detach_client_never_negative(self):
        m = _make_manager(max_sessions=8)
        _inject(m, "s1", kind="user")
        m.detach_client("s1")
        assert m._attach_counts["s1"] == 0

    def test_attach_client_unknown_session_noop(self):
        m = _make_manager(max_sessions=8)
        m.attach_client("nope")
        # Should not raise


# ---------------------------------------------------------------------------
# Block open tracking
# ---------------------------------------------------------------------------

class TestBlockOpen:
    def test_set_block_open(self):
        m = _make_manager(max_sessions=8)
        _inject(m, "s1", kind="agent-pool")
        m.set_block_open("s1", True)
        assert m._block_open["s1"] is True

    def test_set_block_closed(self):
        m = _make_manager(max_sessions=8)
        _inject(m, "s1", kind="agent-pool")
        m.set_block_open("s1", True)
        m.set_block_open("s1", False)
        assert m._block_open["s1"] is False

    def test_set_block_open_unknown_session_noop(self):
        m = _make_manager(max_sessions=8)
        m.set_block_open("nope", True)
        # Should not raise


# ---------------------------------------------------------------------------
# Per-kind TTL reaper
# ---------------------------------------------------------------------------

class TestPerKindTTL:
    def test_user_session_not_reaped_with_attached_client(self):
        m = _make_manager(
            max_sessions=8,
            kind_ttls={"user": 1800, "agent-pool": 900, "oneshot": 60},
        )
        _inject(m, "s1", kind="user")
        m._last_activity["s1"] = time.monotonic() - 9999  # way past TTL
        m.attach_client("s1")
        m._reap_once()
        assert "s1" in m._sessions

    def test_user_session_reaped_when_detached(self):
        m = _make_manager(
            max_sessions=8,
            kind_ttls={"user": 100, "agent-pool": 900, "oneshot": 60},
        )
        _inject(m, "s1", kind="user")
        m._last_activity["s1"] = time.monotonic() - 200  # past 100s TTL
        assert m._attach_counts["s1"] == 0
        m._reap_once()
        assert "s1" not in m._sessions

    def test_agent_pool_not_reaped_with_open_block(self):
        m = _make_manager(
            max_sessions=8,
            kind_ttls={"user": 1800, "agent-pool": 100, "oneshot": 60},
        )
        _inject(m, "s1", kind="agent-pool")
        m._last_activity["s1"] = time.monotonic() - 9999
        m.set_block_open("s1", True)
        m._reap_once()
        assert "s1" in m._sessions

    def test_agent_pool_reaped_when_no_open_block(self):
        m = _make_manager(
            max_sessions=8,
            kind_ttls={"user": 1800, "agent-pool": 100, "oneshot": 60},
        )
        _inject(m, "s1", kind="agent-pool")
        m._last_activity["s1"] = time.monotonic() - 200
        m.set_block_open("s1", False)
        m._reap_once()
        assert "s1" not in m._sessions

    def test_oneshot_reaped_past_ttl(self):
        m = _make_manager(
            max_sessions=8,
            kind_ttls={"user": 1800, "agent-pool": 900, "oneshot": 60},
        )
        _inject(m, "s1", kind="oneshot")
        m._last_activity["s1"] = time.monotonic() - 100
        m._reap_once()
        assert "s1" not in m._sessions

    def test_oneshot_not_reaped_within_ttl(self):
        m = _make_manager(
            max_sessions=8,
            kind_ttls={"user": 1800, "agent-pool": 900, "oneshot": 60},
        )
        _inject(m, "s1", kind="oneshot")
        m._last_activity["s1"] = time.monotonic() - 10
        m._reap_once()
        assert "s1" in m._sessions

    def test_dead_session_reaped_regardless_of_kind(self):
        m = _make_manager(max_sessions=8)
        _inject(m, "s1", kind="user", alive=False)
        m.attach_client("s1")
        m._reap_once()
        assert "s1" not in m._sessions


# ---------------------------------------------------------------------------
# list_active with kind/owner/watched/block_open/attach_count
# ---------------------------------------------------------------------------

class TestListActive:
    def test_list_active_includes_kind(self):
        m = _make_manager(max_sessions=8)
        _inject(m, "s1", kind="user")
        _inject(m, "s2", kind="agent-pool")
        snap = m.list_active()
        kinds = {s["session_id"]: s["kind"] for s in snap}
        assert kinds["s1"] == "user"
        assert kinds["s2"] == "agent-pool"

    def test_list_active_includes_watched(self):
        m = _make_manager(max_sessions=8)
        _inject(m, "s1", kind="user", watched=True)
        _inject(m, "s2", kind="user", watched=False)
        snap = m.list_active()
        watched = {s["session_id"]: s["watched"] for s in snap}
        assert watched["s1"] is True
        assert watched["s2"] is False

    def test_list_active_includes_block_open(self):
        m = _make_manager(max_sessions=8)
        _inject(m, "s1", kind="agent-pool")
        m.set_block_open("s1", True)
        snap = m.list_active()
        s1 = [s for s in snap if s["session_id"] == "s1"][0]
        assert s1["block_open"] is True

    def test_list_active_includes_attach_count(self):
        m = _make_manager(max_sessions=8)
        _inject(m, "s1", kind="user")
        m.attach_client("s1")
        m.attach_client("s1")
        snap = m.list_active()
        s1 = [s for s in snap if s["session_id"] == "s1"][0]
        assert s1["attach_count"] == 2


# ---------------------------------------------------------------------------
# kill cleans up kind/watched/attach/block metadata
# ---------------------------------------------------------------------------

class TestKillCleanup:
    def test_kill_removes_kind_metadata(self):
        m = _make_manager(max_sessions=8)
        _inject(m, "s1", kind="user")
        m.kill("s1")
        assert "s1" not in m._kinds
        assert "s1" not in m._watched
        assert "s1" not in m._attach_counts
        assert "s1" not in m._block_open


# ---------------------------------------------------------------------------
# Default kind_caps and kind_ttls
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_default_kind_caps(self):
        m = TerminalSessionManager(max_sessions=8)
        assert m._kind_caps == {"user": 3, "agent-pool": 3, "oneshot": 2}

    def test_default_kind_ttls(self):
        m = TerminalSessionManager(max_sessions=8)
        assert m._kind_ttls == {"user": 1800, "agent-pool": 900, "oneshot": 60}
