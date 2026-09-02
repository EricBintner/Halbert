# DISPATCH SONNET-02 — Commit the dirty `main` tree, canonical `wt_pytest.py`, retire merged branches/worktrees/stashes

**Owner:** a Sonnet session. **Effort:** low-medium, mostly mechanical, but it touches shared state — go slowly. **Order:** FIRST of all packets.
**Parent:** `.handoff/HANDOFF-STATE-OF-WORK-2026-09-01.md` §2, §3.2. Evidence ids: `MD-01..18`, `VMK-06..12` (verified), `RNC-06..11` (verified), `RET-01..12`, `STASH-01/02`, `HADIR-01`, `WT-01`, `U3-26`, `SEO-05`, `U6-01`, `VM-20/21`.

## Shared rules
- This packet works directly in `/Volumes/4TB-BAD/Halbert` on `main` because the uncommitted work lives there. Before starting: `git -C /Volumes/4TB-BAD/Halbert status --porcelain` must show exactly the state described in §1; if a concurrent session has changed it, stop and re-read.
- Stage by explicit pathspec only (never `git add -A` / `git add .`). No `Co-Authored-By`/generation trailers. Check `git branch --show-current` = `main` before each commit.
- Never edit `.handoff/MASTER-TODO.md` beyond committing the existing Rust hunk (SONNET-05 owns content changes).
- Do not delete anything listed as "keep" in §3 without re-running the verification command shown.

## 1. Expected starting state (main `4a7bf71f`)
Modified: `.handoff/HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md`, `.handoff/MASTER-TODO.md` (one hunk, lines 165-193, Rust section only), `.handoff/RUST-NATIVE-CORE-TODO-AND-IMPLEMENTATION-PLAN-2026-08-31.md` (426→2,640 lines), `packages/design-system/src/primitives/HalbertMark.tsx`, `src/stories/HalbertMark.stories.tsx`, `src/test/primitives.test.tsx`.
Untracked: `.handoff/HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md`, `HANDOFF-SEMANTIC-AUDIT-AND-TERMINOLOGY-REVIEW-2026-09-01.md`, `PAUSE-STATE-RUST-ROADMAP-AUGMENTATION-2026-08-31.md`, `REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md`, `HANDOFF-STATE-OF-WORK-2026-09-01.md`, `DISPATCH-2026-09-01-*.md`, `audit-2026-09-01/` (this audit), `REVIEW-REQUEST-SHELL-ARCHITECTURE-AND-ENTITY-NAV-2026-09-01.md` (795 lines, written 18:31 by a concurrent GLM session — a design-stage review request, no code; commit it with the handoff docs), 35 `assets/brand/halbert-mark-*lines*.svg`, and `halbert_core/halbert_core/dashboard/frontend/src/components/brand/HalbertMark.tsx` (git status output is long — use `--untracked-files=all`).

