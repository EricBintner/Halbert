# SourcePrep→Halbert Plan — Scrutiny & Findings

**Date:** 2026-08-24
**Status:** Findings — for Halbert plan author + SourcePrep maintainers
**Responds to:** `SOURCEPREP-HALBERT-TEMPLATE-2026-08-24.md`
**Method:** Every claim below was reverse-engineered against SourcePrep source
(`main`, 2026-08-24) with file:line evidence. Citations verified by parallel
read-only agents; the three critical findings were re-verified by direct read.

---

## 0. Bottom line

The plan's **citations are ~95% accurate** — file:line references check out.
But three of its **load-bearing reasoning premises are false**, and they
cascade into the central `system_config` value prop. The plan is still viable,
but it needs real amendments, and the "~900 lines, machinery is small" sizing
is optimistic. One headline benefit (group reasoning over config units) does
not work as designed without a deeper fix than the plan identified.

Severity-ranked findings below. Each has a "Required amendment" so the plan
author can patch the plan directly.

---

## 1. CRITICAL findings

### C1. "Docs have no edges / trace is a clean slate Halbert owns" — FALSE

**Plan premise (§2.1):** "the Rust parser only has Python/TypeScript/Rust
grammars… markdown → no symbol nodes and no edges… the only meaningful trace
edges are the ones Halbert itself pushes via `POST /trace/external-edges`."

**Reality:** There is a dedicated `engine/crates/prep-parser/src/markdown.rs`
analyzer (dispatched at `prep-parser/src/lib.rs:194`) that emits three real
edge kinds for every markdown file:

- `contains` — file → section headers (`markdown.rs:156-173`)
- `references` — file → backtick-mentioned file nodes, conf 0.9 (`:175-196`)
- `links_to` — file → `[text](path)` targets, conf 1.0 (`:198-220`)

These are written to `trace_edges.jsonl`
(`prep-graph/src/lib.rs:793,1054-1061`) and traversed at query time
(`core/trace/index.py:328-407`, `get_neighbors`).

**Consequences:**

