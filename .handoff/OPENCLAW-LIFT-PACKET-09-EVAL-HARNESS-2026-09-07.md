# OPENCLAW-LIFT-PACKET-09 — The R5 eval harness + the red-seam probe battery

**Series:** Hermes-derived packet 4 of 4 (master plan: `OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md`)
**Source research:** `.handoff/OSS-REVIEW-HERMES-2026-09-07.md` §9
**Hermes source of record:** `/Volumes/Thunderbolt/AI/OSS/hermes-agent/evals/compaction/` (runner.py, SCORECARD-2026-08-15.md, test_region_scoping.py, fixtures.py), `evals/postmortem/` (probe batteries), `hermes_cli/goals.py` (`judge_goal` gates-before-judge), `agent/background_review.py`
**Executor tier:** Phase A (harness skeleton + synthetic fixtures) — medium, well-specified. Phase B (probe battery) is mechanical but long — splittable per-seam. Phase C (CRAG judge) small.
**Status:** READY TO DISPATCH (Phase A/B independent of the Consolidator LLM work itself — the harness is built to measure it while the gate stays closed)

---

## Objective

Two open Halbert problems get Hermes-proven blueprints in this packet:

1. **The R5 gate.** Halbert's memory `Consolidator` LLM pass is deliberately gated off "until the R5 eval harness confirms" (verified: `continuity/consolidation.py` docstring). Hermes's compaction eval is the harness to copy: a recall exam generated **from the region the policy will destroy**, cached by content hash so every arm answers the identical exam; consolidation under a policy matrix; closed-book answering with a forced "NOT IN CONTEXT" option; an LLM judge that sees gold and scores hedged guesses as partial; a **ceiling control arm** (without it, a score has no meaning — Hermes found 96.7% uncompacted vs 45.8% for their shipped default); committed dated scorecards; a synthetic-transcript fixture so the harness itself smoke-tests in CI without LLMs; and the explicit posture: **"harness as the permanent gate."**
2. **The 38 red seams.** Hermes's postmortem probe battery: reviewer-authored defect reproductions as standalone scripts where pass = exit 0 + an expected stdout marker, run side-by-side against base/branch checkouts via a PROBES table. No framework.

Plus the smaller C: the `judge_goal` structure for CRAG-style state-machine gating (deterministic gates short-circuit the LLM judge).

## Verified current state (do not re-derive; verified 2026-09-07)

- The gated Consolidator: `halbert_core/halbert_core/continuity/consolidation.py` — `Consolidator.consolidate(now=...)` is wired (end of every idle `ThreadManager.tick()`, threads.py:655-661), batches closed threads by domain (≥3 threads in 7 days), records recurring entities into `StateStore` as durable facts, **no LLM pass** (docstring: gated behind a flag until the R5 eval harness confirms).
- Eval-only machinery already present: `continuity/recall_eval.py` (`ReceiptIndex`, `evaluate`), `continuity/corpus.py` (`generate_corpus`) — no production callers; natural home for this harness's fixtures and scoring.
- The red seams: 38 known red tests on main from a past review (REV-06 seams; recorded in session memory and the worktree-lessons handoff — the executor must **collect the current list empirically** at Phase B start, not trust a number).
- Test invocation: `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/ -q`; worktrees need `arch -arm64 ./wt_pytest.py` (the venv editable-install trap).

## Out-of-scope guards

- This packet builds the **harness**, not the Consolidator LLM pass. The flag stays off; the harness's first deliverable is a dated scorecard of the *deterministic* baseline so the LLM arms have something to beat.
- No new eval framework, no pytest plugins — Hermes's discipline is ~15 self-contained batteries with a shared house style; Halbert starts with ONE battery following that style.
- Do not judge with an LLM where a programmatic oracle exists (Hermes rule, adopted wholesale).
- The probe battery pins **defects**, not features — a probe reproduces a seam's failure on the broken revision and passes on the fixed one. If a seam's cause is unclear, write the probe as "reproduce the observed symptom" and mark it observational; don't debug in this packet.

---

## Phase A — the consolidation recall harness (the R5 gate)

**Branch:** `feat/eval-harness` off `main`.

### Task A1: The synthetic-transcript fixture (CI-runnable, no LLM)

