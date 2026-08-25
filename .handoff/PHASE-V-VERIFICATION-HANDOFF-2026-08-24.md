# Phase V Verification — Handoff & Blocker

**Date:** 2026-08-24
**Status:** T-V.4 (doc hygiene) DONE. T-V.0, T-V.1, T-V.2, T-V.3, T-V.5
BLOCKED on the deployed daemon + a real unified build. See "What's needed"
below.

## What landed (implementation complete)

All implementation tasks of
`IMPLEMENTATION-PLAN-SOURCEPREP-TEMPLATE-2026-08-24.md` are committed:

**CoDRAG (SourcePrep) — committed to main:**
- `d73ccce3` Phase S1: per-scope pipeline profiles + ProfileGate
  (T-S1.1 ScopeRecord.pipeline_profile; T-S1.2 pipeline_profiles.py +
  ProfileGate; T-S1.3 gate injection at the 10 worker sites + 5 per-file
  consult points + profile-aware _expected_total; T-S1.4 scopes API; T-S1.6
  group_reasoning input-set filter). T-S1.0 spike + T-S1.5 orchestrator skip
  were the fable tasks, already on the base.
- `2691fc91` Phase S2: profile-keyed prompts (T-S2.1 CATALOGUE REFDOC/CONFIG
  + batched hook with explicit batch size; T-S2.2 ENRICHMENT
  EPISTEMIC_REFDOC/CONFIG; T-S2.3 ATLAS CORPUS/HOST root + segment variants;
  T-S2.4 atlas_deep_dirs knob; T-S2.6 tests). Also re-anchored the
  F2_SITES hold-guarded pins (cluster/group_reasoning had drifted -1 from
  the T-S2.5 fable commit; atlas drifted from S2 additions).

**Halbert — committed to main:**
- `f9aa822` Phase H1: unified staging root (T-H1.1 register_host_project →
  sourceprep/host/, jsonl_to_markdown → sourceprep/knowledge/); scoped
  retrieval (T-H1.3 get_context scope=, scope_for_query intake→scope routing,
  backend figure_id→scope + trace_expand=True); ConfigWatcher → unified
  project (T-H1.4 apply(build_fast_sync_only=True)). T-H1.2 (template +
  apply script) was the fable task, already on the base (`2f02c53`).

With no profiled scopes and no `disabled_stages`, SourcePrep behavior is
byte-identical to before — all of S1/S2 ship inert until a template creates
profiled scopes.

## What's verified (tests, no daemon)

- SourcePrep: 190 passed across the S1/S2-relevant suites (profile matrices,
  gate resolution/overlap/ties/auto-rule, API round-trip + 409, per-file
  consult + _expected_total accounting, prompt selection per profile, atlas
  segmentation, hold-guard pins). The pre-existing unrelated failures
  (test_concept_seeder_swarm routing, test_pipeline_journal, test_recovery_manager)
  remain and are not from this work.
- Halbert: 18 passed (scope_for_query routing, get_context scope body,
  backend figure_id→scope + trace_expand, watcher unified-apply path).
  The Halbert venv has a pre-existing pydantic_core arch mismatch
  (x86_64 python vs arm64 .so) that blocks pydantic-dependent test
  collection — unrelated, flagged in memory.

## T-V.4 — DONE

Doc hygiene (untracked `.handoff/` working docs updated):
- REMAINING-WORK-2026-08-24.md §1.6: closed — scopes were never blocked
  upstream; the template creates them.
- RAG-OPTIMIZATION-PLAN-2026-08-23.md §S1 + IMPLEMENTATION-PLAN-2026-08-23.md
  T0a.1/T5a.1: as-built notes superseding the two-project split with the
  unified template.

## T-V.0 / V.1 / V.2 / V.3 / V.5 — BLOCKED (environment)

These need the SourcePrep daemon running the NEW S1/S2 code and a real
unified build. As of this session:

1. The daemon at `localhost:8400` is running OLD code (Prep 0.1.0; my
   `d73ccce3`/`2691fc91` are on main but not deployed). ProfileGate and the
   profile prompts are therefore inactive in the running pipeline.
2. The unified corpus root `~/.local/share/halbert/sourceprep/` exists
   (a prior `apply` created it) but `knowledge/{linux,macos,bsd,common}/`
   are EMPTY (jsonl_to_markdown has not been run against the unified default)
   and `host/` has no staged files.
3. No unified build has been run against the new code. `classify_node` (T-V.0
   class mix) reads Rust-parser metadata (section_count/ref_count), so even
   the local class-mix measurement needs a structural build.

### What's needed to unblock Phase V (exact steps)

1. **Restart the SourcePrep daemon on the new main.** Stop the running
   daemon and relaunch from the CoDRAG repo on `main` (post-`2691fc91`)
   so ProfileGate + profile prompts + the build-time external-edge loader
   are active. (The plan warns: a daemon restart mid-apply can auto-fire
   fast_sync and race — `apply()` sets `fastSync=false` during the build and
   flips it true after, so restart BEFORE running apply, not during.)
2. **Populate the corpus.**
   - `python -m halbert_core.rag.jsonl_to_markdown --data-dir data`
     (now defaults to `~/.local/share/halbert/sourceprep/knowledge/`).
   - `python -m halbert_core.tools.register_host_project` stages host/ to
     `sourceprep/host/` (or let `apply()` stage it).
3. **Run the unified build.**
   `python -m halbert_core.integrations.sourceprep_setup apply`
   (full path: find-or-create project, PUT config with atlas_deep_dirs +
   disabled_stages, reconcile the 5 scopes with pipeline_profile, poll-to-
   -complete between async steps, push config external edges with
   replace_origin, deep_enrichment → finalize).
4. **Then run the V tasks** (against the built project):
   - T-V.0: run a representative per-platform sample through
     `classify_nodes` for the structured-code/structured-docs/narrative mix
     (decision: >50% narrative → prose_docs v1 disables catalogue too); run
     the markdown analyzer over the same sample for `contains`/`references`/
     `links_to` edge counts and resolved-vs-dangling ratio (decision: poor
     `references` precision → add the doc-scope edge-kind filter in T-H1.3's
     fallback path).
   - T-V.1: assert `trace_epistemic.jsonl` has entries for host/ files, none
     for knowledge/; no group_reasoning output referencing knowledge/ paths;
     atlas segments per platform; `disabled_stages` manifests show
     `disabled_by_config`.
   - T-V.2: extend `scripts/corpus_quality_gate.py` with 20 scoped queries;
     assert linux queries return no macos chunks and host config queries
     return staged config chunks.
   - T-V.3: host query "what happens if I change sshd_config" with
     scope=host → trace_expanded=True, expanded chunks include drop-ins;
     docs query hitting one man-page section with scope=knowledge-linux →
     expanded chunks include sibling sections / cross-linked docs.
   - T-V.5: sshd_config + drop-ins + related unit land in one cluster and
     one reasoning group; group reasoning output references the policy unit.

Steps 1–3 are a heavy, outward-facing action on the live daemon + the
16K-doc corpus (the plan estimates ~50min–2hrs for a full build at cloud
concurrency). They were NOT run autonomously to avoid interrupting the
running daemon and racing a build. Run them when ready; then T-V.0–V.5
become executable. A `--retire-legacy-projects` pass removes the old
halbert-host / halbert-knowledge registrations after the unified build
verifies.