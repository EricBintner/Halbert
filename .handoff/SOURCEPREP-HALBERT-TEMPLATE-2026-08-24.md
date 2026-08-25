# SourcePrep→Halbert Template — Design & Implementation Plan

**Date:** 2026-08-24
**Status:** Plan — awaiting approval
**Supersedes:** the two-project split assumption in RAG-OPTIMIZATION-PLAN-2026-08-23.md §S1 and IMPLEMENTATION-PLAN-2026-08-23.md T0a.1 / T5a.1

---

## 1. Why

Halbert currently plans two SourcePrep projects: `halbert-host` (live config
tree) and `halbert-knowledge` (static doc corpus). Two projects means two
daemons-side registries, two builds, two retrieval targets, and a permanent
split-brain in Halbert's integration code. SourcePrep supports multiple named
scopes per project, so one project with two scope *families* is possible.

The blocker: SourcePrep's 15-stage pipeline runs project-wide, and its LLM
stages are tuned for **code**. Running them naively over 28,869 docs of man
pages / handbook / Homebrew prose wastes hours of LLM time and can actively
degrade retrieval (trace expansion into unrelated neighbor chunks, nonsense
module tiers). Conversely, some LLM stages genuinely *help* docs (CATALOGUE's
doc path, ATLAS orientation) and some genuinely help host config (CATALOGUE
config role, GROUP_REASONING over related units, ATLAS of the config tree).

The answer is not "turn LLM off for docs." It is a **per-scope pipeline
profile** — a named stage matrix + prompt variant set — with a Halbert
template that wires everything up in one project.

---

## 2. Research Findings (verified against source)

### 2.1 The parser reality

> **Corrected 2026-08-24 after SourcePrep scrutiny (C1).** The original
> text claimed markdown produces no trace edges. That was wrong — drawn
> from a truncated grep result. Verified directly:

The Rust parser dispatches on language at `prep-parser/src/lib.rs:181-200`:
python, typescript, go, rust, java, c/cpp, **markdown** all have analyzers;
12 more languages return file-level nodes only. Config files (.service,
.conf, .plist, fstab) hit `UnsupportedLanguage` → **file-level nodes, zero
structural edges** (this half of the original claim holds).

Markdown, however, has a real analyzer (`prep-parser/src/markdown.rs`)
emitting three edge kinds into `trace_edges.jsonl`:

- `contains` — file → section headers (conf 1.0, `markdown.rs:156-173`)
- `references` — file → backtick-mentioned file paths (conf 0.9, `:175-196`)
- `links_to` — file → `[text](path)` targets (conf 1.0, `:198-220`)