**Files:**
- Create: `halbert_core/halbert_core/continuity/eval_corpus.py` (extend, or colocate with `corpus.py` — read `corpus.py` first and extend rather than parallel-file)
- Test: `halbert_core/tests/continuity/test_eval_corpus.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Hermes fixtures.py pattern: a deterministic synthetic corpus with planted
facts every N turns, so the harness itself is CI-testable without models."""
import hashlib
from halbert_core.halbert_core.continuity import eval_corpus

def test_deterministic():
    a = eval_corpus.synthetic_thread(seed=7, turns=40)
    b = eval_corpus.synthetic_thread(seed=7, turns=40)
    assert a == b
    c = eval_corpus.synthetic_thread(seed=8, turns=40)
    assert a != c

def test_facts_planted_every_ten_turns():
    thread = eval_corpus.synthetic_thread(seed=7, turns=40)
    facts = eval_corpus.planted_facts(thread)
    assert len(facts) >= 4  # one fact per 10 turns
    assert all(f.source_turn % 10 == 0 for f in facts)

def test_facts_recoverable_from_text():
    thread = eval_corpus.synthetic_thread(seed=7, turns=40)
    facts = eval_corpus.planted_facts(thread)
    assert all(f.statement in thread.messages[f.source_turn].content for f in facts)
```

