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
