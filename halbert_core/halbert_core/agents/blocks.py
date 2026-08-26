# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Content Block Types for Block-Typed Conversation History

Mirrors the Anthropic Messages API content-block format so conversation
history can store structured turns (text + tool_use + tool_result) instead
of flattening every message to a string. This preserves tool-call structure
across turns for more accurate multi-turn tool use.

A message's ``content`` may now be either:
- a ``str`` (legacy, fully backwards-compatible), or
- a ``list`` of content blocks (TextBlock / ToolUseBlock / ToolResultBlock
  dataclass instances, or plain dicts with a ``"type"`` key).

The helpers below normalize either form to plain text (for the many
string-based consumers) or to an Anthropic content-block list (for the LLM).
See STRATEGY-V2-SCRUTINY.md §A1 and OPUS-HANDOFF Phase A1.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Union

__all__ = [
    "TextBlock",
    "ToolUseBlock",
    "ToolResultBlock",
    "block_to_text",
    "content_to_text",
    "content_to_anthropic",
    "is_block_content",
]


@dataclass
class TextBlock:
    """A plain-text content block (Anthropic ``type: "text"``)."""
    type: str = "text"
    text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "text", "text": self.text}

    def to_text(self) -> str:
        return self.text


@dataclass
class ToolUseBlock:
    """A model-emitted tool call (Anthropic ``type: "tool_use"``)."""
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "tool_use",
            "id": self.id,
            "name": self.name,
            "input": self.input,
        }

    def to_text(self) -> str:
        return f"[tool_use: {self.name}({self.input})]"


@dataclass
class ToolResultBlock:
    """A tool execution result (Anthropic ``type: "tool_result"``)."""
    type: str = "tool_result"
    tool_use_id: str = ""
    content: str = ""
    is_error: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_use_id": self.tool_use_id,
            "content": self.content,
            "is_error": self.is_error,
        }

    def to_text(self) -> str:
        prefix = "[tool_result error" if self.is_error else "[tool_result"
        return f"{prefix}: {self.content}]"


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def block_to_text(block: Any) -> str:
    """Render a single content block (dataclass or dict) to plain text."""
    if block is None:
        return ""
    if isinstance(block, str):
        return block
    # Dataclass instances expose a ``to_text`` method
    to_text = getattr(block, "to_text", None)
    if callable(to_text):
        return to_text()
    if isinstance(block, dict):
        btype = block.get("type", "text")
        if btype == "text":
            return block.get("text", "")
        if btype == "tool_use":
            return f"[tool_use: {block.get('name', '')}({block.get('input', {})})]"
        if btype == "tool_result":
            content = block.get("content", "")
            tag = "tool_result error" if block.get("is_error") else "tool_result"
            return f"[{tag}: {content}]"
        return str(block)
    return str(block)


def content_to_text(content: Any) -> str:
    """Normalize a message's ``content`` (str or list of blocks) to plain text.

    This is the bridge every string-based consumer calls so it keeps working
    when conversation_history carries block-typed content. String content is
    returned unchanged, preserving full backwards compatibility.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(block_to_text(b) for b in content)
    return str(content)


def content_to_anthropic(content: Any) -> List[Dict[str, Any]]:
    """Normalize a message's ``content`` to an Anthropic content-block list."""
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    if isinstance(content, list):
        out: List[Dict[str, Any]] = []
        for b in content:
            if isinstance(b, str):
                if b:
                    out.append({"type": "text", "text": b})
            elif hasattr(b, "to_dict") and callable(b.to_dict):
                out.append(b.to_dict())
            elif isinstance(b, dict):
                out.append(b)
        return out
    return [{"type": "text", "text": str(content)}]


def is_block_content(content: Any) -> bool:
    """Return True if ``content`` is block-typed (a list), False if a string."""
    return isinstance(content, list)
