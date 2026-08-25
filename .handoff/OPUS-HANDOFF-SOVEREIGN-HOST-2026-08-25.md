# Opus-and-Lower Handoff — Sovereign Host v2.0

**Created:** 2026-08-25
**Model tiers:** opus (hardest), sonnet (standard)
**Reads with:**
- [STRATEGY-V2-SCRUTINY.md](../documentation/sovereign-host-vision/STRATEGY-V2-SCRUTINY.md) — factual audit and corrected task list
- [IMPLEMENTATION-STRATEGY-2026-08-25.md](../documentation/sovereign-host-vision/IMPLEMENTATION-STRATEGY-2026-08-25.md) — v2.0 strategy
- [THIRD-PASS-SCRUTINY.md](../documentation/sovereign-host-vision/THIRD-PASS-SCRUTINY.md) — risk analysis
- [CROSS-CODEBASE-PATTERN-INVENTORY.md](../documentation/sovereign-host-vision/CROSS-CODEBASE-PATTERN-INVENTORY.md) — patterns to steal from OCC and Warp

---

## What You're Doing

You are the **main track**. You own everything except the 3 fable tasks (A0a, E1d, E1e). The fable track is handling those in parallel — do not do them.

You have **20 tasks** across 6 phases. Two tracks can run in parallel within your work: the **foundation track** (Phase A → C → D → F) and the **PTY track** (Phase B → E). They touch different files and can proceed simultaneously until they converge at Phase D/E.

---

## Critical Context: What Already Exists

**Read [STRATEGY-V2-SCRUTINY.md](../documentation/sovereign-host-vision/STRATEGY-V2-SCRUTINY.md) §1-2 before starting.** The v2.0 strategy has 8 factual errors about what exists. Key corrections:

1. **Phases 6-8 of the existing roadmap are COMPLETE.** Being config, proactive event bus, gate, morning report scheduler, module registry, module invocation protocol — all built and tested. Do not rebuild these.
2. **`findings/proposal_generator.py` (634 lines) already links approval to execution.** `handle_approval_decision()` does the full approve→execute→rollback flow. Wrap it, don't replace it.
3. **`agents/error_recovery.py` (284 lines) already has retry/backoff/circuit breaker.** The rate limiter should delegate to it.
4. **`proactive/events.py` has a thread-safe event bus.** Use it for subagent events, don't create a new bus.
5. **`compression/` package has 5 compressors.** Use it for context watermark, don't invent new compression.
6. **`aiofiles` is already installed.** No dependency management needed for PTY.
7. **Two `StreamEvent` classes exist** (`agents/events.py` and `streaming/emitter.py`). Unify before adding new event types.
8. **State handlers live in `agents/handlers/`**, not just in `state_machine.py`. Edit the handler files for per-state changes.

**Test suite:** 395 passed, 18 skipped (fable track is activating the 18 skipped tests via pytest-asyncio). 413 total.

---

## Parallelization Plan

```
Time →  Day 1        Day 2-3       Day 4-5       Day 6-7       Week 2       Week 3+

Foundation Track:
  A0b → A1 ──→ A2a→A2b→A2c→A3 ──→ C1a→C1b→C1c→C1d → C2a→C2b
  (sonnet)  (opus)  (sonnet)         (opus/sonnet)    (opus/sonnet)

PTY Track:
  ─────── B1a→B1b→B1c→B1d→B1e→B1f ──────────────────────→ E1a→E1b→E1c→E1f
  (opus/max, 5-7 days)                                   (sonnet)

Convergence:
  After both tracks: D1a→D1b→D1c→D1d → F1→F2→F3→F4
  (sonnet)              (sonnet)
```

**Rule:** The foundation track and PTY track touch completely different files. They can run in parallel. Do not let either track modify files the other track owns.

---

## File Ownership Map

| Files | Owner |
|---|---|
| `agents/events.py`, `streaming/emitter.py` | Foundation (A0b unifies, then owns) |
| `agents/states.py`, `agents/blocks.py` (new) | Foundation (A1) |
| `agents/conversation_status.py` (new) | Foundation (A2a) |
| `agents/state_machine.py`, `agents/handlers/*` | Foundation (A2c, C1d) |
| `agents/react_agent.py` | Foundation (A1) |
| `context/assembler.py` | Foundation (A1, F4) |
| `model/outcome_store.py` (new) | Foundation (A3) |
| `model/rate_limiter.py` (new) | Foundation (A2b) |
| `model/tier_router.py`, `model/cascade_router.py` (new) | Foundation (C2) |
| `somatic/` (new package) | Foundation (C1) |
| `streaming/pty.py` (new) | PTY (B1a) |
| `streaming/session_manager.py` (new) | PTY (B1b) |
| `streaming/sandbox.py` (new) | PTY (B1c) |
| `streaming/injection_check.py` (new) | PTY (B1d) |
| `dashboard/routes/terminal.py` | PTY (B1e) |
| `dashboard/routes/websocket.py` | PTY (B1f) |
| `agents/subagent.py` (new) | Convergence (D1a) |
| `agents/subagents/` (new) | Convergence (D1b) |
| Frontend hooks/components | PTY (E1a-c, E1f) — except E1d/E1e which are fable |

---

## Phase A: Foundation

### A0b: Unify StreamEvent classes
**Tier:** sonnet | **Effort:** high | **Lines:** ~30 | **When:** FIRST, before A1 and B1

