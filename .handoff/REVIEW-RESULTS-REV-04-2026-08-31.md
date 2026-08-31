# REV-04 Review Results — Continuous Terminal / Somatic Nervous System

**Date:** 2026-08-31
**Reviewer pass:** GLM-5.3 adversarial architectural review with end-to-end verification
**Packet:** `.handoff/REVIEW-PACKET-04-SOVEREIGN-HOST-AND-TERMINALS.md` (2026-08-29)
**Code reviewed:** worktree `central-todo-batches` @ `ae376866`; findings re-spot-checked unchanged at current HEAD `51082f83` (`git diff ae376866 HEAD` touches none of the reviewed files)
**Method:** full read of the terminal subsystem, somatic package, continuous session engine, and continuity wiring; adversarial trace of each suspected defect; dynamic reproductions for the pool leak, the unbounded output accumulation, and the event-loop stall; terminal/continuity test suites run read-only via `wt_pytest.py` (1 failed / 93 passed — the failure is itself a finding, F8). No production code modified.
**Naming note:** per the founder directive the review covers the architecture only; no user-visible surface was found that writes the word "Sovereign" (the engaged surfaces use the onboarding name / "Host Controls" labelling), so the directive is respected by the current code.

---

## 1. Scope reality check (packet vs. current code)

The packet's file map is stale. The terminal subsystem no longer lives in `agents/terminal_pool.py` / `agents/watched_shell.py`; it moved to `halbert_core/halbert_core/streaming/`:

- `streaming/pty.py` (402 l) — async PTY session, fork+exec, fan-out reader, bounded scrollback
- `streaming/session_manager.py` (293 l) — kind-capped session registry + idle/dead reaper
- `streaming/agent_pool.py` (255 l) — `TerminalPool` (agent PTY bash pool, OSC 133 blocks)
- `streaming/watched_shell.py` (148 l) — `WatchedShellProcessor` (user-shell block → thread pipeline)
- `streaming/terminal_bridge.py` (154 l) — E1f event bus between executor and state machine
- `streaming/shell_integration.py` (280 l) — OSC 133/7 parser, alt-screen tracking
- `dashboard/routes/terminal.py` (505 l), `dashboard/routes/websocket.py` (126 l)
- Continuity: `agents/threads.py` (1033 l), `agents/thread_signals.py` (443 l), `agents/conversation_sqlite.py` (2309 l)
- Session engine: `agents/state_machine.py` (3276 l), `agents/conversation_status.py`, `agents/blocks.py`
- Somatic: `somatic/{block,store,lifecycle,checkpoints}.py` (794 l total)

Plan A (continuous conversation: SQLite thread store, receipts, thread segmentation, `<continuity>` hint) **has landed and is wired**: `ThreadManager` is constructed in production, `begin_turn`/`end_turn` bracket every turn under the turn lock, boot heals `in_progress` rows (`app.py:85`). Plan B (terminals) has landed as **primitives plus tests, but not as wiring** — see F1/F2/F3/F9: several load-bearing seams are never invoked by any production code path.

---

## 2. Verdicts per area

