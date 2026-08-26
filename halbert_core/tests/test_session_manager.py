"""Tests for TerminalSessionManager (B1b)."""

import asyncio
import time
import pytest

from halbert_core.streaming.session_manager import (
    TerminalSessionManager,
    AtCapacityError,
    get_terminal_manager,
    set_terminal_manager,
)


# ---------------------------------------------------------------------------
# Fake PTYSession (no real fork) for manager-logic tests
# ---------------------------------------------------------------------------

class FakePTY:
    """In-memory PTYSession stand-in for manager logic tests."""

    def __init__(self, command="echo", alive=True, exit_code=None):
        self.command = command
        self._alive = alive
        self.exit_code = exit_code
        self.pid = 12345 if alive else None
        self.killed = False
        self._buffer = b"some output"

    async def spawn(self):
        return self.pid

    def is_alive(self):
        return self._alive and not self.killed

    def kill(self):
        self.killed = True
        self._alive = False

    def get_buffer(self):
        return self._buffer


def _manager_with_fake_sessions(n, max_sessions=2, ttl=60):
    """Build a manager and inject n fake sessions directly."""
    m = TerminalSessionManager(max_sessions=max_sessions, idle_ttl_seconds=ttl)
    for i in range(n):
        sid = f"sess-{i}"
        m._sessions[sid] = FakePTY(alive=True)
        m._last_activity[sid] = time.monotonic()
    return m


# ---------------------------------------------------------------------------
# Capacity + lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spawn_returns_id_and_tracks_session():
    m = TerminalSessionManager(max_sessions=2)
    sid = await m.spawn("echo hi")
    assert sid in m._sessions
    assert m.get(sid) is not None
    assert m.count == 1


@pytest.mark.asyncio
async def test_at_capacity_raises():
    m = _manager_with_fake_sessions(2, max_sessions=2)
    with pytest.raises(AtCapacityError):
        await m.spawn("echo nope")


@pytest.mark.asyncio
async def test_kill_removes_session():
    m = _manager_with_fake_sessions(1, max_sessions=2)
    assert m.kill("sess-0") is True
    assert m.count == 0
    assert m.get("sess-0") is None


def test_kill_unknown_returns_false():
    m = TerminalSessionManager()
    assert m.kill("nope") is False


def test_list_active_snapshot():
    m = _manager_with_fake_sessions(2, max_sessions=2)
    snap = m.list_active()
    assert len(snap) == 2
    assert "session_id" in snap[0]
    assert snap[0]["alive"] is True


def test_touch_resets_idle():
    m = _manager_with_fake_sessions(1, max_sessions=2, ttl=1)
    old = m._last_activity["sess-0"]
    # backdate
    m._last_activity["sess-0"] = time.monotonic() - 100
    m.touch("sess-0")
    assert m._last_activity["sess-0"] > old


# ---------------------------------------------------------------------------
# Reaper
# ---------------------------------------------------------------------------

def test_reaper_kills_idle_sessions():
    m = _manager_with_fake_sessions(2, max_sessions=2, ttl=5)
    # sess-0 idle past TTL, sess-1 recent
    m._last_activity["sess-0"] = time.monotonic() - 100
    m._last_activity["sess-1"] = time.monotonic()
    m._reap_once()
    assert "sess-0" not in m._sessions
    assert "sess-1" in m._sessions


def test_reaper_removes_dead_sessions():
    m = _manager_with_fake_sessions(2, max_sessions=2, ttl=60)
    # sess-0 already dead (exited), should be reaped regardless of idle
    m._sessions["sess-0"]._alive = False
    m._last_activity["sess-0"] = time.monotonic()  # not idle
    m._reap_once()
    assert "sess-0" not in m._sessions
    assert "sess-1" in m._sessions


@pytest.mark.asyncio
async def test_start_stop_reaper_lifecycle():
    m = TerminalSessionManager(max_sessions=2, idle_ttl_seconds=60)
    m.start_reaper()
    assert m._reaper_task is not None
    assert not m._reaper_task.done()
    m.stop_reaper()
    assert m._reaper_task is None


@pytest.mark.asyncio
async def test_shutdown_kills_all_and_stops_reaper():
    m = _manager_with_fake_sessions(2, max_sessions=2, ttl=60)
    m.start_reaper()
    await m.shutdown()
    assert m.count == 0
    assert m._reaper_task is None


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

def test_global_singleton_get_and_set():
    original = get_terminal_manager()
    custom = TerminalSessionManager(max_sessions=9)
    set_terminal_manager(custom)
    assert get_terminal_manager() is custom
    set_terminal_manager(original)  # restore


# ---------------------------------------------------------------------------
# One real-spawn integration test (exercises the real PTYSession)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_real_spawn_and_kill():
    m = TerminalSessionManager(max_sessions=2)
    sid = await m.spawn("printf 'hi\\n'")
    session = m.get(sid)
    assert session is not None
    # Drain the output so the child exits and is reaped
    chunks = []
    gen = session.read_chunk()
    try:
        try:
            while True:
                chunk = await asyncio.wait_for(gen.__anext__(), timeout=3.0)
                chunks.append(chunk)
        except (StopAsyncIteration, asyncio.TimeoutError):
            pass
    finally:
        await gen.aclose()
    assert b"hi" in b"".join(chunks)
    assert m.kill(sid) is True
    assert m.count == 0

# ---------------------------------------------------------------------------
# Dashboard app lifecycle wiring (regression: the reaper must actually be
# started/stopped by the FastAPI app — previously start_reaper, stop_reaper
# and shutdown had zero production call sites, so dead PTY sessions were
# never reaped and live sessions survived app shutdown).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_app_startup_starts_reaper_and_shutdown_stops_it():
    from unittest.mock import AsyncMock, MagicMock, patch

    from halbert_core.dashboard import app as dashboard_app
    from halbert_core.streaming import session_manager as session_manager_module

    manager = MagicMock()
    manager.shutdown = AsyncMock()

    class _DummyThread:
        """Swallow the delayed background-service starters in startup_event."""
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    app = dashboard_app.create_app()

    with patch.object(
        session_manager_module, "get_terminal_manager", return_value=manager
    ), patch("threading.Thread", _DummyThread), patch.object(
        dashboard_app, "_find_config_registry", return_value=None
    ), patch("halbert_core.knowledge.get_self_knowledge") as mock_sk, patch(
        "halbert_core.ingestion.service.get_ingestion_service"
    ):
        # Truthy existing identity -> bootstrap_identity() is not invoked
        mock_sk.return_value.get_identity.return_value = {"name": "halbert"}

        for handler in app.router.on_startup:
            await handler()
        manager.start_reaper.assert_called_once_with()

        for handler in app.router.on_shutdown:
            await handler()
        manager.shutdown.assert_awaited_once_with()
