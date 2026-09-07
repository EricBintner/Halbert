# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R5: the consolidation eval harness — arms x synthetic corpus -> exam -> scorecard.

The Consolidator's LLM abstraction pass is deliberately gated off "until the
R5 eval harness confirms" (see consolidation.py). This module is that harness,
after Hermes's compaction eval:

* a recall exam generated FROM the region the policy will destroy/merge,
  cached by content hash so every arm answers the identical exam;
* consolidation under a policy matrix, always including a NO_CONSOLIDATION
  ceiling arm — without it a score has no meaning — and a TRUNCATE_OLDEST
  baseline any LLM arm must beat;
* closed-book answering with a forced NOT IN CONTEXT option, scored by the
  programmatic judge (2 correct / 1 partial / 0 wrong);
* scores reported as recall@retained, never recall alone;
* committed dated scorecards under ``evals/consolidation/``.

This harness is the permanent gate: the LLM arm is defined in the matrix but
printed SKIPPED-GATE-CLOSED until the founder opens it with this harness's
evidence. Nothing here touches consolidation.py or its flag. The whole run is
deterministic — no network, no model calls; the deterministic baseline it
commits is the number the LLM arms will have to beat.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple, Union

from .consolidation import Consolidator
from .corpus import (
    EVAL_DOMAIN_ORDER,
    EvalMessage,
    EvalThread,
    content_digest,
    planted_facts,
    synthetic_thread,
)
from .recall_eval import context_answerer, question_bank, run_exam
from .state_store import StateStore

__all__ = [
    "Retained", "PolicyFailed", "validate_summary", "Arm", "ArmRow",
    "ArmAggregate", "MatrixReport", "verbatim_policy", "truncate_oldest_policy",
    "durable_facts_policy", "llm_summary_policy", "default_arms", "run_matrix",
    "approx_tokens", "main",
]

#: Fixed "now" so the scorecard is reproducible; nothing here touches the
#: wall clock of the machine being evaluated.
_EVAL_NOW = 1_800_000_000.0

#: The R5 gate the LLM arm sits behind. Kept closed here, verbatim: the
#: harness produces the evidence, the founder opens the gate.
LLM_GATE = "closed"


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------


@dataclass
class Retained:
    """What a policy kept of the region, as answerable text."""

    text: str


class PolicyFailed(Exception):
    """A policy could not produce a retained representation.

    Truncated summaries (Hermes's ``_finish_summary`` rule) are *retryable*
    failures: they are recorded as failures, never stored as results, and the
    arm's row says FAILED-RETRYABLE instead of scoring a mangled context.
    """

    def __init__(self, reason: str, *, finish_reason: Optional[str] = None,
                 retryable: bool = True):
        super().__init__(reason)
        self.reason = reason
        self.finish_reason = finish_reason
        self.retryable = retryable


def validate_summary(result: object) -> str:
    """Hermes ``_finish_summary`` rule: a truncated summary is a retryable
    failure, never a stored result."""
    if not isinstance(result, Mapping):
        raise PolicyFailed(
            f"summarizer returned {type(result).__name__}, not a mapping")
    finish = str(result.get("finish_reason") or "")
    if finish != "stop":
        raise PolicyFailed(
            f"truncated summary (finish_reason={finish!r})",
            finish_reason=finish,
        )
    text = str(result.get("text") or "")
    if not text.strip():
        raise PolicyFailed("empty summary", finish_reason=finish)
    return text


def _region_text(region: Sequence[EvalMessage]) -> str:
    return "\n".join(f"{m.role}: {m.content}" for m in region)


def approx_tokens(text: str) -> int:
    """Whitespace-approximate token count — enough to compare arms, documented
    as approximate in every scorecard."""
    return len(text.split())


def verbatim_policy():
    """NO_CONSOLIDATION, the ceiling: the region is kept word for word."""

    def policy(thread: EvalThread, region: Sequence[EvalMessage]) -> Retained:
        return Retained(text=_region_text(region))

    return policy


def truncate_oldest_policy(keep_turns: int = 10):
    """The cheap baseline: keep only the newest ``keep_turns`` turns of the
    region and drop the rest. Any LLM arm must beat this or it is not worth
    its cost."""

    def policy(thread: EvalThread, region: Sequence[EvalMessage]) -> Retained:
        return Retained(text=_region_text(list(region)[-keep_turns:]))

    return policy


