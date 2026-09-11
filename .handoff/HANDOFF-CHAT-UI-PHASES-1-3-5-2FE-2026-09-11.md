# HANDOFF — Chat UI Modernization: Phases 1/3/5/2FE Done, Phase 4 Remains

**Status:** ACTIVE
**To:** Next agent (fable/k3 tier or equivalent)
**From:** Implementation session, 2026-09-11
**Repo:** `/Volumes/4TB-BAD/Halbert`
**Branch:** `main` (uncommitted changes — see §0)
**Predecessors:**
- `PLAN-CHAT-UI-REFINED-2026-09-11.md` (the refined plan — Phases 1/3/5 scope)
- `PLAN-CHAT-UI-FABLE-LEVEL-DESIGN-2026-09-11.md` (the fable-level design — Phase 2/4 design)
- Backend Phase 2 already committed at `fbd725e9` ("feat(agent): stream model reasoning as thinking, read the structured field")

---

## 0. What was done this session

Four of the five phases from the refined plan are now implemented in the working tree (uncommitted). All frontend gates pass: `npm run typecheck`, `npm test` (1066 tests), `python scripts/check_contrast.py`, `python scripts/check_literal_colors.py`. No new literal colors or contrast violations were introduced.

### Phase 1 — Unboxed Canvas & Rich Markdown

| File | Change |
|------|--------|
| `Timeline.tsx:416-417` | Stripped `bg-muted/50 border rounded-lg p-4` container from assistant turns. Prose flows directly on canvas. |
| `AgentChat.tsx:1088-1089` | Same unboxing for the live assistant block. |
| `MarkdownRenderer.tsx:87-89` | Removed 3 debug `console.log` statements. |
| `MarkdownRenderer.tsx:34-76` | Added inline code chips (`` `code` `` → styled `<code>` with `bg-muted/80 border-hairline/60`). |
| `MarkdownRenderer.tsx:175-225` | Added GFM table detection (`<table>`/`<thead>`/`<tbody>` with alternating row tints) and blockquote rendering (`>` → borderless `<blockquote>` with `border-l-2 border-hairline`). |
| `MessageContent.tsx:12,72` | Wired `MarkdownRenderer` into the text-part path. Non-code parts now render as markdown; fenced code blocks still route to `CodeBlock` via `splitFences()`. |

### Phase 3 — Ephemeral CLI Pills

| File | Change |
|------|--------|
| `ToolExecutionCard.tsx:10,68-70,158-188` | Added compact 1-line pill early return for short successful commands (<2s, exit 0). The pill is a `<button>` with StatusLight, command, duration, exit code, and a ChevronDown icon. Clicking expands to the full card. Errors (`status === 'error'`) auto-expand via `useState` initializer. |

### Phase 5 — Resizable Stacked Terminal Dock

| File | Change |
|------|--------|
| `TerminalTile.tsx:18` | Added Lucide imports: `Pin, PinOff, Square, Copy, Check`. |
| `TerminalTile.tsx:301,354,361,369` | Replaced all 5 pictographic glyphs: `📌`→`Pin`, `📍`→`PinOff`, `⏹`→`Square`, `⧉`→`Copy`, `✓`→`Check`. Geometric shapes (`■`/`●`/`○`) kept. |
| `TerminalTile.tsx:89-110,397-405` | Added stateful height (240px default, clamped 140–600px) and a draggable resize handle above the xterm container. Drag triggers `fitAddon.fit()` and PTY resize. |
| `TasksColumn.tsx:14-18,49-143` | Added expandable terminal drawers to `TaskCard`. Running tasks with a `blockId` show a ChevronDown that mounts a `TerminalTile` inline. De-duplication: if the terminal is visible in the conversation, shows "live in conversation ↑" instead of mounting a duplicate xterm. |

### Phase 2 FE — Borderless ThinkingPanel

| File | Change |
|------|--------|
| `ThinkingPanel.tsx` (full rewrite) | Borderless, dim/italic, minimal vertical space. Header is "Thinking..." while streaming, transforms to "Thought for {elapsed}" on `thinking_complete`. Auto-collapses when finished; manual toggle overrides. Matches warp reference pattern (`agent_block_sections.rs:117-136`). |
| `useAgentStream.ts:299-300,469,578-581,1080,1435,1487` | Added `thinkingDurationMs` state. Handles `thinking_complete` SSE event (reads `duration_ms`). Clears on new turn and on reset. Exposed in return object. |
| `AgentChat.tsx:325,1174` | Passes `thinkingDurationMs` to `ThinkingPanel`. |

### Test updates

Three existing tests were updated to match the new compact pill and auto-expand behavior:

