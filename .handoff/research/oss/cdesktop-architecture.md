# cdesktop Subsystem & Architecture Audit

**Document Path**: `.handoff/research/oss/cdesktop-architecture.md`  
**Date**: 2026-09-12  
**Target Repository**: `/Volumes/Thunderbolt/AI/OSS/cdesktop` (`https://github.com/cdesktop-ai/cdesktop.git`)  
**Commit Count**: 2,244 commits  
**Version**: 0.2.3  
**Stack Alignment with Halbert**: **Rust + Tauri + React 18 + Tailwind CSS** (Direct match)

---

## 1. System Overview

`cdesktop` is an open-source, local-first desktop workspace that wraps multiple coding agent CLIs (Claude Code, Codex, Gemini CLI, OpenCode, Hermes) within a unified desktop GUI modeled directly after the Code tab of Anthropic's Claude Desktop application.

```
                    ┌──────────────────────────────────────────────────┐
                    │               Tauri Desktop Window               │
                    │   ┌───────────────────────────────────────────┐  │
                    │   │        SessionGrid (1 to 4 Panes)         │  │
                    │   │  ┌─────────────────┬───────────────────┐  │  │
                    │   │  │  Active Chat    │ Side Diff Panel   │  │  │
                    │   │  │  (Claude Code)  │ (@pierre/diffs)   │  │  │
                    │   │  ├─────────────────┼───────────────────┤  │  │
                    │   │  │  Dev Preview    │ Terminal Pane     │  │  │
                    │   │  │  (PreviewProxy) │ (PTY Shell)       │  │  │
                    │   │  └─────────────────┴───────────────────┘  │  │
                    │   └───────────────────────────────────────────┘  │
                    └─────────────────────────┬────────────────────────┘
                                              │ WebSockets / IPC
                    ┌─────────────────────────▼────────────────────────┐
                    │            Rust Axum Server (30 Crates)          │
                    │  ┌───────────────────────┬────────────────────┐  │
                    │  │ crates/executors      │ crates/worktree-mgr│  │
                    │  │ (Process Streaming)   │ (Git Worktree Lock)│  │
                    │  ├───────────────────────┼────────────────────┤  │
                    │  │ crates/preview-proxy  │ crates/db          │  │
                    │  │ (Reverse Proxy)       │ (SQLite State)     │  │
                    │  └───────────────────────┴────────────────────┘  │
                    └──────────────────────────────────────────────────┘
```

---

## 2. Deep Dive: Key Subsystems

### 2.1 Process Execution & Stream Protocol (`crates/executors`)
Located in `crates/executors/src/executors/claude.rs` (134 KB) and `claude/`:

- **Child Process Management**: Spawns the agent CLI (`claude`) with piped stdio or pseudo-terminal (PTY) emulation.
- **Protocol Deserializer**: Implements a zero-copy streaming parser for Claude Code's NDJSON output stream:
  ```rust
  pub enum ClaudeStreamEvent {
      ContentBlockStart { index: usize, content_block: ClaudeContentItem },
      ContentBlockDelta { index: usize, delta: ClaudeContentBlockDelta },
      ContentBlockStop { index: usize },
      MessageDelta { delta: ClaudeMessageDelta, usage: ClaudeUsage },
      ToolUse { id: String, name: String, input: serde_json::Value },
  }
  ```
- **Provider Environment Injection** (`server/src/provider_injection.rs`):
  Dynamically injects `ANTHROPIC_BASE_URL` and custom API keys at runtime when spawning agent sessions, allowing third-party LLM gateways (OpenRouter, Bedrock, DeepSeek) to run inside the Claude Code CLI.
- **Local Slash Command Interception** (`claude/slash_commands.rs`):
  Parses user inputs starting with `/` and handles UI-only commands (`/diff`, `/clear`, `/model`, `/login`) locally without forwarding them across the wire.

---

