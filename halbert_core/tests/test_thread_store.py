# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the thread-aware SqliteConversationStore (Plan A: A1, A1b, A3)."""

import json
import logging
import sqlite3
import threading
import time

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

    def test_migration_survives_a_held_write_lock_during_journal_mode_pragma(self, tmp_path):
        """A1 review round 2, finding 1: ``PRAGMA journal_mode=WAL`` claims an
        exclusive lock WITHOUT going through the busy handler -- SQLite
        returns SQLITE_BUSY immediately if another connection already holds
        the write lock, busy_timeout or no busy_timeout. The previous fix
        ran that pragma before ``BEGIN IMMEDIATE`` and treated any pragma
        failure as fatal, ``return``-ing before a single CREATE/ALTER TABLE
        ran while leaving ``self._conn`` set -- so the instance was silently
        and permanently unable to write (every ``append_message`` would fail
        with "table messages has no column named turn_id", logged only at
        WARNING and reported as ``None``).

        This deterministically reproduces the held lock (no thread race
        needed): a legacy-shaped DB, a second connection that grabs the
        write lock with ``BEGIN IMMEDIATE`` and holds it past when the store
        constructor's journal_mode pragma will run, then releases it while
        the constructor is blocked waiting on ``BEGIN IMMEDIATE`` under
        ``busy_timeout``. The migration must still complete correctly, and
        ``self._conn`` must not survive as a half-migrated store.
        """
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
        raw.execute("INSERT INTO conversations (id, title, created_at, updated_at) VALUES ('old', 'Old chat', 1.0, 1.0)")
        raw.commit()
        raw.close()

        holder = sqlite3.connect(str(path))
        holder.execute("BEGIN IMMEDIATE")

        result = {}

        def build():
            start = time.time()
            result["store"] = SqliteConversationStore(str(path))
            result["elapsed"] = time.time() - start

        t = threading.Thread(target=build)
        t.start()
        time.sleep(0.5)  # give the constructor time to hit the held lock
        holder.rollback()
        holder.close()
        t.join(timeout=10)

        s = result["store"]
        assert s._conn is not None, "migration must have completed, not aborted with conn left half-migrated"
        # It really did wait on busy_timeout rather than skipping the lock
        # entirely (i.e. this test is actually exercising the held-lock path).
        assert result["elapsed"] >= 0.4
        mcols = {r[1] for r in s._conn.execute("PRAGMA table_info(messages)")}
        assert {"turn_id", "session_id", "origin", "status", "blocks_json",
                "terminal_block_ids", "diff_proposals_json", "visible_in_timeline"} <= mcols
        assert s.healthy is True
        assert s.append_message("old", "user", "post-migration write") is not None
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

    def test_append_with_older_timestamp_does_not_rewind_updated_at(self, store):
        """A1 review round 2, finding 3: ``save()``'s ON CONFLICT clause was
        fixed to ``MAX(conversations.updated_at, excluded.updated_at)``, but
        ``append_message`` still ended with an unconditional
        ``UPDATE conversations SET updated_at = ?``. Appending with an
        explicitly older ``timestamp=`` -- exactly what
        ``migrate_json_conversations_to_sqlite`` does when it backfills a
        thread's messages one at a time after ``save()`` has already set the
        thread's true (newer) ``updated_at`` -- used to drop the thread's
        recency below its current value, corrupting the
        ``ORDER BY updated_at DESC`` in ``list_conversations``/``list_threads``.
        """
        store.create("t1")
        current = store._conn.execute(
            "SELECT updated_at FROM conversations WHERE id = 't1'"
        ).fetchone()[0]
        much_newer = current + 10_000.0
        store._conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = 't1'", (much_newer,)
        )
        store._conn.commit()

        store.append_message("t1", "user", "backfilled with an old timestamp", timestamp=1.0)

        after = store._conn.execute(
            "SELECT updated_at FROM conversations WHERE id = 't1'"
        ).fetchone()[0]
        assert after == much_newer  # not rewound to 1.0

    def test_append_with_newer_timestamp_still_advances_updated_at(self, store):
        store.create("t1")
        far_future = time.time() + 10_000.0
        store.append_message("t1", "user", "advances updated_at forward", timestamp=far_future)
        after = store._conn.execute(
            "SELECT updated_at FROM conversations WHERE id = 't1'"
        ).fetchone()[0]
        assert after == far_future


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

    def test_update_thread_id_to_unknown_thread_is_rejected(self, store, caplog):
        """A1 review round 2, finding 4: the existence check
        ``append_message`` gained for finding 4 in round 1 was never added
        to this sibling write path. With no FK on ``conversation_id``,
        ``update_message(mid, thread_id="ghost")`` used to succeed, moving
        the row (and its FTS entry) to a thread id that does not exist --
        making the message invisible to every reader (``get``, ``search``,
        a future ``list_threads``) forever. ``thread_id`` moves are exactly
        how later Plan A merge/split tasks use this method, so this matters
        more than an isolated data-integrity nicety.
        """
        store.create("t1")
        mid = store.append_message("t1", "user", "moving to nowhere")
        with caplog.at_level(logging.WARNING, logger="halbert.agents.conversation_sqlite"):
            assert store.update_message(mid, thread_id="ghost") is False
        assert any("update_message" in r.message for r in caplog.records)
        row = store._conn.execute(
            "SELECT conversation_id FROM messages WHERE id = ?", (mid,)
        ).fetchone()
        assert row["conversation_id"] == "t1"  # not moved
        assert store._conn.execute(
            "SELECT conversation_id FROM messages_fts WHERE rowid = ?", (mid,)
        ).fetchone()[0] == "t1"  # FTS entry not moved either
        assert store.search("nowhere") == ["t1"]
        # the store is still usable afterwards for a real move
        store.create("t2")
        assert store.update_message(mid, thread_id="t2") is True


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

    def test_recovery_backfills_messages_written_while_genuinely_degraded(self, store, monkeypatch):
        """A1 review round 2, finding 2: both the ``version >= 2`` branch of
        ``_ensure_schema`` and ``_fts_recover()`` created ``messages_fts``
        with ``CREATE VIRTUAL TABLE IF NOT EXISTS`` and immediately reported
        ``healthy``/``_fts_ok = True`` with no backfill -- so a runtime
        without FTS5 could accumulate unindexed messages, and a later
        runtime with FTS5 would create an empty index and report healthy
        forever while those older messages stayed permanently unsearchable.

        This appends one message while FTS is healthy (indexed the normal
        way), then genuinely degrades (stubbing ``_fts_recover`` to keep
        failing, like ``test_degraded_fts_appends_succeed_but_search_falls_back_to_title``
        above) and appends a second message that is written but NOT
        indexed. Recovery must then backfill -- not just the newly appended
        row, but the fact that recovery actually walks ``messages`` rather
        than trusting an already-populated-looking index -- so both
        messages become searchable again.
        """
        store.create("t1")
        indexed_before_degradation = store.append_message("t1", "user", "alpha unique searchable phrase")
        assert store.search("alpha") == ["t1"]

        monkeypatch.setattr(store, "_fts_recover", lambda: False)
        store._fts_ok = False
        written_while_degraded = store.append_message("t1", "user", "beta unique searchable phrase")
        assert written_while_degraded is not None
        assert store.search("beta") == []  # confirms it was genuinely NOT indexed

        monkeypatch.undo()  # restore the real _fts_recover
        assert store.healthy is False  # still latched False until something recovers it

        assert store._fts_recover() is True
        assert store.healthy is True
        assert store.search("alpha") == ["t1"]
        assert store.search("beta") == ["t1"]
        for mid in (indexed_before_degradation, written_while_degraded):
            assert store._conn.execute(
                "SELECT COUNT(*) FROM messages_fts WHERE rowid = ?", (mid,)
            ).fetchone()[0] == 1

    def test_reopen_backfills_messages_missing_from_an_already_versioned_fts_index(self, tmp_path):
        """The mirror of the above for the ``_ensure_schema`` path directly
        (rather than ``_fts_recover()``): a DB already stamped at
        ``SCHEMA_VERSION`` whose ``messages_fts`` table exists but is
        missing rows for messages that were written by a runtime without
        FTS5. Simply reopening the store (which runs
        ``CREATE VIRTUAL TABLE IF NOT EXISTS`` down the ``version >= 2``
        branch, since the table already exists) must backfill those rows,
        not just leave the store reporting healthy over a thin index.
        """
        path = tmp_path / "thin_index.db"
        s = SqliteConversationStore(str(path))
        s.create("t1")
        indexed = s.append_message("t1", "user", "gamma unique searchable phrase")
        # Simulate a message that a runtime without FTS5 would have written:
        # present in messages, absent from messages_fts, schema_version
        # already at SCHEMA_VERSION.
        unindexed = s.append_message("t1", "user", "delta unique searchable phrase")
        s._conn.execute("DELETE FROM messages_fts WHERE rowid = ?", (unindexed,))
        s._conn.commit()
        assert s.search("delta") == []
        s.close()

        s2 = SqliteConversationStore(str(path))
        assert s2.healthy is True
        assert s2.search("gamma") == ["t1"]
        assert s2.search("delta") == ["t1"]
        s2.close()


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


