# Results — SONNET-02 (Commit dirty `main`, canonical `wt_pytest.py`, retire merged branches/worktrees/stashes)

**Date:** 2026-09-02
**Status:** DONE_WITH_CONCERNS (two `git push` operations blocked by the Claude Code auto-mode classifier; everything else in the packet completed)

## 0. Precondition mismatch found at start (important context)

At session start the working directory was checked out on `fix/opus-packets-2026-09-01`
(a different concurrent session's completed Opus 01-05 batch, 25 commits), not `main`.
The coordinator confirmed this was a legitimate, verified piece of work that had simply
landed on a side branch, and fast-forwarded `main` to `fe0d5017` (was `941cc14b`) — a
clean fast-forward, nothing lost or rewritten. Three of the six files this packet's §1
expected to find dirty on `main` (`HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md`,
`MASTER-TODO.md`, `RUST-NATIVE-CORE-TODO-AND-IMPLEMENTATION-PLAN-2026-08-31.md`) had
already been swept into that branch's first commit, `ef1ce128`, alongside an unrelated
`state_machine.py` fix — not this session's doing. Commit 4 below was adjusted
accordingly (it now covers only the two docs that were still genuinely uncommitted, plus
a header note on the plan doc).

## 1. Commits made (8, in order)

| SHA | Message |
|---|---|
| `a0dc3310` | `chore(test): add wt_pytest.py worktree test wrapper` |
| `a3b55deb` | `feat(design-system): HalbertMark explicit line counts via lines prop; density aliases preserved` |
| `af7b5fe1` | `feat(brand): 5/7/8-line mark variants` |
| `4a7a9283` | `docs(rust): sanity review request, pause-state record, and RNC-06 name-collision note` |
| `432dc0b6` | `docs(handoff): semantic-audit proposal, 2026-09-01 state-of-work audit and dispatch packets` |
| `30aeefe9` | `docs(design): rescue the chat-ui-audit response-modality code audit (U3-26)` (§5 handling) |
| `cf9278d2` | `fix(model): correct stale "three slots" comment in config_wizard schema check (U6-26)` |
| `6bbcb539` | `docs(handoff): save HomeCognitiveLoop wiring draft before retiring home-automation dir` |

`git status --porcelain` is empty after all of the above.

**Self-correction note:** my first attempt at commit 1 (`d436d749`, since replaced) picked up
the design-system trio too, because they were already staged (index) before I started — I
misread the porcelain status columns as "working-tree modified" when they were "staged".
Fixed immediately with `git reset --soft HEAD~1` (no content touched) and re-committed by
explicit pathspec as two separate commits, matching the packet's intent. Content is
identical either way; only the commit boundaries were corrected.

## 2. Pre-steps (§2) — outcomes

1. Removed the resurrected `halbert_core/.../components/brand/HalbertMark.tsx` (unreferenced, untracked, duplicate of the file deleted in `493956ab`).
2. Fixed the doc-comment typo (`Overrides  if provided.` → `` Overrides `density` if provided.``).
3. Aligned `HalbertMark.stories.tsx`'s "4 Lines" candidate label to "Proposed Micro" (matching the badge text).
4. VMK-12 dead branch: kept the `CONFIG_BY_LINE_COUNT[lineCount] || CONFIG_BY_LINE_COUNT[6]` fallback and added a test exercising it via an out-of-range `lines` value cast past the type system (`resolveLineCount` always returns a valid key today, but the fallback documents/guards the boundary rather than being silently deleted).
5. SVG dedup: 20 of the 35 untracked SVGs (10/6/4/3-line tiers × 5 variants) were confirmed whitespace-identical to the already-tracked display/medium/compact/small sets (`diff -bw` = 0 lines) and deleted. Kept the 15 5/7/8-line files, generated the 3 missing `-charcoal.svg` variants (mechanical stroke-color swap to `#1A1918`, matching the existing pattern for every other tier), and documented both the named and numeric tier tables in `assets/brand/README.md`.
6. RNC-06: committed `main`'s copy of `REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md` under its current name (option a); added a header note to the plan doc flagging that `feat/rust-native-core` carries a different, unrelated 382-line document at the same path and must rename it before that branch is next merged.
7. Stripped the machine-specific `~/.claude/projects/...` resume path from `PAUSE-STATE-RUST-ROADMAP-AUGMENTATION-2026-08-31.md`, replaced with "session scratch, gone".
8. Added the superseded banner to `HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md`.
9. `wt_pytest.py` was already present at the repo root (md5 `1e4ec209aa07868d844d807d21b966cc`, matching all four source copies) and confirmed not gitignored — apparently copied by an earlier, interrupted attempt at this same packet. No action needed beyond verifying.

**Verification gates (all green before any commit):**
- `packages/design-system`: `npx vitest run` → 71 passed (70 + 1 new test for the fallback branch).
- `packages/design-system`: `npx tsc --noEmit` → 0 errors.
- `halbert_core/halbert_core/dashboard/frontend`: `npx tsc --noEmit` → 0 errors.

## 3. §5 — `docs/chat-ui-audit` worktree (U3-26)

Compared the worktree's uncommitted, gitignored `11-response-modality-handoff.md` (283
lines, a code-level audit with 10 file:line findings — e.g. TTS speaking raw markdown
syntax, `UserPreferences.verbosity` being dead code, `output-format.xml` loaded but never
sent — plus 8 open questions for an external reviewer) against
`documentation/design/11-response-modality-handoff.md` (517 lines, same date/title).
**Not subsumed** — main's doc is a forward-looking architecture spec (modality matrix,
echo cancellation, speaker gating) with zero textual overlap with any of the worktree
doc's specific findings (verified via grep for `build_response_prompt`,
`output-format.xml`, `UserPreferences.verbosity`, `tts_engine.py`, etc. — 0 matches in
main's doc). Rescued it under a distinct name,
`documentation/design/chat-ui-audit-11-response-modality-findings-2026-08-30.md`, via
`git add -f`, committed in `30aeefe9`, before removing the worktree.

