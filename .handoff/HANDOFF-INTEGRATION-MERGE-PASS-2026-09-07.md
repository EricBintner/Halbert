# Handoff: the integration merge pass — every open branch into `main`

**Date**: 2026-09-07 · **Status:** DONE and pushed · **Wants:** review of six conflict
resolutions, three of which changed someone else's code
**Repos touched:** `Halbert` (this one, six merges) and `Haloysius` (four engine commits, already merged)
**End state:** `main` = `origin/main` = `58ce4b1d`; `git branch --no-merged main` is empty

Every branch that was open in this repository is now on `main`. The suite was run
after each merge, not once at the end, so a regression could be attributed to the
merge that caused it. This document is the record of what was merged, what
conflicted, and — the part that needs your eyes — **which side I took and why**.

If you own one of these branches, read §3. One resolution changed the behaviour
your branch intended, deliberately, and you should confirm the call.

---

## 1. What went in

Merged oldest-work-first, smallest first, `--no-ff` throughout.

| # | Merge | Branch | Suite after |
|---|---|---|---|
| 1 | `20fdd523` | `worktree-sec-1-one-door` — SEC-9 HA governance, the route auth census | 5632 passed, 14 skipped |
| 2 | `53d8bab9` | `feat/guest-persona` — the guest persona, the prose that becomes a warrant | 5982 passed, 14 skipped |
| 3 | `c26222c8` | `feat/attunement-halbert` — Halbert-side attunement | 6158 passed, 14 skipped, 6 xfailed |
| 4 | `da444c70` | `feat/rust-native-core` — the crates and their review request | 6171 passed, 14 skipped, 6 xfailed |
| 5 | `5a3fa8d7` | `worktree-sec-1-one-door` again — SEC-2/SEC-3 | — |
| 6 | `58ce4b1d` | `feat/guest-persona` again — "be Marnie" said out loud | 6221 passed, 15 skipped, 6 xfailed |

**`fix/observation-text-normalisation` needed no merge of its own** — it is fully
contained in `feat/attunement-halbert` (`git merge-base --is-ancestor` confirms),
so merge 3 brought all nine of its commits.

**Merges 5 and 6 exist because both worktrees committed while this pass was
running.** They are live sessions, not stale branches. `main` is current as of
`58ce4b1d`; anything either worktree lands after that is its owner's to merge.
Other sessions were also merging into `main` in parallel — `21a52e61` (branch 3:
A3/A4/A5), `e37ee1be` (wire A4) and `0922b40c` are theirs, not this pass's. The
push was a fast-forward, so nothing of theirs was overwritten.

Whole pass, from `1764ce91` to `58ce4b1d`: 158 files changed, 20,596 insertions,
363 deletions.

---

## 2. Verification

```bash
.venv/bin/python -m pytest halbert_core/tests -q     # after every merge
cd crates && cargo check --workspace                  # after merge 4
```

- **Baseline first.** Before any merge, `main` at `1764ce91` ran
  **1 failed, 5613 passed, 14 skipped**. Recording that first is what makes the
  rest of the numbers mean anything.
- **The one failure is a pre-existing flake, not a regression.**
  `test_scheduler_executor.py::test_one_time_job_runs_and_records_outcome` failed
  on that baseline and again on the final run, and **passes in isolation both
  times** (11 passed, ~3s). It is order- or timing-dependent under a full-suite
  load. It was failing before this pass touched anything.
- **The Rust crates compile.** `cargo check --workspace` is clean across
  `halbert-ffi`, `halbert-mqtt`, `halbert-sandbox`, `halbert-snapshots`,
  `halbert-telemetry` (50s). Nothing in the Python tree imports them, so the
  pytest numbers would not have caught a broken crate.

---

## 3. The conflicts, and which side won

Six conflicts. Three were mechanical (a superset beat a subset, a later document
revision beat an earlier one). Three were judgment. **The first one is the one to
check.**

### 3.1 `dashboard/app.py` — the resolution that could have unauthenticated the API

**This is the one that needs the `feat/guest-persona` owner's sign-off.**

Merge 1 (SEC-9) introduced `mount_api()`, which mounts every router through
`_auth.mount_router(...)`. `feat/guest-persona` was cut before that and still
called bare `app.include_router(...)`. Both sides rewrote the same ~35-line
registration block, so git could not merge them.

Taking the branch's side — the ordinary "theirs wins" reflex, and what a
conflict-resolution pass in a hurry would do — **would have silently reverted
~35 routers to unauthenticated mounting**, undoing SEC-9 one merge after it
landed, with no test naming the loss in the diff.

What the branch actually changed in that file is two lines, nothing more:

```
+ ... findings, state, guest as guest_persona          # the import
+ app.include_router(guest_persona.router, tags=["guest"])
```

**Resolution:** took `main`'s file whole (`--ours`), then re-added those two
lines — with the mount converted to `mount_api`, so the guest routes sit behind
the same auth as everything else:

```python
mount_api(guest_persona.router, tags=["guest"])   # app.py:687
```

**Verify:** `git show origin/main:halbert_core/halbert_core/dashboard/app.py | grep -n guest_persona`
— import at 643, mount at 687. `test_route_auth_census.py` (which arrived with
SEC-9) passes.

