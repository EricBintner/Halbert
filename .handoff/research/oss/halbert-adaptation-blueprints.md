# Halbert Architectural Adaptation Blueprints

**Document Path**: `.handoff/research/oss/halbert-adaptation-blueprints.md`  
**Date**: 2026-09-12  
**Context**: Technical translation of discoveries from Claude Code v2.1.269, `open-claude-code`, `cdesktop`, and macOS `Claude.app` into Halbert's architecture.

---

## 1. Standing Directives & Governance Fencing

All designs strictly adhere to Halbert's non-negotiable rules defined in [`DECISIONS.md`](file:///Volumes/4TB-BAD/Halbert/DECISIONS.md) and [`AGENTS.md`](file:///Volumes/4TB-BAD/Halbert/AGENTS.md):

1. **The Computer Speaks as Itself**: Halbert speaks in the first person grounded in telemetry ("I noticed...", "My CPU usage is..."). Never as "Assistant" or "Sovereign".
2. **Model Locality Choke Point**: `is_local_model()` in `llm_config.py:181` is the sole arbiter of local vs cloud. No model menus or vendor branding on user surfaces.
3. **Conversation Invariant**: "One seamless conversation, hidden topic threads, no conversation list." No competing sidebar lists of separate chats.
4. **Command Staging Invariant**: "Commands staged from the UI are staged, never executed."
5. **Tokenized Palette**: Single palette in `shared-tokens/tokens.css`. No raw hex values, no emoji in UI, contrast validated via `scripts/check_contrast.py`.
6. **Git & Source Control Scope Boundary**: Halbert is an OS and computer hardware steward, not a codebase editor. Git is not in scope for Halbert's internal architecture, state persistence, configuration snapshots, or task isolation. Internal state belongs in SQLite/ledgers, configuration snapshots belong in content-addressed canon manifests (`snapshot.py`), and filesystem reversibility is handled via Btrfs snapshots (`crates/halbert-snapshots`). Git is strictly out of scope except for **Passive Observation of User Repos** (read-only inspection of user-managed repositories via `git status` or `git log` for ambient workspace awareness, which is tablestakes).

---

## 2. Blueprint 1: Professional Diff Review Pipeline

### 2.1 Problem in Halbert Today
Halbert's current `DiffBlock.tsx` (`dashboard/frontend/src/components/agent/DiffBlock.tsx:34`) carries an explicit placeholder:
```typescript
// Simple diff visualization (in production, use a proper diff library)
```
It splits raw strings, lacks virtualization, cannot render split diffs, and cannot track working-tree baselines.

### 2.2 Solution: Adopt `@pierre/diffs: 1.1.4` + Side Diff Panel
Lift the proven architecture from `cdesktop`'s `PierreConversationDiff.tsx`:

