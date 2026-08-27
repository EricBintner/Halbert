# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The margin gate turns silent wrong recalls into questions.

Spec §6 injects the top receipt with no model call whenever a search returns a
hit. At 500 threads that top hit is wrong 37% of the time, and the mistake is
invisible. These tests pin both the arithmetic and the measured effect.
"""

import pytest

from halbert_core.continuity.corpus import generate_corpus
from halbert_core.continuity.recall_eval import ReceiptIndex
from halbert_core.continuity.recall_gate import (
    DEFAULT_MARGIN,
    GateResult,
    MatchStrength,
    classify,
)


class TestClassify:
    def test_no_results_is_none_not_an_error(self):
        r = classify([])
        assert r.strength is MatchStrength.NONE
        assert r.thread_id is None and r.candidates == []

    def test_single_result_is_strong(self):
        r = classify([("t1", 8.0)])
        assert r.strength is MatchStrength.STRONG
        assert r.thread_id == "t1" and r.gap == 1.0

    def test_clear_winner_is_strong(self):
        r = classify([("t1", 10.0), ("t2", 5.0)], margin=0.15)
        assert r.strength is MatchStrength.STRONG
        assert r.thread_id == "t1"
        assert r.gap == pytest.approx(0.5)

    def test_near_tie_is_weak_and_offers_candidates(self):
        r = classify([("t1", 10.0), ("t2", 9.8), ("t3", 9.5)], margin=0.15)
        assert r.strength is MatchStrength.WEAK
        assert r.thread_id is None
        assert r.candidates == ["t1", "t2", "t3"]
        assert r.gap == pytest.approx(0.02)

    def test_exactly_at_the_margin_is_strong(self):
        r = classify([("t1", 10.0), ("t2", 8.5)], margin=0.15)
        assert r.strength is MatchStrength.STRONG

    def test_margin_zero_restores_the_old_behaviour(self):
        r = classify([("t1", 10.0), ("t2", 9.99)], margin=0.0)
        assert r.strength is MatchStrength.STRONG

    def test_unranked_like_fallback_is_never_strong(self):
        """A LIKE hit carries no ranking information, so it is not confidence."""
        r = classify([("t1", 0.0), ("t2", 0.0)])
        assert r.strength is MatchStrength.WEAK

    def test_candidates_are_capped(self):
        scored = [(f"t{i}", 10.0 - i * 0.01) for i in range(10)]
        assert len(classify(scored, max_candidates=3).candidates) == 3

    def test_should_inject_matches_strength(self):
        assert classify([("t1", 9.0)]).should_inject is True
        assert classify([("t1", 10.0), ("t2", 9.9)]).should_inject is False
        assert classify([]).should_inject is False


def _measure(n, margin):
    """Returns (strong_correct, silent_wrong, asked) as fractions."""
    corpus = generate_corpus(n)
    idx = ReceiptIndex()
    idx.add_all(corpus)
    correct = wrong = asked = 0
    for t in corpus:
        g = classify(idx.search_scored(t.query, limit=25), margin=margin)
        if g.strength is MatchStrength.STRONG:
            if g.thread_id == t.thread_id:
                correct += 1
            else:
                wrong += 1
        else:
            asked += 1
    idx.close()
    total = len(corpus)
    return correct / total, wrong / total, asked / total


class TestMeasuredEffect:
    def test_ungated_recall_is_wrong_a_third_of_the_time_at_500(self):
        """The problem, pinned. Remove the gate and this is what ships."""
        _, wrong, _ = _measure(500, margin=0.0)
        assert wrong > 0.30

    def test_the_gate_eliminates_silent_wrong_recalls_at_500(self):
        _, wrong, _ = _measure(500, margin=DEFAULT_MARGIN)
        assert wrong == 0.0

    def test_the_gate_eliminates_silent_wrong_recalls_at_100(self):
        _, wrong, _ = _measure(100, margin=DEFAULT_MARGIN)
        assert wrong == 0.0

    def test_small_stores_keep_almost_all_their_silent_injects(self):
        """The gate must not tax the common case: a young store still injects."""
        correct, wrong, _ = _measure(100, margin=DEFAULT_MARGIN)
        assert correct >= 0.95 and wrong == 0.0

    def test_what_the_gate_costs_is_questions_not_answers(self):
        """At 500 the traffic moves to the weak path, which still holds the
        right thread — hit@5 is 0.996 (see test_recall_eval)."""
        correct, wrong, asked = _measure(500, margin=DEFAULT_MARGIN)
        assert asked > 0.55
        assert correct + wrong + asked == pytest.approx(1.0)


class TestChosenThreshold:
    """DEFAULT_MARGIN is 0.15 because this is what the sweep showed."""

    def test_it_is_the_most_conservative_value_that_costs_nothing_at_100(self):
        safe, _, _ = _measure(100, margin=DEFAULT_MARGIN)
        costly, _, _ = _measure(100, margin=0.20)
        assert safe >= 0.95, "0.15 should not tax a young store"
        assert costly < safe, "0.20 should visibly start costing injects"

    def test_a_smaller_margin_buys_nothing_extra(self):
        loose, loose_wrong, _ = _measure(500, margin=0.05)
        chosen, chosen_wrong, _ = _measure(500, margin=DEFAULT_MARGIN)
        assert loose_wrong == chosen_wrong == 0.0
        assert abs(loose - chosen) < 0.02, "0.05 gains no accuracy over 0.15"