## 2. Pre-steps (all verified necessary)
1. `rm -rf halbert_core/halbert_core/dashboard/frontend/src/components/brand/` — a resurrected copy of a component main deleted in `493956ab`; unreferenced, hardcoded hex colours, would fail the token gate. Never stage it.
2. Fix `packages/design-system/src/primitives/HalbertMark.tsx:45`: `* Overrides  if provided.` → ``* Overrides `density` if provided.``
3. Align `HalbertMark.stories.tsx`: line 50 says `candidate: 'Proposed Small'`, line 108 badge says `Proposed Micro` — pick one label (keep "Micro").
4. Dead branch noted by the verifier: `HalbertMark.tsx:202` `CONFIG_BY_LINE_COUNT[lineCount] || CONFIG_BY_LINE_COUNT[6]` can never take the right-hand side because `resolveLineCount` already clamps — either remove the fallback or add a test for an invalid `lines` value (prefer the test; `VMK-12`).
5. SVGs: of the 35 untracked files, 20 are byte- or whitespace-identical duplicates of the tracked `display/medium/compact/small` sets (`10lines`, `6lines`, `4lines`, `3lines` × 5 variants). Delete those 20. Keep the 15 `5lines`/`7lines`/`8lines` files. Add `-charcoal.svg` for 5/7/8 (the tracked tiers have 6 variants incl. `-charcoal`; the new ones have 5) or amend `assets/brand/README.md:31`; add 5/7/8 rows to the README tier table. (Founder decision `VMK-09`(b) — migrating the whole tracked set to numeric names — is NOT this packet.)
6. `REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md` collides with a different 382-line document committed on `feat/rust-native-core` (`cc19695d`). Default (founder decision `RNC-06`, option a): commit main's copy under its current name and leave a note in the plan doc header that the branch's same-named file must be renamed (`…-EXTERNAL-2026-08-31.md`) when that branch is next touched. If the founder has chosen (b), rename main's copy to `REVIEW-RESULTS-RUST-NATIVE-CORE-SANITY-2026-08-31.md` and fix references: `MASTER-TODO.md:185`, plan doc lines 4 and 10, HA-STRATEGY lines 4, 507, 528 (`grep -rn REVIEW-REQUEST-RUST-NATIVE-CORE .handoff`).
7. `PAUSE-STATE-RUST-ROADMAP-AUGMENTATION-2026-08-31.md` is a finished historical record but embeds a machine-specific `~/.claude/projects/...` resume path. Strip that path (replace with "session scratch, gone") and commit, or delete it — either is fine.
8. `HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md` is superseded and wrong on four claims (state-of-work §2.4). Add a one-line banner at its top: "SUPERSEDED by HANDOFF-STATE-OF-WORK-2026-09-01.md; see its §2.4 for corrections." then commit it as history.
9. Copy `wt_pytest.py` to the repo root: `cp .claude/worktrees/central-todo-batches/wt_pytest.py /Volumes/4TB-BAD/Halbert/wt_pytest.py` (all four copies are md5-identical `1e4ec209aa07868d844d807d21b966cc`). Confirm it is not gitignored (`git check-ignore -v wt_pytest.py` → nothing).

Verification before committing: in `packages/design-system` run `npx vitest run` (expect 70 passed) and `npx tsc --noEmit` (0); in `halbert_core/halbert_core/dashboard/frontend` run `npx tsc --noEmit` (0).

## 3. Commits (in this order, each by pathspec)
1. `chore(test): add wt_pytest.py worktree test wrapper` — `wt_pytest.py`.
2. `feat(design-system): HalbertMark explicit line counts via lines prop; density aliases preserved` — the three design-system files.
3. `feat(brand): 5/7/8-line mark variants` — the 15 (+3 charcoal) SVGs and `assets/brand/README.md`.
4. `docs(rust): apply sanity review — 72-task plan, FFI waves, Docker track, scoping amendments` — `RUST-NATIVE-CORE-TODO-AND-IMPLEMENTATION-PLAN-2026-08-31.md`, `HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md`, `MASTER-TODO.md`, `REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md` (or renamed), `PAUSE-STATE-…` if kept.
5. `docs(handoff): semantic-audit proposal, 2026-09-01 state-of-work audit and dispatch packets` — `HANDOFF-SEMANTIC-AUDIT-AND-TERMINOLOGY-REVIEW-2026-09-01.md`, `HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md` (with banner), `HANDOFF-STATE-OF-WORK-2026-09-01.md`, `DISPATCH-2026-09-01-*.md`, `audit-2026-09-01/`.

After committing, `git status --porcelain` must be empty. Push main.

