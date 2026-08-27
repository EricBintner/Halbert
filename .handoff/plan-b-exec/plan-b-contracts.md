# Plan B shared contracts (binding for every planner)

> **Status: DRAFT** — 2026-08-27. Not yet independently verified. Contracts are complete but have not been dry-run against the codebase (Plan A's contracts were verified by an independent verifier pass). A verifier pass must be run before execution. Plan A must be complete before these contracts are finalised.

Worktree (read and cite code from HERE, not from /Volumes/4TB-BAD/Halbert):
`/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation`
Backend package: `halbert_core/halbert_core/` (BE). Frontend: `halbert_core/halbert_core/dashboard/frontend/src/` (FE).
Spec: `documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md` (read §9.1–9.9, §11, §13).
Plan A contracts (already implemented or in flight): `.handoff/plan-a-exec/plan-a-contracts.md`.
Backend tests run as: `cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/<file> -q -p no:cacheprovider`
Frontend tests: `cd <worktree>/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/<path>` ; typecheck `npx tsc --noEmit -p .`
Baseline after Plan A: backend suite green except the 4 pre-existing failures (`test_tool_calling_bridge.py`, `test_phase_d_integration.py`); frontend suite green; `tsc` clean; literal-colour ratchet unchanged.
Commits: pathspec adds only (`git add <files>`), message subject only + body, NO Co-Authored-By / bot trailers (project rule). Branch: `feat/continuous-conversation` (continue on the same branch as Plan A).

## 0. Plan A surface Plan B builds on (do not re-implement)

These are established by Plan A contracts and must be treated as stable inputs:

- `SqliteConversationStore` (`agents/conversation_sqlite.py`): `SCHEMA_VERSION = 2`; WAL + busy_timeout; `_ensure_schema` with idempotent `ALTER TABLE`; `append_message(..., terminal_block_ids: list[str] | None)`; `update_message(...)`; `get_thread`, `list_threads`, `current_open_thread`, `list_turns`, `recent_messages`, `search_receipts`, `upsert_receipt`.
- `messages.terminal_block_ids TEXT NOT NULL DEFAULT '[]'` — Plan A stores **terminal session ids** here; Plan B task B21 migrates the column to **block ids** and back-fills from `terminal_blocks`.
- `StateContext.terminal_session_ids: List[str]` — appended in `_run_tool_streaming` when a `terminal_spawn` event passes; consumed by `ThreadManager.end_turn(...)`.
- `ThreadManager.end_turn(turn, *, assistant_text, blocks, terminal_session_ids, diff_proposals, status)` — persists the assistant row with `terminal_block_ids`.
- `StreamEvent` factories: `terminal_spawn(session_id, terminal_session_id, command, pid, sandboxed, cwd, attach)`, `terminal_output(session_id, terminal_session_id, data)`, `terminal_complete(session_id, terminal_session_id, exit_code)`.
- `TerminalEventBus` (`streaming/terminal_bridge.py`): `publish_terminal_event(payload)`, `current_agent_session` ContextVar, `terminal_stream_wanted()`.
- `TerminalSessionManager` (`streaming/session_manager.py`): `spawn(command, cwd, env, cols, rows) -> session_id`, `get(session_id) -> PTYSession | None`, `touch`, `list_active`, `kill`, `start_reaper`, `stop_reaper`, `shutdown`, `count`.
- `PTYSession` (`streaming/pty.py`): `spawn() -> pid`, `read_chunk() -> AsyncIterator[bytes]`, `write_stdin(data)`, `resize(cols, rows)`, `kill()`, `is_alive()`, `get_buffer() -> bytes`, `exit_code`, `pid`, `last_output_at`, `_read_queues: set`, `_buffer: bytearray`, `_buffer_bytes: int`.
- Frontend: `useTerminalSessions` store (`hooks/useTerminalSessions.ts`): `TerminalSession` interface, `spawn`, `attach`, `adopt`, `sendInput`, `resize`, `kill`, `setVisible`, `appendOutput`; `MAX_VISIBLE = 3`.
- Frontend: `TerminalTile` (`components/agent/TerminalTile.tsx`), `TerminalAccordionDock` (`components/agent/TerminalAccordionDock.tsx`), `ToolExecutionCard` (`components/agent/ToolExecutionCard.tsx`), `InlineTerminals` (`components/agent/InlineTerminals.tsx`).
- Tokens: `--color-status-nominal`, `--color-status-nominal-bg`, `--color-status-nominal-line`, `--color-status-warning` (+ `-bg`, `-line`), `--color-status-critical` (+ `-bg`, `-line`), `--color-accent-strong`, `--duration-shutter: 220ms`, `--ease-shutter: cubic-bezier(0.2,0,0,1)`. All defined in `shared-tokens/tokens.css` and mapped in `tailwind.config.js` under `colors.status.*`.

## 1. Storage — terminal_blocks and terminal_sessions tables (BE/agents/conversation_sqlite.py — extend in place)

`SCHEMA_VERSION` bumps to 3. `_ensure_schema` adds the two tables when `version < 3` and back-fills nothing (Plan A stored session ids; B21 handles the migration).

### terminal_blocks

```sql
CREATE TABLE IF NOT EXISTS terminal_blocks (
    block_id      TEXT PRIMARY KEY,        -- uuid
    session_id    TEXT NOT NULL,           -- FK -> terminal_sessions.session_id (logical, not enforced)
    thread_id     TEXT,                    -- the open thread at close time (nullable for user shells with no thread)
    turn_id       TEXT,                    -- the per-turn session_id from StateContext
    command       TEXT NOT NULL,           -- the command text (base64-decoded from OSC 133 C marker, or the raw cmd for pool blocks)
    cwd           TEXT,
    owner         TEXT NOT NULL DEFAULT 'agent',  -- 'user' | 'agent'
    interactive   INTEGER NOT NULL DEFAULT 0,     -- alt-screen or needs_input
    remote        INTEGER NOT NULL DEFAULT 0,     -- ssh/mosh block; inner commands not parsed
    redacted      INTEGER NOT NULL DEFAULT 0,
    started_at    REAL NOT NULL,
    ended_at      REAL,
    exit_code     INTEGER,                 -- null while running
    output_head   TEXT NOT NULL DEFAULT '', -- <= 20 lines, utf-8, redacted
    output_tail   TEXT NOT NULL DEFAULT ''  -- <= 4 KiB, utf-8, redacted
);
CREATE INDEX IF NOT EXISTS idx_tb_session ON terminal_blocks(session_id);
CREATE INDEX IF NOT EXISTS idx_tb_thread  ON terminal_blocks(thread_id);
CREATE INDEX IF NOT EXISTS idx_tb_turn    ON terminal_blocks(turn_id);
```

### terminal_sessions

```sql
CREATE TABLE IF NOT EXISTS terminal_sessions (
    session_id    TEXT PRIMARY KEY,        -- matches PTYSession pid-derived id or uuid
    kind          TEXT NOT NULL DEFAULT 'oneshot',  -- 'user' | 'agent-pool' | 'oneshot'
    owner         TEXT NOT NULL DEFAULT 'agent',    -- 'user' | 'agent'
    watched       INTEGER NOT NULL DEFAULT 1,       -- 0 = unwatched (user toggle)
    spawned_at    REAL NOT NULL,
    ended_at      REAL,
    last_state    TEXT NOT NULL DEFAULT 'running'   -- 'running' | 'exited' | 'killed' | 'lost' | 'unknown'
);
```

### New/changed store methods (exact signatures)

```python
def insert_terminal_block(self, block: dict) -> bool
    # block has all terminal_blocks columns; INSERT OR REPLACE; single transaction; WARNING on failure; False on failure

def update_terminal_block(self, block_id: str, **fields) -> bool
    # allowed: ended_at, exit_code, output_head, output_tail, interactive, remote, redacted, last_state (no-op if session ended)

def get_terminal_block(self, block_id: str) -> dict | None

def list_terminal_blocks(self, *, session_id: str | None = None, thread_id: str | None = None, turn_id: str | None = None, limit: int = 50) -> list[dict]
    # newest-first; each row as dict

def insert_terminal_session(self, session: dict) -> bool
    # INSERT OR REPLACE

def update_terminal_session(self, session_id: str, **fields) -> bool
    # allowed: ended_at, last_state, watched

def get_terminal_session(self, session_id: str) -> dict | None

def list_terminal_sessions(self, *, kind: str | None = None, limit: int = 50) -> list[dict]
```

### Migration (B21): terminal_block_ids session→block

```python
def migrate_terminal_block_ids_to_blocks(self) -> int
    # For every message with non-empty terminal_block_ids:
    #   for each session_id in the list, find terminal_blocks rows with that session_id
    #   collect their block_ids, replace the session_id with the block_ids
    # Return the number of messages updated. Idempotent (a session_id that
    # has no terminal_blocks rows is left as-is — it was a one-shot that
    # never persisted a block). Runs once at boot after schema migration.
```

## 2. Redaction (new BE/streaming/redact.py)

```python
PATTERNS: list[tuple[re.Pattern, str]]  # (compiled regex, replacement)
# Matches (case-insensitive where applicable):
#   password=<value>           -> password=[redacted]
#   -p<token>                  -> -p[redacted]        (when preceded by a space or start)
#   Authorization: <scheme>    -> Authorization: [redacted]
#   Bearer <token>             -> Bearer [redacted]
#   AKIA[A-Z0-9]{16}           -> [redacted]
#   hf_[a-zA-Z0-9]{20,}        -> [redacted]
#   ghp_[a-zA-Z0-9]{36}        -> [redacted]
#   -----BEGIN ... PRIVATE KEY-----\n.*?\n-----END ... PRIVATE KEY-----  (DOTALL) -> [redacted]

def redact(text: str) -> tuple[str, bool]
    # Returns (redacted_text, was_redacted). was_redacted is True if any pattern matched.
    # Never raises; on internal error returns (text, False).

def redact_bytes(data: bytes) -> tuple[bytes, bool]
    # Decodes utf-8 errors='replace', calls redact, re-encodes.
```

Redaction runs before **any** write of terminal block `output_head`/`output_tail` or pasted content into `messages.content`. A block with `was_redacted=True` sets `terminal_blocks.redacted = 1`.

## 3. Shell integration (new BE/streaming/shell_integration.py)

### rc files (new BE/shell/bashrc, BE/shell/zsh/.zshrc)

`shell/bashrc`:
```bash
# Halbert shell integration — sourced via `bash --rcfile <halbert>/shell/bashrc -i`
# Source the user's real bashrc first so aliases/functions survive.
[ -f "$HOME/.bashrc" ] && source "$HOME/.bashrc"
__halbert_prompt_cmd() {
    local ec=$?
    printf '\e]133;A\a'           # prompt start
    return $ec
}
PROMPT_COMMAND="__halbert_prompt_cmd${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
__halbert_preexec() {
    printf '\e]133;B\a'           # input start
    printf '\e]7;file://%s%s\a' "$(hostname)" "$PWD"   # OSC 7 cwd
}
__halbert_precmd() {
    local ec=$?
    local id="$$-$(date +%s%N 2>/dev/null || date +%s)"
    local cmd_b64=$(echo -n "$BASH_COMMAND" | base64)
    printf '\e]133;C;id=%s;cmd=%s\a' "$id" "$cmd_b64"   # output start (command + block id)
    printf '\e]133;D;%d\a' "$ec"                          # end (exit code)
}
trap '__halbert_preexec' DEBUG
PROMPT_COMMAND="__halbert_precmd; __halbert_prompt_cmd${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
```

`shell/zsh/.zshrc`:
```zsh
# Halbert shell integration — sourced via ZDOTDIR=<halbert>/shell/zsh zsh
# Source the user's real zshrc first.
[ -f "$HOME/.zshrc" ] && source "$HOME/.zshrc"
__halbert_precmd() {
    local ec=$?
    printf '\e]133;A\a'
    printf '\e]133;D;%d\a' "$ec"
}
__halbert_preexec() {
    printf '\e]133;B\a'
    printf '\e]7;file://%s%s\a' "$(hostname)" "$PWD"
    local id="$$-$(date +%s%N 2>/dev/null || date +%s)"
    local cmd_b64=$(echo -n "$1" | base64)
    printf '\e]133;C;id=%s;cmd=%s\a' "$id" "$cmd_b64"
}
precmd_functions=(__halbert_precmd $precmd_functions)
preexec_functions=(__halbert_preexec $preexec_functions)
```

### OSC 133 parser (byte state machine)

```python
# States
class OSCState(enum.Enum):
    GROUND = 0       # normal output
    ESC = 1          # saw \x1b
    OSC = 2          # inside \e]...\x07 or \e]...\x1b\\  (ST terminator)
    CSI = 3          # inside \e[...  (alt-screen \e[?1049h)
    INTERM = 4       # saw \x1b inside OSC (possible ST)

@dataclass
class BlockBoundary:
    kind: str            # 'A' | 'B' | 'C' | 'D' | '7' | 'alt_enter' | 'alt_exit'
    block_id: str | None # from C marker id= field
    command: str | None  # base64-decoded from C marker cmd= field
    exit_code: int | None # from D marker
    cwd: str | None      # from OSC 7 file://host/path

@dataclass
class ParsedOutput:
    passthrough: bytes   # bytes to forward to xterm.js unchanged
    boundaries: list[BlockBoundary]
    block_bytes: bytes   # bytes attributed to the current open block (between C and D)

class OSCParser:
    def __init__(self) -> None: ...
    def feed(self, data: bytes) -> ParsedOutput: ...
    # Carries partial sequences across reads. On \e[?1049h or \e[?47h:
    #   marks the current block interactive, emits alt_enter boundary,
    #   stops accumulating block_bytes until \e[?1049l / \e[?47l (alt_exit).
    # On \e]133;C;id=<id>;cmd=<b64>\a: decodes command, starts a new block.
    # On \e]133;D;<exit>\a: closes the block, records exit_code.
    # On \e]7;file://<host><path>\a: records cwd.
    # Everything passes through to xterm unchanged (boundaries are metadata).

# Password-prompt detection (runs on the block's accumulated tail)
PASSWORD_PROMPT_RE = re.compile(rb'(?:[Pp]assword(?:\s+for\s+\S+)?|[Pp]assphrase|[Ss]udo)\s*[:：]\s*$')

def detect_needs_input(block_tail: bytes, silence_seconds: float) -> bool
    # True when the tail matches a password prompt AND silence_seconds >= 5.0
```

### Remote detection

```python
REMOTE_PREFIXES = ('ssh ', 'mosh ', 'slogin ')

def is_remote_command(command: str) -> bool
    # True if the command starts with any REMOTE_PREFIXES (after stripping leading whitespace).
    # Remote blocks: inner commands are not parsed (the parser still passes bytes through,
    # but block boundaries from the inner shell are ignored — only the outer block is recorded).
```

## 4. PTYSession fan-out reader (BE/streaming/pty.py — extend in place)

The current `read_chunk()` registers a **per-caller** `loop.add_reader` on the master fd. A second `add_reader` on the same fd starves the first (`pty.py:174-197`). Plan B replaces this with a **single reader task** per session that fans out to every consumer queue.

### Changes

```python
class PTYSession:
    # New fields (in __init__):
    self._reader_task: Optional[asyncio.Task] = None
    self._fanout_queues: set[asyncio.Queue] = set()
    self._replay_buffer: bytes = b''  # same as _buffer but exposed for attach replay

    # New method:
    async def attach(self) -> asyncio.Queue:
        """Subscribe to this session's output stream.

        Returns a queue that receives every future chunk. The caller also
        gets a replay: the first item is ('replay', get_buffer()) so a
        newly-attached xterm can render history without a separate fetch.

        Starts the single reader task if it is not already running.
        """
        ...

    def detach(self, queue: asyncio.Queue) -> None:
        """Unsubscribe a consumer queue. Non-blocking."""
        ...

    # read_chunk() is re-implemented as a thin wrapper around attach/detach
    # for backward compatibility (the terminal route's SSE stream uses it).
    # It creates a queue, yields from it, and detaches in finally.

    # kill() must: cancel the reader task, push None to every fanout queue,
    # then close the fd (today's behaviour).
```

**Replay on attach**: the first item on a newly-attached queue is `("__replay__", self.get_buffer())`. The frontend treats this as a buffer reset (xterm.reset() + write). This fixes the blank-tile bug (`TerminalTile.tsx:62-133` never replays `session.output` after async mount).

**Bus overflow never affects block copies**: the bounded scrollback (`_buffer`) is independent of the fanout queues. A queue that drops chunks (full) does not lose scrollback data.

**Backend startup**: marks open blocks `lost` (a `terminal_blocks` row with `ended_at = NULL` and `last_state = 'lost'`). A 4404 on attach marks the session `ended: unknown`, not `exit -1`.

## 5. TerminalSessionManager kinds/caps/TTLs (BE/streaming/session_manager.py — extend in place)

### Per-kind policy

| kind | cap | idle policy | sandbox |
|------|-----|-------------|---------|
| `user` | 3 (tabs later) | never reaped while a client is attached; detached TTL 30 min | none — admin's shell |
| `agent-pool` | 3 | idle TTL 15 min; never reaped while a block is open | same as `run_command` today: `ToolSafetyFramework` gating per block, no OS sandbox wrapper |
| `oneshot` | 2 | 60 s (today's rule) | as today |

### Changes

```python
class TerminalSessionManager:
    def __init__(
        self,
        max_sessions: int = 8,           # total cap across all kinds
        idle_ttl_seconds: int = 60,       # default (oneshot); overridden per-kind
        kind_caps: dict[str, int] | None = None,   # default: {'user': 3, 'agent-pool': 3, 'oneshot': 2}
        kind_ttls: dict[str, int] | None = None,   # default: {'user': 1800, 'agent-pool': 900, 'oneshot': 60}
    ):
        self._kinds: dict[str, str] = {}           # session_id -> kind
        self._attach_counts: dict[str, int] = {}   # session_id -> ws client count
        self._block_open: dict[str, bool] = {}     # session_id -> has an open block
        ...

    async def spawn(self, command, *, cwd=None, env=None, cols=80, rows=24, kind: str = 'oneshot', watched: bool = True) -> str:
        # Enforces per-kind cap (not just total). kind is stored.
        # For 'user' kind: command is the shell bootstrap (bash --rcfile / zsh ZDOTDIR).
        # For 'agent-pool': command is 'bash --norc --noprofile' (pool sets up markers per-block).
        ...

    def attach_client(self, session_id: str) -> None:
        """Increment the ws client count (prevents user-shell reaping)."""
        ...

    def detach_client(self, session_id: str) -> None:
        """Decrement the ws client count."""
        ...

    def set_block_open(self, session_id: str, is_open: bool) -> None:
        """Mark a session as having an open block (prevents agent-pool reaping)."""
        ...

    def list_active(self) -> list[dict]:
        # Each entry gains: kind, owner, watched, block_open, attach_count
        ...

    def _reap_once(self) -> None:
        # Per-kind TTL. user sessions with attach_count > 0 are never reaped.
        # agent-pool sessions with block_open are never reaped.
        ...
```

The WebSocket bridge (`routes/websocket.py` terminal ws handler) calls `attach_client`/`detach_client` on connect/disconnect.

## 6. Agent pool (new BE/streaming/agent_pool.py)

```python
class TerminalPool:
    """Pool of PTY-backed bash sessions for agent run_command.

    The pool owns 'agent-pool' kind sessions in the TerminalSessionManager.
    executor._run_command asks the pool for a session that is not busy
    (no open block) and not interactive; spawns one up to the cap; falls
    back to the subprocess path at cap or when the session is interactive.
    """

    def __init__(self, manager: TerminalSessionManager, *, cap: int = 3):
        self._manager = manager
        self._cap = cap
        self._sessions: dict[str, PTYSession] = {}  # pool-owned session_ids

    async def acquire(self) -> tuple[str, PTYSession] | None:
        """Return an idle, non-interactive pool session, or spawn one.

        Returns None when at cap and all sessions are busy/interactive
        (caller falls back to subprocess).
        """
        ...

    async def run_block(self, command: str, *, cwd: str | None = None, timeout: float = 30.0) -> dict:
        """Run a single command as a block in a pool session.

        1. Acquire a session (or spawn one).
        2. Write: printf '\e]133;C;id=<block_id>\a'; <cmd>; printf '\e]133;D;%d;id=<block_id>\a' "$?"
           with cwd honoured via a leading `cd <cwd> &&` inside the block.
        3. Await the block's D marker with the tool timeout.
        4. On timeout: write ETX (\x03), grace-wait 2 s for D, else kill and evict.
        5. Return {block_id, session_id, exit_code, output_head, output_tail, duration}.

        Publishes terminal_spawn (attach='ws', owner='agent', block_id) and
        terminal_complete via the terminal event bus.
        """
        ...

    def release(self, session_id: str) -> None:
        """Mark a session as no longer busy (block closed). Does not kill."""
        ...

    async def shutdown(self) -> None:
        """Kill all pool sessions."""
        ...
```

**Pool session spawn**: `bash --norc --noprofile` with job control (`set -m`), ECHO cleared on the slave before exec (via `termios` on the slave fd in `PTYSession.spawn()` — add an `echo: bool = True` param; when False, clear `ECHO` on the slave fd before `execvpe`).

**Block markers**: the pool writes `printf '\e]133;C;id=<block_id>\a'; <cmd>; printf '\e]133;D;%d;id=<block_id>\a' "$?"\n` to the session's stdin. The OSC parser on the master fd sees the C and D markers and records the block.

**Fallback**: at cap, or when the pool session is in an interactive state, fall back to today's `asyncio.create_subprocess_shell` path (the current `_run_command` implementation).

## 7. Executor wiring (BE/tools/executor.py — extend _run_command)

```python
async def _run_command(self, args: Dict) -> str:
    command = args["command"]
    timeout = args.get("timeout", self.DEFAULT_TIMEOUT)
    cwd = args.get("cwd")
    background = args.get("background", False)  # Plan C; Plan B ignores but accepts the kwarg

    if cwd:
        cwd = os.path.expanduser(cwd)

    streaming = terminal_stream_wanted()

    # Try the pool first (only when streaming — non-streaming CLI path stays subprocess)
    if streaming:
        pool = get_terminal_pool()
        result = await pool.run_block(command, cwd=cwd, timeout=timeout)
        if result is not None:
            # Publish spawn + complete events with block_id
            # Store the terminal_block row
            # Return the same string shape the model sees today
            ...
            return _format_block_result(result)

    # Fallback: today's subprocess path (unchanged)
    ...  # existing code
```

The pool path publishes `terminal_spawn` with `attach='ws'`, `owner='agent'`, `block_id=result['block_id']` (new field on the event). The state machine's `_run_tool_streaming` appends `result['block_id']` to `ctx.terminal_session_ids` (which B21 renames to `terminal_block_ids`).

**Long-running promotion**: when a block's `started_at` is > 2 s ago and it is still open, the backend emits `terminal_block_promote` (the tile appears in the Tasks column). This is a timer task in the pool or a check in the reader loop.

## 8. Watched user shell (BE — block insertion + messages.origin='terminal')

When a user shell block closes (OSC 133 D marker on a `user` kind session):

1. `redact()` runs on `output_head` and `output_tail`.
2. `store.insert_terminal_block({...})` records the block.
3. If the session is `watched` and a thread is open: `store.append_message(thread_id, role='system', content=f"$ {command} · exit {exit_code} · {duration:.1f}s · cwd={cwd}", origin='terminal', visible_in_timeline=1, terminal_block_ids=[block_id])`.
4. `thread.last_active` is updated (via `store.update_thread`) for the gap gate, but **never** triggers `new_thread`.
5. The agent sees blocks only at the next turn, in the hint, capped at 8 blocks / 2 KB.

### Hint extension (BE/agents/thread_signals.py build_hint)

Add to the `<continuity>` block, after the recalled threads and before `</continuity>`:

```
[Since your last message you ran N commands in your shell (last: <last cmd>, exit <code>, <relative>)]
```

Only when `N > 0` and the open thread has `terminal`-origin messages since the last `human`/`assistant` message. Capped at 8 blocks / 2 KB.

### terminal_blocks fetch tool (BE/tools/executor.py)

```python
# New tool schema:
{
    "name": "terminal_blocks",
    "description": "Fetch stored terminal block output (≤60 chars)",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Terminal session id"},
            "n": {"type": "integer", "description": "Number of recent blocks (default 5)", "default": 5}
        }
    }
}
# SAFE class in tools/safety.py
# Returns: list of {block_id, command, exit_code, cwd, output_head, output_tail, started_at, ended_at}
```

### Per-session unwatched toggle

`POST /api/terminal/sessions/{id}/watched` with body `{"watched": false}` → `store.update_terminal_session(session_id, watched=0)` and `manager` marks the session unwatched. When unwatched, block closes do not insert `messages` rows (the block row is still stored for the xterm replay, but no timeline/hint entry).

## 9. Stage endpoint (BE/dashboard/routes/terminal.py — extend)

```python
@router.post("/sessions/{session_id}/stage")
async def stage_into_shell(session_id: str, request: StageRequest):
    """Write command text (no newline) to a user PTY at an empty prompt.

    Allowed only when the parser sees the shell at an empty prompt:
    state A/B seen, no C, no bytes typed since B. Otherwise 409 "shell busy".
    """
    # StageRequest: { command: str }
    # 1. Get the session from the manager.
    # 2. Check the parser state: last boundary was A or B, no C open, no bytes since B.
    # 3. If not at prompt: raise HTTPException(409, "shell busy")
    # 4. Write request.command (no newline) to the PTY via session.write_stdin.
    # 5. Return {ok: true, staged: request.command}
```

The parser state is tracked on the session (the OSC parser runs on the master fd for all `user` kind sessions). The manager exposes `is_at_prompt(session_id) -> bool`.

## 10. Events (BE/agents/events.py — new factories)

```python
@classmethod
def terminal_block(
    cls, session_id: str, *, block_id: str, terminal_session_id: str,
    command: str, owner: str, interactive: bool = False, promote: bool = False,
) -> 'StreamEvent'
    # type="terminal_block" (when a new block opens) or "terminal_block_promote" (when promote=True)

@classmethod
def terminal_needs_input(
    cls, session_id: str, *, block_id: str, terminal_session_id: str,
) -> 'StreamEvent'
    # type="terminal_needs_input"

@classmethod
def task_completed(
    cls, session_id: str, *, task_id: str, thread_id: str, title: str,
    exit_code: int, duration: float, tail: str,
) -> 'StreamEvent'
    # type="task_completed" (Plan C uses this; Plan B defines the factory)
```

The existing `terminal_spawn` gains an optional `block_id: str | None = None` and `owner: str = 'agent'` parameter.

## 11. Frontend — StatusLight (new FE/components/agent/StatusLight.tsx)

```typescript
type StatusLightState =
    | 'running'
    | 'needs_attention'
    | 'done_unseen'
    | 'error'
    | 'blocked';

interface StatusLightProps {
    state: StatusLightState;
    elapsedSeconds?: number;  // for running state's mono timer
    exitCode?: number | null; // for done/error text
    label?: string;           // override the default text
    size?: 'sm' | 'md';       // 10px (default) or 14px
}

// Renders an inline SVG (10px or 14px). No state is colour-only:
//   running:          outline ring, no glyph, mono elapsed timer text
//   needs_attention:  outline, '!' glyph, 'needs input' text
//   done_unseen:      filled, '✓' glyph, 'exit 0' text
//   error:            filled, '✕' glyph, 'exit N' text
//   blocked:          filled, '‖' glyph, 'awaiting approval' text
//
// SVG fill/stroke use currentColor; the parent sets the token class:
//   running:          text-status-nominal
//   needs_attention:  text-status-warning
//   done_unseen:      text-status-nominal
//   error:            text-status-critical
//   blocked:          text-accent-strong
//
// Forced-colours safe (currentColor survives).
// One transition: var(--duration-shutter) var(--ease-shutter) on state change.
// No animate-*, no pulses.
```

## 12. Frontend — Tasks column (replaces TerminalAccordionDock)

New component: `FE/components/agent/TasksColumn.tsx` (replaces `TerminalAccordionDock.tsx`).

```typescript
// Structure:
// <div role="complementary" aria-label="Tasks">
//   <div> /* Running section */
//     {runningTasks.map(task => <TaskCard ... />)}
//   </div>
//   <details> /* Finished N › — collapsed */
//     <summary>Finished {count} ›</summary>
//     {finishedTasks.map(task => <TaskCard ... />)}
//   </details>
//   <button>Clear</button>  // removes finished cards from the column only
//
//   <div> /* Your shell — pinned, separate region, never a task */
//     <YourShellRegion session={userSession} />
//   </div>
// </div>

interface TaskCardProps {
    taskId: string;
    title: string;          // the command or sub-agent goal
    threadTopic: string;    // owning thread's provisional title
    state: StatusLightState;
    elapsedSeconds?: number;
    exitCode?: number | null;
    blockId?: string;       // for command tasks: the block to render
    threadId: string;
    onJumpToTurn?: (turnId: string) => void;
    onStop?: (taskId: string) => void;
    onCopy?: (output: string) => void;
}

// TaskCard body:
//   - For a command task: the block (live xterm while running+long-running,
//     frozen <pre> from output_head/tail once done). Says "live in conversation ⤴"
//     when the inline card has the live xterm.
//   - MAX_VISIBLE=3 governs live xterms only.
//   - Finished cards collapse after 10 minutes.
//   - ⤴ opens the task in the timeline at its turn.
//   - stop button calls task_stop (Plan C) or kill (Plan B pool block).
```

`YourShellRegion`:
```typescript
// Renders the user's shell (one session in v1):
//   - xterm.js terminal (interactive, ws transport)
//   - watched/unwatched toggle (calls POST /sessions/{id}/watched)
//   - "stage into my shell" target (receives staged commands from the composer)
//   - badge if the shell is unhooked (watched: false, no OSC 133)
// The admin's shell is never a task card.
```

## 13. Frontend — tile = block (ToolExecutionCard + TerminalTile changes)

### ToolExecutionCard (FE/components/agent/ToolExecutionCard.tsx — rewrite)

For a `run_command` tool block, the card renders **its block**:
- Short block (completed < 2 s): one-line result (`$ smbstatus · exit 1 · 0.3 s`, expandable to `<pre>` with `output_head/tail`).
- Live + long-running (> 2 s): live xterm (the `TerminalTile` component) while it is the session's current open block.
- Frozen once complete: `<pre>` from `output_head/tail` (no xterm, no socket).
- The card's own `<pre>` result is suppressed when a block renders.
- Origin anchor: `data-terminal-block={blockId}`.
- StatusLight on the card header (on a `--color-surface` strip, not on the status-tinted body).
- Labels are measurements (`exit 0`, never "Success").

### TerminalTile (FE/components/agent/TerminalTile.tsx — fix + extend)

- **Replay-on-mount fix**: on mount, call `session.attach()` which sends `("__replay__", buffer)` first; the tile does `term.reset(); term.write(buffer)` then continues with live chunks.
- **Block-based rendering**: the tile renders for a specific `blockId`, not just a session. When the block is complete, the tile shows a frozen `<pre>` (from `output_head/tail`) and disposes the xterm.
- **Agent-owned**: `disableStdin`, no cursor (unless `owner='user'`).
- **Token fixes**:
  - Line 181: `bg-[#1a1b26]` → `bg-canvas-subtle`
  - Line 199: `bg-violet-500/20 text-violet-300 border-violet-500/40` → `bg-status-telemetry-bg text-status-telemetry border-status-telemetry-line`
- **IntersectionObserver**: mount guard + `rootMargin`; docking stays one-way.
- **confirmAction**: gets the partial-line buffer `sendMessage` has.

### Inline vs task card

Inline and the task card never both mount an xterm for one session — inline wins and the task card says "live in conversation ⤴".

## 14. Frontend — PTY key ownership (FE — TerminalTile + ShellModeContext)

- PTY tiles own every key except the escape hatch **Ctrl+`** (via `xterm.attachCustomKeyEventHandler`).
- The tile header is the tab stop (Enter/F2 enters the tile); read-only tiles set the textarea `tabIndex=-1`.
- `ShellModeContext`'s Cmd/Ctrl+B bails inside `.xterm` (check `e.target.closest('.xterm')` in the handler).
- No thread shortcut exists.

## 15. Frontend — Sheet below md (FE — narrow windows)

Below the `md` breakpoint, `ContextStage` (vitals, Tasks column, Your shell) renders as a `Sheet` (bottom sheet / drawer) opened from the aggregate StatusLight on the `ModeSwitch` tab. "Go back to this" opens the sheet, scrolls the timeline, expands the task card.

## 16. Frontend — token fixes and literal-colour ratchet

- `TerminalTile.tsx:181`: `bg-[#1a1b26]` → `bg-canvas-subtle`
- `TerminalTile.tsx:199`: violet classes → `bg-status-telemetry-bg text-status-telemetry border-status-telemetry-line`
- `ToolExecutionCard.tsx`: remove `bg-blue-100`, `border-blue-200`, `text-info` (use `status-*` tokens); remove `animate-spin`; labels become measurements.
- `TerminalAccordionDock.tsx`: deleted (replaced by `TasksColumn.tsx`).
- `check_literal_colors.py`: extend `PATTERN` to catch `-[#hex]` (e.g., `bg-[#1a1b26]`):
  ```python
  HEX_PATTERN = re.compile(r'\b(?:bg|text|border|from|to|via|ring|fill|stroke)-\[#[0-9a-fA-F]{3,8}\]')
  ```
  Add to the scan and the ratchet.
- Delete `glow`/`pulse-subtle` keyframes if they exist in `tailwind.config.js` or CSS.
- `motion-reduce:animate-none` on remaining spinners (if any).

## 17. Frontend — SSE events (FE/hooks/useAgentStream.ts — extend)

New events handled:
- `terminal_block` → push a block record into the session's block list; if long-running, create a task card.
- `terminal_block_promote` → promote the block to a task card in the Tasks column.
- `terminal_needs_input` → set the block's state to `needs_attention`; light the StatusLight.
- `task_completed` → move the task card to Finished; light the StatusLight; set `thread.unread`.

`terminal_spawn` gains `block_id` and `owner` fields. The frontend uses `block_id` to correlate the inline card with the task card.

## 18. Frontend — live regions (FE — extend Plan A's live regions)

Plan A created a `role="status" aria-live="polite"` region. Plan B adds:
- `<command> finished, exit 0` announcements to the polite region.
- xterm `screenReaderMode` on for the focused tile only.

## 19. Tests (spec §13 — Plan B scoped)

### Backend

- OSC parser: split-sequence across reads; interleaved-echo (output between C and D); alt-screen enter/exit; password-prompt detection; remote command tagging.
- ETX timeout on a pool block: write ETX, grace-wait 2 s, kill and evict, emit `terminal_complete` exit −1.
- Reaper never kills an attached user shell (attach_count > 0).
- Reaper never kills an agent-pool session with an open block.
- Two PTY consumers both receive every byte (fan-out reader).
- Replay on attach: buffer is sent first, then live chunks.
- Redaction patterns: password=, -p, Authorization:, Bearer, AKIA, hf_, ghp_, PRIVATE KEY block.
- Stage-into-shell refused when not at prompt (state C open, or bytes typed since B).
- Stage-into-shell succeeds at an empty prompt.
- Block insertion: user block close inserts `messages.origin='terminal'` row with `terminal_block_ids=[block_id]`.
- Unwatched session: block close stores the block but no `messages` row.
- `terminal_blocks` fetch tool returns stored blocks.
- `migrate_terminal_block_ids_to_blocks`: session ids → block ids.
- Pool fallback to subprocess at cap.
- Long-running promotion at 2 s.

### Frontend (vitest)

- `StatusLight` renders each of the 5 states with shape + glyph + text.
- `TasksColumn` renders Running / Finished / Clear + Your shell region.
- `TaskCard` renders a command task with the StatusLight and ⤴.
- `TerminalTile` replay-on-mount (buffer sent first).
- `TerminalTile` frozen block after reuse (no xterm, `<pre>` from output_head/tail).
- `ToolExecutionCard` renders a block (one-line for short, xterm for long-running).
- `YourShellRegion` renders the watched/unwatched toggle.
- Token fixes: no `bg-[#hex]` or violet classes in `TerminalTile` or `ToolExecutionCard`.

### Browser (Playwright against a live backend)

- Tile from message 1 survives message 2 and a reload (replay-on-mount).
- A long-running command (> 2 s) appears in the Tasks column.
- A finished task collapses after 10 minutes (or simulate time).
- `prefers-reduced-motion` → no running animations.
- `forced-colors: active` screenshot of the five StatusLight states.
- Tab into a live tile → Ctrl+` returns focus.
- Ctrl+B inside a tile does not toggle mode.
- Stage into shell: composer stages a command, it appears in the user's shell at the prompt.
