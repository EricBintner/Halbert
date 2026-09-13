# ARCHITECTURAL IMPLEMENTATION PLAN: Chat UI Modernization — Clean & Simple Executive Canvas

**Document**: `PLAN-CHAT-UI-MODERNIZATION-AND-STACKED-TERMINAL-2026-09-11.md`  
**Date**: 2026-09-11  
**Status**: Ready for Implementation (Verified against codebase merge-base)  
**Authors**: Halbert Core Architecture  
**Scope**: Frontend (`dashboard/frontend/src`), Backend (`dashboard/routes/agent.py`, `streaming/`, `agents/`, `tools/`), Database (`agents/conversation_sqlite.py`)  
**Design Philosophy**: "Clean and simple UI; exhaustive and verbose documentation."  
**Supersedes / Extends**:
- [`STRATEGY-CLI-IN-CONVERSATION-2026-09-04.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/STRATEGY-CLI-IN-CONVERSATION-2026-09-04.md) — incorporates and refines phases T1–T7 (terminal pool, promotion timer, blockId wiring, StatusStrip, InspectionGroup, TasksColumn mount, output truncation) and adds the missing conversation canvas overhaul (unboxed markdown, streaming thinking disclosures).
- [`documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md) (§9.1–§9.9: session quotas, tile=block/card=task hierarchy, OSC 133 byte protocol, StatusLight 5-state specification, and watched user shell semantics).
- [`.handoff/oss-pass-2/section_terminal-tools-subagents.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/oss-pass-2/section_terminal-tools-subagents.md) (96 verified mechanisms across Themes A–E: shell executor, watched terminal, background process registry, command classifier, and tool-loop guardrails).

---

## 1. Executive Summary & Core Philosophy

Halbert is not a chatbot widget; it is an executive operating environment where the conversation is the primary surface of the computer.

Three non-negotiable standing directives from [`DECISIONS.md`](file:///Volumes/4TB-BAD/Halbert/DECISIONS.md) govern this surface:
1. *"The conversation is the core layer; the dashboard runs under the hood"* ([`DECISIONS.md:10`](file:///Volumes/4TB-BAD/Halbert/DECISIONS.md#L10)).
2. *"The system speaks as the computer itself, in first person, grounded in measured data — never as an assistant"* ([`DECISIONS.md:9`](file:///Volumes/4TB-BAD/Halbert/DECISIONS.md#L9)).
3. *"One seamless conversation with hidden topic threads; no conversation list; commands from the UI are staged, never executed"* ([`DECISIONS.md:13`](file:///Volumes/4TB-BAD/Halbert/DECISIONS.md#L13)).

### The UX Goal: "Clean and Simple"
The user experience must feel completely unburdened:
- **No visual claustrophobia**: Prose flows directly on the background canvas like an open technical memo, not trapped in chat bubble cards.
- **Whisper-quiet tool runs**: Routine inspections and 100ms commands take up a single 24px hairline pill that disappears into the background unless there is an error.
- **Calm thinking disclosures**: Deep chain-of-thought does not explode into giant tinted boxes with ASCII arrows; it streams behind a hairline border with a quiet elapsed counter and automatically folds away when the answer begins.
- **Effortless background monitoring**: Servers and long jobs run cleanly in the background, surfacing a tiny localhost port chip (`8000 ↗`) and a subtle StatusLight without hijacking the conversational flow.
- **Organized workspace**: The side dock stacks terminal drawers with smooth resizing handles, strictly adhering to tokenized colors with zero emoji distractions.

---

## 2. Visual Architecture & Design Principles (Clean & Simple UI)

### 2.1 Before vs. After: The Visual Experience

#### A. Assistant Prose & Markdown Canvas
```
BEFORE (Chatbot Bubble Regression):
┌────────────────────────────────────────────────────────────────────────┐
│ [User Bubble] "What is the status of the zfs pool?"                    │
│                                                                        │
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │ 🤖 [Assistant Box: max-w-[85%] bg-muted/50 border rounded-lg p-4]  │ │
│ │                                                                    │ │
│ │  ### Pool Status                                                   │ │ <- Raw text!
│ │  **tank** is healthy.                                              │ │ <- Raw asterisks!
│ │  - Read: 0 errors                                                  │ │ <- Raw hyphens!
│ │  - Write: 0 errors                                                 │ │
│ └────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘

AFTER (Clean Unboxed Executive Canvas):
──────────────────────────────────────────────────────────────────────────
                                     ┌───────────────────────────────────┐
                                     │ What is the status of the zfs pool?│
                                     └───────────────────────────────────┘

Pool Status
tank is currently healthy with 0 read and 0 write errors recorded.

  Pool        State      Read Errors    Write Errors    CKsum Errors
  ──────────  ─────────  ─────────────  ──────────────  ────────────
  tank        ONLINE     0              0               0
  mirror-0    ONLINE     0              0               0

All scrub operations completed nominally within the last 14 hours.
──────────────────────────────────────────────────────────────────────────
```

#### B. Thinking Disclosure
```
BEFORE:
┌────────────────────────────────────────────────────────────────────┐
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │ [Bordered Card: border rounded-lg bg-muted]                    │ │
│ │ Thinking Process                                             ▲ │ │
│ │────────────────────────────────────────────────────────────────│ │
│ │ Let me check the zfs status by querying zpool status...        │ │
│ │ Looking at vdev health and scrub completion timestamps...      │ │
│ └────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘

AFTER (Quiet, Borderless, Auto-Collapsing):
Streaming:
  ⟳ Thinking (3.4s)...

Finished (Auto-Collapsed):
  Thought for 4.2s ▾

Expanded (Hairline Left Accent):
  Thought for 4.2s ▴
  │ Checking zpool status for pool 'tank'...
  │ Verified error counters are 0 across mirror-0 and mirror-1.
  │ Formatting response table with measured scrub completion data.
```

#### C. Short CLI Commands (<2s, Exit 0)
```
BEFORE (Loud 120px+ Box for a 100ms Command):
┌────────────────────────────────────────────────────────────────────┐
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │ [ToolExecutionCard: border bg-muted/30 rounded-lg p-3]         │ │
│ │ [StatusLight: Green] run_command                               │ │
│ │ Arguments:                                                     │ │
│ │   command: "zpool status -x"                                   │ │
│ │ Output:                                                        │ │
│ │   all pools are healthy                                        │ │
│ └────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘

AFTER (Clean 24px Ephemeral Pill):
  ● $ zpool status -x · 0.08s · exit 0  ▾
  
  (Click expands into a quiet hairline drawer showing stdout/stderr)
  
IF ERROR (Auto-Expands immediately with clear diagnostics):
  ✕ $ zpool status -x · exit 1 · 0.12s  ▴
  ┌────────────────────────────────────────────────────────────────┐
  │ zpool: command not found in PATH (/usr/local/bin:/usr/bin)     │
  └────────────────────────────────────────────────────────────────┘
```

#### D. Long-Running Processes & Localhost Port Badges
```
AFTER (Clean Background Task Row):
  ● npm run dev · 12.4s · PID 49120 · [ 8000 ↗ ] · [ Stop ] [ Jump ⤴ ]
```

#### E. Stacked Terminal Dock (Tasks Column)
```
┌─ Tasks ──────────────────────────────────────────────────┐
│ RUNNING                                                  │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ ● npm run dev · 8000 ↗                        [ ▴ ]  │ │
│ │──────────────────────────────────────────────────────│ │
│ │ VITE v5.4.14 ready in 240 ms                         │ │
│ │ ➜ Local:   http://localhost:8000/                    │ │
│ │ ➜ Network: use --host to expose                      │ │
│ │ ═ Drag handle to resize (140px - 600px) ═══════════  │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                          │
│ FINISHED (1) ▾                                           │
│   ✓ git status · 0.1s                                    │
│                                                          │
│ ┌─ Your Shell ─────────────────────────────────────────┐ │
│ │ [ Open an administrative shell ]                     │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## 3. Comprehensive Benchmark Analysis

### 3.1 open-claude-code (`/Volumes/Thunderbolt/AI/OSS/open-claude-code`)
- **Unboxed Stream Processing** ([`v2/src/ui/app.mjs:104-135`](file:///Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src/ui/app.mjs#L104-L135)):
  - The CLI event loop receives chunks via SSE and dispatches to Ink components.
  - Text updates in place inside `AssistantMessage` without wrapping in boxes or bounding borders.
  - Full ANSI markdown parsing via [`v2/src/ui/markdown.mjs`](file:///Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src/ui/markdown.mjs) handles bold, headers, tables, and fenced code.
- **Thinking Indicator** ([`v2/src/ui/components.mjs:141-146`](file:///Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src/ui/components.mjs#L141-L146)):
  - Renders `ThinkingMessage` as dim italic text with a subtle spinner, occupying minimal vertical space and collapsing upon completion.
- **Ephemeral Tool Messages** ([`v2/src/ui/components.mjs:114-139`](file:///Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src/ui/components.mjs#L114-L139)):
  - Renders `[tool_name] running...` → `[tool_name] (result truncated 200)` as a single inline text row.
- **Detached Background Execution** ([`v2/src/tools/bash.mjs:42-44, 120-146`](file:///Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src/tools/bash.mjs#L42-L44)):
  - Implements `run_in_background: true`. When enabled, the tool spawns the child process with `stdio: ['ignore', 'pipe', 'pipe']`, records it in an internal `backgroundJobs` Map (`{ id, pid, command, status, stdout, stderr }`), calls `proc.unref()`, and immediately returns `{ status: 'background', job_id, pid }`.

### 3.2 Warp (`/Volumes/Thunderbolt/AI/OSS/warp`)
- **Thinking Section Architecture** ([`crates/warp_tui/src/agent_block_sections.rs:116-189`](file:///Volumes/Thunderbolt/AI/OSS/warp/crates/warp_tui/src/agent_block_sections.rs#L116-L189)):
  - Renders `render_thinking_section` with a dynamic header: `"Thinking..."` while streaming, transforming to `"Thought for {elapsed}"` on finish.
  - Defaults to collapsed when `finished == true`.
  - Body is styled cleanly without bounding cards, indented with a single blank separator row.
- **Tool Call Labels** ([`crates/warp_tui/src/agent_block_sections.rs:76-114`](file:///Volumes/Thunderbolt/AI/OSS/warp/crates/warp_tui/src/agent_block_sections.rs#L76-L114)):
  - Uses a 2-cell status glyph gutter (`✓`, `⟳`, `✗`) with status-tinted color, followed by styled label spans with hanging indents.
- **Terminal Input Ownership Policy** ([`crates/warp_tui/src/terminal_use.rs:11-28, 99-150`](file:///Volumes/Thunderbolt/AI/OSS/warp/crates/warp_tui/src/terminal_use.rs#L11-L28)):
  - Implements `TuiInputTarget` switching between `AgentEditor` and `Pty`.
  - Hides agent-requested commands from the top-level transcript (`hide_agent_requested_command_from_top_level`), embedding them inside collapsible disclosures.
  - Distinguishes between fast commands and active long-running commands (`is_active_and_long_running()`).

### 3.3 Antigravity & Claude Desktop
- **Canvas Flow**: Full document width, zero card containers around prose, high-contrast readable typography.
- **Hairline Thinking Panels**: Clean left-accent line, mono timing metrics, auto-collapse upon receiving response tokens.
- **Pill Tool Results**: Micro-badges showing command name, execution duration, and exit status.
- **Localhost Port Chips**: Detected HTTP ports render as clickable chips (`8000 ↗`) that open directly in the browser.

---

## 4. Current Architectural Analysis & Defect Inventory

Every line number and symbol in this inventory has been verified directly against the codebase merge-base.

### Defect 1: Assistant Turn Boxed Container Look
- **Locations**:
  - [`Timeline.tsx:416-417`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.tsx#L416-L417)
  - [`AgentChat.tsx:1088-1089`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx#L1088-L1089)
- **Current Code**:
  ```tsx
  <div className="flex justify-start">
    <div className="max-w-[85%] bg-muted/50 border border-border/50 rounded-lg p-4 space-y-3">
  ```
- **Root Cause**: The assistant turn is styled like an incoming SMS or chat bubble from a legacy chat widget.
- **Impact**: Constrains the reading width to 85%, creates heavy visual borders, and breaks the feeling of the computer speaking as an open operating environment.

### Defect 2: Raw Markdown Rendering Failure
- **Locations**:
  - [`MessageContent.tsx:23-48, 71-73`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/MessageContent.tsx#L23-L48)
  - [`MarkdownRenderer.tsx:87-89`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/domain/MarkdownRenderer.tsx#L87-L89)
- **Current Code in `MessageContent.tsx`**:
  ```tsx
  return (
    <span key={i} className="whitespace-pre-wrap break-words">{part.content}</span>
  );
  ```
- **Root Cause**: `MessageContent.tsx` only parses triple-backtick fences via `splitFences()`. All non-code text is rendered into a raw `<span>`. The existing [`MarkdownRenderer.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/domain/MarkdownRenderer.tsx) (185 lines) is imported by `Network.tsx`, `Services.tsx`, `AIAnalysisPanel.tsx`, and `ComponentLibraryViewer.tsx`, but is **completely bypassed** by the chat pipeline!
- **Additional Flaws in `MarkdownRenderer.tsx`**:
  - Lines 87–89 contain active debug statements: `console.log('[MarkdownRenderer] Input text (first 500 chars):'...)`.
  - Lacks support for inline code chips (`` `foo` ``), GFM tables (`| a | b |`), and blockquotes (`> quote`).

### Defect 3: Discarded & Disconnected Thinking Pipeline
- **Locations**:
  - Backend streaming: [`dashboard/routes/agent.py:1462-1502`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/agent.py#L1462-L1502) (discard loop at 1466–1495)
  - Reasoning parser: [`utils/reasoning.py:138-247`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/utils/reasoning.py#L138-L247)
  - UI component: [`ThinkingPanel.tsx:46, 51, 64`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/ThinkingPanel.tsx#L46)
  - Timeline types: [`types/timeline.ts:73-84`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/types/timeline.ts#L73-L84)
  - Message persistence: [`agents/conversation_sqlite.py:258-274`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/conversation_sqlite.py#L258-L274)
- **Current Behavior**:
  - `agent.py` accumulates streaming `<think>` tokens into a buffer and **discards** them when `</think>` is reached.
  - `ThinkingPanel.tsx` renders a bordered card (`border rounded-lg overflow-hidden` at line 46, `bg-muted` at line 51, text arrows `▲`/`▼` at line 64).
  - `TimelineTurn` in `types/timeline.ts` does not have `thinking` or `thinkingDuration` fields.
  - `conversation_sqlite.py` `messages` table schema has no thinking columns. Thinking disappears completely on page reload.

### Defect 4: Noisy, Bloated Tool Execution Cards
- **Locations**:
  - [`ToolExecutionCard.tsx:57-134, 159-288`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/ToolExecutionCard.tsx#L57-L134)
- **Current Behavior**:
  - Renders a full status card (`rounded-lg border`, background fill, tool name, argument pre-blocks, output blocks) for every command.
  - Even a 50ms `git status` or `cat` command occupies 120px+ of vertical height.
  - While `blockId` is accepted as an optional prop (line 75), **no caller in `Timeline.tsx` or `AgentChat.tsx` passes it**!

### Defect 5: Disconnected Stacked Terminal & No Resizing Affordance
- **Locations**:
  - Accordion dock deletion: Commit `4a862fee`
  - Tasks column: [`TasksColumn.tsx:34-35, 126-210`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/TasksColumn.tsx#L34-L35)
  - Terminal tile: [`TerminalTile.tsx:353, 368, 375`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.tsx#L353)
  - Inline terminals: [`InlineTerminals.tsx:31-39`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/InlineTerminals.tsx#L31-L39)
  - Context stage: [`ContextStage.tsx:84-91`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/shell/ContextStage.tsx#L84-L91)
- **Current Behavior**:
  - `TasksColumn.tsx` only renders text cards (`TaskCard`), explicitly noting at lines 34–35: *"TaskCard does not mount xterms directly... this constant is informational here."* No live terminal can be mounted in the side dock!
  - `TerminalTile.tsx:375` has a hardcoded height: `className="w-full h-48 px-1 py-1"` (192px) with no resize handle.
  - `TerminalTile.tsx` contains banned emojis: `📌`/`📍` (line 353) and `⏹` (line 368), violating the strict no-emoji invariant in `AGENTS.md`.
  - When an inline terminal scrolls out of viewport, `InlineTerminals.tsx` hides it completely via `setVisible(session.id, false)` and renders an unclickable text chip (`TetherChip`).

---

## 5. Detailed Implementation Phases

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HALBERT CHAT UI REVISION                           │
└─────────────────────────────────────────────────────────────────────────────┘
  │
  ├── PHASE 1: UNBOXED CANVAS & RICH MARKDOWN (Frontend Only, Low Risk)
  │    ├── Unbox assistant prose in Timeline.tsx & AgentChat.tsx
  │    ├── Remove debug console.log from MarkdownRenderer.tsx
  │    ├── Add inline code chips, GFM tables, and blockquotes to MarkdownRenderer
  │    └── Wire MarkdownRenderer into MessageContent.tsx (preserve CodeBlock staging)
  │
  ├── PHASE 2: BORDERLESS STREAMING THINKING (Frontend + Backend, Medium Risk)
  │    ├── Rewire routes/agent.py SSE pump to emit StreamEvent.thinking
  │    ├── Wire StreamingReasoningParser across model streaming paths
  │    ├── Redesign ThinkingPanel.tsx: borderless, live timer, auto-collapse
  │    ├── Add thinking_content and thinking_duration_ms to conversation_sqlite.py
  │    └── Persist thinking on TimelineTurn in types/timeline.ts and threads.py
  │
  ├── PHASE 3: EPHEMERAL 1-LINE CLI PILLS (Frontend Only, Low Risk)
  │    ├── Render fast (<2s, exit 0) commands as 24px pills in ToolExecutionCard.tsx
  │    ├── Auto-expand failures (exit != 0) with clear diagnostic error borders
  │    └── Retain InspectionGroup.tsx for batch inspection pills
  │
  ├── PHASE 4: BACKGROUND PROCESSES & LOCALHOST PORT SNIFFING (Backend Heavy, High Risk)
  │    ├── Wire background=true in tools/executor.py:893 via ProcessRegistry
  │    ├── Enable terminal pool in production (set_terminal_pool_enabled(True))
  │    ├── Sniff stdout in terminal_bridge.py for localhost/127.0.0.1 ports
  │    └── Render interactive [ 8000 ↗ ] port chips and process lifecycle controls
  │
  └── PHASE 5: RESIZABLE STACKED TERMINAL DOCK (Frontend + Backend, Medium Risk)
       ├── Resurrect collapsible stacked terminals in TasksColumn.tsx
       ├── Enforce MAX_VISIBLE = 3 live xterm ceiling via useTerminalSessions.ts
       ├── Add draggable bottom resize handle (140px-600px) in TerminalTile.tsx
       └── Purge forbidden emojis (📌, 📍, ⏹) -> Lucide SVG icons (Pin, Copy, Square)
```

---

### Phase 1: Unboxed Canvas & Rich Markdown System

#### 1. Strip Assistant Container Cards
- **Files**:
  - [`Timeline.tsx:416-417`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.tsx#L416-L417)
  - [`AgentChat.tsx:1088-1089`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx#L1088-L1089)
- **Target Replacement**:
  - Replace:
    ```tsx
    <div className="flex justify-start">
      <div className="max-w-[85%] bg-muted/50 border border-border/50 rounded-lg p-4 space-y-3">
    ```
  - With:
    ```tsx
    <div className="flex justify-start w-full">
      <div className="w-full space-y-3 text-foreground leading-relaxed">
    ```
- **User Message Contrast**:
  - Maintain clear differentiation for user turns: keep right-aligned subtle surface bubble (`bg-surface border border-hairline rounded-lg px-4 py-2.5 max-w-[80%]`).

#### 2. Upgrade `MarkdownRenderer.tsx` & Clean Debug Logs
- **File**: [`components/domain/MarkdownRenderer.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/domain/MarkdownRenderer.tsx)
- **Cleanups**:
  - Delete lines 87–89 (`console.log('[MarkdownRenderer] Input text...'...)`).
- **Feature Enhancements**:
  - **Inline Code**:
    ```tsx
    // Replace `foo` with styled token code chip
    formatted = formatted.replace(
      /`([^`]+)`/g,
      '<code class="px-1.5 py-0.5 rounded bg-muted/80 font-mono text-[12px] text-foreground border border-hairline/60">$1</code>'
    );
    ```
  - **GFM Tables**:
    - Add detection for markdown tables (`| col1 | col2 |`).
    - Render with semantic `<table>`, `<thead>`, `<tbody>`, styled with `w-full border-collapse border border-hairline text-sm`, alternating row tints, and proper padding.
  - **Blockquotes**:
    - Parse lines starting with `> ` into `<blockquote className="border-l-2 border-hairline pl-3 my-2 text-muted-foreground italic">`.
- **Consumer Safeguard**: Ensure changes are backward-compatible with existing consumers (`Network.tsx`, `Services.tsx`, `AIAnalysisPanel.tsx`, `ComponentLibraryViewer.tsx`).

#### 3. Wire `MarkdownRenderer` into `MessageContent.tsx`
- **File**: [`components/agent/MessageContent.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/MessageContent.tsx)
- **Change**:
  - In `MessageContent.tsx`, replace the raw `<span>` fallback (lines 71–73) with `<MarkdownRenderer content={part.content} />`.
  - Keep `splitFences()` for extracting ```` ``` ```` fenced code blocks so that executable CLI blocks still render via `CodeBlock` with staging affordances.

---

### Phase 2: Borderless Streaming Thinking Pipeline & Persistence

#### 1. Backend Think-Tag Stream Pipeline
- **Files**:
  - [`dashboard/routes/agent.py:1462-1502`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/agent.py#L1462-L1502)
  - [`agents/events.py:23-48`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/events.py#L23-L48)
  - [`utils/reasoning.py:138-247`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/utils/reasoning.py#L138-L247)
- **Modifications**:
  - In `routes/agent.py`, replace the discard logic in `_stream_turn` with:
    ```python
    # When in_think_block is True, extract chunk and yield thinking event
    if in_think_block:
        yield StreamEvent.thinking(session_id, thinking_chunk).to_sse()
    ```
  - Use `StreamingReasoningParser` from `utils/reasoning.py` to handle all supported tags (`<think>`, `<thinking>`, `<reasoning>`, `<thought>`).
  - Calculate `thinking_duration_ms` from start to closing tag.

#### 2. Redesign `ThinkingPanel.tsx` (Clean, Borderless Disclosure)
- **File**: [`components/agent/ThinkingPanel.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/ThinkingPanel.tsx)
- **Design Specifications**:
  - Remove outer `border rounded-lg overflow-hidden` (line 46) and `bg-muted` header (line 51).
  - **In-flight**:
    - Subtle pulsing dot (`h-1.5 w-1.5 rounded-full bg-accent-strong animate-pulse`).
    - Text: `Thinking (${elapsedSeconds}s)...` in `text-xs text-muted-foreground font-mono`.
  - **Completed**:
    - Auto-collapse when response tokens arrive.
    - Summary label: `Thought for ${durationSeconds}s ▾` (clickable button).
  - **Expanded Content**:
    - Borderless, indented left-hairline container: `border-l-2 border-hairline pl-3 py-1 my-2 text-xs font-mono text-muted-foreground whitespace-pre-wrap leading-relaxed`.
  - **Standing Directive Guard**: Do NOT display model name anywhere in `ThinkingPanel`.

#### 3. Conversation Thinking Persistence
- **Files**:
  - [`agents/conversation_sqlite.py:258-274`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/conversation_sqlite.py#L258-L274)
  - [`types/timeline.ts:73-84`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/types/timeline.ts#L73-L84)
  - [`agents/threads.py:449`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/threads.py#L449)
- **Database Schema**:
  - Under standing directive ("no users yet — do not build migrations unasked"), execute direct column additions with `NULL` defaults:
    ```sql
    ALTER TABLE messages ADD COLUMN thinking_content TEXT;
    ALTER TABLE messages ADD COLUMN thinking_duration_ms INTEGER;
    ```
- **Timeline Turn Interface**:
  - Add to `TimelineTurn` in `types/timeline.ts`:
    ```ts
    thinking?: string;
    thinkingDuration?: number;
    ```
  - When loading past turns in `Timeline.tsx`, render the thinking disclosure in its collapsed state (`Thought for 12s ▾`).

---

### Phase 3: Ephemeral 1-Line CLI Commands

#### 1. Compact 1-Line Result Pill
- **File**: [`components/agent/ToolExecutionCard.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/ToolExecutionCard.tsx)
- **Condition for 1-Line Pill**:
  - `isCommandBlock === true && execution.status === 'success' && (execution.duration ?? 0) < 2000`
- **Render Markup**:
  ```tsx
  <div className="flex items-center gap-2 py-1 px-2.5 rounded border border-hairline bg-surface/50 text-xs font-mono hover:bg-surface cursor-pointer select-none transition-colors">
    <StatusLight state="done_unseen" />
    <span className="text-muted-foreground">$</span>
    <span className="text-foreground truncate max-w-[400px]">{commandStr}</span>
    <span className="text-hairline">·</span>
    <span className="text-muted-foreground">{durationStr}</span>
    <span className="text-hairline">·</span>
    <span className="text-muted-foreground">exit 0</span>
    <ChevronDown className={`h-3 w-3 ml-auto transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
  </div>
  ```
- **Error Condition**:
  - If `execution.status === 'error'` or exit code is non-zero:
    - Set `StatusLight state="error"`.
    - **Auto-expand** the error disclosure immediately with critical border tint (`border-status-critical/40`).

#### 2. Wiring `blockId` from SSE Events
- **Context**: As documented in `.handoff/STRATEGY-CLI-IN-CONVERSATION-2026-09-04.md`, `ToolExecutionCard` currently accepts `blockId` (line 75) but no caller passes it.
- **Change**: Pass `item.blockId` from `TimelineToolBlock` into `ToolExecutionCard` so that clicking the jump button or promoting the card establishes somatic linkage to the terminal session.

#### 3. Strengthen `InspectionGroup.tsx`
- **File**: [`components/agent/InspectionGroup.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/InspectionGroup.tsx)
- **Behavior**:
  - Continue grouping runs of read-only tools (`read_file`, `grep_search`, `recall_memory`) into quiet collapsed pills (`Looked at 3 files · 2 memories`).
  - Retain Unicode geometric arrows `▾`/`▸` (line 51) which are fully compliant with the no-emoji rule.

---

### Phase 4: Long-Running CLI & Localhost Port Management

#### 1. True Background Process Execution
- **Files**:
  - [`tools/executor.py:890-895`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/tools/executor.py#L890-L895)
  - [`streaming/agent_pool.py:1-419`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/streaming/agent_pool.py)
- **Current Defect**:
  - `executor.py:893` has comment: `# background is accepted but ignored (Plan C).`
- **Implementation**:
  - Wire `background=true` in `run_command` via `ProcessRegistry`.
  - Enable `TerminalPool` in production: wire `set_terminal_pool_enabled(True)` in the application startup path (`halbert_core/main.py` / `dashboard/app.py`).
  - When `background=true` is requested (or execution surpasses `PROMOTE_AFTER_SECONDS = 2.0`):
    - Spawn a detached PTY process via `TerminalPool`.
    - Emit `StreamEvent.task_started(session_id, task_id, command)`.
    - Return execution immediately with `task_id` and block descriptor.

#### 2. Localhost Port Detection
- **Files**:
  - [`streaming/terminal_bridge.py:1-155`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/streaming/terminal_bridge.py)
  - [`hooks/useTerminalSessions.ts:1-465`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/hooks/useTerminalSessions.ts)
- **Implementation**:
  - In `terminal_bridge.py`, sniff the stdout byte stream with regex:
    ```python
    PORT_PATTERN = re.compile(r'(?:https?://)?(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(\d{2,5})')
    ```
  - When detected, emit `StreamEvent.port_discovered(task_id, port, protocol)`.
  - In `useTerminalSessions.ts`, store `listeningPort` on the block/session.
  - Render an interactive port badge:
    ```tsx
    <a
      href={`http://localhost:${session.listeningPort}`}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-accent/15 border border-accent-strong/40 text-[11px] font-mono text-accent-strong hover:bg-accent/25 transition-colors"
    >
      <span>{session.listeningPort}</span>
      <ExternalLink className="h-2.5 w-2.5" />
    </a>
    ```
  - Clicking opens the browser tab directly — staged, no command executed on the server.

#### 3. Process Lifecycle Controls
- Provide immediate controls on task cards and terminal headers:
  - **Stop**: Graceful `SIGINT` (Ctrl+C), escalating to `SIGTERM` after 3s.
  - **Copy**: Copy captured scrollback buffer to clipboard.
  - **Jump**: Scroll conversation timeline back to the initiating turn.

---

### Phase 5: Resizable Stacked Terminal Dock

#### 1. Stacked Terminal Layout in `TasksColumn.tsx`
- **Files**:
  - [`components/agent/TasksColumn.tsx:1-213`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/TasksColumn.tsx)
  - [`hooks/useTasks.ts:1-99`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/hooks/useTasks.ts)
  - [`components/shell/ContextStage.tsx:84-91`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/shell/ContextStage.tsx#L84-L91)
- **Data Plumbing**:
  - `useTasks.ts` already filters sessions into `{ running, finished }` and assigns `StatusLightState`.
  - `TasksColumn.tsx` will now render expandable terminal drawers for each running task:
    - **Collapsed row (32px)**: StatusLight, command name, listening port badge (`8000 ↗`), elapsed timer, jump button (`⤴`), expand chevron (`▾`).
    - **Expanded state**: Mounts `TerminalTile` with live WebSocket attachment and FitAddon.
  - **De-Duplication Rule** (Design Spec §9.5a):
    - If a terminal block is currently visible inline in the conversation, the card in `TasksColumn` displays `"live in conversation ⤴"` and does NOT mount a duplicate xterm instance.
  - **Live xterm Ceiling**: Enforce `MAX_VISIBLE = 3` via `useTerminalSessions.ts`.

#### 2. Interactive Drag Resize Handle in `TerminalTile.tsx`
- **File**: [`components/agent/TerminalTile.tsx:1-379`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.tsx)
- **Resize Implementation**:
  - Replace hardcoded `className="w-full h-48 px-1 py-1"` (line 375) with stateful height:
    ```tsx
    const [height, setHeight] = useState<number>(240); // default 240px
    ```
  - Add a bottom drag handle:
    ```tsx
    <div
      onMouseDown={handleMouseDown}
      className="w-full h-1.5 cursor-row-resize bg-transparent hover:bg-accent/40 active:bg-accent-strong transition-colors border-b border-hairline flex items-center justify-center"
      title="Drag to resize terminal height"
    >
      <div className="w-8 h-0.5 rounded-full bg-hairline/60" />
    </div>
    ```
  - Constraints: `minHeight = 140px`, `maxHeight = 600px`.
  - On mouse drag: update height state, trigger `fitAddon.fit()`, and send terminal resize event via WebSocket to update backend PTY rows/cols.

#### 3. Strict Token & Icon Compliance (Emoji Purge)
- **File**: [`components/agent/TerminalTile.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.tsx)
- **Purge Violations**:
  - Line 353: Replace `{session.visible ? '📌' : '📍'}` with:
    ```tsx
    {session.visible ? (
      <Pin className="h-3.5 w-3.5 text-foreground" />
    ) : (
      <PinOff className="h-3.5 w-3.5 text-muted-foreground" />
    )}
    ```
  - Line 368: Replace literal `⏹` emoji with:
    ```tsx
    <Square className="h-3 w-3 fill-current text-status-critical" />
    ```
  - Copy action: Replace with `<Copy className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />`.
  - All colors mapped to `var(--color-...)` tokens from `tokens.css`.

---

## 6. Data Contracts, Schemas & Event Payloads

### 6.1 Server-Sent Events (SSE) Specifications

#### A. Thinking Event
```json
{
  "event": "stream_event",
  "data": {
    "type": "thinking",
    "session_id": "sess-9a20ceb6",
    "timestamp": 1726048123456,
    "data": {
      "chunk": "Checking active zfs vdevs in /etc/zfs...",
      "duration_ms": 1240
    }
  }
}
```

#### B. Task Started Event
```json
{
  "event": "stream_event",
  "data": {
    "type": "task_started",
    "session_id": "sess-9a20ceb6",
    "timestamp": 1726048124000,
    "data": {
      "task_id": "task-49120",
      "command": "npm run dev",
      "cwd": "/Volumes/4TB-BAD/Halbert",
      "is_background": true
    }
  }
}
```

#### C. Port Discovered Event
```json
{
  "event": "stream_event",
  "data": {
    "type": "port_discovered",
    "session_id": "sess-9a20ceb6",
    "timestamp": 1726048124800,
    "data": {
      "task_id": "task-49120",
      "port": 8000,
      "protocol": "http",
      "url": "http://localhost:8000"
    }
  }
}
```

### 6.2 SQLite Storage Contract (`messages` Table)
```sql
ALTER TABLE messages ADD COLUMN thinking_content TEXT;
ALTER TABLE messages ADD COLUMN thinking_duration_ms INTEGER;
```

---

## 7. Edge Cases, Race Conditions & Failure Modes

1. **Streaming Interruption / Network Drop**:
   - If an SSE stream disconnects while `<think>` is open: `StreamingReasoningParser.finalize()` closes the block and emits partial thinking so far.
2. **Alt-Screen PTY Applications (`htop`, `vim`, `less`)**:
   - OSC 133 byte parser in `agent_pool.py` detects alt-screen sequence `\e[?1049h`.
   - The card automatically marks `isInteractive = true` and promotes to a dedicated live terminal tile rather than a 1-line pill.
3. **Password / Sudo Prompts**:
   - Detected via `needs_input` pattern. StatusLight transitions immediately to `--color-status-warning` (`needs_attention`) and plays a subtle alert chime.
4. **Scroll Jitter & Docking Loops**:
   - `InlineTerminals.tsx:33-39` intersection docking is strictly one-way (`docked` state never flips back to false on upward scroll).
5. **Multiple Concurrent Localhost Ports**:
   - Sniffer collects unique ports into a set (`Set<number>`). If Vite outputs `http://localhost:8000` and `http://localhost:8001`, both render as chips: `[ 8000 ↗ ]` `[ 8001 ↗ ]`.
6. **Background Task Retention & Pruning**:
   - Finished background tasks retain for 10 minutes, after which `TasksColumn.tsx` folds them into `Finished (N) ▾` with a `Clear` button.

---

## 8. Standing Directives & Governance Checklist

Every implementation step must strictly verify compliance against [`DECISIONS.md`](file:///Volumes/4TB-BAD/Halbert/DECISIONS.md) and [`AGENTS.md`](file:///Volumes/4TB-BAD/Halbert/AGENTS.md):

| Directive | Governance Rule | Compliance Check |
|---|---|---|
| **Identity** | System speaks as the computer in first person, grounded in measured data; never as an assistant. | Verify no "I am your AI assistant" in default prompts or UI labels. |
| **No Model Names** | Never name or recommend an AI model on any user-facing surface. Connection slots, not model menus. | Verify `ThinkingPanel` and `TaskCard` display time elapsed ("Thought for 8s"), NEVER model name ("Claude 3.7", "Gemini", etc.). |
| **No Sovereign / Hostname** | Engaged surface carries the onboarding `ai_name`, never raw hostname or "Sovereign". | Checked in UI headers. |
| **Staged, Never Executed** | Commands from UI are staged into composer or user shell, never executed on click. | Click on code blocks stages text into input; port badges open browser tabs. |
| **Color System** | `shared-tokens/tokens.css` is the single palette. Never hardcode colors. | Validated via `scripts/check_contrast.py` and `scripts/check_literal_colors.py`. |
| **Emoji Ban** | No emoji anywhere in the UI. | Purged `📌`, `📍`, `⏹` in `TerminalTile.tsx`. Replaced with Lucide SVG icons. |
| **No Migrations** | No users yet — do not build migrations or back-compat shims unasked. Leave superseded data on disk. | Added columns via direct `ALTER TABLE` with `NULL` defaults; no migration framework. |
| **Commit Hygiene** | Never add `Co-Authored-By`, "Generated with...", or bot-attribution trailers. | Subject and body only. |

---

## 9. Phase Sequencing, Risk Matrix & Rollout Strategy

```
Phase 1  ──→  Phase 2  ──→  Phase 3  ──→  Phase 4  ──→  Phase 5
 (FE only)    (FE + BE)     (FE only)     (BE heavy)     (FE + BE)
```

| Phase | Scope | Risk | Dependents & Dependencies | Rollout Recommendation |
|---|---|---|---|---|
| **Phase 1: Unboxed Canvas** | Frontend | **Low** | Unblocks visual modernization; standalone | **Ship 1st**: Immediate visual leap, zero backend risk. |
| **Phase 2: Borderless Thinking** | Fullstack | **Medium** | Touches `agent.py` streaming pump & `conversation_sqlite.py` | **Ship 2nd**: `StreamingReasoningParser` already exists; clean pipeline upgrade. |
| **Phase 3: Ephemeral CLI** | Frontend | **Low** | Requires Phase 1 canvas; operates independently of backend blockId | **Ship 3rd**: Turns noisy 120px boxes into sleek 24px pills. |
| **Phase 4: Background CLI & Ports** | Backend Heavy | **High** | TerminalPool enablement; PTY stream sniffing; process lifecycle | **Ship 4th**: Riskiest phase; requires deep integration testing. |
| **Phase 5: Resizable Terminal Dock** | Fullstack | **Medium** | Depends on Phase 4 pool; upgrades `TasksColumn` & `TerminalTile` | **Ship 5th**: Delivers the interactive stacked terminal drawer experience. |

---

## 10. Comprehensive Verification & Testing Protocol

### 10.1 Automated Test Invocations

```bash
# 1. Frontend type checking and unit test suite
npm run typecheck
npm test

# 2. Backend Python test suite (MANDATORY: prefix with arch -arm64 on macOS)
arch -arm64 .venv/bin/python -m pytest halbert_core/tests

# 3. Design token and contrast gates
python scripts/check_contrast.py
python scripts/check_literal_colors.py
```

### 10.2 Targeted Vitest Unit Assertions

1. `MessageContent.test.tsx`:
   - Assert `# Heading` renders semantic `<h1>`/`<h2>` tags, not raw `#`.
   - Assert `**bold**` renders `<strong>`.
   - Assert `` `code` `` renders `<code className="...font-mono...">`.
   - Assert markdown tables render semantic `<table>`, `<thead>`, `<tbody>`.
   - Assert fenced code blocks still pass through to `CodeBlock` with staging affordances.
2. `ThinkingPanel.test.tsx`:
   - Assert outer div has no card borders or `bg-muted` background box.
   - Assert live elapsed timer increments while `isStreaming === true`.
   - Assert panel auto-collapses to `Thought for Xs ▾` when `isStreaming` becomes `false`.
   - Assert clicking toggles expansion with proper `aria-expanded` attributes.
   - Assert no model name string appears anywhere in the rendered markup.
3. `ToolExecutionCard.test.tsx`:
   - Assert command executions under 2000ms with exit 0 render as compact 24px pills.
   - Assert non-zero exit codes auto-expand with critical status light.
4. `TasksColumn.test.tsx`:
   - Assert terminal rows expand and collapse upon clicking header chevron.
   - Assert height resize handle updates state between 140px and 600px.
   - Assert `MAX_VISIBLE = 3` ceiling prevents mounting more than 3 active xterms.
   - Assert no emoji glyphs exist in the DOM output (validated with regex `/[^\x00-\x7F]/`).

### 10.3 Manual End-to-End Acceptance Flow
1. Run `make dev-web` (or `make dev` for Tauri desktop).
2. Ask: *"What processes are listening on port 8000?"*
   - Verify prose streams directly onto canvas without container box.
   - Verify thinking disclosure streams cleanly and auto-folds upon answer arrival.
   - Verify single-line CLI pill for short inspection command.
3. Ask: *"Start a simple test web server in the background on port 8765."*
   - Verify task card appears in TasksColumn.
   - Verify `[ 8765 ↗ ]` chip appears as soon as server listens.
   - Verify expanding terminal drawer in TasksColumn mounts xterm and can be resized by dragging the bottom handle.
