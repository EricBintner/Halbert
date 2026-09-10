# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-14 Phase C: the gates the origin calibrated, and three hygiene rows.

- **A01-G7**: the origin's gate block carries its calibration in a comment
  -- 3-day/3-query durable facts score 0.750-0.756, repeated filler
  0.489-0.549, high-relevance one-offs 0.529-0.606 -- and then sets
  MIN_SCORE 0.75, MIN_RECALL_COUNT 3, MIN_UNIQUE_QUERIES 3, MAX_AGE_DAYS
  30, with diversity as ``max(unique_queries, recall_days)``. Halbert kept
  two of the four, halved the diversity floor, and counted queries alone.
  No handoff records a decision to drop the rest, which is what makes it a
  gap rather than a difference: the numbers came from measurement and
  arrived here without it.
- **A01-G11**: the query hash is taken over the raw string, so "Printer
  Status", "printer status" and "  printer   status " are three distinct
  queries. Two of those clear a diversity floor of 2 from one intent --
  and the docstring said the hash existed to stop exactly that.
- **A01-G12**: ``date.fromisoformat`` runs inside the single try that wraps
  the whole load, so one malformed day row disables persistence for the
  process AND leaves a half-loaded store: keys already read back looked
  present with zeroed signals rather than absent.
- **A01-G13**: nothing prunes a signal whose claim no longer exists.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import date, timedelta

import pytest

from halbert_core.continuity.promotion import (
    MAX_AGE_DAYS,
    MIN_QUERY_DIVERSITY,
    MIN_RECALL_COUNT,
    MIN_SCORE,
    PromotionCandidate,
    PromotionSignals,
    PromotionStore,
    context_diversity,
    normalize_query,
    rank_candidates,
)

KEY = ("printer", "status")


def _signals(**kw) -> PromotionSignals:
    base = dict(recall_count=4, query_diversity=3, recall_days=3,
                avg_score=0.8, last_recalled_at=time.time())
    base.update(kw)
    return PromotionSignals(**base)


def _candidate(**kw) -> PromotionCandidate:
    return PromotionCandidate(key=KEY, signals=_signals(**kw))


# ---------------------------------------------------------------------------
# A01-G7 — the four gates
# ---------------------------------------------------------------------------

class TestTheGatesMatchTheOrigin:
    def test_the_thresholds_are_the_calibrated_ones(self):
        assert MIN_RECALL_COUNT == 3
        assert MIN_QUERY_DIVERSITY == 3
        assert MIN_SCORE == 0.75
        assert MAX_AGE_DAYS == 30

    def test_a_durable_fact_promotes(self):
        assert rank_candidates([_candidate()], limit=5)

    def test_too_few_recalls_is_refused(self):
        assert rank_candidates([_candidate(recall_count=2)], limit=5) == []

    def test_too_little_diversity_is_refused(self):
        assert rank_candidates(
            [_candidate(query_diversity=1, recall_days=1)], limit=5) == []

    def test_diversity_is_the_greater_of_queries_and_days(self):
        """The origin's ``max(uniqueQueries, recallDays.length)``. Asking
        the same question on three different days is three pieces of
        evidence about durability; counting queries alone throws two of
        them away."""
        assert context_diversity(_signals(query_diversity=1, recall_days=3)) == 3
        assert context_diversity(_signals(query_diversity=3, recall_days=1)) == 3
        assert rank_candidates(
            [_candidate(query_diversity=1, recall_days=3)], limit=5)

    def test_a_stale_key_is_refused_however_often_it_was_recalled(self):
        now = time.time()
        old = _candidate(recall_count=50,
                         last_recalled_at=now - (MAX_AGE_DAYS + 1) * 86400)
        assert rank_candidates([old], limit=5, now=now) == []

    def test_a_key_just_inside_the_age_window_survives(self):
        """The age gate does not remove it. Whether it then clears the
        score bar is the score's business -- at 29 days the recency term
        has more than halved, so the candidate here is one strong enough
        to survive on its other evidence."""
        now = time.time()
        strong = _candidate(recall_count=10, query_diversity=4, recall_days=4,
                            avg_score=1.0,
                            last_recalled_at=now - (MAX_AGE_DAYS - 1) * 86400)
        assert rank_candidates([strong], limit=5, now=now)

    def test_a_low_scoring_key_is_refused(self):
        """Filler that clears the counts still has to clear the bar the
        counts were calibrated against."""
        weak = _candidate(recall_count=3, query_diversity=3, recall_days=3,
                          avg_score=0.0)
        ranked = rank_candidates([weak], limit=5)
        from halbert_core.continuity.promotion import promotion_score

        assert promotion_score(weak.signals) < MIN_SCORE
        assert ranked == []

    def test_the_gates_are_all_of_not_any_of(self):
        assert rank_candidates(
            [_candidate(recall_count=2, query_diversity=9, recall_days=9)],
            limit=5) == []

    def test_the_limit_still_applies(self):
        many = [PromotionCandidate(key=(f"s{i}", "p"), signals=_signals())
                for i in range(10)]
        assert len(rank_candidates(many, limit=3)) == 3


