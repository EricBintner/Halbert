# Role-Scoped Config Harvesting — Open Items

2026-08-27

The implementation is merged and pushed (`511dd5d` on `model-picker-frontend`,
comprising the feature merge `0cb99ad` and the audit-fix merge). Local tests:
**1482** in `halbert_core/tests/`, **122** in the root tree, 0 failures.

These items are NOT done. Two of them mean the role scopes are **not
production-ready** despite the code being complete.

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
