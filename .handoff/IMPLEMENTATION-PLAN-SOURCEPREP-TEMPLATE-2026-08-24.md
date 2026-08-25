# Implementation Plan: SourcePrep→Halbert Template

**Date:** 2026-08-24
**Status:** Ready for execution
**Design doc:** SOURCEPREP-HALBERT-TEMPLATE-2026-08-24.md (same directory) — read first, including §6 scrutiny integration
**Scrutiny:** SOURCEPREP-HALBERT-SCRUTINY-2026-08-24.md (same directory) — findings C1/C2/C3/M1 integrated below
**Follow-ups (out of scope):** /Volumes/4TB-BAD/HumanAI/CoDRAG/.handoff/HANDOFF-HALBERT-TEMPLATE-FOLLOWUPS-2026-08-24.md

## Execution order

Phase S1 (SourcePrep machinery) → Phase S2 (SourcePrep prompts + fixes) →
Phase H1 (Halbert unification) → Phase V (verification). S1 and S2 are in
the CoDRAG repo (`/Volumes/4TB-BAD/HumanAI/CoDRAG`); H1 and V are in the
Halbert repo (`/Volumes/4TB-BAD/Halbert`).

**Commit rules (both repos):** no Co-Authored-By trailers, no
generation-attribution lines.

---

## Phase S1 — SourcePrep: per-scope pipeline profiles (CoDRAG repo)

### T-S1.0 — SPIKE: staleness/baseline-shrink behavior of profile-skipped files
**Assignment: fable / high**

**Scrutiny Risk 1 — verify before coding anything else.**

**Implementation:**
- Read `Changeset.should_process` interaction with stage manifests and the
  write guard (`orchestrator.py:56-62` baseline-shrink comment)
- Empirically: on a test project, run a stage where a worker skips all files
  (simulate a profile skip with a monkeypatched gate), then run the pipeline
  twice more and observe: does the stage record "complete/stable" or does
  staleness keep flagging the skipped files as pending (re-entering the
  stage every run)?
- Known-safe half (verified by read): changeset carry-forward means skipped
  files go `unchanged` next run — no changeset-driven re-entry. The open
  half is manifest quality accounting and selfheal orphan detection.

**Acceptance:**
- Written verdict: profile-skipped files are stable (safe to proceed) OR a
  named list of the exact manifest/staleness touchpoints that must learn
  "skipped-by-profile" as a first-class outcome

**Blocks:** T-S1.3 (gate semantics depend on the verdict)

---

### T-S1.1 — Add `pipeline_profile` to ScopeRecord
**Assignment: sonnet / med**

**Edit:** `src/prep/core/scope_store.py`

**Implementation:**
- Add field: `pipeline_profile: str = "code"` to the `ScopeRecord` dataclass
- `from_dict`: `pipeline_profile=str(d.get("pipeline_profile") or "code")` —
  back-compat with old serialized records
- `create()` / `update()` accept optional `pipeline_profile` param
- Validate against known profile names on write: `{"code", "prose_docs",
  "system_config"}` — unknown value → ValueError (409 via API)
- No migration needed (default covers existing records)

**Acceptance:**
- Old records without the field load with `pipeline_profile="code"`
- Round-trip through settings_store preserves the field
- `pytest tests/test_scope_resolver.py tests/test_prep_data_scope.py` passes

---

### T-S1.2 — Profile definitions + ProfileGate
**Assignment: opus / xhigh**

**Create:** `src/prep/core/pipeline_profiles.py`

**Implementation:**
```python
PIPELINE_PROFILES: dict[str, dict[str, bool]] = {
    "code": {},  # empty = all stages enabled (today's behavior)
    "prose_docs": {
        "inferred_edges": False, "catalogue": True, "enrichment": False,
        "group_reasoning": False, "clustering": True, "deepening": False,
        "atlas": True, "rules": False, "concepts": False,
        "audit": False, "antibodies": False,
    },
    "system_config": {
        "inferred_edges": False, "catalogue": True, "enrichment": True,
        "group_reasoning": True, "clustering": True, "deepening": False,
        "atlas": True, "rules": False, "concepts": False,
        "audit": False, "antibodies": False,
    },
}
```
- Rust/embedding stages (structural, validation, knowledge,
  deep_knowledge) are never gated — omit from matrices
- `class ProfileGate`: constructed with `(project_id, stage: StageId)`;
  lazily loads scopes via `scope_store.list(project_id)`; builds
  `disabled_path_set` = union of paths of scopes whose profile disables
  this stage; `allows(file_path) -> bool` using
  `path_matches_any_scope()` from `core/scope_resolver.py`
- **Overlap resolution:** most-specific path prefix wins; tie → lowest
  scope id (deterministic). Log a warning when a file matches multiple
  scopes with different profiles.
