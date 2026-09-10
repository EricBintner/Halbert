# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Recall-driven promotion, lifted from OpenClaw short-term-promotion-record.ts +
short-term-promotion.ts: memory graduates because it kept being USEFUL (recalled),
not because it was written confidently. Pure and deterministic."""
import time
import pytest

from halbert_core.continuity.promotion import (
    PromotionSignals, PromotionStore, rank_candidates, PromotionCandidate,
)

def _recalled(query="how is the scanner set up", days=0, score=0.8):
    return {"event": "recall", "query": query, "days_ago": days, "score": score}

def test_counts_and_query_diversity():
    store = PromotionStore()
    key = ("subject:scanner", "predicate:config")
    store.record_recall(key, query="how is the scanner set up")
    store.record_recall(key, query="how is the scanner set up")  # same query: count rises, diversity doesn't
    store.record_recall(key, query="scanner keeps dropping off wifi")
    sig = store.signals(key)
    assert sig.recall_count == 3
    assert sig.query_diversity == 2
    assert sig.recall_days == 1  # all same day

def test_multi_day_recurrence_counts():
    store = PromotionStore()
    key = ("subject:printer", "predicate:state")
    store.record_recall(key, query="printer status", days_ago=3)
    store.record_recall(key, query="printer offline again", days_ago=1)
    assert store.signals(key).recall_days == 2

def test_recalled_content_cannot_reenter():
    # the recall-loop rule: entries derived from recalled content never produce signals
    store = PromotionStore()
    key = ("subject:door", "predicate:code")
    store.record_recall(key, query="door code", provenance="recalled_content")
    assert store.signals(key) is None

def test_ranking_uses_utility_not_confidence():
    often_used_low_score = PromotionCandidate(
        key=("subject:a", "predicate:p"), signals=PromotionSignals(recall_count=7, query_diversity=4, recall_days=3, avg_score=0.5))
    written_once_high_score = PromotionCandidate(
        key=("subject:b", "predicate:p"), signals=PromotionSignals(recall_count=1, query_diversity=1, recall_days=1, avg_score=0.95))
    ranked = rank_candidates([often_used_low_score, written_once_high_score], limit=1)
    assert ranked[0].key == ("subject:a", "predicate:p")

def test_gates_block_noise():
    one_hit = PromotionCandidate(
        key=("subject:c", "predicate:p"), signals=PromotionSignals(recall_count=1, query_diversity=1, recall_days=1, avg_score=0.9))
    assert rank_candidates([one_hit], limit=5) == []  # min recall count not met

def test_decay_is_a_ranking_multiplier_never_a_delete():
    # Decay only ever lowers a candidate's rank among eligible candidates; it
    # never removes one. (Both candidates here pass the hard gates, so this
    # isolates the recency multiplier — see test_gates_block_noise for the
    # one-off trivia those gates exclude.)
    #
    # A01-G7 added the origin's four calibrated gates, and the fixture had
    # to grow to clear them: four distinct phrasings on four distinct days
    # with a real relevance score is what "a durable fact" looks like on
    # the scale MIN_SCORE was fitted to. The old fixture -- three recalls,
    # all on one day, score 0.0 -- was noise by the origin's own bands,
    # and asserting a ranking order over it was asserting the order of
    # things that should not have been ranked at all.
    store = PromotionStore()
    old_key = ("subject:old", "predicate:p")
    fresh_key = ("subject:fresh", "predicate:p")
    phrasings = ("first phrasing", "second phrasing",
                 "third phrasing", "fourth phrasing")
    for key, offset in ((old_key, 10), (fresh_key, 0)):
        # Newest last, so ``last_recalled_at`` ends up at the offset.
        for step, phrasing in zip((3, 2, 1, 0), phrasings):
            store.record_recall(key, query=phrasing,
                                days_ago=offset + step, score=0.9)
    ranked = rank_candidates(
        [PromotionCandidate(key=old_key, signals=store.signals(old_key)),
         PromotionCandidate(key=fresh_key, signals=store.signals(fresh_key))],
        limit=5)
    # the stale one is still present, ranked lower than the fresh equal signal
    assert [c.key for c in ranked] == [fresh_key, old_key]

    # ...and "never a delete" said precisely: a key aged past the promotion
    # window keeps its signal. The gate refuses to promote it; nothing
    # erases it, and a recall tomorrow makes it a candidate again.
    ancient = ("subject:ancient", "predicate:p")
    for step, phrasing in zip((3, 2, 1, 0), phrasings):
        store.record_recall(ancient, query=phrasing,
                            days_ago=90 + step, score=0.9)
    assert store.signals(ancient) is not None
    assert rank_candidates(
        [PromotionCandidate(key=ancient, signals=store.signals(ancient))],
        limit=5) == []
