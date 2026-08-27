# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A11b: POST /api/agent/message/{id}/redact forgets one row —
content and blocks replaced, FTS rewritten, receipt regenerated (spec §5)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.threads import ThreadManager
from halbert_core.intake.signals import analyze_message
import halbert_core.dashboard.routes.agent as agent_routes

REDACTED = "[redacted by admin]"


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


def _seed(tm, query, answer, blocks=None):
    turn = tm.begin_turn(query, analyze_message(query), "sess-redact")
    tm.end_turn(turn, assistant_text=answer, blocks=blocks or [], terminal_session_ids=[], diff_proposals=[])
    return turn


def test_redact_replaces_content_blocks_fts_and_receipt(client, tm):
    turn = _seed(
        tm, "set up the samba media share", "added [media] to smb.conf and ran testparm",
        blocks=[{"tool": "run_command", "args": {"command": "testparm"},
                 "result": "Loaded services file OK.", "exit": 0}],
    )
    tid = turn.thread_id
    assistant_id = tm.store.list_turns(limit=5)[-1]["assistant"]["message_id"]
    assert "testparm" in tm.store.get_thread(tid)["receipt"]
    assert tm.store.search("testparm", None, 5) == [tid]

    r = client.post(f"/api/agent/message/{assistant_id}/redact")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "thread_id": tid}

    row = tm.store.list_turns(limit=5)[-1]
    assert row["assistant"]["content"] == REDACTED
    assert row["blocks"] == [{"tool": REDACTED, "args": {}, "result": REDACTED, "exit": None, "redacted": True}]
    assert row["user"]["content"] == "set up the samba media share"      # only the one row
    assert tm.store.search("testparm", None, 5) == []                     # FTS row rewritten
    receipt = tm.store.get_thread(tid)["receipt"]
    assert "testparm" not in receipt and REDACTED in receipt              # receipt regenerated
    assert tm.store.search("samba", None, 5) == [tid]                     # the user row is untouched
    assert tm.store.list_messages(tid)[-1]["metadata"]["redacted"] is True


def test_redact_a_row_without_blocks_keeps_blocks_empty(client, tm):
    turn = _seed(tm, "hello there", "hi!")
    user_id = tm.store.list_turns(limit=5)[-1]["user"]["message_id"]
    assert client.post(f"/api/agent/message/{user_id}/redact").json() == {"ok": True, "thread_id": turn.thread_id}
    row = tm.store.list_turns(limit=5)[-1]
    assert row["user"]["content"] == REDACTED and row["assistant"]["content"] == "hi!"
    assert row["blocks"] == []
    # idempotent: redacting twice is still ok
    assert client.post(f"/api/agent/message/{user_id}/redact").status_code == 200


def test_redact_unknown_row_is_404_and_no_store_is_503(client, tm, monkeypatch):
    assert client.post("/api/agent/message/999999/redact").status_code == 404
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: None)
    assert client.post("/api/agent/message/1/redact").status_code == 503


def test_store_redact_message_returns_none_for_missing_row_or_no_connection(tm, tmp_path):
    assert tm.store.redact_message(424242) is None
    dead = SqliteConversationStore(str(tmp_path / "x" / "y" / "z" / "not-creatable.db"))
    dead._conn = None
    assert dead.redact_message(1) is None


# ---------------------------------------------------------------------------
# Review round 1: the title is a derived copy of the founding user row, the
# route must not report a failed write as "no such row", and a receipt that
# could not be regenerated must not be left quoting the redacted words.
# ---------------------------------------------------------------------------

SECRET = "rotate the postgres backup password hunter2secret on zfs pool tank"


def test_redacting_the_founding_row_takes_the_title_and_receipt_index_with_it(client, tm):
    """The provisional title is "first user message truncated" (spec §5), so a
    secret pasted into the first message lives on in `conversations.title`,
    in `search`'s title LIKE pass and — once the receipt refresh re-indexes
    it — in `receipts_fts`, which recall injects into later prompts."""
    turn = _seed(tm, SECRET, "done")
    tid = turn.thread_id
    user_id = tm.store.list_turns(limit=5)[-1]["user"]["message_id"]
    assert "hunter2secret" in tm.store.get_thread(tid)["title"]
    assert tm.store.search("hunter2secret", None, 5) == [tid]
    assert [h["thread_id"] for h in tm.store.search_receipts("hunter2secret")] == [tid]

    assert client.post(f"/api/agent/message/{user_id}/redact").status_code == 200

    thread = tm.store.get_thread(tid)
    assert thread["title"] == REDACTED and thread["title_source"] == "redacted"
    assert "hunter2secret" not in thread["receipt"]
    assert thread["receipt"].splitlines()[0] == f"Title: {REDACTED}"
    assert tm.store.search("hunter2secret", None, 5) == []
    assert tm.store.search_receipts("hunter2secret") == []