**The question for you:** this makes the guest router authenticated, which the
branch as written did not. If a guest session is *supposed* to reach those routes
without the dashboard's auth, then my resolution is wrong on the product and the
fix belongs in `auth.py`'s exemptions, decided deliberately — not restored by
reverting the mount. Say which, and I will change it.

### 3.2 `ha_event_mapper.py` — not a real conflict

`main` added `_record_state` (the state-ledger write) at the same point where the
branch added `_route` and `_forward_to_guest`. Different methods, same line
number. **Kept all three.** Nothing chose between them because nothing had to.

### 3.3 `EntityIdentityCard.vocabulary.test.tsx` — both sides additive

`main` added a comment explaining that retired terms are banned repo-wide by
`vocabulary.guard.test.ts` rather than per-component; the branch added a test
(`does not invent a third name for a mode`). **Kept both.**

### 3.4 `HANDOFF-OBSERVATION-LENSES-2026-09-04.md` — rev 2.1 beat rev 2

The branch carried rev 2 (1,344 lines). `main` carried rev 2.1 (1,398 lines,
"reconciled with branch 1 as shipped"). §2 of
`TODO-OBSERVATION-LENSES-2026-09-05.md` had predicted exactly this collision and
said to take the descendant. **Kept `main`'s rev 2.1.** Verify: it is the copy
that contains the "Rev 2.1 changes" line.

### 3.5 `test_agent_pool_shell_syntax.py` — add/add, superset won

Both branches added the file. Identical for 97 lines; `main`'s continues for 36
more with `TestTheHostSaysWhetherItOnlyLooked`. **Kept `main`'s superset.**

### 3.6 `REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md` — add/add, later state won

Two different documents under one filename: the branch had the original external
review request (382 lines); `main` had the same request after the fact, marked
**APPLIED 2026-09-01 (founder directive)** with all 13 findings and 5
recommendations landed (360 lines). **Kept `main`'s.** The branch's copy is the
historical original and is recoverable from
`git show feat/rust-native-core:.handoff/REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md`
if anyone wants it as a record.

---

## 4. Deliberately not committed

Five files sit untracked in the working tree and are **staying** untracked by
explicit decision:

```
.handoff/SECURITY-AUDIT-FINDINGS-2026-09-06.md
.handoff/SECURITY-AUDIT-REPORT-2026-09-06.html
.handoff/SECURITY-IMPLEMENTATION-PLAN-2026-09-06.md
.handoff/security-audit-findings-2026-09-06.json
documentation/design/PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md
```

**This repository is public.** The first four are a security audit of this tree
and its remediation plan; publishing them would publish the unremediated half.
The decision to publish, to hold, or to move them somewhere outside the working
tree is the founder's, and it has not been made.

**If you are a later session: do not `git add -A` in this repository.** A blanket
add sweeps these in, and a push is not reversible in any way that matters — the
content is public the moment it lands. Stage by path here.

No branch in this pass tracked any of these five (checked before merging), so no
merge could have published them by accident.

---

## 5. The Haloysius side of the same work

The engine half was finished and pushed before this pass. Halbert's four Phase-1
upstream asks (§10 of `TODO-OBSERVATION-LENSES-2026-09-05.md`) are all landed on
Haloysius `main`:

| Ask | Haloysius commit |
|---|---|
| `ObservationStore.delete()` under `PRAGMA secure_delete`, FTS entry retired, WAL truncated | `2648e72` |
| `save()` refuses to resurrect a `forgotten_by_user:` tombstone | `2648e72` |
| `teach()` / `update_preference()` enter at 0.9 as user-sourced (`PeerMemoryBackend` too) | `324f186` |
| `_extract_subject` sees a withdrawn interest, so it supersedes the held one | `4f95418` |
| A `VIGILANCE` category | not needed — `ANTICIPATION` is Plutchik's own primitive |

Engine-side handoff with the API facts: `HANDOFF-OBSERVATION-LENSES-UPSTREAM-ASKS-2026-09-06.md`
(Haloysius `.handoff/`, commit `5058b94`); CHANGELOG under 0.3.0 in `e95d0b5`;
§10 here rewritten in `611661a2`. Haloysius's 120 `memory_v2` tests pass, and
that repo is clean and level with its own origin.

What this unblocks here, restated from §10 so it is not missed: `ERASURE_LIMITS`
can claim the observation plane; `RQ-6` no longer has to settle for "Stop using",
because `delete()` now exists beside the tombstone; a `remember` writer that
builds its own `PersonaMemory` must set `source="user"` itself; and the writer
still owns every negation except "interested in X".

---

## 6. Open for the reviewer

1. **§3.1** — should the guest routes be authenticated? I made them so. If not,
   the exemption belongs in `auth.py`, not in reverting the mount.
2. **The flake** — `test_one_time_job_runs_and_records_outcome` fails only under
   full-suite load. It predates this pass. Someone should own it or quarantine
   it; a suite with a known red is a suite people stop reading.
3. **§4** — the five untracked files need a decision. They are one careless
   `git add -A` away from being public.
4. **Live worktrees** — `feat/guest-persona` and `worktree-sec-1-one-door` are
   still being committed to. They were merged twice each during this pass; the
   next commit on either is its owner's to bring over.