## 4. Retire (every branch below is a verified strict ancestor of main — re-check with `git merge-base --is-ancestor <branch> main && echo ok` before each delete)
```
# worktrees (--force where they hold untracked noise)
git worktree remove --force ~/.config/superpowers/worktrees/Halbert/chat-ui-audit        # see §5 first
git worktree remove        ~/.config/superpowers/worktrees/Halbert/ha-simplification
git worktree remove --force ~/.config/superpowers/worktrees/Halbert/halbert-mcp          # dirty MASTER-TODO is an OLDER copy already on main
git worktree remove        ~/.config/superpowers/worktrees/Halbert/modality-voice-phase2
git worktree remove        ~/.config/superpowers/worktrees/Halbert/rev03-sentient-home-fixes
git worktree remove        ~/.config/superpowers/worktrees/Halbert/singular-entity
git worktree remove --force ~/.config/superpowers/worktrees/Halbert/voice-mode-reland    # untracked wt_pytest.py only
git worktree remove --force ~/.config/superpowers/worktrees/Halbert/voice-mode-visual-ui # 10 dirty files = strict subset of main (VMK-02)
git worktree remove --force ~/.config/superpowers/worktrees/Halbert/opus-singular-tasks
git worktree remove --force /Volumes/4TB-BAD/Halbert/.claude/worktrees/central-todo-batches   # 7.0 GB
git worktree remove --force /Volumes/4TB-BAD/Halbert/.claude/worktrees/voice-mode-opus
git worktree remove        /Volumes/4TB-BAD/Halbert/.claude/worktrees/u6-home-simplification
# branches
git branch -d docs/chat-ui-audit feat/compute-peer-setting feat/ha-simplification feat/halbert-mcp \
  feat/modality-voice-phase2 feat/rev03-sentient-home-fixes feat/singular-entity feat/voice-mode-visual-ui \
  voice-mode-v2-backup worktree-central-todo-batches
git branch -D feat/voice-mode-mark-v2 feat/singular-entity-opus worktree-u6-home-simplification   # content on main, sha not an ancestor
# remote
git push origin --delete docs/chat-ui-audit feat/halbert-mcp feat/modality-voice-phase2 feat/federated-fleet feat/plan-b-terminals
# stashes (both already on main: client.py:76 via 0514a5c3; PeerPairingModal line 147)
git stash drop stash@{1}; git stash drop stash@{0}
# not a worktree — plain directory; save the HomeCognitiveLoop wiring draft first (LOOP-01)
mkdir -p .handoff/audit-2026-09-01/drafts && sed -n '578,610p;661,670p' ~/.config/superpowers/worktrees/Halbert/home-automation/halbert_core/halbert_core/dashboard/app.py > .handoff/audit-2026-09-01/drafts/home-cognitive-loop-app-wiring-draft.py.txt
rm -rf ~/.config/superpowers/worktrees/Halbert/home-automation
git worktree prune
```
Keep: `feat/security-review-01` + its worktree (SONNET-01 merges it), `feat/rust-native-core` + its worktree (parked; **push it**: `git push -u origin feat/rust-native-core` — it is local-only with no backup).

Before retiring `worktree-u6-home-simplification`, port its three cosmetic residues to main in one small commit (`U6-25/26/27`): remove the dead `secure` resolution in `model/tier_router.py:162` (`from_legacy`), fix the stale "three slots" comment in `model/config_wizard.py:692`, and add a test that a secure turn skips the dedicated secure slot when `CAP_SECURE_MODEL` is absent (branch commit `ef34ae4c` has the test shape). Coordinate: SONNET-03 owns `tier_router.py`/`config_wizard.py` — do this only if SONNET-03 has not started, otherwise hand it to them.

## 5. `docs/chat-ui-audit` worktree (`U3-26`)
Its README has one uncommitted line linking `11-response-modality-handoff.md`, a 283-line file that is gitignored (`.gitignore:108 docs/`) and exists nowhere in git. Compare it with `documentation/design/11-response-modality-handoff.md` (517 lines, same date and subject). If subsumed (expected), discard and remove the worktree. If not, `git add -f` it under `documentation/design/` with a distinct name before removing the worktree — removing first loses the file.

## 6. Results
Expected reclaim ≈ 11 GB. Write `.handoff/RESULTS-SONNET-02-<date>.md` with the commit shas, the final `git worktree list` and `git branch -a`, and anything you chose not to delete and why.
