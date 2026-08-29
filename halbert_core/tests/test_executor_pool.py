# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for executor _run_command pool wiring (Plan B: B7)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from halbert_core.tools.executor import ToolExecutor


class TestFormatBlockResult:
    def test_success_with_output(self):
        result = {"exit_code": 0, "output_head": "hello", "output_tail": "hello"}
        out = ToolExecutor._format_block_result(result)
        assert "hello" in out
        assert "Exit code" not in out

    def test_error_with_output(self):
        result = {"exit_code": 1, "output_head": "error msg", "output_tail": "error msg"}
        out = ToolExecutor._format_block_result(result)
        assert "Exit code 1" in out
        assert "error msg" in out

    def test_success_no_output(self):
        result = {"exit_code": 0, "output_head": "", "output_tail": ""}
        out = ToolExecutor._format_block_result(result)
        assert "(no output)" in out

    def test_head_and_tail_combined(self):
        result = {
            "exit_code": 0,
            "output_head": "line1\nline2",
            "output_tail": "lineN",
        }
        out = ToolExecutor._format_block_result(result)
        assert "line1" in out
        assert "lineN" in out


class TestRunCommandPoolPath:
    @pytest.mark.asyncio
    async def test_pool_path_used_when_streaming(self):
        """When streaming is wanted, the pool path is tried first."""
        executor = ToolExecutor.__new__(ToolExecutor)

        mock_result = {
            "block_id": "blk-1",
            "session_id": "sess-1",
            "exit_code": 0,
            "output_head": "hello world",
            "output_tail": "hello world",
            "duration": 0.1,
        }

        mock_pool = MagicMock()
        mock_pool.run_block = AsyncMock(return_value=mock_result)

        with patch(
            "halbert_core.streaming.agent_pool.get_terminal_pool",
            return_value=mock_pool,
        ), patch(
            "halbert_core.tools.executor.terminal_pool_wanted",
            return_value=True,
        ), patch(
            "halbert_core.tools.executor.terminal_stream_wanted",
            return_value=True,
        ):
            result = await executor._run_command({
                "command": "echo hello world",
                "timeout": 5,
            })

        assert "hello world" in result
        mock_pool.run_block.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_subprocess_on_pool_none(self):
        """When pool returns None (at cap), falls back to subprocess."""
        executor = ToolExecutor.__new__(ToolExecutor)

        mock_pool = MagicMock()
        mock_pool.run_block = AsyncMock(return_value=None)

        with patch(
            "halbert_core.streaming.agent_pool.get_terminal_pool",
            return_value=mock_pool,
        ), patch(
            "halbert_core.tools.executor.terminal_pool_wanted",
            return_value=True,
        ), patch(
            "halbert_core.tools.executor.terminal_stream_wanted",
            return_value=True,
        ), patch(
            "halbert_core.tools.executor.publish_terminal_event",
        ):
            result = await executor._run_command({
                "command": "echo fallback",
                "timeout": 5,
            })

        assert "fallback" in result

    @pytest.mark.asyncio
    async def test_falls_back_on_pool_exception(self):
        """When pool raises, falls back to subprocess without crashing."""
        executor = ToolExecutor.__new__(ToolExecutor)

        mock_pool = MagicMock()
        mock_pool.run_block = AsyncMock(side_effect=Exception("pool down"))

        with patch(
            "halbert_core.streaming.agent_pool.get_terminal_pool",
            return_value=mock_pool,
        ), patch(
            "halbert_core.tools.executor.terminal_pool_wanted",
            return_value=True,
        ), patch(
            "halbert_core.tools.executor.terminal_stream_wanted",
            return_value=True,
        ), patch(
            "halbert_core.tools.executor.publish_terminal_event",
        ):
            result = await executor._run_command({
                "command": "echo recovered",
                "timeout": 5,
            })

        assert "recovered" in result

    @pytest.mark.asyncio
    async def test_pool_not_used_when_not_streaming(self):
        """When streaming is not wanted, the pool is not tried."""
        executor = ToolExecutor.__new__(ToolExecutor)

        mock_pool = MagicMock()
        mock_pool.run_block = AsyncMock(return_value=None)

        with patch(
            "halbert_core.streaming.agent_pool.get_terminal_pool",
            return_value=mock_pool,
        ), patch(
            "halbert_core.tools.executor.terminal_pool_wanted",
            return_value=False,
        ), patch(
            "halbert_core.tools.executor.terminal_stream_wanted",
            return_value=False,
        ), patch(
            "halbert_core.tools.executor.publish_terminal_event",
        ):
            result = await executor._run_command({
                "command": "echo nosubprocess",
                "timeout": 5,
            })

        # Pool was not called
        mock_pool.run_block.assert_not_called()
        assert "nosubprocess" in result

    @pytest.mark.asyncio
    async def test_background_kwarg_accepted(self):
        """The background kwarg (Plan C) is accepted but ignored in Plan B."""
        executor = ToolExecutor.__new__(ToolExecutor)

        mock_pool = MagicMock()
        mock_pool.run_block = AsyncMock(return_value=None)

        with patch(
            "halbert_core.streaming.agent_pool.get_terminal_pool",
            return_value=mock_pool,
        ), patch(
            "halbert_core.tools.executor.terminal_pool_wanted",
            return_value=True,
        ), patch(
            "halbert_core.tools.executor.terminal_stream_wanted",
            return_value=True,
        ), patch(
            "halbert_core.tools.executor.publish_terminal_event",
        ):
            # Should not raise
            result = await executor._run_command({
                "command": "echo bg",
                "timeout": 5,
                "background": True,
            })

        # background kwarg is accepted but ignored (Plan C) — pool still used
        mock_pool.run_block.assert_called_once()
        assert "bg" in result
