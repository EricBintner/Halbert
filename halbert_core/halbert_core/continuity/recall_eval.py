# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Measure recall quality as the thread store grows (handoff R5).

Two pieces here:

``ReceiptIndex`` / ``evaluate`` / ``cumulative_curve`` — retrieval-precision
decay as the store grows. Every score is computed from structured output, so
the numbers are reproducible and a change in them means a change in retrieval.

``question_bank`` / ``answer_prompt`` / ``judge_score`` / ``run_exam`` — the
Hermes compaction-exam protocol (the R5 gate the Consolidator's LLM pass waits
on): questions are generated from the region a consolidation policy will
destroy and cached by content hash so every arm answers the identical exam;
the answerer is closed-book with a forced NOT-IN-CONTEXT option; the judge
sees gold and scores hedged guesses as partial.

No LLM anywhere: every number below is computed from structured output.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from .corpus import PlantedFact, SyntheticThread, generate_corpus

__all__ = [
    "ReceiptIndex", "RecallMetrics", "evaluate", "cumulative_curve", "format_curve",
    # R5 exam protocol
    "LLM_JUDGE_ENABLED", "QuestionRow", "ExamVerdict", "ExamResult",
    "question_bank", "answer_prompt", "judge_score", "run_exam", "context_answerer",
]

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


# ---------------------------------------------------------------------------
# R5 exam protocol — question-bank invariance + closed-book answering
# ---------------------------------------------------------------------------
#
# The Hermes compaction-eval rules this implements:
#   (1) questions come FROM the region the policy will destroy/merge and are
#       cached by content hash — every arm answers the identical exam;
#   (2) the answerer is closed-book with a forced NOT IN CONTEXT option, so
#       hallucination and recall are measured by one instrument;
#   (3) the judge sees gold; a hedged guess scores partial (2 correct /
#       1 partial / 0 wrong).

#: Flag-off hook, never consulted on the deterministic path. An LLM judge —
#: for free-text answer variance a regex cannot score — would sit behind this
#: flag and must route through the model-picker's existing slots, never a new
#: provider path. The synthetic corpus never needs it: ``judge_score`` below
#: is fully programmatic.
LLM_JUDGE_ENABLED = False

#: Hedging vocabulary. Recorded here so the (flag-off) LLM judge and the
#: programmatic judge agree on what "hedged" means; the programmatic judge
#: itself only needs the gold-substring rule.
_HEDGES = ("not in context", "possibly", "maybe", "perhaps", "i think",
           "might be", "not sure", "could be")

QuestionRow = Dict[str, object]


def question_bank(thread_digest: str, facts: Sequence[PlantedFact],
                  cache_dir: Optional[Union[str, Path]] = None) -> List[QuestionRow]:
    """One factual question per planted fact, cached by content digest.

    Template-based, no LLM: each planted fact already carries its question
    and gold. The cache is the invariance guarantee — two calls with the
    same digest return the identical bank (the second from disk), so every
    arm of a policy matrix provably answers the same exam. ``cache_dir=None``
    generates without persisting (single-run use).
    """
    if cache_dir is not None:
        path = Path(cache_dir) / f"questions-{thread_digest[:10]}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    bank: List[QuestionRow] = [
        {"question": f.question, "gold": f.gold, "source_turn": f.source_turn}
        for f in facts
    ]
    if cache_dir is not None:
        path = Path(cache_dir) / f"questions-{thread_digest[:10]}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(bank, indent=2, sort_keys=True), encoding="utf-8")
    return bank


def answer_prompt(context: Union[str, Sequence[str]], question: str) -> str:
    """Closed-book instructions with the forced NOT IN CONTEXT phrasing.

    This is the prompt an LLM answerer arm would receive; the deterministic
    harness answers programmatically, but the protocol — including the forced
    refusal-with-guess option — is defined once, here.
    """
    if not isinstance(context, str):
        context = "\n".join(str(part) for part in context)
    return (
        "Answer the question using ONLY the context below.\n"
        "If the answer is not present in the context, you MUST reply\n"
        "'NOT IN CONTEXT — <your best guess>' — a hedged guess, never a\n"
        "confident answer the context does not support.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}"
    )


def judge_score(gold: str, answer: str) -> int:
    """Programmatic judge: 2 correct / 1 partial / 0 wrong.

    Exact match is correct; gold appearing inside a longer, hedged answer
    ("NOT IN CONTEXT — possibly 47-29 based on the pattern") is partial —
    the knowledge survived but the answerer would not commit; anything else
    is wrong. Free-text variance beyond this is the flag-off LLM judge's
    job, not this harness's.
    """
    if not answer or not gold:
        return 0
    if answer.strip() == gold:
        return 2
    if gold.lower() in answer.lower():
        return 1
    return 0


@dataclass
class ExamVerdict:
    """One question, one answer, one score."""

    question: str
    gold: str
    answer: str
    score: int

    def as_dict(self) -> Dict[str, object]:
        return {"question": self.question, "gold": self.gold,
                "answer": self.answer, "score": self.score}


@dataclass
class ExamResult:
    """Per-question verdicts plus the summary the scorecard reports."""

    verdicts: List[ExamVerdict] = field(default_factory=list)

    def summary(self) -> Dict[str, float]:
        n = len(self.verdicts)
        correct = sum(1 for v in self.verdicts if v.score == 2)
        partial = sum(1 for v in self.verdicts if v.score == 1)
        wrong = sum(1 for v in self.verdicts if v.score == 0)
        refused = sum(1 for v in self.verdicts
                      if v.score == 0 and v.answer.strip().upper().startswith("NOT IN CONTEXT"))
        recall = (2 * correct + partial) / (2 * n) if n else 0.0
        return {"n": n, "correct": correct, "partial": partial, "wrong": wrong,
                "refused": refused, "recall": recall}


def run_exam(questions: Sequence[QuestionRow],
             answer_fn) -> ExamResult:
    """Ask every question against whatever ``answer_fn`` closes the book on.

    ``answer_fn`` receives the bank row and returns a free-text answer; it
    never sees gold — that is the closed-book constraint, and it is why the
    answerer is constructed from the retained context, not from the exam.
    """
    verdicts: List[ExamVerdict] = []
    for row in questions:
        question = row["question"]
        gold = row["gold"]
        answer = answer_fn(row)
        verdicts.append(ExamVerdict(
            question=str(question),
            gold=str(gold),
            answer=answer,
            score=judge_score(str(gold), answer),
        ))
    return ExamResult(verdicts=verdicts)


def context_answerer(context: Union[str, Sequence[str]]):
    """The deterministic closed-book answerer for the synthetic corpus.

    Reads only the retained context it is handed. For a template question
    ("what is the garage keypad code?") it searches the context for the
    planted statement's value and answers it; when the context does not
    contain the statement it refuses with the forced NOT IN CONTEXT option.
    A wrong-but-confident answer is impossible by construction — which is
    why the hallucination half of the instrument only becomes live with an
    LLM answerer arm.
    """
    if not isinstance(context, str):
        context = "\n".join(str(part) for part in context)

    def answer(row: QuestionRow) -> str:
        subject = str(row["question"]).strip().rstrip("?")
        prefix = "what is the "
        if subject.lower().startswith(prefix):
            subject = subject[len(prefix):]
        match = re.search(
            r"\bthe " + re.escape(subject.strip().lower()) + r" is (\d{2}-\d{2})",
            context,
        )
        if match:
            return match.group(1)
        return "NOT IN CONTEXT"

    return answer
