# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for terminal_blocks and terminal_sessions tables (Plan B: B1)."""

import time

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore, SCHEMA_VERSION


@pytest.fixture
def store():
    s = SqliteConversationStore(":memory:")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------

class TestSchemaMigration:
    def test_schema_version_is_4(self):
        assert SCHEMA_VERSION == 4

    def test_terminal_blocks_table_exists(self, store):
        tables = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='terminal_blocks'"
        ).fetchall()
        assert len(tables) == 1

    def test_terminal_sessions_table_exists(self, store):
        tables = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='terminal_sessions'"
        ).fetchall()
        assert len(tables) == 1

    def test_terminal_blocks_columns(self, store):
        cols = {
            r["name"]
            for r in store._conn.execute("PRAGMA table_info(terminal_blocks)").fetchall()
        }
        expected = {
            "block_id", "session_id", "thread_id", "turn_id", "command",
            "cwd", "owner", "interactive", "remote", "redacted",
            "started_at", "ended_at", "exit_code", "output_head", "output_tail",
        }
        assert expected <= cols

    def test_terminal_sessions_columns(self, store):
        cols = {
            r["name"]
            for r in store._conn.execute("PRAGMA table_info(terminal_sessions)").fetchall()
        }
        expected = {
            "session_id", "kind", "owner", "watched",
            "spawned_at", "ended_at", "last_state",
        }
        assert expected <= cols

    def test_terminal_blocks_indexes(self, store):
        idxs = {
            r["name"]
            for r in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_tb_%'"
            ).fetchall()
        }
        assert {"idx_tb_session", "idx_tb_thread", "idx_tb_turn"} <= idxs

    def test_idempotent_migration(self, store):
        # Calling _ensure_schema again should be a no-op (tables already exist)
        store._ensure_schema()
        assert store._conn is not None
        # Still can query the tables
        assert store.list_terminal_blocks() == []

    def test_v2_db_migrates_to_v3(self, tmp_path):
        """A database at schema v2 should migrate to v3 with both new tables."""
        db = str(tmp_path / "v2.db")
        # Create a v2 database manually
        import sqlite3
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_version VALUES (2)")
        conn.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, created_at REAL, updated_at REAL)")
        conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT, role TEXT, content TEXT, timestamp REAL)")
        conn.commit()
        conn.close()
        # Open with the store — should migrate
        s = SqliteConversationStore(db)
        assert s._conn is not None
        version = s._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        assert version == 4
        # New tables exist
        assert s.list_terminal_blocks() == []
        assert s.list_terminal_sessions() == []
        assert s.list_open_loops("any-thread") == []
        s.close()


# ---------------------------------------------------------------------------
# terminal_blocks CRUD
# ---------------------------------------------------------------------------