**Problem:** Two `StreamEvent` classes exist with overlapping factory methods:
- `agents/events.py` (395 lines) — 20+ factory methods, used by state machine
- `streaming/emitter.py` (347 lines) — used by SSE layer

**Task:** Make `streaming/emitter.py` import `StreamEvent` from `agents/events.py` and re-export it. Remove the duplicate class definition from `emitter.py`. Keep any emitter-specific classes (`StreamConfig`, `EventEmitter`) in `emitter.py`.

**Steps:**
1. Read both files. Identify which factory methods exist in `agents/events.py` but not `streaming/emitter.py` and vice versa.
2. Add any missing factory methods to `agents/events.py`.
3. In `streaming/emitter.py`, replace the `StreamEvent` class with `from ..agents.events import StreamEvent`.
4. Run tests: `python3 -m pytest halbert_core/tests/ -q --timeout=30`
5. All 395+ tests must still pass.

**Do not:** Add new event types yet. That happens in A2c, C1d, D1c.

### A1: Conversation as block-typed messages
**Tier:** opus | **Effort:** xhigh | **Lines:** ~200 | **When:** After A0b

**Goal:** Change `StateContext.conversation_history` from `List[Dict[str, Any]]` with string `content` to block-typed messages matching Anthropic's content block format.

**Current state** (`agents/states.py:94`):
```python
conversation_history: List[Dict[str, Any]] = field(default_factory=list)
```
Each entry is `{"role": "user"/"assistant", "content": "string"}`.

**Target state:**
```python
conversation_history: List[Dict[str, Any]] = field(default_factory=list)
```
Each entry is `{"role": "user"/"assistant", "content": [TextBlock, ToolUseBlock, ToolResultBlock, ...]}`.

**Steps:**

1. Create `agents/blocks.py` (new, ~60 lines):
   ```python
   @dataclass
   class TextBlock:
       type: str = "text"
       text: str = ""

   @dataclass
   class ToolUseBlock:
       type: str = "tool_use"
       id: str = ""
       name: str = ""
       input: Dict[str, Any] = field(default_factory=dict)

   @dataclass
   class ToolResultBlock:
       type: str = "tool_result"
       tool_use_id: str = ""
       content: str = ""
       is_error: bool = False
   ```

2. Add helpers to `StateContext` in `agents/states.py` (~30 lines):
   - `add_text_block(role, text)` — appends `{"role": role, "content": [TextBlock(text=text)]}`
   - `add_tool_use_block(tool_id, name, args)` — appends to current assistant message
   - `add_tool_result_block(tool_use_id, result, is_error=False)` — appends a user message with a ToolResultBlock

3. Update `context/assembler.py` (~40 lines):
   - In `_combine_sources()`, when processing the "conversation" source, preserve block structure instead of flattening to a string.
   - Other sources (retrieval, memory, discovery) stay string-based.
   - The assembled context for the LLM should include block-typed conversation + string-typed other sources.

4. Update `agents/react_agent.py` (~40 lines):
   - `_call_llm_with_tools()` already sends block-typed content to Anthropic. Update it to store the blocks in `StateContext.conversation_history` instead of flattening to strings.
   - When receiving tool_use from the LLM, store as `ToolUseBlock`. When executing tools, store results as `ToolResultBlock`.

5. Update `agents/handlers/` files as needed (~30 lines):
   - Any handler that reads `conversation_history` and expects string content needs to handle block arrays.
   - Check `handlers/planning.py`, `handlers/executing.py`, `handlers/responding.py`.

6. Run tests. Fix any failures. The block-typed representation must be backwards-compatible with existing tests — if a test expects string content, update it to expect block arrays.

**Critical:** Do NOT change how the Anthropic provider sends messages. It already expects block-typed content. The change is in how we STORE the conversation, not how we SEND it.

**Pattern to steal:** OCC's `ContextManager.getTokenCount()` — per-block-type token estimation with different overhead for text vs. tool_use vs. tool_result.

### A2a: ConversationStatus enum + state machine
**Tier:** sonnet | **Effort:** high | **Lines:** ~110 | **When:** After A1

**Goal:** Add a `ConversationStatus` enum separate from `AgentState`. This gives the UI user-facing states.

**Steps:**

1. Add to `agents/states.py` (~30 lines):
   ```python
   class ConversationStatus(Enum):
       IN_PROGRESS = "in_progress"
       SUCCESS = "success"
       ERROR = "error"
       TRANSIENT_ERROR = "transient_error"  # API failure, will retry
       CANCELLED = "cancelled"
       BLOCKED = "blocked"  # Waiting for user approval
       WAITING_FOR_EVENTS = "waiting_for_events"  # Waiting for subagent
   ```
   Terminal states: SUCCESS, ERROR, CANCELLED.
   Non-terminal: TRANSIENT_ERROR, BLOCKED, WAITING_FOR_EVENTS.

