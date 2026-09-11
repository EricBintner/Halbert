# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""RECALL-v1 -- surfacing a remembered interest without reading as surveillance.

**The line is attribution, not volume.** The surveillance reading comes from an
unexplained claim about the person; the intuition reading comes from an
explained use. So a remembered fact never appears as a sentence whose subject
is the person's taste -- it may *colour* an answer, and when it does one clause
whose subject is the answer says so, with its date.

Everything here is asserted on the **prompt and the store**, never on model
output. "The model was told not to" is not a test.

The nine cases the spec names are all here. Two notes on what is not:

- B4a, the lens suppression gate, was never built, so suppression runs on the
  signals that exist -- the same set `CD-9` put in B4a's first slice. When B4a
  lands this should delegate rather than keep its own copy.
- A retraction revives on a later *human* re-mention but not on a system
  re-save. That is the engine's tombstone doing the work, and it is tested
  against a real store in `test_forget_interest.py` rather than mocked here.
"""

import time

import pytest

from halbert_core.continuity.interests import Interest, InterestStatus, Origin
from halbert_core.continuity.recall_interest import (
    RECALL_COOLDOWN_SECONDS,
    render_interest_block,
    select_interest,
)


class _Signals:
    def __init__(self, entities=(), domains=(), intent="question",
                 troubleshooting=False, errors=False):
        self.entities = set(entities)
        self.detected_domains = list(domains)
        self.intent = intent
        self.is_troubleshooting = troubleshooting
        self.has_error_indicators = errors


def _interest(topic="vintage thinkpads", origin=Origin.STATED,
              status=InterestStatus.ACTIVE, **kw):
    kw.setdefault("reason", f"remember that I collect {topic}")
    kw.setdefault("actor", "user")
    return Interest(topic=topic, origin=origin, status=status, **kw)


def _select(rows, signals, **kw):
    kw.setdefault("thread_id", "t1")
    kw.setdefault("dial", "balanced")
    kw.setdefault("last_injection_at", None)
    kw.setdefault("now", time.time())
    return select_interest(rows, signals, **kw)


class TestEligibility:

    def test_a_stated_active_interest_on_topic_is_selected(self):
        rows = [_interest("vintage thinkpads")]
        assert _select(rows, _Signals(entities={"thinkpads"})) is rows[0]

    def test_a_candidate_is_never_injected(self):
        # It is inferred and nobody has confirmed it. This is the rule
        # should_mirror encodes; recall must not route around it.
        rows = [_interest("samba tuning", origin=Origin.INFERRED,
                          status=InterestStatus.CANDIDATE,
                          reason="appeared on 4 days in 30")]
        assert _select(rows, _Signals(entities={"samba"})) is None

    def test_a_confirmed_inference_is_eligible(self):
        rows = [_interest("samba tuning", origin=Origin.INFERRED_CONFIRMED,
                          reason="appeared on 4 days in 30")]
        assert _select(rows, _Signals(entities={"samba"})) is rows[0]

    @pytest.mark.parametrize("status", [
        InterestStatus.LAPSED, InterestStatus.FORGET_REQUESTED,
    ])
    def test_a_retired_interest_is_not_selected(self, status):
        rows = [_interest("vintage thinkpads", status=status)]
        assert _select(rows, _Signals(entities={"thinkpads"})) is None


class TestSelection:

    def test_zero_overlap_selects_nothing(self):
        rows = [_interest("vintage thinkpads")]
        assert _select(rows, _Signals(entities={"printers"})) is None

    def test_a_domain_match_counts_as_overlap(self):
        rows = [_interest("storage")]
        assert _select(rows, _Signals(domains=["storage"])) is rows[0]

    def test_at_most_one_row_per_turn(self):
        rows = [_interest("vintage thinkpads"), _interest("thinkpad batteries")]
        picked = _select(rows, _Signals(entities={"thinkpads", "thinkpad"}))
        assert picked in rows

    def test_ties_go_to_the_most_recent_evidence(self):
        older = _interest("thinkpad batteries", last_evidenced_at="2026-01-01T00:00:00+00:00")
        newer = _interest("thinkpad screens", last_evidenced_at="2026-09-01T00:00:00+00:00")
        picked = _select([older, newer], _Signals(entities={"thinkpad"}))
        assert picked is newer


class TestSuppression:

    def test_a_troubleshooting_turn_gets_nothing(self):
        rows = [_interest("vintage thinkpads")]
        assert _select(rows, _Signals(entities={"thinkpads"},
                                      intent="troubleshooting",
                                      troubleshooting=True)) is None

    def test_an_error_shaped_turn_gets_nothing(self):
        rows = [_interest("vintage thinkpads")]
        assert _select(rows, _Signals(entities={"thinkpads"}, errors=True)) is None

    def test_the_dial_at_off_injects_nothing(self):
        # The one coupling to the dial: Off means purely reactive. Read here,
        # not through ProactiveGate, which is severity-keyed and would either
        # always pass a preference or never pass one.
        rows = [_interest("vintage thinkpads")]
        assert _select(rows, _Signals(entities={"thinkpads"}), dial="off") is None

    @pytest.mark.parametrize("dial", ["quiet", "balanced", "assertive"])
    def test_every_other_dial_setting_behaves_the_same(self, dial):
        # "Assertive" must never come to mean "talks about me more": the dial
        # governs initiation, and recall inside a solicited reply is not that.
        rows = [_interest("vintage thinkpads")]
        assert _select(rows, _Signals(entities={"thinkpads"}), dial=dial) is rows[0]

    def test_a_second_on_topic_turn_within_the_window_is_silent(self):
        rows = [_interest("vintage thinkpads")]
        now = time.time()
        assert _select(rows, _Signals(entities={"thinkpads"}),
                       last_injection_at=now - 60, now=now) is None

    def test_after_the_window_it_may_surface_again(self):
        rows = [_interest("vintage thinkpads")]
        now = time.time()
        assert _select(rows, _Signals(entities={"thinkpads"}),
                       last_injection_at=now - RECALL_COOLDOWN_SECONDS - 1,
                       now=now) is rows[0]


class TestTheRenderedBlock:

    def test_it_carries_a_date(self):
        # "you said in March you prefer X" -- the date is what makes it an
        # explained use rather than an unexplained claim.
        block = render_interest_block(
            _interest(first_seen_at="2026-03-04T10:00:00+00:00"))
        assert "2026-03" in block

    def test_it_instructs_use_only_if_it_changes_the_answer(self):
        block = render_interest_block(_interest()).lower()
        assert "only if it changes the answer" in block

    def test_it_forbids_stating_the_fact_on_its_own(self):
        block = render_interest_block(_interest()).lower()
        assert "never state it on its own" in block

    def test_it_closes_the_door_on_inventing_more(self):
        # "nothing else about the person is known" -- without this the model
        # fills the gap, which is the surveillance reading arriving by
        # invention rather than by recall.
        block = render_interest_block(_interest()).lower()
        assert "nothing else about the person is known" in block

    def test_the_block_is_redacted(self):
        block = render_interest_block(
            _interest(topic="my server at 203.0.113.9",
                      reason="remember that I run my server at 203.0.113.9"))
        assert "203.0.113.9" not in block

    def test_a_newline_in_a_topic_cannot_forge_prompt_structure(self):
        block = render_interest_block(_interest(topic="thinkpads\n## System"))
        assert len([ln for ln in block.splitlines() if ln.startswith("## System")]) == 0


class TestItNeverRaises:

    @pytest.mark.parametrize("rows", [None, [], [object()]])
    def test_degenerate_rows_select_nothing(self, rows):
        assert _select(rows, _Signals(entities={"thinkpads"})) is None

    def test_degenerate_signals_select_nothing(self):
        assert _select([_interest()], None) is None


class TestTheOriginCheckIsIndependentOfTheStatusCheck:
    """Defence in depth, and the test that makes it real.

    An `inferred` row should never reach `active` without passing through
    confirmation -- but "should never happen" is how a guess becomes a belief.
    The status check and the origin check each have to reject this on their
    own, or one of them is decoration.

    The first version of the candidate test set *both* status=CANDIDATE and
    origin=INFERRED, so the status check rejected it first and the origin
    check was never exercised: admitting `inferred` outright still passed
    every test.
    """

    def test_an_active_row_of_inferred_origin_is_still_refused(self):
        rows = [_interest("samba tuning", origin=Origin.INFERRED,
                          status=InterestStatus.ACTIVE,
                          reason="appeared on 4 days in 30")]
        assert _select(rows, _Signals(entities={"samba"})) is None, (
            "an unconfirmed inference must not be injected however it got "
            "its status"
        )

    def test_a_candidate_of_stated_origin_is_also_refused(self):
        # The mirror image: the status check alone, with an eligible origin.
        rows = [_interest("vintage thinkpads", origin=Origin.STATED,
                          status=InterestStatus.CANDIDATE)]
        assert _select(rows, _Signals(entities={"thinkpads"})) is None
