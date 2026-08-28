# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for watched user shell block processing (Plan B: B8)."""

import time

import pytest

from halbert_core.streaming.watched_shell import (
    WatchedShellProcessor,
    BlockRecord,
)
from halbert_core.agents.conversation_sqlite import SqliteConversationStore


@pytest.fixture
def store():
    s = SqliteConversationStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def processor(store):
    return WatchedShellProcessor(store)


# ---------------------------------------------------------------------------
# BlockRecord
# ---------------------------------------------------------------------------

class TestBlockRecord:
    def test_create_block_record(self):
        rec = BlockRecord(
            block_id="blk-1",
            session_id="sess-1",
            command="ls -la",
            cwd="/tmp",
            exit_code=0,
            started_at=1000.0,
            ended_at=1000.5,
            output_head="total 0",
            output_tail="total 0",
        )
        assert rec.block_id == "blk-1"
        assert rec.command == "ls -la"
        assert rec.exit_code == 0

    def test_duration(self):
        rec = BlockRecord(
            block_id="blk-1", session_id="s", command="cmd", cwd=None,
            exit_code=0, started_at=1000.0, ended_at=1000.5,
            output_head="", output_tail="",
        )
        assert rec.duration == 0.5


# ---------------------------------------------------------------------------
# process_block_close
# ---------------------------------------------------------------------------

class TestProcessBlockClose:
    def test_inserts_terminal_block(self, processor, store):
        rec = BlockRecord(
            block_id="blk-1", session_id="sess-1", command="ls -la",
            cwd="/tmp", exit_code=0, started_at=1000.0, ended_at=1000.5,
            output_head="total 0", output_tail="total 0",
        )
        processor.process_block_close(rec, thread_id="thread-1", watched=True)
        block = store.get_terminal_block("blk-1")
        assert block is not None
        assert block["command"] == "ls -la"
        assert block["exit_code"] == 0
        assert block["cwd"] == "/tmp"
        assert block["owner"] == "user"

    def test_redacts_output(self, processor, store):
        rec = BlockRecord(
            block_id="blk-2", session_id="s", command="cat config",
            cwd=None, exit_code=0, started_at=1000.0, ended_at=1000.1,
            output_head="password=secret123", output_tail="password=secret123",
        )
        processor.process_block_close(rec, thread_id="thread-1", watched=True)
        block = store.get_terminal_block("blk-2")
        assert block["redacted"] == 1
        assert "secret123" not in block["output_head"]
        assert "secret123" not in block["output_tail"]

    def test_appends_message_when_watched(self, processor, store):
        # Create a thread first
        store.create_thread("thread-1", "test", created_at=time.time())
        rec = BlockRecord(
            block_id="blk-3", session_id="s", command="echo hi",
            cwd="/tmp", exit_code=0, started_at=1000.0, ended_at=1000.1,
            output_head="hi", output_tail="hi",
        )
        processor.process_block_close(rec, thread_id="thread-1", watched=True)
        msgs = store.list_messages("thread-1")
        assert len(msgs) == 1
        assert msgs[0]["origin"] == "terminal"
        assert "echo hi" in msgs[0]["content"]
        assert "exit 0" in msgs[0]["content"]
        assert msgs[0]["terminal_block_ids"] == ["blk-3"]

    def test_does_not_append_message_when_not_watched(self, processor, store):
        store.create_thread("thread-1", "test", created_at=time.time())
        rec = BlockRecord(
            block_id="blk-4", session_id="s", command="echo hi",
            cwd=None, exit_code=0, started_at=1000.0, ended_at=1000.1,
            output_head="hi", output_tail="hi",
        )
        processor.process_block_close(rec, thread_id="thread-1", watched=False)
        # Block is still inserted
        assert store.get_terminal_block("blk-4") is not None
        # But no message
        msgs = store.list_messages("thread-1")
        assert len(msgs) == 0

    def test_does_not_append_message_when_no_thread(self, processor, store):
        rec = BlockRecord(
            block_id="blk-5", session_id="s", command="echo hi",
            cwd=None, exit_code=0, started_at=1000.0, ended_at=1000.1,
            output_head="hi", output_tail="hi",
        )
        processor.process_block_close(rec, thread_id=None, watched=True)
        # Block is still inserted
        assert store.get_terminal_block("blk-5") is not None

    def test_message_content_format(self, processor, store):
        store.create_thread("thread-1", "test", created_at=time.time())
        rec = BlockRecord(
            block_id="blk-6", session_id="s", command="ls /tmp",
            cwd="/tmp", exit_code=1, started_at=1000.0, ended_at=1002.5,
            output_head="", output_tail="",
        )
        processor.process_block_close(rec, thread_id="thread-1", watched=True)
        msgs = store.list_messages("thread-1")
        content = msgs[0]["content"]
        assert "$ ls /tmp" in content
        assert "exit 1" in content
        assert "2.5s" in content
        assert "cwd=/tmp" in content

    def test_updates_thread_last_active(self, processor, store):
        store.create_thread("thread-1", "test", created_at=time.time())
        rec = BlockRecord(
            block_id="blk-7", session_id="s", command="echo hi",
            cwd=None, exit_code=0, started_at=1000.0, ended_at=1000.1,
            output_head="hi", output_tail="hi",
        )
        processor.process_block_close(rec, thread_id="thread-1", watched=True)
        thread = store.get("thread-1")
        assert thread is not None
        assert thread.updated_at >= rec.ended_at

    def test_handles_store_failure_gracefully(self, processor):
        # Dead store
        processor._store._conn = None
        rec = BlockRecord(
            block_id="blk-8", session_id="s", command="echo hi",
            cwd=None, exit_code=0, started_at=1000.0, ended_at=1000.1,
            output_head="hi", output_tail="hi",
        )
        # Should not raise
        processor.process_block_close(rec, thread_id="thread-1", watched=True)