| Area | Verdict |
|---|---|
| PTY primitives (`pty.py`) | **PASS with defects.** Fork+`TIOCSCTTY`+exec chain is correct (ctty acquired, master closed in child, EIO-echo disabled for pool shells); scrollback bounded at 1 MiB with oldest-trim; `is_alive()` does a non-blocking reap so abandoned readers can't strand zombies on the normal path. Defects F5, F6, F12, F13. |
| Session manager & reaper (`session_manager.py`) | **PASS with one fatal misapplication.** Kind caps/TTLs, dead-session sweep, and stdout-as-activity are sound; `kill()` cleans every tracking dict. But the reaper's user-session exemption is keyed to `kind="user"` + attach counts, and **no production path ever creates a `user` session or increments an attach count** — F1, the most severe finding. |
| Agent terminal pool (`agent_pool.py`) | **FAIL as shipped.** The pool is correct in the happy path (subshell `exit` isolation, OSC 133 block ids the command cannot spoof, ETX→grace→kill escalation), but `terminal_pool_wanted()` requires `set_terminal_pool_enabled(True)`, which **only tests call** — the pool is unreachable in the running app, and when enabled it carries F3 (permanent slot leak on any error) and F4 (unbounded memory). |
| Watched-shell → thread pipeline (`watched_shell.py`, B8/B9/B22) | **FAIL — dead code in production.** `process_block_close`, `update_parser_state`, and `insert_terminal_session` have no production callers; `/sessions/{id}/stage` always answers 409 "shell busy"; the terminal hint in `begin_turn` is always None; the `watched` toggle persists to a table nothing ever populates. The "nervous system" loop — shells observed → blocks redacted → thread memory → next-turn hint — is unwired end to end (F2). |
| Somatic blocks (`somatic/`, C1a–C1d) | **NOT WIRED.** Store, lifecycle, and checkpoints are competently built and unit-tested, but the production agent is constructed without `somatic_lifecycle`/`somatic_store` (`routes/agent.py:253`), `ctx.current_somatic_block_id` is never set by anything, and the `session_somatic_blocks` table has no writer. The 5-phase pipeline cannot run in the shipped app (F9). |
| Continuous session engine (`state_machine.py`) | **PASS.** No new deadlock found. Bounded turn-lock wait (600 s, `TURN_LOCK_TIMEOUT_S`), `_settle_turn` returns the machine to IDLE on exception/disconnect, terminal guard on RESPONDING failure, ERROR give-up at 3 attempts bounded by a transition to RESPONDING, cancellation polled between handler steps *and* between yielded events, `aclosing()` at both SSE route consumers. The terminal bridge drain (`_run_tool_streaming`) balances subscribe/unsubscribe in a `finally` and cancels the tool task on consumer loss. One process defect: the flagship e2e test is red (F8), so this wiring is unguarded. |
| Cross-session continuity (`threads.py`, `thread_signals.py`, `conversation_sqlite.py`) | **PASS with one doc/code lie.** This layer shows multiple completed review rounds in-code (windowed topic sets, fenced system rows, margin gate, per-close locking, `_locked` manager, WAL-fallback schema migration, `RedactionFailed` as the single raising path) and I found no new corruption or race: single connection + RLock, `BEGIN IMMEDIATE` migration serialization, every write transactional, failures return falsy rather than raising. Defect F10: `tick()`'s docstring promises a live-terminal guard the code does not implement. |
| Terminal event bridge (E1f, `terminal_bridge.py`) | **PASS.** Bounded queues (512) with drop-oldest, ContextVar session propagation set/reset in the executor's `finally`, `has_subscribers` fast path — genuinely zero-cost when nobody listens. |
| HTTP/WS terminal routes (`terminal.py`, `websocket.py`) | **FAIL with defects.** F1 (reaper kills attached interactive tiles) and F7 (client-controlled unbounded timeout + unbounded output accumulation on `/exec`). WS bridge itself is sound (both pumps torn down on either side closing, session deliberately left for reattach). |
| Subagent / daemon seams | **NOT WIRED.** `spawn_subagent`/`await_subagent_completion` and the `WAITING_FOR_EVENTS` status exist but the production agent is constructed without `subagent_manager`; consistent with the 2026-08-26 audit's "orchestrator = stubs". Out of defect scope; noted so the packet's "subagent daemons" claim is not read as shipped. |

---

## 3. Findings (most severe first)

Line numbers are from the reviewed tree (`ae376866`); all confirmed unchanged at HEAD.

### F1 — CONFIRMED (High, user-facing today): the reaper kills interactive terminal tiles after 60 seconds of quiet

`dashboard/routes/terminal.py:320` (`spawn_session`) calls `manager.spawn(...)` **without `kind=`**, so every interactive session a user opens is `kind="oneshot"` — TTL 60 s (`session_manager.py:23`). The reaper's only exemption ("user sessions with attached clients are never reaped", `session_manager.py:262-265`) requires `kind="user"`, which **no production code path ever creates** (`kind=` appears only in `agent_pool.py:65`), *and* requires `attach_client()` to have been called — which `dashboard/routes/websocket.py:61-125` never does. `SpawnRequest` (`terminal.py:85-91`) has no `kind` field, so the frontend cannot ask for one either.

**Failure scenario (live today):** the admin opens a terminal tile (POST `/sessions` + WS attach, which `useTerminalSessions.ts` does), runs `ssh` into a quiet router, opens `man`, or simply thinks for more than 60 s without typing and without output. `last = max(last_activity, last_output_at)` goes stale, the reaper (started in `app.py:644`, 10 s period) kills the session, and the WS receives `{"type":"exit"}` — the user's shell is gone mid-use. The 1800 s `user` TTL and the attach-count guard exist precisely to prevent this and are both unreachable.

