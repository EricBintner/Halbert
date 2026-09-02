# DISPATCH OPUS-04 — Terminals: the reaper bug, the PTY pool, and what Plan B left unwired

**Owner:** an Opus session. **Effort:** medium; one P0 user-facing bug plus resource-safety fixes in async PTY code.
**Parent:** `.handoff/HANDOFF-STATE-OF-WORK-2026-09-01.md` §6.4. Evidence ids (area F2, adversarially verified): `R04-F1..F13`, `R04-POOL`; area F25: `TERM-02..12`, `CC-11`. Report: `REVIEW-RESULTS-REV-04-2026-08-31.md`; design: `documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md`; Plan B merged at `0ba316b2` (B1–B22, despite the plan doc still saying DRAFT).

## Shared rules
- Fresh worktree off main (`-b fix/terminals-rev04`). `git branch --show-current` before every commit. No trailers.
- Python tests ONLY via `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py <paths>`; baseline 71 failures, no new ones. Note `test_terminal_e2e.py` currently fails on a stale `fake_execute` double (`R04-F8`, OPUS-01 fixes it) — apply that 1-line double fix locally if OPUS-01 has not landed, so the bridge e2e guard is live while you work.
- Frontend via `npx vitest run`/`npx tsc --noEmit` only if the founder chooses to mount Plan B's surface (Task 5).
- Files you own: `halbert_core/halbert_core/streaming/**` (`session_manager.py`, `agent_pool.py`, `pty.py`, `terminal_bridge.py`, `emitter.py`), `dashboard/routes/terminal.py`, `dashboard/routes/websocket.py`, `tools/executor.py` (pool gate `:528-531` only), `agents/threads.py` (`_close_due`/`tick` docstring only), frontend `components/shell/ContextStage.tsx`, `components/agent/TasksColumn.tsx`, `YourShellRegion.tsx`, `TerminalAccordionDock.tsx`, `TerminalTile.tsx`. Do NOT edit `agents/state_machine.py` (OPUS-01) or `dashboard/app.py` beyond the reaper/pool start lines (`:642`).

## Task 1 — `R04-F1`: the reaper kills live user terminals after 60 s (P0, ~5 lines)
`routes/terminal.py:306-323` `spawn_session` calls `manager.spawn(wrapped, cwd=…, cols=…, rows=…)` with no `kind=`; `SpawnRequest` (`:85-91`) has no `kind` field; `streaming/session_manager.py:78` defaults `kind="oneshot"`, `:23` TTLs `{"user": 1800, "agent-pool": 900, "oneshot": 60}`, `:257`/`:262` exempt only `kind == "user"` with an attached client; the WS route never calls `attach_client`; `app.py:642` starts the reaper. Fix: pass `kind="user"` (or add `kind` to `SpawnRequest` with a whitelist); call `manager.attach_client(session_id)` after `websocket.accept()` and `detach_client` in the `finally` of `terminal_websocket`; optionally treat any session with an attached WS as user-TTL. Test: user-kind + attached ⇒ not reaped past 60 s; detached user ⇒ reaped at 1800 s.

## Task 2 — Pool resource safety (`R04-F3`, `R04-F4`) (P1, must land before anyone enables the pool)
`streaming/agent_pool.py`: `q = await session.attach()` `:131`, `replay = await asyncio.wait_for(q.get(), 5.0)` `:133`, `await session.write_stdin(block_cmd)` `:142` all precede the `try:` at `:161`, whose `finally` (`:181`) only detaches; `self._manager.set_block_open(sid, False)` at `:206` is unguarded; the busy flag is set at `:55` in `_acquire`; `session_manager.py:264` exempts `agent-pool` + block-open from the reaper → any error before the drain loop leaks a permanently busy PTY slot. `block_output = bytearray()` `:137` grows unbounded (`:154`), head/tail applied only after completion (`:194-199`); the review reproduced ~800 MB RSS; contrast `pty.py:367-372` `_append_buffer` bounded at `_buffer_bytes`. Fix: move attach/replay/write inside the `try`, clear the busy flag in `finally`, evict on the kill path; cap while accumulating (first/last N KiB with an elision marker). Tests for both.

