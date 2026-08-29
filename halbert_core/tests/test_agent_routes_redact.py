# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A11b: POST /api/agent/message/{id}/redact forgets one row —
content and blocks replaced, FTS rewritten, receipt regenerated (spec §5)."""

import sqlite3

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


def _seed(tm, query, answer, blocks=None, diffs=None, terminals=None):
    turn = tm.begin_turn(query, analyze_message(query), "sess-redact")
    tm.end_turn(turn, assistant_text=answer, blocks=blocks or [],
                terminal_block_ids=terminals or [], diff_proposals=diffs or [])
    return turn


def test_redact_replaces_content_blocks_fts_and_receipt(client, tm):
    turn = _seed(
        tm, "set up the samba media share", "added [media] to smb.conf and ran testparm",
        blocks=[{"tool": "run_command", "args": {"command": "testparm"},
                 "result": "Loaded services file OK.", "exit": 0}],
        diffs=[{"diff_id": "d1", "path": "/etc/samba/smb.conf",
                "new_content": "passdb backend = tdbsam:SECRETINDIFF"}],
    )
    tid = turn.thread_id
    assistant_id = tm.store.list_turns(limit=5)[-1]["assistant"]["message_id"]
    assert "testparm" in tm.store.get_thread(tid)["receipt"]
    assert tm.store.search("testparm", None, 5) == [tid]
    assert tm.store.list_turns(limit=5)[-1]["diff_proposals"] != []

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
    # A staged diff carries the file contents being written -- the loudest
    # payload on the row, and the one nothing pinned (A11b review finding 3).
    assert row["diff_proposals"] == []
    assert "SECRETINDIFF" not in tm.store.get_thread(tid)["receipt"]


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


# ---------------------------------------------------------------------------
# Review round 2: the entity sets are a third derived copy of the message,
# an index scrub that is skipped (or silently fails) is permanent, and the
# dropped diff proposals were promised by three documents and pinned by none.
# ---------------------------------------------------------------------------

SECRET_PATH = "/srv/clients/acmecorp-payroll-2026.kdbx"


def test_redaction_drops_the_entities_that_only_that_row_yielded(client, tm):
    """`entities_json` / `topic_window.entities` / `founding_entities` are
    harvested from the message by `intake/signals.py::_scan`, which keeps raw
    file paths. Left standing they put the redacted words back on the
    `Entities:` line of the regenerated receipt and, through `upsert_receipt`,
    into `receipts_fts` -- the copy `recall()` feeds into later prompts
    (A11b review finding 1)."""
    turn = _seed(tm, f"restore the postgres backup from {SECRET_PATH} onto the zfs pool", "done")
    later = _seed(tm, "is the zfs pool still degraded?", "it looks healthy")
    assert later.thread_id == turn.thread_id, "second turn should stay in the same thread"
    tid = turn.thread_id
    before = tm.store.get_thread(tid)
    assert SECRET_PATH in before["entities_json"]
    assert SECRET_PATH in before["receipt"]
    assert [h["thread_id"] for h in tm.store.search_receipts("acmecorp")] == [tid]

    founding_user_id = tm.store.list_turns(limit=5)[0]["user"]["message_id"]
    assert client.post(f"/api/agent/message/{founding_user_id}/redact").status_code == 200

    thread = tm.store.get_thread(tid)
    assert SECRET_PATH not in thread["entities_json"]
    assert "backup" not in thread["entities_json"] and "restore" not in thread["entities_json"]
    # ...but an entity the surviving turn still says stays: these sets
    # describe the thread, not the row.
    assert "zfs" in thread["entities_json"]
    window = thread["metadata"]["topic_window"]["entities"]
    assert SECRET_PATH not in window and "zfs" in window
    assert SECRET_PATH not in thread["metadata"]["founding_entities"]
    assert SECRET_PATH not in thread["receipt"]
    assert tm.store.search_receipts("acmecorp") == []
    assert tm.store.search_receipts("payroll") == []
    assert tm.store.search("acmecorp", None, 5) == []


def test_the_store_and_the_manager_agree_on_the_metadata_key_names():
    """The store spells `topic_window` / `founding_entities` itself (threads.py
    imports it, not the other way round); a rename on either side must fail
    here rather than turn the entity scrub into a silent no-op."""
    from halbert_core.agents import conversation_sqlite as cs
    from halbert_core.agents import threads as threads_module

    assert cs._META_TOPIC_WINDOW == threads_module._TOPIC_WINDOW_KEY
    assert cs._META_FOUNDING_ENTITIES == threads_module._FOUNDING_ENTITIES_KEY


def test_the_index_is_scrubbed_even_when_recovery_itself_fails(client, tm):
    """Gating the scrub on `_fts_recover()` was still a leak: when recovery
    fails the original words stay in `messages_fts` verbatim and *for good*
    -- the backfill only INSERTs rows that are missing, so no later healthy
    process rewrites a stale one, and `search_snippets` reads the FTS copy,
    not `messages.content` (A11b review finding 2)."""
    turn = _seed(tm, "check the samba share", "ran testparm; secretpassphrase99 is in smb.conf")
    tid = turn.thread_id
    assistant_id = tm.store.list_turns(limit=5)[-1]["assistant"]["message_id"]
    assert tm.store.search("secretpassphrase99", None, 5) == [tid]

    tm.store._fts_ok = False
    tm.store._fts_recover = lambda: False          # recovery keeps failing
    try:
        assert client.post(f"/api/agent/message/{assistant_id}/redact").status_code == 200
    finally:
        del tm.store._fts_recover

    tm.store._fts_ok = False
    assert tm.store._fts_recover() is True         # a later, healthy process
    assert tm.store.search("secretpassphrase99", None, 5) == []
    assert tm.store.search_snippets(tid, "secretpassphrase99") == []


class _FtsWritesFail:
    """A connection that can read `sqlite_master` but cannot write the FTS5
    table -- a runtime whose sqlite lacks the module over a database an
    earlier build indexed."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *exc):
        return self._conn.__exit__(*exc)

    def execute(self, sql, *args, **kwargs):
        if "messages_fts" in sql and not sql.lstrip().upper().startswith("SELECT"):
            raise sqlite3.OperationalError("no such module: fts5")
        return self._conn.execute(sql, *args, **kwargs)


