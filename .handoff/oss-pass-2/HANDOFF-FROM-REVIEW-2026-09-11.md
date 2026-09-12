# HANDOFF — From the OSS Pass-2 Plan Review

**Status:** ACTIVE — review complete, dispatch system written, ready to execute
**To:** Next agent / the founder
**From:** Review session (fable-tier), 2026-09-11
**Repo:** `/Volumes/4TB-BAD/Halbert`, branch `main` @ `fbd725e9`
**Supersedes:** the review brief `HANDOFF-TO-REVIEW-2026-09-11.md`

---

## 1. What this session did

Reviewed `FORMAL-IMPLEMENTATION-PLAN-2026-09-11.md` with four independent
evidence sources — a deep code-verification pass, an OSS-origin
spot-verification pass, a 156-agent five-lens adversarial review workflow
(every finding attacked by three refuters), and a completeness critic — then
wrote the corrected dispatch system.

Deliverables produced (all under `.handoff/oss-pass-2/`):

| File | What it is |
|---|---|
| `REVIEW-FORMAL-PLAN-2026-09-11.md` | The review: what survives, 11 blocker/major findings, minor corrections, what was rejected and why. |
| `DISPATCH-INDEX-2026-09-11.md` | The master control document: packet template, 18-lane collision map with explicit merge orders, 85-unit registry with tier + effort + dependencies, cross-cutting primitives, full packet accounting, integration-review protocol, tactical directives. |
| `PKT-*.md` | Self-contained dispatch packets, one per dispatchable unit (see §5). |
| `HANDOFF-FROM-REVIEW-2026-09-11.md` | This document. |

The handoff asked for three deliverables (review, verbose plan, return
handoff). The review found the handoff's own spec **missing four artifacts the
dispatch model actually needs** (finding L5-12): the packet template, the
machine-readable index, the complete collision map, and the gate registry. The
`DISPATCH-INDEX` supplies all four; the per-unit `PKT-*.md` files are the
verbose plan, broken into dispatchable form as the user directed.

---

## 2. What I reviewed

- The formal plan (6 milestones, claimed 87 units).
- The authoritative verdicts (`FINAL-CRITICAL-DISCOVERY-BACKLOG`), the four
  deep-evals, and the §3 cross-cutting primitives.
- The actual codebase — 14 defect-claim spot-checks, a full path/symbol audit,
  a full hot-file collision tally, dependency sanity, directive compliance.
- The four OSS origin checkouts at `/Volumes/Thunderbolt/AI/OSS/`.
- The git state (sonnet batch merge status, untracked corpus).

---

## 3. What I changed (headline corrections)

The plan's **technical diagnosis is sound** (all 14 defect claims verified
true or partially-true). Its failures are in **accounting, collisions,
contracts, and path precision**. Every confirmed finding is adopted:

1. **Packet accounting was false.** True counts: 74 packets (38 ACCEPT / 30
   RESHAPE / 6 DEFER), not the report's "27 ACCEPT" / "~84". Restored four
   silently-dropped RESHAPE packets (P3, P5, CSC-05, MEM-P4) and two missing
   buildable cores (T3, T6). F01–F20 are now explicitly tracked as research
   reads, not silently absent.
2. **Re-keyed the scrambled CSC/MEM units** to their deep-evals (the report's
   master-table labels were fused with the wrong content). The real MEM-P3
   (forgotten-request tombstones) is restored; the plan's "MEM-P3" backup work
   is correctly OTHER-P1; the plan's "MEM-P2" is MEM-P4's residual.
3. **Full 18-lane collision map with explicit merge orders** — the plan flagged
   2 of 9 `state_machine.py` consumers and 0 of the other collisions.
4. **Resolved the approval/engine.py conflict**: SURFACE-01a owns expiry
   enforcement and lands before P2's artefact binding (the plan had the order
   inverted and both units claiming expiry). P3 is last in that lane.
5. **Merged the duplicate backup build** (plan MEM-P3 + OTHER-P1) into one
   OTHER-P1 unit honoring "no users yet."
6. **Corrected the activity_clock contract** (per-instance, `idle_timeout`,
   `source`, thread-safe, `time.monotonic()`) in a NEW `utils/activity_clock.py`,
   with an explicit note on why `agents/turn_activity.py` (a cancellation-
   generation counter, not an idle clock) is NOT the home.
7. **Added the reconnect_supervisor primitive** (the plan scattered it across
   four units — the duplicate-primitive pattern the report forbids).