class TestTerminalBlocksCRUD:
    def test_insert_and_get_block(self, store):
        now = time.time()
        block = {
            "block_id": "blk-1",
            "session_id": "sess-1",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "command": "ls -la",
            "cwd": "/tmp",
            "owner": "agent",
            "interactive": 0,
            "remote": 0,
            "redacted": 0,
            "started_at": now,
            "ended_at": now + 0.5,
            "exit_code": 0,
            "output_head": "total 0",
            "output_tail": "total 0",
        }
        assert store.insert_terminal_block(block) is True
        got = store.get_terminal_block("blk-1")
        assert got is not None
        assert got["block_id"] == "blk-1"
        assert got["command"] == "ls -la"
        assert got["exit_code"] == 0
        assert got["owner"] == "agent"

    def test_get_nonexistent_block(self, store):
        assert store.get_terminal_block("nope") is None

    def test_update_block(self, store):
        now = time.time()
        store.insert_terminal_block({
            "block_id": "blk-2", "session_id": "s", "thread_id": "t",
            "turn_id": "tn", "command": "echo hi", "cwd": None,
            "owner": "agent", "interactive": 0, "remote": 0, "redacted": 0,
            "started_at": now, "ended_at": None, "exit_code": None,
            "output_head": "", "output_tail": "",
        })
        assert store.update_terminal_block("blk-2", ended_at=now + 1, exit_code=0, output_head="hi") is True
        got = store.get_terminal_block("blk-2")
        assert got["exit_code"] == 0
        assert got["output_head"] == "hi"
        assert got["ended_at"] == now + 1

    def test_update_nonexistent_block(self, store):
        assert store.update_terminal_block("nope", exit_code=1) is False

    def test_insert_or_replace_block(self, store):
        now = time.time()
        block = {
            "block_id": "blk-3", "session_id": "s", "thread_id": "t",
            "turn_id": "tn", "command": "pwd", "cwd": "/",
            "owner": "user", "interactive": 0, "remote": 0, "redacted": 0,
            "started_at": now, "ended_at": now, "exit_code": 0,
            "output_head": "/", "output_tail": "/",
        }
        store.insert_terminal_block(block)
        block["exit_code"] = 1
        block["output_head"] = "/tmp"
        store.insert_terminal_block(block)  # INSERT OR REPLACE
        got = store.get_terminal_block("blk-3")
        assert got["exit_code"] == 1
        assert got["output_head"] == "/tmp"

    def test_list_blocks_by_session(self, store):
        now = time.time()
        for i in range(3):
            store.insert_terminal_block({
                "block_id": f"blk-s-{i}", "session_id": "sess-a", "thread_id": "t",
                "turn_id": "tn", "command": f"cmd{i}", "cwd": None,
                "owner": "agent", "interactive": 0, "remote": 0, "redacted": 0,
                "started_at": now + i, "ended_at": now + i, "exit_code": 0,
                "output_head": "", "output_tail": "",
            })
        store.insert_terminal_block({
            "block_id": "blk-other", "session_id": "sess-b", "thread_id": "t",
            "turn_id": "tn", "command": "other", "cwd": None,
            "owner": "agent", "interactive": 0, "remote": 0, "redacted": 0,
            "started_at": now, "ended_at": now, "exit_code": 0,
            "output_head": "", "output_tail": "",
        })
        blocks = store.list_terminal_blocks(session_id="sess-a")
        assert len(blocks) == 3
        # newest-first
        assert blocks[0]["block_id"] == "blk-s-2"

    def test_list_blocks_by_thread(self, store):
        now = time.time()
        for tid in ["thread-x", "thread-y"]:
            store.insert_terminal_block({
                "block_id": f"blk-{tid}", "session_id": "s", "thread_id": tid,
                "turn_id": "tn", "command": "cmd", "cwd": None,
                "owner": "agent", "interactive": 0, "remote": 0, "redacted": 0,
                "started_at": now, "ended_at": now, "exit_code": 0,
                "output_head": "", "output_tail": "",
            })
        blocks = store.list_terminal_blocks(thread_id="thread-x")
        assert len(blocks) == 1
        assert blocks[0]["thread_id"] == "thread-x"

    def test_list_blocks_by_turn(self, store):
        now = time.time()
        store.insert_terminal_block({
            "block_id": "blk-t1", "session_id": "s", "thread_id": "t",
            "turn_id": "turn-aaa", "command": "cmd", "cwd": None,
            "owner": "agent", "interactive": 0, "remote": 0, "redacted": 0,
            "started_at": now, "ended_at": now, "exit_code": 0,
            "output_head": "", "output_tail": "",
        })
        blocks = store.list_terminal_blocks(turn_id="turn-aaa")
        assert len(blocks) == 1

    def test_list_blocks_limit(self, store):
        now = time.time()
        for i in range(10):
            store.insert_terminal_block({
                "block_id": f"blk-l-{i}", "session_id": "s", "thread_id": "t",
                "turn_id": "tn", "command": f"cmd{i}", "cwd": None,
                "owner": "agent", "interactive": 0, "remote": 0, "redacted": 0,
                "started_at": now + i, "ended_at": now + i, "exit_code": 0,
                "output_head": "", "output_tail": "",
            })
        blocks = store.list_terminal_blocks(limit=5)
        assert len(blocks) == 5
        # newest-first
        assert blocks[0]["block_id"] == "blk-l-9"

    def test_list_blocks_no_filter(self, store):
        now = time.time()
        for i in range(3):
            store.insert_terminal_block({
                "block_id": f"blk-n-{i}", "session_id": f"s{i}", "thread_id": f"t{i}",
                "turn_id": "tn", "command": "cmd", "cwd": None,
                "owner": "agent", "interactive": 0, "remote": 0, "redacted": 0,
                "started_at": now + i, "ended_at": now + i, "exit_code": 0,
                "output_head": "", "output_tail": "",
            })
        blocks = store.list_terminal_blocks()
        assert len(blocks) == 3

    def test_redacted_flag(self, store):
        now = time.time()
        store.insert_terminal_block({
            "block_id": "blk-red", "session_id": "s", "thread_id": "t",
            "turn_id": "tn", "command": "cmd", "cwd": None,
            "owner": "user", "interactive": 0, "remote": 0, "redacted": 1,
            "started_at": now, "ended_at": now, "exit_code": 0,
            "output_head": "password=[redacted]", "output_tail": "",
        })
        got = store.get_terminal_block("blk-red")
        assert got["redacted"] == 1


# ---------------------------------------------------------------------------
# terminal_sessions CRUD
# ---------------------------------------------------------------------------