## Task 3 — Bounds and loop hygiene (P2)
- `R04-F7`: `routes/terminal.py:59-63` `CommandRequest.timeout: int = 30` has no ceiling/validator; `:269-276` accumulates output unbounded under `wait_for(drain(), timeout=request.timeout)`. Clamp `1..300` via a pydantic validator; cap output head/tail like the pool.
- `R04-F5`: `PTYSession.kill()` blocks the event loop with synchronous sleeps (~50–70 ms per kill).
- `R04-F6`: PTY fan-out queues are unbounded; the drop-on-overflow branch is unreachable.
- `R04-F12/F13` (plausible): SIGKILLed child not reaped within 20 ms leaks as a zombie; fd pair leaks if `os.fork()` raises.
- `R04-F11`: `streaming/emitter.py` `EventEmitter` is dead code with a shared-queue consumer-splitting bug — delete.
- `R04-F10`: `ThreadManager.tick()` docstring promises a live-terminal guard `_close_due` does not implement — implement or fix the docstring.
- `TERM-10`: `/api/terminal/history` reads a file nothing writes (Plan B B11 said delete/repoint).

## Task 4 — Built-but-unwired: label honestly or wire (founder decisions `R04-POOL`, `R04-F2`, `R04-F9`, `TERM-08`)
- Agent PTY pool: `terminal_bridge.py:140` `_pool_enabled = False`; `set_terminal_pool_enabled` is called only from `tests/test_terminal_e2e.py:121/124`; `tools/executor.py:528-531` gates on `terminal_pool_wanted()`. The subprocess path is the shipped executor. Decision: enable in app startup (only after Task 2) or mark B7 unshipped.
- Watched-shell → thread pipeline (`R04-F2`, B8/B9/B22): no production reader; `/stage` always 409; `/watched` is a no-op; the frontend never calls either (the review's claim that it does is wrong — dead on both sides). `YourShellRegion` (the only component exposing `onToggleWatched`/`onStageCommand`) and `TasksColumn` are rendered by no non-test file; `ContextStage.tsx:18/:73` still renders `TerminalAccordionDock`; `components/agent/index.ts:23` still exports it. Plan B B16 ("replace all references… delete TerminalAccordionDock.tsx") not done.
- Somatic block pipeline (`R04-F9`, C1a–C1d) and subagent seams (`R06-O3`) unwired.
Given "finish current features", present the founder with: (a) wire the watched-shell pipeline + mount `TasksColumn`/`YourShellRegion` + aggregate `StatusLight` on `ModeSwitch` (`TERM-08`, the design's direction: user shells stay but are watched by the AI, indicator-light notifications), or (b) relabel B7/B8/B9/B22/C1a–d as built-unwired in the plan docs and remove the dead endpoints. Do not pick alone; do (b)'s doc part in your results either way.

## Task 5 — Only if the founder picks (a)
Mount `TasksColumn` (Running / Finished N › / Clear) and the pinned `YourShellRegion` in `ContextStage`, retire `TerminalAccordionDock`, wire the aggregate `StatusLight` onto `ModeSwitch` and the Sheet below `md`; implement the production reader for watched blocks and make `/stage` and `/watched` real (`TERM-03`); `TERM-09` PTY key ownership (Cmd/Ctrl+B still toggles mode inside a tile, B18). Plan C (background commands, task notifications, timeline SSE/search, thread export — `CC-11`) stays out of scope.

## Results
`.handoff/RESULTS-OPUS-04-<date>.md`: commits per finding, tests, the decision memo for Task 4 with your recommendation, and the doc corrections for SONNET-05.
