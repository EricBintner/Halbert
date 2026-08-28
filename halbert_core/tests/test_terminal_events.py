# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for Plan B terminal block event factories (B12)."""

import pytest

from halbert_core.agents.events import StreamEvent


class TestTerminalSpawnExtended:
    def test_terminal_spawn_with_block_id(self):
        ev = StreamEvent.terminal_spawn(
            "sess-1", "tsess-1", "echo hi", 123,
            block_id="blk-1", owner="agent",
        )
        assert ev.type == "terminal_spawn"
        assert ev.data["block_id"] == "blk-1"
        assert ev.data["owner"] == "agent"

    def test_terminal_spawn_with_owner_user(self):
        ev = StreamEvent.terminal_spawn(
            "sess-1", "tsess-1", "bash", 123,
            owner="user", attach="ws",
        )
        assert ev.data["owner"] == "user"

    def test_terminal_spawn_block_id_defaults_none(self):
        ev = StreamEvent.terminal_spawn(
            "sess-1", "tsess-1", "echo hi", 123,
        )
        assert ev.data["block_id"] is None

    def test_terminal_spawn_owner_defaults_agent(self):
        ev = StreamEvent.terminal_spawn(
            "sess-1", "tsess-1", "echo hi", 123,
        )
        assert ev.data["owner"] == "agent"


class TestTerminalCompleteExtended:
    def test_terminal_complete_with_block_id(self):
        ev = StreamEvent.terminal_complete(
            "sess-1", "tsess-1", 0, block_id="blk-1",
        )
        assert ev.type == "terminal_complete"
        assert ev.data["block_id"] == "blk-1"
        assert ev.data["exit_code"] == 0

    def test_terminal_complete_without_block_id(self):
        ev = StreamEvent.terminal_complete("sess-1", "tsess-1", 0)
        assert "block_id" not in ev.data


class TestTerminalBlock:
    def test_terminal_block_basic(self):
        ev = StreamEvent.terminal_block(
            "sess-1",
            block_id="blk-1",
            terminal_session_id="tsess-1",
            command="ls -la",
            owner="agent",
        )
        assert ev.type == "terminal_block"
        assert ev.data["block_id"] == "blk-1"
        assert ev.data["command"] == "ls -la"
        assert ev.data["owner"] == "agent"
        assert ev.data["interactive"] is False

    def test_terminal_block_with_owner_user(self):
        ev = StreamEvent.terminal_block(
            "sess-1",
            block_id="blk-1",
            terminal_session_id="tsess-1",
            command="ls",
            owner="user",
        )
        assert ev.data["owner"] == "user"

    def test_terminal_block_interactive(self):
        ev = StreamEvent.terminal_block(
            "sess-1",
            block_id="blk-1",
            terminal_session_id="tsess-1",
            command="vim",
            owner="agent",
            interactive=True,
        )
        assert ev.data["interactive"] is True

    def test_terminal_block_promote(self):
        ev = StreamEvent.terminal_block(
            "sess-1",
            block_id="blk-1",
            terminal_session_id="tsess-1",
            command="long-build",
            owner="agent",
            promote=True,
        )
        assert ev.type == "terminal_block_promote"
        assert ev.data["block_id"] == "blk-1"


class TestTerminalNeedsInput:
    def test_terminal_needs_input(self):
        ev = StreamEvent.terminal_needs_input(
            "sess-1",
            block_id="blk-1",
            terminal_session_id="tsess-1",
        )
        assert ev.type == "terminal_needs_input"
        assert ev.data["block_id"] == "blk-1"
        assert ev.data["terminal_session_id"] == "tsess-1"


class TestTaskCompleted:
    def test_task_completed(self):
        ev = StreamEvent.task_completed(
            "sess-1",
            task_id="task-1",
            thread_id="thread-1",
            title="run tests",
            exit_code=0,
            duration=12.5,
            tail="all passed",
        )
        assert ev.type == "task_completed"
        assert ev.data["task_id"] == "task-1"
        assert ev.data["thread_id"] == "thread-1"
        assert ev.data["title"] == "run tests"
        assert ev.data["exit_code"] == 0
        assert ev.data["duration"] == 12.5
        assert ev.data["tail"] == "all passed"

    def test_task_completed_error(self):
        ev = StreamEvent.task_completed(
            "sess-1",
            task_id="task-2",
            thread_id="thread-1",
            title="failing cmd",
            exit_code=1,
            duration=0.5,
            tail="error: something",
        )
        assert ev.data["exit_code"] == 1