# ---------------------------------------------------------------------------
# Hint data
# ---------------------------------------------------------------------------

class TestHintData:
    def test_get_recent_blocks(self, processor, store):
        store.create_thread("thread-1", "test", created_at=time.time())
        for i in range(3):
            rec = BlockRecord(
                block_id=f"blk-h-{i}", session_id="s", command=f"cmd{i}",
                cwd=None, exit_code=0, started_at=1000.0 + i, ended_at=1000.1 + i,
                output_head="", output_tail="",
            )
            processor.process_block_close(rec, thread_id="thread-1", watched=True)

        blocks = processor.get_recent_blocks("thread-1", limit=8)
        assert len(blocks) == 3
        # newest first
        assert blocks[0]["command"] == "cmd2"

    def test_get_recent_blocks_empty(self, processor, store):
        blocks = processor.get_recent_blocks("nope", limit=8)
        assert blocks == []

    def test_get_recent_blocks_limit(self, processor, store):
        store.create_thread("thread-1", "test", created_at=time.time())
        for i in range(10):
            rec = BlockRecord(
                block_id=f"blk-l-{i}", session_id="s", command=f"cmd{i}",
                cwd=None, exit_code=0, started_at=1000.0 + i, ended_at=1000.1 + i,
                output_head="", output_tail="",
            )
            processor.process_block_close(rec, thread_id="thread-1", watched=True)
        blocks = processor.get_recent_blocks("thread-1", limit=5)
        assert len(blocks) == 5

    def test_hint_text_with_blocks(self, processor, store):
        store.create_thread("thread-1", "test", created_at=time.time())
        rec = BlockRecord(
            block_id="blk-ht", session_id="s", command="ls /tmp",
            cwd="/tmp", exit_code=0, started_at=1000.0, ended_at=1000.1,
            output_head="", output_tail="",
        )
        processor.process_block_close(rec, thread_id="thread-1", watched=True)
        hint = processor.build_hint_text("thread-1")
        assert hint is not None
        assert "1 command" in hint
        assert "ls /tmp" in hint

    def test_hint_text_no_blocks(self, processor, store):
        hint = processor.build_hint_text("thread-1")
        assert hint is None