| File | Change |
|------|--------|
| `ToolExecutionCard.wiring.test.tsx:37-53` | Test now asserts the compact pill button by role and text content instead of the old inline one-liner format. |
| `ToolExecutionCard.test.tsx:53-67` | Same — asserts the pill button instead of `getByText(/\$ echo hello/)`. |
| `Timeline.blocks.test.tsx:60-68` | Test now asserts the command label renders (and auto-expands on error exit) instead of the old one-liner format. |

---

## 1. What remains: Phase 4 — Background Processes & Port Sniffing

Phase 4 is the only phase not implemented. It is backend-heavy and requires new architecture that does not exist yet. The fable-level design document (`PLAN-CHAT-UI-FABLE-LEVEL-DESIGN-2026-09-11.md` §3) has the full design; this section is the actionable summary.

### 1.1 The four things that don't exist yet

1. **`ProcessRegistry`** — no such class exists anywhere in the codebase. `executor.py:893` has `# background is accepted but ignored (Plan C).` The `background` parameter is accepted but not wired. This is a new subsystem, not a wiring task.

2. **`StreamEvent.task_started`** — doesn't exist. `events.py` has `task_completed` (line 691) but no `task_started`. A new factory is needed.

3. **`StreamEvent.port_discovered`** — doesn't exist. A new factory is needed.

4. **Port sniffing** — no stdout regex for `localhost:PORT` exists anywhere. The session manager is the natural home (it already parses OSC 133 markers from the PTY byte stream).

### 1.2 The design decisions (already made in the fable document)

**Q1 — spawn mechanism: split by intent.**
- `background=true` (fire-and-forget server) → a detached subprocess, open-claude-code style (`spawn(..., {detached:true, stdio:['ignore','pipe','pipe']})` + `proc.unref()` + immediate return). NOT the PTY pool — a PTY keeps a bash session alive that a detached server doesn't need.
- `background=false` (foreground command) → the PTY pool, as today.
- **Gated on founder confirmation** — this is the one place the refined plan's "no new subprocess path" is wrong. The fable document explains why.

**Q2 — lifecycle: already exists.**
The chain is: `terminal_block` (spawn) → `terminal_block_promote` (long-running, >2s) → `terminal_output` (streaming) → `terminal_complete` (exit code, duration, output head/tail) → `task_completed` (task card done). The frontend's `useAgentStream.ts:948-959` already consumes `task_completed` and calls `terminalSessionStore.completeBlock`. The only missing piece is the **start** signal (`task_started`).

**Q3 — port sniffing: in the PTY output path (SessionManager).**
`terminal_bridge.py` is the event bus (publish/subscribe), not the byte stream — it has no stdout to sniff. The session manager is where `is_interactive` and OSC 133 detection already live. The sniff is a regex over each output chunk for `(localhost|127.0.0.1|0.0.0.0|::1):(\d{1,5})`, deduplicated per block, emitting `port_discovered` when a new port appears. Must be cheap (single regex pass per chunk) and non-blocking.

**Q4 — the new factory signatures.**
```python
@classmethod
def task_started(cls, session_id, *, task_id, thread_id, title, block_id) -> 'StreamEvent':
    return cls(type="task_started", session_id=session_id,
               data={"task_id": task_id, "thread_id": thread_id,
                     "title": title, "block_id": block_id})

@classmethod
def port_discovered(cls, session_id, *, port, host, block_id) -> 'StreamEvent':
    return cls(type="port_discovered", session_id=session_id,
               data={"port": port, "host": host, "block_id": block_id})
```

### 1.3 What to build, in order

1. **`StreamEvent.task_started` factory** in `agents/events.py` — the symmetric twin of `task_completed`.
2. **`StreamEvent.port_discovered` factory** in `agents/events.py`.
3. **`ProcessRegistry`** — a new subsystem that owns the detached-spawn lifecycle. Stores `{id, pid, command, status, stdout, stderr}` in a map. Calls `proc.unref()`. Returns immediately with `{block_id, pid, status: "running"}`. The `close` event flips status to `completed`/`exited(code)` and emits `task_completed` (already wired on the frontend).
4. **Wire `background=true` in `tools/executor.py`** — when `background=true`, spawn via `ProcessRegistry` instead of the PTY pool. Emit `task_started` immediately. The turn does not block on completion.
5. **Port sniffing in the session manager** — regex over output chunks, deduplicated per block, emit `port_discovered`.
6. **Frontend: handle `task_started` and `port_discovered` in `useAgentStream.ts`** — `task_started` creates a task card in the running section; `port_discovered` renders a port chip that opens a browser tab (staged, never executed).
7. **Frontend: port chip component** — a small badge showing `:8765` with a click handler that stages `open http://localhost:8765` into the composer (per the standing directive: commands staged, never executed).

