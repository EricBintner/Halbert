# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A8b: the conversation bucket fits six raw turns at MEDIUM, and
the thread receipt gets its own slot instead of the history being
re-summarised out of what the receipt was already built from (spec §7).

Since the merge the receipt no longer travels through the prose
``_format_conversation`` walk. ``AgentStateMachine._begin_turn`` shapes the
history exactly once per turn (D3): it splits the receipt row off, fits it to
its own allowance out of the shared conversation bucket, parks the rendered
block on ``ctx.thread_receipt_block`` for ``messages[0]``, and spends what is
left of the bucket on the raw turns, which become real ``messages[]`` entries
(E-3). The receipt helpers themselves are module-level functions taking an
explicit counter (D7). Every test below therefore drives that path through
``_shape`` rather than the walk, but asks it the same questions.
"""

import asyncio
import logging
from types import SimpleNamespace

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
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.states import StateContext
from halbert_core.context.assembler import (
    ContextAssembler,
    RECEIPT_HEADER,
    _history_tokens,
    fit_receipt,
    split_receipt_row,
)
from halbert_core.context.tokens import TokenCounter
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


def _receipt_body(block):
    """The rendered receipt, header stripped."""
    assert block.startswith(RECEIPT_HEADER), block
    return block[len(RECEIPT_HEADER):].strip()


COUNTER = TokenCounter()


class _NullLLM:
    """Enough of a client for the machine's constructor; never called."""

    max_tokens = 8192
    temperature = 0.7

    async def chat(self, messages, tools=None, **kwargs):  # pragma: no cover
        raise AssertionError("_begin_turn must not reach the model")

    async def stream(self, messages, **kwargs):  # pragma: no cover
        raise AssertionError("_begin_turn must not reach the model")
        yield ""


class _StubManager:
    """A ThreadManager that hands back exactly the rows under test."""

    def __init__(self, rows):
        self.rows = rows

    def begin_turn(self, text, signals, session_id):
        return SimpleNamespace(
            thread_id="t1", turn_id="turn-1", hint="", recalled=[],
            history=list(self.rows),
        )


def _machine(**ctx_kwargs):
    agent = AgentStateMachine(llm_client=_NullLLM())
    agent.ctx = StateContext(
        session_id="s", request_id="r", user_query="continue", **ctx_kwargs
    )
    return agent


def _shape(rows, budget):
    """``(receipt block, window)`` as a real turn gets them.

    Drives the production path — ``AgentStateMachine._begin_turn`` — rather
    than restating its arithmetic, so a change to how the bucket is split
    fails here instead of quietly diverging from what ships.
    """
    agent = _machine(history_budget=budget, thread_manager=_StubManager(rows))

    async def drive():
        async for _ in agent._begin_turn():
            pass

    asyncio.run(drive())
    return agent.ctx.thread_receipt_block, agent.ctx.conversation_history


def _cost(block, window):
    """What the receipt and the turns together take out of the bucket."""
    return COUNTER.count(block) + _history_tokens(window, COUNTER)


class TestBudget:
    def test_medium_and_large_conversation_buckets(self):
        medium = CONTEXT_BUDGETS[ModelTier.MEDIUM]
        large = CONTEXT_BUDGETS[ModelTier.LARGE]
        assert medium.conversation == 1600 and medium.total == 2000
        assert large.conversation == 2400 and large.total == 4000

    def test_six_raw_turns_and_the_receipt_fit_at_medium(self):
        budget = CONTEXT_BUDGETS[ModelTier.MEDIUM].conversation
        block, window = _shape([RECEIPT_ROW] + _turns(6, PAD), budget)
        assert len(window) == 12, window
        assert block.startswith(RECEIPT_HEADER)
        assert _cost(block, window) <= budget
        # the old 800-token bucket could not hold them
        _, old = _shape([RECEIPT_ROW] + _turns(6, PAD), 800)
        assert len(old) < 12