2. Create `agents/conversation_status.py` (new, ~80 lines):
   ```python
   class ConversationStatusMachine:
       """Tracks user-facing conversation status. Separate from AgentStateMachine."""
       def __init__(self):
           self._status = ConversationStatus.IN_PROGRESS
           self._blocked_action: Optional[Dict] = None
           self._waiting_for: Optional[str] = None  # subagent_id

       def transition(self, new_status, **kwargs): ...
       def current(self) -> ConversationStatus: ...
       def blocked_action(self) -> Optional[Dict]: ...
       def waiting_for(self) -> Optional[str]: ...
   ```

   Transitions:
   - `IN_PROGRESS → TRANSIENT_ERROR` (on API failure)
   - `TRANSIENT_ERROR → IN_PROGRESS` (on retry)
   - `TRANSIENT_ERROR → ERROR` (on max retries)
   - `IN_PROGRESS → BLOCKED` (on approval needed, store blocked_action)
   - `BLOCKED → IN_PROGRESS` (on approval granted)
   - `BLOCKED → CANCELLED` (on rejection)
   - `IN_PROGRESS → WAITING_FOR_EVENTS` (on subagent spawn, store subagent_id)
   - `WAITING_FOR_EVENTS → IN_PROGRESS` (on subagent completion)
   - `IN_PROGRESS → SUCCESS` (on response complete)
   - `IN_PROGRESS → CANCELLED` (on user cancel)
   - `IN_PROGRESS → ERROR` (on unrecoverable error)

### A2b: Rate limiter (HTTP 429/529 only)
**Tier:** sonnet | **Effort:** high | **Lines:** ~60 | **When:** After A0b, parallel with A1

**Goal:** HTTP-level rate limit handling for 429/529 responses. Delegate retry loop to existing `agents/error_recovery.py`.

**Critical:** `agents/error_recovery.py` (284 lines) already has `ErrorRecoveryManager` with `execute_with_retry()`, `classify_error()`, and circuit breaker. Do NOT duplicate this. The rate limiter only handles HTTP-specific concerns:

1. Create `model/rate_limiter.py` (new, ~60 lines):
   ```python
   class RateLimiter:
       """HTTP 429/529 rate limit handler with Retry-After support."""
       def __init__(self, max_retries=5):
           self._max_retries = max_retries
           self._instance_state: Dict[str, RetryState] = {}  # per-model

       def should_retry(self, status_code: int, headers: dict, attempt: int) -> bool: ...
       def get_wait_time(self, status_code: int, headers: dict, attempt: int) -> float: ...
       def reset(self, model_id: str): ...
       def status(self, model_id: str) -> dict: ...
   ```

2. Wire into `model/tier_router.py:generate()` (~20 lines):
   - After a 429/529 response, call `rate_limiter.should_retry()`.
   - If yes, sleep for `rate_limiter.get_wait_time()` and retry.
   - Delegate the retry loop to `ErrorRecoveryManager.execute_with_retry()` — don't write your own retry loop.

**Pattern to steal:** OCC's `RateLimiter` — exponential backoff with jitter, `Retry-After` header respect, per-instance state tracking.

### A2c: Wire ConversationStatus into state machine + SSE
**Tier:** sonnet | **Effort:** high | **Lines:** ~60 | **When:** After A2a

**Steps:**

1. Add `ConversationStatusMachine` to `StateContext` in `agents/states.py`:
   ```python
   conversation_status: ConversationStatusMachine = field(default_factory=ConversationStatusMachine)
   ```

2. In `agents/state_machine.py`, update transitions to also update conversation status:
   - `ERROR` state → check if transient (via `error_recovery.classify_error()`) → `TRANSIENT_ERROR` or `ERROR`
   - `AWAITING_CONFIRMATION` → `conversation_status.transition(BLOCKED, blocked_action=...)`
   - `confirm_action()` → `conversation_status.transition(IN_PROGRESS)`
   - Response complete → `conversation_status.transition(SUCCESS)`

3. Add `StreamEvent.conversation_status()` factory method to `agents/events.py` (~20 lines):
   ```python
   @classmethod
   def conversation_status(cls, session_id, status, blocked_action=None, waiting_for=None):
       return cls(type="conversation_status", session_id=session_id,
                  data={"status": status.value, "blocked_action": blocked_action, "waiting_for": waiting_for})
   ```

4. Emit the event on every conversation status transition in the state machine.

### A3: Outcome store
**Tier:** sonnet | **Effort:** high | **Lines:** ~130 | **When:** After A1, parallel with A2

**Steps:**

1. Create `model/outcome_store.py` (new, ~80 lines):
   ```python
   class OutcomeStore:
       """Records model call outcomes for self-tuning router."""
       def __init__(self, db_path=None):
           # SQLite table: model_outcomes (id, model, success, latency_ms,
           #   input_tokens, output_tokens, cost_usd, complexity, task, ts)

       def record(self, model, success, latency_ms, input_tokens, output_tokens,
                  cost_usd, complexity, task): ...
       def stats_for(self, model) -> dict:
           """Returns {attempts, successes, success_rate, avg_latency, avg_cost}"""
       def summary(self) -> List[dict]: ...
   ```

2. Wire into `model/tier_router.py:generate()` (~30 lines):
   - After `generate()` returns, record the outcome.
   - Success = CRAG evaluator says CORRECT (or no CRAG available → success = no exception).
   - Latency = wall-clock time of the call.
   - Tokens = from response usage metadata.
   - Cost = tokens × published price (lookup table or model config).

3. Wire into `agents/react_agent.py` (~20 lines):
   - After each LLM call, if CRAG evaluation is available, record the outcome.

**Pattern to steal:** OCC's `OutcomeStore` — JSONL append-only, tolerant of corrupt lines, best-effort recording that never throws. Use SQLite instead of JSONL for queryability.

---

## Phase B: PTY Backend

