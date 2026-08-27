# Role-Scoped Config Harvesting — Open Items

2026-08-27

The implementation is merged and pushed (`511dd5d` on `model-picker-frontend`,
comprising the feature merge `0cb99ad` and the audit-fix merge). Local tests:
**1482** in `halbert_core/tests/`, **122** in the root tree, 0 failures.

These items are NOT done. Two of them mean the role scopes are **not
production-ready** despite the code being complete.

---

## 0. NEWLY FOUND 2026-08-27 — scoping does not work on the live path

Three findings from a follow-up investigation, each verified directly against
`origin/model-picker-frontend`. Together they mean **no query in production is
currently being scoped as intended.** These supersede everything below in
priority.

### 0a. The three role scopes are unreachable at query time

`sourceprep_retrieval_backend.py::scope_for_query` can return exactly three
things: `None`, `"host"`, or `f"knowledge_{platform}"`. There is **no code path
that returns `network_admin`, `service_admin`, or `storage_admin`**, and
`context/adapters.py` is the only caller that passes a scope at all.

So the role scopes are indexed, registered in the template, and covered by the
quality gate — and **dead on the live path**. The gate exercises them only
because `corpus_quality_gate.py` hand-builds its own request body rather than
going through `scope_for_query`.

Nothing is broken by this; the scopes simply never activate. But the feature
does not deliver its purpose until routing can reach it. See item 0d.

### 0b. `knowledge-*` scopes have been silently unscoped all along

The template registers **hyphenated** ids:

```yaml
- id: knowledge-linux
- id: knowledge-macos
```

while `scope_for_query` returns **underscored** names (`knowledge_linux`).
The daemon has no scope by the underscored name, so the request silently falls
back to the global union.

This is not speculation — `sourceprep_retrieval_backend.py:37-38` documents the
behavior explicitly:

> *scope IDs on the SourcePrep daemon use underscores, e.g. `"knowledge_macos"`;
> hyphens silently fall back to the global union*

So the mismatch was known when that comment was written, and the template still
carries hyphens. **Every knowledge-scoped query has been returning full-corpus
results while appearing to succeed.** A 200 carrying union results is
byte-identical to a correctly scoped 200.

This also settles item 2a below: unknown scope names **fail open**, confirmed by
the project's own comment rather than by daemon testing.

**Fix:** change the four `knowledge-*` ids in `sourceprep_template.yml` to
underscores. Note the migration: `_reconcile_scopes` keys on `display_name`, so
renaming creates four *new* scopes and orphans the four hyphenated ones on the
daemon. Needs a daemon to clean up, so do it with one in front of you.

### 0c. `scope_mode` is not in the shipped branch at all

`grep scope_mode` on `origin/model-picker-frontend` returns **nothing** in
`sourceprep_client.py`. It exists only as an uncommitted edit in the dirty main
checkout. On the branch, the client sends `scope` and nothing else.

Consequence: scoping is a **rank boost**, not a hard filter. Every design
decision justified by "an empty mask under `scope_mode=hard` excludes
everything rather than narrowing" — including making `storage_admin`
file-backed on Darwin, and the `file_backed_platforms` gate in `roles.py` —
rests on behavior that is not active in the shipped code. Those decisions are
still defensible, but the stated reason is currently false.

The comments in `roles.py` (lines 32, 60, 95, 117) and `sourceprep_setup.py`
(line 275) should either be corrected or the flag should be landed.

### 0d. Minimum work to make scoping real

In order. Item 1 is required under any future routing design.

1. **Observability first (~0.5 day).** Assert returned `source_path`s match the
   requested scope; retry unscoped on zero chunks; log a warning when a scope
   request returns union-shaped results. Without this, every fix below is
   unmeasurable — and 0b went undetected precisely because nothing checks.
2. Fix the hyphen/underscore mismatch (0b) and validate scope names against the
   daemon's list at startup, so a typo fails loudly instead of silently
   widening.
3. Land `scope_mode` (0c) so scoping actually filters.
4. Give the agent an explicit scope-by-name tool. This is the only routing
   design where the agent can *retry a different scope* after seeing bad
   results — keyword routing cannot recover from a wrong pick.

---

## 1. BLOCKING — nothing here has ever been evaluated by CI

`.github/workflows/ci.yml` triggers on `push` to `main`/`master` and on
`pull_request`. All of this work landed on `model-picker-frontend`, which is
neither, and no PR exists. **Every green test number reported for this work is
local-only.**

That matters more than usual here, because CI runs on **Python 3.11 / Ubuntu**
while local verification ran on **Python 3.10 / macOS**, and CI installs
`libsystemd-dev` which activates the `systemd-python` dependency that never
installs on macOS. Neither divergence has been exercised.

**To resolve:**

```bash
gh pr create --base main --head model-picker-frontend \
  --title "Role-scoped config harvesting" \
  --body "See .handoff/ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md"
```

