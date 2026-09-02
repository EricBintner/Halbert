# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""C4-03: ThreadManager.tick() has a production caller.

``tick()`` closes paused threads past the grace window and then runs the R8
Consolidator, but nothing in the dashboard ever called it — a paused thread
stayed paused until the next user turn happened to sweep it, and cross-thread
consolidation never ran at all. The dashboard now runs a heartbeat task
(``run_thread_tick_loop``) every ``heartbeat_s`` (being.yml, else 60 s) that
ticks the manager off the event loop whenever no turn is in flight.
"""

import asyncio
from datetime import datetime

import pytest

pytest.importorskip("fastapi")

from halbert_core.agents.conversation_sqlite import SqliteConversationStore  # noqa: E402
from halbert_core.agents.thread_signals import GRACE_MINUTES  # noqa: E402
from halbert_core.agents.threads import ThreadManager  # noqa: E402
from halbert_core.dashboard import app as dashboard_app  # noqa: E402
from halbert_core.intake.signals import analyze_message  # noqa: E402

NOW = datetime(2026, 9, 2, 9, 0).timestamp()


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def tm():
    store = SqliteConversationStore(":memory:")
    clock = Clock(NOW)
    manager = ThreadManager(store, now=clock)
    manager.clock = clock
    yield manager
    store.close()


def _paused_past_grace(tm):
    """One finished thread, paused by a successor, then the grace window elapses."""
    text = "add a samba share for the media folder"
    turn = tm.begin_turn(text, analyze_message(text), "s1")
    tm.end_turn(turn, assistant_text="Added it.", blocks=[], terminal_block_ids=[], diff_proposals=[])
    tm.new_thread("Scanner share", "x", from_thread_id=turn.thread_id)
    tm.clock.advance(GRACE_MINUTES * 60)
    assert tm.store.get_thread(turn.thread_id)["status"] == "paused"
    return turn.thread_id


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------

def test_paused_thread_past_grace_closes_without_a_user_turn(tm, monkeypatch):
    thread_id = _paused_past_grace(tm)
    turns = []
    monkeypatch.setattr(tm, "begin_turn", lambda *a, **k: turns.append(a))

    beats = asyncio.run(dashboard_app.run_thread_tick_loop(
        0.01, tick=tm.tick, turn_busy=lambda: False, max_beats=1,
    ))

    assert beats == 1
    assert tm.store.get_thread(thread_id)["status"] == "closed"
    assert turns == [], "the sweep must not need a user turn to run"


def test_tick_is_skipped_while_a_turn_is_in_flight(tm):
    thread_id = _paused_past_grace(tm)
    ticks = []

    def tick():
        ticks.append(1)
        return tm.tick()

    asyncio.run(dashboard_app.run_thread_tick_loop(
        0.01, tick=tick, turn_busy=lambda: True, max_beats=3,
    ))

    assert ticks == []
    assert tm.store.get_thread(thread_id)["status"] == "paused"


def test_a_failing_tick_does_not_stop_the_loop():
    calls = []

    def tick():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("store locked")
        return []

    beats = asyncio.run(dashboard_app.run_thread_tick_loop(
        0.01, tick=tick, turn_busy=lambda: False, max_beats=2,
    ))
    assert beats == 2 and len(calls) == 2


def test_tick_runs_off_the_event_loop_thread():
    import threading

    seen = []
    asyncio.run(dashboard_app.run_thread_tick_loop(
        0.01, tick=lambda: seen.append(threading.current_thread()), turn_busy=lambda: False, max_beats=1,
    ))
    assert seen and seen[0] is not threading.main_thread()


# ---------------------------------------------------------------------------
# the production wiring: interval, busy check, start/stop
# ---------------------------------------------------------------------------

def test_heartbeat_interval_defaults_to_60s(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    assert dashboard_app.heartbeat_interval_s() == 60.0


def test_heartbeat_interval_reads_being_yml(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    (tmp_path / "being.yml").write_text("voice: first_person\nheartbeat_s: 15\n")
    assert dashboard_app.heartbeat_interval_s() == 15.0


def test_heartbeat_interval_has_a_floor(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    (tmp_path / "being.yml").write_text("heartbeat_s: 0\n")
    assert dashboard_app.heartbeat_interval_s() == dashboard_app.MIN_HEARTBEAT_S


def test_heartbeat_interval_survives_a_broken_being_yml(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    (tmp_path / "being.yml").write_text("heartbeat_s: [not: closed\n")
    assert dashboard_app.heartbeat_interval_s() == 60.0


def test_agent_turn_busy_reads_the_turn_lock(monkeypatch):
    from halbert_core.dashboard.routes import agent as agent_routes

    class FakeAgent:
        _turn_lock = None

    async def probe():
        agent = FakeAgent()
        monkeypatch.setattr(agent_routes, "_agent_instance", agent)
        assert dashboard_app._agent_turn_busy() is False   # no lock built yet
        agent._turn_lock = asyncio.Lock()
        assert dashboard_app._agent_turn_busy() is False   # lock free
        async with agent._turn_lock:
            assert dashboard_app._agent_turn_busy() is True  # a turn in flight

    monkeypatch.setattr(agent_routes, "_agent_instance", None)
    assert dashboard_app._agent_turn_busy() is False        # no agent yet
    asyncio.run(probe())


def test_start_and_stop_heartbeat_on_an_app():
    from fastapi import FastAPI

    ticks = []

    async def scenario():
        app = FastAPI()
        task = dashboard_app.start_thread_tick_heartbeat(
            app, interval_s=0.01, tick=lambda: ticks.append(1), turn_busy=lambda: False,
        )
        assert app.state.thread_tick_task is task and not task.done()
        await asyncio.sleep(0.1)
        await dashboard_app.stop_thread_tick_heartbeat(app)
        assert task.done()
        assert app.state.thread_tick_task is None

    asyncio.run(scenario())
    assert ticks, "the heartbeat never ticked"


def test_stop_heartbeat_is_a_no_op_without_one():
    from fastapi import FastAPI

    asyncio.run(dashboard_app.stop_thread_tick_heartbeat(FastAPI()))