### B1a: PTYSession
**Tier:** opus | **Effort:** max | **Lines:** ~200 | **When:** After A0b, parallel with A1+

**This is the hardest single component in the entire plan.**

**Goal:** Real async PTY using `os.openpty()` + `aiofiles`. Manages master/slave file descriptors, reads stdout in chunks, writes stdin, handles resize.

**Steps:**

1. Create `streaming/pty.py` (new, ~200 lines):

   ```python
   import os
   import fcntl
   import termios
   import struct
   import signal
   import asyncio
   import aiofiles
   from typing import AsyncIterator, Optional

   class PTYSession:
       """Async PTY session using os.openpty() + aiofiles."""

       def __init__(self, command: str, cwd: str = None, env: dict = None,
                    cols: int = 80, rows: int = 24):
           self._command = command
           self._cwd = cwd
           self._env = env
           self._cols = cols
           self._rows = rows
           self._master_fd: Optional[int] = None
           self._slave_fd: Optional[int] = None
           self._pid: Optional[int] = None
           self._ring_buffer = bytearray(1024 * 1024)  # 1MB
           self._ring_write_pos = 0
           self._exited = False
           self._exit_code: Optional[int] = None

       async def spawn(self) -> int:
           """Open PTY, fork child process. Returns session ID (PID)."""
           self._master_fd, self._slave_fd = os.openpty()
           # Set window size
           self._set_winsize(self._cols, self._rows)
           # Fork
           pid = os.fork()
           if pid == 0:
               # Child
               os.setsid()
               os.dup2(self._slave_fd, 0)
               os.dup2(self._slave_fd, 1)
               os.dup2(self._slave_fd, 2)
               os.close(self._master_fd)
               os.close(self._slave_fd)
               # Execute
               os.execvpe("/bin/sh", ["/bin/sh", "-c", self._command],
                          dict(os.environ, **(self._env or {})))
           else:
               # Parent
               os.close(self._slave_fd)
               self._slave_fd = None
               self._pid = pid
               return pid

       async def read_chunk(self) -> AsyncIterator[bytes]:
           """Async generator yielding stdout chunks."""
           async with aiofiles.open(self._master_fd, mode='rb', closefd=False) as f:
               while not self._exited:
                   try:
                       chunk = await f.read(4096)
                       if not chunk:
                           break
                       self._append_ring(chunk)
                       yield chunk
                   except OSError:
                       break
               # Reap child
               if self._pid:
                   _, status = os.waitpid(self._pid, os.WNOHANG)
                   self._exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
                   self._exited = True

       async def write_stdin(self, data: str):
           """Write to the child's stdin."""
           os.write(self._master_fd, data.encode())

       def resize(self, cols: int, rows: int):
           """Send SIGWINCH with new window size."""
           self._cols = cols
           self._rows = rows
           self._set_winsize(cols, rows)

       def _set_winsize(self, cols, rows):
           winsize = struct.pack("HHHH", rows, cols, 0, 0)
           fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

       def _append_ring(self, data: bytes):
           """Append to ring buffer, wrapping if needed."""
           remaining = len(self._ring_buffer) - self._ring_write_pos
           if len(data) <= remaining:
               self._ring_buffer[self._ring_write_pos:self._ring_write_pos + len(data)] = data
               self._ring_write_pos += len(data)
           else:
               self._ring_buffer[self._ring_write_pos:] = data[:remaining]
               self._ring_buffer[:len(data) - remaining] = data[remaining:]
               self._ring_write_pos = len(data) - remaining

       def get_buffer(self) -> bytes:
           """Get the full ring buffer contents."""
           return bytes(self._ring_buffer[:self._ring_write_pos])

       def is_alive(self) -> bool:
           return not self._exited

       def kill(self):
           if self._pid and not self._exited:
               os.kill(self._pid, signal.SIGTERM)
               try:
                   os.waitpid(self._pid, 0)
               except OSError:
                   pass
               self._exited = True
           if self._master_fd:
               os.close(self._master_fd)
               self._master_fd = None
   ```

**Critical notes:**
- `os.fork()` is Unix-only. This is fine for v1 (macOS + Linux). Windows is post-v1.
- The ring buffer is a `bytearray` with manual write position. When it wraps, old data is overwritten. This is intentional — 1MB of scrollback is enough.
- `aiofiles.open(self._master_fd, ...)` wraps the fd for async reads. This is the key trick — `aiofiles` can wrap an existing fd.
- Do NOT use `subprocess` anywhere. This is a raw PTY.
- Test with a simple command first: `PTYSession("echo hello")` should yield `b"hello\n"`.

### B1b: TerminalSessionManager
**Tier:** sonnet | **Effort:** xhigh | **Lines:** ~120 | **When:** After B1a

**Steps:**

1. Create `streaming/session_manager.py` (new, ~120 lines):

   ```python
   class TerminalSessionManager:
       """Singleton managing all active PTY sessions."""
       def __init__(self, max_sessions=2, idle_ttl_seconds=60):
           self._sessions: Dict[str, PTYSession] = {}
           self._max_sessions = max_sessions
           self._idle_ttl = idle_ttl_seconds
           self._reaper_task: Optional[asyncio.Task] = None

       async def spawn(self, command, cwd=None, env=None, cols=80, rows=24) -> str:
           session_id = str(uuid.uuid4())
           if len(self._sessions) >= self._max_sessions:
               raise AtCapacityError(f"Max {self._max_sessions} sessions")
           session = PTYSession(command, cwd, env, cols, rows)
           await session.spawn()
           self._sessions[session_id] = session
           return session_id

       def get(self, session_id) -> Optional[PTYSession]: ...
       def list_active(self) -> List[dict]: ...
       def kill(self, session_id): ...
       def start_reaper(self): ...  # Background task that kills idle sessions
       def stop_reaper(self): ...
   ```

   - `AtCapacityError` is a non-blocking signal — callers should queue, not crash.
   - The reaper runs every 10 seconds, checks `session.is_alive()` and last-activity time.