class TestReceiptSlot:
    def test_receipt_row_renders_as_its_own_block_before_the_turns(self):
        block, window = _shape([RECEIPT_ROW] + _turns(2), 4000)
        assert block.startswith(RECEIPT_HEADER), block
        assert "Title: Samba media share" in block
        assert "Open loop: verify the mount." in block
        assert RECEIPT_ROW_PREFIX not in block
        assert len(window) == 4
        assert not any(m["role"] == "system" for m in window)
        # "before the turns" is array position now: the block rides
        # messages[0] with the instructions and the raw turns follow it.
        messages = _machine(
            thread_receipt_block=block, conversation_history=window
        )._build_messages("INSTRUCTIONS")
        assert messages[0]["role"] == "system"
        assert messages[0]["content"].startswith("INSTRUCTIONS")
        assert RECEIPT_HEADER.strip() in messages[0]["content"]
        assert [m["role"] for m in messages[1:]] == [
            "user", "assistant", "user", "assistant", "user",
        ]

    def test_receipt_bypasses_summarisation_for_the_remaining_rows(self):
        rows = _turns(6)  # 12 rows: above the old message-count threshold
        block, window = _shape([RECEIPT_ROW] + rows, 8000)
        assert len(window) == 12                       # every row raw, oldest first
        assert window[0]["content"].startswith("user message number 0")
        assert not any(m["role"] == "system" for m in window)
        assert block.startswith(RECEIPT_HEADER)
        # Rewritten for the merged contract. The prose walk still compresses,
        # but on main's token watermark (fd9d7fd) rather than the pre-E-3
        # message count this merge briefly reverted it to: twelve one-line
        # turns that fit an 8000-token bucket easily are left whole, and it
        # takes rows that actually fill the bucket to trip it. Either way the
        # walk never sees a receipt — that is what this test is about.
        #
        # These four assertions are the only thing left driving the walk
        # behaviourally, and driving it is all they do: no production caller
        # reaches `_format_conversation` any more (see its docstring). They
        # are green because the walk is correct, not because it runs.
        assembler = ContextAssembler()
        out_small, _ = assembler._format_conversation(rows, 8000)
        assert len(_raw_lines(out_small)) == 12       # a count would have fired
        heavy = _turns(6, PAD * 4)
        out_heavy, _ = assembler._format_conversation(
            heavy, _history_tokens(heavy, COUNTER)   # every row, no headroom
        )
        assert len(_raw_lines(out_heavy)) < 12
        assert RECEIPT_HEADER not in out_small
        assert RECEIPT_HEADER not in out_heavy

    def test_receipt_is_cut_to_fit_a_tiny_budget(self):
        block, window = _shape([RECEIPT_ROW], 30)
        assert block.startswith(RECEIPT_HEADER)
        assert "Title: Samba" in block
        assert _cost(block, window) <= 30

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
        block, window = _shape([MAX_RECEIPT_ROW] + _turns(6, PAD), budget)
        assert len(window) == 12, window
        assert block.startswith(RECEIPT_HEADER)
        assert "Title: Samba media share" in block   # cut down, but still there
        assert _cost(block, window) <= budget

    @pytest.mark.parametrize(
        "tier,pad",
        [(ModelTier.TINY, ""), (ModelTier.SMALL, ""), (ModelTier.SMALL, PAD)],
    )
    def test_a_producer_max_receipt_never_evicts_the_newest_turn(self, tier, pad):
        budget = CONTEXT_BUDGETS[tier].conversation
        block, window = _shape([MAX_RECEIPT_ROW] + _turns(6, pad), budget)
        assert window, block
        assert window[-1]["role"] == "assistant"
        assert window[-1]["content"].startswith("assistant reply number 5")
        assert block.startswith(RECEIPT_HEADER)
        assert _cost(block, window) <= budget

    def test_a_turn_too_big_for_the_bucket_leaves_the_receipt_the_whole_bucket(self):
        # The one case where no turn survives: a ~100-token turn does not fit
        # in TINY's 100-token bucket with or without a receipt. There is
        # nothing to protect, so the receipt takes the room rather than the
        # assembler returning an empty conversation block.
        budget = CONTEXT_BUDGETS[ModelTier.TINY].conversation
        block, window = _shape([MAX_RECEIPT_ROW] + _turns(6, PAD), budget)
        assert block.startswith(RECEIPT_HEADER)
        assert window == []
        assert "Title: Samba media share" in block
        assert _cost(block, window) <= budget

    def test_a_long_history_does_not_evict_the_receipt(self):
        # The reservation cuts both ways: 20 turns want more than the whole
        # bucket, and the receipt still keeps its floor.
        budget = CONTEXT_BUDGETS[ModelTier.MEDIUM].conversation
        block, window = _shape([MAX_RECEIPT_ROW] + _turns(20, PAD), budget)
        assert block.startswith(RECEIPT_HEADER)
        assert "Title: Samba media share" in block
        assert len(window) >= 12                # the newest six turns, raw
        assert _cost(block, window) <= budget

    def test_the_receipt_may_have_the_bucket_when_there_is_no_turn_to_protect(self):
        budget = CONTEXT_BUDGETS[ModelTier.SMALL].conversation
        block, window = _shape([MAX_RECEIPT_ROW], budget)
        assert block.startswith(RECEIPT_HEADER)
        tokens = _cost(block, window)
        assert tokens > budget // 2 and tokens <= budget


