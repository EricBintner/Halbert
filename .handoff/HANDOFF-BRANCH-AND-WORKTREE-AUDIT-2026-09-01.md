# Handoff: Branch & Worktree Audit — 2026-09-01

> **SUPERSEDED by HANDOFF-STATE-OF-WORK-2026-09-01.md; see its §2.4 for corrections.**

> **Date:** 2026-09-01
> **Scope:** All 14 worktrees/branches in Halbert plus uncommitted changes on `main`, cross-checked against `.handoff/MASTER-TODO.md`.
> **Method:** Read-only git log/diff/show + targeted pytest/vitest runs per branch. No branches switched, nothing merged or deleted.
> **Companion:** family-wide summary in `/Volumes/4TB-BAD/Haloysius/.handoff/HANDOFF-ECOSYSTEM-STATUS-AUDIT-2026-09-01.md`.

---

## Do this first — unmerged HIGH-severity fix

- [ ] **Merge `feat/security-review-01`'s 2 remaining commits to `main`.** `MASTER-TODO.md`'s "merged into main at `297ceb67`" is only half true — that merge landed an *earlier* state of the branch. Two commits made after it, `9e057db7` (redactor hardening: base64 size/depth caps, nested-JSON leaf redaction) and `c5b6bb91` (MCP path allowlist for `get_config_value`/`get_config_structure`/`get_config_dependencies`), never made it to `main`. `c5b6bb91` closes a live **HIGH-severity arbitrary-file-read** hole — those three config-query tools can currently read arbitrary paths (e.g. `~/.ssh/id_rsa`, `/etc/shadow`) via traversal. Both commits' own tests pass (73/73) and a `git merge-tree` dry run against current `main` is clean.
- [ ] Land `5057e893` (REV-02 findings doc, sitting on `worktree-central-todo-batches`, confirmed NOT on `main`) — documents 6 new findings including **F1 (HIGH): autonomy escalation via a client-supplied `confirm` boolean** on `set_autonomy_level`/`approve_proposal`.
- [ ] Decide whether to commit the two untracked docs sitting in the `security-review-01` worktree (`SCOPE-01-SECURITY-REVIEW-PROGRESS.md`, `SCOPE-01-DUPLICATE-WORK-RECONCILIATION.md`) — the reconciliation doc already has a ready-made merge plan.
- [ ] Correct `MASTER-TODO.md`: `test_tier2_guarantee.py` and `test_security_roles.py` already exist on `main` (via `5a132654`) — drop them from the "missing tests" list. `test_redactor.py`'s absence is a deliberate, documented decision (coverage lives in `test_redact.py`/`test_mcp_response_boundary.py`/`test_secure_response.py`), not an open gap.

## Broken as committed — needs a decision, not just a commit

- [ ] **`feat/voice-mode-mark-v2`** — its one commit (`25213235`, new tine-density geometry) removes exports (`TINE_COUNT`, `STATIC_TINE_PATHS`, array-shaped `TINE_AMPLITUDES`) that `springs.ts`, `spectrum.ts`, and `AudioReactiveHalbertMark.tsx` still import. Merged alone, the design-system package won't build. **The fix is already sitting uncommitted in the same worktree** (`~/.config/superpowers/worktrees/Halbert/voice-mode-visual-ui`) — confirmed 39/39 vitest tests pass with it applied.
- [ ] Before committing that fix: reconcile against `voice-mode-v2-backup` (`38e95899`), which independently contains a more complete version of the same "v2 mark tuning" work plus `VoiceMode.tsx`/`App.tsx`/`ShellModeContext` wiring this branch never got. Neither branch is an ancestor of the other — pick one lineage.
- [ ] Once reconciled, this still needs unifying with `feat/voice-mode-visual-ui`'s Opus-tier work (O1-O8, P1-P4) before the overall Voice Mode feature is mergeable.

## Ready to commit — finished, just needs a commit

- [ ] Uncommitted changes on `main`: 4/5/7/8-line HalbertMark density tiers (backward-compatible `lines` prop), 35 new brand SVGs, a 2,640-line Rust-native-core plan augmentation, and a new semantic-audit handoff doc. **23/23 tests pass, `tsc --noEmit` clean** — this is finished work, not a mid-edit.
  - [ ] Fix a dropped word in the new `lines` prop's JSDoc ("Overrides&nbsp;if provided." should name `density`).
  - [ ] Consider splitting into separate commits (density-tier code / brand assets / Rust-roadmap docs / semantic-audit doc are unrelated concerns riding together).
  - [ ] Add a `MASTER-TODO.md` pointer to `HANDOFF-SEMANTIC-AUDIT-AND-TERMINOLOGY-REVIEW-2026-09-01.md` so it isn't orphaned.

## Safe to retire — fully superseded, no code action needed

- [ ] **`worktree-u6-home-simplification`** (16 commits) — technically sound (232 tests pass), but `feat/ha-simplification` finished the same Batch U6 workstream further and was merged to `main` on 2026-08-30; you already ported this branch's unique tests over in `092117dd`. A merge-tree dry run shows real conflicts in ~33 files against current `main`. Delete the worktree and branch.
- [ ] **`feat/singular-entity-opus`** (7 commits, Opus O1-O6) — every commit's content is already on `main`, either byte-identical or superseded by a more complete version via `feat/singular-entity`. Merging now would *regress* `main` (loses the P4c degraded-marker fix, `wol_timeout`, `delete_peer`, the peer-token endpoint). Delete the branch and worktree at `~/.config/superpowers/worktrees/Halbert/opus-singular-tasks`.
- [ ] While cleaning up, update `MASTER-TODO.md`'s Batch U6 row (S1-S7, D1-D4) — it still lists all of Batch U6 as unchecked despite it being merged via `feat/ha-simplification`.

## Deferred, no action expected

- **`feat/rust-native-core`** — real code (a working `halbert-mqtt` crate + 4-crate workspace scaffold), but deliberately self-paused at an architecture decision gate (R2.1, eBPF framework: aya vs. libbpf-rs) pending external review. 70 of 72 planned tasks are untouched. Consistent with deferring the full Rust rebuild until current features are done and tested — leave as is.