### B1c: Sandbox integration
**Tier:** opus | **Effort:** xhigh | **Lines:** ~100 | **When:** After B1a, parallel with B1b

**Steps:**

1. Create `streaming/sandbox.py` (new, ~100 lines):

   ```python
   import platform
   import re
   import shlex

   class Sandbox:
       """Platform-specific command sandboxing."""
       def wrap_command(self, command: str, writable_paths: List[str] = None) -> str:
           """Wrap a command with sandbox execution."""
           if platform.system() == "Linux":
               return self._wrap_bwrap(command, writable_paths or [])
           elif platform.system() == "Darwin":
               return self._wrap_seatbelt(command, writable_paths or [])
           else:
               return command  # No sandbox on unsupported platforms

       def _wrap_bwrap(self, command, writable) -> str: ...
       def _wrap_seatbelt(self, command, writable) -> str: ...

       def validate_path(self, path: str) -> bool:
           """Validate a path is safe for sandbox binding."""
           # Must be absolute, no metacharacters, no null bytes
           if not path.startswith('/'): return False
           if '\x00' in path: return False
           if '..' in path: return False
           return True
   ```

   - Linux: `bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --bind {writable} {writable} -- {command}`
   - macOS: `sandbox-exec -p '(allow process-exec) (allow file-read*) (deny file-read* (subpath "/etc/ssh")) (allow file-write* (subpath "{writable}"))' -- {command}`
   - Start with permissive profiles. Tighten based on testing.

**Pattern to steal:** OCC's `sandbox.mjs` — path validation regex. OCC's `Sandbox.wrapCommand()` — but treat it as a reference, not a copy. OCC wraps the command string; we wrap the PTY spawn command.

### B1d: Injection check
**Tier:** sonnet | **Effort:** high | **Lines:** ~80 | **When:** After B1a, parallel with B1b/B1c

**Steps:**

1. Create `streaming/injection_check.py` (new, ~80 lines):

   16+ dangerous patterns:
   - `rm -rf /`, `rm -rf /*`
   - `:(){:|:&};:` (fork bomb)
   - `mkfs.`, `dd if=`
   - `> /dev/sd`, `> /dev/nvme`
   - `chmod -R 777 /`
   - `curl ... | bash`, `wget ... | sh`
   - `eval `, `exec `
   - Backticks, `$(` in unquoted contexts
   - `zpool destroy`, `lvremove`, `ip link delete`
   - `sudo su -`, `sudo -i`

   Also: `uses_elevation(command)` → detect `sudo`, `su`, `doas`.

   This is a **superset** of the existing `dashboard/routes/terminal.py` safety checks. The existing checks stay; this adds more.

### B1e: Rewrite terminal route
**Tier:** sonnet | **Effort:** xhigh | **Lines:** ~120 (rewrite) | **When:** After B1a-d

**Steps:**

1. Rewrite `dashboard/routes/terminal.py`:
   - Replace `asyncio.create_subprocess_shell()` with `TerminalSessionManager.spawn()`
   - Add endpoints: `GET /sessions` (list), `POST /{id}/input` (write stdin), `POST /{id}/resize` (SIGWINCH), `GET /{id}/stream` (SSE output)
   - Keep existing safety tier checks (`check_command_safety()`)
   - Add sandbox wrapping via `Sandbox.wrap_command()`
   - Add injection check via `injection_check.py`
   - **Remove sudo stripping.** Instead, let the PTY handle password prompts. The frontend will see `Password:` in the output and show an input field.

2. Keep the existing `check_command_safety()` function and `SafetyTier` enum — they're used by the frontend.

### B1f: WebSocket bridge
**Tier:** sonnet | **Effort:** high | **Lines:** ~80 | **When:** After B1e

**Steps:**

1. Rewrite `dashboard/routes/websocket.py` (currently 37 lines):
   - Upgrade to bidirectional WebSocket for PTY sessions
   - Message protocol: `{"type": "stdin", "data": "..."}`, `{"type": "resize", "cols": 80, "rows": 24}`, `{"type": "stdout", "data": "..."}`, `{"type": "exit", "code": 0}`
   - On connect, create or attach to a PTY session
   - Forward stdin to `session.write_stdin()`
   - Forward stdout from `session.read_chunk()` to WebSocket
   - Handle resize via `session.resize()`

---

## Phase C: Somatic Blocks and Integration

### C1a: SomaticBlock dataclass + SomaticStore
**Tier:** sonnet | **Effort:** high | **Lines:** ~150 | **When:** After A2c + A3

**Steps:**

