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
    tm.end_turn(turn, assistant_text=answer, blocks=[], terminal_block_ids=[], diff_proposals=diff_proposals or [])
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


def test_a_decided_diff_is_never_actionable_again(client, tm, tmp_path):
    """A stored proposal stays addressable by id forever, so apply/reject must
    settle it once: `new_content` is a whole-file replacement and a re-apply
    would silently discard every admin edit made since."""
    target = tmp_path / "smb.conf"
    _seed_turn(tm, "add two shares", "two diffs", diff_proposals=[
        {"diff_id": "d1", "file_path": str(target), "new_content": "one\n", "status": "pending"},
        {"diff_id": "d2", "file_path": str(target), "new_content": "two\n", "status": "pending"},
    ])
    assert client.post("/api/agent/diff/dead-session/d1/reject").json() == {"rejected": True, "diff_id": "d1"}
    assert client.post("/api/agent/diff/dead-session/d1/apply").status_code == 400
    assert not target.exists()

    assert client.post("/api/agent/diff/dead-session/d2/apply").status_code == 200
    target.write_text("hand edited by the admin\n")
    assert client.post("/api/agent/diff/dead-session/d2/apply").status_code == 400
    assert client.post("/api/agent/diff/dead-session/d2/reject").status_code == 400
    assert target.read_text() == "hand edited by the admin\n"
    stored = {d["diff_id"]: d["status"] for d in tm.store.list_turns(limit=10)[-1]["diff_proposals"]}
    assert stored == {"d1": "rejected", "d2": "applied"}


def _live_ctx(monkeypatch, session_id, pending_diffs):
    ctx = type("Ctx", (), {})()
    ctx.pending_diffs = pending_diffs
    agent = type("Agent", (), {})()
    agent.active_sessions = {session_id: ctx}
    monkeypatch.setattr(agent_routes, "_agent_instance", agent)
    return ctx


def test_live_session_apply_writes_the_file_and_settles_the_stored_copy(client, tm, tmp_path, monkeypatch):
    target = tmp_path / "live" / "smb.conf"
    proposal = {"diff_id": "L1", "file_path": str(target), "new_content": "[live]\n", "status": "pending"}
    _seed_turn(tm, "add a live share", "diff attached", diff_proposals=[dict(proposal)])
    ctx = _live_ctx(monkeypatch, "live", {"L1": proposal})

    body = client.post("/api/agent/diff/live/L1/apply").json()
    assert body["applied"] is True and body["file_path"] == str(target)
    assert target.read_text() == "[live]\n"
    assert ctx.pending_diffs["L1"]["status"] == "applied"
    # The turn row was persisted when the turn ended, so the store holds the
    # same proposal: it must not still say "pending" once the session is gone.
    stored = {d["diff_id"]: d["status"] for d in tm.store.list_turns(limit=10)[-1]["diff_proposals"]}
    assert stored == {"L1": "applied"}
    target.write_text("hand edited by the admin\n")
    assert client.post("/api/agent/diff/live/L1/apply").status_code == 400
    assert target.read_text() == "hand edited by the admin\n"


def test_live_session_reject_touches_no_file_and_settles_the_stored_copy(client, tm, tmp_path, monkeypatch):
    target = tmp_path / "live" / "hosts"
    proposal = {"diff_id": "L2", "file_path": str(target), "new_content": "nope\n", "status": "pending"}
    _seed_turn(tm, "edit the hosts file", "diff attached", diff_proposals=[dict(proposal)])
    ctx = _live_ctx(monkeypatch, "live", {"L2": proposal})

    assert client.post("/api/agent/diff/live/L2/reject").json() == {"rejected": True, "diff_id": "L2"}
    assert not target.exists()
    assert ctx.pending_diffs["L2"]["status"] == "rejected"
    stored = {d["diff_id"]: d["status"] for d in tm.store.list_turns(limit=10)[-1]["diff_proposals"]}
    assert stored == {"L2": "rejected"}
    assert client.post("/api/agent/diff/live/L2/apply").status_code == 400
    assert not target.exists()


def test_a_diff_decided_from_the_store_settles_the_live_session_too(client, tm, tmp_path, monkeypatch):
    """The mirror in the other direction, and the one that loses data.

    A turn paused on AWAITING_CONFIRMATION keeps its session in
    active_sessions while process() has already persisted the turn, so both
    copies exist and both say "pending" -- and the diff card rendered from
    the timeline has no session id to send (the persisted turn dicts carry
    none), so the two copies get decided through different requests. Settling
    only the one a request routed to leaves the other actionable, and
    `new_content` is a whole-file replacement.
    """
    target = tmp_path / "live" / "smb.conf"
    proposal = {"diff_id": "L1", "file_path": str(target), "new_content": "agent version\n", "status": "pending"}
    _seed_turn(tm, "add a share while paused", "diff attached", diff_proposals=[dict(proposal)])
    ctx = _live_ctx(monkeypatch, "live", {"L1": proposal})

    assert client.post("/api/agent/diff/unknown-session/L1/apply").status_code == 200
    assert target.read_text() == "agent version\n"
    assert ctx.pending_diffs["L1"]["status"] == "applied"

    target.write_text("hand edited by the admin\n")
    # The still-open streaming UI posts with the session id it does know.
    assert client.post("/api/agent/diff/live/L1/apply").status_code == 400
    assert client.post("/api/agent/diff/live/L1/reject").status_code == 400
    assert target.read_text() == "hand edited by the admin\n"