## 4. U6-25/26/27 residue (ported before retiring `worktree-u6-home-simplification`)

Re-verified against current `main` rather than trusting the packet's stale line
references (main had moved past the worktree in this area, apparently via the Opus
batch / OPUS-03):

- **U6-25** (remove dead `secure` resolution in `tier_router.py:162`, `from_legacy`):
  **superseded, nothing to do.** Main's `tier_router.py` already resolves `secure_model`
  live, gated on the `CAP_SECURE_MODEL` capability — that's the intended end state, not
  dead code. The worktree's own version already deliberately does *not* resolve it
  (comment: "would be dead code").
- **U6-26** (stale "three slots" comment in `config_wizard.py:692`): **still real**,
  found at main's current line 694 (the packet's line number had drifted). Fixed in
  `cf9278d2`. Verified with `.venv/bin/python3 -m pytest
  halbert_core/tests/test_config_wizard_schema.py
  halbert_core/tests/test_tier_router_config.py` → 19 passed.
- **U6-27** (add a test that a secure turn skips the dedicated secure slot when
  `CAP_SECURE_MODEL` is absent): **superseded, nothing to do.** Main already has
  `test_home_variant_does_not_read_the_secure_slot` in
  `halbert_core/tests/test_tier_router_config.py`, more precise than the `ef34ae4c`
  shape the packet pointed at (`ef34ae4c` is not an ancestor of main).

## 5. Worktrees removed (12)

```
~/.config/superpowers/worktrees/Halbert/chat-ui-audit              (--force, after §5 rescue)
~/.config/superpowers/worktrees/Halbert/ha-simplification
~/.config/superpowers/worktrees/Halbert/halbert-mcp                (--force; dirty MASTER-TODO confirmed an older copy than main's)
~/.config/superpowers/worktrees/Halbert/modality-voice-phase2
~/.config/superpowers/worktrees/Halbert/rev03-sentient-home-fixes
~/.config/superpowers/worktrees/Halbert/singular-entity
~/.config/superpowers/worktrees/Halbert/voice-mode-reland           (--force; untracked wt_pytest.py only)
~/.config/superpowers/worktrees/Halbert/voice-mode-visual-ui        (--force; 10 dirty tracked files independently re-verified as a strict subset of main's content — 7 byte-identical, 3 where main has strictly more: an analyser-disconnect fix + its test, and a P4 status paragraph)
~/.config/superpowers/worktrees/Halbert/opus-singular-tasks         (--force; clean)
/Volumes/4TB-BAD/Halbert/.claude/worktrees/central-todo-batches     (--force; 7.0 GB, wt_pytest.py already copied+committed)
/Volumes/4TB-BAD/Halbert/.claude/worktrees/voice-mode-opus          (--force; untracked wt_pytest.py only)
/Volumes/4TB-BAD/Halbert/.claude/worktrees/u6-home-simplification   (U6-25/26/27 handled first, see §4)
```

Note: two directory-name/branch mismatches were found and resolved by re-verifying
actual content rather than trusting the packet's path-based comments: the
`voice-mode-visual-ui` path was actually checked out on `feat/voice-mode-mark-v2`, and
the `voice-mode-opus` path was actually checked out on `feat/voice-mode-visual-ui`
(swapped from what the directory names suggest). Both were still in the packet's removal
list under their respective paths, so both got removed; the dirty-content claims were
re-verified against the branch actually present, not the one implied by the path name.

