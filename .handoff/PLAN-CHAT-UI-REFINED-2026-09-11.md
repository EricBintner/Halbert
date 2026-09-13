# REFINED IMPLEMENTATION PLAN: Chat UI Modernization & Stacked Terminal

**Date**: 2026-09-11
**Status**: Ready for implementation (Phases 1, 3, 5); Phase 2 deferred to Fable; Phase 4 needs design pass
**Supersedes**: `PLAN-CHAT-UI-MODERNIZATION-AND-STACKED-TERMINAL-2026-09-11.md`
**Scope**: Frontend (`dashboard/frontend/src`), Backend (`dashboard/routes/agent.py`, `streaming/`, `agents/`, `tools/`)

---

## 0. Corrections to the Original Plan

Every line number and code claim in the original was verified against the merge-base. Twelve inaccuracies were found. The corrected plan below incorporates all fixes.

### Major corrections (would have caused implementation failures)

1. **`set_terminal_pool_enabled(True)` is already called in production.** `dashboard/app.py:199-201` already wires it. The original Phase 4 listed this as new work. Removed.

2. **TetherChip is clickable, not "unclickable."** The original Defect 5 claimed InlineTerminals renders an "unclickable text chip." `InlineTerminals.tsx:53` wires `onClick={undock}` and `TetherChip.tsx:29` implements it. The chip restores the terminal on click. Corrected.

3. **`ProcessRegistry` does not exist.** Phase 4 said "Wire `background=true` via `ProcessRegistry`." No such class exists anywhere in the codebase. This is a new component that must be designed and built. Flagged as a design item, not a wiring task.

4. **`StreamEvent.task_started` and `StreamEvent.port_discovered` don't exist.** Phase 4 referenced both as if they existed. `events.py` has `task_completed` (line 690) but no `task_started`. No `port_discovered` exists at all. These are new factories that must be explicitly designed.

5. **MarkdownRenderer prop is `text`, not `content`.** Phase 1 step 3 said `<MarkdownRenderer content={part.content} />`. The actual interface (`MarkdownRenderer.tsx:21`) is `text: string`. Corrected to `<MarkdownRenderer text={part.content} />`.

6. **Backend streaming rewiring is architecturally mismatched.** Phase 2 said to replace the discard logic in `agent.py:1462-1502` with `yield StreamEvent.thinking(...).to_sse()`. But that generator yields **raw text strings** to its caller, not SSE events. Injecting SSE-formatted strings would corrupt the response. Thinking events must go through the SSE event bus (alongside `tool_start`, `state_change`, etc.), not the text generator. This is a design problem, not a wiring task. **Deferred to Fable.**

7. **`StreamEvent.thinking` data contract doesn't match the plan's SSE spec.** The plan's section 6.1A showed `duration_ms` inside the thinking event data. The existing factory (`events.py:328-334`) only sends `{"content": content}`. The factory would need modification. Folded into the Fable deferral.

### Moderate corrections

8. **blockId fallback already exists.** `ToolExecutionCard.tsx:74-75` falls back to `execution.blockId`. The original said "no caller passes blockId" — true for the explicit prop, but the execution object may carry it on the stream path. Clarified.

9. **SQLite ALTER TABLE needs an idempotency guard.** Bare `ALTER TABLE ADD COLUMN` throws `OperationalError: duplicate column name` on restart. The plan needs a column-exists check. Folded into Phase 2 deferral.

10. **Default height change.** Phase 5 changes TerminalTile from 192px (`h-48`) to 240px. Noted as a visual shift.

### Minor corrections

11. **MarkdownRenderer consumer paths.** Original said `Network.tsx`, `Services.tsx` — they're at `pages/Network.tsx`, `pages/Services.tsx`.

12. **OSC 133 alt-screen detection.** Section 7.2 attributed it to `agent_pool.py`. The pool delegates to `self._manager.is_interactive(sid)` (`agent_pool.py:73`); the byte detection lives in the session manager.

---

## 1. Phase Sequencing

