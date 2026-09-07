# Consolidation evals (R5 — the harness that gates the Consolidator's LLM pass)

Halbert's memory `Consolidator` has a deliberately gated-off LLM abstraction
pass (`halbert_core/halbert_core/continuity/consolidation.py` docstring: "An
LLM abstraction pass is the natural next step but is gated behind a flag
until the eval harness (R5) confirms the pattern"). This directory is that
harness's output of record. The harness itself lives in
`halbert_core/halbert_core/continuity/eval_consolidation.py`, with the
fixture in `continuity/corpus.py` and the exam protocol in
`continuity/recall_eval.py`.

The design follows the Hermes compaction eval, and the posture is the same:
**the harness is the permanent gate.** A scorecard here is the evidence the
founder reads before opening any gate; the LLM arm appears in every
scorecard's matrix as `SKIPPED-GATE-CLOSED` until it is opened with this
harness's own numbers.

## How a run works

1. **Corpus** — deterministic synthetic transcripts
   (`corpus.synthetic_thread`): 9 threads x 40 turns in the ledger's real
   subject vocabulary (scanner, printer, HA devices), with a distinctive
   planted fact ("the garage keypad code is 47-29"-style) every 10th turn.
   Same seed, same corpus — a change in a number is a change in a policy,
   never in the fixture.
2. **Region** — the part of each thread the policies would destroy/merge:
   turns 0..19 by default. Questions are generated FROM this region, and
   every arm's policy receives ONLY this region (pinned by a sentinel test).
3. **Exam** — one template question per planted fact inside the region,
   banked and cached by the region's content digest
   (`recall_eval.question_bank`), so every arm provably answers the
   identical exam. Invariance is asserted, not assumed.
4. **Arms** —
   - `NO_CONSOLIDATION` — the ceiling: the region kept verbatim. Without it
     a score has no meaning.
   - `CONSOLIDATOR_DETERMINISTIC` — the current deterministic Consolidator,
     run over the real store path; what survives of the region is the
     durable facts it records.
   - `TRUNCATE_OLDEST` — keep the newest 10 turns of the region and drop the
     rest. The cheap baseline any LLM arm must beat.
   - `LLM_SUMMARY` — defined in the matrix, `SKIPPED-GATE-CLOSED` in every
     scorecard while the gate holds.
5. **Answering** — closed-book against each arm's retained text, with a
   forced `NOT IN CONTEXT — <best guess>` option. The default answerer is
   programmatic (`recall_eval.context_answerer`) — no model calls, no
   network, so the harness smoke-tests in CI.
6. **Judging** — programmatic first (`recall_eval.judge_score`): exact match
   2, hedged gold-substring 1, else 0. An LLM judge exists only as a
   flag-off hook for free-text variance and must route through the
   model-picker's existing slots. A summarizer that truncates
   (`finish_reason != "stop"`) is a retryable failure, never a stored
   result — the row is `FAILED-RETRYABLE`, not a score.
7. **Scorecard** — `SCORECARD-<date>.md`, committed and dated, ceiling
   printed first, findings numbered, caveats included; raw rows as JSONL
   alongside.

## Files

- `SCORECARD-<date>.md` — the dated scorecard of record.
- `rows-<date>.jsonl` — the raw per-thread-per-arm rows behind it.
- `cache/` — question-bank cache keyed by content digest (gitignored; a
  cache hit is the proof of exam invariance, and it regenerates from the
  seed).

## Caveats that always apply

- Small n. These are baselines and gates, not a leaderboard; deltas at this
  n are noise, and every scorecard says so.
- The programmatic answerer measures literal retention, not semantic recall.
  The LLM arms, when the gate opens, will be judged on free-text answers
  with the same gold and the same partial-credit rule.
- Token counts are whitespace-approximate — for comparing arms, not for
  budgeting a context window.
- No run of this harness may touch the Consolidator's flag, the network, or
  a model. If a future arm needs a model, it goes through the model-picker's
  slots and its scorecard says which slot it used.