- **Layered resolution** (scrutiny Risk 4): (1) explicit scope profile →
  (2) per-file content-type detection ONLY when project config
  `auto_profile_files: true` (off by default; markdown→prose_docs is the
  only v1 rule) → (3) `code` default. Halbert uses explicit scopes; the
  per-file layer ships dormant.
- Files matching NO scope → allowed (default `code` profile, unchanged
  behavior for all existing projects)
- Cache the scope list per ProfileGate instance (one per worker
  construction)

**Acceptance:**
- `ProfileGate(pid, StageId.ENRICHMENT).allows("knowledge/linux/x.md")`
  is False when a `prose_docs` scope covers `knowledge/linux/`
- `ProfileGate(pid, StageId.CATALOGUE).allows(...)` is True for same path
- Unscoped paths always allowed, every stage

---

### T-S1.3 — Inject profile_gate into per-file workers (mechanism 1 of 3)
**Assignment: opus / high**

**Edit:** `src/prep/services/pipeline/workers/__init__.py`

**Scope correction (scrutiny M1):** `should_process` gating covers only the
5 per-file stages (inferred_edges, catalogue, enrichment, deepening,
deep_knowledge). The `.changeset` injection exists at **10 sites**
(~lines 504, 751, 816, 960, 1034, 1099, 1153, 1211, 1389, 1403) — inject
`.profile_gate` at all 10 (harmless where unused), but only the 5 per-file
stages consult it.

**Implementation:**
- In `create_worker()` next to the changeset injection (lines ~498-508):
  construct `ProfileGate(project_id, stage)`; set on both
  `wrapped_worker.profile_gate` and `base_worker.profile_gate` (same
  dual-attribute pattern as changeset — inner closures read the
  base_worker attr)
- At each of the 10 processor injection sites, add the parallel line:
  `X.profile_gate = getattr(worker, "profile_gate", None)`

**Edit processors to consult the gate** (per-file stages only, each ~3-5
lines at the existing skip check):
- `core/augmenter.py` `_should_skip()` — first check:
  `gate = getattr(self, "profile_gate", None); if gate is not None and not gate.allows(fp): return True`
- `core/epistemic_enrichment.py` `_needs_enrichment()` — same pattern
- `core/inferred_edges.py` — same at its per-file loop (:230)
- `core/deepening.py` — DriftDetector / node iteration (:141)
- `core/knowledge.py` — stage 10 changeset path (:482)

**Non-per-file stages are NOT gated here** — see T-S1.5 (orchestrator skip)
and T-S1.6 (group_reasoning input-set filter).

**CRITICAL:** Do NOT touch `core/trace/loaders.py
load_filtered_trace_nodes()` — shared with query-time search
(`api/routers/projects/search.py:300`). Gating lives in workers only.

**Acceptance:**
- A scope with `prose_docs` profile: ENRICHMENT run produces zero
  trace_epistemic entries for in-scope files, non-zero for out-of-scope
- Workers with no scopes defined behave identically to before
- `pytest tests/ -k "pipeline or worker" -x` passes

---

### T-S1.5 — Per-stage skip flag at the orchestrator (mechanism 2 of 3)
**Assignment: fable / xhigh**

**New surface — scrutiny M1.** Today gating is per stage-GROUP
(`auto_config.{fastSync,deepEnrichment,finalize}`,
`orchestrator.py:1971-2044`), not per stage. A mixed project needs
`atlas: True` / `concepts: False` — both in finalize — so group gating is
insufficient.

**Edit:** `src/prep/services/pipeline/orchestrator.py`,
`src/prep/services/pipeline/stages.py`

**Implementation:**
- Add project config `disabled_stages: list[str]` (stage ids)
- In the orchestrator's stage dispatch (where each stage worker is
  launched), check membership: if stage in `disabled_stages` → emit a
  manifest entry `{status: "disabled_by_config", stage: <id>}` and skip —
  NOT a failure, NOT pending (interacts with T-S1.0 verdict)
- Atlas/concepts/audit/antibodies/rules are all-or-nothing per project —
  never per-file (scrutiny M2). `disabled_stages` is the ONLY way they
  get turned off.
- The Halbert template sets: `disabled_stages: ["rules", "concepts",
  "audit", "antibodies"]` (plus "deepening" while both profiles have it
  off) — profile matrices still apply to the per-file stages within
  enabled stages.
- Pipeline status UI surfaces disabled stages as skipped-by-config
  (dashboard label, not error)

**Acceptance:**
- `disabled_stages: ["concepts"]` → finalize group runs atlas + rules,
  concepts manifest shows disabled_by_config, no stage failure
- Re-runs stay stable (no re-entry loop — per T-S1.0 verdict)
- Absent the config → byte-identical behavior

---

### T-S1.6 — group_reasoning input-set filter (mechanism 3 of 3)
**Assignment: sonnet / med**

**Edit:** `src/prep/core/group_reasoning.py`

**Implementation:**
- Before `build_dependency_groups` (:906), filter the epistemic input set:
  drop entries whose file path the ProfileGate rejects for
  `group_reasoning`