**Fix:** spawn user-facing interactive sessions with `kind="user"` in `spawn_session`; call `manager.attach_client(session_id)` / `detach_client(session_id)` at WS accept/disconnect; consider defaulting unknown kinds' reaper TTL to the user TTL when a WS is attached.

### F2 — CONFIRMED (High, architectural): the watched-shell → thread pipeline is dead code in production

Repo-wide grep (production trees, tests excluded) shows no caller for any of: `WatchedShellProcessor.process_block_close` (`watched_shell.py:51`), `TerminalSessionManager.update_parser_state` (`session_manager.py:184`), `insert_terminal_session` (`conversation_sqlite.py:2076`). Consequences, each verified directly:

- No reader loop parses user-shell output into `BlockRecord`s, so no block is ever redacted, stored, or appended to a thread as a `terminal`-origin message. The whole point of "shells are watched by the AI" (founder direction, 2026-08-26) is unimplemented in the shipped path.
- `is_at_prompt` always returns False (no parser state is ever recorded) → `POST /sessions/{id}/stage` (`terminal.py:402`) **always answers 409 "shell busy"** — the staging feature (B9) cannot work, and the frontend `ContextStage` component is talking to a dead endpoint.
- `is_interactive` always False → the pool's alt-screen/needs-input skip logic (`agent_pool.py:53`) is inert.
- `begin_turn`'s terminal hint (`threads.py:339-346`) calls `build_hint_text`, which reads a table nothing populates → always None; the "Since your last message you ran N commands" hint never renders.
- `set_watched` (`terminal.py:425-431`) persists to `terminal_sessions`, a table with zero rows ever inserted — the UPDATE is a silent no-op behind a bare `except Exception: pass`.

**Fix:** add the missing reader: one `OSCParser` + `WatchedShellProcessor` per `user`-kind session fed from the PTY fan-out, and call `update_parser_state` from it; call `insert_terminal_session` from `spawn`. Until then, mark B8/B9/B22 as unshipped in the plan docs rather than shipped.

### F3 — CONFIRMED (High, latent until the pool is enabled): `run_block` leaks a permanently-busy PTY slot on any error between `acquire` and the drain loop

`agent_pool.py`: `attach()` (line 131), the replay `q.get()` (133) and `write_stdin(block_cmd)` (142) all run **before** the `try:` at line 161 whose `finally` only detaches the queue; the busy flag is cleared at line **206**, outside any exception guard. An `OSError` (EIO when the pool shell died — the exact case `write_stdin` raises), a replay timeout, or a `CancelledError` at any of those awaits leaves `manager._block_open[sid] = True` forever.

