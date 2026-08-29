# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for terminal_block_ids migration (Plan B: B21)."""

import json
import time

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore


@pytest.fixture
def store(tmp_path):
    s = SqliteConversationStore(str(tmp_path / "test.db"))
    yield s
    s.close()


class TestMigrateTerminalBlockIdsToBlocks:
    def test_no_messages_returns_zero(self, store):
        assert store.migrate_terminal_block_ids_to_blocks() == 0

    def test_migrates_session_ids_to_block_ids(self, store):
        """A message with session_ids should be updated to block_ids."""
        thread_id = "thread-1"
        store.create_thread(thread_id, "Test", created_at=time.time())
        session_id = "sess-1"
        # Insert a terminal_block for this session
        store.insert_terminal_block({
            "block_id": "blk-1",
            "session_id": session_id,
            "thread_id": thread_id,
            "turn_id": "turn-1",
            "command": "echo hi",
            "cwd": "/tmp",
            "owner": "agent",
            "interactive": 0,
            "remote": 0,
            "redacted": 0,
            "started_at": time.time(),
            "ended_at": time.time() + 0.1,
            "exit_code": 0,
            "output_head": "hi",
            "output_tail": "hi",
        })
        # Insert a message with the session_id in terminal_block_ids
        store.append_message(
            thread_id, "assistant", "ran a command",
            origin="assistant", terminal_block_ids=[session_id],
        )
        # Run migration
        updated = store.migrate_terminal_block_ids_to_blocks()
        assert updated == 1
        # Verify the message now has the block_id
        msgs = store.list_messages(thread_id)
        assert len(msgs) >= 1
        assistant_msg = [m for m in msgs if m["role"] == "assistant"][0]
        ids = assistant_msg.get("terminal_block_ids") or []
        assert "blk-1" in ids
        assert session_id not in ids

    def test_idempotent(self, store):
        """Running twice doesn't re-update already-migrated messages."""
        thread_id = "thread-1"
        store.create_thread(thread_id, "Test", created_at=time.time())
        session_id = "sess-1"
        store.insert_terminal_block({
            "block_id": "blk-1",
            "session_id": session_id,
            "thread_id": thread_id,
            "turn_id": "turn-1",
            "command": "echo hi",
            "cwd": "/tmp",
            "owner": "agent",
            "interactive": 0,
            "remote": 0,
            "redacted": 0,
            "started_at": time.time(),
            "ended_at": time.time() + 0.1,
            "exit_code": 0,
            "output_head": "hi",
            "output_tail": "hi",
        })
        store.append_message(
            thread_id, "assistant", "ran a command",
            origin="assistant", terminal_block_ids=[session_id],
        )
        first = store.migrate_terminal_block_ids_to_blocks()
        second = store.migrate_terminal_block_ids_to_blocks()
        assert first == 1
        assert second == 0

    def test_leaves_oneshot_without_blocks_as_is(self, store):
        """A session_id with no terminal_blocks rows is left unchanged."""
        thread_id = "thread-1"
        store.create_thread(thread_id, "Test", created_at=time.time())
        store.append_message(
            thread_id, "assistant", "ran a oneshot",
            origin="assistant", terminal_block_ids=["oneshot-sess-no-blocks"],
        )
        updated = store.migrate_terminal_block_ids_to_blocks()
        assert updated == 0
        msgs = store.list_messages(thread_id)
        assistant_msg = [m for m in msgs if m["role"] == "assistant"][0]
        ids = assistant_msg.get("terminal_block_ids") or []
        assert ids == ["oneshot-sess-no-blocks"]

    def test_already_block_ids_left_as_is(self, store):
        """A message that already has block_ids is not changed."""
        thread_id = "thread-1"
        store.create_thread(thread_id, "Test", created_at=time.time())
        store.insert_terminal_block({
            "block_id": "blk-existing",
            "session_id": "sess-x",
            "thread_id": thread_id,
            "turn_id": "turn-1",
            "command": "echo hi",
            "cwd": "/tmp",
            "owner": "agent",
            "interactive": 0,
            "remote": 0,
            "redacted": 0,
            "started_at": time.time(),
            "ended_at": time.time() + 0.1,
            "exit_code": 0,
            "output_head": "hi",
            "output_tail": "hi",
        })
        store.append_message(
            thread_id, "assistant", "already has block id",
            origin="assistant", terminal_block_ids=["blk-existing"],
        )
        updated = store.migrate_terminal_block_ids_to_blocks()
        assert updated == 0

    def test_multiple_session_ids(self, store):
        """Multiple session_ids in one message are all migrated."""
        thread_id = "thread-1"
        store.create_thread(thread_id, "Test", created_at=time.time())
        for i in range(3):
            store.insert_terminal_block({
                "block_id": f"blk-{i}",
                "session_id": f"sess-{i}",
                "thread_id": thread_id,
                "turn_id": "turn-1",
                "command": f"echo {i}",
                "cwd": "/tmp",
                "owner": "agent",
                "interactive": 0,
                "remote": 0,
                "redacted": 0,
                "started_at": time.time(),
                "ended_at": time.time() + 0.1,
                "exit_code": 0,
                "output_head": str(i),
                "output_tail": str(i),
            })
        store.append_message(
            thread_id, "assistant", "ran 3 commands",
            origin="assistant",
            terminal_block_ids=["sess-0", "sess-1", "sess-2"],
        )
        updated = store.migrate_terminal_block_ids_to_blocks()
        assert updated == 1
        msgs = store.list_messages(thread_id)
        assistant_msg = [m for m in msgs if m["role"] == "assistant"][0]
        ids = assistant_msg.get("terminal_block_ids") or []
        assert set(ids) == {"blk-0", "blk-1", "blk-2"}
