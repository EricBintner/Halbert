# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Measure recall quality as the thread store grows (handoff R5).

Two pieces:

``ReceiptIndex`` — a reference FTS5 index over receipts, matching the shape Plan A
specifies (``receipts_fts``, ``porter unicode61``, query tokenised and quoted with
a LIKE fallback). It stands in for the real search until Plan A merges, and then
becomes the control to compare the real one against.

``evaluate`` / ``cumulative_curve`` — the measurement. No LLM anywhere: every
score is computed from structured output, so the numbers are reproducible and a
change in them means a change in retrieval.

The metric that matters is not hit-rate, which stays high. It is **candidates** —
how many receipts match at all. That is the noise the model must disambiguate,
and it is what grows with the store.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .corpus import SyntheticThread, generate_corpus

__all__ = ["ReceiptIndex", "RecallMetrics", "evaluate", "cumulative_curve", "format_curve"]

_WORD = re.compile(r"[A-Za-z0-9_/.:-]+")


def _tokenise(q: str) -> List[str]:
    return [w for w in _WORD.findall(q or "") if len(w) > 2]


class ReceiptIndex:
    """FTS5 over receipts — the deterministic read path, no LLM."""

    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            "CREATE VIRTUAL TABLE receipts_fts USING fts5("
            "thread_id UNINDEXED, receipt, tokenize='porter unicode61')"
        )

    def add(self, thread_id: str, receipt: str) -> None:
        self._conn.execute(
            "INSERT INTO receipts_fts (thread_id, receipt) VALUES (?, ?)",
            (thread_id, receipt),
        )

    def add_all(self, threads: Sequence[SyntheticThread]) -> None:
        for t in threads:
            self.add(t.thread_id, t.receipt)

    def search(self, query: str, limit: int = 10) -> List[str]:
        """Thread ids best-first. Falls back to LIKE when MATCH cannot parse."""
        return [tid for tid, _ in self.search_scored(query, limit=limit)]

    def search_scored(self, query: str, limit: int = 10) -> List[Tuple[str, float]]:
        """``(thread_id, relevance)`` best-first, relevance higher-is-better.

        SQLite's ``bm25()`` returns a negative number where more negative is a
        better match; it is negated here so callers can reason about a *gap*
        between first and second place without sign confusion. LIKE-fallback
        rows all score 0.0 — no ranking information is available, which
        ``recall_gate`` treats as never strong enough to inject silently.
        """
        tokens = _tokenise(query)
        if not tokens:
            return []
        match = " OR ".join(f'"{t}"' for t in tokens)
        try:
            rows = self._conn.execute(
                "SELECT thread_id, bm25(receipts_fts) AS score FROM receipts_fts "
                "WHERE receipts_fts MATCH ? ORDER BY score LIMIT ?",
                (match, limit),
            ).fetchall()
            return [(r["thread_id"], -float(r["score"])) for r in rows]
        except sqlite3.OperationalError:
            pass
        like = f"%{tokens[0]}%"
        rows = self._conn.execute(
            "SELECT thread_id FROM receipts_fts WHERE receipt LIKE ? LIMIT ?",
            (like, limit),
        ).fetchall()
        return [(r["thread_id"], 0.0) for r in rows]

    def close(self) -> None:
        self._conn.close()


@dataclass
class RecallMetrics:
    """Scores for one corpus size."""

    n: int
    hit_at_1: float
    hit_at_5: float
    mrr: float
    mean_candidates: float
    cross_domain_rate: float

    def as_row(self) -> str:
        return (f"{self.n:>6} | {self.hit_at_1:>7.3f} | {self.hit_at_5:>7.3f} | "
                f"{self.mrr:>6.3f} | {self.mean_candidates:>10.1f} | "
                f"{self.cross_domain_rate:>11.3f}")


def evaluate(
    threads: Sequence[SyntheticThread],
    index: Optional[ReceiptIndex] = None,
    k: int = 5,
    limit: int = 25,
) -> RecallMetrics:
    """Score every thread's own query against the index built from all of them."""
    own = index is None
    if index is None:
        index = ReceiptIndex()
        index.add_all(threads)

    by_id: Dict[str, SyntheticThread] = {t.thread_id: t for t in threads}
    hits1 = hits5 = 0
    rr_total = 0.0
    cand_total = 0
    cross_total = 0
    for t in threads:
        results = index.search(t.query, limit=limit)
        cand_total += len(results)
        if results[:1] == [t.thread_id]:
            hits1 += 1
        if t.thread_id in results[:k]:
            hits5 += 1
            rr_total += 1.0 / (results.index(t.thread_id) + 1)
        # candidates from a different domain than the target: measurable bleed
        cross_total += sum(
            1 for r in results[:k]
            if r in by_id and by_id[r].domain != t.domain
        )
    n = len(threads) or 1
    if own:
        index.close()
    return RecallMetrics(
        n=len(threads),
        hit_at_1=hits1 / n,
        hit_at_5=hits5 / n,
        mrr=rr_total / n,
        mean_candidates=cand_total / n,
        cross_domain_rate=cross_total / (n * k),
    )


def cumulative_curve(sizes: Sequence[int] = (10, 100, 500),
                     seed: int = 1) -> List[RecallMetrics]:
    """Evaluate at each corpus size. This is ATANT's cumulative mode."""
    return [evaluate(generate_corpus(n, seed=seed)) for n in sizes]


def format_curve(rows: Sequence[RecallMetrics]) -> str:
    head = ("     N |   hit@1 |   hit@5 |    MRR | candidates | cross-domain\n"
            "-------+---------+---------+--------+------------+-------------")
    return "\n".join([head] + [r.as_row() for r in rows])