8. **Fixed a dozen wrong paths/symbols** (SP-3 is at `state_machine.py:3426`
   not 2669; `voice/` → `audio/speech/`; `continuity/memory_v2.py` doesn't
   exist — it's the Haloysius upstream; `strip_unicode_tags` →
   `sanitize_metadata_text`; `build_child_env` → `child_env` and it's an
   allowlist vs MP-6's needed blocklist).
9. **Re-labeled understated efforts** (SP-3 S→M, MP-5 S-M→L, TT-05 S→M+, P2
   S→M).
10. **Split the support bundle** out of LOG-01 (it false-depended on DIAG-01).

---

## 4. What I rejected (and why)

The adversarial pass refuted 32 over-reaches. The notable ones — so the next
reviewer doesn't re-raise them:

- **"T1 shouldn't gate the M0 primitives"** — no; T1 first is correct.
- **"DIAG-01 is an unauthorized surface"** — no; it's the report's ACCEPTed
  universal diagnostic sink.
- **"M5a should note the sonnet batch may never merge"** — moot; the user
  directed the merge as step 1.
- **"The milestone ordering is wrong"** — no; themes, not barriers.
- **"F01–F20 must be dispatched"** — no; they're research reads, now tracked.

Full list in `REVIEW-FORMAL-PLAN-2026-09-11.md` §4.

---

## 5. What the next agent should do

The execution sequence is in `DISPATCH-INDEX-2026-09-11.md` §1. In short:

| Step | Action | Owner |
|---|---|---|
| 0 | Land **SP-3 + SP-4a** (own worktree). User-directed; supersedes the prior handoff's planning-only constraint. | fable |
| 1 | **Merge the sonnet batch** (`fix/remediation-sonnet-batch-1`). Survey says: clean, zero conflicts, zero new failures. Procedure + acceptance criterion in §6 below. | fable + founder merge |
| 2 | Re-baseline M5a verdicts against the merged tree. | fable |
| 3 | Build the **M0 substrate** (10 primitives) in one worktree. | fable |
| 4 | Dispatch M1–M4 packets to parallel opus/sonnet sessions, respecting lanes. | other sessions |
| 5 | Final integration review against measured state. | fable |

The packets are the dispatch unit. A receiving session reads its own
`PKT-*.md` and nothing else — it carries the 11 fields, the repo traps, the
OSS reference, the collision-lane position, and the merge order.

---

## 6. The sonnet-merge procedure (step 1, verified)

Empirically validated in a scratch worktree at main tip `fbd725e9`:

```bash
git checkout main
git merge --no-ff fix/remediation-sonnet-batch-1 \
  -m "merge: remediation sonnet batch 1 (R-03, R-12 Phase A, R-13, R-15)

R-03 scheduler durability + heartbeat liveness (17 commits), R-12 Phase A
session-tree threads wiring (6), R-13 utility-slot locality and catalog
fixes (4), R-15 eval harness and verdict contract (5). No conflicts; full
suite shows no new failures vs main baseline (23 pre-existing)."
```

Post-merge validation (from the repo root, not a worktree):

```bash
arch -arm64 .venv/bin/python -m pytest halbert_core/tests -q
```

**Acceptance criterion:** the same ~23 failures currently on main
(`test_agent_model_override.py`, `test_agent_model_selected_event.py`,
`test_no_model_names_in_user_facing_source.py`, `test_num_ctx.py`) and nothing
else. Anything beyond those four files is a merge regression.

**Caveat:** main moves under concurrent sessions. Re-run
`git merge-tree --write-tree main fix/remediation-sonnet-batch-1` right before
merging; if main advanced past `fbd725e9`, re-check the new commits don't touch
`dashboard/app.py`, `agents/threads.py`, or the two overlap test files.

---

## 7. Open questions for the founder

1. **Merge gates.** Steps 0 and 1 both end at a merge to `main`. Per the
   repo's merge-decision step, these are presented for founder approval, not
   auto-merged. Confirm the founder wants to review each, or delegate the
   step-0 (SP-3/SP-4a) and step-1 (sonnet) merges.
2. **Tier assignment sanity.** M1–M4 are assigned opus; the mechanical sweeps
   (SP-4a, OTHER-P6a, MP-6, T2, T6) sonnet; M0 + review fable. Confirm the
   tier split before dispatch.
3. **M5b gates.** The 7 gated units (MEM-P5, SP-5, SP-6, CMD-A, DIST-02,
   TT-06, SP-4) each name their gate. Several reference founder decisions by
   number that resolve to nothing in DECISIONS.md's numbering (finding L5-4) —
   the gate registry maps them to verbatim decision text where it exists and
   flags the unresolvable ones. Founder should confirm the gates before any
   M5b dispatch.
4. **Commit the corpus?** `.handoff/oss-pass-2/` is untracked. Recommend
   committing it (tactical directive 1) so the dispatch manifest isn't one
   `git clean` from lost — but `.handoff/` is correspondence; confirm whether
   the founder wants it tracked.

---

## 8. Verified non-obvious facts (for the next session's traps)

- The sonnet branch is **clean to merge** — but re-verify `git merge-tree`
  right before, because main moves.
- `agents/turn_activity.py` is a **cancellation-generation counter**, not an
  idle clock. Do not "extend" it for activity tracking; build
  `utils/activity_clock.py`.
- `mcp/client.py:153 child_env()` is an **allowlist**; MP-6 needs a
  **blocklist** (`tools/subprocess_env.py`). They are siblings, not a rename.
- `obs/logging.py` already has `JsonFormatter` at `:45` — LOG-01's residual is
  the RotatingFileHandler + RedactingFilter + LogRecordFactory, not the
  formatter.
- `mcp/server.py` has **18** bare error sites, not 55.
- The Warp event replay ring is **not in the checkout** (private repo). Use
  openclaw's `seqByRun` (`src/infra/agent-events.ts:265`) as the `since_seq`
  reference.
- P2's approval-bound-to-artifact reference is **openclaw**, not
  open-claude-code.
- sherpa-onnx is an **existing optional extra** — VMV-1 adds no new hard
  dependency; the two-dep rule is Haloysius's, not halbert_core's.
- The known-red baseline is **~23 failures in four files** (streaming-reasoning
  / num_ctx work), not the older "~71 / ~205" figures in memory — those were
  earlier baselines. Baseline fresh on your merge-base.