def test_an_index_write_that_cannot_land_is_a_500_not_a_clean_ok(client, tm):
    """A redaction whose index scrub cannot land is refused outright: the
    whole thing rolls back and the caller is told so. Reporting `ok` here
    would leave the words searchable behind a green tick, with nothing that
    ever rewrites them (A11b review finding 2)."""
    turn = _seed(tm, "check the samba share", "ran testparm; secretpassphrase99 is in smb.conf")
    tid = turn.thread_id
    assistant_id = tm.store.list_turns(limit=5)[-1]["assistant"]["message_id"]

    real = tm.store._conn
    tm.store._conn = _FtsWritesFail(real)
    try:
        r = client.post(f"/api/agent/message/{assistant_id}/redact")
    finally:
        tm.store._conn = real

    assert r.status_code == 500
    assert tm.store.list_turns(limit=5)[-1]["assistant"]["content"].startswith("ran testparm")
    assert tm.store.search("secretpassphrase99", None, 5) == [tid]


def test_a_database_with_no_fts_index_still_redacts(client, tm):
    """The one benign scrub failure: with no `messages_fts` table nothing is
    indexed, so nothing leaks -- and whenever the table is (re)created it is
    backfilled from `messages`, which by then holds the marker."""
    turn = _seed(tm, "check the samba share", "ran testparm; secretpassphrase99 is in smb.conf")
    assistant_id = tm.store.list_turns(limit=5)[-1]["assistant"]["message_id"]
    with tm.store._conn:
        tm.store._conn.execute("DROP TABLE messages_fts")
    tm.store._fts_ok = False
    tm.store._fts_recover = lambda: False          # this runtime can't rebuild it either
    try:
        assert client.post(f"/api/agent/message/{assistant_id}/redact").status_code == 200
    finally:
        del tm.store._fts_recover

    assert tm.store.list_turns(limit=5)[-1]["assistant"]["content"] == REDACTED
    tm.store._fts_ok = False
    assert tm.store._fts_recover() is True         # rebuilt from the scrubbed rows
    assert tm.store.search("secretpassphrase99", None, 5) == []


def test_redaction_keeps_the_rows_terminal_ids_and_earlier_metadata(client, tm):
    """A redaction is about text. Terminal ids are opaque session handles and
    the timeline still wants to show that a terminal was involved; metadata
    written before the redaction (an A12a-migrated row carries arbitrary JSON
    from disk) is kept as well -- only `redacted` is added."""
    turn = _seed(tm, "tail the samba log", "watching it", terminals=["term-7"])
    assistant_id = tm.store.list_turns(limit=5)[-1]["assistant"]["message_id"]
    tm.store.update_message(assistant_id, metadata={"imported_from": "chat-2024.json", "tokens": 12})

    assert client.post(f"/api/agent/message/{assistant_id}/redact").status_code == 200

    row = next(m for m in tm.store.list_messages(turn.thread_id) if m["message_id"] == assistant_id)
    assert row["content"] == REDACTED
    assert row["terminal_block_ids"] == ["term-7"]
    assert row["metadata"]["imported_from"] == "chat-2024.json"
    assert row["metadata"]["tokens"] == 12
    assert row["metadata"]["redacted"] is True


def test_the_survivor_scan_is_bounded_and_errs_towards_dropping(client, tm, monkeypatch):
    """"Does any surviving row still say this?" is a regex sweep per row on an
    `async` route, so it walks newest-first under a character budget. An
    entity the budget did not reach is dropped, not kept: over-dropping costs
    a recall term the next turn that says it re-adds, over-keeping is the leak
    the scrub exists to close."""
    from halbert_core.agents import conversation_sqlite as cs

    turn = _seed(tm, "the samba share on /srv/media keeps dropping", "looking into it")
    for _ in range(3):
        later = _seed(tm, "and the samba share on /srv/media now?", "still looking")
        assert later.thread_id == turn.thread_id
    assert "samba" in tm.store.get_thread(turn.thread_id)["entities_json"]

    monkeypatch.setattr(cs, "_ENTITY_SURVIVOR_BUDGET", 1)
    founding_user_id = tm.store.list_turns(limit=9)[0]["user"]["message_id"]
    assert client.post(f"/api/agent/message/{founding_user_id}/redact").status_code == 200

    entities = tm.store.get_thread(turn.thread_id)["entities_json"]
    assert "samba" not in entities and "/srv/media" not in entities
