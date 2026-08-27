# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Context watermark (F4).

Decides *when* to compact the agent's context, plus a cheap micro-compaction
pass. Full compaction itself is already built (the ``compression/`` package +
ContextAssembler._compress_with_cascade); F4 adds the trigger policy and the
tool-result truncation that runs first.

Policy (should_compact):
  - the 80% token watermark must be reached (token_count >= 0.8 * max_tokens)
  - AND either the 2-hour temporal gate has elapsed since the last compaction
    OR a topic boundary was detected (a natural compaction point, allowed even
    within the 2h window)

Micro-compaction (micro_compact): truncates old tool_result blocks whose content
exceeds ``tool_result_truncate`` chars (default 200) to a short prefix +
``...[truncated N chars]``. Operates on block-typed conversation history (A1),
tolerating both ToolResultBlock dataclasses and plain dicts.

WHAT OF THIS STILL SHIPS, as of the Plan A merge. ``micro_compact`` and the
``watermark`` attribute do: ``ContextAssembler.build_conversation_window``
compares ``used < wm.watermark * max_tokens`` itself and hard-trims. The
trigger policy does not. ``should_compact``'s only call site in the tree is
``assembler.py``'s compaction branch, inside ``_format_conversation``, which
no production caller reaches (see its docstring); ``detect_topic_change`` has
no caller at all outside ``tests/test_context_watermark.py``. Both are kept —
they are a coherent, tested policy and the window trimmer is a cruder thing
than they are — but ``tests/test_context_watermark.py`` passing is not
evidence that any shipping decision goes through them.

See OPUS-HANDOFF §F4 and STRATEGY-V2-SCRUTINY.md §2 Hidden Dependency 5.
"""

from __future__ import annotations

import time
from typing import Any, List, Optional

from ..agents.blocks import ToolResultBlock

__all__ = ["ContextWatermark"]


class ContextWatermark:
    """Context-compaction trigger + micro-compaction (F4)."""

    def __init__(
        self,
        watermark: float = 0.8,
        temporal_gate_seconds: float = 7200.0,  # 2 hours
        tool_result_truncate: int = 200,
        topic_overlap_threshold: float = 0.3,
    ):
        self.watermark = watermark
        self.temporal_gate = temporal_gate_seconds
        self.tool_result_truncate = tool_result_truncate
        self.topic_overlap_threshold = topic_overlap_threshold

    # ------------------------------------------------------------------
    # Trigger
    # ------------------------------------------------------------------

    def should_compact(
        self,
        token_count: int,
        max_tokens: int,
        last_compaction_ts: float = 0.0,
        topic_changed: bool = False,
        now: Optional[float] = None,
    ) -> bool:
        """True when the 80% watermark is reached and a gate allows compaction.

        NO PRODUCTION CALLER. The one call site in the tree is
        ``ContextAssembler._format_conversation``'s compaction branch, and
        nothing production reaches that function. Nothing in the shipping path
        compacts on a trigger at all: ``build_conversation_window`` reads
        ``self.watermark`` directly and trims to fit. See the module docstring.
        """
        if max_tokens <= 0:
            return False
        if token_count < self.watermark * max_tokens:
            return False
        # Topic boundary: a natural compaction point (allowed within 2h)
        if topic_changed:
            return True
        # Temporal gate: don't compact more than once per window
        ts = now if now is not None else time.time()
        return (ts - last_compaction_ts) >= self.temporal_gate

    # ------------------------------------------------------------------
    # Micro-compaction: truncate long tool results
    # ------------------------------------------------------------------

    def micro_compact(self, conversation_history: List[dict]) -> int:
        """Truncate old tool_result blocks over the char cap. Returns count.

        Mutates tool_result blocks in place (both ToolResultBlock dataclasses
        and plain dicts). Non-tool_result content is left untouched.
        """
        cap = self.tool_result_truncate
        if cap <= 0:
            return 0
        truncated = 0
        for msg in conversation_history:
            content = msg.get("content") if isinstance(msg, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if self._truncate_block(block, cap):
                    truncated += 1
        return truncated

    def _truncate_block(self, block: Any, cap: int) -> bool:
        """Truncate one block if it's a long tool_result. Returns True if truncated."""
        is_tr = False
        text = None
        if isinstance(block, ToolResultBlock):
            is_tr = True
            text = block.content
        elif isinstance(block, dict) and block.get("type") == "tool_result":
            is_tr = True
            text = block.get("content", "")
        if not is_tr or not isinstance(text, str) or len(text) <= cap:
            return False
        suffix = f"...[truncated {len(text) - cap} chars]"
        new_text = text[:cap] + suffix
        if isinstance(block, ToolResultBlock):
            block.content = new_text
        else:
            block["content"] = new_text
        return True

    # ------------------------------------------------------------------
    # Topic-boundary detection
    # ------------------------------------------------------------------

    def detect_topic_change(
        self, query: str, prev_query: Optional[str] = None
    ) -> bool:
        """Heuristic topic-change check via word-overlap (Jaccard).

        Returns True when there's no previous query, or the word overlap with
        the previous query falls below ``topic_overlap_threshold``.

        NO CALLER outside ``tests/test_context_watermark.py``. It fed
        ``should_compact``'s ``topic_changed`` gate, which is itself unreached
        (above). Note that Plan A's topic segmentation is a different, much
        richer mechanism — ``agents/thread_signals.py`` decides where one
        subject ends — so this is not the thing that splits threads today, and
        wiring it back in would be a second, disagreeing opinion about the same
        question rather than a missing connection.
        """
        if not prev_query:
            return True
        cur = {w.lower() for w in _tokens(query) if len(w) > 2}
        prev = {w.lower() for w in _tokens(prev_query) if len(w) > 2}
        if not cur or not prev:
            return True
        overlap = len(cur & prev) / len(cur | prev)
        return overlap < self.topic_overlap_threshold


def _tokens(text: str) -> List[str]:
    return (text or "").split()