def durable_facts_policy(state_store: StateStore):
    """The current deterministic Consolidator as a retention policy: what
    survives of the region is the durable facts the real Consolidator
    records for the thread's domain — entity-level structure, not episodic
    turns. This is exactly what production retains when the raw region is
    dropped after an idle consolidation pass."""

    def policy(thread: EvalThread, region: Sequence[EvalMessage]) -> Retained:
        triples = state_store.current_state(
            subject=f"domain:{thread.domain}", strict=True)
        lines = [
            f"{t.subject} {t.predicate}: {t.object} ({t.reason})"
            for t in triples
        ]
        return Retained(text="\n".join(lines))

    return policy


def llm_summary_policy(summarizer: Optional[Callable[[str], Mapping]]):
    """The LLM arm's policy. ``summarizer`` summarizes the region text and
    MUST return ``{"text": ..., "finish_reason": ...}`` — and, per founder
    rules, must be routed through the model-picker's existing slots, never a
    new provider path. While the R5 gate is closed this policy never runs;
    the runner skips the arm before touching anything model-shaped."""

    def policy(thread: EvalThread, region: Sequence[EvalMessage]) -> Retained:
        if summarizer is None:
            raise PolicyFailed("llm summarizer not configured (gate closed)")
        return Retained(text=validate_summary(summarizer(_region_text(region))))

    return policy


@dataclass
class Arm:
    """One policy in the matrix. ``policy(thread, region)`` receives ONLY the
    region slice — region scoping is enforced by the runner, not by the
    arm, and is pinned by the sentinel test."""

    name: str
    policy: Callable[[EvalThread, Sequence[EvalMessage]], Retained]
    label: str = ""
    gate: str = "open"  # "open" | "closed"


def default_arms(state_store: StateStore) -> List[Arm]:
    """The matrix, ceiling first. The LLM arm is present in the definition —
    the scorecard shows what the gate is holding back — but its gate is
    closed."""
    return [
        Arm(
            name="NO_CONSOLIDATION",
            label="the ceiling — the region is retained verbatim",
            policy=verbatim_policy(),
        ),
        Arm(
            name="CONSOLIDATOR_DETERMINISTIC",
            label="the current deterministic Consolidator's durable facts",
            policy=durable_facts_policy(state_store),
        ),
        Arm(
            name="TRUNCATE_OLDEST",
            label="cheap baseline — keep the newest 10 turns of the region",
            policy=truncate_oldest_policy(keep_turns=10),
        ),
        Arm(
            name="LLM_SUMMARY",
            label="LLM abstraction pass — gated until this harness's "
                  "evidence is reviewed",
            policy=llm_summary_policy(None),
            gate=LLM_GATE,
        ),
    ]


# ---------------------------------------------------------------------------
# Rows, aggregates, report
# ---------------------------------------------------------------------------


@dataclass
class ArmRow:
    """One arm's result on one thread's exam."""

    arm: str
    thread_id: str
    bank_digest: str
    status: str                 # OK | FAILED-RETRYABLE | SKIPPED-GATE-CLOSED
    n_questions: Optional[int] = None
    correct: Optional[int] = None
    partial: Optional[int] = None
    wrong: Optional[int] = None
    recall: Optional[float] = None       # None when nothing was scored
    retained_tokens: Optional[int] = None
    failure: Optional[str] = None
    retryable: bool = False

    def as_dict(self) -> dict:
        return {
            "arm": self.arm, "thread_id": self.thread_id,
            "bank_digest": self.bank_digest, "status": self.status,
            "n_questions": self.n_questions, "correct": self.correct,
            "partial": self.partial, "wrong": self.wrong,
            "recall": self.recall, "retained_tokens": self.retained_tokens,
            "failure": self.failure, "retryable": self.retryable,
        }


@dataclass
class ArmAggregate:
    """One arm's totals across the corpus."""

    arm: str
    label: str
    status: str
    ceiling: bool
    rows: int
    questions: int
    correct: int
    partial: int
    wrong: int
    recall: Optional[float]
    mean_retained_tokens: Optional[float]