**Reproduced end to end** (script, this worktree's code): patching `PTYSession.write_stdin` to raise EIO once, `run_block` propagates `OSError` and afterwards — session still in the manager, `alive=True`, `block_open=True`, one fan-out queue still attached (unbounded, accumulating all output, F6); **every later `run_block` returns None** (cap-1 pool permanently dead, silent subprocess fallback only); a full `_reap_once()` pass leaves the session alive because `agent-pool + block_open` is reaper-exempt (`session_manager.py:264`). Net result: a leaked bash process, a leaked queue, and a permanently diminished pool per failure — with no recovery except process restart.

**Fix:** hoist the busy flag into the `finally` (`set_block_open(sid, False)` on every exit, evicting the session on the kill path), and move the attach/replay/write sequence inside the `try`.

### F4 — CONFIRMED (High, latent until the pool is enabled): `block_output` accumulates without bound — packet §5.1 is unresolved in the pool

`agent_pool.py:138,154`: `block_output = bytearray()` collects **every** block byte with no cap; the head/tail caps are applied only after the command finishes (194-199). The wall-clock timeout bounds it in time, not in bytes.

**Reproduced:** a 300 MiB-emitting command (`dd | tr`) through the pool grew peak process RSS by roughly **800 MiB** (bytearray + decode + head/tail copies ≈ 2.7× amplification), and the 60 s drain timeout does not help: at PTY throughput a 60 s window accumulates hundreds of MB before the ETX ever fires. `cat /dev/urandom` in a stuck pipe is the pathological case the packet named, and it is unguarded.

**Fix:** cap `block_output` while accumulating (keep first N and last N bytes, e.g. 64 KiB each, with an elision marker), mirroring `pty.py::_append_buffer`'s bounded-scrollback approach.

### F5 — CONFIRMED (Medium): `PTYSession.kill()` blocks the event loop for ~50–70 ms per kill

`pty.py:340,347`: synchronous `time.sleep(0.05)` after SIGTERM and `time.sleep(0.02)` after SIGKILL, inside a sync method called from the async reaper task (`_reap_once`), from route handlers, and from the pool's timeout path. **Measured: 54 ms** of loop stall for one kill on this machine. A reaper pass that kills N dead sessions stalls every concurrent request — SSE streams, WS pumps, the agent turn — for N × ~70 ms, every 10 s.

**Fix:** make kill async (`await asyncio.sleep`) or reap via `loop.call_later` / `asyncio.wait_for(os.waitpid(...))` on a thread; at minimum, drop the sleeps and rely on the next `is_alive()` poll.

### F6 — CONFIRMED (Medium): fan-out queues are unbounded; the "drop on overflow" defence is unreachable

`pty.py:119-132`: `attach(*, _maxsize=0)` — `asyncio.Queue(maxsize=0)` means **infinite**, and no caller passes a size (`read_chunk`, `run_block`, the WS route all use the default). `_push_to_all`'s `QueueFull` branch (`pty.py:190-193`) with its "never block the reader on one slow consumer" comment is therefore dead code.

**Failure scenario:** a WS client stalls (TCP backpressure blocks `send_text`, so `pump_stdout` stops draining) while its session chatters (build log, `tail -f`) — the abandoned queue accumulates without bound. Same exposure for the SSE `/stream` route. (Contrast: the terminal bridge's bus is correctly bounded at 512 with drop-oldest — `terminal_bridge.py:47,96-104` — proving the intent existed.)

**Fix:** attach with a real bound (e.g. 1024 chunks) and drop-oldest in `_push_to_all`; the scrollback already guarantees a re-attacher can replay.

### F7 — CONFIRMED (Medium): `/exec` accepts a client-controlled unbounded timeout and accumulates unbounded output

`dashboard/routes/terminal.py:62` — `CommandRequest.timeout: int = 30` with **no ceiling**; `timeout=86400` holds a PTY and the drain for a day. `output = bytearray()` (line 269) accumulates every byte until that timeout, with no cap. Combined: an unauthenticated-by-tier dashboard client can pin a session-manager slot and grow server memory arbitrarily (`/exec` of a noisy command with a huge timeout). The executor's own `run_command` path correctly clamps to its default; the route does not.

**Fix:** clamp `timeout` (e.g. `min(max(1, timeout), 300)`) and cap the `output` bytearray (head/tail like the pool does).

### F8 — CONFIRMED (Medium, process): the flagship terminal e2e test is red — bridge coverage is dark

`halbert_core/tests/test_terminal_e2e.py::test_e2e_agent_block_persisted_and_replayed` **fails** (1 failed / 93 passed): the test's `fake_execute` predates the `speaker_role` kwarg the state machine has passed since the voice TASK-07 commit (`state_machine.py:2356`), so every turn dies in the EXECUTING handler with a `TypeError` and the assertion on `terminal_spawn` never sees one. The only end-to-end guard of the E1f bridge (executor → bus → state machine → SSE tile events → persisted block ids) has been silently reporting nothing. Fix the fake's signature and re-run; until then any regression in the bridge ships unnoticed.

### F9 — CONFIRMED (Medium, architectural): the somatic block pipeline is unwired in the shipped app

The production agent is constructed without `somatic_lifecycle`/`somatic_store` (`dashboard/routes/agent.py:253-265`), `StateContext.current_somatic_block_id` (`states.py:139`) is never set by any code, and the `session_somatic_blocks` table (`conversation_sqlite.py:352`) has no writer. `_handle_reflecting`'s C1d seam (`state_machine.py:2669-2680`) is therefore unreachable. The store/lifecycle/checkpoints are solid in isolation (correct status mapping, checkpoint-before-execute with rollback-on-unclear), but nothing can ever create a block. Recommend either wiring the detector → lifecycle path or marking C1a–C1d "built, unwired" in the plan docs so the packet's "somatic telemetry ingested" claim is not read as shipped.

### F10 — CONFIRMED (Low): `tick()`'s docstring promises a live-terminal guard that does not exist

`threads.py:556-557`: "Plan B adds the live-terminal guard: never close while a terminal session of this thread is open (spec §5 'Stale')" — but `_close_due` (`threads.py:795-804`) checks only the grace window and successor turns; no code consults terminal sessions (today it couldn't: sessions never carry a thread id). Either implement the check when F2's wiring lands or delete the claim — docstrings that promise guards invite exactly the misplaced trust this review is for.

### F11 — CONFIRMED (Low): `EventEmitter` is a dead module carrying a latent consumer-splitting bug

No production caller of `get_event_emitter`/`init_event_emitter` exists. If it were wired as-is: `subscribe()` (`emitter.py:144-162`) hands **the same queue** to every SSE stream for a session id, so two consumers split each other's events; and hitting `max_subscribers` silently evicts the oldest live session. Delete the module, or fix per-consumer queues before anyone wires it.

### F12 — PLAUSIBLE (Low): a SIGKILLed child that is not reaped within 20 ms is leaked as a zombie forever

`pty.py:349-355`: `kill()` ends with an unconditional `self._exited = True`. If the post-SIGKILL `waitpid(WNOHANG)` returns 0 (uninterruptible wait, being ptraced, scheduler delay), `is_alive()` short-circuits on the flag forever and nothing ever reaps the pid. Requires an unusual child state, so PLAUSIBLE rather than CONFIRMED; a final blocking-or-threaded reap (or not setting `_exited` until a successful reap) closes it.

### F13 — PLAUSIBLE (Low): PTY descriptor pair leaks if `os.fork` raises

`pty.py:224-239`: `os.openpty()` succeeds, then `os.fork()` raising (EAGAIN under a process-limit) leaves master and slave open with no object registered anywhere to close them — and `manager.spawn` never registers the session either. Rare trigger, trivial fix (close both fds on the failure path).

---

## 4. Resolved from the packet (verified in current code)

- **§6 Process isolation & signal safety** — RESOLVED. `PTYSession.kill()` escalates SIGTERM → 50 ms → SIGKILL → 20 ms → reap (caveats F5/F12); the executor's subprocess path kills the child on timeout *and* on any reader failure, including the closed-std-fds daemonising case (`executor.py:578-615`). Verified live in the reproduction script.
- **§6 State machine deadlock analysis** — RESOLVED. No conversation can strand in a non-terminal state: every handler exception routes to ERROR (give-up at 3 attempts → RESPONDING), a RESPONDING failure ends the session instead of looping, consumer disconnect reaches the settled-IDLE path via the double `finally` in `process()`, and the turn lock's wait is bounded at 600 s (`state_machine.py:215,534-557,670-692`). The prior audit's "terminals built for one turn" no longer applies to the agent-bridge path, which streams tiles live (though see F3/F4 for the pool and F8 for its dead e2e guard).
- **§5.1 PTY stream backpressure** — PARTIALLY RESOLVED. Bounded: PTY scrollback (1 MiB, `pty.py:367-372`) and the terminal bridge (512, drop-oldest). Unbounded: pool `block_output` (F4), `/exec` output (F7), fan-out queues (F6).
- **§5.3 Daemon reboot recovery** — PARTIALLY RESOLVED. `in_progress` message rows are healed to `interrupted` at boot (`app.py:85` → `threads.py:414` → `store.mark_in_progress_interrupted()`). There is no `ABORTED_ON_RESTART` for terminal/background-task records — moot today because terminal sessions are never persisted (F2) and subagents are not wired; add it when those land.
- **§5.2 Frontend virtualized renderer** — out of backend scope, not assessed; the frontend surface exists (`HostShell.tsx`, `useTerminalSessions.ts`, `TerminalTile.tsx`), and the WS scrollback the hook keeps is client-side bounded.
- Packet's commit map (§3) — superseded: all listed A1/A2a commits are folded into the current `conversation_sqlite`/`state_machine`/`blocks` modules; `StreamEvent` unification (A0b) confirmed present.

---

## 5. Recommended order of work

1. F1 — one-line `kind="user"` + two `attach_client` calls; it is the only finding users hit today.
2. F8 — fix the e2e test's `fake_execute` signature so the bridge is guarded again.
3. F3 + F4 — fix the pool before enabling it (they ship together with the wiring work).
4. F2 + F9 — decide: wire the watched-shell reader and the somatic lifecycle, or relabel them unshipped; do not leave the plan docs claiming the nervous-system loop.
5. F5/F6/F7/F10-F13 — bounded follow-ups.