### 1.4 What NOT to build

- Do not persist background task state to SQLite. No migrations.
- Do not add `thinking_content` or `thinking_duration_ms` columns. Phase 2 persists nothing (fable design §2.4).
- Do not use openclaw's `ports-probe.ts` / `ports-lsof.ts` — it answers "is this port free / who owns it," not "what port did my server open." The regex-over-stdout approach is correct and has no direct OSS twin.
- Do not recreate the terminal event vocabulary. It already exists (`terminal_spawn`, `terminal_output`, `terminal_complete`, `terminal_block`, `terminal_block_promote`, `terminal_needs_input`). The detached-spawn branch reuses the same events — only the spawn mechanism differs.

### 1.5 Acceptance criteria

1. `background=true` returns immediately with a block id; the turn does not block on completion.
2. `StreamEvent.task_started` fires when a background task begins; `task_completed` fires when it ends (already wired).
3. `StreamEvent.port_discovered` fires when a listening port appears in a block's output.
4. The event vocabulary and frontend rendering stay single; the detached-spawn branch is the one justified second spawn path.
5. Port sniffing is a single regex pass per chunk, deduplicated, non-blocking.
6. The port chip stages a browser-open command into the composer; it does not execute.

### 1.6 Test command

```bash
# Frontend
cd halbert_core/halbert_core/dashboard/frontend
npm run typecheck
npm test

# Backend (MANDATORY arch -arm64 prefix)
arch -arm64 .venv/bin/python -m pytest halbert_core/tests

# Design gates
python scripts/check_contrast.py
python scripts/check_literal_colors.py
```

### 1.7 OSS reference

| Pattern | Source | What to lift |
|---------|--------|--------------|
| Background detached spawn | `open-claude-code/v2/src/tools/bash.mjs:119-146` | `spawn(..., {detached:true, stdio:['ignore','pipe','pipe']})` + `Map` store + `proc.unref()` + immediate `{id,pid,command,status}` return |
| Terminal input ownership | `warp/crates/warp_tui/src/terminal_use.rs:37-54` | `TuiInputTarget` (Pty vs AgentEditor) — who owns input |
| Port probe/lsof | `openclaw/src/infra/ports-probe.ts`, `ports-lsof.ts` | **Nothing** — answers a different question |

---

## 2. Standing directives that still apply

| Directive | How Phase 4 must comply |
|-----------|------------------------|
| No model names | Task cards show command, never model name |
| No Sovereign/hostname | UI headers use the onboarding name |
| Staged, never executed | Port chips stage `open http://localhost:PORT` into the composer; they do not execute |
| Colour from tokens | All new classes use `shared-tokens/tokens.css` tokens; run `check_contrast.py` + `check_literal_colors.py` |
| No emoji | Port chips use Lucide icons or text, never pictographic glyphs |
| No migrations | Phase 4 adds no schema. Background task state is ephemeral. |
| One place each thing | The event vocabulary + frontend rendering stay single; the detached-spawn branch is the one justified second spawn path |
| Commit hygiene | No Co-Authored-By, no generation trailers |

---

## 3. Committing the current work

The changes from this session are uncommitted. When committing:

- Do not add `Co-Authored-By` or `Generated with` trailers.
- Suggested commit subject: `feat(dashboard): unboxed canvas, rich markdown, CLI pills, resizable terminal dock, borderless thinking`
- The test updates are part of the same commit — they assert the new behavior.
- The `web/feature-reference/` changes in the diff are NOT from this session; they are pre-existing uncommitted changes from another session. Do not include them in this commit.

```bash
git add halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.tsx \
  halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx \
  halbert_core/halbert_core/dashboard/frontend/src/components/domain/MarkdownRenderer.tsx \
  halbert_core/halbert_core/dashboard/frontend/src/components/agent/MessageContent.tsx \
  halbert_core/halbert_core/dashboard/frontend/src/components/agent/ToolExecutionCard.tsx \
  halbert_core/halbert_core/dashboard/frontend/src/components/agent/ToolExecutionCard.test.tsx \
  halbert_core/halbert_core/dashboard/frontend/src/components/agent/ToolExecutionCard.wiring.test.tsx \
  halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.blocks.test.tsx \
  halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.tsx \
  halbert_core/halbert_core/dashboard/frontend/src/components/agent/TasksColumn.tsx \
  halbert_core/halbert_core/dashboard/frontend/src/components/agent/ThinkingPanel.tsx \
  halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.ts
```