def test_redacting_a_later_row_leaves_the_title_alone(client, tm):
    turn = _seed(tm, "set up the samba media share", "added [media] to smb.conf")
    second = _seed(tm, "also share the samba scanner folder", "shared it")
    assert second.thread_id == turn.thread_id, "second turn should stay in the same thread"
    title = tm.store.get_thread(turn.thread_id)["title"]
    later_user_id = tm.store.list_turns(limit=5)[-1]["user"]["message_id"]

    assert client.post(f"/api/agent/message/{later_user_id}/redact").status_code == 200

    thread = tm.store.get_thread(turn.thread_id)
    assert thread["title"] == title and thread["title_source"] != "redacted"
    assert tm.store.search("scanner", None, 5) == []


def test_fts_row_is_rewritten_even_when_the_degraded_flag_is_stale(client, tm):
    """`_fts_recover()`, not `self._fts_ok`: a stale degraded flag over a
    populated `messages_fts` would otherwise leave the original words
    searchable for good (recovery only backfills *missing* rows)."""
    _seed(tm, "check the samba share", "ran testparm, all good")
    assistant_id = tm.store.list_turns(limit=5)[-1]["assistant"]["message_id"]
    tm.store._fts_ok = False

    assert client.post(f"/api/agent/message/{assistant_id}/redact").status_code == 200

    assert tm.store._fts_ok is True
    assert tm.store.search("testparm", None, 5) == []


def test_a_failed_write_is_500_and_the_row_is_untouched(client, tm, monkeypatch):
    """A rolled-back redaction must not come back as 404 "message not found":
    that tells the person nothing needed forgetting while the words are still
    on disk."""
    import sqlite3

    _seed(tm, "wipe the samba share", "done")
    user_id = tm.store.list_turns(limit=5)[-1]["user"]["message_id"]

    def boom(*_a, **_kw):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(tm.store, "_is_founding_user_row", boom)
    r = client.post(f"/api/agent/message/{user_id}/redact")
    assert r.status_code == 500
    assert tm.store.list_turns(limit=5)[-1]["user"]["content"] == "wipe the samba share"
    assert tm.store.search("wipe", None, 5) != []   # rolled back, FTS row included


def test_store_raises_rather_than_returning_none_when_the_write_fails(tm, monkeypatch):
    import sqlite3

    from halbert_core.agents.conversation_sqlite import RedactionFailed

    _seed(tm, "hello samba", "hi")
    user_id = tm.store.list_turns(limit=5)[-1]["user"]["message_id"]
    monkeypatch.setattr(tm.store, "_is_founding_user_row", lambda *a, **k: 1 / 0)
    with pytest.raises(RedactionFailed):
        tm.store.redact_message(user_id)


def test_a_receipt_that_cannot_be_regenerated_is_blanked_not_left_standing(client, tm, monkeypatch):
    turn = _seed(tm, SECRET, "done")
    tid = turn.thread_id
    user_id = tm.store.list_turns(limit=5)[-1]["user"]["message_id"]

    def boom(_thread_id):
        raise RuntimeError("receipt build exploded")

    monkeypatch.setattr(tm, "_refresh_receipt", boom)
    r = client.post(f"/api/agent/message/{user_id}/redact")

    assert r.status_code == 200
    assert r.json() == {"ok": True, "thread_id": tid, "receipt_refreshed": False}
    assert tm.store.get_thread(tid)["receipt"] == ""
    assert tm.store.search_receipts("hunter2secret") == []


def test_a_receipt_that_cannot_even_be_blanked_is_a_500(client, tm, monkeypatch):
    _seed(tm, SECRET, "done")
    user_id = tm.store.list_turns(limit=5)[-1]["user"]["message_id"]
    monkeypatch.setattr(tm, "_refresh_receipt", lambda _t: (_ for _ in ()).throw(RuntimeError("no")))
    monkeypatch.setattr(tm.store, "upsert_receipt", lambda *a, **k: False)

    assert client.post(f"/api/agent/message/{user_id}/redact").status_code == 500


class _StoreOnlyManager:
    """A manager with no receipt hook at all — the route's `build_receipt` +
    `upsert_receipt` fallback branch."""

    def __init__(self, store):
        self.store = store


def test_redact_falls_back_to_build_receipt_when_the_manager_has_no_hook(monkeypatch, tm):
    turn = _seed(tm, SECRET, "done")
    tid = turn.thread_id
    user_id = tm.store.list_turns(limit=5)[-1]["user"]["message_id"]
    bare = _StoreOnlyManager(tm.store)
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: bare)
    app = FastAPI()
    app.include_router(agent_routes.router)
    bare_client = TestClient(app)

    assert bare_client.post(f"/api/agent/message/{user_id}/redact").json() == {
        "ok": True, "thread_id": tid,
    }

    receipt = tm.store.get_thread(tid)["receipt"]
    assert receipt.splitlines()[0] == f"Title: {REDACTED}"
    assert "hunter2secret" not in receipt
    assert tm.store.search_receipts("hunter2secret") == []
    # an unknown thread is a no-op, not a crash
    assert agent_routes._refresh_thread_receipt(bare, "no-such-thread") is None


def test_a_store_with_no_connection_is_503_not_404(client, tm, monkeypatch):
    monkeypatch.setattr(tm.store, "_conn", None)
    assert client.post("/api/agent/message/1/redact").status_code == 503
