# Claude Desktop Open-Source Ecosystem Survey

**Document Path**: `.handoff/research/oss/claude-desktop-ecosystem.md`  
**Date**: 2026-09-12  
**Scope**: Comparative survey of open-source desktop clients, agent wrappers, and workspaces modeled on Claude Code Desktop.

---

## 1. Ecosystem Landscape Overview

With Anthropic restricting third-party model names in official desktop builds and developer demand for local multi-agent management rising, several community open-source desktop implementations have emerged:

| Project | Stars / Activity | Framework | Primary Engine(s) | Key Innovations |
|---|---|---|---|---|
| **`cdesktop`** | High (2,244 commits) | Rust (Axum + Tokio) + Tauri + React 18 | Claude Code, Codex, Gemini, OpenCode, Hermes | Multi-cell grid (1-4 panes), `@pierre/diffs: 1.1.4`, Git worktree locks, dev server proxy, mobile emulation frames. |
| **`cc-haha`** | Growing | Node.js + Electron / Web | Claude Code, Multi-model | Git worktree isolation, visual diffs, Computer Use support, chat bridge to Feishu / WeChat / Telegram / WhatsApp. |
| **`cc-switch`** | Moderate | Go / Webview | Claude Code, Codex, OpenClaw, Grok, Hermes | Multi-harness CLI switcher, binary path resolution, config file switching. |
| **`desktop-cc-gui`** | Early | Rust + Tauri | Claude Code, Gemini, DeepSeek | Pure Tauri client focused on lightweight memory footprint. |
| **`eigent`** | High | TypeScript + Electron | Autonomous Cowork agent | Dedicated alternative to Claude Cowork; long-horizon task planning. |

---

## 2. Detailed Project Audits

### 2.1 `cdesktop` (`cdesktop-ai/cdesktop`)
- **Verdict**: By far the most mature, feature-complete, and technically sound open-source implementation of the Claude Code Desktop UX.
- **Why it matters to Halbert**:
  - Exact technology stack alignment (**Rust + Tauri + React 18 + Tailwind**).
  - Production-tested implementation of `@pierre/diffs` with custom CSS theme mapping.
  - Asynchronous, path-mutexed Git worktree management in `cdesktop` (developer IDE pattern; out of scope for Halbert's OS runtime).
  - Clean dev server proxy architecture with responsive iframe sandbox.

### 2.2 `cc-haha` (`NanmiCoder/cc-haha`)
- **Overview**: Local-first cross-platform desktop workspace for Claude Code with multi-agent orchestration.
- **Notable Features**:
  - Multi-channel notification relay: Enables an agent running on the desktop to send status updates and receive user replies via IM platforms (Telegram, WeChat, Feishu).
  - Task-aware desktop pets / HUD indicators: Floating status indicators that visualize agent thinking and execution states.
- **Takeaway for Halbert**: Useful reference for Halbert's proactive event notifications and mobile dispatch relays.

### 2.3 `cc-switch` (`farion1231/cc-switch`)
- **Overview**: An all-in-one launcher and assistant for switching between multiple coding agent harnesses.
- **Notable Features**:
  - Global configuration injector: Manages environment variables and token storage across conflicting CLI tools.
  - Environment sanity checker: Verifies Node, Python, and CLI binary paths before launching.

---

## 3. Technology Selection Matrix for Halbert

| Capability | Official Claude Desktop | `cdesktop` | Proposed Halbert Solution |
|---|---|---|---|
| **App Shell** | Electron (v32+) | Tauri v1/v2 + Axum | **Tauri v2** (Existing Halbert standard) |
| **Diff Rendering** | Custom Web Component | `@pierre/diffs: 1.1.4` | **`@pierre/diffs: 1.1.4`** with Halbert tokens |
| **Session Isolation** | Git Worktrees (`--worktree`) | `crates/worktree-manager` | **Staged Scratch / OS Sandboxing** (Git is not in scope for Halbert state/isolation; internal execution uses filesystem staging & `crates/halbert-snapshots`. Git is strictly confined to passive observation of user repos.) |
| **Terminal I/O** | `ptyHostWorker` (Node worker) | PTY stream processor | **Isolated PTY worker** with 128KB output ceilings |
| **macOS Control** | Swift Native (`@ant/claude-swift`) | None (CLI wrapper) | **`crates/halbert-ffi`** (Swift/Obj-C Quartz + Accessibility bridge) |
| **Dev Preview** | Embedded Browser pane | `PreviewBrowser` + proxy | **`PreviewBrowser`** with iframe sandbox & auto-verify loop |
