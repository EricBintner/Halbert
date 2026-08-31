# Handoff: Wrap-Up Work for the Successor AI (2026-08-31)

**Audience:** the next AI session picking up the Halbert central task list.
**Predecessor state:** batches U1–U5 of the central list were executed 2026-08-31 and
merged to main at `f112151b` (39 commits, fast-forward, verified: backend 4,083 passed /
67 pre-existing failures, none new; frontend 451/451, tsc + build clean).
**Companion docs (read these first):**
- `.handoff/HANDOFF-CENTRAL-TODO-BATCHES-2026-08-31.md` — full state of what landed, by batch
- `.handoff/HANDOFF-WRAP-UP-2026-08-31.md` — this file: what YOU do next
- `.handoff/FOUNDER-DECISION-DRAFTS-2026-08-31.md` — the four founder-gated drafts
- `.handoff/REVIEW-RESULTS-REV-*.md` (×10) — the remediation backlog, with file:line + scenarios

---

## 0. How to run things

- Tests from the MAIN tree: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -q`
  (the `arch -arm64` prefix is required — universal2 starts x86_64 otherwise).
- Tests from any WORKTREE: the shared venv's editable install pins `halbert_core` to the
  MAIN tree; plain pytest silently tests the wrong code. Use the wrapper pattern at
  `.claude/worktrees/central-todo-batches/wt_pytest.py` (strips the editable finder,
  prepends the worktree package dir, asserts resolution, then runs pytest).
- Baseline: main carries ~67 pre-existing test failures. Do not chase them unless a task
  names them; DO keep any change you make from adding to the set.
- Founder rules in force: never name/recommend AI models in user-facing surfaces; no
  emojis in UI; no "Co-Authored-By"/"Generated with" trailers in commits; never write
  "Sovereign" on user-facing surfaces; colours come from the shared tokens, never hardcoded.
- If a founder names a handoff file you cannot find, look in the WORKTREES
  (`.claude/worktrees/*/` and `~/.config/superpowers/worktrees/Halbert/*/`) — it will be
  there. Never guess at a missing file's contents; ask.

## 1. First: bring the central task list up to date (mechanical)

`MASTER-TODO.md` still shows items as open that are now done. Strike through and date
(§1 of that doc explains the convention) from `.handoff/HANDOFF-CENTRAL-TODO-BATCHES-2026-08-31.md` §1:
- Security section: the dispatch/egress/CORS/phrase verification item; the rebuild-index
  item (script exists); the three missing test files (created; `test_redactor.py`
  deliberately skipped as duplicate coverage — note it).
- Voice section: the four TASK-07 items; the ThreadManager injection item; the
  StreamingTagDemuxer/speech_chunk/modality-prompt-builder/modality_context items
  (landed under different names via the modality merge — see handoff doc §U2); the voice
  UI components item; the Rust AEC + NSPanel item.
- Frontend section: Settings decomposition, nav consolidation, Security→Findings rename,
  the chat-UI token-buffer/ARIA items.
- Model routing: `HALBERT_MODEL` env wiring; the role harvester; GPU deep-scan refactor;
  TASK-09/TASK-10 verification items.
- REV-01/REV-02's findings are fixed; REV-03's were fixed separately (already on main).

## 2. The remediation backlog (the real work, in priority order)

Reviews found real defects with file:line + reproduced scenarios. Fix by report. The
top-severity items across reports, ranked:

1. **REV-09 F1 (severe, security):** Wyoming TCP server binds `0.0.0.0:10400`, enabled by
   default, NO authentication — any LAN host drives agent turns and executes medium-risk
   tools. Bind loopback by default + add the peer-token auth (the federation PeersConfig
   already exists). Then REV-09 F2 (voice turns run on a second event loop and clobber
   the shared state machine's `ctx`/LLM params — restructure to submit turns to the
   main loop).
2. **REV-10 F1 (severe, security):** peer pairing is self-service — `POST /api/peers/pair`
   returns the PIN to the requester and `verify` issues a full bearer token with no
   desktop-user confirmation, no expiry, no rate limit; a paired peer can revoke legit
   peers. Add a confirmation step on the desktop side (the ComputePeerCard/fleet UI is
   the natural surface). COORDINATE on F2/F3 (compute endpoint never mounted; health-probe
   path mismatch) with whichever session owns the compute-peer/federation work — that is
   federation-9.3+ territory and half-owned elsewhere.
3. **REV-04 F1 (user-facing):** the idle reaper kills live user terminal tiles after 60s —
   `spawn_session` defaults `kind="oneshot"` and no production path creates `kind="user"`,
   and the WS route never calls `attach_client()`. Then F3 (pool slot leak), F4 (unbounded
   `block_output`), F2 (dead watched-shell wiring), F8 (dark e2e guard from test rot).
4. **REV-06 F1/F2:** two regressions in the state machine's prompt-assembly seams that
   break 30 agent-core tests and corrupt multi-turn planning — read the report's exact
   seams before touching anything; these are subtle.
5. **REV-11 F1 (HIGH):** every normally-completed turn aborts its own SSE stream
   mid-drain and POSTs `/api/agent/cancel` for itself (`useAgentStream.ts:379-390`); the
   cancel can flip a fully-streamed reply to "cancelled" in the store. Then F2 (queued
   send drops pending approvals), F3 (StrictMode double-fire), plus the 13-item worklist.
6. **REV-05 F1/F2 (High):** `peer://` chat turns break the production streaming path
   (no `peer` branch in `_stream_turn`; every home-variant chat turn errors) — compute-peer
   session territory, coordinate; and Apple Intelligence auto-provision can assign a dead
   chat slot on eligible Macs (bridge absent) — gate on `apple_intelligence_bridge_running`.
