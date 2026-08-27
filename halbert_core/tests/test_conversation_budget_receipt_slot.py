# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A8b: the conversation bucket fits six raw turns at MEDIUM, and
the assembler renders a thread receipt in its own slot instead of
re-summarising the history it was already built from (spec §7)."""

import logging

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.receipt import (
    CUT_MARKER,
    ONE_LINER_LABELS,
    OPEN_LOOP_LABEL,
    receipt_one_liner,
)
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


#: A receipt the shape `agents.receipt.build_receipt` actually emits: nine
#: labelled lines, with a `Commands:` line carrying a command whose meaning
#: changes if it is cut short (`rm -rf /srv/media/tmp-old-transcodes` ->
#: `rm -rf /srv/media`) and an `Open loop:` line the producer reserves.
NINE_LINE_RECEIPT = "\n".join([
    "Title: Samba media share",
    "When: 2026-07-14..2026-07-16 \u00b7 7 turns",
    "Domains: file sharing, storage",
    "Entities: smbd, /srv/media, /etc/samba/smb.conf, nas-01, media-rw",
    "Started with: set up a samba share for the media library on the NAS",
    "Last said: The share mounts read-write from the laptop now.",
    "Commands: testparm -s (exit 0); systemctl restart smbd (exit 0); "
    "rm -rf /srv/media/tmp-old-transcodes (exit 0)",
    "Files written: /etc/samba/smb.conf; /etc/fstab; /srv/media/.hidden",
    "Open loop: verify the mount survives a reboot.",
])
NINE_LINE_ROW = {
    "role": "system",
    "content": f"{RECEIPT_ROW_PREFIX} {NINE_LINE_RECEIPT}]",
}
DANGEROUS_COMMAND = "rm -rf /srv/media/tmp-old-transcodes"
OPEN_LOOP_LINE = NINE_LINE_RECEIPT.splitlines()[-1]


def _turns(n, pad=""):
    rows = []
    for i in range(n):
        rows.append({"role": "user", "content": f"user message number {i} about the share {pad}".strip()})
        rows.append({"role": "assistant", "content": f"assistant reply number {i} about the share {pad}".strip()})
    return rows


def _raw_lines(out):
    return [l for l in out.splitlines() if l.startswith("**user**") or l.startswith("**assistant**")]


def _receipt_body(out):
    """The rendered receipt, header stripped, turns dropped."""
    header = "## Earlier in this subject\n"
    assert out.startswith(header), out
    return out.split("## Recent Conversation")[0][len(header):].strip()


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


class TestReceiptCut:
    """What survives a cut is an operational question, not a cosmetic one.

    The character tail-cut this replaced deleted `Open loop:` — the line
    `build_receipt` reserves precisely because it is the most important one
    — and stopped mid-string inside `Commands:` / `Files written:`, turning
    `rm -rf /srv/media/tmp-old-transcodes` into `rm -rf /srv/media`: valid,
    different, and with no marker to say it had been shortened (review:
    Plan A / A8b).
    """

    #: Every budget from "one token" to "the whole receipt and then some",
    #: so no band between the ladder's rungs goes unchecked.
    BUDGETS = range(1, 200)

    def test_an_uncut_receipt_is_returned_whole_and_unmarked(self):
        assembler = ContextAssembler()
        assert assembler._fit_receipt(NINE_LINE_RECEIPT, 4000) == NINE_LINE_RECEIPT
        assert CUT_MARKER not in NINE_LINE_RECEIPT

    def test_every_cut_is_marked(self):
        assembler = ContextAssembler()
        for budget in self.BUDGETS:
            body = assembler._fit_receipt(NINE_LINE_RECEIPT, budget)
            if not body or body == NINE_LINE_RECEIPT or CUT_MARKER in body:
                continue
            # Unmarked only where the marker itself would not fit — and a
            # whole line beats a mangled one plus a notice that it was
            # mangled, so what is left is still an intact line.
            assert assembler.tokens.count(f"{CUT_MARKER}\n{body}") > budget, (budget, body)
            assert body in NINE_LINE_RECEIPT.splitlines(), (budget, body)

    def test_a_cut_never_half_quotes_a_line(self):
        """A line is kept whole, dropped, or marked — never silently short."""
        assembler = ContextAssembler()
        originals = NINE_LINE_RECEIPT.splitlines()
        # `receipt_one_liner`'s digest is three *complete* lines joined by
        # the producer's own function, so it is not a half-quote either.
        digest = receipt_one_liner(NINE_LINE_RECEIPT)
        for budget in self.BUDGETS:
            for line in assembler._fit_receipt(NINE_LINE_RECEIPT, budget).splitlines():
                assert (
                    line == CUT_MARKER
                    or line in originals
                    or line == digest
                    or line.endswith(CUT_MARKER)
                ), (budget, line)

    def test_a_staged_command_is_never_silently_shortened(self):
        """`rm -rf /srv/media` is not `rm -rf /srv/media/tmp-old-transcodes`."""
        assembler = ContextAssembler()
        for budget in self.BUDGETS:
            body = assembler._fit_receipt(NINE_LINE_RECEIPT, budget)
            if "rm -rf /srv/media" in body:
                assert DANGEROUS_COMMAND in body, (budget, body)

    def test_the_open_loop_survives_whenever_there_is_room_for_it(self):
        assembler = ContextAssembler()
        floor = assembler.tokens.count(OPEN_LOOP_LINE)
        for budget in self.BUDGETS:
            body = assembler._fit_receipt(NINE_LINE_RECEIPT, budget)
            if budget >= floor:
                assert OPEN_LOOP_LINE in body, (budget, body)
            elif body:
                # Below that it is cut like anything else — but marked, and
                # it is still the line that is kept.
                assert body.endswith(CUT_MARKER), (budget, body)
                assert OPEN_LOOP_LINE.startswith(body[:-1].rstrip()), (budget, body)

    def test_a_metadata_only_prefix_falls_back_to_the_digest(self):
        """`Title`/`When`/`Domains`/`Entities` say nothing about what happened.

        Where the leading lines would fill the room with metadata alone and
        `receipt_one_liner`'s digest fits in the same room, the digest wins.
        """
        assembler = ContextAssembler()
        digest = receipt_one_liner(NINE_LINE_RECEIPT)
        used = [
            b for b in self.BUDGETS
            if assembler._fit_receipt(NINE_LINE_RECEIPT, b) == f"{CUT_MARKER}\n{digest}"
        ]
        assert used, "the one-liner fallback is unreachable at every budget"
        for budget in self.BUDGETS:
            body = assembler._fit_receipt(NINE_LINE_RECEIPT, budget)
            if not body or body == NINE_LINE_RECEIPT:
                continue
            if any(ln.startswith(ONE_LINER_LABELS) for ln in body.splitlines()):
                continue
            # Nothing about what happened survived, so the digest must not
            # have fitted either.
            assert assembler.tokens.count(f"{CUT_MARKER}\n{digest}") > budget, budget

    @pytest.mark.parametrize(
        "tier,pad",
        [
            (ModelTier.TINY, PAD),
            (ModelTier.SMALL, ""),
            (ModelTier.SMALL, PAD),
            (ModelTier.MEDIUM, PAD),
        ],
    )
    def test_a_real_receipt_keeps_its_open_loop_at_every_tier(self, tier, pad):
        budget = CONTEXT_BUDGETS[tier].conversation
        out, tokens = ContextAssembler()._format_conversation(
            [NINE_LINE_ROW] + _turns(6, pad), budget
        )
        body = _receipt_body(out)
        assert body.splitlines()[-1].startswith(OPEN_LOOP_LABEL), (tier, body)
        if DANGEROUS_COMMAND.split("/srv")[0] in body:
            assert DANGEROUS_COMMAND in body, (tier, body)
        assert tokens <= budget


class TestBucketsBelowOneItem:
    """MEDIUM's non-conversation buckets are now smaller than one item.

    A8b's Step 3 funds the conversation bucket out of the others, and at
    MEDIUM three of them end up below the cost of a single length-capped
    item: `observations=75` against a 500-char cap (~134 tokens once the
    header is counted) drops a realistic `systemctl status` whole. The
    budget trade itself is a plan-level decision (spec §7 / A10's num_ctx),
    not the assembler's to make — but it is recorded here, and the drop is
    logged rather than silent (review: Plan A / A8b).
    """

    OBSERVATION = "systemctl status smbd: " + ("active (running) since Tue; " * 22)

    def test_a_realistic_observation_does_not_fit_at_medium(self, caplog):
        assert len(self.OBSERVATION) > 500
        budget = CONTEXT_BUDGETS[ModelTier.MEDIUM].observations
        assembler = ContextAssembler()
        assert assembler.tokens.count(self.OBSERVATION[:500]) > budget
        with caplog.at_level(logging.INFO, logger="halbert.context.assembler"):
            assert assembler._format_observations([self.OBSERVATION], budget) == ("", 0)
        assert any("observations" in r.getMessage() for r in caplog.records), caplog.text

    def test_a_short_observation_still_fits_at_medium(self):
        budget = CONTEXT_BUDGETS[ModelTier.MEDIUM].observations
        out, tokens = ContextAssembler()._format_observations(["smbd is running"], budget)
        assert "smbd is running" in out and 0 < tokens <= budget