### 2.2 Concurrency-Safe Git Worktree Engine (`crates/worktree-manager`)
Located in `crates/worktree-manager/src/worktree_manager.rs` (23 KB):

- **Path-Keyed Asynchronous Mutex**:
  ```rust
  static WORKTREE_CREATION_LOCKS: Lazy<Mutex<HashMap<String, Arc<tokio::sync::Mutex<()>>>>> =
      Lazy::new(|| Mutex::new(HashMap::new()));
  ```
  Prevents race conditions, lockfile collisions (`.git/index.lock`), and corrupted worktree trees when multiple subagents or parallel tabs launch simultaneously.
- **Non-Blocking Git Operations**:
  Wraps all git operations (`git2` branch creation, worktree addition, and checkout) in `tokio::task::spawn_blocking` to prevent blocking the async runtime.
- **Corrupted State Self-Healing**:
  Checks whether `.git` pointer files and working directories are intact; if git state is damaged or detached, executes `comprehensive_worktree_cleanup_async` and cleanly recreates the worktree.

*(Architectural Boundary for Halbert: Git worktree management is specific to developer coding environments like `cdesktop`. Git is not in scope for Halbert's internal architecture, execution isolation, or state management; Halbert's interaction with source control is strictly limited to passive, read-only observation of user-managed repositories.)*

---

### 2.3 Visual Diff Engine (`packages/ui/src/components/PierreConversationDiff.tsx`)
Built with `@pierre/diffs: 1.1.4`:

- **Input Discriminated Union**:
  ```typescript
  export type DiffInput =
    | {
        type: 'content';
        oldContent: string;
        newContent: string;
        oldPath?: string;
        newPath: string;
      }
    | {
        type: 'unified';
        path: string;
        unifiedDiff: string;
        hasLineNumbers?: boolean;
      };
  ```
- **Virtualization**:
  Leverages Pierre Diffs' internal virtual DOM renderer, smoothly handling large refactors (5,000+ lines) without frame drops.
- **Unified & Split View Modes**:
  Toggles between side-by-side split diffs and inline unified diffs based on available pane width.
- **Tokenized Styling Overrides**:
  Uses `@layer unsafe` CSS injection to override Pierre Diffs default color variables directly with application CSS tokens:
  - `--diffs-light-addition-color: hsl(160, 77%, 35%)`
  - `--diffs-dark-addition-color: hsl(130, 50%, 50%)`
  - `--diffs-fg-number-override: hsl(var(--text-low))`

---

### 2.4 Dev Server Preview Engine (`PreviewBrowser.tsx` & `crates/preview-proxy`)
Located in `packages/ui/src/components/PreviewBrowser.tsx`:

- **Iframe Sandbox Configuration**:
  ```typescript
  const PREVIEW_IFRAME_SANDBOX =
    'allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals';
  ```
- **Viewport Emulation**:
  - **Desktop**: Full responsive width.
  - **Mobile**: Fixed iPhone dimension frame ($390 \times 844\text{px}$) with realistic outer padding ($24\text{px}$).
  - **Responsive**: Drag-handle resizable container.
- **Proxy Rewriting**:
  `crates/preview-proxy` acts as a reverse proxy between the embedded iframe and the developer's localhost server (Vite, Next.js), stripping restrictive CSP headers and rewriting cookies for persistent sessions.

---

### 2.5 Multi-Cell Grid Architecture (`SessionGrid.tsx`)
- Supports splitting the main canvas into 1, 2, 3, or 4 cells.
- Session tabs can be dragged between cells using `@hello-pangea/dnd`.
- Allows viewing code generation, terminal output, visual diffs, and the live browser preview concurrently on a single screen.

---

### 2.6 Routines & Scheduled Automation (`routes/routines.rs`)
- Enables defining scheduled recurring tasks (hourly, daily, weekdays, weekly) or manual-fire templates.
- When triggered, automatically checks out an isolated Git worktree, boots an agent session, runs the specified task, and stages the completed work for developer review.
