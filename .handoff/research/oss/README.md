# Open-Source Coding Agent & Desktop Research Dossier

**Location**: `.handoff/research/oss/`  
**Date**: 2026-09-12  
**Subject**: In-depth research on upstream Claude Code acceleration (v2.1.243 → v2.1.269), `open-claude-code`, the `cdesktop` workspace, official macOS `Claude.app` disassembly, and adaptation blueprints for Halbert.

---

## 1. Document Directory

| Document | Topic & Focus Area | Key Findings / Highlights |
|---|---|---|
| [`claude-code-upstream-diff.md`](claude-code-upstream-diff.md) | **Upstream Progression & Code Diff** | Audits 26 releases of `@anthropic-ai/claude-code`. Covers the live side-by-side Diff Panel (`/diff`), out-of-band ephemeral questions (`/btw`), 128KB output ceilings (`bashOutputMaxChars`), `/skill-doctor`, and `open-claude-code`'s API key normalization. |
| [`cdesktop-architecture.md`](cdesktop-architecture.md) | **`cdesktop` Subsystem Anatomy** | Deep dive into `/Volumes/Thunderbolt/AI/OSS/cdesktop` (2,244 commits). Analyzes the 30-crate Rust backend, `crates/executors` streaming parser, `crates/worktree-manager` path-mutexed Git worktrees, `PierreConversationDiff.tsx` with `@pierre/diffs: 1.1.4`, and `PreviewBrowser.tsx`. |
| [`claude-desktop-binary-disassembly.md`](claude-desktop-binary-disassembly.md) | **macOS `Claude.app` Disassembly** | Unpacks `/Applications/Claude.app/Contents/Resources/app.asar` (v1.52386.3). Discovers native Swift bindings (`@ant/claude-swift`) for Quartz/Accessibility Computer Use, dedicated out-of-process PTY worker hosts (`ptyHostWorker.js`), and packaged `.skill` archives. |
| [`claude-desktop-ecosystem.md`](claude-desktop-ecosystem.md) | **Desktop Agent Workspace Survey** | Evaluates open-source alternatives: `cdesktop`, `NanmiCoder/cc-haha`, `farion1231/cc-switch`, `zhukunpenglinyutong/desktop-cc-gui`, and `eigent-ai/eigent`. Includes technology selection matrix for Halbert. |
| [`halbert-adaptation-blueprints.md`](halbert-adaptation-blueprints.md) | **Halbert Implementation Specifications** | Concrete plans for Halbert: upgrading `DiffBlock.tsx` with `@pierre/diffs: 1.1.4`, dockable Side Diff Panel, `/btw` ephemeral context queries, passive user repository observation, dev server preview loops, and native Swift bridges via `crates/halbert-ffi`. |

---

## 2. Core Takeaways for Halbert

1. **Exact Stack Synergy with `cdesktop`**:
   `cdesktop` proves that the modern AI Desktop experience can be cleanly implemented using **Rust + Tauri + React 18 + Tailwind**—the exact same foundation as Halbert. Its battle-tested code patterns for Pierre Diffs, streaming process parsing, and dev server proxies can be lifted directly with minimal adaptation.
2. **Modernizing the Diff Presentation**:
   Halbert's current `DiffBlock.tsx` explicitly carries a placeholder comment indicating a proper diff library is required. Upgrading to `@pierre/diffs: 1.1.4` and adding a dockable Side Diff Panel with prompt-selection attachment resolves this limitation.
3. **Preserving Single-Conversation Invariant via `/btw`**:
   Halbert's directive of "One seamless conversation, hidden topic threads, no conversation list" is strongly reinforced by the `/btw` ephemeral query pattern. Developers can query active context without polluting session transcripts or incurring cumulative context penalties.
4. **Native Swift Performance**:
   Anthropic's use of native Swift binaries (`@ant/claude-swift`) demonstrates that high-performance macOS integration requires moving beyond brittle AppleScript (`osascript`) to native Quartz and Accessibility FFI calls, which Halbert can implement in `crates/halbert-ffi`.
5. **Source Control Scope Boundary**:
   Git is not in scope for Halbert's internal architecture, state persistence, configuration snapshots, or task isolation (which rely on SQLite, content-addressed canon manifests, and Btrfs filesystem rollbacks). Git is strictly confined to **Passive Observation of User Repos** (read-only inspection of user-managed repositories for ambient workspace telemetry, which is tablestakes).
