# Sovereign Host v2.0 — Post-Review Findings & Wrap-Up

**Created:** 2026-08-25 (wrap-up session, after all 23 strategy tasks landed)
**Reads with:** [FABLE-HANDOFF-SOVEREIGN-HOST-2026-08-25.md](FABLE-HANDOFF-SOVEREIGN-HOST-2026-08-25.md), [OPUS-HANDOFF-SOVEREIGN-HOST-2026-08-25.md](OPUS-HANDOFF-SOVEREIGN-HOST-2026-08-25.md)

## What happened in the wrap-up

A 29-agent adversarial review of the completed opus-track work (commits
0b35a7e..cc39617, all phases A–F against the OPUS handoff spec) produced
**39 findings → 23 adversarially verified → 21 confirmed real** (2 refuted).
The 6 live-path criticals/majors were fixed, verified, and committed (see
below); the rest are deferred here. Backend suite at wrap-up: **940 passed**
(+4 failures in `test_dashboard_main.py` owned by the in-flight licensing
workstream — see "Known red tests" at the bottom).

## Fixed this pass (verified green)

| Defect | Fix mechanism | Commit |
|---|---|---|
| state_machine give-up path crashed with `error → success` ValueError, leaked internal message to SSE | `_handle_responding` guards the SUCCESS transition behind `conversation_status.is_terminal()` | 4d5a7a5 (+ tests in 9a1402c) |
| PTY `read_chunk()` hung forever if `kill()` ran mid-iteration | `kill()` pushes EOF sentinel into all in-flight reader queues (`_read_queues`) | b4958c9 |
| Child PTY never acquired a controlling terminal → sudo password prompts broken | `TIOCSCTTY` ioctl in child after `setsid()` | b4958c9 |
| Injection evasions: `dd of=/dev/...` (any arg order), `curl \| python3\|perl\|node`, `rm -r -f /` sailed through both gates | Broadened patterns in `injection_check.py` + `terminal.py`; regression tests for every evasion string | b4958c9 |
| Terminal tile froze permanently at the 1 MiB scrollback cap (length stops growing, writer compares lengths) | `droppedChars` monotonic trim counter; tile writes by absolute stream offset | bf5a072 |
| Reflex events bypassed ProactiveGate (quiet hours / safe mode defeated, `reflex_escalate` force-published) | Reflex publish now goes through `gate.should_notify()` | 9b07b95 (folded) |
| Cascade-disabled routing was NOT byte-identical to pre-C2b (different complexity scorer) | Original `_score_complexity` restored; disabled path uses it; parity regression test | 9b07b95 (folded) |
| Reaper idle-TTL ignored stdout activity (dormant until reaper was wired; activated by 0a91afd) | `PTYSession.last_output_at` stamped per chunk; `_reap_once` takes `max(touch, last_output_at)` | 4c9bf1c |

Note: several wrap-up fixes were folded into concurrent workstreams' commits
(9b07b95, 4d5a7a5, 48e9a9c) — multiple sessions were committing to main
simultaneously. Content verified present; attribution is muddy.

## DEFERRED — unwired code (fix BEFORE enabling the feature)

These defects are inert today because the containing feature has no production
call path. Each becomes live the moment the feature is wired in.

1. **CRITICAL — `agents/conversation_sqlite.py:211`**: `save()` is not
   transactional. A mid-save exception leaves pending DELETE/upsert statements
   that the *next unrelated* save's `commit()` finalizes → silent conversation
   data loss. Migration (`migrate_json_conversations_to_sqlite`) hits the same
   path. Fix: explicit transaction + `rollback()` in the except. *Required
   before the SQLite store replaces the JSON conversation store.*
2. **CRITICAL — `model/cascade_router.py:178`**: `route()` passes
   `model.model_id` into `predict()`/`_tier_of()`, which compares against
   config tier primary names (logical names) — every model classifies as
   "other" and tier priors never apply. *Required before enabling the cascade
   router (currently opt-in OFF).*
3. **MAJOR — `model/tier_router.py:617`**: with the cascade router enabled, a
   persistent `GenerationError` on the routed model causes unbounded recursion
   in `generate()` — the cascade path ignores model health and re-selects (or
   falls back to) the same model. Same gate as #2.
4. **MAJOR — `agents/conversation_sqlite.py:284`**: raw user query into FTS5
   `MATCH` aborts the whole `search()` on syntax error, skipping the title
   LIKE fallback the docstring promises. Consumer: session_affinity (unwired).
5. **MAJOR — `agents/conversation_sqlite.py:404`**: migration counts every
   file as migrated even when `save()` silently failed → reports full success
   with missing message history.
6. **MAJOR — `context/watermark.py:85`**: `micro_compact` truncates EVERY
   `tool_result` block including the most recent one — destroys the tool
   result the agent most needs on its next turn. Spec says "old" blocks only.
   Module currently has no production importer.
7. **DESIGN — `context/watermark.py:132`**: `detect_topic_change` is raw
   Jaccard word overlap (no stopwords/stemming, threshold 0.3). The review's
   "defect" claim was refuted *because nothing calls it yet*, but the 2h
   temporal gate is bypassed whenever `topic_changed` flips — revisit before
   wiring F4 in.
8. **Subagent system is unreachable end-to-end** (`agents/state_machine.py:607`
   + `agents/subagent.py` + `agents/subagents/storage_auditor.py`):
   nothing routes a `spawn_subagent` tool call from PLANNING; no production
   code executes a subagent. Consequences that must be fixed when wiring D:
   - `SubagentManager` has no timeout/reaper → a crashed executor permanently
     leaks a concurrency slot (`subagent.py:160`).
   - `await_subagent_completion` crashes with ValueError if the conversation
     was cancelled while waiting (`state_machine.py:504`, CANCELLED has no
     outbound edges).
   - Timeout path emits bogus lifecycle event ('queued'/'running' instead of
     'timed_out'); the still-running handle lingers (`state_machine.py:496`).
   - `StorageAuditorAgent` records a Finding but never creates/emits the
     spec-required SomaticBlock (`storage_auditor.py:134`); the manager's
     `somatic_store` is dead code.
