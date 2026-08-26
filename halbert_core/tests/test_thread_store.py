# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the thread-aware SqliteConversationStore (Plan A: A1, A1b, A3)."""

import json
import logging
import sqlite3

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


class TestSearchPunctuation:
    def test_dotted_and_apostrophe_queries_do_not_abort(self, store):
        store.create("t1")
        store.append_message("t1", "user", "the config lives in smb.conf")
        assert store.search("smb.conf") == ["t1"]
        assert store.search("what's") == []
        assert store.search("what's in smb.conf") == ["t1"]