class TestTerminalSessionsCRUD:
    def test_insert_and_get_session(self, store):
        now = time.time()
        store.insert_terminal_session({
            "session_id": "sess-1",
            "kind": "user",
            "owner": "user",
            "watched": 1,
            "spawned_at": now,
            "ended_at": None,
            "last_state": "running",
        })
        got = store.get_terminal_session("sess-1")
        assert got is not None
        assert got["kind"] == "user"
        assert got["watched"] == 1
        assert got["last_state"] == "running"

    def test_get_nonexistent_session(self, store):
        assert store.get_terminal_session("nope") is None

    def test_update_session(self, store):
        now = time.time()
        store.insert_terminal_session({
            "session_id": "sess-2", "kind": "agent-pool", "owner": "agent",
            "watched": 1, "spawned_at": now, "ended_at": None, "last_state": "running",
        })
        assert store.update_terminal_session("sess-2", watched=0, last_state="exited", ended_at=now + 10) is True
        got = store.get_terminal_session("sess-2")
        assert got["watched"] == 0
        assert got["last_state"] == "exited"
        assert got["ended_at"] == now + 10

    def test_update_nonexistent_session(self, store):
        assert store.update_terminal_session("nope", watched=0) is False

    def test_list_sessions_by_kind(self, store):
        now = time.time()
        for kid, kind in enumerate(["user", "agent-pool", "oneshot"]):
            store.insert_terminal_session({
                "session_id": f"sess-k-{kid}", "kind": kind, "owner": "agent",
                "watched": 1, "spawned_at": now, "ended_at": None, "last_state": "running",
            })
        user_sessions = store.list_terminal_sessions(kind="user")
        assert len(user_sessions) == 1
        assert user_sessions[0]["kind"] == "user"

    def test_list_sessions_no_filter(self, store):
        now = time.time()
        for i in range(3):
            store.insert_terminal_session({
                "session_id": f"sess-l-{i}", "kind": "oneshot", "owner": "agent",
                "watched": 1, "spawned_at": now + i, "ended_at": None, "last_state": "running",
            })
        sessions = store.list_terminal_sessions()
        assert len(sessions) == 3

    def test_list_sessions_limit(self, store):
        now = time.time()
        for i in range(10):
            store.insert_terminal_session({
                "session_id": f"sess-lm-{i}", "kind": "oneshot", "owner": "agent",
                "watched": 1, "spawned_at": now + i, "ended_at": None, "last_state": "running",
            })
        sessions = store.list_terminal_sessions(limit=5)
        assert len(sessions) == 5


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

class TestFailureHandling:
    def test_methods_return_empty_on_no_connection(self):
        s = SqliteConversationStore(":memory:")
        s._conn = None  # simulate a dead connection
        assert s.insert_terminal_block({}) is False
        assert s.update_terminal_block("x", exit_code=0) is False
        assert s.get_terminal_block("x") is None
        assert s.list_terminal_blocks() == []
        assert s.insert_terminal_session({}) is False
        assert s.update_terminal_session("x", watched=0) is False
        assert s.get_terminal_session("x") is None
        assert s.list_terminal_sessions() == []
        assert s.add_open_loop("t", "text") is None
        assert s.list_open_loops("t") == []
        assert s.close_open_loop(1) is False
        s.close()


# ---------------------------------------------------------------------------
# open_loops CRUD (continuity R2-N2)
# ---------------------------------------------------------------------------

class TestOpenLoops:
    def test_add_and_list(self, store):
        lid = store.add_open_loop("thread-1", "verify guest access is off")
        assert lid is not None
        loops = store.list_open_loops("thread-1")
        assert len(loops) == 1
        assert loops[0]["text"] == "verify guest access is off"
        assert loops[0]["closed_at"] is None

    def test_list_open_only(self, store):
        lid1 = store.add_open_loop("t1", "loop A")
        lid2 = store.add_open_loop("t1", "loop B")
        store.close_open_loop(lid1)
        loops = store.list_open_loops("t1", open_only=True)
        assert len(loops) == 1
        assert loops[0]["text"] == "loop B"

    def test_list_all_includes_closed(self, store):
        lid = store.add_open_loop("t1", "done loop")
        store.close_open_loop(lid)
        loops = store.list_open_loops("t1", open_only=False)
        assert len(loops) == 1
        assert loops[0]["closed_at"] is not None

    def test_close_idempotent(self, store):
        lid = store.add_open_loop("t1", "close me")
        assert store.close_open_loop(lid) is True
        # Second close is a no-op (WHERE closed_at IS NULL)
        assert store.close_open_loop(lid) is True
        loops = store.list_open_loops("t1", open_only=False)
        assert len(loops) == 1

    def test_thread_isolation(self, store):
        store.add_open_loop("t1", "thread 1 loop")
        store.add_open_loop("t2", "thread 2 loop")
        assert len(store.list_open_loops("t1")) == 1
        assert len(store.list_open_loops("t2")) == 1
        assert store.list_open_loops("t1")[0]["text"] == "thread 1 loop"
