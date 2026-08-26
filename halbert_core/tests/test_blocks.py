# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for block-typed conversation history (A1).

Covers agents/blocks.py dataclasses + normalization helpers and the
StateContext block helpers, plus backwards-compatibility of the string
content path through the assembler/summarization consumers.
"""

import pytest

from halbert_core.agents.blocks import (
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    block_to_text,
    content_to_text,
    content_to_anthropic,
    is_block_content,
)
from halbert_core.agents.states import StateContext
from halbert_core.conversation.summarization import (
    create_simple_summary,
    estimate_token_count,
    should_summarize,
    compress_conversation_history,
)


class TestContentBlocks:
    def test_text_block_to_dict(self):
        assert TextBlock(text="hi").to_dict() == {"type": "text", "text": "hi"}

    def test_tool_use_block_to_dict(self):
        b = ToolUseBlock(id="tu1", name="ls", input={"path": "/"})
        d = b.to_dict()
        assert d["type"] == "tool_use"
        assert d["id"] == "tu1"
        assert d["input"] == {"path": "/"}

    def test_tool_result_block_to_dict(self):
        b = ToolResultBlock(tool_use_id="tu1", content="ok", is_error=False)
        assert b.to_dict() == {
            "type": "tool_result",
            "tool_use_id": "tu1",
            "content": "ok",
            "is_error": False,
        }


class TestContentToText:
    def test_string_passthrough(self):
        assert content_to_text("hello") == "hello"

    def test_none(self):
        assert content_to_text(None) == ""

    def test_list_of_dataclass_blocks(self):
        blocks = [
            TextBlock(text="hi"),
            ToolUseBlock(id="x", name="ls", input={}),
            ToolResultBlock(tool_use_id="x", content="file1", is_error=False),
        ]
        out = content_to_text(blocks)
        assert "hi" in out
        assert "[tool_use: ls" in out
        assert "[tool_result: file1]" in out

    def test_list_of_dict_blocks(self):
        out = content_to_text([{"type": "text", "text": "json-block"}])
        assert out == "json-block"

    def test_tool_result_error_rendered(self):
        out = block_to_text(ToolResultBlock(content="boom", is_error=True))
        assert "error" in out and "boom" in out


class TestContentToAnthropic:
    def test_string(self):
        assert content_to_anthropic("hi") == [{"type": "text", "text": "hi"}]

    def test_empty_string(self):
        assert content_to_anthropic("") == []

    def test_blocks(self):
        out = content_to_anthropic([TextBlock(text="hi")])
        assert out == [{"type": "text", "text": "hi"}]


class TestIsBlockContent:
    def test_list_is_blocks(self):
        assert is_block_content([TextBlock(text="x")]) is True

    def test_string_is_not_blocks(self):
        assert is_block_content("x") is False


class TestStateContextBlockHelpers:
    def _ctx(self):
        return StateContext(
            session_id="s", request_id="r", user_query="check disks"
        )

    def test_add_text_block(self):
        ctx = self._ctx()
        ctx.add_text_block("user", "check disks")
        msg = ctx.conversation_history[-1]
        assert msg["role"] == "user"
        assert is_block_content(msg["content"])
        assert content_to_text(msg["content"]) == "check disks"

    def test_add_tool_use_block_creates_new_assistant_turn(self):
        ctx = self._ctx()
        ctx.add_tool_use_block("tu1", "read_file", {"path": "/etc/fstab"})
        msg = ctx.conversation_history[-1]
        assert msg["role"] == "assistant"
        assert isinstance(msg["content"][0], ToolUseBlock)
        assert msg["content"][0].name == "read_file"

    def test_add_tool_use_block_appends_to_existing_assistant_turn(self):
        ctx = self._ctx()
        ctx.add_text_block("assistant", "let me check")
        ctx.add_tool_use_block("tu1", "read_file", {"path": "/etc/fstab"})
        # Should NOT create a new message — append to the assistant turn
        assert len(ctx.conversation_history) == 1
        assert len(ctx.conversation_history[0]["content"]) == 2

    def test_add_tool_result_block_is_user_role(self):
        ctx = self._ctx()
        ctx.add_tool_result_block("tu1", "UUID=abc / ext4", is_error=False)
        msg = ctx.conversation_history[-1]
        assert msg["role"] == "user"
        assert isinstance(msg["content"][0], ToolResultBlock)
        assert msg["content"][0].is_error is False

    def test_add_tool_result_block_coerces_nonstring(self):
        ctx = self._ctx()
        ctx.add_tool_result_block("tu1", {"data": 42}, is_error=False)
        assert isinstance(ctx.conversation_history[-1]["content"][0].content, str)


class TestBlockTolerantConsumers:
    """The string-based consumers must accept block-typed history (A1)."""

    def test_create_simple_summary_with_blocks(self):
        msgs = [
            {"role": "user", "content": [TextBlock(text="install nginx")]},
            {"role": "assistant", "content": [TextBlock(text="ran apt install nginx")]},
        ]
        summary = create_simple_summary(msgs)
        assert "nginx" in summary

    def test_estimate_token_count_with_blocks(self):
        msgs = [{"role": "user", "content": [TextBlock(text="abcd")]}]
        # 4 chars / 4 = 1 token
        assert estimate_token_count(msgs) == 1

    def test_should_summarize_counts_messages_not_content(self):
        msgs = [{"role": "user", "content": [TextBlock(text="x")]}] * 12
        assert should_summarize(msgs) is True

    def test_compress_conversation_history_with_blocks(self):
        msgs = [{"role": "user", "content": [TextBlock(text=f"msg {i}")]} for i in range(20)]
        compressed, summary = compress_conversation_history(msgs, keep_recent=6)
        assert summary is not None
        # Recent messages keep their (block) content; summary is a string
        assert isinstance(summary, str)
        assert is_block_content(compressed[-1]["content"])

    def test_legacy_string_history_still_works(self):
        """Backwards compat: plain string content must pass through unchanged."""
        msgs = [{"role": "user", "content": "plain string message"}]
        assert content_to_text(msgs[0]["content"]) == "plain string message"
        assert create_simple_summary(msgs) is not None
