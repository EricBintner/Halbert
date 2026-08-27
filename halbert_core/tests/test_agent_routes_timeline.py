# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A11: /api/agent/timeline, /thread/current, recall retraction,
diff apply/reject from the store, /message hands the ThreadManager to the
state machine, and the /agent/conversations endpoints are gone."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.threads import ThreadManager
from halbert_core.intake.signals import analyze_message
import halbert_core.dashboard.routes.agent as agent_routes


@pytest.fixture
def tm(tmp_path):
    store = SqliteConversationStore(str(tmp_path / "threads.db"))
    manager = ThreadManager(store)
    yield manager
    store.close()


@pytest.fixture
def client(monkeypatch, tm):
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: tm)
    monkeypatch.setattr(agent_routes, "_agent_instance", None)
    app = FastAPI()
    app.include_router(agent_routes.router)
    return TestClient(app)


def _seed_turn(tm, query, answer, diff_proposals=None):
    turn = tm.begin_turn(query, analyze_message(query), f"sess-{query[:8]}")
    tm.end_turn(turn, assistant_text=answer, blocks=[], terminal_session_ids=[], diff_proposals=diff_proposals or [])
    return turn


def test_timeline_empty_and_degraded(client, tm, monkeypatch):
    assert client.get("/api/agent/timeline").json() == {"turns": [], "has_more": False, "current_thread": None}

    def boom(**kw):
        raise RuntimeError("db gone")

    monkeypatch.setattr(tm.store, "list_turns", boom)
    r = client.get("/api/agent/timeline")
    assert r.status_code == 200 and r.json()["turns"] == []
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: None)
    assert client.get("/api/agent/timeline").json() == {"turns": [], "has_more": False, "current_thread": None}
    assert client.get("/api/agent/thread/current").json() is None


def test_timeline_turns_with_roles_and_current_thread(client, tm):
    t1 = _seed_turn(tm, "hello there", "hi!")
    t2 = _seed_turn(tm, "what is my hostname?", "It is halbert.")
    body = client.get("/api/agent/timeline").json()
    assert body["has_more"] is False
    assert [t["turn_id"] for t in body["turns"]] == [t1.turn_id, t2.turn_id]
    first = body["turns"][0]
    assert first["thread_id"] == t1.thread_id
    assert first["user"]["content"] == "hello there" and first["user"]["status"] == "complete"
    assert first["assistant"]["content"] == "hi!"
    assert first["blocks"] == [] and first["terminal_block_ids"] == []
    assert body["current_thread"]["thread_id"] == t2.thread_id
    assert body["current_thread"]["status"] == "open" and isinstance(body["current_thread"]["title"], str)


def test_timeline_paging_with_limit_and_before(client, tm):
    turns = [_seed_turn(tm, f"message number {i}", f"answer {i}") for i in range(5)]
    body = client.get("/api/agent/timeline", params={"limit": 2}).json()
    assert [t["turn_id"] for t in body["turns"]] == [turns[3].turn_id, turns[4].turn_id] and body["has_more"] is True
    body = client.get("/api/agent/timeline", params={"limit": 2, "before": turns[3].turn_id}).json()
    assert [t["turn_id"] for t in body["turns"]] == [turns[1].turn_id, turns[2].turn_id] and body["has_more"] is True
    body = client.get("/api/agent/timeline", params={"limit": 2, "before": turns[1].turn_id}).json()
    assert [t["turn_id"] for t in body["turns"]] == [turns[0].turn_id] and body["has_more"] is False


def test_current_thread_and_recall_retraction(client, tm):
    old = _seed_turn(tm, "set up the samba media share", "added [media] to smb.conf")
    tm.store.update_thread(old.thread_id, status="closed")
    new = _seed_turn(tm, "unrelated: check disk space", "df says fine")
    body = client.get("/api/agent/thread/current").json()
    assert body["thread_id"] == new.thread_id and body["status"] == "open"
    assert "title" in body and "receipt" in body

    assert client.delete(f"/api/agent/thread/{new.thread_id}/recall/nope").json() == {"ok": False}
    tm.store.update_thread(new.thread_id, recalled_json=[{
        "thread_id": old.thread_id, "title": "Samba media share", "date": "2026-07-14", "status": "accepted", "at": 1.0,
    }])
    r = client.delete(f"/api/agent/thread/{new.thread_id}/recall/{old.thread_id}")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert tm.store.get_thread(new.thread_id)["recalled_json"][0]["status"] == "retracted"


def test_diff_apply_and_reject_from_store_when_session_is_dead(client, tm, tmp_path):
    target = tmp_path / "out" / "smb.conf"
    _seed_turn(tm, "add a share", "here is the diff", diff_proposals=[
        {"diff_id": "d1", "file_path": str(target), "new_content": "[scanner]\npath=/srv/scanner\n", "status": "pending"},
        {"diff_id": "d2", "file_path": "/nowhere", "new_content": "x", "status": "pending"},
        {"diff_id": "d3", "file_path": None, "edit_blocks": [], "status": "pending"},
    ])
    r = client.post("/api/agent/diff/dead-session/d1/apply")
    assert r.status_code == 200, r.text
    assert r.json()["applied"] is True
    assert target.read_text() == "[scanner]\npath=/srv/scanner\n"
    assert client.post("/api/agent/diff/dead-session/d2/reject").json() == {"rejected": True, "diff_id": "d2"}
    stored = {d["diff_id"]: d["status"] for d in tm.store.list_turns(limit=10)[-1]["diff_proposals"]}
    assert stored == {"d1": "applied", "d2": "rejected", "d3": "pending"}
    assert client.post("/api/agent/diff/dead-session/d3/apply").status_code == 400
    assert client.post("/api/agent/diff/dead-session/none/apply").status_code == 404
    assert client.post("/api/agent/diff/dead-session/none/reject").status_code == 404


def test_message_passes_thread_manager_and_never_force_resets(client, tm, monkeypatch):
    from halbert_core.agents.events import StreamEvent
    seen = {}

    class _FakeAgent:
        def __init__(self):
            self.cancelled = {}
            self.active_sessions = {"s1": object()}
            self.llm = type("L", (), {"max_tokens": 0, "temperature": 0.0})()
            self.current_state = "planning"

        async def process(self, **kwargs):
            seen.update(kwargs)
            yield StreamEvent.session_started("s1", "r1")
            yield StreamEvent.response_complete("s1")

    fake = _FakeAgent()
    monkeypatch.setattr(agent_routes, "get_agent", lambda: fake)
    r = client.post("/api/agent/message", json={"message": "hi", "session_id": "s1"})
    assert r.status_code == 200
    assert "session_started" in r.text and "response_complete" in r.text
    assert seen["thread_manager"] is tm and seen["query"] == "hi" and seen["session_id"] == "s1"
    assert fake.cancelled == {} and fake.current_state == "planning"


def test_conversations_routes_removed_and_thread_routes_present():
    paths = {getattr(r, "path", "") for r in agent_routes.router.routes}
    assert "/api/agent/conversations" not in paths
    assert "/api/agent/conversations/{conversation_id}" not in paths
    assert {"/api/agent/timeline", "/api/agent/thread/current",
            "/api/agent/thread/{thread_id}/recall/{recalled_thread_id}"} <= paths
