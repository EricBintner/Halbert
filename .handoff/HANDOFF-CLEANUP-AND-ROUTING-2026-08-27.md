# Handoff: cleanup, routing, and the picker's remaining edges

**Created:** 2026-08-27
**Base:** `origin/main` after Plan A merged (`c184000`) and its follow-ups
**Plan:** `documentation/design/HALBERT-CLEANUP-AND-WIRING-PLAN-2026-08-27.md` — **read
revision 2 at the top first.** Revision 1's delete list is superseded in part and must not
be executed as written.

---

## Read this before proposing any deletion

The dominant defect class in this repo is code that is correct, tested, and unreachable
from the path that runs. It has been confirmed many times. But an audit of `main` found
that **half its "dead code" was scaffolding for an in-flight plan** — the diff-review
feature it proposed deleting is a column on Plan A's `messages` table, mid-repair.

**The gate:** before proposing a deletion, grep `.handoff/*PLAN*` and
`documentation/design/` for the module. If anything intends to reach it, it is not dead,
it is early. Reachability is only a defect when nothing means to reach it.

---

## 1. The one live bug — do this first

**`dashboard/routes/compression.py` is a second writer of `models.yml`.**

`compression.py:102` reads with `find_models_config()` (`include_repo=True`, so it can
read the *repo's* `config/models.yml`), mutates the whole dict, and writes it back at
`:118` with a bare `yaml.safe_dump`. That bypasses the store's atomic write, `.bak`,
0600 mode and normalisation, and copies the repo's `routing:` block into the operator's
own file.

`settings.py` states the invariant this breaks out loud: *"Every write goes through the
store, so the file keeps its backup, atomic rename, 0600 mode and sibling keys."*

**Fix:** read via `llm_store.load_file()`, write via `llm_store.set_top_level("compression", …)`
— which already exists and is already used for this exact key in `settings.py`. Deletes
~30 lines.

**Watch out:** installs whose `models.yml` was written this way already carry a stray
`routing:` block. Either strip it in `normalise_file` as a one-shot migration, or ship the
fix with a note. *Size: small. Behaviour-changing on affected installs.*

Verified still open on `origin/main` as of this handoff.

## 2. Two complexity scales under one config key

`routing.complexity_threshold` is read on **two incompatible scales**:

- `intake/pipeline.py` reads it as **1–5** (default 3), and intake's verdict is
  authoritative for a chat turn when intake ran.
- `model/router.py` and `model/tier_router.py` read the same key as **0.0–1.0**
  (default 0.5). The shipped `config/models.yml` sets `0.5`.

So the shipped value is meaningless to the reader that actually decides a chat turn.
Collapse to one scale, rename the key so the scale is in the name, and delete the two
duplicated `_score_complexity` implementations (~110 lines) in favour of
`client.score_query_complexity`.

**Do this in the same change as §1**, or the migration has nowhere to land.
*Size: medium. Behaviour-changing: `/api/services/*/explain|diagnose` and the Haloysius
seam start escalating on the same sentences chat does.*

## 3. Delete `model/cascade_router.py` — do not fix it

It is off by default and **wrong when on**. A runtime probe showed every query, including
`"hi"`, routing to the **vision** slot: it treats a capability slot as a capability tier,
so the fallback for a hard *text* task is a vision model. Its cost axis is hardcoded to
zero (`tier_router.py` writes `cost_usd=0.0`), so the outcome store's `avg_cost` is
structurally always zero. Its tests pass only on a config shape the real loader never
produces.

It is also an **Open Claude Code add-on, not Claude Code behaviour** — `v2/src/optimize/`
is the OCC authors' own opt-in layer and nothing in `v2/src/core` imports it. There was
never an upstream mandate for it.

Delete it, its two tests, and the two `is_enabled()` branches in `tier_router.py`. Keep
`OutcomeStore` if latency/success telemetry is wanted. *Size: small. Invisible — it never ran.*

## 4. What Claude Code actually does about routing

Worth knowing before anyone builds more of it. In OCC's core there is **no complexity
routing at all**. The model comes from `--model`/`-m` with a plain default, `SUBAGENT_MODEL`
for sub-agents, and an explicit per-call override. Every model decision is the operator's.

Halbert already has the explicit half — the pill, the tier badge, `/model`, and a per-turn
override that bypasses the router entirely. The remaining question is whether the automatic
half should be **default-off**, matching both OCC's core and the founder's stated goal of
clarity, simplicity and control. That is a product decision, not a bug.

If auto-routing stays, the one pattern worth taking from OCC's add-on is **escalate on
actual failure rather than on a predicted score** — real evidence instead of a keyword
guess. The fallback machinery for it already exists in `LLMClientAdapter`.

## 5. Picker edges still open

Small, none blocking, all verified against `origin/main`:

- **D-4.3** — the Vision slot does not warn when the chat model *loses* vision; it sits
  there looking configured.
- **Inline key verification** — pasting an API key does not verify on the spot.
- **The session config layer is unreachable** — `bind_session`/`set_session_slot` have no
  production caller. Either wire it or take it out with the workspace layer (revision 2, D-6).
- **`/model status`** does not report session state; **`Cmd + /`** is unwired.
- **V-02** needs a real Anthropic key for a live 200. The wire format is unit-tested; nobody
  has confirmed a live success.
- `.handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md` never got its "Resolution" section.

## 6. Auto-select is opt-in by founder decision

A fresh install registers a reachable local engine but **chooses no model**. That is
deliberate: registering what is demonstrably there needs no permission, choosing does.

The hardware-fit selection code is unchanged and still reachable two ways — the Quick-setup
button, and `first_run: {auto_select_model: true}` in `models.yml`. **Do not make it the
default again.** The heuristic ranks models against a detected VRAM budget, which says
nothing useful about a hosted model that does not run on the machine at all; on its first
real run it selected exactly such a model.

## 7. Things that will mislead you

- **The shared worktree is not `main`.** `/Volumes/4TB-BAD/Halbert` sits on whichever
  branch a concurrent session left it on, often several commits behind. An earlier audit
  read the wrong tree and nearly concluded a shipped feature did not exist. **Work from a
  fresh worktree off `origin/main`.**
- **Branch names move under you.** A branch was deleted and recreated mid-merge here,
  making `git log main..branch` report nothing while the work sat under a different name.
  Verify by **content** (`git grep` for a distinguishing symbol on `origin/main`), not by
  SHA or branch name.
- `python3` has no `pytest-asyncio`; it silently skips every async test and reports a false
  green. Use `arch -arm64 .venv/bin/python`.
- **Never prefix a command with `timeout`** — it is x86_64 here, so it launches the
  universal2 python under Rosetta and every arm64 native extension fails with an
  architecture error that looks like a code bug.
- Run `tsc` from the directory you mean. Running it from `packages/model-picker` and
  reading the result as the frontend's has produced a false green twice.

## 8. Verification

```
cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/ -q
cd halbert_core/halbert_core/dashboard/frontend && npx tsc --noEmit && npm run test
cd packages/model-picker && ./node_modules/.bin/tsc --noEmit && node scripts/check-boundary.mjs && ./node_modules/.bin/vitest run
```

`check-boundary.mjs` is what keeps `packages/model-picker` extractable (no non-relative
imports but `react`, no I/O, no CSS). Keep it green; it runs in CI.

Commits need `git commit -s` — the repo's DCO workflow checks every commit in a PR.
Never add a `Co-Authored-By` or generation-attribution trailer.
