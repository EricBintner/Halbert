# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A8b: the conversation bucket fits six raw turns at MEDIUM, and
the assembler renders a thread receipt in its own slot instead of
re-summarising the history it was already built from (spec §7)."""

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.threads import (
    RECEIPT_ROW_MAX,
    RECEIPT_ROW_PREFIX,
    ThreadManager,
)
from halbert_core.context.assembler import ContextAssembler
from halbert_core.intake.budget import CONTEXT_BUDGETS, ModelTier
from halbert_core.intake.signals import analyze_message

RECEIPT = (
    "Title: Samba media share\nWhen: 2026-07-14..2026-07-14, 3 turns\n"
    "Started with: set up the samba share\nLast said: restarted smbd.\n"
    "Open loop: verify the mount."
)
RECEIPT_ROW = {"role": "system", "content": f"[Earlier in this subject: {RECEIPT}]"}
PAD = "and the samba config " * 18   # ~380 chars: a realistic ~100-token row


def _producer_max_receipt() -> str:
    """A receipt at the size the producer actually allows.

    `threads._history` fences the stored receipt to ``RECEIPT_ROW_MAX``
    chars, ~376 tokens by the assembler's estimator — a quarter of the whole
    MEDIUM conversation bucket and nearly four times TINY's. The tests below
    use this rather than the short RECEIPT: the interesting question is what
    the receipt does to the turns when it is as big as it is allowed to get.
    """
    text = RECEIPT
    while len(text) < RECEIPT_ROW_MAX:
        text += "\nFiles written: /etc/samba/smb.conf, /etc/fstab"
    return text[:RECEIPT_ROW_MAX]


MAX_RECEIPT_ROW = {
    "role": "system",
    "content": f"{RECEIPT_ROW_PREFIX} {_producer_max_receipt()}]",
}


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


class TestReceiptShare:
    """The receipt and the turns share one bucket, and the turns win.

    Fitted first against the whole bucket the receipt inverted the old
    priority: a producer-max receipt evicted every raw turn at TINY and
    SMALL and one of the six at MEDIUM, where the pre-A8b walk had dropped
    the receipt row first and kept the turns (review: Plan A / A8b).
    """

    def test_a_producer_max_receipt_still_leaves_six_raw_turns_at_medium(self):
        budget = CONTEXT_BUDGETS[ModelTier.MEDIUM].conversation
        out, tokens = ContextAssembler()._format_conversation(
            [MAX_RECEIPT_ROW] + _turns(6, PAD), budget
        )
        assert len(_raw_lines(out)) == 12, out
        assert out.startswith("## Earlier in this subject\n")
        assert "Title: Samba media share" in out   # cut down, but still there
        assert tokens <= budget

    @pytest.mark.parametrize(
        "tier,pad",
        [(ModelTier.TINY, ""), (ModelTier.SMALL, ""), (ModelTier.SMALL, PAD)],
    )
    def test_a_producer_max_receipt_never_evicts_the_newest_turn(self, tier, pad):
        budget = CONTEXT_BUDGETS[tier].conversation
        out, tokens = ContextAssembler()._format_conversation(
            [MAX_RECEIPT_ROW] + _turns(6, pad), budget
        )
        raw = _raw_lines(out)
        assert raw, out
        assert raw[-1].startswith("**assistant**: assistant reply number 5")
        assert out.startswith("## Earlier in this subject\n")
        assert tokens <= budget

    def test_a_turn_too_big_for_the_bucket_leaves_the_receipt_the_whole_bucket(self):
        # The one case where no turn survives: a ~100-token turn does not fit
        # in TINY's 100-token bucket with or without a receipt. There is
        # nothing to protect, so the receipt takes the room rather than the
        # assembler returning an empty conversation block.
        budget = CONTEXT_BUDGETS[ModelTier.TINY].conversation
        out, tokens = ContextAssembler()._format_conversation(
            [MAX_RECEIPT_ROW] + _turns(6, PAD), budget
        )
        assert out.startswith("## Earlier in this subject\n")
        assert _raw_lines(out) == []
        assert "Title: Samba media share" in out and tokens <= budget

    def test_a_long_history_does_not_evict_the_receipt(self):
        # The reservation cuts both ways: 20 turns want more than the whole
        # bucket, and the receipt still keeps its floor.
        budget = CONTEXT_BUDGETS[ModelTier.MEDIUM].conversation
        out, tokens = ContextAssembler()._format_conversation(
            [MAX_RECEIPT_ROW] + _turns(20, PAD), budget
        )
        assert out.startswith("## Earlier in this subject\n")
        assert "Title: Samba media share" in out
        assert len(_raw_lines(out)) >= 12       # the newest six turns, raw
        assert tokens <= budget

    def test_the_receipt_may_have_the_bucket_when_there_is_no_turn_to_protect(self):
        budget = CONTEXT_BUDGETS[ModelTier.SMALL].conversation
        out, tokens = ContextAssembler()._format_conversation([MAX_RECEIPT_ROW], budget)
        assert out.startswith("## Earlier in this subject\n")
        assert tokens > budget // 2 and tokens <= budget


class TestProducerContract:
    """One string literal, two modules: pin them together.

    `threads._history` writes the row and `_split_receipt_row` reads it. If
    either side is reworded alone the receipt degrades silently — back into
    the walk as a `**system**:` line, with summarisation switched on over
    the turns the receipt was built to replace — and every isolated test on
    either side still passes.
    """

    def test_the_assembler_splits_the_row_the_thread_manager_writes(self):
        store = SqliteConversationStore(":memory:")
        try:
            manager = ThreadManager(store)
            for i in range(8):
                text = f"step {i} of the samba setup"
                turn = manager.begin_turn(text, analyze_message(text), "s")
                manager.end_turn(
                    turn, assistant_text=f"did step {i}", blocks=[],
                    terminal_session_ids=[], diff_proposals=[],
                )
            history = manager.begin_turn(
                "continue", analyze_message("continue"), "s"
            ).history
        finally:
            store.close()

        assert history[0]["role"] == "system"          # the producer's row
        receipt, rest = ContextAssembler()._split_receipt_row(history)
        assert receipt.startswith("Title: step 0 of the samba setup")
        assert rest == history[1:]

        out, _ = ContextAssembler()._format_conversation(
            history, CONTEXT_BUDGETS[ModelTier.MEDIUM].conversation
        )
        assert out.startswith("## Earlier in this subject\n")
        assert "**system**" not in out
        assert "step 0 of the samba setup" in out.split("## Recent Conversation")[0]
