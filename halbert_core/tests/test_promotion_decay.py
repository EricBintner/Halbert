# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-14: recency decays, and a guest's recall is not evidence about them.

- **A01-G2 + bug 2** (fix-first row 21) -- "decay multiplies ranking" was
  a no-op. ``last_recalled_days_ago`` is a SNAPSHOT written at record
  time and reloaded verbatim, and both callers passed ``0.0`` -- so a key
  recalled once, sixty days ago, ranked exactly as if it had been
  recalled today. The half-life constant was decoration.
- **A01 bug 6 + A01-G4** (row 35) -- a guest's recall, or a private-mode
  turn's, persisted promotion evidence: a durable record that these words
  mattered to somebody, keyed to a claim, which "forget me" could not
  reach.
"""

import time

import pytest

from halbert_core.continuity.promotion import (
    HALF_LIFE_DAYS,
    PromotionCandidate,
    PromotionSignals,
    rank_candidates,
)


def _signals(**kw):
    base = dict(recall_count=5, query_diversity=3, recall_days=3, avg_score=0.9)
    base.update(kw)
    sig = PromotionSignals()
    for name, value in base.items():
        setattr(sig, name, value)
    return sig


def test_recency_is_derived_from_the_timestamp_not_the_snapshot():
    now = 1_000_000.0
    sig = _signals()
    sig.last_recalled_at = now - (60 * 86400)
    assert sig.days_since_recall(now) == pytest.approx(60.0)


def test_a_stale_key_ranks_below_a_fresh_one():
    now = 1_000_000.0
    fresh = PromotionCandidate(("a", "b"), _signals())
    stale = PromotionCandidate(("c", "d"), _signals())
    fresh.signals.last_recalled_at = now
    stale.signals.last_recalled_at = now - (60 * 86400)

    ranked = rank_candidates([stale, fresh], limit=2, now=now)
    assert [c.key for c in ranked] == [("a", "b"), ("c", "d")]


def test_the_half_life_actually_halves():
    """Mirrors the origin's calibration: 0.25 at 60 days on a 30-day
    half-life."""
    now = 1_000_000.0
    sig = _signals()
    sig.last_recalled_at = now - (2 * HALF_LIFE_DAYS * 86400)
    import math

    recency = math.exp(
        -math.log(2) / HALF_LIFE_DAYS * sig.days_since_recall(now))
    assert recency == pytest.approx(0.25, abs=0.01)


def test_a_key_with_no_timestamp_falls_back_to_the_snapshot():
    """Rows written before the timestamp was read back keep working."""
    sig = _signals()
    sig.last_recalled_at = 0.0
    sig.last_recalled_days_ago = 7.0
    assert sig.days_since_recall(1_000_000.0) == 7.0


def test_recording_stamps_the_timestamp(tmp_path):
    from halbert_core.continuity.promotion import PromotionStore

    store = PromotionStore(db_path=str(tmp_path / "p.db"))
    before = time.time()
    store.record_recall(("subject", "predicate"), "where is the disk", score=0.8)
    sig = store.signals(("subject", "predicate"))
    assert sig.last_recalled_at >= before


def test_the_timestamp_survives_a_reload(tmp_path):
    from halbert_core.continuity.promotion import PromotionStore

    path = str(tmp_path / "p.db")
    store = PromotionStore(db_path=path)
    store.record_recall(("s", "p"), "a query", score=0.5)
    recorded = store.signals(("s", "p")).last_recalled_at

    reloaded = PromotionStore(db_path=path)
    assert reloaded.signals(("s", "p")).last_recalled_at == pytest.approx(
        recorded, abs=1.0)


# ---------------------------------------------------------------------------
# A01 bug 6 + G5 (fix-first row 35): whose evidence it is
# ---------------------------------------------------------------------------

def test_a_guest_turn_records_no_promotion_evidence(monkeypatch):
    import halbert_core.agents.threads as threads

    monkeypatch.setattr(threads, "_conversation_is_halberts", lambda: False)
    recorded = []

    class _Store:
        def record_recall(self, *a, **kw):
            recorded.append((a, kw))

    import halbert_core.continuity.promotion as promotion
    monkeypatch.setattr(promotion, "get_promotion_store", lambda: _Store())

    manager = threads.ThreadManager.__new__(threads.ThreadManager)
    manager._record_promotion_signal(
        "a query", type("S", (), {"score": 0.9})(), {"thread_id": "t1"})
    assert recorded == [], (
        "a guest's recall must not persist evidence about them"
    )


def test_a_halbert_turn_still_records(monkeypatch):
    import halbert_core.agents.threads as threads

    monkeypatch.setattr(threads, "_conversation_is_halberts", lambda: True)
    recorded = []

    class _Store:
        def record_recall(self, *a, **kw):
            recorded.append((a, kw))

    import halbert_core.continuity.promotion as promotion
    monkeypatch.setattr(promotion, "get_promotion_store", lambda: _Store())

    manager = threads.ThreadManager.__new__(threads.ThreadManager)
    manager._record_promotion_signal(
        "a query", type("S", (), {"score": 0.9})(), {"thread_id": "t1"})
    assert recorded


def test_forget_reaches_the_promotion_tables(tmp_path):
    from halbert_core.continuity.promotion import PromotionStore

    store = PromotionStore(db_path=str(tmp_path / "p.db"))
    store.record_recall(("thread:t1", "recalled"), "a query",
                        request_id="run-1", score=0.8)
    store.record_recall(("thread:t2", "recalled"), "another",
                        request_id="run-2", score=0.8)

    assert store.forget_request("run-1") == 1
    assert store.signals(("thread:t1", "recalled")) is None
    assert store.signals(("thread:t2", "recalled")) is not None


def test_the_companion_tables_go_with_it(tmp_path):
    """A signal row whose query hashes survived would keep contributing
    diversity to a key that is supposed to be gone."""
    from halbert_core.continuity.promotion import PromotionStore

    path = str(tmp_path / "p.db")
    store = PromotionStore(db_path=path)
    store.record_recall(("thread:t1", "recalled"), "q1",
                        request_id="run-1", score=0.8)
    store.forget_request("run-1")

    reloaded = PromotionStore(db_path=path)
    assert reloaded.signals(("thread:t1", "recalled")) is None


def test_the_erasure_limits_mention_the_promotion_tables():
    from halbert_core.continuity.provenance import ERASURE_LIMITS

    assert "promotion" in ERASURE_LIMITS.lower()