```
Phase 1  ──→  Phase 3  ──→  Phase 5
(FE only)    (FE only)    (FE + BE)

Phase 2: DEFERRED TO FABLE (backend architecture needs design)
Phase 4: NEEDS DESIGN PASS (ProcessRegistry + event factories don't exist)
```

| Phase | Scope | Risk | Status |
|-------|-------|------|--------|
| **1: Unboxed Canvas & Rich Markdown** | Frontend | Low | Ready |
| **2: Borderless Streaming Thinking** | Fullstack | Medium | **Deferred to Fable** |
| **3: Ephemeral CLI Pills** | Frontend | Low | Ready |
| **4: Background Processes & Ports** | Backend heavy | High | **Needs design pass** |
| **5: Resizable Terminal Dock** | Frontend | Medium | Ready |

---

## 2. Phase 1: Unboxed Canvas & Rich Markdown

**Risk**: Low. Frontend only. No backend changes.
**Reference patterns**: `open-claude-code/v2/src/ui/markdown.mjs` (table parsing, blockquote handling), `open-claude-code/v2/src/ui/components.mjs:98-104` (AssistantMessage renders markdown directly, no box).

### 2.1 Strip Assistant Container Cards

**Files**:
- `Timeline.tsx:416-417`
- `AgentChat.tsx:1088-1089`

**Current code** (both locations identical):
```tsx
<div className="flex justify-start">
  <div className="max-w-[85%] bg-muted/50 border border-border/50 rounded-lg p-4 space-y-3">
```

**Replacement**:
```tsx
<div className="flex justify-start w-full">
  <div className="w-full space-y-3 text-foreground leading-relaxed">
```

**User message contrast**: Keep the existing right-aligned user bubble (`Timeline.tsx:402-407`, `AgentChat.tsx:1082-1084`) unchanged. The user turn stays a subtle surface bubble; the assistant turn flows directly on canvas.

### 2.2 Clean Debug Logs from MarkdownRenderer

**File**: `components/domain/MarkdownRenderer.tsx:87-89`

Delete these three lines:
```tsx
console.log('[MarkdownRenderer] Input text (first 500 chars):', JSON.stringify(text.slice(0, 500)));
console.log('[MarkdownRenderer] Has double newlines:', text.includes('\n\n'));
console.log('[MarkdownRenderer] Newline count:', (text.match(/\n/g) || []).length);
```

### 2.3 Add Inline Code, GFM Tables, Blockquotes to MarkdownRenderer

**File**: `components/domain/MarkdownRenderer.tsx`

The existing renderer handles `#`/`##` headers, `**bold**`, `[links](url)`, bullet lists, and code blocks. It lacks inline code chips, GFM tables, and blockquotes.