# ---------------------------------------------------------------------------
# Thread + turn readers (A1b)
# ---------------------------------------------------------------------------

class TestThreadReaders:
    def test_create_get_update_thread(self, store):
        assert store.create_thread("t1", "Samba share") is True
        assert store.create_thread("t1", "dup") is False
        t = store.get_thread("t1")
        assert (t["thread_id"], t["id"], t["title"], t["status"], t["title_source"]) == ("t1", "t1", "Samba share", "open", "provisional")
        assert t["topic_domains"] == [] and t["entities_json"] == [] and t["recalled_json"] == [] and t["metadata"] == {}
        assert t["turn_count"] == 0 and t["message_count"] == 0
        assert store.update_thread("t1", status="paused", paused_at=10.0, topic_domains=["network"],
                                   entities_json=["samba"], stale=True, metadata={"k": 1}) is True
        t = store.get_thread("t1")
        assert (t["status"], t["paused_at"], t["topic_domains"], t["entities_json"], t["stale"], t["metadata"]) == ("paused", 10.0, ["network"], ["samba"], 1, {"k": 1})
        assert store.update_thread("t1", paused_at=None) is True and store.get_thread("t1")["paused_at"] is None
        assert store.update_thread("t1", bogus=1) is False
        assert store.update_thread("missing", status="open") is False
        assert store.get_thread("nope") is None

    def test_list_threads_and_current_open(self, store):
        for tid in ("a", "b", "c"):
            store.create_thread(tid, tid.upper())
        store.update_thread("a", status="closed", last_active=100.0)
        store.update_thread("b", status="paused", last_active=200.0)
        store.update_thread("c", status="open", last_active=300.0)
        assert [t["thread_id"] for t in store.list_threads()] == ["c", "b", "a"]
        assert [t["thread_id"] for t in store.list_threads(status="paused")] == ["b"]
        assert [t["thread_id"] for t in store.list_threads(status=["paused", "closed"])] == ["b", "a"]
        assert [t["thread_id"] for t in store.list_threads(limit=1)] == ["c"]
        assert store.current_open_thread()["thread_id"] == "c"
        store.update_thread("c", status="closed")
        assert store.current_open_thread() is None

    def test_recent_messages_filters_origin_and_orders(self, store):
        store.create_thread("t1", "T")
        for i in range(14):
            role = "user" if i % 2 == 0 else "assistant"
            store.append_message("t1", role, f"m{i}", origin="human" if role == "user" else "assistant")
        store.append_message("t1", "system", "from terminal", origin="terminal")
        rows = store.recent_messages("t1", limit=12)
        assert len(rows) == 12 and rows[0]["content"] == "m2" and rows[-1]["content"] == "m13"
        assert all(r["origin"] in ("human", "assistant") for r in rows)
        assert set(rows[0]) == {"role", "content", "timestamp", "origin"}
        assert store.recent_messages("nope") == []

    def test_list_messages_full_rows(self, store):
        store.create_thread("t1", "T")
        mid = store.append_message("t1", "assistant", "done", origin="assistant", turn_id="u1",
                                   blocks=[{"tool": "run_command", "args": {"command": "ls"}, "exit": 0}])
        rows = store.list_messages("t1")
        assert rows[0]["message_id"] == mid and rows[0]["thread_id"] == "t1"
        assert rows[0]["blocks"][0]["tool"] == "run_command" and rows[0]["turn_id"] == "u1"
        assert rows[0]["visible_in_timeline"] is True
        assert store.list_messages("t1", limit=0) == []

    def test_list_turns_groups_and_pages(self, store):
        store.create_thread("t1", "T")
        for i in range(5):
            store.append_message("t1", "user", f"q{i}", turn_id=f"turn-{i}", session_id=f"s{i}", timestamp=float(i * 10))
            store.append_message("t1", "assistant", f"a{i}", origin="assistant", turn_id=f"turn-{i}", session_id=f"s{i}",
                                 timestamp=float(i * 10 + 1),
                                 blocks=[{"tool": "run_command", "args": {"command": f"cmd{i}"}, "exit": 0}],
                                 terminal_block_ids=[f"term-{i}"], diff_proposals=[{"id": f"d{i}"}])
        store.append_message("t1", "system", "hidden", origin="system", turn_id="turn-4", visible_in_timeline=False)
        turns = store.list_turns(limit=50)
        assert [t["turn_id"] for t in turns] == [f"turn-{i}" for i in range(5)]
        last = turns[-1]
        assert last["user"]["content"] == "q4" and last["user"]["status"] == "complete"
        assert last["assistant"]["content"] == "a4"
        assert last["blocks"][0]["args"]["command"] == "cmd4" and last["terminal_block_ids"] == ["term-4"]
        assert last["diff_proposals"] == [{"id": "d4"}]
        assert last["timestamp"] == 40.0 and last["origin"] == "human" and last["thread_id"] == "t1"
        assert [t["turn_id"] for t in store.list_turns(limit=2)] == ["turn-3", "turn-4"]
        assert [t["turn_id"] for t in store.list_turns(before_turn_id="turn-3", limit=2)] == ["turn-1", "turn-2"]
        assert [t["turn_id"] for t in store.list_turns(around_turn_id="turn-2", limit=3)] == ["turn-1", "turn-2", "turn-3"]
        assert store.list_turns(before_turn_id="nope") == []
        assert store.list_turns(before_turn_id="turn-0") == []

    def test_list_turns_around_backfills_from_either_edge(self, store):
        """Round-2 A1b review: ``around_turn_id`` must return exactly
        ``limit`` turns (when that many exist) even when the anchor sits
        near either end of the timeline, by topping up from the side that
        still has turns left."""
        store.create_thread("t1", "T")
        for i in range(20):
            tid = f"turn-{i:02d}"
            store.append_message("t1", "user", f"q{i}", turn_id=tid, timestamp=float(i * 10))
            store.append_message("t1", "assistant", f"a{i}", origin="assistant", turn_id=tid,
                                 timestamp=float(i * 10 + 1))
        # Anchored on the newest turn: nothing sits after it, so the whole
        # shortfall must be backfilled from the older side.
        turns = store.list_turns(around_turn_id="turn-19", limit=11)
        assert [t["turn_id"] for t in turns] == [f"turn-{i:02d}" for i in range(9, 20)]
        # Anchored on the oldest turn: nothing sits before it, so the whole
        # shortfall must be backfilled from the newer side.
        turns = store.list_turns(around_turn_id="turn-00", limit=11)
        assert [t["turn_id"] for t in turns] == [f"turn-{i:02d}" for i in range(0, 11)]
        # Anchored in the middle: both sides have plenty, half/half holds.
        turns = store.list_turns(around_turn_id="turn-10", limit=11)
        assert [t["turn_id"] for t in turns] == [f"turn-{i:02d}" for i in range(5, 16)]

    def test_list_turns_rows_without_turn_id(self, store):
        store.create_thread("t1", "T")
        mid = store.append_message("t1", "user", "legacy row")
        turns = store.list_turns()
        assert turns[0]["turn_id"] == f"m{mid}" and turns[0]["user"]["content"] == "legacy row"

    def test_mark_in_progress_interrupted(self, store):
        store.create_thread("t1", "T")
        store.append_message("t1", "user", "a", status="in_progress")
        store.append_message("t1", "user", "b", status="complete")
        assert store.mark_in_progress_interrupted() == 1
        assert [r["status"] for r in store.list_messages("t1")] == ["interrupted", "complete"]
        assert store.mark_in_progress_interrupted() == 0
