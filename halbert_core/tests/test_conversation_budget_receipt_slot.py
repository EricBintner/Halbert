# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A8b: the conversation bucket fits six raw turns at MEDIUM, and
the assembler renders a thread receipt in its own slot instead of
re-summarising the history it was already built from (spec §7)."""

from halbert_core.context.assembler import ContextAssembler
from halbert_core.intake.budget import CONTEXT_BUDGETS, ModelTier

RECEIPT = (
    "Title: Samba media share\nWhen: 2026-07-14..2026-07-14, 3 turns\n"
    "Started with: set up the samba share\nLast said: restarted smbd.\n"
    "Open loop: verify the mount."
)
RECEIPT_ROW = {"role": "system", "content": f"[Earlier in this subject: {RECEIPT}]"}
PAD = "and the samba config " * 18   # ~380 chars: a realistic ~100-token row


def _turns(n, pad=""):
    rows = []
    for i in range(n):
        rows.append({"role": "user", "content": f"user message number {i} about the share {pad}".strip()})
        rows.append({"role": "assistant", "content": f"assistant reply number {i} about the share {pad}".strip()})
    return rows


def _raw_lines(out):
    return [l for l in out.splitlines() if l.startswith("**user**") or l.startswith("**assistant**")]


class TestBudget:
    def test_medium_and_large_conversation_buckets(self):
        medium = CONTEXT_BUDGETS[ModelTier.MEDIUM]
        large = CONTEXT_BUDGETS[ModelTier.LARGE]
        assert medium.conversation == 1600 and medium.total == 2000
        assert large.conversation == 2400 and large.total == 4000

    def test_six_raw_turns_and_the_receipt_fit_at_medium(self):
        budget = CONTEXT_BUDGETS[ModelTier.MEDIUM].conversation
        out, tokens = ContextAssembler()._format_conversation([RECEIPT_ROW] + _turns(6, PAD), budget)
        assert len(_raw_lines(out)) == 12, out
        assert tokens <= budget
        # the old 800-token bucket could not hold them
        out_old, _ = ContextAssembler()._format_conversation([RECEIPT_ROW] + _turns(6, PAD), 800)
        assert len(_raw_lines(out_old)) < 12


class TestReceiptSlot:
    def test_receipt_row_renders_as_its_own_block_before_the_turns(self):
        out, tokens = ContextAssembler()._format_conversation([RECEIPT_ROW] + _turns(2), 4000)
        assert out.startswith("## Earlier in this subject\n"), out
        assert "Title: Samba media share" in out and "Open loop: verify the mount." in out
        assert "[Earlier in this subject:" not in out
        assert out.index("## Earlier in this subject") < out.index("## Recent Conversation")
        assert "**system**" not in out
        assert len(_raw_lines(out)) == 4 and tokens > 0

    def test_receipt_bypasses_summarisation_for_the_remaining_rows(self):
        rows = _turns(6)  # 12 rows: above should_summarize's threshold of 10
        out_with, _ = ContextAssembler()._format_conversation([RECEIPT_ROW] + rows, 8000)
        out_without, _ = ContextAssembler()._format_conversation(rows, 8000)
        assert len(_raw_lines(out_with)) == 12              # every row raw, oldest first
        assert _raw_lines(out_with)[0].startswith("**user**: user message number 0")
        assert len(_raw_lines(out_without)) < 12            # the old path still compresses
        assert "## Earlier in this subject" not in out_without

    def test_receipt_is_cut_to_fit_a_tiny_budget(self):
        out, tokens = ContextAssembler()._format_conversation([RECEIPT_ROW], 30)
        assert out.startswith("## Earlier in this subject\n")
        assert "Title: Samba" in out
        assert tokens <= 30

    def test_no_receipt_row_is_byte_identical_to_before(self):
        rows = _turns(2)
        out, tokens = ContextAssembler()._format_conversation(rows, 4000)
        assert out.startswith("## Recent Conversation\n")
        assert len(_raw_lines(out)) == 4 and tokens > 0
        assert ContextAssembler()._format_conversation([], 4000) == ("", 0)
        assert ContextAssembler()._format_conversation(rows, 0) == ("", 0)
