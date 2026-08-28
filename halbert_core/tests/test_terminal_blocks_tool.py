# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the terminal_blocks fetch tool (Plan B: B11)."""

import json
import time

import pytest
from unittest.mock import MagicMock, patch

from halbert_core.tools.executor import ToolExecutor


@pytest.fixture
def store_with_blocks():
    store = MagicMock()
    store.list_terminal_blocks.return_value = [
        {
            "block_id": "blk-1",
            "session_id": "sess-1",
            "command": "echo hello",
            "exit_code": 0,
            "cwd": "/tmp",
            "output_head": "hello",
            "output_tail": "hello",
            "started_at": 1000.0,
            "ended_at": 1000.1,
        },
        {
            "block_id": "blk-2",
            "session_id": "sess-1",
            "command": "ls -la",
            "exit_code": 0,
            "cwd": "/tmp",
            "output_head": "total 0",
            "output_tail": "total 0",
            "started_at": 1001.0,
            "ended_at": 1001.2,
        },
    ]
    return store


class TestTerminalBlocksTool:
    @pytest.mark.asyncio
    async def test_returns_blocks_for_session(self, store_with_blocks):
        executor = ToolExecutor.__new__(ToolExecutor)
        mock_manager = MagicMock()
        mock_manager.store = store_with_blocks

        with patch(
            "halbert_core.agents.threads.get_thread_manager",
            return_value=mock_manager,
        ):
            result = await executor._terminal_blocks({
                "session_id": "sess-1",
                "n": 5,
            })

        data = json.loads(result)
        assert len(data) == 2
        assert data[0]["block_id"] == "blk-1"
        assert data[0]["command"] == "echo hello"
        assert data[0]["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_returns_blocks_without_session(self, store_with_blocks):
        executor = ToolExecutor.__new__(ToolExecutor)
        mock_manager = MagicMock()
        mock_manager.store = store_with_blocks

        with patch(
            "halbert_core.agents.threads.get_thread_manager",
            return_value=mock_manager,
        ):
            result = await executor._terminal_blocks({"n": 10})

        data = json.loads(result)
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_default_n_is_5(self, store_with_blocks):
        executor = ToolExecutor.__new__(ToolExecutor)
        mock_manager = MagicMock()
        mock_manager.store = store_with_blocks

        with patch(
            "halbert_core.agents.threads.get_thread_manager",
            return_value=mock_manager,
        ):
            await executor._terminal_blocks({"session_id": "sess-1"})

        # list_terminal_blocks was called with limit=5
        store_with_blocks.list_terminal_blocks.assert_called_once_with(
            session_id="sess-1", limit=5,
        )

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        executor = ToolExecutor.__new__(ToolExecutor)
        mock_manager = MagicMock()
        mock_manager.store = MagicMock()
        mock_manager.store.list_terminal_blocks.side_effect = Exception("db down")

        with patch(
            "halbert_core.agents.threads.get_thread_manager",
            return_value=mock_manager,
        ):
            result = await executor._terminal_blocks({"session_id": "sess-1"})

        assert result == "[]"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_blocks(self):
        executor = ToolExecutor.__new__(ToolExecutor)
        mock_manager = MagicMock()
        mock_manager.store = MagicMock()
        mock_manager.store.list_terminal_blocks.return_value = []

        with patch(
            "halbert_core.agents.threads.get_thread_manager",
            return_value=mock_manager,
        ):
            result = await executor._terminal_blocks({"session_id": "sess-1"})

        data = json.loads(result)
        assert data == []

    @pytest.mark.asyncio
    async def test_output_fields_present(self, store_with_blocks):
        executor = ToolExecutor.__new__(ToolExecutor)
        mock_manager = MagicMock()
        mock_manager.store = store_with_blocks

        with patch(
            "halbert_core.agents.threads.get_thread_manager",
            return_value=mock_manager,
        ):
            result = await executor._terminal_blocks({"session_id": "sess-1"})

        data = json.loads(result)
        block = data[0]
        assert "block_id" in block
        assert "command" in block
        assert "exit_code" in block
        assert "cwd" in block
        assert "output_head" in block
        assert "output_tail" in block
        assert "started_at" in block
        assert "ended_at" in block

    @pytest.mark.asyncio
    async def test_tool_is_registered(self):
        """The terminal_blocks tool is registered in _register_builtins."""
        executor = ToolExecutor()
        schemas = executor.get_schemas()
        # Schemas are in OpenAI format: list of {type: function, function: {name, ...}}
        tool_names = [s.get("function", {}).get("name", "") for s in schemas]
        assert "terminal_blocks" in tool_names
        tb_schema = next(s["function"] for s in schemas if s.get("function", {}).get("name") == "terminal_blocks")
        assert "session_id" in tb_schema["parameters"]["properties"]
        assert "n" in tb_schema["parameters"]["properties"]