# ---------------------------------------------------------------------------
# A01-G11 — one intent is one query
# ---------------------------------------------------------------------------

class TestQueryNormalisation:
    def test_case_and_whitespace_fold_together(self):
        assert (normalize_query("Printer Status")
                == normalize_query("printer status")
                == normalize_query("  printer   status "))

    def test_three_spellings_of_one_question_are_one_query(self):
        store = PromotionStore()
        for text in ("Printer Status", "printer status", "  printer   status "):
            store.record_recall(KEY, text)
        signals = store.signals(KEY)
        assert signals.recall_count == 3
        assert signals.query_diversity == 1, (
            "three spellings of one intent used to clear the diversity floor "
            "on their own")

    def test_genuinely_different_questions_still_count_separately(self):
        store = PromotionStore()
        store.record_recall(KEY, "is the printer online")
        store.record_recall(KEY, "why is the printer jammed")
        assert store.signals(KEY).query_diversity == 2

    def test_an_empty_query_is_still_a_recall(self):
        store = PromotionStore()
        store.record_recall(KEY, "")
        assert store.signals(KEY).recall_count == 1


# ---------------------------------------------------------------------------
# A01-G12 — one bad row is one bad row
# ---------------------------------------------------------------------------

class TestAMalformedRowIsSkipped:
    def _store_with_bad_day(self, tmp_path):
        path = str(tmp_path / "state.db")
        store = PromotionStore(db_path=path)
        store.record_recall(KEY, "is the printer online")
        store.close()
        conn = sqlite3.connect(path)
        conn.execute(
            "INSERT INTO promotion_recall_days (subject, predicate, day) "
            "VALUES ('other', 'claim', '2026-9-1')")
        conn.commit()
        conn.close()
        return path

    def test_persistence_survives_one_bad_day(self, tmp_path):
        path = self._store_with_bad_day(tmp_path)
        store = PromotionStore(db_path=path)
        assert store._conn is not None, (
            "one malformed row used to disable persistence for the process")
        store.close()

    def test_the_good_row_reloads_intact(self, tmp_path):
        """Worse than reported: the first SELECT loop had already
        populated ``_signals`` when the third raised, so a previously
        persisted key came back with zeroed counts rather than being
        absent -- a store that looks loaded and is not."""
        path = self._store_with_bad_day(tmp_path)
        store = PromotionStore(db_path=path)
        signals = store.signals(KEY)
        assert signals is not None
        assert signals.recall_count == 1
        assert signals.query_diversity == 1
        store.close()

    def test_the_bad_row_is_simply_not_there(self, tmp_path):
        path = self._store_with_bad_day(tmp_path)
        store = PromotionStore(db_path=path)
        assert store.signals(("other", "claim")) is None
        store.close()

    def test_a_genuinely_unopenable_store_still_degrades_to_memory(self, tmp_path):
        bad = tmp_path / "not-a-db"
        bad.write_bytes(b"this is not a database" * 100)
        store = PromotionStore(db_path=str(bad))
        assert store._conn is None
        store.record_recall(KEY, "still recorded")
        assert store.signals(KEY).recall_count == 1