Also removed the plain (non-worktree) directory
`~/.config/superpowers/worktrees/Halbert/home-automation` after saving the
HomeCognitiveLoop wiring draft (lines 578-610, 661-670 of its `app.py`) to
`.handoff/audit-2026-09-01/drafts/home-cognitive-loop-app-wiring-draft.py.txt`, committed
in `6bbcb539`. `git worktree prune` run afterward (no-op, all paths were properly removed).

**Kept** (not touched): `feat/rust-native-core` + its worktree (parked, local-only —
see §7), `feat/security-review-01` + its worktree (SONNET-01's), `feat/shell-redesign` +
its worktree (not mentioned anywhere in this packet; already merged to main via
`941cc14b` — out of scope for SONNET-02, left for whoever owns it).

## 6. Branches deleted

Safe (`-d`, all verified ancestors of `main`):
`docs/chat-ui-audit`, `feat/compute-peer-setting`, `feat/ha-simplification`,
`feat/halbert-mcp`, `feat/modality-voice-phase2`, `feat/rev03-sentient-home-fixes`,
`feat/singular-entity`, `feat/voice-mode-visual-ui`, `voice-mode-v2-backup`,
`worktree-central-todo-batches`.

Force (`-D`, content already on main under a different sha, not a direct ancestor):
`feat/voice-mode-mark-v2`, `feat/singular-entity-opus`, `worktree-u6-home-simplification`.

Also deleted (added by the coordinator, safe ordinary `-d`, identical to `main`
post-fast-forward): `fix/opus-packets-2026-09-01`.

**Remote branch deletion NOT done** — see §7, blocked by the auto-mode classifier.

## 7. Blocked: two `git push` operations

Both were explicitly pre-authorized (the packet's own remote-delete command, and general
permission to run destructive git ops in this session) but the Claude Code auto-mode
classifier denied them outright, the same way it denied `git checkout main` earlier in
this session (which the coordinator resolved by doing it themselves):

1. **`git push origin --delete docs/chat-ui-audit feat/halbert-mcp
   feat/modality-voice-phase2 feat/federated-fleet feat/plan-b-terminals`** — all 5
   confirmed still present on `origin` and re-verified as ancestors of `main` right
   before the attempt (`git merge-base --is-ancestor <branch> main` for each). Ready to
   run; just needs to be run by someone/something the classifier will allow, or a
   permission rule added for `git push` in this session.
2. **`git push` for `main`** and **`git push -u origin feat/rust-native-core`** — per
   this task's own deviation instructions, these were never attempted; reporting their
   pending state below per that instruction.

## 8. Pending-push state (for the coordinator)

- **`main`**: currently `6bbcb539`, **35 commits ahead of `origin/main`** (`941cc14b`),
  **0 behind**. Of those 35: 25 are the Opus 01-05 batch (already coordinator-verified:
  Python 71→26 failures, 0 new regressions across 9 full-suite runs, frontend green) and
  8 are this packet's commits (`a0dc3310` through `6bbcb539`, listed in §1). Not pushed —
  holding for final go-ahead per the deviation instructions.
- **`feat/rust-native-core`**: local-only (`git ls-remote --heads origin
  feat/rust-native-core` returns nothing) — still needs a backup push to origin. Not
  pushed, per deviation instructions; left exactly as found.
- **Remote branch deletions** (`docs/chat-ui-audit`, `feat/halbert-mcp`,
  `feat/modality-voice-phase2`, `feat/federated-fleet`, `feat/plan-b-terminals`): still
  present on origin, ready to delete, blocked only by the classifier (see §7).

## 9. Final state

```
$ git worktree list
/Volumes/4TB-BAD/Halbert                                                     6bbcb539 [main]
/Users/ericbintner/.config/superpowers/worktrees/Halbert/rust-native-core    cc19695d [feat/rust-native-core]
/Users/ericbintner/.config/superpowers/worktrees/Halbert/security-review-01  a09632e1 [feat/security-review-01]
/Users/ericbintner/.config/superpowers/worktrees/Halbert/shell-redesign      601c2fdb [feat/shell-redesign]

$ git branch -a
+ feat/rust-native-core
+ feat/security-review-01
+ feat/shell-redesign
* main
  remotes/origin/HEAD -> origin/main
  remotes/origin/docs/chat-ui-audit
  remotes/origin/feat/federated-fleet
  remotes/origin/feat/halbert-mcp
  remotes/origin/feat/modality-voice-phase2
  remotes/origin/feat/plan-b-terminals
  remotes/origin/feat/shell-redesign
  remotes/origin/main

$ git stash list
(empty)
```

Disk reclaim: the packet's estimate was ≈11 GB; the single largest item
(`.claude/worktrees/central-todo-batches`, ~7.0 GB) plus 11 other worktrees were removed.
Exact before/after bytes were not measured (no baseline `du` was taken before this
session started), so the reclaim figure is not independently confirmed here, only that
all 12 target worktree directories and the `home-automation` plain directory no longer
exist on disk.
