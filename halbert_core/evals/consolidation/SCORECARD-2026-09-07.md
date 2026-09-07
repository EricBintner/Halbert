# Consolidation recall scorecard — 2026-09-07

## Setup

- Corpus: synthetic, deterministic; 9 threads x 40 turns; region = turns 0..19 — the region the policies destroy/merge.
- Exam: one template question per planted fact inside the region (18 questions), bank cached by content digest — every arm answers the identical exam.
- Answerer: programmatic closed-book with a forced NOT IN CONTEXT option. No model calls anywhere; the hallucination half of the instrument becomes a live measurement only when an LLM arm runs.
- Judge: programmatic — 2 correct / 1 partial (hedged gold-substring) / 0 wrong.
- Scoring: recall@retained. A recall number is never reported without the tokens the arm retained to get it.

## Arms

| arm | status | questions | correct | partial | wrong | recall | retained tokens (mean) |
|---|---|---:|---:|---:|---:|---:|---:|
| NO_CONSOLIDATION (ceiling) | OK | 18 | 18 | 0 | 0 | 1.000 | 283 |
| CONSOLIDATOR_DETERMINISTIC | OK | 18 | 0 | 0 | 18 | 0.000 | 20 |
| TRUNCATE_OLDEST | OK | 18 | 9 | 0 | 9 | 0.500 | 141 |
| LLM_SUMMARY | SKIPPED-GATE-CLOSED | — | — | — | — | — | — |

## Findings

1. The ceiling (NO_CONSOLIDATION) answers 18 of 18 at 283 retained tokens — the exam is answerable from the region; any arm below this is losing real information.
2. The current deterministic Consolidator retains durable entity facts (20 tokens) and no episodic planted facts — recall 0.000. It was never designed to; the LLM pass this harness gates must beat TRUNCATE_OLDEST, not merely this arm.
3. TRUNCATE_OLDEST keeps only the newest planted fact of the region — recall 0.500 at 141 tokens. It is the cheap baseline: an LLM arm that cannot beat it is not worth its cost or its risk.
4. LLM_SUMMARY: SKIPPED-GATE-CLOSED — the Consolidator's LLM flag is untouched; this scorecard is the deterministic evidence the gate asks for.

## Caveats

- n = 18 questions over 9 threads (54 scored arm-runs of the identical exam); deltas at this n are noise. These numbers are the deterministic baseline, not a ranking of arms.
- The programmatic answerer matches the planted statement literally, so recall here measures literal retention, not semantic recall; an LLM arm will be judged on free-text answers.
- Token counts are whitespace-approximate; they exist to compare arms, not to budget a context window.
- The CONSOLIDATOR_DETERMINISTIC arm models production idle consolidation across the whole corpus: its retained context is the durable facts the real Consolidator records for the thread's domain.
- The LLM judge / LLM answerer hooks are flag-off and route through the model-picker's existing slots; this run used neither.