# ---------------------------------------------------------------------------
# A01-G13 — a signal for a claim that no longer exists
# ---------------------------------------------------------------------------

class TestDanglingSignals:
    def test_a_dangling_key_is_dropped_at_rank_time(self):
        live = {("printer", "status")}
        candidates = [
            PromotionCandidate(("printer", "status"), _signals()),
            PromotionCandidate(("removed", "claim"), _signals()),
        ]
        ranked = rank_candidates(candidates, limit=5, is_live=live.__contains__)
        assert [c.key for c in ranked] == [("printer", "status")]

    def test_no_predicate_means_no_filtering(self):
        candidates = [PromotionCandidate(("removed", "claim"), _signals())]
        assert rank_candidates(candidates, limit=5)

    def test_a_predicate_that_raises_does_not_lose_the_sweep(self):
        """A liveness check that cannot answer is not a licence to promote
        and not a reason to promote nothing: the key is kept, and the
        failure is a log line."""
        def _boom(_key):
            raise RuntimeError("state store unavailable")

        candidates = [PromotionCandidate(("printer", "status"), _signals())]
        assert rank_candidates(candidates, limit=5, is_live=_boom)


# ---------------------------------------------------------------------------
# A01-G9 — the two events, and A01-G1 which is not built
# ---------------------------------------------------------------------------

class TestTheEvents:
    def test_a_recorded_recall_appends_a_timeline_event(self, monkeypatch):
        appended = []
        monkeypatch.setattr(
            "halbert_core.continuity.timeline.append_event",
            lambda *a, **k: appended.append((a, k)), raising=False)
        store = PromotionStore()
        store.record_recall(KEY, "is the printer online")
        assert appended, "no recall.recorded event"
        assert any("recall" in str(entry) for entry in appended)

    def test_a_ranking_sweep_appends_one_event(self, monkeypatch):
        appended = []
        monkeypatch.setattr(
            "halbert_core.continuity.timeline.append_event",
            lambda *a, **k: appended.append((a, k)), raising=False)
        rank_candidates([_candidate()], limit=5, emit_events=True)
        assert any("promotion" in str(entry) for entry in appended)

    def test_a_sweep_that_finds_nothing_says_so(self, monkeypatch):
        appended = []
        monkeypatch.setattr(
            "halbert_core.continuity.timeline.append_event",
            lambda *a, **k: appended.append((a, k)), raising=False)
        rank_candidates([_candidate(recall_count=1)], limit=5, emit_events=True)
        assert appended, "a sweep that promoted nothing recorded nothing"

    def test_events_are_off_by_default(self, monkeypatch):
        """The ranker is called from tests and from a future consumer; an
        event per call from a pure function would be a surprise."""
        appended = []
        monkeypatch.setattr(
            "halbert_core.continuity.timeline.append_event",
            lambda *a, **k: appended.append((a, k)), raising=False)
        rank_candidates([_candidate()], limit=5)
        assert appended == []

    def test_a_failing_timeline_never_costs_the_sweep(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("ledger unavailable")

        monkeypatch.setattr(
            "halbert_core.continuity.timeline.append_event", _boom,
            raising=False)
        assert rank_candidates([_candidate()], limit=5, emit_events=True)


def test_the_ranker_still_has_no_production_consumer():
    """A01-G1 is founder-gated (FD-22), and this records that rather than
    letting it be rediscovered.

    Phase B is where the ranked candidates would feed the curated core,
    and it touches the R9 fence and the Haloysius coexistence question.
    The gate stands, so the ranker is deliberately unwired -- and if
    someone wires it, this test says out loud that a decision was skipped.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "halbert_core"
    callers = []
    for path in root.rglob("*.py"):
        if path.name == "promotion.py":
            continue
        if re.search(r"\brank_candidates\s*\(", path.read_text(
                encoding="utf-8", errors="replace")):
            callers.append(str(path.relative_to(root)))
    assert callers == [], (
        "rank_candidates has a production caller; FD-22's Phase-B "
        f"coexistence checkpoint has to be cleared first: {callers}")