class TestProducerContract:
    """One string literal, two modules: pin them together.

    `threads._history` writes the row and `split_receipt_row` reads it. If
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
                    terminal_block_ids=[], diff_proposals=[],
                )
            history = manager.begin_turn(
                "continue", analyze_message("continue"), "s"
            ).history
        finally:
            store.close()

        assert history[0]["role"] == "system"          # the producer's row
        receipt, rest = split_receipt_row(history)
        assert receipt.startswith("Title: step 0 of the samba setup")
        assert rest == history[1:]

        block, window = _shape(
            history, CONTEXT_BUDGETS[ModelTier.MEDIUM].conversation
        )
        assert block.startswith(RECEIPT_HEADER)
        assert not any(m["role"] == "system" for m in window)
        assert "step 0 of the samba setup" in block


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
        assert fit_receipt(NINE_LINE_RECEIPT, 4000, COUNTER) == NINE_LINE_RECEIPT
        assert CUT_MARKER not in NINE_LINE_RECEIPT

    def test_every_cut_is_marked(self):
        for budget in self.BUDGETS:
            body = fit_receipt(NINE_LINE_RECEIPT, budget, COUNTER)
            if not body or body == NINE_LINE_RECEIPT or CUT_MARKER in body:
                continue
            # Unmarked only where the marker itself would not fit — and a
            # whole line beats a mangled one plus a notice that it was
            # mangled, so what is left is still an intact line.
            assert COUNTER.count(f"{CUT_MARKER}\n{body}") > budget, (budget, body)
            assert body in NINE_LINE_RECEIPT.splitlines(), (budget, body)

    def test_a_cut_never_half_quotes_a_line(self):
        """A line is kept whole, dropped, or marked — never silently short."""
        originals = NINE_LINE_RECEIPT.splitlines()
        # `receipt_one_liner`'s digest is three *complete* lines joined by
        # the producer's own function, so it is not a half-quote either.
        digest = receipt_one_liner(NINE_LINE_RECEIPT)
        for budget in self.BUDGETS:
            for line in fit_receipt(
                NINE_LINE_RECEIPT, budget, COUNTER
            ).splitlines():
                assert (
                    line == CUT_MARKER
                    or line in originals
                    or line == digest
                    or line.endswith(CUT_MARKER)
                ), (budget, line)

    def test_a_staged_command_is_never_silently_shortened(self):
        """`rm -rf /srv/media` is not `rm -rf /srv/media/tmp-old-transcodes`."""
        for budget in self.BUDGETS:
            body = fit_receipt(NINE_LINE_RECEIPT, budget, COUNTER)
            if "rm -rf /srv/media" in body:
                assert DANGEROUS_COMMAND in body, (budget, body)

    def test_the_open_loop_survives_whenever_there_is_room_for_it(self):
        floor = COUNTER.count(OPEN_LOOP_LINE)
        for budget in self.BUDGETS:
            body = fit_receipt(NINE_LINE_RECEIPT, budget, COUNTER)
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
        digest = receipt_one_liner(NINE_LINE_RECEIPT)
        used = [
            b for b in self.BUDGETS
            if fit_receipt(NINE_LINE_RECEIPT, b, COUNTER)
            == f"{CUT_MARKER}\n{digest}"
        ]
        assert used, "the one-liner fallback is unreachable at every budget"
        for budget in self.BUDGETS:
            body = fit_receipt(NINE_LINE_RECEIPT, budget, COUNTER)
            if not body or body == NINE_LINE_RECEIPT:
                continue
            if any(ln.startswith(ONE_LINER_LABELS) for ln in body.splitlines()):
                continue
            # Nothing about what happened survived, so the digest must not
            # have fitted either.
            assert COUNTER.count(f"{CUT_MARKER}\n{digest}") > budget, budget

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
        block, window = _shape([NINE_LINE_ROW] + _turns(6, pad), budget)
        body = _receipt_body(block)
        assert body.splitlines()[-1].startswith(OPEN_LOOP_LABEL), (tier, body)
        if DANGEROUS_COMMAND.split("/srv")[0] in body:
            assert DANGEROUS_COMMAND in body, (tier, body)
        assert _cost(block, window) <= budget


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


class TestMergeSeam:
    """Two things the merge broke where Plan A's receipt met main's array.

    Both are silent: no exception, no failing assertion anywhere else, just a
    model that remembers badly.
    """

    def test_a_long_turn_survives_whatever_the_receipt_costs(self):
        """The allowance must bill the turns the way the window spends them.

        ``receipt_allowance`` measured them with the prose renderer, which
        caps a row at 1000 chars, while ``build_conversation_window`` charges
        it whole — the two were one measurer until the merge moved the
        consumer. One long answer reads as ~260 prose tokens and ~1287 real
        ones, so the receipt was handed room the turns needed and the window
        came back EMPTY: the single outcome the allowance's cap exists to
        make impossible.
        """
        budget = CONTEXT_BUDGETS[ModelTier.MEDIUM].conversation
        long_turn = [
            {"role": "user", "content": "what did the transcode job print?"},
            {"role": "assistant", "content": "and the samba config " * 245},
        ]
        block, window = _shape([MAX_RECEIPT_ROW] + long_turn, budget)
        assert [m["role"] for m in window] == ["user", "assistant"]
        assert window[-1]["content"].startswith("and the samba config")
        assert block.startswith(RECEIPT_HEADER)
        assert "Title: Samba media share" in block
        assert _cost(block, window) <= budget

    def test_the_soft_landing_note_reaches_the_instructions(self):
        """A subject change sends the previous subject's last turns, and the
        row that says so must travel with them.

        ``threads._soft_landing`` prefixes those six rows with '[Previous
        subject "X", kept for one turn only; it is not the current task]'.
        It is a leading *system* row, and every path out of
        ``build_conversation_window`` opens on a user one — so it was dropped
        silently and the model read six rows of the old subject as the new
        one (review: merge seam).
        """
        note = ('[Previous subject "Samba media share", kept for one turn '
                'only; it is not the current task]')
        rows = [{"role": "system", "content": note}] + _turns(3)
        block, window = _shape(rows, CONTEXT_BUDGETS[ModelTier.MEDIUM].conversation)

        assert not any(m["role"] == "system" for m in window)
        assert [m["role"] for m in window] == ["user", "assistant"] * 3
        assert "it is not the current task" in block

        messages = _machine(
            thread_receipt_block=block, conversation_history=window
        )._build_messages("INSTRUCTIONS")
        assert messages[0]["role"] == "system"
        assert "it is not the current task" in messages[0]["content"]
        assert "Samba media share" in messages[0]["content"]
