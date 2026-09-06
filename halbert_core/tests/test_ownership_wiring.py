# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The writers consult ownership — the tick, the transcript, the receipts,
and one sensor output as the reference wiring.

``.handoff/DESIGN-PERSONA-LAYERS-2026-09-06.md`` §4.2 table and §5.3. The
leak these tests close first: before this, a guest conversation ran the
cognitive tick against Halbert's own ``PersonaCognition`` and semantic
memory (§1.6).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.llm_client import LLMResponse
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.threads import ThreadManager
from halbert_core.config.being_config import BeingConfig
from halbert_core.continuity.state_store import ACTOR_AGENT
from halbert_core.continuity.timeline import TimelineStore
from halbert_core.integrations.frigate.frigate_event_mapper import FrigateEventMapper
from halbert_core.integrations.frigate.frigate_mqtt_subscriber import TOPIC_EVENTS
from halbert_core.persona import guest, private_sources, sibling
from halbert_core.persona.guest import GuestHome
from halbert_core.prompts.agent_prompts import AgentPromptBuilder


HOME = GuestHome(base_url="http://127.0.0.1:8002", persona_id="marnie-7", label="H2")


@pytest.fixture(autouse=True)
def _fresh():
    guest.reset_for_tests()
    private_sources.reset_for_tests()
    yield
    guest.reset_for_tests()
    private_sources.reset_for_tests()


def _front(home=HOME, name="Marnie"):
    persona, _ = guest.GuestPersona.from_payload({"name": name})
    return guest.offer(persona, offered_by="h2-node", offered_by_name="H2", home=home)


class _Transport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, body, headers):
        self.calls.append((method, url, body))
        return 200, {"success": True}


# ---------------------------------------------------------------------------
# The tick
# ---------------------------------------------------------------------------