**Inline code** — add to `formatInlineMarkdown` (after the bold/link regex, line 39):
```tsx
// Inline code: `text` -> styled code chip
result = result.replace(/`([^`]+)`/g, (_, t) =>
  String.fromCharCode(0) + 'CODE:' + t + String.fromCharCode(0)  // placeholder
);
```
Then in the JSX return, convert placeholders to `<code className="px-1.5 py-0.5 rounded bg-muted/80 font-mono text-[12px] text-foreground border border-hairline/60">{t}</code>`.

**GFM tables** — add table detection before the paragraph fallback (after line 173). Pattern from `open-claude-code/v2/src/ui/markdown.mjs:134-152`:
- Detect lines starting and ending with `|`.
- Skip separator rows (`|---|---|`).
- Parse cells by splitting on `|` and trimming.
- Render with semantic `<table className="w-full border-collapse border border-hairline text-sm">`, `<thead>`, `<tbody>`, alternating row tints (`bg-surface/50` on even rows).

**Blockquotes** — add before the paragraph fallback. Pattern from `markdown.mjs:202-206`:
- Detect lines starting with `> `.
- Render as `<blockquote className="border-l-2 border-hairline pl-3 my-2 text-muted-foreground italic">`.

**Consumer safeguard**: Existing consumers (`pages/Network.tsx`, `pages/Services.tsx`, `components/AIAnalysisPanel.tsx`, `components/ComponentLibraryViewer.tsx`) pass `text` and optional `onRunCommand`/`compact`. The new features are additive — they only activate when the input contains tables/blockquotes/inline code, so existing prose renders identically.

### 2.4 Wire MarkdownRenderer into MessageContent

**File**: `components/agent/MessageContent.tsx:71-73`

**Current**:
```tsx
return (
  <span key={i} className="whitespace-pre-wrap break-words">{part.content}</span>
);
```

**Replacement**:
```tsx
return (
  <MarkdownRenderer key={i} text={part.content} />
);
```

**Import**: Add `import { MarkdownRenderer } from '../domain/MarkdownRenderer';` at the top.

**Preserve fenced code blocks**: Keep `splitFences()` (lines 23-47) so that ```` ``` ```` fenced blocks still route to `CodeBlock` with staging affordances. Only the non-code text parts route to `MarkdownRenderer`.

**Note**: `MarkdownRenderer` already extracts its own code blocks internally (lines 92-96), so if a fenced block slips through the text path it will still render as a `CodeBlock`. The two paths are compatible — `splitFences` is a first-pass filter, `MarkdownRenderer` is the second-pass renderer for everything else.

### 2.5 Tests

- `MessageContent.test.tsx`: Assert `# Heading` renders `<h2>`/`<h3>`, `**bold**` renders `<strong>`, `` `code` `` renders `<code>`, tables render `<table>`/`<thead>`/`<tbody>`, fenced blocks still route to `CodeBlock`.
- Existing `MarkdownRenderer` consumers should have no visual regression (verify via Storybook).

---

## 3. Phase 2: Borderless Streaming Thinking — DEFERRED TO FABLE

### Why deferred

The backend thinking pipeline has an architectural mismatch that is a design problem, not a wiring task:

1. **Two separate channels exist**: The text stream generator (`agent.py:1462-1502`) yields raw text strings. The SSE event bus (`StreamEvent` factories in `events.py`) emits structured events (`tool_start`, `state_change`, `response_chunk`, etc.) through a separate path. The original plan conflated these by proposing to yield `StreamEvent.thinking(...).to_sse()` from the text generator, which would inject SSE-formatted strings into the raw text stream and corrupt the response.

2. **`StreamingReasoningParser` exists but is unused in the streaming path**: `utils/reasoning.py:138-246` has a complete incremental parser, but `agent.py:1462-1502` uses a hand-rolled `buffer.find("`)` loop instead. Wiring the parser in requires deciding where thinking events are emitted (the event bus), how duration is calculated, and how the text stream stays clean.

3. **`StreamEvent.thinking` needs modification**: The existing factory (`events.py:328-334`) sends `{"content": content}`. The plan's SSE spec adds `duration_ms`. This is a contract change that needs review.

4. **SQLite persistence needs an idempotent column-add**: Bare `ALTER TABLE ADD COLUMN` throws on restart. A column-exists guard or try/except pattern is needed.

### What can proceed now (frontend only)

The `ThinkingPanel.tsx` redesign is independent of the backend pipeline. It can be restyled to be borderless and auto-collapsing using the existing thinking data path (whatever the frontend currently receives). But without the backend emitting thinking events through the event bus, the panel has no data to show. So the frontend redesign is gated on the backend decision.

### What Fable needs to decide

1. Should thinking events be emitted through the SSE event bus (new `StreamEvent.thinking` with duration), with the text stream generator stripped of all thinking-tag handling?
2. Should `StreamingReasoningParser` replace the hand-rolled `buffer.find` loop in `agent.py`?
3. Should thinking be persisted to SQLite (`thinking_content`, `thinking_duration_ms` columns), and if so, what idempotent migration pattern?
4. Should the `TimelineTurn` type gain `thinking?` and `thinkingDuration?` fields, and should the timeline API return them?

### Reference patterns

- `warp/crates/warp_tui/src/agent_block_sections.rs:117-136` — `render_thinking_section`: header is `"Thinking..."` while streaming, transforms to `"Thought for {elapsed}"` on finish, defaults to collapsed when `finished == true`.
- `open-claude-code/v2/src/ui/components.mjs:141-146` — `ThinkingMessage`: dim italic text with a subtle spinner, minimal vertical space.

---

## 4. Phase 3: Ephemeral 1-Line CLI Pills

**Risk**: Low. Frontend only.
**Reference patterns**: `warp/crates/warp_tui/src/tool_call_labels.rs:66-97` (ToolCallDisplayState: glyph + glyph_style per state), `open-claude-code/v2/src/ui/components.mjs:114-139` (ToolMessage: single inline row, truncated result).

### 4.1 Compact 1-Line Result Pill

**File**: `components/agent/ToolExecutionCard.tsx`

The existing card already has a `isShortBlock` path (line 125) that renders a one-line result (lines 201-205). But it's a truncated text line inside the card's bordered container, not a standalone pill.

**Change**: When `isShortBlock && !isExpanded`, replace the entire bordered card with a standalone pill:

```tsx
// Before the existing return, add an early return for short blocks
if (isShortBlock && !isExpanded) {
  return (
    <button
      type="button"
      onClick={() => setIsExpanded(true)}
      className="flex items-center gap-2 py-1 px-2.5 rounded border border-hairline bg-surface/50 text-xs font-mono hover:bg-surface cursor-pointer select-none transition-colors w-full text-left"
      aria-expanded={false}
      aria-label={`Command: ${commandLabel}`}
    >
      <StatusLight state="done_unseen" size="sm" />
      <span className="text-muted-foreground">$</span>
      <span className="text-foreground truncate max-w-[400px]">{commandLabel}</span>
      <span className="text-hairline">·</span>
      <span className="text-muted-foreground">{blockDuration?.toFixed(2)}s</span>
      <span className="text-hairline">·</span>
      <span className="text-muted-foreground">exit {blockExitCode ?? 0}</span>
      <ChevronDown className="h-3 w-3 ml-auto text-muted-foreground" />
    </button>
  );
}
```

**Error condition**: If `execution.status === 'error'` or `blockExitCode !== 0`, auto-expand with critical border:
```tsx
if (isCommandBlock && (execution.status === 'error' || (blockExitCode != null && blockExitCode !== 0))) {
  // Don't early-return; fall through to the expanded card with error styling
}
```

### 4.2 blockId Wiring

**Current state**: `ToolExecutionCard.tsx:74-75` already falls back to `execution.blockId`. The timeline path (`Timeline.tsx:436`) passes `execution={row.item}` which carries `blockId` via `blockFromServer` (`timeline.ts:141-142`). The live stream path (`AgentChat.tsx:1129`) also passes `execution={row.item}`.

**Action**: Verify that the stream path's `ToolExecution` type includes `blockId`. If it does, no wiring is needed — the fallback already works. If it doesn't, add `blockId` to the stream's `ToolExecution` type and populate it from the `terminal_block` SSE event.

### 4.3 InspectionGroup

**File**: `components/agent/InspectionGroup.tsx`

No changes needed. The existing implementation already:
- Groups read-only tools into collapsed pills (line 52: `Looked at {summarise(items)}`)
- Uses Unicode geometric arrows `▾`/`▸` (line 51) — compliant with no-emoji rule
- Expands to show individual `ToolExecutionCard` items on click (lines 55-61)

---

## 5. Phase 4: Background Processes & Port Sniffing — NEEDS DESIGN PASS

### Why this needs design

Three components referenced by the original plan don't exist:

1. **`ProcessRegistry`** — no such class exists. The background-process pattern in `open-claude-code/v2/src/tools/bash.mjs:119-146` uses a simple `Map` (`backgroundJobs`), but Halbert's architecture has a `TerminalPool` and `SessionManager` that would need integration. A design decision is needed: does background execution go through the existing `TerminalPool` (PTY-backed), or a new `ProcessRegistry` (subprocess-backed like open-claude-code)?

2. **`StreamEvent.task_started`** — doesn't exist. `events.py` has `task_completed` (line 690) but no `task_started`. A new factory is needed.

3. **`StreamEvent.port_discovered`** — doesn't exist. A new factory is needed.

### What's already done

- `set_terminal_pool_enabled(True)` is already called in `dashboard/app.py:199-201`. The terminal pool is live in production.
- `executor.py:893` has `# background is accepted but ignored (Plan C).` — the `background` parameter is accepted but not wired.
- `events.py` has `terminal_spawn`, `terminal_output`, `terminal_complete`, `terminal_block`, `terminal_block_promote`, `terminal_needs_input` factories — the terminal event vocabulary is rich.