1. **`trace_expand` on docs is NOT a no-op.** It expands a doc to its sections,
   referenced files, and linked docs. The plan's §3.5 decision
   (`knowledge-* → trace_expand=False`, "no edges exist; avoids trace-index
   lookup") would **suppress real neighbor context**, not skip a no-op. The
   "avoids trace-index lookup" rationale is also moot — the lookup is a dict
   `.get()`, near-free (`index.py:385,391`).
2. **Halbert does not own a clean-slate trace graph.** A man page that
   backtick-mentions `sshd_config` will auto-create a `references` edge to the
   host's `sshd_config` file node — a **cross-scope edge**, automatically, with
   no Halbert code involved. These coexist with Halbert's pushed external
   edges.
3. The `inferred_edges` markdown guard (`core/inferred_edges.py:202`) blocks
   only the Stage-1.5 LLM analyzer. The augmenter's Pass 0.5
   (`core/augmenter.py:2091-2115`) writes markdown `related_files` hypotheses
   to `trace_inferred_edges.jsonl` with **no markdown filter** — so docs can
   also produce *inferred* edges.

**Required amendment:** Replace the "docs have no edges" premise. Decide
whether `markdown.rs` `references`/`links_to` edges are **signal or noise** for
Halbert's man-page/homebrew corpus:

- If **signal** (man-page → config linkage is useful): set `trace_expand=True`
  for doc scopes — the opposite of §3.5 — and let cross-refs flow.
- If **noise** (backtick command mentions creating spurious file refs): add an
  explicit edge filter for doc scopes and document it. Do not leave the
  decision resting on "no edges exist."

Either way, verify how many `references` edges `markdown.rs` actually emits for
the real corpus before trusting either choice — a man page mentioning
`/etc/ssh/sshd_config` resolves to a real file node; a man page mentioning
`grep` does not. The signal/noise ratio is empirical, not theoretical.

### C2. External edges are invisible to the ENTIRE build pipeline — not just group_reasoning

**Plan (§5b):** Found that `group_reasoning.load_edges()`
(`core/group_reasoning.py:386-397`) reads only `trace_edges.jsonl` +
`trace_inferred_edges.jsonl`, missing `trace_external_edges.jsonl`. Called it
"two gaps found, both small" and framed the fix as a one-line tuple extension.

**Reality:** The plan found **half** the gap. `core/cluster.py:1165-1176` —
clustering's `load_edges()` has the **identical** tuple. And clustering is
what *forms the groups* group_reasoning reasons over: `cluster.py:380-384`
builds the Louvain adjacency directly from those edges; `:710` "edge-based
adjacency"; `:762` "no edges → each node its own cluster."

Grep across the whole build pipeline: **no stage anywhere reads
`trace_external_edges.jsonl`.** External edges are a write-only / query-time
feature — loaded by `TraceIndex` for retrieval (`core/trace/index.py:173`) but
reaching zero build-time consumers.

**Consequence:** A one-line fix to `group_reasoning.load_edges()` is
**insufficient**. Even with that fix, `sshd_config` and its drop-in never land
in the same **cluster** (clustering never saw the external edge), so they never
form a **group**, so group_reasoning never reasons over them together. The fix
must be at the shared build-time edge-loading path — both clustering and
group_reasoning (and any other build-time edge consumer) must read
`trace_external_edges.jsonl`.

**Required amendment:** Replace the §5b "one-line tuple extension" fix with a
shared build-time edge loader that includes external edges, consumed by both
`cluster.py:load_edges` and `group_reasoning.py:load_edges`. This is a
SourcePrep-side change (see §4 — it's a generic bug fix, not Halbert-special).

### C3. Cascade: the `system_config` group_reasoning value prop is internally inconsistent

This is the damaging one. Trace the plan's own choices:

1. Config files (`.service`, `.conf`, `fstab`, `.plist`) have no grammar →
   **zero structural edges** (this part of §2.1 is correct — no AST, no
   `contains`/`references`/`links_to`).
2. The `system_config` profile sets `inferred_edges: False` ("Halbert's
   deterministic `edge_extractor.py` is strictly better than LLM guessing").
3. So config files' only possible edges are the external edges Halbert pushes.
4. But external edges don't reach clustering (C2).
5. → config files have **zero edges in clustering** → each is a singleton
   cluster → `min_group_size=2` drops them (`group_reasoning.py:218,258`,
   confirmed) → **group_reasoning produces no config groups at all**.

The plan's headline `system_config` benefit — "sshd_config + drop-ins +
systemd unit as one policy unit" (§2.3, stage 6b) — **cannot occur** under the
plan's own profile plus the unfixed clustering gap.

**What does survive:** the *query-time* benefit. `trace_expand` at retrieval
does follow external edges (`TraceIndex` loads all four edge files,
`index.py:129-173`), so "sshd_config → drop-ins" expansion works when a user
query hits the config. The value prop lives at retrieval, not at build-time
group reasoning.

**Required amendment — pick one:**
- **(a)** Fix external edges to flow into clustering (C2). Then
  `inferred_edges: False` for `system_config` is viable — Halbert's external
  edges carry the graph. This is the option that matches the plan's intent.
- **(b)** Set `inferred_edges: True` for `system_config` and let the LLM infer
  config relationships. Cheaper to build, but the plan explicitly rejected this
  ("LLM guessing is strictly worse than Halbert's deterministic extractor").
- **(c)** Accept that group_reasoning produces no config groups and drop the
  "one policy unit" value prop from the plan — rely on query-time trace_expand
  only.

The plan currently implies (a) but only pays for the group_reasoning half of
the fix. Make the choice explicit and fund the full fix if (a).

---

## 2. MAJOR findings

### M1. The per-file gate enforces only 5 of 11 stages — the profile matrix cannot be one chokepoint

**Plan (§3.3):** Enforcement lives in `Worker.should_process(path)`
(`services/pipeline/workers/base.py:62`), described as the single chokepoint
for the whole profile matrix.

**Reality:** Every stage's unit-of-work was reverse-engineered. `should_process`
is called by only 5 stages:

| Stage | Calls `should_process`? | Per-file gate works? |
|---|---|---|
| inferred_edges | Yes (`inferred_edges.py:230`) | ✅ |
| catalogue | Yes (`augmenter.py:490` via `_should_skip`) | ✅ |
| enrichment | Yes, via `cs.modified` (`epistemic_enrichment.py:468`) | ✅ |
| deepening | Yes (`deepening.py:141`) | ✅ |
| deep_knowledge | Yes, stage 10 only (`knowledge.py:482`) | ✅ |
| **group_reasoning** | **No** — per-**group**, staleness via `_group_is_stale` (`group_reasoning.py:326-339`) | ❌ per-file gate would *dissolve* groups |
| **clustering** | **No** — whole-graph Louvain over all file nodes (`cluster.py:662-665,779,981`) | ❌ can't skip files inside one Louvain pass |
| **atlas** | **No** — project-wide + per-segment (`atlas/generator.py:354-405`) | ❌ no file loop to gate |
| **concepts** | **No** — per-module swarm (`concept_seeder.py:725`, `concept_generate_swarm.py:134`) | ❌ operates on modules, not files |
| **audit** | **No** — whole-graph analyzers, no changeset check (`audit/runner.py:80-140`) | ❌ excluding docs changes findings, not just cost |
| **antibodies** | **No** — per-concept, no file dimension (`antibody_derivation.py:202-209`) | ❌ nonsensical at file level |

So the `PIPELINE_PROFILES` matrix (§3.2) is the right **intuition** (which
stages matter for which content) but the wrong **mechanism**. Enforcing it
needs **three** things, not one:

1. **Per-file gate** (`should_process`) — for the 5 per-file LLM/embed stages.
   This is where the real LLM cost saving lives (catalogue, enrichment,
   deepening). The plan's chokepoint works here. ✅
2. **Per-stage skip at the orchestrator** — for stages turned off entirely
   (deepening, rules, concepts, audit, antibodies). This mechanism **does not
   exist today**: gating is per *stage-group*
   (`auto_config.{fastSync,deepEnrichment,finalize}`; `orchestrator.py:1971-2044`),
   not per stage. The plan's matrix toggles `atlas: True` / `concepts: False`,
   both in the **finalize group** — you cannot do that with the group gate. A
   new per-stage enable flag is required.
3. **Input-set filtering** — for `group_reasoning` (filter the epistemic set
   fed to `build_dependency_groups`, `group_reasoning.py:906`, so groups reform
   without docs). For Halbert this is largely automatic: docs' only file↔file
   edges are markdown `references`/`links_to` (C1), and man pages rarely link
   to each other, so doc groups are mostly empty and dropped by `min_group_size=2`
   anyway. But the mechanism must exist for the general case.

**Required amendment:**
- Split §3.3's enforcement model into the three mechanisms above.
- Re-estimate Phase S1 (§4). The "~350 lines, machinery is small because
  gating chokepoints already exist" sizing covers only mechanism (1). The
  per-stage-skip flag (2) is new orchestrator surface and is not small.
- Note that `WorkerFactory` injects `.changeset` at **10 sites**, not the 7 the
  plan lists (§5b missed `workers/__init__.py:1211, 1389, 1403`). A parallel
  `.profile_gate` injection touches the same 10 sites.

### M2. Audit-as-cost-optimization is a semantic change, not a saving (latent)

The plan skips audit for both profiles (fine today). But if anyone later flips
audit on for docs and tries to gate it per-file: excluding doc nodes from
`load_audit_context` changes graph topology → changes circular-dependency and
hub-score **findings**, not just cost (`audit/runner.py:80-140`, no changeset
check). The profile model should not treat audit as a per-file toggle — it is a
whole-graph semantic.

**Required amendment:** Add a note in the profile spec that `audit` is
all-or-nothing per project, never a per-file/per-scope gate. Same for
`antibodies` (derived from concepts; no file dimension).

---

## 3. MODERATE findings

### M3. Catalogue cost for 16K docs is ~800 calls, not 160

**Plan (decision #2):** "CATALOGUE ~160 calls at LARGE batch."

**Reality:** 160 is the **code** batch (`CATALOGUE_FILE=100`,
`core/batch_profiles.py:89` → 16K/100 = 160). The **doc** sub-batch is
`batch_size//5 = 20` at LARGE (`augmenter.py:1447`) → 16K/20 = **800 calls**.
For "narrative" files the batch is `1` (`augmenter.py:1564`) → **16,000 calls**.

The augmenter's batched path (`_augment_files_batched`, `augmenter.py:1326`)
splits files into three content classes: structured-code / structured-docs /
narrative, each with its own batch size. `DOC_ROLE_PROMPT` (the prompt the plan
cites) is the *unbatched single-file* template (`augmenter.py:246-265`, used at
`:1039`); the batched doc path uses a different prompt
`build_batched_doc_prompt` (`augmenter.py:1488`).

**Impact:** The decision (catalogue on, enrichment off) still holds at the
structured-docs end — 800 catalogue calls < ~1,067 enrichment calls
(`EPISTEMIC_DOC=15` at LARGE, `batch_profiles.py:92`), and catalogue uses
smaller output slots. But:
- The estimate is off **5×** for structured docs.
- If Halbert's man-page/homebrew prose classifies as **narrative**, catalogue
  is 16,000 calls — *more* than enrichment — and the decision flips.

**Required amendment:** Before trusting catalogue-on, verify which content
class Halbert's corpus lands in (`_augment_files_batched`'s three-way split).
Report the empirical class mix. Re-state cost with the doc batch (20) or
narrative batch (1), not the code batch (100).

### M4. Deepening "huge cost" is per-run capped, unbounded cumulatively

**Plan (§2.3, stage 8):** "16K docs × refinement = huge cost, marginal gain."

**Reality:** `DeepeningLoop(max_iterations=10, batch_size=20)`
(`workers/__init__.py:1393`, `deepening.py:410,456`) → hard cap **200 LLM calls
per run**. "Huge" is only true cumulatively across many daemon runs (16K nodes
/ 20 per run ≈ 800 runs to cover once; `ConvergenceTracker` stops at
`settled_threshold=0.60` or `budget_exhausted`).

**Required amendment:** Re-frame as "capped at 200 calls/run, unbounded
cumulatively across runs." Skipping still saves real money; the per-run
framing is just inaccurate.

### M5. Concurrency reality for "hours" estimate

The "wastes hours of LLM time" framing is defensible but depends on the user's
`cloud_concurrency` endpoint setting, which is **AIMD-throttled** and **defaults
to 1** (`scheduler.py:2773`; jumpstart seed 5, `:169`; user "Max" plan = 10).
At `cloud_concurrency=1`, 1,067 enrichment calls × ~20s ≈ **5.9 hours**. At
5–10 in-flight, ~50 min–2 hrs. So "hours" is the worst case (default config),
not guaranteed.

**Required amendment:** State the concurrency assumption behind "hours."
Halbert should set `cloud_concurrency` explicitly or the enrichment-off
decision is justified only at the default-1 worst case.

---

## 4. What the plan got RIGHT (keep these)

- `group_reasoning` `min_group_size=2` → singleton groups dropped. ✓
- Docs get their own clustering layer (`_DOCS_PATTERNS`, `cluster.py:591`). ✓
- The `should_process` chokepoint + `WorkerFactory` injection pattern exist and
  are the right hook **for the per-file stages**. ✓
- Scopes work at query time (`resolve_mask`, Phase 120, `search.py:1256-1288`)
  — Halbert-side `scope=` wiring is trivial; the API already honors it. ✓
- `ScopeRecord.from_dict` uses `.get()` defaults → adding `pipeline_profile`
  is backwards-compatible. ✓
- No template/preset mechanism exists — real product gap. ✓
- `atlas_deep_dirs` is net-new and feasible (`routing.py:82` `_DEEP_DIRS` is a
  hardcoded frozenset). ✓
- Decision #1 (profiles + prompts version with SourcePrep; apps reference by
  name only; no prompt text crosses the API) is the right product principle. ✓
- The `/projects/{id}/trace/external-edges` endpoint + `replace_origin`
  semantics work as described (actual path includes the `/projects/{id}`
  prefix — `trace_routes/query.py:609`). ✓
- `load_filtered_trace_nodes` is shared by pipeline AND query-time
  (`loaders.py:28`; query site `search.py:296`) — the plan's warning to keep
  profile gating OUT of this shared loader is correct. ✓

---

## 5. SourcePrep-side opportunities (build generic, not Halbert-special)

Several required fixes are things SourcePrep should do regardless. Framing
them as generic SourcePrep features (not Halbert patches) lets Halbert
reference them by name and lets every other project benefit.

| Work item | Halbert-special? | SourcePrep product value |
|---|---|---|
| **C2 fix: external edges into build-time loader** (clustering + group_reasoning) | No — latent bug for ALL external-edges users | High — external edges are a shipped feature that silently doesn't affect build-time intelligence. Fix generically. |
| **M1 mechanism 2: per-stage skip flag at orchestrator** | No — needed for any profile | High — enables cleanly disabling concepts/audit/antibodies for docs-heavy SourcePrep projects (SourcePrep's own corpus is 46% markdown). |
| **Per-file content-type → stage-policy map** (profiles) | No | High — SourcePrep dogfoods on its own docs; code-shaped prompts over prose is a known weakness. `prose_docs` profile helps SourcePrep itself. |
| **Declarative project template/preset** (the `sourceprep_template.yml` pattern) | Halbert's *first use*; generalize to `prep template apply` | High — SourcePrep has no opinionated setup story today. |
| **`atlas_deep_dirs` config** | No | Medium — de-hardcodes a code-ism (`src/lib/pkg/…`). |
| **Per-content-type ATLAS segment prompts** | No | Medium — `SEGMENT_ATLAS_PROMPT` is already per-segment (`atlas/prompts.py:75`); choose code/docs/config variant per segment's dominant content-type. The plan's "dominant profile of segments" is achievable here but unspecified for the **root** atlas in a mixed project — needs design. |
| **`prose_docs` CONCEPTS pass** (diverges from plan decision #4) | Not now — follow-up | High for SourcePrep dogfooding — planning/phase docs hold the "why." A doc-concepts pass is SourcePrep's epistemic brand applied to its own corpus. The profile machinery enables it (just a prompt variant + matrix flip). Flag as a follow-up the profile work unlocks. |
| `system_config` profile, host staging, `edge_extractor.py`, intake→scope mapping | **Yes — Halbert-local** | Keep in Halbert. |

**Product principle to preserve (plan decision #1):** SourcePrep owns the
prompt engineering and the profile definitions; apps declare intent by name.
No prompt text should cross the API.

---

## 6. Risks the plan does not address

1. **Baseline-shrink / staleness interaction (top implementation risk).** The
   pipeline has write guards with baseline-shrink and changeset-driven
   staleness, and known state-machine fragility (F-66/67/68/75/78 series). If a
   profile skips a scope's files for a stage, does the skip count as *stable*
   (no spurious re-runs) or does staleness keep flagging those files as
   unprocessed? The plan is silent. **Verify before coding** that "worker
   returned skip for all profile files" marks them stable, not pending — else
   every rebuild re-enters the stage.
2. **One-project-vs-two tradeoff is not weighed.** The plan asserts one project
   is better (avoids "split-brain in integration code") but does not cost the
   downsides of merging: (a) one shared build **barrier** — a slow 16K-doc
   rebuild blocks a fast host-config edit; (b) shared project-level
   `path_weights`/`role_weights`/`primer`/`priority_level` (scope weights are
   "reserved v1.1", not implemented — so no per-corpus weighting); (c) one
   blended ATLAS (two projects would give two clean orientation docs); (d)
   shared concurrency budget. With two projects, host-config can rebuild
   independently of the slow docs build. The plan should weigh these against
   the "split-brain" cost it cites as the reason to merge.
3. **Mixed/overlapping scopes.** `path_matches_any_scope` returns a boolean. If
   a file matches two scopes with different profiles, what wins? Needs a
   resolution rule (last-wins / most-specific / reject). Plan is silent.
4. **Profile granularity: per-scope vs per-file.** The plan puts
   `pipeline_profile` on `ScopeRecord`. But content-type is a per-file
   property, and SourcePrep already detects it per file (`is_markdown`,
   `_infer_role_from_path`, `_DOCS_PATTERNS`). A more general design: profile =
   a content-type → stage-policy + prompt-variant map applied **per-file**, with
   scopes as an **override** channel. For Halbert (host/=all config,
   knowledge/=all docs) per-scope is clean; for a normal repo mixing `docs/`
   and `src/` in one scope, per-file detection is what you want. Recommend
   per-file detection as the base, scope-profile as override.
5. **`scopes.py` update does not accept `paths`** (separate `/add` `/remove`
   endpoints, `api/routers/scopes.py:155`). The template's
   `scopes: [{id, paths, profile}]` shape maps to create-then-add-paths, not a
   single create call. Minor plumbing note for the Halbert setup script.

---

## 7. Amended plan checklist (for the plan author)

- [ ] **C1:** Replace "docs have no edges" premise. Decide signal vs noise for
      `markdown.rs` reference edges; set `trace_expand` for docs accordingly
      (likely `True`, not `False`). Verify empirical edge counts on the real
      corpus.
- [ ] **C2:** Replace the one-line `group_reasoning.load_edges()` fix with a
      shared build-time edge loader that includes external edges, consumed by
      both `cluster.py` and `group_reasoning.py`. Scope this as a SourcePrep
      generic fix.
- [ ] **C3:** Make the `system_config` group_reasoning choice explicit
      ((a) fix clustering + keep inferred_edges off, (b) inferred_edges on,
      or (c) drop the build-time group-reasoning value prop). Fund the full
      fix if (a).
- [ ] **M1:** Split enforcement into per-file gate + per-stage skip flag +
      input-set filter. Re-estimate Phase S1 sizing. Note 10 `WorkerFactory`
      injection sites, not 7.
- [ ] **M2:** Note in profile spec that `audit` and `antibodies` are
      all-or-nothing, never per-file gates.
- [ ] **M3:** Verify Halbert docs' content class (structured-docs vs
      narrative). Re-state catalogue cost with doc/narrative batch sizes.
- [ ] **M4:** Re-frame deepening cost as capped-per-run, unbounded-cumulatively.
- [ ] **M5:** State the `cloud_concurrency` assumption behind "hours."
- [ ] **Risk 1:** Verify baseline-shrink/staleness marks profile-skipped files
      stable before coding.
- [ ] **Risk 2:** Weigh one-project-vs-two (barrier, weights, atlas,
      concurrency) against the split-brain cost.
- [ ] **Risk 3:** Define a profile resolution rule for overlapping scopes.
- [ ] **Risk 4:** Decide per-file vs per-scope profile granularity (recommend
      per-file + scope-override).
- [ ] Update REMAINING-WORK §1.6, RAG-OPTIMIZATION-PLAN §S1, IMPLEMENTATION-PLAN
      T0a.1/T5a.1 per the as-built reality.

---

## 8. Verification provenance

All findings were checked against SourcePrep `main` on 2026-08-24. Key
file:line evidence:

- markdown edges: `engine/crates/prep-parser/src/markdown.rs:156-220`,
  `prep-graph/src/lib.rs:793,1054-1061`
- query-time edge load: `core/trace/index.py:129-173,328-407`
- clustering edges: `core/cluster.py:1165-1176,380-384,710,762`
- group_reasoning edges + groups: `core/group_reasoning.py:386-397,215-286,326-339`
- per-file gate contract: `services/pipeline/workers/base.py:62-72`
- per-stage gate call sites: `inferred_edges.py:230`, `augmenter.py:490`,
  `epistemic_enrichment.py:468`, `deepening.py:141`, `knowledge.py:482`
- group-level gating: `services/pipeline/orchestrator.py:1971-2044`;
  stage list `services/pipeline/stages.py:13-32`
- batch sizes: `core/batch_profiles.py:84-150`; doc sub-batch
  `augmenter.py:1447`; narrative `augmenter.py:1564`
- deepening caps: `services/pipeline/workers/__init__.py:1393`,
  `core/deepening.py:410,456`
- concurrency: `services/pipeline/scheduler.py:169,2773`
- atlas segments: `core/atlas/generator.py:354-405,1601`; prompts
  `core/atlas/prompts.py:75`
- scopes CRUD: `api/routers/scopes.py`; resolver `core/scope_resolver.py:22,57`
- external-edges endpoint: `api/routers/trace_routes/query.py:609`
- shared trace loader: `core/trace/loaders.py:28`; query site
  `api/routers/projects/search.py:296`

Re-verification welcome. The two most important things to re-check before
implementation: **C1** (run `markdown.rs` over a sample of Halbert's actual
docs and count `references`/`links_to` edges — this is empirical and
corpus-specific) and **Risk 1** (staleness behavior of profile-skipped files —
read `Changeset.should_process` interaction with the baseline-shrink write
guard).