9. **Terminal UI is unreachable** (`hooks/useTerminalSessions.ts`): nothing in
   the frontend ever calls `store.spawn()`, and `useAgentStream` does not
   handle the E1f-specified `terminal_spawn` / `terminal_output` /
   `terminal_complete` events. The dock always renders empty. Note: the fable
   track's `useIntersectionDock` hook and `TetherChip` component are delivered
   but likewise unwired (by design — wiring belongs to a follow-up task that
   was never run).

## DEFERRED — live but non-breaking (needs design care)

10. **`model/tier_router.py:556`**: the A2b rate-limiter integration wrote its
    own `while True` retry loop with blocking `time.sleep()` instead of
    delegating to `ErrorRecoveryManager.execute_with_retry()` as the spec
    mandated ("wrap, don't rewrite"). Additionally the circuit-breaker sharing
    is one-directional: `record_failure(model_id)` is called on 429/529 but
    `record_success()` / `is_circuit_open()` are never consulted → failure
    counts grow monotonically and the `RateLimiter.blocked_until` window is
    never checked. Live code, but only visible under rate-limit storms.

## Minors (16, reported by review, not adversarially verified)

- `streaming/pty.py:222` — `kill()` blocks the event loop with `time.sleep()`
  (~70 ms per session).
- `streaming/pty.py:190` — `write_stdin` single blocking `os.write`; can
  short-write when the input buffer is full.
- `streaming/pty.py:175` — second concurrent `read_chunk()` on one session
  clobbers the first reader (partially mitigated by the `_read_queues` fix —
  verify).
- `dashboard/routes/terminal.py:103` — cols/rows accepted unbounded; >65535
  crashes `struct.pack` in `_set_winsize` (500s).
- `agents/session_affinity.py:104` — tier-2 scoring excludes the current
  session from candidacy; a weak keyword hit on an old conversation can
  outrank the current one. (Unwired anyway.)
- `model/cascade_router.py:31` — `_TECH_KEYWORDS` contains 'diagnose' twice →
  one occurrence double-counts (+0.16 instead of +0.08).
- `somatic/checkpoints.py:70` — `rollback()` pops the checkpoint before the
  restore write; on write OSError the only copy of pre-action content is lost.
- `agents/state_machine.py:852` — C1d wired only REFLECTING; the spec's
  EXECUTING→advance_to_action and proposals→advance_to_proposal seams absent.
- `agents/state_machine.py:428` — ProactiveEvent for somatic blocks drops
  finding_id/proposal_id (no deep-linking from the proactive feed).
- `somatic/lifecycle.py:172` — `block.action_id` set to the proposal id,
  contradicting block.py's doc that action_id references the execution.
- `agents/state_machine.py:465` — spawning a second subagent while waiting
  leaves conversation metadata pointing at the first handle. (Unwired anyway.)
- `agents/subagent.py:51` — `SubagentHandle.to_dict()` omits
  `agent_config_snapshot`; `subagent_event_to_stream` drops
  error/result_block_id.
- `agents/state_machine.py:1090` — A2c broadcasts TRANSIENT_ERROR for every
  recovery attempt without calling `error_recovery.classify_error()` (spec
  deviation).
- `dashboard/frontend/.../TerminalAccordionDock.tsx:55` — MAX_VISIBLE (3)
  live-xterm cap not actually enforced: expanded dock rows mount live
  TerminalTiles regardless of visibility flag.
- `dashboard/frontend/.../useTerminalSessions.ts:133` — unexpected WebSocket
  close permanently marks a still-running PTY as done (exit -1), no reattach.
- `TerminalAccordionDock.tsx:55` — `toggle()` mutates the external store
  (`setVisible`) inside a `useState` functional updater (must be pure).

## Known red tests at wrap-up (NOT sovereign-host scope)

`halbert_core/tests/test_dashboard_main.py` — 4 failures
(`test_main_creates_app_and_runs_uvicorn`, `test_main_reload_uses_import_string`,
`test_module_help_exits_zero`, `test_env_defaults`), all
`ImportError: cannot import name '__version__' from 'halbert_core'
(unknown location)`. Cause: the licensing workstream committed
version/legal-metadata tests (c265725) while the matching `dashboard/__main__.py`
edit was still uncommitted WIP, and under pytest-from-repo-root the editable
install resolves `halbert_core` as a *namespace* package rooted at the outer
project dir, so `from .. import __version__` can never resolve there. Owner:
the licensing session. If this persists after their next commit, the test-side
fix is to ensure `halbert_core/` (inner) precedes the repo root on pytest's
`sys.path`, or to import the version in tests via the editable finder path.

## Process notes for future multi-track handoffs

- Multi-session commits to a shared `main` + `git add` whole-index commits
  will sweep other sessions' staged WIP. Fix agents must be told explicitly
  (and re-told) not to commit, or run in isolated worktrees.
- The review found that several phases (D subagents, F1 SQLite store, F2
  affinity, F4 watermark, terminal-spawn UI, cascade router) are *committed
  but inert*. Wiring them is follow-up work, and each has a "fix before
  enabling" item in this document.

## Suite state at wrap-up (2026-08-25)

- Backend: **940 passed**, 2 skipped (haloysius guards), + the 4 known
  licensing-WIP failures above.
- Frontend: `npx tsc --noEmit` clean.
- Pushed: local main == origin/main.