`gh` is **not installed** on this machine (`which gh` → not found), so this
must be done from the GitHub web UI or after `brew install gh`.

Note the branch also carries unrelated model-picker commits, so the PR will be
larger than just this work.

---

## 2. BLOCKING for production use — three verifications need a running daemon

None can be done without a SourcePrep daemon and a built index. All three are
recorded in the design doc's "Unverified claims" section; repeated here so they
are not lost.

### 2a. Does an unknown scope name fail closed?

Reported (unverified) that an unrecognized scope yields `mask=None` and falls
back to **the global union with HTTP 200**. If true, a typo'd scope name
silently searches the entire corpus — the exact inverse of narrowing, and
undetectable from the client side.

**Test:** issue a scoped `context()` query with a deliberately bogus scope name
against the running daemon. If it returns results rather than an error, this
must be fixed before role scopes are trusted.

### 2b. Does `to_remove` actually remove?

`sourceprep_setup.py::_reconcile_scopes` computes `to_remove` from
`rec.get("paths")`, sourced from `_list_scopes()` (`GET /projects/{pid}/scopes`).
If that endpoint returns summaries **without** a `paths` key, `current_paths`
is always empty — so `to_remove` is always empty and scope masks only ever
grow, while `to_add` re-sends everything on every apply.

**Test:** inspect the raw `GET /projects/{pid}/scopes` response for a `paths`
key. If absent, fix by fetching `GET /scopes/{sid}` per scope.

### 2c. End-to-end quality gate has never run

`scripts/corpus_quality_gate.py` now holds 28 entries (20 platform + 8 role) at
a 90% pass threshold, tolerating at most 2 failures. **Until the role trees are
both staged and indexed, all 8 role queries fail → 20/28 = 71% → the gate
FAILS.** That is expected, not a defect, but it means the gate cannot be used
as a health signal until a build has run.

Two gate queries were tuned without being executable: `r04` and `r06` were
changed to content-bearing terms because the matcher concatenates
`content + file_path`, so path-derived terms pass trivially. `r06`'s `-hosts`
term assumes the chunker indexes comment lines — if it strips comments, that
query needs revisiting. macOS `storage_admin` content is thin enough that no
uncommented term is both distinctive and absent from the path.

---

## 3. Known limitations carried forward (documented, not defects)

Each is recorded in `.handoff/ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md`
with reasoning. Listed here for triage, ranked by how much they'd bite.

1. **Role trees duplicate the flat host tree** — staging goes 42 → 99 files
   with 40 duplicated, and `remap_edges_for_unified_root` maps only to `host/`,
   so `trace_expand` finds no edges inside a role scope. Two candidate fixes
   are written up (scope masks over the flat tree, or pruning overlaps from the
   flat staging list). **Decide with a working index in front of you** — both
   change staging topology and neither can be verified without one.
2. **`<integer>[redacted]</integer>` produces well-formed XML but an invalid
   plist** — `plistlib` raises on the int parse. Pre-existing (verified against
   `0cb99ad`), hits 1 of 461 launchd plists on this host. Fixing it means
   choosing a placeholder integer, which is a real design call.
3. **Schemeless URL credentials leak** — `//user:pass@host` (UNC form, no
   scheme) is not matched by the URL-credential rule. Narrow but real.
4. **`RoleScope.aliases_from` has no consumer.** It names `security_admin` and
   `sharing_admin`, which do not exist in `ROLES` yet — so any future code
   doing `ROLES[alias]` will `KeyError`. Either wire aliasing in wave 2 or drop
   the field.
5. **`scope_mode="hard"` is cited as load-bearing justification but is never
   set** anywhere in this tree — it appears only in comments and tests. The
   `file_backed_platforms` gate rests entirely on "an empty mask excludes
   everything rather than narrowing", which is currently an unverified property
   of a flag nothing enables. Confirm it is the daemon default, or stop citing
   it.
6. **`fnmatch`'s `*` crosses `/`** in manifest patterns, so
   `system-connections/*` also matches nested files. Over-collection only,
   bounded within the intended directory — but worth knowing before widening a
   glob.

---

## 4. Merge hazard for concurrent sessions

Other sessions are working on branches that do **not** contain this merge, and
are independently editing two files this merge changed:

- `scripts/corpus_quality_gate.py` — this merge appended 8 role queries to
  `SCOPED_QUERIES`; another session has ~85 insertions/53 deletions in flight.
- `halbert_core/halbert_core/integrations/sourceprep_template.yml` — this merge
  added three role scopes.

**The dangerous case is not a conflict — it is a clean auto-merge.** If another
session adds a scope with a duplicate `id`, git merges it without complaint and
`_reconcile_scopes` (which keys on `display_name`) double-registers it at
runtime. Check for duplicate scope ids by hand after any merge touching that
template.
