# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Recall-driven promotion store (OpenClaw short-term-promotion pattern).

Design rules lifted from the review:
- promotion signals are USAGE facts (recall count, distinct queries, distinct days,
  average gate score) — never write-time confidence;
- decay multiplies ranking and never deletes;
- content derived from recalled material never re-enters (provenance guard) —
  "a fact recalled one hundred times stays one fact";
- hard gates (min recall count, min diversity) keep one-off trivia out.

Pure and deterministic: no model, no network. Phase A2 adds persistence to
the continuity state DB and wiring at the two live recall sites.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Optional, Sequence, Tuple

__all__ = [
    "HALF_LIFE_DAYS",
    "MIN_RECALL_COUNT",
    "MIN_QUERY_DIVERSITY",
    "PromotionSignals",
    "PromotionCandidate",
    "PromotionStore",
    "rank_candidates",
]

HALF_LIFE_DAYS = 30.0
MIN_RECALL_COUNT = 3
MIN_QUERY_DIVERSITY = 2

#: A signal key is a ledger claim key: ``(subject, predicate)``. Claim-shaped
#: on purpose (the promotion second-guess verdict) — never a memory-row id.
PromotionKey = Tuple[str, str]


@dataclass
class PromotionSignals:
    recall_count: int = 0
    query_diversity: int = 0
    recall_days: int = 0
    avg_score: float = 0.0
    last_recalled_days_ago: float = 0.0


@dataclass(frozen=True)
class PromotionCandidate:
    key: PromotionKey
    signals: PromotionSignals


def _signal_score(s: PromotionSignals) -> float:
    utility = math.log1p(s.recall_count)
    diversity = s.query_diversity / 5.0
    spread = s.recall_days / 5.0
    recency = math.exp(-math.log(2) / HALF_LIFE_DAYS * s.last_recalled_days_ago)
    return 0.5 * utility + 0.2 * diversity + 0.2 * spread + 0.1 * recency


def rank_candidates(candidates: Sequence[PromotionCandidate], limit: int) -> list:
    eligible = [
        c for c in candidates
        if c.signals.recall_count >= MIN_RECALL_COUNT
        and c.signals.query_diversity >= MIN_QUERY_DIVERSITY
    ]
    ranked = sorted(eligible, key=lambda c: _signal_score(c.signals), reverse=True)
    return ranked[:limit]


class PromotionStore:
    """In-process signal accumulator; snapshots persist to the continuity DB (A2).
    Queries are stored as sha256 so chatty loops can't inflate diversity with
    trivially different strings, and raw user text never lands in the store."""

    def __init__(self):
        self._signals: Dict[PromotionKey, PromotionSignals] = {}
        self._queries: Dict[PromotionKey, set] = {}
        self._days: Dict[PromotionKey, set] = {}

    def record_recall(self, key: PromotionKey, query: str, *, days_ago: float = 0.0,
                      score: float = 0.0, provenance: str = "agent_query") -> None:
        if provenance == "recalled_content":
            return  # recall-loop hygiene: never re-enter
        sig = self._signals.setdefault(key, PromotionSignals())
        sig.recall_count += 1
        self._queries.setdefault(key, set()).add(
            hashlib.sha256(query.encode()).hexdigest()[:16])
        # A recall recorded as ``days_ago`` happened that many days back; the
        # day set must reflect *when*, not when the signal happened to be
        # written, or multi-day recurrence is invisible.
        self._days.setdefault(key, set()).add(date.today() - timedelta(days=days_ago))
        sig.query_diversity = len(self._queries[key])
        sig.recall_days = len(self._days[key])
        # Running average, weighted by the count so a store reloaded from
        # persistence keeps the same mean.
        prev_n = sig.recall_count - 1
        sig.avg_score = ((sig.avg_score * prev_n) + score) / sig.recall_count
        sig.last_recalled_days_ago = days_ago

    def signals(self, key: PromotionKey) -> Optional[PromotionSignals]:
        return self._signals.get(key)