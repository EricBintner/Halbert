# Continuous Conversation — Plan B: Terminal Sessions, Blocks, Watched Shell, Pool, Tasks Column, Light

> **Status: DRAFT** — 2026-08-27. Contracts and task outline only; full inline code not yet generated. Not independently verified. Plan A must be complete before this plan is finalised or executed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Halbert real terminal sessions with command-boundary detection (OSC 133), a PTY-backed agent pool that reuses idle shells, a watched user shell that feeds the timeline, a Tasks column that replaces the accordion dock, and a StatusLight primitive — so terminal tiles stop vanishing, the agent sees what the admin ran, and long-running commands become task cards.

**Architecture:** A byte-state-machine OSC 133 parser (`shell_integration.py`) segments user-shell output into blocks. A `TerminalPool` (`agent_pool.py`) runs agent commands as blocks in reusable PTY sessions. `PTYSession` gets a single-reader fan-out so multiple consumers (xterm, block parser, SSE) all receive every byte. `TerminalSessionManager` gains per-kind caps and TTLs (user/agent-pool/oneshot). Two new SQLite tables (`terminal_blocks`, `terminal_sessions`) persist block records. Redaction runs before any write. The frontend replaces `TerminalAccordionDock` with a `TasksColumn` (Running / Finished / Clear + Your shell), a `StatusLight` primitive (5 states, token-based, forced-colours safe), and block-based tile rendering with replay-on-mount.

**Spec:** `documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md` (§9.1–9.9, §11, §13). Binding names/signatures: `.handoff/plan-b-exec/plan-b-contracts.md`.

**Tech Stack:** Python 3.10 / FastAPI / sqlite3 + FTS5 / pytest + pytest-asyncio (run with `/Volumes/4TB-BAD/Halbert/.venv/bin/python`); React 18 + TypeScript / Vite / vitest + jsdom / Tailwind on the canonical tokens.