- For Halbert this is nearly automatic (docs' sparse markdown edges +
  min_group_size=2 drops them anyway) but the mechanism must exist for the
  general case

**Acceptance:**
- Docs-scope files never appear in any group, even if markdown edges link
  two docs
- Host config files group normally (after T-S2.5 lands)

---

### T-S1.4 — Scopes API exposure
**Assignment: sonnet / med**

**Edit:** `src/prep/api/routers/scopes.py`

**Implementation:**
- `CreateScopeRequest` / `UpdateScopeRequest` gain
  `pipeline_profile: str | None = None`
- `create_scope` / `update_scope` pass through to scope_store (validation
  errors → 409 SCOPE_INVALID)
- `_summary()` includes `pipeline_profile`
- `_synthesize_global()` includes `pipeline_profile: "code"`

**Acceptance:**
- `POST /projects/{id}/scopes` with `pipeline_profile: "prose_docs"`
  persists and round-trips via GET
- Invalid profile name → 409
- `pytest tests/test_mcp_scope_envelope.py` passes

---

## Phase S2 — SourcePrep: prompt variants + two small fixes (CoDRAG repo)

### T-S2.1 — Profile-keyed prompts in CATALOGUE
**Assignment: opus / xhigh**

**Edit:** `src/prep/core/augmenter.py`

**Implementation:**
- Replace the binary `is_markdown` branch (line ~917) with profile
  resolution: `profile = profile_for_path(self.project_id, file_path)`
  (helper from pipeline_profiles.py; the augmenter already receives
  `project_id` at construction, line ~812)
- Add `REFDOC_ROLE_SYSTEM` / `REFDOC_ROLE_PROMPT`: doc_type ∈
  {man_page, handbook_chapter, guide, formula, faq, reference}; drop
  doc_status; extract SEE ALSO / cross-reference targets; fields otherwise
  match AugmentationEntry
- Add `CONFIG_ROLE_SYSTEM` / `CONFIG_ROLE_PROMPT`: what directive set the
  file controls, which service/daemon it configures, risk/sensitivity notes
- Mapping: `prose_docs` → REFDOC prompts; `system_config` → CONFIG prompts;
  `code` → existing is_markdown behavior (unchanged)
- **Cost correction (scrutiny M3):** the doc sub-batch is
  `catalogue_file//5` = 20/call at LARGE (`augmenter.py:1447`) → 16K docs ≈
  **800 calls, not 160**; narrative-class files batch at 1 (:1564) → up to
  16K calls. The new REFDOC prompt must hook the **batched** path
  (`build_batched_doc_prompt`, :1488), not just the unbatched
  DOC_ROLE_PROMPT — and should ship with its own explicit doc batch size so
  prose corpus cost is controlled by design, not by the generic
  content-class heuristic. Decision rule enforced by T-V.0: if >50% of the
  corpus classifies narrative, prose_docs v1 disables catalogue too.

**Acceptance:**
- Man page fixture produces doc_type="man_page" + no doc_status field
- sshd_config fixture produces a config-role summary
- Existing markdown/code behavior unchanged for `code` profile files

---

### T-S2.2 — Profile-keyed prompts in ENRICHMENT
**Assignment: sonnet / high**

**Edit:** `src/prep/core/epistemic_enrichment.py`

**Implementation:**
- Same pattern at the `is_markdown` branch (line ~502): profile resolution
  first
- Add `EPISTEMIC_REFDOC_PROMPT`: topic domain tags (storage/network/auth/
  package-mgmt), platform (linux/macos/bsd/common), commands covered; drop
  decision_chains and doc_status
- Add `EPISTEMIC_CONFIG_PROMPT`: controlled resources, conflicts with
  sibling files, effective-value notes, security sensitivity
- `code` profile → existing prompts unchanged
- Note: `prose_docs` v1 has enrichment disabled in the matrix (T-S1.2), so
  the REFDOC prompt ships dormant — it activates when the matrix entry
  flips. CONFIG prompt is live immediately (system_config enrichment on).

**Acceptance:**
- Config fixture produces controlled-resources output, not code-role output
- `code` profile unchanged

---

### T-S2.3 — ATLAS prompt variants per segment
**Assignment: opus / high**

**Edit:** `src/prep/core/atlas/prompts.py`, `src/prep/core/atlas/generator.py`

**Implementation:**
- Add `CORPUS_ATLAS_PROMPT` (root atlas for doc-heavy projects: platform
  coverage, doc-type mix, "which source answers which kind of question")
  and `HOST_ATLAS_PROMPT` (config-tree orientation: services, mounts,
  network, auth policy surfaces)
- Add segment-level variants: `SEGMENT_CORPUS_PROMPT`,
  `SEGMENT_HOST_PROMPT`
- In `generate_segmented()`: per segment, resolve dominant profile (majority
  of segment file paths by scope membership) → pick prompt variant