7. **REV-08 (4 findings):** Approvals page orphaned off the rail (HIGH); NavRail ARIA
   tabs pattern half-implemented (no arrow keys, dangling `aria-labelledby`); 2 hardcoded
   colour violations (VisionTab, Findings); polling leak in the Settings shell.
8. Everything else in the reports (lower findings, PLAUSIBLE items) — triage as you go.

Do not start new batches or re-run completed reviews. TDD for fixes; one report's
findings = one focused commit set.

## 3. Rust voice follow-ups (from `HANDOFF-CENTRAL-TODO-BATCHES` §3)

The AEC pipeline (`e10ea62f`) and NSPanel/CGEventTap HUD (`057990e9`) are committed,
feature-gated (`voice-capture` / `aec` features, OFF by default), compile- and
unit-verified — but not yet useful:
1. The Python consumer of the loopback socket (127.0.0.1:18400, 16 kHz mono PCM; TTS
   far-end reference on port+1) — wire it into `integrations/voice_backend.py` / the
   audio pipeline so mic capture replaces the dead VAD path (REV-09's 480-vs-512 frame bug
   is in the same neighborhood — fix both together).
2. The frontend `voice-hud` route the pill window loads — build a minimal HUD surface.
3. On-hardware runtime verification (mic + tap + panel) — needs the founder's machine,
   schedule it.
4. Decide whether `macos-private-api` (enabled for the transparent pill) is acceptable
   for the App Store target, or the HUD ships only in the Pro channel.

## 4. Founder-gated (do NOT close; remind, draft, wait)

- FDR-DEC-01…04: drafts committed (`.handoff/FOUNDER-DECISION-DRAFTS-2026-08-31.md`).
  The founder ratifies/amends; nothing ships until they do.
- D2/D4 ratification from the U6 simplification (option-b boundary; home/home-light merge)
  — evidence in the U6 handoff.

## 5. Cleanup (safe, low priority)

- `.claude/worktrees/central-todo-batches/` — fully merged; `git worktree remove` it and
  delete branch `worktree-central-todo-batches`.
- Branch `feat/compute-peer-setting` — empty pointer, delete.
- Stash `stash@{0}` ("duplicate U6-S3 compute-peer work") — obsolete duplicate of work
  another session landed; drop after a glance.
- The 67 baseline failures: worth one triage pass someday (several are REV-06's seam
  regressions and test rot named in the reports).

## 6. Coordination notes

- Sessions run concurrently on this repo — before starting, `git fetch` and check
  `origin/main`; re-read any handoff doc you inherit; work in a worktree for anything
  large; commit small; never leave another session's uncommitted work in your `git add`.
- The compute-peer / federation continuation (REV-05 F1, REV-10 F2/F3, federation-9.3+)
  may have an owning session — check for a newer handoff before claiming it.