1. Create `somatic/__init__.py`, `somatic/block.py`, `somatic/store.py`:

   `somatic/block.py` (~80 lines):
   ```python
   class BlockType(Enum):
       SENSORY = "sensory"
       DELIBERATION = "deliberation"
       PROPOSAL = "proposal"
       ACTION = "action"
       REFLECTION = "reflection"

   class BlockStatus(Enum):
       DETECTED = "detected"
       DELIBERATING = "deliberating"
       PROPOSED = "proposed"
       PENDING_APPROVAL = "pending_approval"
       APPROVED = "approved"
       EXECUTING = "executing"
       COMPLETED = "completed"
       ROLLED_BACK = "rolled_back"
       REJECTED = "rejected"

   @dataclass
   class SomaticBlock:
       id: str
       block_type: BlockType
       status: BlockStatus
       session_id: str
       finding_id: Optional[str] = None
       proposal_id: Optional[str] = None
       approval_request_id: Optional[str] = None
       action_id: Optional[str] = None
       reflection_id: Optional[str] = None
       created_at: float = field(default_factory=time.time)
       updated_at: float = field(default_factory=time.time)
       metadata: Dict[str, Any] = field(default_factory=dict)
   ```

   `somatic/store.py` (~70 lines):
   - SQLite table `somatic_blocks`
   - CRUD: `create()`, `get()`, `update_status()`, `list_for_session()`, `list_by_type()`

2. **Do NOT absorb existing models.** `SomaticBlock` references `finding_id`, `proposal_id`, etc. as foreign keys. The existing `Finding`, `Proposal`, `ApprovalRequest` stay in their modules.

### C1b: SomaticLifecycle state machine
**Tier:** opus | **Effort:** xhigh | **Lines:** ~120 | **When:** After C1a

**Steps:**

1. Create `somatic/lifecycle.py` (new, ~120 lines):

   ```python
   class SomaticLifecycle:
       """Drives a SomaticBlock through its 5 phases.
       Calls existing modules — does NOT replace them."""

       def __init__(self, store, finding_store, proposal_generator,
                    approval_engine, recovery_executor, guardrail_enforcer):
           # Inject all existing modules

       async def advance_to_sensory(self, block, detector_output): ...
       async def advance_to_deliberation(self, block, cognitive_tick_output): ...
       async def advance_to_proposal(self, block):
           # Calls proposal_generator.generate() which creates Finding + Proposal + ApprovalRequest
           # Updates block with finding_id, proposal_id, approval_request_id
       async def advance_to_action(self, block, approved: bool):
           # If approved: calls proposal_generator.handle_approval_decision(approved=True)
           # If rejected: calls proposal_generator.handle_approval_decision(approved=False)
       async def advance_to_reflection(self, block, tick_output):
           # Stores reflection data, marks block COMPLETED
   ```

**Critical:** `SomaticLifecycle` wraps `findings/proposal_generator.py` (634 lines). It does NOT replace it. The `ProposalGenerator.generate()` method already creates Finding + Proposal + ApprovalRequest. The `handle_approval_decision()` method already executes or rolls back. `SomaticLifecycle` just calls these and updates the block status.

### C1c: Per-file checkpoints
**Tier:** sonnet | **Effort:** high | **Lines:** ~80 | **When:** After C1a, parallel with C1b

**Steps:**

1. Create `somatic/checkpoints.py` (new, ~80 lines):

   ```python
   class CheckpointManager:
       """Per-file checkpoint stack for undo before actions."""
       def __init__(self, max_checkpoints=50):
           self._stacks: Dict[str, List[bytes]] = {}  # path → [original, original, ...]
           self._max = max_checkpoints

       def checkpoint(self, path: str):
           """Save current file content before modifying it."""
           with open(path, 'rb') as f:
               content = f.read()
           self._stacks.setdefault(path, []).append(content)
           if len(self._stacks[path]) > self._max:
               self._stacks[path] = self._stacks[path][-self._max:]

       def rollback(self, path: str) -> Optional[bytes]:
           """Pop and restore the most recent checkpoint."""
           if path not in self._stacks or not self._stacks[path]:
               return None
           content = self._stacks[path].pop()
           with open(path, 'wb') as f:
               f.write(content)
           return content
   ```

   Wire into `SomaticLifecycle.advance_to_action()` — before executing, checkpoint all affected files.

**Pattern to steal:** OCC's `CheckpointManager` — per-file stack with FIFO trim.

### C1d: Wire into state machine + SSE + ProactiveEventBus
**Tier:** sonnet | **Effort:** xhigh | **Lines:** ~80 | **When:** After C1b + C1c

**Steps:**

1. In `agents/state_machine.py` and `agents/handlers/`:
   - REFLECTING state → `SomaticLifecycle.advance_to_reflection()`
   - EXECUTING state → `SomaticLifecycle.advance_to_action()`
   - Proposals → `SomaticLifecycle.advance_to_proposal()`
   - When approval needed → set `ConversationStatus::BLOCKED` (from A2)

2. Add `StreamEvent.somatic_block()` to `agents/events.py` (~20 lines):
   ```python
   @classmethod
   def somatic_block(cls, session_id, block_type, block_id, status, **kwargs):
       return cls(type="somatic_block", session_id=session_id,
                  data={"block_type": block_type, "block_id": block_id,
                        "status": status, **kwargs})
   ```

3. Also publish via `proactive/events.py:ProactiveEventBus` for the proactive channel:
   ```python
   event = ProactiveEvent.create(
       type="somatic_block", severity="info",
       title=f"Block {block_type}: {status}",
       body=..., finding_id=block.finding_id, proposal_id=block.proposal_id)
   await get_event_bus().publish(event)
   ```