def test_a_reject_from_the_store_settles_the_live_session_too(client, tm, tmp_path, monkeypatch):
    target = tmp_path / "live" / "hosts"
    proposal = {"diff_id": "L2", "file_path": str(target), "new_content": "nope\n", "status": "pending"}
    _seed_turn(tm, "edit hosts while paused", "diff attached", diff_proposals=[dict(proposal)])
    ctx = _live_ctx(monkeypatch, "live", {"L2": proposal})

    assert client.post("/api/agent/diff/unknown-session/L2/reject").json() == {"rejected": True, "diff_id": "L2"}
    assert ctx.pending_diffs["L2"]["status"] == "rejected"
    assert client.post("/api/agent/diff/live/L2/apply").status_code == 400
    assert not target.exists()


def test_apply_settles_the_proposal_before_it_touches_disk(client, tm, tmp_path):
    """Ordering, not politeness: a proposal left "pending" by a write that
    succeeded is replayable over the admin's next edit, while one marked
    applied by a write that failed only costs them a re-ask."""
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory\n")
    _seed_turn(tm, "write below a plain file", "diff attached", diff_proposals=[
        {"diff_id": "d9", "file_path": str(blocker / "smb.conf"), "new_content": "x\n", "status": "pending"},
    ])
    assert client.post("/api/agent/diff/dead-session/d9/apply").status_code == 500
    stored = {d["diff_id"]: d["status"] for d in tm.store.list_turns(limit=10)[-1]["diff_proposals"]}
    assert stored == {"d9": "applied"}
    assert client.post("/api/agent/diff/dead-session/d9/apply").status_code == 400


def test_a_decision_the_store_refused_is_reported_not_hidden(client, tm, tmp_path, monkeypatch):
    """A status the store would not take leaves the proposal replayable after
    a restart, so the response says so instead of showing a clean tick."""
    target = tmp_path / "smb.conf"
    _seed_turn(tm, "two more shares", "two diffs", diff_proposals=[
        {"diff_id": "d1", "file_path": str(target), "new_content": "one\n", "status": "pending"},
        {"diff_id": "d2", "file_path": str(target), "new_content": "two\n", "status": "pending"},
    ])

    def boom(*args, **kwargs):
        raise RuntimeError("store is read-only")

    monkeypatch.setattr(tm.store, "update_message", boom)
    assert client.post("/api/agent/diff/dead-session/d1/apply").json() == {
        "applied": True, "diff_id": "d1", "file_path": str(target), "status_persisted": False,
    }
    assert target.read_text() == "one\n"
    assert client.post("/api/agent/diff/dead-session/d2/reject").json() == {
        "rejected": True, "diff_id": "d2", "status_persisted": False,
    }


def test_timeline_around_keeps_the_anchor_on_the_page(client, tm):
    turns = [_seed_turn(tm, f"message number {i}", f"answer {i}") for i in range(9)]

    def ids(**params):
        return [t["turn_id"] for t in client.get("/api/agent/timeline", params=params).json()["turns"]]

    # Anchor in the middle: a centred window, four turns wide.
    assert ids(limit=4, around=turns[5].turn_id) == [t.turn_id for t in turns[3:7]]
    # Anchor at the oldest end: the window tops up forwards and the anchor
    # itself must survive -- this is the recall chip's "jump to the start".
    assert ids(limit=4, around=turns[0].turn_id) == [t.turn_id for t in turns[0:4]]
    # Anchor at the newest end: tops up backwards, still four wide.
    assert ids(limit=4, around=turns[8].turn_id) == [t.turn_id for t in turns[5:9]]

    # has_more means "a `before=` fetch from turns[0] would find something".
    assert client.get("/api/agent/timeline", params={"limit": 4, "around": turns[0].turn_id}).json()["has_more"] is False
    assert client.get("/api/agent/timeline", params={"limit": 4, "around": turns[5].turn_id}).json()["has_more"] is True
    assert ids(limit=4, around="no-such-turn") == []
    assert client.get("/api/agent/timeline", params={"around": "no-such-turn"}).json()["has_more"] is False


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


def test_the_real_thread_manager_resolves_and_feeds_the_timeline(tmp_path, monkeypatch):
    """The one test that does not monkeypatch `_thread_manager`.

    The helper swallows any exception, ImportError included, so a renamed
    `get_thread_manager` or a broken import path would leave /timeline,
    /thread/current, the recall retraction and the stored-diff fallback
    silently answering empty in production with the suite still green.
    """
    import halbert_core.agents.threads as threads_mod

    monkeypatch.setattr(threads_mod._cs, "_DEFAULT_DB", str(tmp_path / "conv.db"))
    monkeypatch.setattr(threads_mod, "_manager", None)
    monkeypatch.setattr(agent_routes, "_agent_instance", None)
    manager = agent_routes._thread_manager()
    assert isinstance(manager, ThreadManager)
    assert manager is threads_mod.get_thread_manager()
    try:
        turn = _seed_turn(manager, "hello from the real manager", "hi")
        app = FastAPI()
        app.include_router(agent_routes.router)
        real_client = TestClient(app)
        body = real_client.get("/api/agent/timeline").json()
        assert [t["turn_id"] for t in body["turns"]] == [turn.turn_id]
        assert body["current_thread"]["thread_id"] == turn.thread_id
        assert real_client.get("/api/agent/thread/current").json()["thread_id"] == turn.thread_id
    finally:
        manager.store.close()
