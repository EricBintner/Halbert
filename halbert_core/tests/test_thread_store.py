# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the thread-aware SqliteConversationStore (Plan A: A1, A1b, A3)."""

import json
import logging
import sqlite3
import threading

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore, SCHEMA_VERSION


@pytest.fixture
def store():
    s = SqliteConversationStore(":memory:")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Connection + schema
# ---------------------------------------------------------------------------

class TestConnection:
    def test_wal_and_busy_timeout_on_file_db(self, tmp_path):
        s = SqliteConversationStore(str(tmp_path / "t.db"))
        assert s._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert s._conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        s.close()


class TestSchema:
    def test_new_columns_and_version(self, store):
        cols = {r[1] for r in store._conn.execute("PRAGMA table_info(conversations)")}
        assert {"status", "receipt", "receipt_updated_at", "topic_domains", "entities_json",
                "last_active", "stale", "ephemeral", "parent_thread_id", "merged_into",
                "recalled_json", "unread", "paused_at", "turns_since_pause",
                "title_source"} <= cols
        mcols = {r[1] for r in store._conn.execute("PRAGMA table_info(messages)")}
        assert {"turn_id", "session_id", "origin", "status", "blocks_json",
                "terminal_block_ids", "diff_proposals_json", "visible_in_timeline"} <= mcols
        assert store._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == SCHEMA_VERSION
        sql = store._conn.execute("SELECT sql FROM sqlite_master WHERE name = 'messages_fts'").fetchone()[0]
        assert "porter unicode61" in sql
        assert store._conn.execute("SELECT name FROM sqlite_master WHERE name = 'receipts_fts'").fetchone() is not None
        # compact_boundaries ships in Plan A with no writers (spec §8, §14: default off)
        ccols = {r[1] for r in store._conn.execute("PRAGMA table_info(compact_boundaries)")}
        assert {"thread_id", "trigger", "pre_tokens", "post_tokens", "preserved_message_ids",
                "summary_message_id", "created_at"} <= ccols
        assert store._conn.execute("SELECT COUNT(*) FROM compact_boundaries").fetchone()[0] == 0

    def test_legacy_db_migrates_in_place(self, tmp_path):
        path = tmp_path / "legacy.db"
        raw = sqlite3.connect(str(path))
        raw.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, user_id TEXT, title TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, metadata TEXT NOT NULL DEFAULT '{}')")
        raw.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, timestamp REAL NOT NULL, metadata TEXT NOT NULL DEFAULT '{}')")
        raw.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(conversation_id UNINDEXED, content)")
        raw.execute("INSERT INTO conversations (id, title, created_at, updated_at) VALUES ('old', 'Old chat', 1.0, 1.0)")
        raw.execute("INSERT INTO messages (conversation_id, role, content, timestamp) VALUES ('old', 'user', 'edit smb.conf for the media share', 1.0)")
        raw.execute("INSERT INTO messages_fts(conversation_id, content) VALUES ('old', 'edit smb.conf for the media share')")
        raw.commit()
        raw.close()

        s = SqliteConversationStore(str(path))
        row = s._conn.execute("SELECT status, title_source, receipt FROM conversations WHERE id = 'old'").fetchone()
        assert (row["status"], row["title_source"], row["receipt"]) == ("open", "provisional", "")
        assert s._conn.execute("SELECT origin, status FROM messages").fetchone()[:] == ("human", "complete")
        assert s._conn.execute("SELECT rowid FROM messages_fts").fetchall()[0][0] == 1
        assert s._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 2
        assert s._conn.execute("SELECT name FROM sqlite_master WHERE name = 'compact_boundaries'").fetchone() is not None
        assert s.search("smb.conf") == ["old"]
        s.close()
        # Reopening is idempotent
        s2 = SqliteConversationStore(str(path))
        assert s2._conn.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0] == 1
        assert s2._conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 1
        s2.close()


