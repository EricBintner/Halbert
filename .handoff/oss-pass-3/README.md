# oss-pass-3: Upstream Claude Code Diff, Desktop Ecosystem & Native App Reverse Engineering

Produced 2026-09-12 by the third OSS reverse-engineering pass.
Audits the acceleration of official Anthropic Claude Code (v2.1.243 to v2.1.269), updates to `open-claude-code`, the open-source `cdesktop` workspace, and the native architecture of macOS `Claude.app`.

---

## 1. Directory Structure & Document Index

| Document | Description |
|---|---|
| [`01-UPSTREAM-CLAUDE-CODE-DIFF-2.1.243-TO-2.1.269.md`](01-UPSTREAM-CLAUDE-CODE-DIFF-2.1.243-TO-2.1.269.md) | **Upstream Progression & Code Diff**: Tracks 26 releases of `@anthropic-ai/claude-code` and git changes in `open-claude-code`. Details the **Live Diff Panel (`/diff`)**, **Ephemeral Side-Questions (`/btw`)**, **128KB output buffers**, and **`/skill-doctor`**. |
| [`02-CLAUDE-DESKTOP-ECOSYSTEM-AND-REVERSE-ENGINEERING.md`](02-CLAUDE-DESKTOP-ECOSYSTEM-AND-REVERSE-ENGINEERING.md) | **Desktop Ecosystem & Binary Inspection**: Full audit of `cdesktop` (`https://github.com/cdesktop-ai/cdesktop`, 2,244 commits, Rust/Tauri/React), survey of open-source alternatives (`cc-haha`, `cc-switch`), and binary disassembly of official macOS `Claude.app` (unpacked from `app.asar`, showing native Swift Computer Use bindings and isolated PTY workers). |
| [`03-HALBERT-ARCHITECTURAL-LEVERAGE-AND-UI-ROADMAP.md`](03-HALBERT-ARCHITECTURAL-LEVERAGE-AND-UI-ROADMAP.md) | **Halbert Implementation Blueprints**: Concrete plans to modernize Halbert's diff presentation (upgrading `DiffBlock.tsx` with `@pierre/diffs: 1.1.4`), add `/btw` ephemeral context queries, isolate tasks via Git worktrees, and integrate Swift FFI into `crates/halbert-ffi`. |

---

## 2. Key Takeaways

1. **`open-claude-code` Update Status**:
   - Pulled cleanly to `origin/main` (`e482312`, tag `v2.0.0-nightly.20260912`), tracking upstream release `2.1.269`.
   - The primary code change landed in `v2/` is API key sanitization, whitespace trimming, and pre-network failure surfacing in `agent-loop.mjs`.
   - Automated decompilation in GitHub Actions currently skips because the `rudevolution` submodule is uninitialized in CI.

2. **Upstream Anthropic Innovations (2.1.243 -> 2.1.269)**:
   - **Interactive Diff Panel**: Docks beside the conversation stream, updates dynamically on file/command changes, allows drag-selecting lines into prompt chips, and offers 3-way baseline switching (`Ctrl+X B`).
   - **Ephemeral `/btw` Questions**: Out-of-band context queries hitting warm prompt cache with zero context accumulation and zero transcript pollution.
   - **Configurable Output Truncation**: `bashOutputMaxChars` up to 128KB.

3. **`cdesktop` Project Assessment**:
   - `cdesktop` is a production-grade (2,244 commits) open-source desktop implementation of Claude Code Desktop.
   - Built on the exact same stack as Halbert (**Rust + Tauri + React 18 + Tailwind CSS**).
   - Features ready-to-lift implementations of `@pierre/diffs` (`PierreConversationDiff.tsx`), Git worktree lifecycle management (`crates/worktree-manager`), and dev server preview proxies (`PreviewBrowser.tsx`).

4. **Official macOS `Claude.app` Architectural Secrets**:
   - Computer Use is powered by native Swift binaries (`@ant/claude-swift`) calling Quartz and Accessibility APIs directly, rather than slow AppleScript wrappers.
   - Terminal sessions run in an out-of-process `ptyHostWorker` to guarantee zero UI thread lag.