- [ ] **Step 2: Run, verify failure.** **Step 3: Implement** — `synthetic_thread(seed, turns)` builds a deterministic thread of plausible conversation messages (mix of domains: scanner, printer, HA devices — matching the ledger's real subject vocabulary so FTS/tokenization behaves like production) with a distinctive planted fact (`"the garage keypad code is 47-29"`, numbered variants) every 10th turn; `PlantedFact(statement, source_turn)`; content hashing helper.

- [ ] **Step 4: Run, verify pass. Commit:** `feat(continuity): deterministic synthetic eval corpus with planted facts`

### Task A2: Question-bank invariance + the closed-book exam

**Files:**
- Create: `halbert_core/halbert_core/continuity/eval_recall.py`
- Test: `halbert_core/tests/continuity/test_eval_recall.py`

- [ ] **Step 1: Write the failing tests**

```python
"""The exam protocol (Hermes compaction eval):
(1) questions are generated FROM the to-be-destroyed/merged region and cached by
content hash — every policy answers the identical exam;
(2) the answerer is closed-book with a forced NOT_IN_CONTEXT option (measures
hallucination and recall in one instrument);
(3) the judge sees gold; a correct guess is scored partial (hedging measured)."""
import json
from halbert_core.halbert_core.continuity import eval_recall

def test_bank_cached_by_content_hash(tmp_path):
    thread_digest = "a" * 64
    bank = eval_recall.question_bank(thread_digest, facts=[...], cache_dir=tmp_path)
    bank2 = eval_recall.question_bank(thread_digest, facts=[...], cache_dir=tmp_path)
    assert (tmp_path / f"questions-{thread_digest[:10]}.json").exists()
    assert bank == bank2  # second call served from cache

def test_answer_forced_not_in_context_option():
    prompt = eval_recall.answer_prompt([], question="what is the garage keypad code?")
    assert "NOT IN CONTEXT" in prompt

def test_judge_scores_partial_for_hedged_guess():
    verdict = eval_recall.judge_score(
        gold="47-29", answer="NOT IN CONTEXT — possibly 47-29 based on the pattern")
    assert verdict == 1  # 2 correct / 1 partial / 0 wrong

def test_judge_scores_correct():
    assert eval_recall.judge_score(gold="47-29", answer="47-29") == 2
```

- [ ] **Step 2: Run, verify failure.** **Step 3: Implement** — `question_bank(thread_digest, facts, cache_dir)`: deterministically generate one factual question per planted fact (template-based, no LLM needed for the synthetic corpus — "what is X?" per fact; record `gold` per question), cached as `questions-<digest10>.json`. `answer_prompt(context, question)`: closed-book instructions with the forced `NOT IN CONTEXT — <best guess>` phrasing. `judge_score(gold, answer)`: programmatic first (exact match → 2; gold-substring in answer with hedging markers → 1; else 0) — the LLM judge is only for free-text variance, behind a flag, and the synthetic corpus doesn't need it. `run_exam(questions, answer_fn)` → per-question verdicts + summary.

- [ ] **Step 4: Run, verify pass. Commit:** `feat(continuity): recall exam protocol with question-bank invariance and hedged-guess scoring`

### Task A3: The policy matrix + ceiling arm + scorecard

**Files:**
- Create: `halbert_core/halbert_core/continuity/eval_consolidation.py` (the runner: arms × corpus → exam → scorecard)
- Test: `halbert_core/tests/continuity/test_eval_consolidation.py`
- Output: `halbert_core/evals/consolidation/SCORECARD-<date>.md` (committed, dated, methodology caveats included — the Hermes house style)

- [ ] **Step 1: Write the failing tests:**

```python
"""Arms: (1) NO_CONSOLIDATION — the ceiling; (2) current deterministic
Consolidator; (3) TRUNCATE_OLDEST — a cheap baseline any LLM arm must beat.
Scores are recall@retained, never recall alone. Region scoping is pinned by a
sentinel test (Hermes test_region_scoping.py)."""
def test_arms_answer_identical_exam():
    ...  # same bank hash across arms
def test_ceiling_arm_defined():
    ...  # NO_CONSOLIDATION present and scored first in the report
def test_region_scoping_sentinel():
    ...  # plant sentinels head/middle/tail; the consolidator input contains ONLY the expected region
def test_truncated_summary_is_a_failure_not_a_result():
    ...  # a summarizer that returns finish_reason=length-style truncation is a retryable failure, never stored (Hermes _finish_summary rule)
```

- [ ] **Step 2: Run, verify failure.** **Step 3: Implement** the runner: for each arm × seed corpus: apply the policy → measure retained tokens → answer the identical bank closed-book → score → append rows. Scorecard rendering: per-arm recall@tokens table, findings numbered, caveats ("n = ...; deltas at this n are noise"), ceiling printed first. The `Consolidator`'s LLM flag remains untouched — arm 3 (LLM) is present in the matrix definition but **marked SKIPPED-GATE-CLOSED** in the scorecard until the founder opens it with this harness's evidence.

- [ ] **Step 4: Run, verify pass; run the runner on the synthetic corpus; commit the first scorecard.** Commit: `feat(continuity): consolidation eval harness with ceiling arm — first scorecard committed`

## Phase B — the red-seam probe battery

**Files:**
- Create: `halbert_core/probes/` (a directory of standalone scripts + `PROBES.md`)
- Test: none as pytest — the probes ARE the tests; a `test_probe_registry.py` that asserts every listed probe runs and exits 0 **on current main** (probes that reproduce FIXED defects pass on main; the registry documents the broken-at revision per probe)

- [ ] **Step 1 (collect, don't trust):** Run the full suite and empirically collect the current red list: `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/ -q 2>&1 | tail -50`. Record the actual failing tests and their seams (the historical count was 38 REV-06 seams; the number today may differ — write down what you see).
- [ ] **Step 2:** For each seam, a standalone probe script: minimal reproduction outside pytest (direct module calls), emitting one `PROBE <id>: <result>` line; pass = exit 0 + expected marker. `PROBES.md` = the table: `probe script → seam → observed-on revision → status (fixed-red-on-main / still-red / observational)`. Probes that are still red on main are **recorded, not fixed** — the battery documents state; fixing is separate work.
- [ ] **Step 3:** `test_probe_registry.py` runs every probe and asserts the registry's claimed status matches reality — so the battery can't rot silently.
- [ ] **Step 4:** Commit: `test(probes): red-seam probe battery with self-checking registry`

## Phase C — the CRAG judge contract (small)

- [ ] Port `judge_goal`'s shape into `halbert_core/halbert_core/continuity/verdict.py`: a `verdict(claims, gates)` function where **deterministic gates run first and short-circuit** (a failing gate's bounded output becomes the continuation prompt; no judge is spent), a closed vocabulary (`DONE / BLOCKED / CONTINUE / WAIT` with an optional structured wait directive), judge prompt language requiring specific evidence, and failure-mode separation (parse-failure circuit breaker vs transport-failure fail-open-to-CONTINUE). Tests for each rule. Commit: `feat(continuity): gates-before-judge verdict contract for CRAG evaluation`. Wiring into the state machine's CRAG path is **not** this packet — the contract lands for the retrieval-gating deep pass to consume.

## Verification gates (whole packet)

- `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/continuity -q` green; the harness runs end-to-end on the synthetic corpus **with no network and no model calls** (Phase A is fully deterministic; the LLM judge hook exists but is flag-off).
- A committed, dated scorecard exists with the ceiling arm first and the LLM arm explicitly SKIPPED-GATE-CLOSED.
- The probe registry test passes on main; every still-red seam is listed in PROBES.md with status observational, and nothing in the packet "fixes" tests to make them green (that would defeat the battery's purpose).
- The Consolidator's LLM flag is untouched (`git diff` shows no consolidation.py change).

## Executor gotchas

- Standard set: arch-arm64 pytest; `wt_pytest.py` in worktrees; pathspec commits; no co-author trailers.
- `recall_eval.py` and `corpus.py` already exist eval-only — READ them first and extend; a parallel duplicate would be exactly the sprawl this program avoids. If they're unusable as-is, say so in the handoff and supersede them explicitly.
- The scorecard is a committed artifact in a new `halbert_core/evals/` tree following the Hermes house style (README with methodology + caveats, dated scorecards, raw rows as JSONL). Do not put it under `docs/` (gitignored).
- LLM-judge calls, if ever enabled, must go through the model-picker's existing slots — never a new provider path; and per founder rules, the utility-slot work is pending (PACKET-06's references) — the judge can use the existing specialist slot config until then.