### C2a: MetaHarnessRouter
**Tier:** opus | **Effort:** xhigh | **Lines:** ~120 | **When:** After A3 + C1a

**Steps:**

1. Create `model/cascade_router.py` (new, ~120 lines):

   ```python
   class MetaHarnessRouter:
       """Cost-cascade model router with outcome-based self-tuning."""
       def __init__(self, tier_router, outcome_store, min_samples=3,
                    evidence_weight_cap=0.9, quality_bar=0.7):
           self._tier_router = tier_router
           self._outcomes = outcome_store
           self._min_samples = min_samples
           self._cap = evidence_weight_cap
           self._quality_bar = quality_bar
           self._enabled = False  # Opt-in, default OFF

       def estimate_complexity(self, text: str) -> float:
           """Bag-of-words heuristic. 0 = trivial, 1 = hard."""
           # Steal OCC's estimateComplexity() logic

       def predict(self, model_id: str, complexity: float) -> float:
           """Blend tier-based prior with recorded stats."""
           stats = self._outcomes.stats_for(model_id)
           if stats["attempts"] < self._min_samples:
               return self._prior(model_id, complexity)
           # Blending: w = clamp(attempts / (attempts + min_samples), 0, cap)
           w = min(stats["attempts"] / (stats["attempts"] + self._min_samples), self._cap)
           prior = self._prior(model_id, complexity)
           evidence = stats["success_rate"]
           return (1 - w) * prior + w * evidence

       def route(self, task_text: str) -> ModelSelection:
           """Iterate ladder cheapest-first, return first model that clears bar."""
           complexity = self.estimate_complexity(task_text)
           for model in self._ladder():
               if self.predict(model.model_id, complexity) >= self._quality_bar:
                   return model
           return self._ladder()[-1]  # Fallback to most capable

       def escalate(self, failed_model_id: str) -> ModelSelection:
           """Step up one tier after a failure."""
           ...

       def is_enabled(self) -> bool:
           return self._enabled
   ```

**Pattern to steal:** OCC's `MetaHarnessRouter` — the entire pattern is directly portable. The blending formula prevents overfitting. The opt-in default (byte-identical when disabled) is critical.

### C2b: Merge complexity systems + wire into tier router
**Tier:** sonnet | **Effort:** high | **Lines:** ~90 | **When:** After C2a

**Steps:**

1. Remove `_score_complexity()` from `model/tier_router.py` (lines 464-502). Replace with `cascade_router.estimate_complexity()`.

2. Keep `intake/complexity.py` as a fallback for uncertain cases (heuristic score near tier boundary). The LLM-based assessment is secondary; the bag-of-words heuristic is primary.

3. Update `tier_router.py:route_request()` to delegate to `MetaHarnessRouter.route()` when enabled, or use the old heuristic path when disabled.

4. After `generate()`, record outcome via `OutcomeStore.record()`.

---

## Phase D: Subagents

### D1a: SubagentHandle + SubagentManager
**Tier:** sonnet | **Effort:** xhigh | **Lines:** ~170 | **When:** After B1 + C1

**Steps:**

1. Create `agents/subagent.py` (new, ~170 lines):

   ```python
   @dataclass
   class SubagentHandle:
       id: str
       agent_type: str
       task_goal: str
       scoped_sources: List[str]
       model_tier: str
       pty_session_id: Optional[str]
       status: str  # queued, running, completed, failed, cancelled
       started_at: float
       completed_at: Optional[float]
       result_block_id: Optional[str]
       agent_config_snapshot: Dict  # frozen config for reproducibility
       parent_task_id: Optional[str]
       children: List[str]

   class SubagentManager:
       def __init__(self, pty_manager, somatic_store, max_concurrent=2):
           self._pty = pty_manager
           self._somatic = somatic_store
           self._max = max_concurrent
           self._active: Dict[str, SubagentHandle] = {}
           self._queue: List[SubagentHandle] = []  # FIFO, SQLite-backed

       async def spawn(self, agent_type, task_goal, scoped_sources) -> SubagentHandle: ...
       def cancel(self, handle_id: str): ...
       def list_active(self) -> List[SubagentHandle]: ...
       def list_queued(self) -> List[SubagentHandle]: ...
   ```

   - Use `asyncio.Semaphore(max_concurrent)` for the concurrency ceiling.
   - When at capacity, queue the handle and emit `AtCapacity` event (non-blocking).
   - `agent_config_snapshot` freezes the current config into the handle for reproducibility.

**Pattern to steal:** Warp's `AmbientAgentEvent` — lifecycle events, not function calls. Warp's `agent_config_snapshot`. OCC's `AgentTeams` — `register()`, `send_message()`, `broadcast()`.

### D1b: StorageAuditorAgent
**Tier:** sonnet | **Effort:** high | **Lines:** ~100 | **When:** After D1a

**Steps:**

1. Create `agents/subagents/__init__.py` and `agents/subagents/storage_auditor.py` (new, ~100 lines):

   ```python
   class StorageAuditorAgent:
       """Deterministic script: runs smartctl/zpool/lsblk, parses output, emits block."""
       async def run(self, pty_manager) -> SomaticBlock:
           # 1. Spawn PTY session: smartctl -a /dev/sda
           # 2. Read output
           # 3. Parse with regex for anomalies (reallocations, pending sectors, etc.)
           # 4. If anomalies: create Finding via FindingStore
           #    → create Proposal via ProposalGenerator
           #    → create SomaticBlock (type=SENSORY, finding_id=...)
           # 5. Return block
   ```

   - NO LLM call. Pure command execution + regex parsing.
   - Commands: `smartctl -a /dev/sda`, `zpool status`, `lsblk -o NAME,SIZE,TYPE,MOUNTPOINT`
   - Parse for: reallocated sectors, pending sectors, offline uncorrectable, SMART health status, zpool errors.