**Worktree:** `~/.config/superpowers/worktrees/Halbert/continuous-conversation` (branch `feat/continuous-conversation`, continuing from Plan A's final commit). Baseline after Plan A: backend green except 4 pre-existing failures; frontend green; `tsc` clean; literal-colour ratchet unchanged.

**Prerequisites:** Plan A must be complete (all 27 tasks + amendments). The `terminal_block_ids` column on `messages` stores session ids (Plan A); task B21 migrates it to block ids. `StateContext.terminal_session_ids` exists. `StreamEvent.terminal_spawn/output/complete` factories exist. `TerminalEventBus` exists. `SqliteConversationStore` has `SCHEMA_VERSION = 2` with WAL and idempotent schema migration.

**Verification status of this plan:** Not yet independently verified. The contracts are complete and binding; a verifier pass (like Plan A's) should be run before execution. The task outline below has file targets, test names, and dependencies but does NOT include full inline code — that is for the planner workflow to generate (as Plan A's `plan-a-writers.workflow.js` did).

---

## Task dependency graph

```
B1 (schema) ─────────────────────────────────┐
B2 (redact) ─────────────────────────────────┤
B3 (shell integration: rc files + parser) ──┤
B4 (PTYSession fan-out) ────────────────────┤
B5 (session manager kinds) ─────────────────┤
                                              │
B6 (agent pool) ← B3, B4, B5                 │
B7 (executor wiring) ← B6                    │
B8 (block store methods) ← B1                ├── B21 (block_ids migration) ← B8, B7
B9 (watched user shell) ← B3, B4, B5, B8    │
B10 (stage endpoint) ← B3, B4, B5           │
B11 (terminal route changes) ← B5, B10      │
B12 (new SSE events) ← B7, B9               │
                                              │
B13 (StatusLight) ← (no BE dep)             │
B14 (TerminalTile fixes) ← B4, B12           │
B15 (ToolExecutionCard block) ← B12, B13    │
B16 (TasksColumn) ← B13, B14, B15           │
B17 (YourShellRegion) ← B14, B16            │
B18 (PTY key ownership) ← B14                │
B19 (Sheet below md) ← B16                   │
B20 (token fixes + ratchet) ← B14, B15      │
                                              │
B22 (e2e integration test) ← B7, B9, B14, B16
```

**Parallelisable groups:**
- Group 1 (no deps): B1, B2, B3, B13 — can run in parallel.
- Group 2 (after Group 1): B4, B5, B8, B20 (token fixes are mechanical).
- Group 3 (after Group 2): B6, B9, B10, B11, B12, B14, B15.
- Group 4 (after Group 3): B7, B16, B17, B18, B19, B21.
- Group 5: B22 (final integration).

**Model tier guidance** (from Plan A's method):
- Sonnet (mechanical): B1, B2, B8, B13, B18, B19, B20, B21.
- Strongest available (state machine / parser / pool): B3, B4, B5, B6, B7, B9, B12, B22.
- Sonnet or stronger: B10, B11, B14, B15, B16, B17.

---

## Part S — Storage

### Task B1: terminal_blocks and terminal_sessions tables

**Files:**
- Modify: `halbert_core/halbert_core/agents/conversation_sqlite.py` (schema migration, new methods)
- Test: `halbert_core/tests/test_terminal_store.py` (new)

**What:**
- Bump `SCHEMA_VERSION` to 3.
- Add `terminal_blocks` and `terminal_sessions` tables (contracts §1).
- Add store methods: `insert_terminal_block`, `update_terminal_block`, `get_terminal_block`, `list_terminal_blocks`, `insert_terminal_session`, `update_terminal_session`, `get_terminal_session`, `list_terminal_sessions`.
- Schema migration is idempotent (`_add_missing_columns` pattern + `CREATE TABLE IF NOT EXISTS`).

**Tests:**
- `test_terminal_blocks_crud`: insert, update, get, list by session/thread/turn.
- `test_terminal_sessions_crud`: insert, update watched, get, list by kind.
- `test_schema_version_3_migration`: a v2 db migrates to v3 with both tables present.
- `test_idempotent_migration`: running `_ensure_schema` twice is a no-op.

**Dependencies:** None. Can start immediately after Plan A.

**Commit:** `feat(agents): terminal_blocks and terminal_sessions tables`

---

### Task B2: Redaction module

**Files:**
- New: `halbert_core/halbert_core/streaming/redact.py`
- Test: `halbert_core/tests/test_redact.py` (new)

**What:**
- Implement `redact(text: str) -> tuple[str, bool]` and `redact_bytes(data: bytes) -> tuple[bytes, bool]` (contracts §2).
- Patterns: `password=`, `-p<token>`, `Authorization:`, `Bearer`, `AKIA…`, `hf_…`, `ghp_…`, `BEGIN … PRIVATE KEY` blocks.
- Never raises; on internal error returns `(text, False)`.

**Tests:**
- `test_password_redacted`
- `test_dash_p_token_redacted`
- `test_authorization_header_redacted`
- `test_bearer_token_redacted`
- `test_aws_key_redacted`
- `test_hf_token_redacted`
- `test_github_pat_redacted`
- `test_private_key_block_redacted`
- `test_no_match_returns_unchanged`
- `test_bytes_redact`
- `test_no_crash_on_invalid_utf8`

**Dependencies:** None.

**Commit:** `feat(streaming): redaction module for terminal block writes`

---

## Part M — Machine (Backend Core)

### Task B3: Shell integration — rc files and OSC 133 parser

**Files:**
- New: `halbert_core/halbert_core/shell/bashrc`
- New: `halbert_core/halbert_core/shell/zsh/.zshrc`
- New: `halbert_core/halbert_core/streaming/shell_integration.py`
- Test: `halbert_core/tests/test_osc_parser.py` (new)

**What:**
- Write `shell/bashrc` and `shell/zsh/.zshrc` (contracts §3) — source user's real rc first, then add precmd/preexec hooks emitting OSC 133 A/B/C/D + OSC 7.
- Implement `OSCParser` byte state machine (contracts §3): GROUND → ESC → OSC → CSI → INTERM states; carries partial sequences across reads; produces `ParsedOutput(passthrough, boundaries, block_bytes)`.
- Implement `detect_needs_input(block_tail, silence_seconds)` for password-prompt detection.
- Implement `is_remote_command(command)` for ssh/mosh tagging.
- Alt-screen detection: `\e[?1049h` / `\e[?47h` → `alt_enter`; `\e[?1049l` / `\e[?47l` → `alt_exit`.

**Tests:**
- `test_prompt_start_A_marker`: feed `\e]133;A\a` → boundary kind='A'.
- `test_input_start_B_marker`: feed `\e]133;B\a` → boundary kind='B'.
- `test_output_start_C_marker_with_id_and_cmd`: feed `\e]133;C;id=abc;cmd=$(echo -n "ls" | base64)\a` → boundary kind='C', block_id='abc', command='ls'.
- `test_end_D_marker_with_exit`: feed `\e]133;D;0\a` → boundary kind='D', exit_code=0.
- `test_osc7_cwd`: feed `\e]7;file://host/path\a` → boundary kind='7', cwd='/path'.
- `test_split_sequence_across_reads`: feed `\e]133;` in one chunk and `A\a` in the next → boundary kind='A'.
- `test_interleaved_echo`: output between C and D is attributed to block_bytes.
- `test_alt_screen_enter_exit`: `\e[?1049h` → alt_enter, block marked interactive; `\e[?1049l` → alt_exit.
- `test_passthrough_unchanged`: all bytes appear in passthrough.
- `test_password_prompt_detection`: tail matches `Password: ` with 5s silence → True.
- `test_remote_command_ssh`: `is_remote_command("ssh user@host")` → True.
- `test_remote_command_mosh`: `is_remote_command("mosh user@host")` → True.
- `test_not_remote`: `is_remote_command("ls -la")` → False.

**Dependencies:** None. Can start immediately.

**Commit:** `feat(streaming): shell integration rc files and OSC 133 byte state machine parser`

---

### Task B4: PTYSession fan-out reader

**Files:**
- Modify: `halbert_core/halbert_core/streaming/pty.py`
- Test: `halbert_core/tests/test_pty_fanout.py` (new)

**What:**
- Replace per-caller `loop.add_reader` with a single reader task per session that fans out to every consumer queue (contracts §4).
- Add `attach() -> asyncio.Queue` (starts reader task if not running; first item is `("__replay__", get_buffer())`).
- Add `detach(queue)` (non-blocking; cancels reader task when last consumer detaches).
- Re-implement `read_chunk()` as a thin wrapper around `attach`/`detach` for backward compat.
- `kill()` must cancel the reader task, push None to every fanout queue, then close the fd.
- Add `echo: bool = True` param to `__init__` / `spawn()`; when False, clear `ECHO` on the slave fd before `execvpe`.

**Tests:**
- `test_two_consumers_both_receive_every_byte`: spawn `echo hello`, two `attach()` queues both receive the full output.
- `test_replay_on_attach`: write some output, then `attach()` — first item is `("__replay__", buffer)`.
- `test_detach_stops_receiving`: after `detach(queue)`, no more items arrive.
- `test_kill_wakes_all_consumers`: `kill()` pushes None to every queue.
- `test_read_chunk_backward_compat`: the old `read_chunk()` generator still works.
- `test_echo_disabled`: spawn with `echo=False`, verify ECHO is cleared on the slave (check via `termios.tcgetattr` on the slave fd before exec — or test the behavioural effect: input written to the master does not appear in the output).

**Dependencies:** None (extends existing `pty.py`).

**Commit:** `fix(streaming): single-reader fan-out for PTYSession, replay on attach`

---

### Task B5: TerminalSessionManager kinds/caps/TTLs

**Files:**
- Modify: `halbert_core/halbert_core/streaming/session_manager.py`
- Test: `halbert_core/tests/test_session_manager_kinds.py` (new)

**What:**
- Add `kind` parameter to `spawn()` (contracts §5): `user`, `agent-pool`, `oneshot`.
- Add per-kind caps (`kind_caps`) and TTLs (`kind_ttls`).
- Add `attach_client`/`detach_client` (ws client count) and `set_block_open` (block state).
- `_reap_once()` uses per-kind TTL; user sessions with `attach_count > 0` are never reaped; agent-pool sessions with `block_open` are never reaped.
- `list_active()` returns `kind`, `owner`, `watched`, `block_open`, `attach_count`.

**Tests:**
- `test_user_session_not_reaped_while_attached`: spawn user session, attach_client, advance clock past TTL → not reaped.
- `test_user_session_reaped_after_detach`: detach_client, advance clock past TTL → reaped.
- `test_agent_pool_not_reaped_with_open_block`: spawn agent-pool, set_block_open(True), advance past TTL → not reaped.
- `test_oneshot_reaped_at_60s`: spawn oneshot, advance 61s → reaped.
- `test_per_kind_cap_enforced`: spawn 3 user sessions, 4th raises `AtCapacityError` for kind 'user'.
- `test_list_active_includes_kind_and_watched`: list_active entries have `kind`, `watched` fields.

**Dependencies:** B4 (PTYSession fan-out is needed for the reader task lifecycle).

**Commit:** `feat(streaming): per-kind caps, TTLs, and attach/block-aware reaping`

---

### Task B6: Agent pool

**Files:**
- New: `halbert_core/halbert_core/streaming/agent_pool.py`
- Test: `halbert_core/tests/test_agent_pool.py` (new)

**What:**
- Implement `TerminalPool` (contracts §6): `acquire()`, `run_block(command, cwd, timeout)`, `release(session_id)`, `shutdown()`.
- Pool sessions are `agent-pool` kind in the manager: `bash --norc --noprofile` with `set -m`, ECHO off.
- Block execution: write `printf '\e]133;C;id=<block_id>\a'; <cmd>; printf '\e]133;D;%d;id=<block_id>\a' "$?"\n` to stdin.
- Await the block's D marker with the tool timeout.
- On timeout: write ETX (`\x03`), grace-wait 2 s for D, else kill and evict the session.
- Publish `terminal_spawn` (attach='ws', owner='agent', block_id) and `terminal_complete` via the terminal event bus.
- Fallback to `None` when at cap and all sessions busy/interactive.
- Long-running promotion: when a block is open > 2 s, emit `terminal_block_promote`.

**Tests:**
- `test_run_block_success`: `run_block("echo hello")` → exit_code=0, output contains "hello".
- `test_run_block_cwd`: `run_block("pwd", cwd="/tmp")` → output contains "/tmp".
- `test_run_block_timeout_etx`: `run_block("sleep 10", timeout=0.5)` → exit_code=-1, session evicted.
- `test_run_block_reuse_idle_session`: two consecutive `run_block` calls reuse the same session.
- `test_run_block_fallback_at_cap`: fill the pool, next `acquire()` returns None.
- `test_run_block_fallback_interactive`: session in interactive state → `acquire()` returns None.
- `test_long_running_promotion`: block open > 2s → `terminal_block_promote` event emitted.
- `test_pool_shutdown_kills_all`: `shutdown()` kills all pool sessions.

**Dependencies:** B3 (OSC parser for D marker detection), B4 (PTYSession fan-out + echo param), B5 (session manager kinds).

**Commit:** `feat(streaming): PTY-backed agent terminal pool with block markers`

---

### Task B7: Executor wiring — run_command via pool

**Files:**
- Modify: `halbert_core/halbert_core/tools/executor.py` (`_run_command`)
- Modify: `halbert_core/halbert_core/tools/safety.py` (add `terminal_blocks` to SAFE)
- Test: `halbert_core/tests/test_executor_pool.py` (new)

**What:**
- `_run_command` tries the pool first when `terminal_stream_wanted()` is True (contracts §7).
- Pool path: `pool.run_block(command, cwd, timeout)` → publish spawn/complete events with `block_id` → store the `terminal_block` row → return the same string shape the model sees today.
- Fallback: today's `asyncio.create_subprocess_shell` path (unchanged).
- Add `terminal_blocks` tool schema (contracts §8): SAFE class, returns stored blocks.
- `ctx.terminal_session_ids` appends `block_id` (not session_id) when the pool path is used.

**Tests:**
- `test_run_command_uses_pool_when_streaming`: mock `terminal_stream_wanted()=True`, verify pool is called.
- `test_run_command_falls_back_when_no_stream`: mock `terminal_stream_wanted()=False`, verify subprocess path.
- `test_run_command_falls_back_at_cap`: pool returns None, subprocess path runs.
- `test_run_command_publishes_spawn_with_block_id`: verify `terminal_spawn` event has `block_id`.
- `test_terminal_blocks_tool_returns_stored`: insert blocks, call tool, verify returned.
- `test_terminal_blocks_tool_safe_class`: verify `classify('terminal_blocks')` is SAFE.

**Dependencies:** B6 (pool), B8 (block store methods for storing blocks).

**Commit:** `feat(tools): route run_command through the agent pool with block persistence`

---

### Task B8: Block store methods

**Files:**
- Modify: `halbert_core/halbert_core/agents/conversation_sqlite.py`
- Test: `halbert_core/tests/test_terminal_store.py` (extend B1's file)

**What:**
- Implement `insert_terminal_block`, `update_terminal_block`, `get_terminal_block`, `list_terminal_blocks` (contracts §1).
- These are the write path for B7 (pool blocks) and B9 (user shell blocks).
- All writes are in `with self._conn:` transactions; failures logged at WARNING, return False.

**Tests:**
- `test_insert_and_get_block`: insert a block, get it back by block_id.
- `test_update_block`: insert, update exit_code/ended_at, verify.
- `test_list_blocks_by_session`: insert 3 blocks for session A, 1 for session B, list by session A → 3 rows.
- `test_list_blocks_by_thread`: insert blocks with different thread_ids, list by thread.
- `test_list_blocks_limit`: insert 10 blocks, list with limit=5 → 5 rows, newest-first.

**Dependencies:** B1 (tables exist). Can be done as part of B1 or as a follow-up.

**Commit:** `feat(agents): terminal block store methods (insert/update/get/list)`

---

### Task B9: Watched user shell — block insertion and hint

**Files:**
- New: `halbert_core/halbert_core/streaming/watched_shell.py` (the watcher that runs the OSC parser on user sessions and inserts blocks/messages)
- Modify: `halbert_core/halbert_core/agents/thread_signals.py` (hint extension)
- Modify: `halbert_core/halbert_core/agents/conversation_sqlite.py` (if needed for the origin='terminal' append)
- Test: `halbert_core/tests/test_watched_shell.py` (new)

**What:**
- A `WatchedShellWatcher` that attaches to `user` kind sessions, runs the OSC parser, and on each block close:
  1. `redact()` the output_head/tail.
  2. `store.insert_terminal_block({...})`.
  3. If `watched` and a thread is open: `store.append_message(thread_id, role='system', origin='terminal', content=f"$ {cmd} · exit {ec} · {dur:.1f}s", terminal_block_ids=[block_id])`.
  4. `store.update_thread(thread_id, last_active=now)`.
- Extend `build_hint` (contracts §8): add "Since your last message you ran N commands in your shell (last: ...)" when there are terminal-origin messages since the last human/assistant message.
- Per-session unwatched toggle: `POST /api/terminal/sessions/{id}/watched` suppresses both block insertion and hint.
- Remote blocks (ssh/mosh): inner commands not parsed; only the outer block is recorded.

**Tests:**
- `test_user_block_close_inserts_message`: close a block on a watched user session → `messages` row with `origin='terminal'` and `terminal_block_ids=[block_id]`.
- `test_unwatched_session_no_message`: close a block on an unwatched session → block stored, no `messages` row.
- `test_hint_includes_watched_commands`: thread has terminal-origin messages → hint contains "Since your last message you ran".
- `test_hint_capped_at_8_blocks`: 10 terminal blocks → hint mentions 8.
- `test_remote_block_inner_not_parsed`: ssh block → only the outer block recorded.
- `test_redaction_on_user_block`: block output contains `password=secret` → stored block has `password=[redacted]`, `redacted=1`.

**Dependencies:** B3 (OSC parser), B4 (fan-out attach), B5 (session manager kinds), B8 (block store).

**Commit:** `feat(streaming): watched user shell with block insertion and hint extension`

---

### Task B10: Stage-into-shell endpoint

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/routes/terminal.py`
- Test: `halbert_core/tests/test_stage_endpoint.py` (new)

**What:**
- `POST /api/terminal/sessions/{session_id}/stage` with body `{command: str}` (contracts §9).
- Checks the parser state: last boundary was A or B, no C open, no bytes typed since B.
- If not at prompt: `HTTPException(409, "shell busy")`.
- If at prompt: `session.write_stdin(command)` (no newline).
- Return `{ok: true, staged: command}`.
- The parser state is tracked on the session via the `WatchedShellWatcher` from B9 (or a separate `is_at_prompt(session_id)` method on the manager).

**Tests:**
- `test_stage_at_empty_prompt`: session at prompt (A/B seen, no C) → 200, command written.
- `test_stage_refused_when_busy`: session has an open block (C seen) → 409.
- `test_stage_refused_when_bytes_typed`: bytes typed since B (not at prompt) → 409.
- `test_stage_no_newline`: verify the written data does not end with `\n`.

**Dependencies:** B3 (parser state), B4 (PTYSession write_stdin), B5 (manager).

**Commit:** `feat(terminal): stage-into-shell endpoint with prompt-state guard`

---

### Task B11: Terminal route changes

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/routes/terminal.py`
- Test: `halbert_core/tests/test_terminal_routes.py` (new or extend)

**What:**
- `spawn_session` gains `kind` parameter (default 'oneshot'; 'user' for the Your shell launcher).
- `list_sessions` returns kind, owner, watched, block_open, attach_count (from B5's `list_active`).
- Add `POST /sessions/{id}/watched` endpoint (B9's unwatched toggle).
- Add `GET /sessions/{id}/blocks` endpoint: returns stored blocks for a session (from `store.list_terminal_blocks`).
- Delete the dead `/api/terminal/history` endpoint (repointed at the ledger per spec §9.6).
- WebSocket handler calls `attach_client`/`detach_client` on connect/disconnect.

**Tests:**
- `test_spawn_with_kind_user`: POST /sessions with kind='user' → response includes kind.
- `test_list_sessions_includes_kind`: GET /sessions → entries have kind, watched.
- `test_watched_toggle`: POST /sessions/{id}/watched {watched: false} → GET /sessions shows watched=0.
- `test_get_blocks`: insert blocks, GET /sessions/{id}/blocks → returns them.
- `test_history_endpoint_deleted`: GET /api/terminal/history → 404.

**Dependencies:** B5 (kinds), B8 (block store), B9 (watched toggle), B10 (stage endpoint).

**Commit:** `feat(terminal): kind-aware spawn, watched toggle, block fetch, delete dead history`

---

### Task B12: New SSE events

**Files:**
- Modify: `halbert_core/halbert_core/agents/events.py`
- Modify: `halbert_core/halbert_core/agents/state_machine.py` (handle new event types in `_run_tool_streaming`)
- Test: `halbert_core/tests/test_terminal_events.py` (new)

**What:**
- Add `StreamEvent.terminal_block(session_id, *, block_id, terminal_session_id, command, owner, interactive, promote)` (contracts §10).
- Add `StreamEvent.terminal_needs_input(session_id, *, block_id, terminal_session_id)`.
- Add `StreamEvent.task_completed(session_id, *, task_id, thread_id, title, exit_code, duration, tail)` (factory only; Plan C uses it).
- Extend `terminal_spawn` with optional `block_id` and `owner` params.
- State machine: when a `terminal_block` payload arrives on the bus, yield `StreamEvent.terminal_block(...)`. When `terminal_block_promote`, yield with `promote=True`. When `terminal_needs_input`, yield `StreamEvent.terminal_needs_input(...)`.

**Tests:**
- `test_terminal_block_event_factory`: verify type, data fields.
- `test_terminal_block_promote_event`: verify `promote=True` produces type `terminal_block_promote`.
- `test_terminal_needs_input_event`: verify type, data fields.
- `test_task_completed_event`: verify type, data fields.
- `test_terminal_spawn_with_block_id`: verify `block_id` and `owner` in data.
- `test_state_machine_yields_terminal_block`: mock a `terminal_block` bus payload, verify the state machine yields the event.

**Dependencies:** B7 (executor publishes block events), B9 (watched shell publishes needs_input).

**Commit:** `feat(agents): terminal_block, terminal_block_promote, terminal_needs_input, task_completed events`

---

## Part F — Frontend

### Task B13: StatusLight primitive

**Files:**
- New: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/StatusLight.tsx`
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/StatusLight.test.tsx` (new)

**What:**
- Inline SVG (10px or 14px), 5 states (contracts §11): running, needs_attention, done_unseen, error, blocked.
- SVG `fill`/`stroke` with `currentColor`; parent sets token class (`text-status-nominal`, `text-status-warning`, `text-status-critical`, `text-accent-strong`).
- One transition: `var(--duration-shutter) var(--ease-shutter)` on state change.
- No `animate-*`, no pulses. Forced-colours safe.
- Glyphs: running (none), needs_attention ('!'), done_unseen ('✓'), error ('✕'), blocked ('‖').
- Text: running (mono elapsed timer), needs_attention ('needs input'), done_unseen ('exit 0'), error ('exit N'), blocked ('awaiting approval').

**Tests:**
- `test_running_state`: render with state='running' → outline ring, no glyph, elapsed timer.
- `test_needs_attention_state`: render → '!' glyph, 'needs input' text.
- `test_done_unseen_state`: render → '✓' glyph, 'exit 0' text.
- `test_error_state`: render with exitCode=1 → '✕' glyph, 'exit 1' text.
- `test_blocked_state`: render → '‖' glyph, 'awaiting approval' text.
- `test_uses_current_color`: verify SVG uses `currentColor` for fill/stroke.
- `test_no_animation_classes`: verify no `animate-*` classes.

**Dependencies:** None (pure component, uses existing tokens).

**Commit:** `feat(components): StatusLight primitive — 5 states, token-based, forced-colours safe`

---

### Task B14: TerminalTile fixes — replay-on-mount, block-based, tokens

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.tsx`
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.test.tsx` (new or extend)

**What:**
- **Replay-on-mount**: on mount, call `session.attach()` which sends `("__replay__", buffer)` first; the tile does `term.reset(); term.write(buffer)` then continues with live chunks. This fixes the blank-tile bug.
- **Block-based rendering**: accept a `blockId` prop. When the block is complete, show a frozen `<pre>` from `output_head/tail` and dispose the xterm.
- **Agent-owned**: `disableStdin`, no cursor (unless `owner='user'`).
- **Token fixes**:
  - Line 181: `bg-[#1a1b26]` → `bg-canvas-subtle`
  - Line 199: violet classes → `bg-status-telemetry-bg text-status-telemetry border-status-telemetry-line`
- **IntersectionObserver**: mount guard + `rootMargin`.
- **StatusLight**: replace the `● ■ ○` pill with `<StatusLight>`.
- Remove emoji pin/copy/terminate buttons; use lucide icons with `aria-label`s.

**Tests:**
- `test_replay_on_mount`: mount the tile → xterm receives the replay buffer first.
- `test_frozen_block_after_complete`: block complete → `<pre>` rendered, no xterm.
- `test_no_literal_hex_colors`: verify no `bg-[#` classes.
- `test_no_violet_classes`: verify no `violet` classes.
- `test_status_light_rendered`: verify `<StatusLight>` is in the header.
- `test_agent_owned_disables_stdin`: `owner='agent'` → `disableStdin=true`.

**Dependencies:** B4 (attach/replay), B12 (terminal_block events), B13 (StatusLight).

**Commit:** `fix(components): TerminalTile replay-on-mount, block-based rendering, token fixes`

---

### Task B15: ToolExecutionCard renders block

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/ToolExecutionCard.tsx`
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/ToolExecutionCard.test.tsx` (new or extend)

**What:**
- For a `run_command` tool block, render **its block** (contracts §13):
  - Short block (completed < 2 s): one-line result (`$ smbstatus · exit 1 · 0.3 s`, expandable).
  - Live + long-running: live `TerminalTile` while it is the session's current open block.
  - Frozen once complete: `<pre>` from `output_head/tail` (no xterm, no socket).
- The card's own `<pre>` result is suppressed when a block renders.
- Origin anchor: `data-terminal-block={blockId}`.
- `StatusLight` on the card header (on a `--color-surface` strip).
- Labels are measurements (`exit 0`, never "Success").
- Remove `bg-blue-100`, `border-blue-200`, `text-info` (use `status-*` tokens).
- Remove `animate-spin`.

**Tests:**
- `test_short_block_one_line`: completed block < 2s → one-line result, expandable.
- `test_long_running_live_xterm`: block open > 2s → `TerminalTile` rendered.
- `test_frozen_block_pre`: block complete → `<pre>` from output, no xterm.
- `test_data_terminal_block_anchor`: verify `data-terminal-block` attribute.
- `test_status_light_on_header`: verify `<StatusLight>` in header.
- `test_no_blue_classes`: verify no `bg-blue-100` or `text-info`.
- `test_no_animate_spin`: verify no `animate-spin`.

**Dependencies:** B12 (block events), B13 (StatusLight), B14 (TerminalTile).

**Commit:** `feat(components): ToolExecutionCard renders terminal block with StatusLight`

---

### Task B16: TasksColumn (replaces TerminalAccordionDock)

**Files:**
- New: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/TasksColumn.tsx`
- New: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/TaskCard.tsx`
- Delete: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalAccordionDock.tsx`
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/TasksColumn.test.tsx` (new)

**What:**
- `TasksColumn` (contracts §12): Running section, collapsed Finished N › section, Clear button, Your shell pinned region.
- `TaskCard`: title (command or goal), thread topic, `StatusLight`, elapsed time, ⤴ to originating turn, stop, copy. Body is the block (live xterm while running, frozen `<pre>` once done). Finished cards collapse after 10 minutes. `MAX_VISIBLE=3` for live xterms.
- Replace all references to `TerminalAccordionDock` in the app with `TasksColumn`.
- "live in conversation ⤴" when the inline card has the live xterm.

**Tests:**
- `test_running_section`: running tasks appear in the Running section.
- `test_finished_section_collapsed`: finished tasks in a collapsed `<details>`.
- `test_clear_button`: Clear removes finished cards from the column.
- `test_task_card_status_light`: each card has a `<StatusLight>`.
- `test_task_card_jump_to_turn`: ⤴ calls `onJumpToTurn`.
- `test_your_shell_region_present`: the Your shell pinned region is rendered.
- `test_max_visible_xterms`: 4 running tasks, only 3 have live xterms.
- `test_finished_card_collapses_after_10min`: simulate time → card collapses.

**Dependencies:** B13 (StatusLight), B14 (TerminalTile), B15 (ToolExecutionCard block rendering).

**Commit:** `feat(components): TasksColumn replaces TerminalAccordionDock with Running/Finished/Clear + Your shell`

---

### Task B17: YourShellRegion

**Files:**
- New: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/YourShellRegion.tsx`
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/YourShellRegion.test.tsx` (new)

**What:**
- Renders the user's shell (one session in v1): xterm.js terminal (interactive, ws transport).
- Watched/unwatched toggle (calls `POST /sessions/{id}/watched`).
- Badge if the shell is unhooked (watched: false, no OSC 133).
- "Stage into my shell" target: receives staged commands from the composer (the composer's "stage into my shell" action calls `POST /sessions/{id}/stage`).
- Never a task card.

**Tests:**
- `test_renders_xterm`: verify xterm container is present.
- `test_watched_toggle`: click toggle → calls API with `watched: false`.
- `test_unhooked_badge`: session with `watched=false` → badge rendered.
- `test_stage_target`: composer stages a command → it appears in the shell.

**Dependencies:** B14 (TerminalTile), B16 (TasksColumn layout).

**Commit:** `feat(components): YourShellRegion with watched toggle and stage target`

---

### Task B18: PTY key ownership

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.tsx`
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/contexts/ShellModeContext.tsx` (or wherever Cmd+B is handled)
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.keys.test.tsx` (new)

**What:**
- `xterm.attachCustomKeyEventHandler`: every key except Ctrl+` is consumed by the tile.
- Tile header is the tab stop (Enter/F2 enters the tile); read-only tiles set `tabIndex=-1`.
- `ShellModeContext`'s Cmd/Ctrl+B bails inside `.xterm` (check `e.target.closest('.xterm')`).
- No thread shortcut exists.

**Tests:**
- `test_ctrl_backtick_escapes`: Ctrl+` → focus leaves the tile.
- `test_other_keys_consumed`: any other key → not propagated.
- `test_cmd_b_bails_in_xterm`: Cmd+B inside `.xterm` → mode does not toggle.
- `test_tab_enters_tile`: Tab to header, Enter → tile focused.
- `test_readonly_tabindex_neg1`: read-only tile → `tabIndex=-1`.

**Dependencies:** B14 (TerminalTile).

**Commit:** `feat(components): PTY key ownership — Ctrl+` escape hatch, Cmd+B guard`

---

### Task B19: Sheet below md

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/ContextStage.tsx` (or wherever the right column lives)
- New or modify: a `Sheet` component (if one doesn't exist, use a simple bottom-sheet drawer)
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/ContextStage.sheet.test.tsx` (new)

**What:**
- Below the `md` breakpoint, `ContextStage` (vitals, Tasks column, Your shell) renders as a `Sheet` (bottom sheet) opened from the aggregate `StatusLight` on the `ModeSwitch` tab.
- "Go back to this" opens the sheet, scrolls the timeline, expands the task card.
- Aggregate `StatusLight` on `ModeSwitch`: precedence blocked > error > done-unseen > needs-attention > running; `aria-label="<ai_name> — 1 running, 1 awaiting approval"`.

**Tests:**
- `test_sheet_below_md`: render at < md breakpoint → ContextStage is a Sheet.
- `test_aggregate_light_precedence`: blocked + running → blocked light shown.
- `test_aggregate_light_aria_label`: verify `aria-label` with counts.
- `test_go_back_to_this_opens_sheet`: click aggregate light → sheet opens.

**Dependencies:** B13 (StatusLight), B16 (TasksColumn).

**Commit:** `feat(components): Sheet for ContextStage below md with aggregate StatusLight`

---

### Task B20: Token fixes and literal-colour ratchet

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.tsx` (if not already done in B14)
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/ToolExecutionCard.tsx` (if not already done in B15)
- Modify: `scripts/check_literal_colors.py`
- Modify: `halbert_core/halbert_core/dashboard/frontend/tailwind.config.js` (delete `glow`/`pulse-subtle` keyframes if present)
- Test: run `python3 scripts/check_literal_colors.py --check` (ratchet)

**What:**
- Extend `check_literal_colors.py` `PATTERN` to catch `-[#hex]` (contracts §16):
  ```python
  HEX_PATTERN = re.compile(r'\b(?:bg|text|border|from|to|via|ring|fill|stroke)-\[#[0-9a-fA-F]{3,8}\]')
  ```
- Add `HEX_PATTERN` to the scan and the ratchet.
- Delete `glow`/`pulse-subtle` keyframes from `tailwind.config.js` if they exist.
- `motion-reduce:animate-none` on remaining spinners (if any).
- Re-baseline the literal-colour counts after fixes.

**Tests:**
- `check_literal_colors.py --check` passes (no file grew).
- `tsc --noEmit` clean.

**Dependencies:** B14, B15 (token fixes in those tasks; B20 is the ratchet enforcement).

**Commit:** `chore(tokens): extend literal-colour ratchet to catch hex, delete glow keyframes`

---

## Part D — Migration and Integration

### Task B21: terminal_block_ids migration (session ids → block ids)

**Files:**
- Modify: `halbert_core/halbert_core/agents/conversation_sqlite.py` (add `migrate_terminal_block_ids_to_blocks`)
- Modify: `halbert_core/halbert_core/dashboard/routes/agent.py` (call migration at boot, after Plan A's `run_conversation_boot_hooks`)
- Test: `halbert_core/tests/test_block_id_migration.py` (new)

**What:**
- Implement `migrate_terminal_block_ids_to_blocks()` (contracts §1): for every message with non-empty `terminal_block_ids`, replace session ids with their block ids from `terminal_blocks`. Idempotent.
- Call at boot after Plan A's boot hooks.
- Rename `StateContext.terminal_session_ids` to `terminal_block_ids` (or add an alias) — the field now stores block ids, not session ids.
- Update `ThreadManager.end_turn(..., terminal_block_ids=...)` parameter name (or keep the old name with a comment).

**Tests:**
- `test_migration_replaces_session_ids_with_block_ids`: insert a session id in `terminal_block_ids`, insert blocks for that session, run migration → `terminal_block_ids` contains block ids.
- `test_migration_idempotent`: run twice → no change on second run.
- `test_migration_no_blocks_leaves_as_is`: session id with no blocks → left as-is.
- `test_state_context_uses_block_ids`: verify the state machine appends block ids.

**Dependencies:** B7 (pool stores blocks), B8 (block store methods).

**Commit:** `feat(agents): migrate terminal_block_ids from session ids to block ids`

---

### Task B22: End-to-end integration test

**Files:**
- Test: `halbert_core/tests/test_terminal_e2e.py` (new)

**What:**
- Full integration test over the real state machine + pool + store + watcher:
  1. User sends a message → agent runs `echo hello` via the pool → block stored → tile event emitted.
  2. Second message → agent sees the first turn's block in history.
  3. User shell block closes → `messages.origin='terminal'` row inserted → next turn's hint includes "Since your last message you ran".
  4. Long-running command (> 2s) → `terminal_block_promote` emitted.
  5. Pool at cap → falls back to subprocess.
  6. Stage into shell: composer stages a command → appears in the user's shell.

**Tests:**
- `test_e2e_agent_block_persisted_and_replayed`
- `test_e2e_watched_shell_in_hint`
- `test_e2e_long_running_promotion`
- `test_e2e_pool_fallback_at_cap`
- `test_e2e_stage_into_shell`

**Dependencies:** B7, B9, B12, B14, B16, B21. This is the final task.

**Commit:** `test(agents): end-to-end terminal integration — pool, watched shell, blocks, stage`

---

## Definition of done (spec §13, Plan B scoped)

- All backend tests green except the 4 pre-existing failures.
- All frontend tests green; `tsc --noEmit` clean.
- `check_literal_colors.py --check` passes (no file grew).
- OSC parser handles split sequences, interleaved echo, alt-screen, password prompts.
- Pool reuses idle sessions; falls back to subprocess at cap; ETX timeout works.
- Reaper never kills an attached user shell or a pool session with an open block.
- Two PTY consumers both receive every byte; replay on attach works.
- Redaction runs before all block writes.
- Stage-into-shell refused when not at prompt.
- Watched user shell inserts `origin='terminal'` rows; unwatched does not.
- `terminal_block_ids` migrated from session ids to block ids.
- `StatusLight` renders all 5 states with shape + glyph + text; forced-colours safe.
- `TasksColumn` replaces `TerminalAccordionDock`; Running / Finished / Clear + Your shell.
- `TerminalTile` replays on mount (blank-tile bug fixed); frozen block after reuse.
- `ToolExecutionCard` renders a block (one-line for short, xterm for long-running).
- PTY key ownership: Ctrl+` escapes, Cmd+B bails inside xterm.
- No `bg-[#hex]` or violet classes in terminal components.
- Browser tests: tile survives message 2 and reload; long-running appears in Tasks; `prefers-reduced-motion` → no animations; `forced-colors` screenshot of 5 light states; Tab into tile → Ctrl+` returns focus; Cmd+B inside tile does not toggle.

---

## Notes for the planner workflow

1. **Follow Plan A's method**: contracts → four planners (S/M/D/F) → verifier. The contracts are in `plan-b-contracts.md`. The task outline above is the skeleton; the planner workflow generates full inline code for each task (as `plan-a-writers.workflow.js` did for Plan A).

2. **Plan A must be complete before execution.** The contracts reference Plan A's surface (store schema, state machine, events, frontend hooks). If Plan A's amendments change any signature, update the contracts before planning.

3. **The OSC parser is the hardest single component** (like Plan A's `num_ctx` task). Allocate the strongest model for B3. The pool (B6) is the second hardest.

4. **Frontend tasks B13-B20 can partially parallelise** with backend tasks B3-B12 if the event contracts are stable. B13 (StatusLight) has no backend dependency at all.

5. **B21 (migration) is a one-time boot task** — it runs once and is done. It must run after the schema migration (B1) and after the pool is storing blocks (B7).

6. **The `terminal_block_ids` column rename** (session ids → block ids) is the key interface change between Plan A and Plan B. Plan A stores session ids; B21 migrates to block ids. After B21, `StateContext.terminal_session_ids` should be renamed or aliased to `terminal_block_ids` to avoid confusion.

7. **Token fixes are mechanical** (B20) but must be done after B14 and B15 (which change the components). The ratchet extension in `check_literal_colors.py` is the enforcement.

8. **The `Sheet` below md (B19)** depends on the layout structure. Check how `ContextStage` and the right column are currently rendered before implementing.