@dataclass
class MatrixReport:
    """The whole run: per-thread rows plus the rendered scorecard."""

    rows: List[ArmRow]
    arms: List[Arm]
    n_threads: int
    turns: int
    region: Tuple[int, int]

    def aggregates(self) -> List[ArmAggregate]:
        out: List[ArmAggregate] = []
        labels = {a.name: a.label for a in self.arms}
        order: List[str] = []
        for row in self.rows:
            if row.arm not in order:
                order.append(row.arm)
        for arm_name in order:
            rows = [r for r in self.rows if r.arm == arm_name]
            if all(r.status == "SKIPPED-GATE-CLOSED" for r in rows):
                status = "SKIPPED-GATE-CLOSED"
            elif any(r.status == "FAILED-RETRYABLE" for r in rows):
                status = "FAILED-RETRYABLE"
            else:
                status = "OK"
            scored = [r for r in rows if r.status == "OK"]
            questions = sum(r.n_questions or 0 for r in scored)
            correct = sum(r.correct or 0 for r in scored)
            partial = sum(r.partial or 0 for r in scored)
            wrong = sum(r.wrong or 0 for r in scored)
            tokens = [r.retained_tokens for r in scored
                      if r.retained_tokens is not None]
            out.append(ArmAggregate(
                arm=arm_name,
                label=labels.get(arm_name, ""),
                status=status,
                ceiling=arm_name == "NO_CONSOLIDATION",
                rows=len(rows),
                questions=questions,
                correct=correct,
                partial=partial,
                wrong=wrong,
                recall=(2 * correct + partial) / (2 * questions)
                       if questions else None,
                mean_retained_tokens=(sum(tokens) / len(tokens))
                                       if tokens else None,
            ))
        return out

    # -- rendering ----------------------------------------------------------

    def render(self, date: Optional[str] = None) -> str:
        aggs = self.aggregates()
        r0, r1 = self.region
        # every arm answers the identical exam; count it once, not per arm
        distinct_questions = max((a.questions for a in aggs), default=0)
        runs = sum(a.questions for a in aggs if a.status == "OK")
        lines: List[str] = []
        title = "Consolidation recall scorecard"
        if date:
            title += f" — {date}"
        lines.append(f"# {title}")
        lines.append("")
        lines.append("## Setup")
        lines.append("")
        lines.append(
            f"- Corpus: synthetic, deterministic; {self.n_threads} threads x "
            f"{self.turns} turns; region = turns {r0}..{r1 - 1} — the region "
            "the policies destroy/merge.")
        lines.append(
            f"- Exam: one template question per planted fact inside the region "
            f"({distinct_questions} questions), bank cached by "
            "content digest — every arm answers the identical exam.")
        lines.append(
            "- Answerer: programmatic closed-book with a forced "
            "NOT IN CONTEXT option. No model calls anywhere; the "
            "hallucination half of the instrument becomes a live measurement "
            "only when an LLM arm runs.")
        lines.append(
            "- Judge: programmatic — 2 correct / 1 partial (hedged "
            "gold-substring) / 0 wrong.")
        lines.append(
            "- Scoring: recall@retained. A recall number is never reported "
            "without the tokens the arm retained to get it.")
        lines.append("")
        lines.append("## Arms")
        lines.append("")
        lines.append("| arm | status | questions | correct | partial | wrong "
                      "| recall | retained tokens (mean) |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
        for a in aggs:
            name = f"{a.arm} (ceiling)" if a.ceiling else a.arm
            lines.append(
                f"| {name} | {a.status} | {a.questions} | {a.correct} | "
                f"{a.partial} | {a.wrong} | "
                f"{a.recall:.3f} | {a.mean_retained_tokens:.0f} |"
                if a.status == "OK" else
                f"| {name} | {a.status} | — | — | — | — | — | — |")
        lines.append("")
        lines.append("## Findings")
        lines.append("")
        finding_no = 1
        for a in aggs:
            if a.status == "OK" and a.ceiling:
                lines.append(
                    f"{finding_no}. The ceiling (NO_CONSOLIDATION) answers "
                    f"{a.correct} of {a.questions} at "
                    f"{a.mean_retained_tokens:.0f} retained tokens — the exam "
                    "is answerable from the region; any arm below this is "
                    "losing real information.")
                finding_no += 1
        for a in aggs:
            if a.arm == "CONSOLIDATOR_DETERMINISTIC" and a.status == "OK":
                lines.append(
                    f"{finding_no}. The current deterministic Consolidator "
                    f"retains durable entity facts ({a.mean_retained_tokens:.0f} "
                    f"tokens) and no episodic planted facts — recall "
                    f"{a.recall:.3f}. It was never designed to; the LLM pass "
                    "this harness gates must beat TRUNCATE_OLDEST, not merely "
                    "this arm.")
                finding_no += 1
        for a in aggs:
            if a.arm == "TRUNCATE_OLDEST" and a.status == "OK":
                lines.append(
                    f"{finding_no}. TRUNCATE_OLDEST keeps only the newest "
                    f"planted fact of the region — recall {a.recall:.3f} at "
                    f"{a.mean_retained_tokens:.0f} tokens. It is the cheap "
                    "baseline: an LLM arm that cannot beat it is not worth "
                    "its cost or its risk.")
                finding_no += 1
        for a in aggs:
            if a.status == "SKIPPED-GATE-CLOSED":
                lines.append(
                    f"{finding_no}. {a.arm}: SKIPPED-GATE-CLOSED — the "
                    "Consolidator's LLM flag is untouched; this scorecard is "
                    "the deterministic evidence the gate asks for.")
                finding_no += 1
        for a in aggs:
            if a.status == "FAILED-RETRYABLE":
                lines.append(
                    f"{finding_no}. {a.arm}: FAILED-RETRYABLE — a truncated "
                    "summary is a retryable failure, never a stored result "
                    "(Hermes _finish_summary rule). No score was recorded.")
                finding_no += 1
        lines.append("")
        lines.append("## Caveats")
        lines.append("")
        lines.append(
            f"- n = {distinct_questions} questions over {self.n_threads} threads "
            f"({runs} scored arm-runs of the identical exam); deltas at this "
            "n are noise. These numbers are the deterministic baseline, not "
            "a ranking of arms.")
        lines.append(
            "- The programmatic answerer matches the planted statement "
            "literally, so recall here measures literal retention, not "
            "semantic recall; an LLM arm will be judged on free-text answers.")
        lines.append(
            "- Token counts are whitespace-approximate; they exist to compare "
            "arms, not to budget a context window.")
        lines.append(
            "- The CONSOLIDATOR_DETERMINISTIC arm models production idle "
            "consolidation across the whole corpus: its retained context is "
            "the durable facts the real Consolidator records for the "
            "thread's domain.")
        lines.append(
            "- The LLM judge / LLM answerer hooks are flag-off and route "
            "through the model-picker's existing slots; this run used "
            "neither.")
        lines.append("")
        return "\n".join(lines)

    def jsonl(self) -> str:
        return "\n".join(
            _json_dumps_row(r.as_dict()) for r in self.rows) + "\n"


def _json_dumps_row(d: dict) -> str:
    import json

    return json.dumps(d, sort_keys=True)


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------


def _seed_store(store, threads: Sequence[EvalThread], now: float) -> None:
    """Adapt synthetic threads into closed conversation-store threads so the
    real Consolidator sees exactly the shape production gives it."""
    for t in threads:
        store.create_thread(t.thread_id, f"Eval thread {t.thread_id}",
                            created_at=now)
        store.update_thread(
            t.thread_id,
            topic_domains=[t.domain],
            entities_json=t.entities,
            status="closed",
            updated_at=now,
        )


def run_matrix(
    *,
    threads: Optional[Sequence[EvalThread]] = None,
    seeds: Optional[Sequence[int]] = None,
    turns: int = 40,
    region: Optional[Tuple[int, int]] = None,
    arms: Optional[Sequence[Arm]] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    store=None,
    state_store: Optional[StateStore] = None,
    now: float = _EVAL_NOW,
) -> MatrixReport:
    """Apply every arm to the same corpora and answer the identical exams.

    Deterministic and offline: the only moving parts are the real
    deterministic Consolidator, the synthetic corpus, and the programmatic
    exam. The LLM arm is skipped at its gate before anything model-shaped is
    touched.
    """
    if threads is None:
        if seeds is None:
            seeds = tuple(range(1, 10))  # 9 threads = 3 per eval domain
        threads = [
            synthetic_thread(
                seed=s, turns=turns,
                domain=EVAL_DOMAIN_ORDER[i % len(EVAL_DOMAIN_ORDER)])
            for i, s in enumerate(seeds)
        ]
    threads = list(threads)
    if region is None:
        region = (0, max(1, len(threads[0].messages) // 2))

    # The real stores, in-memory: the Consolidator arm must be the production
    # code path, not a reimplementation of it.
    if store is None:
        # Lazy import: continuity must not grow a module-level edge into the
        # agents package (agents already imports continuity).
        from ..agents.conversation_sqlite import SqliteConversationStore

        store = SqliteConversationStore(":memory:")
    if state_store is None:
        state_store = StateStore(db_path=":memory:")

    _seed_store(store, threads, now)
    Consolidator(store, state_store).consolidate(now=now)

    if arms is None:
        arms = default_arms(state_store)
    arms = list(arms)

    rows: List[ArmRow] = []
    for t in threads:
        region_messages = t.messages[region[0]:region[1]]
        digest = content_digest(region_messages)
        facts = [f for f in planted_facts(t)
                 if region[0] <= f.source_turn < region[1]]
        bank = question_bank(digest, facts=facts, cache_dir=cache_dir)
        for arm in arms:
            rows.append(_run_arm(arm, t, region_messages, bank, digest))

    return MatrixReport(
        rows=rows, arms=arms, n_threads=len(threads),
        turns=len(threads[0].messages), region=region,
    )


def _run_arm(arm: Arm, thread: EvalThread,
             region_messages: Sequence[EvalMessage],
             bank, digest: str) -> ArmRow:
    if arm.gate == "closed":
        return ArmRow(arm=arm.name, thread_id=thread.thread_id,
                      bank_digest=digest, status="SKIPPED-GATE-CLOSED")
    try:
        retained = arm.policy(thread, region_messages)
    except PolicyFailed as e:
        return ArmRow(arm=arm.name, thread_id=thread.thread_id,
                      bank_digest=digest, status="FAILED-RETRYABLE",
                      failure=e.reason, retryable=e.retryable)
    exam = run_exam(bank, context_answerer(retained.text))
    s = exam.summary()
    return ArmRow(
        arm=arm.name, thread_id=thread.thread_id, bank_digest=digest,
        status="OK", n_questions=int(s["n"]), correct=int(s["correct"]),
        partial=int(s["partial"]), wrong=int(s["wrong"]),
        recall=float(s["recall"]) if s["n"] else None,
        retained_tokens=approx_tokens(retained.text),
    )


# ---------------------------------------------------------------------------
# CLI: run the harness, commit the first scorecard
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out_dir = Path(__file__).resolve().parents[2] / "evals" / "consolidation"
    if "--out-dir" in argv:
        out_dir = Path(argv[argv.index("--out-dir") + 1])
    date = datetime.now(timezone.utc).date().isoformat()

    report = run_matrix(seeds=tuple(range(1, 10)), turns=40,
                        cache_dir=out_dir / "cache")

    out_dir.mkdir(parents=True, exist_ok=True)
    scorecard = out_dir / f"SCORECARD-{date}.md"
    scorecard.write_text(report.render(date=date), encoding="utf-8")
    rows_path = out_dir / f"rows-{date}.jsonl"
    rows_path.write_text(report.jsonl(), encoding="utf-8")

    r0, r1 = report.region
    print(f"R5 consolidation eval — synthetic corpus "
          f"({report.n_threads} threads x {report.turns} turns, "
          f"region turns {r0}-{r1 - 1})")
    for a in report.aggregates():
        if a.status == "OK":
            print(f"  {a.arm:<26} recall {a.recall:.3f}  "
                  f"retained ~{a.mean_retained_tokens:.0f} tokens")
        else:
            print(f"  {a.arm:<26} {a.status}")
    print("gate: the Consolidator's LLM pass stays OFF; deterministic "
          "baseline recorded")
    print(f"scorecard: {scorecard}")
    print(f"rows:      {rows_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())