These are traversed at query time (`core/trace/index.py:328-407`), so
**`trace_expand` on docs is real signal, not a no-op**: expansion pulls in
the hit document's own sections and its linked/cross-referenced docs.
Whether `references` edges (backtick path mentions) are signal or noise for
a man-page corpus is empirical — dangling targets (e.g. `/etc/...` paths
that don't exist under the project root) simply don't resolve. Verify edge
counts on the real corpus before finalizing retrieval flags (Phase V task).

All files still reach the CodeIndex and get embedded regardless of grammar
support (`core/index.py:574-577`).

### 2.2 Existing per-file-type behavior (already in SourcePrep)

| Mechanism | Location | Behavior |
|---|---|---|
| INFERRED_EDGES skips markdown | `core/inferred_edges.py:202` | `language not in (None, "markdown")` |
| CATALOGUE doc path | `core/augmenter.py:1008-1100` | `_augment_markdown_file()` with DOC_ROLE_PROMPT: doc_type, doc_status, cross-refs, related files |
| CATALOGUE config role | `core/augmenter.py:639` | `_infer_role_from_path()` → `role="config"` for .json/.toml/.yaml/.ini/.env |
| EPISTEMIC doc path | `core/epistemic_enrichment.py:96-147,502` | EPISTEMIC_DOC_PROMPT: decision_chains, doc_type, doc_status; 3000-line excerpt vs 150 for code |
| CLUSTERING layer separation | `core/cluster.py:589-608,673-678` | `_DOCS_PATTERNS`, `_CONFIG_PATTERNS` → separate "docs"/"config" layers |
| Per-file gating chokepoint | `workers/base.py:62-72` | Every LLM worker calls `should_process(file_path)` |
| Policy-filtered node loading | `load_filtered_trace_nodes()` | Shared loader already applies `effective_excludes()` path filtering |

The pipeline already *half*-knows about docs and config. What's missing is
(a) per-scope control over which stages run, and (b) prompt variants tuned
for **reference documentation** and **system config** rather than project
docs and code.

### 2.3 Stage-by-stage verdict for Halbert's two content types

| # | Stage | Type | Host config value | Doc corpus value | Notes |
|---|-------|------|-------------------|------------------|-------|
| 1 | STRUCTURAL | Rust | RUN — file nodes anchor external edges | RUN — header chunking feeds embeddings | Cheap. Required. |
| 2 | INFERRED_EDGES | LLM | **SKIP** — Halbert's deterministic `edge_extractor.py` is strictly better than LLM guessing at config refs | Already skipped (markdown guard) | Saves the "code" model slot. |
| 3 | CATALOGUE | LLM | RUN — config role summaries aid retrieval ("this unit mounts /data before backup") | RUN — doc_type classification (reference vs guide) + SEE ALSO cross-refs | Needs prompt variant for both (§4.3). |
| 4 | VALIDATION | Rust | RUN | RUN | Pass-through, free. |
| 5 | KNOWLEDGE | Embed | RUN | RUN | **The core value.** |
| 6a | ENRICHMENT | LLM | RUN — config-aware prompt (what this config controls, conflicts); ~50 files, cheap | **OFF in v1** — cost (~1,000+ large-slot calls) disproportionate; flip-on path after quality gate (§5.2). Doc prompt exists but needs reference-doc variant when enabled | 3000-line excerpt path already exists for docs. |
| 6b | GROUP_REASONING | LLM | **RUN** — sshd_config + drop-ins + systemd unit as one policy unit. **Precondition: C2 fix** — external edges must reach clustering (they don't today; see §5b) or config files are all singleton clusters and no groups form | **SKIP** — docs' only file↔file edges are markdown references/links_to (sparse cross-doc), so groups are mostly empty and dropped by min_group_size=2 anyway | |
| 7 | CLUSTERING | LLM | RUN — config domains (network/auth/storage) as modules | RUN — Louvain on sparse graph falls back to directory-ish clusters; module summaries = topic areas ("storage tools", "networking daemons") | Feeds ATLAS. |
| 8 | DEEPENING | LLM | SKIP — iterative refinement overkill for small config files | SKIP — 16K docs × refinement = huge cost, marginal gain | |
| 9 | DEEP_KNOWLEDGE | Embed | RUN | RUN | Re-embeds with enriched data. |
| 11 | ATLAS | LLM | RUN — orientation doc of the host config tree = Halbert ambient context | **RUN** — user's instinct confirmed: orientation doc ("16K docs, platform coverage, which sources answer which questions") + segment routing boost = platform-aware retrieval | Needs doc/config prompt variants (current ATLAS_PROMPT expects modules/imports/architecture layers). |
| 12 | RULES | Rust | SKIP — generated AGENTS.md targets repo agents, not Halbert | SKIP | Cheap either way; skipping keeps outputs clean. |
| 13 | CONCEPTS | LLM | SKIP — prompt expects architectural decisions/coupling/falsifiable grep tests | SKIP — same | Halbert's WHY-facts come from its own findings system, not SourcePrep concepts. Revisit later with a custom doc-concepts pass if needed. |
| 14 | AUDIT | LLM | SKIP — config audit is Halbert's own job (findings/precedence.py) | SKIP | |
| 15 | ANTIBODIES | Rust | SKIP — immune system guards code edits | SKIP | No concepts → nothing to derive from. |

### 2.4 Config surface available (verified)

Project config knobs that exist today: `include_globs`, `exclude_globs`,
`included_paths`, `max_file_bytes`, `hard_limit_bytes`, `use_gitignore`,
`trace.enabled`, `trace.ignore_patterns`, `auto_rebuild.{enabled,debounce_ms}`,
`auto_config.{fastSync,deepEnrichment,finalize}` (`manual`/`auto`/`scheduled`),
`priority_level`, `path_weights`, `role_weights`, `primer`.

Scope system: `ScopeRecord{id, display_name, paths, weights(reserved v1.1),
assigned_to_role}`, full CRUD at `/projects/{id}/scopes`, `scope_orchestrator`
reacts to path add/remove/change with debounced rebuilds, query-time scope
masking via `scope_resolver.resolve_mask()` (works today, stored in
settings_store — **the REMAINING-WORK §1.6 "blocked upstream" note is stale**;
scopes were never blocked, just never created via the API).

**No template/preset mechanism exists.** Stack presets only suggest glob
patterns. `prep add` accepts only path/name/mode/index-path.

**Watcher** observes the whole project root; rebuilds are incremental via
changeset gating, so a config edit in one scope does **not** reprocess doc
files (they fail the changeset gate). One unified root is safe.

### 2.5 Halbert-side retrieval contract

- Primary: `POST /projects/{id}/context` — structured, k=5, max_chars=12000,
  min_score=0.15, trace_expand=True (currently hardcoded).
- `scope=` param is referenced in the retrieval backend but **not implemented
  in `SourcePrepClient.get_context()`** — needs wiring.
- Edge push: `POST /trace/external-edges` with `replace_origin="config"`.
- Query domains from intake signals: storage, backup, service, network,
  security, config → these should map to scopes.
- Corpus: 28,869 docs across linux/ (arch-wiki, man-pages, tldr,
  system-docs…), macos/ (homebrew 8,777, man-pages, support,
  ask-different, macports), bsd/ (freebsd), common/ (git, docker, shell…).

---

## 3. Design

### 3.1 One project, scope families

```
~/.local/share/halbert/sourceprep/        ← single SourcePrep project root ("halbert")
  host/                                    ← staged from live config (register_host_project.py)
    etc/ssh/sshd_config
    etc/systemd/system/*.service
    ...
  knowledge/                               ← jsonl_to_markdown.py output (moved from data/staging/sourceprep/)
    linux/  macos/  bsd/  common/
```

Named scopes (created via API):

| Scope | Paths | Profile |
|---|---|---|
| `host` | `["host/"]` | `system_config` |
| `knowledge-linux` | `["knowledge/linux/"]` | `prose_docs` |
| `knowledge-macos` | `["knowledge/macos/"]` | `prose_docs` |
| `knowledge-bsd` | `["knowledge/bsd/"]` | `prose_docs` |
| `knowledge-common` | `["knowledge/common/"]` | `prose_docs` |

Unscoped queries hit everything (union); scoped queries get the mask.
Platform routing = scope selection, driven by Halbert's intake signals +
atlas segment routing boost (§3.4).

### 3.2 SourcePrep change: `pipeline_profile` on scopes

Add to `ScopeRecord`:

```python
pipeline_profile: str = "code"   # "code" | "prose_docs" | "system_config"
```

A profile is a built-in named stage matrix (lives in SourcePrep, not in the
template, so any app can reuse them):

```python
PIPELINE_PROFILES = {
    "code": { ...all stages enabled... },              # today's behavior
    "prose_docs": {
        "inferred_edges": False, "catalogue": True, "enrichment": True,
        "group_reasoning": False, "clustering": True, "deepening": False,
        "atlas": True, "rules": False, "concepts": False,
        "audit": False, "antibodies": False,
        # rust/embed stages always run
    },
    "system_config": {
        "inferred_edges": False, "catalogue": True, "enrichment": True,
        "group_reasoning": True, "clustering": True, "deepening": False,
        "atlas": True, "rules": False, "concepts": False,
        "audit": False, "antibodies": False,
    },
}
```

### 3.3 Enforcement — three mechanisms, not one

> **Corrected 2026-08-24 after SourcePrep scrutiny (M1).** The original
> text named `Worker.should_process` as the single chokepoint. Verified
> per-stage: only **5 of 11** LLM/embed stages gate per file
> (inferred_edges, catalogue, enrichment, deepening, deep_knowledge).
> The other six have different units of work — per-group, whole-graph,
> per-module, per-concept — where a per-file gate is wrong or meaningless.

The profile matrix is enforced by three mechanisms:

1. **Per-file gate** — for the 5 per-file stages. Inject `profile_gate`
   parallel to `.changeset` (WorkerFactory injection sites: 10, not 7 —
   `workers/__init__.py` lines ~504, 751, 816, 960, 1034, 1099, 1153,
   1211, 1389, 1403). This is where the real LLM cost saving lives.
2. **Per-stage skip flag at the orchestrator** — for stages a profile
   disables entirely (deepening, rules, concepts, audit, antibodies).
   This mechanism **does not exist today**: `auto_config` gates whole
   stage-*groups* (fastSync/deepEnrichment/finalize,
   `orchestrator.py:1971-2044`), not individual stages. Since a mixed
   project needs `atlas: True` while `concepts: False` — both in the
   finalize group — a per-stage enable check is new orchestrator surface:
   when ALL scopes bearing content disable stage S (or the project's
   profile config lists S as disabled), skip S with a manifest note, not
   a failure.
3. **Input-set filtering** — for `group_reasoning`: filter the epistemic
   set fed to `build_dependency_groups` so docs never form groups.
   For Halbert this is nearly automatic (sparse doc edges + min_group_size=2
   drops them), but the mechanism must exist for the general case.

**`audit` and `antibodies` are all-or-nothing per project, never per-file
gates** — excluding doc nodes from audit's whole-graph analyzers would
change findings (topology, hub scores), not just cost.

Files with **no** scope membership keep the default `code` profile —
behavior unchanged for every existing SourcePrep user. **Overlapping
scopes**: most-specific path prefix wins; tie → lowest scope id
(deterministic). The Halbert template keeps scopes disjoint by
construction; ProfileGate logs a warning on overlap.

### 3.4 Prompt variants per profile

Profiles also select prompt variants where content-type matters:

| Stage | `prose_docs` variant | `system_config` variant |
|---|---|---|
| CATALOGUE | Reference-doc prompt: doc_type ∈ {man_page, handbook_chapter, guide, formula, faq}; drop doc_status; extract SEE ALSO / cross-refs | Config prompt: what directive set this file controls, which service it configures, risk notes |
| ENRICHMENT | Reference-doc epistemic: topic domain tags (storage/network/auth), platform, command coverage; drop decision_chains | Config epistemic: controlled resources, conflicts with other files, effective-value notes |
| ATLAS | Corpus orientation: platform coverage, doc-type mix, "which source answers which kind of question", segment descriptors per platform dir | Host orientation: "this host's config surface — services, mounts, network, auth policy", segment = config domain |
| CLUSTERING | (no variant needed — Louvain + synthesis works off enriched summaries) | same |

Selection mechanism: the stage worker resolves the file's scope profile once
per file and passes `profile` into the prompt builder. Prompts live in
SourcePrep alongside the existing ones (`augmenter.py`,
`epistemic_enrichment.py`, `atlas/prompts.py`) — keyed by profile name, so
they're versioned with SourcePrep and reusable by other apps.

### 3.5 Query-time routing (Halbert side)

> **Corrected 2026-08-24 after SourcePrep scrutiny (C1).** Original text
> set `trace_expand=False` for docs on the false premise that docs have no
> edges.

- `SourcePrepClient.get_context()` gains `scope` param (plumb through to the
  request body — the API already supports it).
- `SourcePrepRetrievalBackend` maps Haloysius `figure_id` → scope.
  `trace_expand` is **True for all scopes**: host follows Halbert's external
  edges; knowledge-* follows markdown `contains`/`links_to` edges (a hit
  expands to the doc's own sections and cross-linked docs — real signal).
  Final confirmation after the corpus edge-count measurement (Phase V) —
  if `references` edges prove noisy on the real corpus, add a doc-scope
  edge-kind filter (`contains`/`links_to` only) rather than disabling
  expansion.
- Halbert intake signals (storage/network/security/…) map to the knowledge
  platform scopes + `host` for config questions. `include_atlas=True` on
  ambient/first-turn calls for orientation.

### 3.6 The template itself

A declarative spec in Halbert's repo —
`halbert_core/halbert_core/integrations/sourceprep_template.yml` —
applied by a setup script (extends `register_host_project.py`):

```yaml
project:
  name: halbert
  root: ~/.local/share/halbert/sourceprep
  config:
    include_globs: ["host/**", "knowledge/**/*.md"]
    exclude_globs: ["**/ssl/**", "**/shadow", "**/gshadow", "**/*.key", "**/*.pem"]
    max_file_bytes: 500000
    use_gitignore: false
    trace: {enabled: true}
    auto_config: {fastSync: true, deepEnrichment: manual, finalize: manual}
scopes:
  - {id: host, paths: ["host/"], pipeline_profile: system_config}
  - {id: knowledge-linux, paths: ["knowledge/linux/"], pipeline_profile: prose_docs}
  - {id: knowledge-macos, paths: ["knowledge/macos/"], pipeline_profile: prose_docs}
  - {id: knowledge-bsd,   paths: ["knowledge/bsd/"],   pipeline_profile: prose_docs}
  - {id: knowledge-common, paths: ["knowledge/common/"], pipeline_profile: prose_docs}
post_build:
  - push_external_edges: {origin: config}     # edge_extractor.py output
  - verify: scripts/corpus_quality_gate.py    # 20-query gate
```

Application = pure API calls (PUT project config, POST scopes, build).
Idempotent. Re-run on every Halbert startup / config change (debounced).

**End users without SourcePrep:** unchanged — retrieval falls back to
ChromaDB; the template only applies when the daemon is reachable.

---

## 4. Work breakdown

### Phase S1 — SourcePrep: scope pipeline profiles (~350 lines + tests)

| Task | Where | Est. |
|---|---|---|
| S1.1 `pipeline_profile` field on ScopeRecord + from_dict/to_dict | `core/scope_store.py` | 15 |
| S1.2 `PIPELINE_PROFILES` stage matrices (code/prose_docs/system_config) | `core/pipeline_profiles.py` (new) | 60 |
| S1.3 Path→profile resolver (reuse `path_matches_any_scope`) | `core/scope_resolver.py` | 25 |
| S1.4 Profile gate in `should_process` (+ stage_id/project_id threading through WorkerFactory) | `workers/base.py`, `workers/__init__.py` | 80 |
| S1.5 API: create/update scope accepts `pipeline_profile`; GET returns it | `api/routers/scopes.py` | 20 |
| S1.6 Tests: profile gating per stage, default-code back-compat, unknown-profile fallback | `tests/` | 150 |

### Phase S2 — SourcePrep: prompt variants (~300 lines + tests)

| Task | Where | Est. |
|---|---|---|
| S2.1 CATALOGUE: reference-doc + config prompts; select by profile | `core/augmenter.py` | 90 |
| S2.2 ENRICHMENT: reference-doc + config epistemic prompts; select by profile | `core/epistemic_enrichment.py` | 90 |
| S2.3 ATLAS: corpus-orientation + host-orientation prompts; select by dominant profile of segments | `core/atlas/prompts.py`, `generator.py` | 90 |
| S2.4 Tests: prompt selection, output shape for man page + sshd_config fixtures | `tests/` | 60 |

### Phase H1 — Halbert: unify + template (~250 lines)

| Task | Where | Est. |
|---|---|---|
| H1.1 Unified staging root; register_host_project.py stages to `sourceprep/host/`; jsonl_to_markdown.py outputs to `sourceprep/knowledge/` | `tools/register_host_project.py`, `rag/jsonl_to_markdown.py` | 40 |
| H1.2 Template spec + idempotent apply script (project config, scopes, build) | `integrations/sourceprep_template.yml`, `integrations/sourceprep_setup.py` | 120 |
| H1.3 `get_context(scope=...)`; retrieval backend per-scope trace_expand; intake-domain→scope mapping | `integrations/sourceprep_client.py`, `sourceprep_retrieval_backend.py` | 60 |
| H1.4 ConfigWatcher → unified project (re-stage host/, incremental rebuild, push edges with replace_origin) | `config/watcher.py` | 30 |

### Phase V — Verification

| Task | Est. |
|---|---|
| V.1 Build unified project on dev machine; confirm stage skips in manifests (doc scopes: no enrichment entries for group_reasoning/deepening/audit; host scope: no inferred_edges) | — |
| V.2 Corpus quality gate: 20 queries through scoped retrieval, platform routing correct (linux query → no macos chunks) | — |
| V.3 Host config query path: trace expansion follows external edges (sshd_config → drop-ins) | — |
| V.4 Update REMAINING-WORK §1.6 (stale "blocked upstream" note), RAG-OPTIMIZATION-PLAN §S1, IMPLEMENTATION-PLAN T0a.1/T5a.1 as-built notes | — |

### Sizing

~900 lines total across both repos, of which ~210 are tests. The heavy
thinking is in the prompt variants (S2) — the machinery (S1) is small
because the gating chokepoints already exist.

---

## 5. Decisions (resolved 2026-08-24, user accepted recommendations)

1. **Built-in profiles in SourcePrep.** `prose_docs` and `system_config`
   ship as SourcePrep built-ins; prompts version with SourcePrep. Halbert's
   template references profiles by name only — no prompt text crosses the
   API.
2. **ENRICHMENT off for `prose_docs` v1.** 16K docs ÷ epistemic_doc batch
   (3-15/call) ≈ 1,000+ large-slot calls — disproportionate for v1.
   `prose_docs` runs CATALOGUE (small slot, ~160 calls at LARGE batch) +
   CLUSTERING + ATLAS off catalogue summaries. `system_config` runs
   ENRICHMENT (~50 host files, cheap). Flip path: change the profile matrix
   entry and rebuild deep_enrichment — no code change.
3. **ATLAS segmentation gets a config knob.** Verified: `_group_by_directory`
   (`core/atlas/routing.py:277`) groups depth-1 by default, depth-2 only
   under hardcoded `_DEEP_DIRS` (src/, packages/…). Halbert's tree would
   yield only `{host, knowledge}` segments — too coarse for platform
   routing boosts. Add project config `atlas_deep_dirs: ["knowledge"]`
   (unioned with `_DEEP_DIRS`) → segments become `knowledge/linux`,
   `knowledge/macos`, etc.
4. **CONCEPTS stays off** for both profiles (prompt expects code
   architecture, coupling, falsifiable grep tests). Halbert's WHY-facts
   come from its own findings system. A doc-concepts pass is a possible
   future SourcePrep follow-up — see HANDOFF-SOURCEPREP-FOLLOWUPS doc.
5. **Homebrew corpus stays** in v1 (already cleaned/deduped in Phase 0);
   quality gate will tell us if it earns its budget.

## 5b. Fit-check amendments (verified against source 2026-08-24)

Confirmed clean fits:

- **WorkerFactory injection.** `create_worker(project_id, stage)` has both
  values at construction; `.changeset` attribute injection is the
  established pattern at 6+ sites (workers/__init__.py:504-508, 751, 816,
  960, 1034, 1099, 1153). `.profile_gate` is a parallel injection.
- **Prompt selection.** Binary `is_markdown` checks at `augmenter.py:917`
  and `epistemic_enrichment.py:502` become profile-keyed prompt-map lookups.
- **ScopeRecord field.** `from_dict` uses `.get()` defaults — adding
  `pipeline_profile` is back-compat with old serialized records; TS
  consumers (`packages/ui`, dashboard `useScopes`) are additive-tolerant.

Gaps found, pulled into scope — **amended 2026-08-24** after scrutiny C2
found the gap is pipeline-wide, not one function:

- **External edges reach ZERO build-time consumers.** Not just
  `group_reasoning.load_edges()` (`core/group_reasoning.py:386-397`) —
  `cluster.py:1165-1176` has the identical two-file tuple, and grep across
  the build pipeline confirms no stage reads `trace_external_edges.jsonl`.
  External edges are loaded by `TraceIndex` at query time only. The fix is
  a **shared build-time edge loader** (new helper in
  `core/trace/loaders.py`, e.g. `load_all_build_edges()`) consumed by both
  `cluster.py` and `group_reasoning.py`. Without this, config files are all
  singleton clusters → no groups → the `system_config` group_reasoning
  value prop cannot occur (scrutiny C3; we take its option (a) — fund the
  full fix, keep `inferred_edges: False` for system_config).
- **Query-time loader must stay ungated.** `load_filtered_trace_nodes()`
  (`core/trace/loaders.py:28`) is shared by pipeline workers AND query-time
  search (`api/routers/projects/search.py:300`). Profile gating must live
  in the per-file worker consult points, never in the shared loader.
  (Scrutiny confirmed this warning was correct.)

Build sequencing (verified): CodeIndex (primary retrieval) and the pipeline
trace/enrichment indexes are separate build paths. The template apply flow
must order: project config → CodeIndex build → fast_sync → push external
edges → deep_enrichment → finalize. Replicates the proven sequences of the
existing two projects.

---

## 6. Scrutiny integration (2026-08-24)

SourcePrep-side review (SOURCEPREP-HALBERT-SCRUTINY-2026-08-24.md) verified
the plan's citations at ~95% and found three false load-bearing premises.
C1/C2 were re-verified by direct read before integration. Dispositions:

| Finding | Disposition |
|---|---|
| C1 markdown edges exist | Integrated — §2.1 rewritten, §3.5 flips trace_expand=True for docs (with edge-kind filter as fallback pending corpus measurement) |
| C2 external edges pipeline-wide gap | Integrated — §5b now scopes the shared build-time edge loader; implementation plan T-S2.5 rewritten |
| C3 system_config cascade | Resolved per scrutiny option (a): fund the full C2 fix, keep `inferred_edges: False` for system_config |
| M1 three enforcement mechanisms | Integrated — §3.3 rewritten; Phase S1 re-estimated (see below) |
| M2 audit/antibodies all-or-nothing | Integrated — noted in §3.3 mechanism 2 |
| M3 catalogue cost 800 not 160 | Accepted — doc sub-batch is 20/call at LARGE (`augmenter.py:1447`), and narrative files batch at 1. Mitigation: new REFDOC prompt work (T-S2.1) hooks the **batched** path with an explicit doc batch size; Phase V gains a corpus classification pre-flight that runs the real corpus through the three-way content-class split before the first full build. Decision rule: if >50% narrative, prose_docs v1 disables catalogue too |
| M4 deepening capped per-run | Accepted — framing correction: 200 calls/run cap, unbounded cumulatively; skipping still correct |
| M5 concurrency assumption | Accepted — "hours" assumed cloud_concurrency=1 (default); at 5-10 in-flight it's ~50min-2hrs. Halbert's template sets explicit concurrency expectations in the setup docs |

### Risk dispositions (scrutiny §6)

1. **Baseline-shrink/staleness (top implementation risk).** Partially
   verified: `Changeset.should_process` (changeset.py:44) returns True only
   for added/modified — a profile-skipped file goes `unchanged` next run and
   carries forward, so no changeset-driven re-entry loop. The write guard
   tolerates baseline shrink (orchestrator.py:56-62 comment, added after the
   2026-06-08 incident for exactly this class). **Still requires the
   pre-coding spike** (T-S1.0): confirm a worker returning skip-for-all-
   profile-files records the stage as stable/complete in its manifest, not
   pending.
2. **One-project-vs-two weighed.** Costs of merging: shared build barrier
   (a 16K-doc rebuild could block a config edit), shared project-level
   weights/primer (scope weights are reserved-v1.1, unimplemented), one
   blended root atlas, shared concurrency budget. Assessment: the barrier is
   group-scheduled and changeset-gated — host edits trigger incremental
   fast_sync only; the slow docs build is one-time. Weights aren't needed at
   launch. The blended atlas is mitigated by per-segment prompt variants
   (segments are per-corpus orientation docs). Concurrency contention is
   first-build-only for a single-user local app. The split-brain cost (two
   retrieval targets, two registrations, watcher complexity) dominates.
   **Verdict: one project stands.** Reversal path: the template format
   already supports emitting two projects if the barrier proves real in
   operation.
3. **Overlapping scopes:** resolution rule added to §3.3 (most-specific
   prefix, deterministic tiebreak, template keeps scopes disjoint).
4. **Per-file vs per-scope granularity:** adopt the scrutiny's layered
   model — resolution order: (1) explicit scope profile, (2) per-file
   content-type detection **only when the project opts in**
   (`auto_profile_files: true` config — off by default, preserving
   back-compat for existing repos where markdown is project docs), (3)
   `code` default. Halbert uses explicit scopes; the per-file layer ships
   disabled and is SourcePrep's dogfooding path for mixed src/+docs/ repos.
5. **scopes.py plumbing:** noted — template apply does create-scope then
   add-paths (two calls per scope); reflected in T-H1.2.

### Sizing re-estimate

The "~900 lines, machinery is small" framing covered only the per-file gate.
With the per-stage orchestrator skip flag (new surface), shared build-time
edge loader, and 10 injection sites: **~1,200-1,400 lines total** (S1 grows
~350 → ~550; S2 grows ~300 → ~350; H1 unchanged ~250; V +spike/classification
tasks). Still "flags and minor work" relative to a pipeline rewrite, but no
longer tiny.

---

## 7. What this supersedes / touches

- RAG-OPTIMIZATION-PLAN-2026-08-23.md §S1 ("define two SourcePrep projects")
  → **one project, two scope families**.
- IMPLEMENTATION-PLAN-2026-08-23.md T0a.1 (halbert-knowledge project) and
  T5a.1 (halbert-host project) → merge into H1 template application.
- REMAINING-WORK-2026-08-24.md §1.6 ("declarative project scopes blocked
  upstream") → **stale**; scopes work via settings_store + scope_resolver
  today. Close after H1.2 creates them.
- ROADMAP-2026-08-23.md Phase 0/2 (SourcePrep doc ingestion, RAG
  consolidation) → unchanged in intent; this plan is the *how* for the
  SourcePrep side.