- Root atlas: pick by project-wide dominant profile; mixed → CORPUS variant
  with a host paragraph (Halbert is knowledge-dominant by volume)
- `generate_structural()` (no-LLM path) unchanged

**Acceptance:**
- Atlas of a fixture project with knowledge/linux + knowledge/macos
  segments mentions platform coverage, not "modules/imports"
- Host segment atlas describes config surfaces
- Code-only project atlas byte-identical to before

---

### T-S2.4 — `atlas_deep_dirs` project config knob
**Assignment: sonnet / med**

**Edit:** `src/prep/core/atlas/routing.py`, config plumbing

**Implementation:**
- `_group_by_directory()` reads `proj.config.get("atlas_deep_dirs", [])`
  (thread project config in — compute_segments already takes
  `project_root`; add optional `extra_deep_dirs` param from the caller in
  generator.py which has the project)
- Union with `_DEEP_DIRS`; Halbert template sets `["knowledge"]` → segments
  become `knowledge/linux`, `knowledge/macos`, `knowledge/bsd`,
  `knowledge/common`, `host`
- Default unchanged (no config → today's behavior)

**Acceptance:**
- With `atlas_deep_dirs: ["knowledge"]`, compute_segments yields
  per-platform segments on a fixture tree
- Without it, identical output to before

---

### T-S2.5 — Shared build-time edge loader including external edges (scrutiny C2)
**Assignment: fable / xhigh**

**Scope correction:** the gap is pipeline-wide, not one function. Grep
confirms **no build stage reads `trace_external_edges.jsonl`** — not
`group_reasoning.load_edges()` (:386-397) and not `cluster.py:load_edges()`
(:1165-1176, identical tuple). External edges are a query-time-only feature
today (`TraceIndex`, `core/trace/index.py:129-173`). Since clustering forms
the groups group_reasoning reasons over, fixing only group_reasoning is
insufficient — config files would stay singleton clusters and no groups
would form (scrutiny C3).

**Edit:** `src/prep/core/trace/loaders.py` (new helper),
`src/prep/core/cluster.py`, `src/prep/core/group_reasoning.py`

**Implementation:**
- New `load_all_build_edges(index_dir)` in `core/trace/loaders.py`: reads
  `trace_edges.jsonl` + `trace_inferred_edges.jsonl` +
  `trace_external_edges.jsonl`, tags each edge with its origin file
- `cluster.py:load_edges()` and `group_reasoning.py:load_edges()` delegate
  to it
- External edges use `file:`-prefixed node IDs (Halbert's format) — verify
  Louvain adjacency and `build_dependency_groups` match them against file
  nodes; add ID normalization if forms differ
- This is a **generic SourcePrep bug fix** (external edges are a shipped
  feature that silently didn't affect build-time intelligence) — frame the
  commit accordingly, not as Halbert-special

**Acceptance:**
- Fixture: push an external edge between two config files → they land in
  the same cluster AND the same reasoning group
- No external edges file → unchanged behavior
- Query-time trace expansion still works (TraceIndex path untouched)

---

### T-S2.6 — Phase S2 tests
**Assignment: sonnet / high**

**Create/extend:** `tests/test_pipeline_profiles.py` (S1 tests can live here
too), `tests/test_augmenter_profiles.py`, fixture trees under
`tests/fixtures/`

**Coverage:**
- Profile gating per stage × profile matrix
- Prompt selection per profile (mock LLM client, assert prompt class used)
- atlas_deep_dirs segmentation
- External edges in group reasoning
- Full back-compat: no scopes → byte-identical pipeline behavior

---

## Phase H1 — Halbert: unify into one project (Halbert repo)

### T-H1.1 — Unified staging root
**Assignment: sonnet / med**

**Edit:** `halbert_core/halbert_core/tools/register_host_project.py`,
`halbert_core/halbert_core/rag/jsonl_to_markdown.py`

**Implementation:**
- New root: `~/.local/share/halbert/sourceprep/` with `host/` and
  `knowledge/` subdirs
- register_host_project stages to `sourceprep/host/` (change STAGING_DIR)
- jsonl_to_markdown outputs to `sourceprep/knowledge/{linux,macos,bsd,common}/`
  (change default output dir; Phase 0 markdown already grouped per platform)
- Keep the old `data/staging/sourceprep/` path as a `--output` override for
  debugging; default moves

**Acceptance:**
- Both staging scripts write under the unified root
- `sourceprep/host/etc/ssh/sshd_config` and
  `sourceprep/knowledge/linux/...` exist after running both

---

### T-H1.2 — Template spec + idempotent apply script
**Assignment: fable / max**

**Create:** `halbert_core/halbert_core/integrations/sourceprep_template.yml`,
`halbert_core/halbert_core/integrations/sourceprep_setup.py`

**Implementation:**
- Template YAML exactly as in design doc §3.6, plus
  `atlas_deep_dirs: ["knowledge"]` in project config and
  `pipeline_profile` per scope
- `sourceprep_setup.py apply()`:
  1. Find-or-create project "halbert" at the unified root (mode standalone)
  2. PUT project config (include_globs `["host/**", "knowledge/**/*.md"]`,
     excludes for secrets, max_file_bytes 500000, use_gitignore false,
     trace.enabled true, atlas_deep_dirs, auto_config fastSync=true /
     deepEnrichment=manual / finalize=manual, disabled_stages per T-S1.5)
  3. Reconcile scopes via API (create/update to match template;
     pipeline_profile on each). **Plumbing note (scrutiny §6.5):** the
     scopes API's update endpoint does not accept `paths` — path mutation
     is via `POST /scopes/{id}/add` and `/remove`. Apply does
     create-scope → add-paths (two calls per scope), or update → add/remove
     diff for existing scopes.
  4. Build sequence: CodeIndex build → fast_sync → push external edges
     (`replace_origin="config"`) → deep_enrichment → finalize
     (edge push BEFORE deep_enrichment so group reasoning sees them —
     depends on T-S2.5)
  5. Idempotent: safe to re-run; only changed steps do work
- CLI entry: `python -m halbert_core.integrations.sourceprep_setup apply`
- Keep the old two-project registrations functional during migration;
  add `--retire-legacy-projects` flag that removes halbert-host /
  halbert-knowledge after unified build verifies (manual step, not default)

**Acceptance:**
- Fresh machine: one `apply` run → project exists, 5 scopes with correct
  profiles, all indexes built, external edges present
- Second `apply` run: no-op (idempotent)
- Legacy projects untouched unless flag passed

---

### T-H1.3 — Client scope param + per-scope trace_expand
**Assignment: sonnet / high**

**Edit:** `halbert_core/halbert_core/integrations/sourceprep_client.py`,
`halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py`

**Implementation:**
- `get_context(..., scope: Optional[str] = None)` — include in request
  body only when set (API already supports it; verified scope_resolver)
- Retrieval backend: `search()` maps `figure_id` → scope.
  **`trace_expand=True` for all scopes** (scrutiny C1 correction — markdown
  `contains`/`links_to` edges are real signal: a hit expands to the doc's
  own sections and cross-linked docs). Fallback if T-V.5 shows `references`
  edges are noisy on the real corpus: doc-scope edge-kind filter
  (`contains`/`links_to` only), not disabled expansion.
- Intake-domain → scope mapping (intake/signals.py domains):
  config/service/security/network/storage questions about THIS host →
  `host`; platform questions → `knowledge-{platform}`; ambiguous → unscoped
- Platform from `platform.system()` for default knowledge scope

**Acceptance:**
- Scoped query returns `applied_scope` in envelope matching request
- knowledge-* queries expand to sections/linked docs via markdown edges
- host queries trace-expand over Halbert's external edges

---

### T-H1.4 — ConfigWatcher → unified project
**Assignment: sonnet / med**

**Edit:** `halbert_core/halbert_core/config/watcher.py`

**Implementation:**
- `create_sourceprep_reindex_callback()` calls
  `sourceprep_setup.apply(build_fast_sync_only=True)` instead of
  `HostProjectRegistrar.register(name="halbert-host")` — re-stage host/,
  incremental fast_sync, re-push edges with replace_origin
- Keep the detector sweep as-is

**Acceptance:**
- Touch a staged config file → debounce → host/ re-staged, fast_sync runs,
  edges refreshed, knowledge/ untouched (changeset gate)

---

## Phase V — Verification

### T-V.0 — Corpus classification + edge-count pre-flight (before first full build)
**Assignment: opus / high**

**Scrutiny M3 + C1 empirical requirements.**

**Implementation:**
- Run Halbert's real corpus (a representative sample per platform:
  man pages, homebrew formulas, handbook chapters, ask-different Q&A)
  through the augmenter's three-way content-class split
  (`_augment_files_batched`, `augmenter.py:1326`) — report the
  structured-code / structured-docs / narrative mix
- Decision rule: if >50% narrative → prose_docs v1 disables catalogue too
  (retrieval = embeddings only); re-state the build cost with the measured
  mix, not the code batch
- Run the markdown analyzer over the same sample and count emitted
  `contains` / `references` / `links_to` edges, and how many
  `references`/`links_to` targets resolve to real file nodes vs dangle
- Decision rule: if `references` precision is poor (mostly dangling or
  spurious), add the doc-scope edge-kind filter (`contains`/`links_to`
  only) in T-H1.3's fallback path

**Acceptance:**
- Written numbers: class mix %, edge counts by kind, resolved-vs-dangling
  ratio
- Catalogue on/off and edge-filter decisions recorded with the data

### T-V.1 — Profile gating evidence in manifests
**Assignment: sonnet / med**
- After unified build: `trace_epistemic.jsonl` has entries for host/ files,
  none for knowledge/ files; no group_reasoning output referencing
  knowledge/ paths; atlas segments exist per platform; `disabled_stages`
  manifests show `disabled_by_config`

### T-V.2 — Retrieval quality gate
**Assignment: sonnet / high**
- Extend `scripts/corpus_quality_gate.py`: 20 queries through the unified
  project with scope routing; assert linux queries return no macos chunks
  (scope mask works), host config queries return staged config chunks

### T-V.3 — Trace expansion on both scope families
**Assignment: sonnet / med**
- Host: query "what happens if I change sshd_config" with scope=host →
  trace_expanded=True, expanded chunks include drop-ins (external edges
  followed)
- Docs: query hitting one section of a man page with scope=knowledge-linux
  → trace_expanded=True, expanded chunks include sibling sections /
  cross-linked docs (markdown edges followed)

### T-V.5 — Group reasoning over host config (C3 end-to-end)
**Assignment: sonnet / med**
- After the C2 fix: sshd_config + drop-ins + related unit land in one
  cluster and one reasoning group; group reasoning output references the
  policy unit

### T-V.4 — Doc hygiene updates
**Assignment: sonnet / med**
- REMAINING-WORK-2026-08-24.md §1.6: mark stale/closed (scopes were never
  blocked; template creates them)
- RAG-OPTIMIZATION-PLAN-2026-08-23.md §S1 + IMPLEMENTATION-PLAN-2026-08-23.md
  T0a.1/T5a.1: as-built notes superseding two-project split with the
  unified template

---

## Dependency graph

```
T-S1.0 (spike) → T-S1.1 → T-S1.2 → T-S1.3 → T-S1.4
                                      ↘ T-S1.5, T-S1.6
T-S2.5 (generic fix, independent) → T-S2.6 ← T-S2.1, T-S2.2, T-S2.3, T-S2.4
                                                  ↓
T-H1.1 → T-H1.2 (needs S1+S2 deployed in the daemon Halbert talks to)
       → T-H1.3, T-H1.4 → T-V.0 → T-V.1..V.5
```

S1/S2 are pure SourcePrep and independently shippable — with no scopes
carrying profiles and no `disabled_stages` config, behavior is
byte-identical to today. H1 only works against a daemon running the new
code.

## Sizing (re-estimated post-scrutiny)

~1,200-1,400 lines total (S1 ~550 incl. orchestrator skip surface, S2 ~350
incl. shared edge loader, H1 ~250, V +spike/pre-flight). The original "~900,
machinery is small" covered only the per-file gate — scrutiny M1 identified
the other two enforcement mechanisms as new surface.

---

## Task assignments: model tier + effort level

**Model tiers:** `fable` (novel design, forensic judgment, subtle
interactions) → `opus` (complex implementation with clear spec) →
`sonnet` (mechanical, well-specified, pattern-following).

**Effort levels:** `med` (bounded, single-file-ish) → `high` (moderate
spread) → `xhigh` (significant, multi-file or subtle) → `max` (large
multi-day integration) → `ultracode` (reserved for tasks that may
expand beyond initial scope).

Rationale is in the rightmost column. Each task header below also
carries its assignment inline.

| Task | Model | Effort | Why this tier |
|------|-------|--------|---------------|
| **T-S1.0** staleness spike | fable | high | Forensic: reads manifest/staleness code, runs empirical test, produces a verdict that gates T-S1.3. Judgment-heavy, not pattern-matching. |
| **T-S1.1** ScopeRecord field | sonnet | med | Mechanical dataclass addition + back-compat + validation. Single file, clear spec. |
| **T-S1.2** ProfileGate module | opus | xhigh | New module: scope matching, overlap resolution (most-specific-prefix-wins), layered resolution (explicit→auto→default). Logic is well-specified but has edge cases. |
| **T-S1.3** Inject gate at 10+5 sites | opus | high | 10 WorkerFactory injection sites + 5 processor edits. Mechanical per-site, but blast radius is large (worker factory is central) and the loaders.py trap must be respected. |
| **T-S1.5** Orchestrator per-stage skip | fable | xhigh | New central surface in the orchestrator stage dispatch. Manifest entries must interact correctly with staleness (T-S1.0 verdict) and dashboard status. Subtle, load-bearing. |
| **T-S1.6** group_reasoning filter | sonnet | med | Small, well-defined filter insertion before `build_dependency_groups`. Follows the gate pattern established by T-S1.2/T-S1.3. |
| **T-S1.4** Scopes API exposure | sonnet | med | Simple API plumbing: request model field, pass-through, summary inclusion. Single router file. |
| **T-S2.1** CATALOGUE profile prompts | opus | xhigh | Prompt design for REFDOC/CONFIG roles + routing the batched path (`build_batched_doc_prompt`, not just unbatched). Cost-model awareness (800 vs 16K calls). |
| **T-S2.2** ENRICHMENT profile prompts | sonnet | high | Follows T-S2.1's pattern (one branch, profile resolution first). One prompt ships dormant. Simpler than T-S2.1. |
| **T-S2.3** ATLAS prompt variants | opus | high | Corpus-orientation and host-orientation prompt design + segment-level dominant-profile routing. Prompt quality matters for atlas usefulness. |
| **T-S2.4** atlas_deep_dirs knob | sonnet | med | Small config plumbing: read project config in `_group_by_directory`, union with `_DEEP_DIRS`. Two files, clear spec. |
| **T-S2.5** Shared build-time edge loader | fable | xhigh | Generic bug fix (external edges silently never affected build-time intelligence). New helper + two delegations + ID normalization verification (Halbert's `file:`-prefixed IDs vs internal node IDs — unknown until investigated). |
| **T-S2.6** Phase S2 tests | sonnet | high | Test writing across new features. Mechanical-to-moderate, follows existing test patterns. |
| **T-H1.1** Unified staging root | sonnet | med | Path constant changes in two scripts. Mechanical, clear spec. |
| **T-H1.2** Template spec + apply script | fable | max | Keystone integration: YAML template, find-or-create project, PUT config, scope reconciliation (create→add-paths, two calls per scope), async build sequence with poll-to-complete (3 operational gaps), idempotency, legacy retirement flag. Most complex single task. |
| **T-H1.3** Client scope param + trace_expand | sonnet | high | Client request-body change + intake-domain→scope mapping logic. Moderate, well-specified. |
| **T-H1.4** ConfigWatcher → unified project | sonnet | med | Callback rewiring from old registrar to `apply(build_fast_sync_only=True)`. Small, clear spec. |
| **T-V.0** Corpus classification pre-flight | opus | high | Empirical measurement + decision rules that affect catalogue on/off and edge-filter fallback. Judgment-heavy, data-driven. |
| **T-V.1** Manifest gating evidence | sonnet | med | Verification: read manifests, assert expected entries. Bounded. |
| **T-V.2** Retrieval quality gate | sonnet | high | Extend existing script with 20 scoped queries + assertions. Moderate. |
| **T-V.3** Trace expansion verification | sonnet | med | Manual verification queries on both scope families. Bounded. |
| **T-V.5** Group reasoning e2e (C3) | sonnet | med | End-to-end verification that C2 fix produces clusters + groups. Bounded. |
| **T-V.4** Doc hygiene updates | sonnet | med | Documentation cross-references. Mechanical. |

**Tier distribution:** 4 fable, 6 opus, 13 sonnet. The fable tasks
(T-S1.0, T-S1.5, T-S2.5, T-H1.2) are the load-bearing judgment /
novel-surface / generic-bug tasks; everything else is implementation
against a clear spec and can run on opus or sonnet.

**Parallelization note:** within each phase, tasks that don't depend on
each other can run concurrently on different tiers. The dependency
graph (below) shows the critical path; off-critical-path tasks (e.g.
T-S1.4, T-S1.6, T-S2.4, T-H1.1) can be assigned to sonnet agents in
parallel with the fable/opus tasks they don't block.

---

## API execution findings (re-check 2026-08-24)

End-to-end verification of the apply-script build sequence against the daemon
API (every step checked against source, file:line below). **Verdict: the
sequence executes and produces one working project, conditional on S1/S2
landing first and on the three operational fixes in the next section.**

### Confirmed working

- **One project is achievable.** `POST /projects` accepts `mode="standalone"`
  (valid values: standalone/embedded/custom, `crud.py:54-55`) + an arbitrary
  non-repo root that merely `exists()` and `is_dir()` (`crud.py:71-77`). **No
  git requirement.** Standalone index lands in XDG
  (`~/.local/share/sourceprep/projects/{id}`), pointer file in the root
  (`project_registry.py:55-65,250`).
- **Config PUT is free-form** (`config: Dict[str, Any]`, `models.py:78`) →
  `atlas_deep_dirs` and `disabled_stages` store verbatim, no schema change
  needed. `auto_config` deep-merges (`crud.py:369-376`); `true/"manual"/"manual"`
  is accepted (`orchestrator.py:2011,2059`).
- **Scopes:** create + `POST /scopes/{id}/add` execute; `global` is synthetic
  & un-creatable (`scope_store.py:7,81`) — safe.
- **Build endpoints are distinct & correctly ordered:** `POST /projects/{id}/build`
  (CodeIndex, `build.py:22`) vs `POST /pipeline/fast` (trace graph,
  `pipeline.py:132`). `orchestrator.py:2336` confirms fast_sync does NOT build
  CodeIndex — so "CodeIndex build → fast_sync" as two calls is the right model.
- **External-edges ordering correct:** endpoint requires trace built
  (`query.py:629`, else 409 `TRACE_NOT_BUILT`) and validates source/target
  nodes exist (`query.py:678`) → must be after fast_sync. Plan's ordering holds.
- **deep_enrichment blocks only if fast_sync is *active*** (`orchestrator.py:1082`),
  no hard cross-group barrier — host fast_sync can proceed during docs
  deep_enrichment (scoped barriers, Phase 117). This largely **defuses the
  one-vs-two barrier-contention concern** (scrutiny Risk 2).

### Expected no-ops today (unblocked by S1/S2 — NOT defects)

- `pipeline_profile` on scope create: field absent today, silently dropped by
  Pydantic → unblocked by **T-S1.4**.
- `atlas_deep_dirs` / `disabled_stages`: stored, never consulted today →
  unblocked by **T-S2.4** / **T-S1.5**.

Both are consistent with the dependency graph (H1 needs S1/S2 deployed in the
daemon). The plumbing targets (free-form config, scopes CRUD) are confirmed to
exist, so S1/S2 can land.

### Three operational gaps the apply script MUST handle — T-H1.2 amendment

1. **Async polling between build steps.** `POST /pipeline/fast`, `/deep`,
   `/finalize` are async (return `{started:true}`). The T-H1.2 step-4 sequence
   reads as synchronous — it is not. Without polling
   `GET /projects/{id}/pipeline/status` (`pipeline.py:432`) and CodeIndex build
   status (`GET /projects/{id}/status`) to completion between steps:
   - Pushing external edges before fast_sync completes → **409 `TRACE_NOT_BUILT`**.
   - Starting fast_sync before the CodeIndex build completes → concurrent
     heavy I/O (no mutual exclusion between `build_manager` and
     `pipeline_orchestrator`).
   → **Add explicit poll-to-complete between each step of the build sequence.**

2. **Redundant CodeIndex re-embed.** deep_enrichment auto-triggers
   `_trigger_code_index_build` on completion (`orchestrator.py:2342`), which
   **overwrites** the explicit first CodeIndex build with enriched embeddings.
   The explicit first build is wasted for a one-shot apply. → Either **drop**
   the explicit CodeIndex build (let deep_enrichment trigger it) or keep it
   **deliberately** only if mid-sequence retrieval is required. Make the choice
   explicit — don't accidentally double-embed a 16K-doc corpus.

3. **Daemon-restart race.** Startup auto-runs fast_sync for
   `auto_config.fastSync=true` + active + stale projects (`server.py:1140`). If
   the daemon restarts mid-apply, it auto-fires fast_sync and races the
   script's explicit calls. → Set `auto_config.fastSync=false` (manual) **during
   apply**, flip to `true` after the build verifies; OR document that the daemon
   must not restart mid-apply. (Note: PUT config does NOT auto-fire fast_sync —
   `crud.py:510` reads a different `fast_sync_auto` field — so the race is
   restart-only, not PUT-triggered.)

### Minor notes

- `trace.ignore_patterns` is **dropped from PUT config** (`crud.py:367`); owned
  by `POST /trace/ignore`. Template only sets `trace.enabled` today — fine; use
  the dedicated endpoint if ignore_patterns are added later.
- **Watcher is NOT auto-started on project creation** (`watch.py:72`). Halbert's
  ConfigWatcher (T-H1.4) must explicitly `POST /projects/{id}/watch/start`. It
  works on non-repo dirs (watchdog, no git dependency, `watcher.py:144`).

### One-vs-two project decision (scrutiny Risk 2 — resolved)

Proceeding with one project is sound. The main concern (barrier contention
between slow docs deep_enrichment and fast host config edits) is largely
defused by scoped barriers — host fast_sync can proceed during docs
deep_enrichment. Remaining losses vs two projects: project-level
`path_weights`/`role_weights`/`primer` can't differ per corpus (scope weights
are reserved v1.1) — scope masking at query time is the v1 substitute and is
sufficient. Concurrency is daemon-wide either way (budget divided across
active projects, `scheduler.py`), so one project gets the **full** budget —
actually better than two. **Decision stands; no further analysis needed.**

### Opportunities documentation (confirmed)

The SourcePrep-side generic opportunities are captured in
`/Volumes/4TB-BAD/HumanAI/CoDRAG/.handoff/HANDOFF-HALBERT-TEMPLATE-FOLLOWUPS-2026-08-24.md`
as F1–F7: F1 per-scope model-slot overrides, F2 declarative scopes in
project.json, F3 template registry (`prep add --template`), F4 tree-sitter
config grammars, **F5 doc-aware CONCEPTS pass (endorsed by scrutiny §5)**, F6
dashboard UI for `pipeline_profile`, F7 KnowledgeIndex input-tolerance audit.
In-scope generic work (external-edges shared loader T-S2.5, per-stage skip
T-S1.5, atlas_deep_dirs T-S2.4, per-content-type ATLAS T-S2.3, profiles S1)
ships with the template itself. **Nothing is undocumented.**