### Reference patterns

- `open-claude-code/v2/src/tools/bash.mjs:119-146` — `runBackground`: spawns with `detached: true`, `stdio: ['ignore', 'pipe', 'pipe']`, stores in a `Map`, calls `proc.unref()`, returns immediately with `{ id, pid, command, status }`.
- `warp/crates/warp_tui/src/terminal_use.rs:99-113` — `terminal_use_interrupt_action`: distinguishes agent-controlled vs user-controlled long-running commands, with `TakeControl` vs `InterruptCommand` actions.

### Design questions for the design pass

1. Does `background=true` spawn through `TerminalPool` (PTY-backed, OSC 133 blocks) or a new subprocess path (like open-claude-code's `runBackground`)?
2. What is the lifecycle of a background task? How does it report completion? (The existing `terminal_complete` event carries exit code, duration, output head/tail.)
3. Where does port sniffing live — in `terminal_bridge.py` (stdout stream) or in `SessionManager` (PTY output)?
4. What are the new `StreamEvent` factory signatures for `task_started` and `port_discovered`?

---

## 6. Phase 5: Resizable Stacked Terminal Dock

**Risk**: Medium. Frontend + minor backend.
**Reference patterns**: `warp/crates/warp_tui/src/terminal_use.rs:37-54` (TuiInputTarget: AgentEditor vs Pty ownership).

### 6.1 Emoji Purge in TerminalTile

**File**: `components/agent/TerminalTile.tsx`

Three emoji violations verified at current lines:

- **Line 353**: `{session.visible ? '📌' : '📍'}` — replace with Lucide icons:
```tsx
import { Pin, PinOff, Square, Copy } from 'lucide-react';
// ...
{session.visible ? (
  <Pin className="h-3.5 w-3.5 text-foreground" />
) : (
  <PinOff className="h-3.5 w-3.5 text-muted-foreground" />
)}
```

- **Line 368**: `⏹` — replace with:
```tsx
<Square className="h-3 w-3 fill-current text-status-critical" />
```

- **Line 360**: `⧉` (copy icon) — replace with:
```tsx
<Copy className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
```

- **Line 290/325**: `■` in frozen/running status badges — these are Unicode geometric shapes, not emoji. Verify against the no-emoji rule. If `■` (U+25A0 BLACK SQUARE) is considered an emoji, replace with a styled `<span>` or Lucide icon. The rule in AGENTS.md says "no emoji" — geometric Unicode shapes (`■`, `●`, `○`, `▾`, `▸`, `✓`, `✗`, `⟳`) are used throughout the codebase and are not emoji. Keep them.

**Verify**: Run `scripts/check_literal_colors.py` after changes. All colors must come from `shared-tokens/tokens.css`.

### 6.2 Draggable Resize Handle in TerminalTile

**File**: `components/agent/TerminalTile.tsx:375`

**Current**: `<div ref={containerRef} className="w-full h-48 px-1 py-1" />` (192px fixed).

**Change**: Add stateful height and a drag handle:
```tsx
const [height, setHeight] = useState<number>(240); // default 240px (was 192px)

// ... in the return, before the container div:
<div
  onMouseDown={handleMouseDown}
  className="w-full h-1.5 cursor-row-resize bg-transparent hover:bg-accent/40 active:bg-accent-strong transition-colors border-t border-hairline flex items-center justify-center"
  title="Drag to resize terminal height"
>
  <div className="w-8 h-0.5 rounded-full bg-hairline/60" />
</div>
<div ref={containerRef} className="w-full px-1 py-1" style={{ height: `${height}px` }} />
```

**Drag handler**:
```tsx
const handleMouseDown = (e: React.MouseEvent) => {
  e.preventDefault();
  const startY = e.clientY;
  const startHeight = height;
  const onMove = (ev: MouseEvent) => {
    const delta = startY - ev.clientY; // drag up = taller
    const next = Math.min(600, Math.max(140, startHeight + delta));
    setHeight(next);
    fitRef.current?.fit();
    if (interactive && termRef.current?.cols && termRef.current?.rows) {
      resize(session.id, termRef.current.cols, termRef.current.rows);
    }
  };
  const onUp = () => {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  };
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
};
```

**Constraints**: `minHeight = 140px`, `maxHeight = 600px`. On resize, trigger `fitAddon.fit()` and send terminal resize event via WebSocket to update backend PTY rows/cols.

**Note**: This changes the default height from 192px to 240px. This is a deliberate visual improvement — 192px was too short for useful terminal output.

### 6.3 Stacked Terminal Layout in TasksColumn

**File**: `components/agent/TasksColumn.tsx`

**Current state**: `TaskCard` renders text-only cards (lines 46-111). The comment at lines 34-35 explicitly says "TaskCard does not mount xterms directly... this constant is informational here." No live terminal can be mounted in the side dock.

**Change**: Add an expandable terminal drawer to each running `TaskCard`:

```tsx
// In TaskCard, add expand state
const [expanded, setExpanded] = useState(false);

// In the card's return, after the existing header row:
{expanded && blockId && (
  <TerminalTile
    session={/* look up by blockId from useTerminalSessions */}
    blockId={blockId}
    owner="agent"
  />
)}
```

**Collapsed row** (existing 32px header): StatusLight, command name, elapsed timer, jump button (`↑`), expand chevron (`▾`).

**Expanded state**: Mounts `TerminalTile` with live WebSocket attachment and FitAddon.

**De-duplication rule** (Design Spec section 9.5a): If a terminal block is currently visible inline in the conversation (check `InlineTerminals` / `useTerminalSessions.visible`), the card displays `"live in conversation ↑"` and does NOT mount a duplicate xterm instance.

**Live xterm ceiling**: `MAX_VISIBLE = 3` is already enforced in `useTerminalSessions.ts:92`. The store's `visibleCount()` check (lines 148, 269, 393) prevents mounting more than 3 active xterms. No new enforcement needed — the existing ceiling applies.

### 6.4 TetherChip Correction

The original plan claimed TetherChip is "unclickable." It is not — `TetherChip.tsx:29` implements `onClick`. When an inline terminal scrolls out of view, `InlineTerminals.tsx:33-39` docks it and renders a clickable TetherChip that restores the terminal on click. No change needed here.

---

## 7. Verification Protocol

### 7.1 Automated Tests

```bash
# Frontend type checking and unit tests
npm run typecheck
npm test

# Backend Python test suite (MANDATORY: arch -arm64 prefix)
arch -arm64 .venv/bin/python -m pytest halbert_core/tests

# Design token and contrast gates
python scripts/check_contrast.py
python scripts/check_literal_colors.py
```

### 7.2 Targeted Vitest Assertions

1. **MessageContent.test.tsx**:
   - `# Heading` renders `<h2>`/`<h3>`, not raw `#`.
   - `**bold**` renders `<strong>`.
   - `` `code` `` renders `<code className="...font-mono...">`.
   - Markdown tables render `<table>`, `<thead>`, `<tbody>`.
   - Fenced code blocks still route to `CodeBlock` with staging affordances.

2. **ToolExecutionCard.test.tsx**:
   - Command executions under 2000ms with exit 0 render as compact pills (no bordered card).
   - Non-zero exit codes render as expanded cards with critical status light.
   - Clicking a pill expands it.

3. **TasksColumn.test.tsx**:
   - Terminal rows expand and collapse on clicking the header chevron.
   - Height resize handle updates state between 140px and 600px.
   - `MAX_VISIBLE = 3` ceiling prevents mounting more than 3 active xterms.
   - No emoji glyphs in DOM output (regex `/[\u{1F000}-\u{1FFFF}]|[\u{2600}-\u{27BF}]/u` — note: geometric shapes like `■`, `●`, `▾` are NOT emoji and should pass).

4. **TerminalTile.test.tsx**:
   - No `📌`, `📍`, `⏹` in rendered output.
   - Lucide icons (Pin, PinOff, Square, Copy) render as SVG elements.

### 7.3 Manual End-to-End

1. Run `make dev-web`.
2. Ask: *"What is the status of the zfs pool?"*
   - Verify prose streams directly onto canvas without container box.
   - Verify markdown renders (headers, bold, tables, inline code).
3. Ask: *"Run `git status`"*
   - Verify single-line CLI pill for the short command.
   - Click the pill — verify it expands to show output.
4. Ask: *"Start a simple test web server in the background on port 8765."*
   - Verify task card appears in TasksColumn.
   - Verify expanding the task card mounts a live xterm.
   - Verify the resize handle works (drag between 140px and 600px).
   - Verify no emoji in the terminal tile header (Pin, Copy, Square icons instead).

---

## 8. OSS Reference Patterns

Patterns verified against source code at `/Volumes/Thunderbolt/AI/OSS/`:

| Pattern | Source | Relevance |
|---------|--------|-----------|
| Markdown table parsing | `open-claude-code/v2/src/ui/markdown.mjs:134-152, 251-278` | Phase 1: GFM table detection and column-width calculation |
| Blockquote rendering | `open-claude-code/v2/src/ui/markdown.mjs:202-206` | Phase 1: `>` prefix detection |
| Inline code styling | `open-claude-code/v2/src/ui/markdown.mjs:56` | Phase 1: backtick replacement |
| Unboxed assistant message | `open-claude-code/v2/src/ui/components.mjs:98-104` | Phase 1: AssistantMessage renders markdown directly, no box container |
| Ephemeral tool message | `open-claude-code/v2/src/ui/components.mjs:114-139` | Phase 3: single inline row, truncated result |
| Background job pattern | `open-claude-code/v2/src/tools/bash.mjs:119-146` | Phase 4: detached spawn, Map store, unref, immediate return |
| Thinking section header | `warp/crates/warp_tui/src/agent_block_sections.rs:117-136` | Phase 2: "Thinking..." -> "Thought for {elapsed}", auto-collapse on finish |
| Tool call state glyphs | `warp/crates/warp_tui/src/tool_call_labels.rs:66-97` | Phase 3: ToolCallDisplayState enum, glyph + glyph_style per state |
| Terminal input ownership | `warp/crates/warp_tui/src/terminal_use.rs:37-54` | Phase 5: TuiInputTarget (AgentEditor vs Pty) — who owns input |
| Agent command hiding | `warp/crates/warp_tui/src/terminal_use.rs:16-28` | Phase 5: hide agent-requested commands from top-level transcript |

---

## 9. Standing Directive Compliance

| Directive | Compliance |
|-----------|------------|
| **No model names** | ThinkingPanel and TaskCard show time elapsed, never model name |
| **No Sovereign/hostname** | UI headers use onboarding name |
| **Staged, never executed** | Code blocks stage into composer; port badges open browser tabs |
| **Color system** | All colors from `shared-tokens/tokens.css`; verified via `check_contrast.py` and `check_literal_colors.py` |
| **Emoji ban** | Purge `📌`, `📍`, `⏹` in TerminalTile; replace with Lucide SVG icons |
| **No migrations** | Phase 2 SQLite columns (if built) use idempotent column-exists guard, not a migration framework |
| **Commit hygiene** | No Co-Authored-By, no "Generated with" trailers |