```
┌────────────────────────────────────────────────────────────────────────┐
│ Halbert AgentChat Layout                                               │
│                                                                        │
│ ┌───────────────────────────────┐ ┌──────────────────────────────────┐ │
│ │ Conversation Stream           │ │ Dockable Side Diff Panel         │ │
│ │                               │ │ 3 files modified (+62, -14)      │ │
│ │ ┌───────────────────────────┐ │ ├──────────────────────────────────┤ │
│ │ │ Inline Turn DiffBlock     │ │ │ Baseline: [Staged|On-Disk|Backup]│ │
│ │ │ Staged edits for Turn #12 │ │ ├──────────────────────────────────┤ │
│ │ │ (Powered by Pierre Diffs) │ │ │ ▼ /etc/nginx/nginx.conf          │ │
│ │ └───────────────────────────┘ │ │   (Virtualized Pierre Diff)      │ │
│ │                               │ │ ▼ halbert_core/config.py         │ │
│ │ [Composer: In lines 42-50...] │ │   (Click to jump)                │ │
│ └───────────────────────────────┘ └──────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

#### Implementation Steps:
1. **Dependency Installation**:
   Add `@pierre/diffs: 1.1.4` and `@pierre/diffs/react` to `packages/design-system` and `dashboard/frontend`.
2. **Theme Adapter** (`dashboard/frontend/src/styles/diff-theme.css`):
   Map Halbert's `tokens.css` variables to Pierre Diffs CSS variables:
   ```css
   [data-diff][data-theme-type='dark'] {
     --diffs-dark-bg: var(--color-bg-panel) !important;
     --diffs-dark-addition-color: var(--color-success) !important;
     --diffs-bg-addition-override: var(--color-success-muted) !important;
     --diffs-dark-deletion-color: var(--color-danger) !important;
     --diffs-bg-deletion-override: var(--color-danger-muted) !important;
     --diffs-fg-number-override: var(--color-text-muted) !important;
   }
   ```
3. **Dual Surface Experience**:
   - **Inline Turn Block** (`DiffBlock.tsx`): Displays exact file edits proposed in that turn with "Stage" / "Reject" actions.
   - **Persistent Side Diff Panel**: Dockable pane toggled via header or `/diff` command, showing full staged file diffs with 3-way baseline switching (Active Turn Staged, Current On-Disk, Pre-Edit Backup).
4. **Line-Selection Prompt Attachment**:
   Selecting lines in the diff panel copies structured reference tags (`[Diff: /etc/nginx/nginx.conf#L42-L50]`) into the message input box.

---

## 3. Blueprint 2: Ephemeral Side-Questions (`/btw`)

### 3.1 Preserving Halbert's "One Seamless Conversation"
Halbert forbids conversation list sidebars. However, developers frequently need to ask clarifying questions about code or tool outputs already in memory without bloating the conversation transcript or paying quadratic context token penalties on future turns.

### 3.2 Mechanism
1. **Composer Interception**:
   Entering `/btw <question>` triggers an out-of-band request.
2. **Backend Route** (`dashboard/routes/agent.py`):
   - Dispatches the prompt to the active session model with `tools=[]` (strict zero-tool gate).
   - Ingests active conversation context (hitting warm provider prompt cache).
   - Returns response marked with `ephemeral: true`.
3. **Transient UI Rendering**:
   - Renders in a floating HUD popover directly above the prompt input.
   - Kept in an in-memory ring buffer (max 20 entries) for quick recall.
   - Dismissed via `Esc` or `Enter`.
   - **Never persisted** to SQLite or JSONL session transcripts.
   - Optional "Promote to Conversation" action allows formalizing the insight into the main stream if needed.

---

## 4. Blueprint 3: Passive Observation of User Repositories (Tablestakes Integration)

### 4.1 Scope & Governance Boundary
Halbert is an operating system and hardware steward, not a codebase editor. Git is **not in scope** for Halbert's internal state management, configuration backups, task execution, or subagent isolation. Subagent isolation is handled through isolated scratch workspaces (`.halbert/scratch/`) and OS sandboxing (`crates/halbert-sandbox`), while system-level rollback is backed by atomic Btrfs filesystem snapshots (`crates/halbert-snapshots`).

Halbert's only touchpoint with source control is **Passive Observation of User Repositories**—a tablestakes requirement for understanding the developer or homelab operator's active host context without modifying git state.

### 4.2 Passive Sensor Architecture
1. **Read-Only Inspection Engine**:
   - Executes purely non-mutating status probes: `git status --porcelain`, `git log -n <limit>`, and `git branch --show-current` within detected user workspace directories.
   - Strictly wrapped in timeout guards and read-only subprocess restrictions.
2. **Contextual Ingestion**:
   - Ingests user repo metadata into ambient context (e.g., noticing dirty working trees or branch switches when diagnosing local services or answering user queries).
   - Surfaces uncommitted changes as read-only telemetry in system overview panels.
3. **Zero-Mutation Guarantee**:
   - Halbert never executes `git checkout`, `git commit`, `git push`, `git merge`, or worktree manipulations.
   - All proposed file modifications remain governed by Halbert's standard staged approval workflow (`DiffBlock.tsx`) writing directly to disk on user confirmation, completely independent of Git.

---

## 5. Blueprint 4: Dev Server Preview & Headless Auto-Verification

### 5.1 Architecture
Modeled after Anthropic's `.claude/launch.json` and `cdesktop`'s `PreviewBrowser.tsx`:

1. **Configuration File** (`.halbert/launch.json`):
   Standardized configuration specifying dev server startup commands (`npm run dev`, `make dev-web`), health endpoints, and port definitions.
2. **Preview Pane Component** (`dashboard/frontend/src/components/preview/PreviewBrowser.tsx`):
   - Embedded iframe with secure sandbox tokens (`allow-scripts allow-same-origin allow-forms allow-popups`).
   - Device frame emulation: Desktop (responsive) and Mobile (iPhone $390 \times 844\text{px}$).
   - Dev server start, stop, refresh, and pop-out controls.
3. **Auto-Verification Hook**:
   Before completing a frontend turn, Halbert's backend queries the local preview endpoint, checks console error streams, and captures a verification screenshot for user confirmation.

---

## 6. Blueprint 5: Native macOS System Integration via Swift FFI

### 6.1 Replacing AppleScript
Currently, system inspections on macOS often rely on `osascript` subprocess calls. As revealed by the disassembly of `/Applications/Claude.app`, Anthropic uses native Swift binaries (`@ant/claude-swift`).

### 6.2 Implementation in `crates/halbert-ffi`
Halbert already has `crates/halbert-ffi`. We can implement native Swift/Objective-C bindings:

1. **Display & Window Querying**:
   Call Quartz Services (`CGWindowListCopyWindowInfo`) directly for sub-millisecond active window inspection without spawning shell processes.
2. **Hardware-Accelerated Screen Capture**:
   Use `CGDisplayStreamCreate` or `CGWindowListCreateImage` for instantaneous screen sampling for local vision models.
3. **Accessibility Inspection**:
   Use `AXUIElementCopyAttributeValue` to inspect the accessibility tree of active GUI applications, providing grounded context for system assistance.
4. **Deterministic Security Gate**:
   All native actions remain gated by Halbert's deterministic security layer; no execution occurs without explicit user consent.