class TestConcurrentMigration:
    """A1 review finding 1: concurrent first-opens of a legacy DB used to
    race bare ``ALTER TABLE`` statements against one another. The loser saw
    a duplicate-column error, which aborted the rest of its own migration
    (never adding the ``messages`` columns) and left it permanently unable
    to write a message (``append_message`` would fail with "table messages
    has no column named turn_id" for the life of that connection)."""

    def test_concurrent_open_of_legacy_db_all_migrate_cleanly(self, tmp_path):
        path = tmp_path / "legacy.db"
        raw = sqlite3.connect(str(path))
        raw.execute(
            "CREATE TABLE conversations (id TEXT PRIMARY KEY, user_id TEXT, title TEXT, "
            "created_at REAL NOT NULL, updated_at REAL NOT NULL, metadata TEXT NOT NULL DEFAULT '{}')"
        )
        raw.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, "
            "role TEXT NOT NULL, content TEXT NOT NULL, timestamp REAL NOT NULL, "
            "metadata TEXT NOT NULL DEFAULT '{}')"
        )
        raw.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(conversation_id UNINDEXED, content)")
        raw.execute("INSERT INTO conversations (id, title, created_at, updated_at) VALUES ('old', 'Old chat', 1.0, 1.0)")
        for i in range(200):
            raw.execute(
                "INSERT INTO messages (conversation_id, role, content, timestamp) VALUES ('old', 'user', ?, ?)",
                (f"legacy message {i}", float(i)),
            )
        raw.commit()
        raw.close()

        n_openers = 6
        barrier = threading.Barrier(n_openers)
        results = []
        results_lock = threading.Lock()

        def opener():
            barrier.wait()
            s = SqliteConversationStore(str(path))
            mcols = {r[1] for r in s._conn.execute("PRAGMA table_info(messages)")}
            has_all_message_cols = {
                "turn_id", "session_id", "origin", "status", "blocks_json",
                "terminal_block_ids", "diff_proposals_json", "visible_in_timeline",
            } <= mcols
            append_ok = s.append_message("old", "user", "race probe") is not None
            with results_lock:
                results.append((has_all_message_cols, s.healthy, append_ok))
            s.close()

        threads = [threading.Thread(target=opener) for _ in range(n_openers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert len(results) == n_openers, "an opener hung or crashed instead of returning"
        for has_all_message_cols, healthy, append_ok in results:
            assert has_all_message_cols, results
            assert healthy, results
            assert append_ok, results


# ---------------------------------------------------------------------------
# append_message / update_message
# ---------------------------------------------------------------------------

class TestAppend:
    def test_append_returns_id_and_indexes_fts(self, store):
        store.create("t1")
        mid = store.append_message("t1", "user", "check the samba share", origin="human",
                                   turn_id="turn-1", session_id="s1", status="in_progress")
        assert isinstance(mid, int)
        row = store._conn.execute("SELECT * FROM messages WHERE id = ?", (mid,)).fetchone()
        assert (row["turn_id"], row["session_id"], row["origin"], row["status"]) == ("turn-1", "s1", "human", "in_progress")
        assert row["blocks_json"] == "[]" and row["visible_in_timeline"] == 1
        assert store._conn.execute("SELECT rowid FROM messages_fts WHERE messages_fts MATCH '\"samba\"'").fetchone()[0] == mid
        assert store._conn.execute("SELECT updated_at FROM conversations WHERE id = 't1'").fetchone()[0] == row["timestamp"]

    def test_block_content_is_flattened_and_kept(self, store):
        store.create("t1")
        content = [{"type": "text", "text": "Running it"},
                   {"type": "tool_use", "id": "x", "name": "run_command", "input": {"command": "testparm"}}]
        mid = store.append_message("t1", "assistant", content, origin="assistant")
        row = store._conn.execute("SELECT content, blocks_json FROM messages WHERE id = ?", (mid,)).fetchone()
        assert row["content"] == "Running it\n[tool_use: run_command({'command': 'testparm'})]"
        assert json.loads(row["blocks_json"]) == content

    def test_failed_append_rolls_back_and_returns_none(self, store, caplog):
        store.create("t1")
        store._conn.execute("DROP TABLE messages_fts")
        store._conn.execute("CREATE TABLE messages_fts (conversation_id TEXT, content TEXT CHECK(length(content) < 5))")
        with caplog.at_level(logging.WARNING, logger="halbert.agents.conversation_sqlite"):
            assert store.append_message("t1", "user", "hello world") is None
        assert store._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
        assert store._conn.in_transaction is False
        assert any("append_message failed" in r.message for r in caplog.records)
        # the store is still usable afterwards
        assert store.append_message("t1", "user", "hey") is not None

    def test_append_to_unknown_thread_returns_none(self, store, caplog):
        """A1 review finding 4: there is no FK on conversation_id, so without
        an explicit existence check a typo'd/deleted/merged thread id used to
        insert a message row that no ``get``/``search`` call could ever
        surface again (search JOINs conversations, so the row is invisible;
        the trailing ``UPDATE conversations SET updated_at`` also no-ops)."""
        assert store.get("no-such-thread") is None
        with caplog.at_level(logging.WARNING, logger="halbert.agents.conversation_sqlite"):
            assert store.append_message("no-such-thread", "user", "orphan") is None
        assert store._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
        assert any("append_message failed" in r.message for r in caplog.records)
        # the store is still usable afterwards, for a thread that does exist
        store.create("t1")
        assert store.append_message("t1", "user", "hi") is not None


class TestUpdateMessage:
    def test_update_status_and_lists(self, store):
        store.create("t1")
        mid = store.append_message("t1", "assistant", "x", origin="assistant", status="in_progress")
        assert store.update_message(mid, status="complete",
                                    blocks=[{"tool": "run_command", "args": {"command": "ls"}, "exit": 0}],
                                    terminal_block_ids=["term-1"], diff_proposals=[{"id": "d1"}]) is True
        row = store._conn.execute("SELECT * FROM messages WHERE id = ?", (mid,)).fetchone()
        assert row["status"] == "complete"
        assert json.loads(row["blocks_json"])[0]["tool"] == "run_command"
        assert json.loads(row["terminal_block_ids"]) == ["term-1"]
        assert json.loads(row["diff_proposals_json"]) == [{"id": "d1"}]

    def test_update_content_reindexes_fts(self, store):
        store.create("t1")
        mid = store.append_message("t1", "user", "old words")
        assert store.update_message(mid, content="new samba words") is True
        assert store._conn.execute("SELECT rowid FROM messages_fts WHERE messages_fts MATCH '\"samba\"'").fetchone()[0] == mid
        assert store._conn.execute("SELECT rowid FROM messages_fts WHERE messages_fts MATCH '\"old\"'").fetchone() is None

    def test_update_thread_id_moves_row(self, store):
        store.create("t1"); store.create("t2")
        mid = store.append_message("t1", "user", "moving")
        assert store.update_message(mid, thread_id="t2") is True
        assert store._conn.execute("SELECT conversation_id FROM messages WHERE id = ?", (mid,)).fetchone()[0] == "t2"
        assert store._conn.execute("SELECT conversation_id FROM messages_fts WHERE rowid = ?", (mid,)).fetchone()[0] == "t2"

    def test_unknown_field_and_missing_row(self, store):
        store.create("t1")
        mid = store.append_message("t1", "user", "x")
        assert store.update_message(mid, role="assistant") is False
        assert store.update_message(999, status="complete") is False


class TestSave:
    def test_save_does_not_touch_messages(self, store):
        conv = store.create("t1")
        store.append_message("t1", "user", "kept")
        conv.messages = []
        conv.title = "renamed"
        assert store.save(conv) is True
        got = store.get("t1")
        assert got.title == "renamed"
        assert [m.content for m in got.messages] == ["kept"]

    def test_save_preserves_thread_columns(self, store):
        conv = store.create("t1")
        store._conn.execute("UPDATE conversations SET status = 'paused', receipt = 'r' WHERE id = 't1'")
        store._conn.commit()
        store.save(conv)
        row = store._conn.execute("SELECT status, receipt FROM conversations WHERE id = 't1'").fetchone()
        assert (row["status"], row["receipt"]) == ("paused", "r")

    def test_save_does_not_rewind_updated_at_behind_append(self, store):
        """A1 review finding 2: ``save`` used to write ``excluded.updated_at``
        unconditionally, so re-saving a ``Conversation`` object whose
        in-memory ``updated_at`` predates a later ``append_message`` call
        rewound the row backwards -- silently corrupting recency ordering
        for ``list_conversations``/``list_threads``."""
        conv = store.create("t1")
        stale_updated_at = conv.updated_at
        store.append_message("t1", "user", "bumps updated_at forward")
        bumped = store._conn.execute(
            "SELECT updated_at FROM conversations WHERE id = 't1'"
        ).fetchone()[0]
        assert bumped > stale_updated_at
        assert conv.updated_at == stale_updated_at  # caller's copy is now stale
        conv.title = "renamed"
        assert store.save(conv) is True
        row = store._conn.execute(
            "SELECT title, updated_at FROM conversations WHERE id = 't1'"
        ).fetchone()
        assert row["title"] == "renamed"
        assert row["updated_at"] == bumped  # not rewound to the stale value

    def test_save_can_still_advance_updated_at_forward(self, store):
        """MAX(...) must not pin updated_at to whatever append_message set --
        an explicit newer save (e.g. a route bumping "last touched") still
        moves it forward."""
        conv = store.create("t1")
        newer = conv.updated_at + 1000.0
        conv.updated_at = newer
        store.save(conv)
        row = store._conn.execute("SELECT updated_at FROM conversations WHERE id = 't1'").fetchone()
        assert row["updated_at"] == newer


class TestFtsHealth:
    """A1 review finding 3: ``_fts_ok`` used to be a permanent, silent,
    per-instance kill switch with no way for a caller to observe or recover
    from it -- ``append_message`` kept writing message rows but never
    indexed them again for the rest of the process's life."""

    def test_healthy_property_reflects_fts_state(self, store):
        assert store.healthy is True
        store._fts_ok = False
        assert store.healthy is False

    def test_degraded_fts_appends_succeed_but_search_falls_back_to_title(self, store, monkeypatch):
        store.create("t1")
        # Simulate FTS5 genuinely unavailable: recovery attempts keep failing.
        monkeypatch.setattr(store, "_fts_recover", lambda: False)
        store._fts_ok = False
        assert store.healthy is False

        mid = store.append_message("t1", "user", "zzzqux unique unindexed phrase")
        assert mid is not None  # the message itself is still written
        assert store.search("zzzqux") == []  # ...but not indexed while degraded

        store._conn.execute("UPDATE conversations SET title = 'zzzqux thread' WHERE id = 't1'")
        store._conn.commit()
        assert store.search("zzzqux") == ["t1"]  # title LIKE still finds it

    def test_fts_recovers_instead_of_latching_false_forever(self, store):
        store.create("t1")
        # Simulate a stale degraded flag left over from a past transient
        # failure; the underlying FTS5 tables are actually still fine.
        store._fts_ok = False
        mid = store.append_message("t1", "user", "recovered indexing works")
        assert mid is not None
        assert store.healthy is True
        assert store._conn.execute(
            "SELECT rowid FROM messages_fts WHERE messages_fts MATCH '\"recovered\"'"
        ).fetchone()[0] == mid
        assert store.search("recovered") == ["t1"]


class TestDeleteCleansFts:
    def test_delete_removes_fts_rows(self, store):
        """A1 review finding 5: nothing locked in delete()'s FTS cleanup, so
        a future change to that method could leave a deleted thread's
        content silently searchable."""
        store.create("t1")
        store.append_message("t1", "user", "a very particular searchable phrase")
        assert store.search("particular") == ["t1"]
        assert store._conn.execute(
            "SELECT COUNT(*) FROM messages_fts WHERE conversation_id = 't1'"
        ).fetchone()[0] == 1

        assert store.delete("t1") is True

        assert store.search("particular") == []
        assert store._conn.execute(
            "SELECT COUNT(*) FROM messages_fts WHERE conversation_id = 't1'"
        ).fetchone()[0] == 0


class TestMarkInProgressInterrupted:
    def test_marks_only_in_progress_rows(self, store):
        """A1 review finding 5: mark_in_progress_interrupted shipped with
        zero coverage in A1."""
        store.create("t1")
        in_progress_id = store.append_message("t1", "assistant", "still working", status="in_progress")
        complete_id = store.append_message("t1", "assistant", "already done", status="complete")

        assert store.mark_in_progress_interrupted() == 1

        row1 = store._conn.execute("SELECT status FROM messages WHERE id = ?", (in_progress_id,)).fetchone()
        row2 = store._conn.execute("SELECT status FROM messages WHERE id = ?", (complete_id,)).fetchone()
        assert row1["status"] == "interrupted"
        assert row2["status"] == "complete"
        # idempotent: nothing left in_progress to sweep on a second call
        assert store.mark_in_progress_interrupted() == 0


class TestSearchPunctuation:
    def test_dotted_and_apostrophe_queries_do_not_abort(self, store):
        store.create("t1")
        store.append_message("t1", "user", "the config lives in smb.conf")
        assert store.search("smb.conf") == ["t1"]
        assert store.search("what's") == []
        assert store.search("what's in smb.conf") == ["t1"]