### D1c: Lifecycle event stream
**Tier:** sonnet | **Effort:** high | **Lines:** ~60 | **When:** After D1a

**Steps:**

1. Add subagent event types to `agents/events.py` (~30 lines):
   ```python
   @classmethod
   def subagent_event(cls, session_id, event_type, handle_id, **kwargs):
       # event_type: spawned, state_changed, session_started, timed_out, at_capacity, completed
       return cls(type="subagent_event", session_id=session_id,
                  data={"subagent_event": event_type, "handle_id": handle_id, **kwargs})
   ```

2. Also publish via `ProactiveEventBus` (~30 lines):
   ```python
   event = ProactiveEvent.create(
       type="subagent_event", severity="info",
       title=f"Subagent {event_type}: {handle.agent_type}",
       body=...)
   await get_event_bus().publish(event)
   ```

### D1d: Wire into state machine + ConversationStatus::WaitingForEvents
**Tier:** sonnet | **Effort:** xhigh | **Lines:** ~60 | **When:** After D1b + D1c

**Steps:**

1. In `agents/state_machine.py`:
   - PLANNING state can emit `spawn_subagent` tool call
   - On spawn: `conversation_status.transition(WAITING_FOR_EVENTS, waiting_for=handle_id)`
   - On completion: `conversation_status.transition(IN_PROGRESS)`
   - Subagent completion emits Somatic Block via SSE

---

## Phase E: Frontend

### E1a: useTerminalSessions hook
**Tier:** sonnet | **Effort:** xhigh | **Lines:** ~120 | **When:** After B1f

Create `dashboard/frontend/src/hooks/useTerminalSessions.ts`. Singleton store with WebSocket per session. Tracks session state (running/done/idle), output buffer, scrollback. Max 3 visible xterm.js instances; rest headless.

### E1b: TerminalTile component
**Tier:** sonnet | **Effort:** xhigh | **Lines:** ~150 | **When:** After E1a

Create `dashboard/frontend/src/components/agent/TerminalTile.tsx`. Inline xterm.js in conversation stream. Status badge, timer, PID, quick actions (Pin, Terminate, Copy).

### E1c: TerminalAccordionDock component
**Tier:** sonnet | **Effort:** high | **Lines:** ~200 | **When:** After E1a

Create `dashboard/frontend/src/components/agent/TerminalAccordionDock.tsx`. Right-column accordion. Lists all sessions. Expand/collapse. Jump-to-origin. Full PTY interactivity on expand. Coexists with ContextBar (sits below it).

### E1f: Integrate into SidePanel + SSE event handling
**Tier:** sonnet | **Effort:** high | **Lines:** ~140 | **When:** After E1b + E1c + E1d (fable) + E1e (fable)

1. Modify `dashboard/frontend/src/components/SidePanel.tsx` — add right-column dock below ContextBar. Render `TerminalTile` in conversation stream.
2. Modify `dashboard/frontend/src/hooks/useAgentStream.ts` — handle `somatic_block`, `subagent_event`, `conversation_status`, `terminal_spawn`, `terminal_output`, `terminal_complete` events.

---

## Phase F: Advanced Features

### F1: SQLite session store + FTS5
**Tier:** sonnet | **Effort:** high | **Lines:** ~160 | **When:** After C1 + D1

Migrate `ConversationStore` from JSON to SQLite + FTS5. Create `session_somatic_blocks` table. One-time migration script.

### F2: Session affinity router
**Tier:** sonnet | **Effort:** high | **Lines:** ~140 | **When:** After F1

3-tier routing: explicit reference regex → FTS5 search → current session. Reuse `intake/signals.py` for entity extraction.

### F3: Living Reflexes
**Tier:** sonnet | **Effort:** xhigh | **Lines:** ~200 | **When:** After C1 + F1

`Reflex` dataclass + YAML store + `ReflexMatcher` (regex + threshold). Wire into existing `proactive/detector_runner.py`. Use existing morning report scheduler for cron.

### F4: Context watermark
**Tier:** opus | **Effort:** xhigh | **Lines:** ~60 | **When:** After A1 + F1

80% token watermark trigger. 2-hour temporal gate. Topic boundary gate. Micro-compaction (truncate tool results >200 chars). Use existing `compression/` package for full-compaction.

---

## Rules

1. **Run tests after every task:** `python3 -m pytest halbert_core/tests/ -q --timeout=30`
2. **Do not touch fable track files:** `hooks/useIntersectionDock.ts`, `components/agent/TetherChip.tsx`
3. **Do not rewrite existing modules** — see "Do Not Rewrite" list in STRATEGY-V2-SCRUTINY.md §7
4. **Commit after each task** with a clear message. No Co-Authored-By trailers.
5. **If you hit a blocker, stop and report.** Do not work around it.
6. **The PTY track (B1) and foundation track (A1+) can run in parallel** — they touch different files. Don't let either track modify the other's files.