class _RecordingLLM:
    tools_supported = None

    async def chat(self, messages, tools=None, **kwargs):
        return LLMResponse(content="answer", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        yield "answer"


def _agent(tick):
    cfg = BeingConfig(name="Halbert-Test")
    builder = AgentPromptBuilder(voice="first_person", being_cfg=cfg)
    return AgentStateMachine(llm_client=_RecordingLLM(), prompt_builder=builder, max_loops=2, cognition_tick=tick)


async def _turn(agent, query="is the garage shut?"):
    events = []
    with patch("halbert_core.integrations.cognition_wiring.get_cognition", return_value=SimpleNamespace()):
        async for event in agent.process(query, session_id="wiring"):
            events.append(event)
    return events


class TestTheTick:

    async def test_without_a_guest_the_tick_runs_once_as_before(self):
        """Once per turn, with the user's message. (That the reply it sees
        is REFLECTING's stand-in rather than the real one is the open
        defect recorded in the attunement plan, not this change's.)"""
        calls = []
        agent = _agent(lambda cognition, user_message, assistant_response: calls.append(user_message))
        await _turn(agent)
        assert calls == ["is the garage shut?"]

    async def test_with_a_guest_the_tick_is_skipped_and_the_turn_goes_home(self, monkeypatch):
        calls = []
        transport = _Transport()
        monkeypatch.setattr(sibling, "default_transport", transport)
        session = _front()
        agent = _agent(lambda **kw: calls.append(kw))
        await _turn(agent)
        assert calls == []
        posts = [b for m, u, b in transport.calls if m == "POST" and u.endswith("/memory-v2/memories")]
        assert len(posts) == 1
        assert "is the garage shut?" in posts[0]["content"]
        assert "Marnie: answer" in posts[0]["content"]
        assert session.id in posts[0]["tags"]

    async def test_with_a_guest_and_no_home_the_user_is_told(self):
        calls = []
        _front(home=None)
        agent = _agent(lambda **kw: calls.append(kw))
        events = await _turn(agent)
        assert calls == []
        said = [e.data.get("content", "") for e in events if e.type == "thinking"]
        assert any("will not remember" in s for s in said), said


# ---------------------------------------------------------------------------
# The transcript
# ---------------------------------------------------------------------------

def _rows(store):
    return store._conn.execute("SELECT role, content, metadata FROM messages ORDER BY id").fetchall()


class TestMessages:

    def test_without_a_guest_rows_are_written_as_before(self):
        store = SqliteConversationStore(":memory:")
        store.create("t1")
        assert store.append_message("t1", "user", "hello", metadata={"k": 1}) is not None
        (row,) = _rows(store)
        assert row[1] == "hello" and '"k": 1' in row[2] and "guest" not in row[2]

    def test_guest_normal_rows_carry_the_session_tag(self):
        session = _front()
        store = SqliteConversationStore(":memory:")
        store.create("t1")
        assert store.append_message("t1", "user", "hello", metadata={"k": 1}) is not None
        (row,) = _rows(store)
        assert f"guest:{session.id}" in row[2]
        assert f"guest-session-{session.id}" in row[2]
        assert '"k": 1' in row[2]

    def test_guest_private_rows_are_not_written(self):
        _front()
        private_sources.assign("webcam:0")
        store = SqliteConversationStore(":memory:")
        store.create("t1")
        assert store.append_message("t1", "user", "hello") is None
        assert store.append_message("t1", "assistant", "hi") is None
        assert _rows(store) == []

    def test_forget_request_removes_a_sessions_rows_and_nothing_else(self):
        store = SqliteConversationStore(":memory:")
        store.create("t1")
        store.append_message("t1", "user", "before")
        session = _front()
        store.append_message("t1", "user", "private-ish")
        store.append_message("t1", "assistant", "reply")
        guest.withdraw()
        store.append_message("t1", "user", "after")
        assert store.forget_request(f"guest-session-{session.id}") == 2
        assert [r[1] for r in _rows(store)] == ["before", "after"]
        assert store.forget_request(f"guest-session-{session.id}") == 0


# ---------------------------------------------------------------------------
# The receipts
# ---------------------------------------------------------------------------

class _RecordingStateStore:
    calls = []

    def __init__(self, *a, **kw):
        pass

    def record_state(self, *args, **kwargs):
        _RecordingStateStore.calls.append((args, kwargs))


@pytest.fixture
def receipts(monkeypatch, tmp_path):
    _RecordingStateStore.calls = []
    monkeypatch.setattr("halbert_core.continuity.state_store.StateStore", _RecordingStateStore)
    monkeypatch.setattr("halbert_core.continuity.state_store.default_state_db_path", lambda: tmp_path / "s.db")
    monkeypatch.setattr("halbert_core.agents.receipt._command_lines", lambda blocks: ["ls ✓"])
    monkeypatch.setattr("halbert_core.agents.receipt._file_lines", lambda blocks, diffs: [])
    store = SqliteConversationStore(":memory:")
    tm = ThreadManager(store, now=lambda: 1000.0)
    store.create_thread("t1", "a thread")
    store.append_message("t1", "user", "hello")
    return tm, _RecordingStateStore.calls


class TestReceipts:

    def test_without_a_guest_receipts_are_the_agents(self, receipts):
        tm, calls = receipts
        tm._record_thread_state("t1", {"id": "t1"}, 1000.0)
        assert calls, "no receipt recorded"
        kwargs = calls[0][1]
        assert kwargs["actor"] == ACTOR_AGENT
        assert kwargs["request_id"] == "threadclose-t1"

    def test_guest_normal_receipts_carry_the_session(self, receipts):
        tm, calls = receipts
        session = _front()
        tm._record_thread_state("t1", {"id": "t1"}, 1000.0)
        assert calls
        kwargs = calls[0][1]
        assert kwargs["actor"] == f"guest:{session.id}"
        assert kwargs["request_id"] == f"guest-session-{session.id}"

    def test_guest_private_writes_no_receipt(self, receipts):
        tm, calls = receipts
        _front()
        private_sources.assign("webcam:0")
        tm._record_thread_state("t1", {"id": "t1"}, 1000.0)
        assert calls == []


# ---------------------------------------------------------------------------
# One sensor output — Frigate, which already names its camera
# ---------------------------------------------------------------------------

def _detection(camera="patio", label="person"):
    return {
        "type": "new",
        "after": {"id": "1", "camera": camera, "label": label, "sub_label": None,
                  "current_zones": [], "top_score": 0.9, "start_time": 500.0},
    }


class TestFrigateGate:

    @pytest.fixture
    def timeline(self, tmp_path):
        return TimelineStore(db_path=str(tmp_path / "timeline.db"))

    def test_without_a_guest_the_row_is_written(self, timeline):
        mapper = FrigateEventMapper(timeline=timeline)
        mapper.handle_event(TOPIC_EVENTS, _detection())
        assert timeline.query(event_type="frigate_event")
        assert mapper._pending_events

    def test_a_private_camera_goes_to_the_guest_not_the_timeline(self, timeline, monkeypatch):
        transport = _Transport()
        monkeypatch.setattr(sibling, "default_transport", transport)
        session = _front()
        private_sources.assign("frigate:patio")
        mapper = FrigateEventMapper(timeline=timeline)
        mapper.handle_event(TOPIC_EVENTS, _detection("patio"))
        assert timeline.query(event_type="frigate_event") == []
        assert mapper._pending_events == []
        posts = [b for m, u, b in transport.calls if m == "POST"]
        assert len(posts) == 1
        assert "patio" in posts[0]["content"]
        assert {"observation", "frigate:patio", session.id} <= set(posts[0]["tags"])

    def test_a_camera_not_handed_over_stays_halberts(self, timeline, monkeypatch):
        transport = _Transport()
        monkeypatch.setattr(sibling, "default_transport", transport)
        _front()
        private_sources.assign("frigate:patio")
        mapper = FrigateEventMapper(timeline=timeline)
        mapper.handle_event(TOPIC_EVENTS, _detection("front_door"))
        assert timeline.query(event_type="frigate_event")
        assert transport.calls == []

    def test_life_safety_on_a_private_camera_still_reaches_halbert(self, timeline, monkeypatch):
        """D1: the house is not private from its own smoke alarm."""
        transport = _Transport()
        monkeypatch.setattr(sibling, "default_transport", transport)
        _front()
        private_sources.assign("frigate:patio")
        mapper = FrigateEventMapper(timeline=timeline)
        mapper.handle_event(TOPIC_EVENTS, _detection("patio", label="smoke"))
        assert timeline.query(event_type="frigate_event")
        assert mapper._pending_events

    def test_a_guest_without_private_sources_changes_nothing(self, timeline):
        _front()
        mapper = FrigateEventMapper(timeline=timeline)
        mapper.handle_event(TOPIC_EVENTS, _detection("patio"))
        assert timeline.query(event_type="frigate_event")
