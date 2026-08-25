# T-S1.0 Verdict — Staleness/Baseline Behavior of Profile-Skipped Files

**Date:** 2026-08-24
**Task:** IMPLEMENTATION-PLAN-SOURCEPREP-TEMPLATE-2026-08-24.md → T-S1.0
**Verdict: SAFE TO PROCEED.** Profile-skipped files are stable across runs —
no changeset-driven re-entry, no phantom-pending re-trigger, no selfheal
orphan action. One manifest quality-accounting touchpoint and one T-S1.5
manifest-channel requirement are named below (neither blocks; both must be
respected by T-S1.3 / T-S1.5 respectively).

---

## Method

Static read of every "does this stage run / is this file pending" decision
point, plus an empirical run of the **real orchestrator** (FastAPI
TestClient, real ManifestStore/recovery/resume/scheduler, real Rust
structural stage, real native embeddings) on a fixture project with
3 `.py` + 3 `.md` files, with the catalogue per-file skip monkeypatched to
drop all `.md` files (exactly the future ProfileGate consult point), and a
FakeLLMClient so every real LLM call is counted. Spike harness:
`/tmp/spike_s10_runner.py` (throwaway; not committed).

## Empirical results

| Scenario | Result |
|---|---|
| Run 1 (initial build, .md profile-skipped in CATALOGUE) | All 5 fast_sync stages `completed`; `trace_augment_manifest.json` written (`total=6, processed=6, success_rate=1.0`); zero `.md` entries in `trace_augmented.jsonl`; 10 LLM calls, none processing doc content (3 prompts merely *listed* doc paths in inferred_edges "known files" context) |
| Run 2 (no file changes) | **Refused: `PIPELINE_UP_TO_DATE`** — no phantom pending work from skipped files; the pipeline does not re-enter |
| Run 3 (`force_from_start=True` — maximum staleness pressure, all files `added`) | Completed cleanly; gate held (no doc entries); write guard passed; manifest rewritten consistently |
| `RecoveryManager.selfheal_group(pid, FAST_SYNC_STAGES)` after all runs | 5/5 `already_complete`, 0 resurrected, 0 still_missing |
| `ResumeStrategy.check_coverage_gap(pid)` | `needs_rebuild=False` |
| ENRICHMENT worker with skip-all gate (direct invocation) | 0 LLM calls; stats `_expected_total=6, _processed_count=0` → see touchpoint 1 |

## Why skipped files are stable (verified mechanisms)

1. **Changeset re-entry — safe.** Stage 1 (structural) is never
   profile-gated, so every profile-skipped file still lands in
   `trace_manifest.json.file_hashes`. Next run it is `unchanged` and
   `Changeset.should_process()` (`services/pipeline/changeset.py:44`)
   returns True only for added/modified → carry-forward, no re-entry.
2. **Freshness skip — unaffected.** `should_skip_stage_freshness`
   (`resume.py:910`) is per-stage mtime/provenance based and bypassed on
   incremental runs; per-file skips never feed it.
3. **Coverage retrigger — safe.** `maybe_retrigger_for_coverage` +
   `compute_trace_coverage` operate at the trace-graph level (stage 1),
   which profile gating never touches. Skipped files are still traced →
   coverage stays 100%.
4. **Selfheal — safe.** `selfheal_group` (`recovery.py:831`) reconciles
   manifests vs data files. Skipped files produce no output entries, so
   there is nothing to prune (`prune_orphan_enrichments` prunes entries
   whose *nodes* vanished — not files lacking entries) and nothing to
   resurrect (orphan rule fires only when a >1 KiB output file exists
   with no manifest — a stage that ran and wrote nothing still has its
   manifest).
5. **Manifest quality — self-consistent for line-count stages.** With no
   `_expected_total` override, `aggregate_quality_metrics` derives
   totals from JSONL line counts, so a 6-entry catalogue run over a
   3-allowed-file scope reads `total=6, processed=6, success_rate=1.0`.
   No control-flow consumer of `success_rate` exists (verified by grep —
   manifests are observability only; stage advancement never gates on it).

## Named touchpoints (must be handled downstream)

1. **ENRICHMENT/DEEPENING `_expected_total` misaccounting** —
   `core/epistemic_enrichment.py:1315` sets
   `_expected_total = len(file_nodes)` (project-wide, profile-blind) and
   `workers/__init__.py:134,1377,1460` (deepening totals helper) follow the
   same shape. With a profile skipping K files permanently, the manifest
   shows `success_rate < 1.0` forever (empirically: skip-all → 0/6).
   **No re-entry loop** (no control-flow consumer), but the dashboard chip
   reads as permanently incomplete. **T-S1.3 must subtract gate-rejected
   files from `_expected_total`** (or thread the gate into the totals
   helpers) when it adds the consult points.
2. **T-S1.5 must write a real provenance manifest for disabled stages.**
   `detect_resume_point` (`resume.py:91`) considers a stage complete iff
   `ManifestStore.provenance_exists(stage)`. A never-run disabled stage
   without a manifest would pin that group's resume point at itself
   forever and re-run every enabled stage after it on each group
   invocation. Writing the `disabled_by_config` manifest through
   `store.write_provenance` fixes resume pinning, selfheal
   (`already_complete`), and freshness in one move. **Constraint:** the
   manifest must NOT carry `restored: true` — `is_stub_manifest` keys on
   that field and stubs during rebuilds are treated as incomplete
   (`resume.py:204-233`). Use a distinct marker (`status:
   "disabled_by_config"`), not the selfheal-stub shape.

## Consequence for the plan

- **T-S1.3 gate semantics: proceed as spec'd** (first-check consult in
  `_should_skip`, `_needs_enrichment`, inferred_edges loop, deepening,
  knowledge stage 10), plus the `_expected_total` adjustment above.
- **T-S1.5: implement with `store.write_provenance`-backed
  `disabled_by_config` manifests** (not selfheal stubs), and reuse the
  existing `mark_stage_skipped` run-metadata pattern
  (`_update_run_metadata_for_skip`, `orchestrator.py:4988`) for the
  dashboard's skipped-by-config rendering.
