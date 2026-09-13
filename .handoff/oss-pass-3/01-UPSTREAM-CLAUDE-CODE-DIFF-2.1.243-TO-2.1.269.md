# Upstream Claude Code Diff & Analysis: v2.1.243 to v2.1.269

Produced 2026-09-12 for `.handoff/oss-pass-3`.
Tracks upstream acceleration across 26 releases of `@anthropic-ai/claude-code` (from 2026-08-24 to 2026-09-11) and updates in `/Volumes/Thunderbolt/AI/OSS/open-claude-code`.

---

## 1. Executive Summary

Between August 24, 2026 (v2.1.243) and September 11, 2026 (v2.1.269), Anthropic shipped 26 rapid releases of Claude Code. This period marked a major evolution in the user experience and backend orchestration:

1. **Live Side-by-Side Diff Panel (`/diff`)** (v2.1.260): Moving beyond sequential inline diff blocks to an interactive, auto-updating diff panel alongside the conversation, complete with prompt-selection attachment and 3-way baseline switching.
2. **Ephemeral Side-Questions (`/btw`)**: Enabling out-of-band context queries against warm prompt cache without polluting the linear conversation transcript or incurring cumulative context penalties.
3. **App Previews & Auto-Verification**: Formalized dev server orchestration via `.claude/launch.json` paired with DOM inspection and screenshot verification loops before completing turns.
4. **Configurable Output Truncation Buffers** (`bashOutputMaxChars` / `taskOutputMaxChars` up to 128KB, v2.1.261): Eliminating excessive scratchpad round-trips for medium-sized CLI outputs.
5. **Context Hygiene Tools** (`/skill-doctor`, prompt-cache miss attribution): Measuring and eliminating dead-weight skill descriptions and tracking TTL/mutation cache misses.

---

## 2. Local OSS Repository State (`open-claude-code`)

### 2.1 Git Sync and Commit Progression

The local checkout at `/Volumes/Thunderbolt/AI/OSS/open-claude-code` was pulled from commit `22a47be` to `e482312` (`origin/main`, tag `v2.0.0-nightly.20260912`):

```
e482312 chore: update last-known Claude Code version to 2.1.269
28fee39 chore: update last-known Claude Code version to 2.1.268
3a79178 chore: update last-known Claude Code version to 2.1.267
090f244 chore: update last-known Claude Code version to 2.1.266
c38db2b chore: update last-known Claude Code version to 2.1.263
3faea37 chore: update last-known Claude Code version to 2.1.261
ab8c4c7 chore: update last-known Claude Code version to 2.1.259
f30766c chore: update last-known Claude Code version to 2.1.258
9d0052f chore: update last-known Claude Code version to 2.1.252
c65609b chore: update last-known Claude Code version to 2.1.251
b5dcc92 chore: update last-known Claude Code version to 2.1.250
d0bcad4 chore: update last-known Claude Code version to 2.1.247
65d45b9 fix(v2): validate and normalize API key configuration (#24)
7bfc4db chore: update last-known Claude Code version to 2.1.246
```

### 2.2 Analysis of Code Changes in `open-claude-code`

The substantive code change landed in `v2/` was commit `65d45b9` (`fix(v2): validate and normalize API key configuration`):

1. **Whitespace Trimming & Sanitization** (`v2/src/core/providers.mjs`):
   ```javascript
   export function readApiKey(...envKeys) {
       for (const envKey of envKeys) {
           const value = (process.env[envKey] || '').trim();
           if (value) return value;
       }
       return '';
   }
   ```
   - Guards against accidental newlines or trailing spaces injected by shell command substitutions (`$(cat ...)` or `pbpaste`).
   - Treats whitespace-only values as unset, falling through to secondary fallback variable names (e.g., `GOOGLE_API_KEY` falling through to `GEMINI_API_KEY`).
   - Delegates validation strictly to the provider authenticator rather than attempting brittle regex pattern checks locally.

2. **Command and Diagnostics Integration** (`v2/src/ui/commands.mjs`):
   - Updates `/doctor` to report `NOT SET` for empty/whitespace keys.
   - Updates `/login` to sanitize input before storage and refuse empty arguments.

3. **Pre-Network Failure Surfacing** (`v2/src/core/agent-loop.mjs`):
   - Missing or blank configuration now generates an immediate `{ type: 'error' }` event locally before dispatching to HTTP clients, avoiding unnecessary network round-trips and socket timeouts.

### 2.3 Automated Pipeline Throttling in `open-claude-code`

The automated nightly release notes in `open-claude-code` reported:
> `Decompilation was not available for this release.`
> `AI analysis was unavailable for this release.`

**Root Cause:**
- In `.github/workflows/nightly.yml`, Phase 3 runs `scripts/decompile-and-diff.mjs` and `scripts/analyze-discoveries.sh`.
- The `rudevolution` submodule (`path = rudevolution`) is uninitialized in the workflow environment, causing the decompiler to fail-open without breaking the build.
- `ANTHROPIC_API_KEY` was unset in repository secrets, causing AI analysis to skip.
- Consequently, while the repository detects and records upstream version bumps nightly, code synchronization into `v2/src/` is currently manual and periodic.

---

## 3. Deep Dive: Upstream Anthropic Claude Code Feature Additions

Based on the official changelog (`code.claude.com/docs/en/changelog`), documentation (`interactive-mode.md`, `desktop.md`), and npm distribution packages (`@anthropic-ai/claude-code@2.1.269`):

### 3.1 The Live Diff Panel (`/diff`) (v2.1.260)

Anthropic introduced a persistent, interactive Diff Panel alongside the conversation in fullscreen rendering mode, completely overhauling how code changes are inspected during active agent runs.

#### Key Mechanics:
1. **Side-by-Side Fullscreen Docking**:
   - Requires a terminal or view with at least 110 columns.
   - Automatically opens if the terminal width is >= 144 columns as soon as Claude begins editing files.
   - Remains docked beside the active conversation stream while the user continues typing.
2. **Real-Time Synchronous Refresh**:
   - Re-runs git analysis automatically after every file edit tool call (`write_file`, `edit_file`, `replace_file_content`) and after every shell execution (`bash`).
3. **Interactive Line-Range Prompt Attachment**:
   - Users can drag-select lines directly in the diff panel using the mouse.
   - Selected line ranges are attached as structured context chips to the next user prompt in the composer, allowing rapid feedback ("In lines 45-52 here, make this async").
4. **Intelligent Noise Filtering**:
   - Automatically filters out test files and generated artifacts from the main file list.
   - Groups changes made prior to the current session into a collapsed footer drawer ("X older uncommitted changes").
5. **Three-Way Baseline Cycling (`Ctrl+X B`)**:
   - **Mode 1: Session Only** — Shows solely edits made during the active session.
   - **Mode 2: Working Tree** — Shows all uncommitted changes across the entire workspace.
   - **Mode 3: Branch Divergence** — Compares the current working tree against the point where the active branch diverged from the default branch (`main` / `master`).

---

### 3.2 Ephemeral Side-Questions (`/btw`) (v2.1.260)

To resolve the tension between answering quick developer queries and preserving clean context windows, Claude Code added the `/btw` command.

#### Key Mechanics:
1. **Zero Context-History Contamination**:
   - Neither the question nor the model's answer is appended to the session message history.
   - Future turns never pay token costs for the exchange.
2. **Full In-Memory Context Accessibility**:
   - The query sees all messages, loaded file contents, tool outputs, and decisions accumulated up to the current turn.
3. **Strict Zero-Tool Policy**:
   - To guarantee zero side-effects and instant response times, tool execution is blocked during `/btw` turns (no file reads, command execution, or web lookups).
4. **Warm Prompt-Cache Re-use**:
   - Because the session prefix is completely identical to the main conversation, the prompt cache hits at near 100%, costing fractions of a cent.
5. **In-Memory History Ring Buffer**:
   - Maintains the last 20 side exchanges in an in-memory ring buffer (separate from disk transcripts).
   - In TUI, renders as a modal overlay dismissible with `Space`, `Enter`, or `Esc`.
   - Pressing `f` forks the side-exchange into a dedicated background subagent with full tool capabilities.

---

### 3.3 Configurable Terminal Output Ceilings (v2.1.261)

- **`bashOutputMaxChars` and `taskOutputMaxChars`**:
  - Developers can raise the inline buffer limit up to 128,000 characters before Claude Code diverts the output to a disk file.
  - Previous tight limits caused frequent interruptions where the agent had to invoke additional file-reading tools to inspect standard test logs or compiler outputs.

---

### 3.4 Context Hygiene & Diagnostics (`/skill-doctor`) (v2.1.261)

- **Dead-Weight Skill Pruning**:
  - `/skill-doctor` calculates the exact token footprint that each installed skill adds to the system prompt.
  - Tracks invocation counts per skill across sessions; flags skills with 0 invocations for safe removal.
- **Prompt-Cache Miss Attribution**:
  - `/cost` and status bars now diagnose why cache misses occurred:
    - Tool schema definitions altered dynamically.
    - System prompt invalidated by config change.
    - Session idle exceeded provider cache TTL (e.g., Anthropic 5-minute cache expiry).

---

### 3.5 App Previews & Headless Auto-Verification

- **Configuration File**: `.claude/launch.json` detects standard dev servers (Vite, Next.js, FastAPI, etc.).
- **Auto-Verification Loop**:
  - When enabled, Claude automatically triggers dev server startup after code modifications.
  - Takes headless screenshots, inspects DOM elements, checks console error streams, and iterates on fixes before signaling turn completion.
- **Session Cookie Persistence**:
  - `Persist sessions` retains cookies and local storage across server restarts to eliminate login friction during test cycles.

---

## 4. Technical Relevance to Halbert

| Feature | Upstream Status | Halbert Status | Recommended Action |
|---|---|---|---|
| **Diff Presentation** | Live side panel + Turn viewer | Naive inline `DiffBlock.tsx` | Replace naive diff with `@pierre/diffs: 1.1.4`; add side Diff Panel. |
| **Out-of-band Queries** | `/btw` overlay with warm cache | Not implemented | Implement `/btw` overlay; answer from active context without transcript logging. |
| **Output Buffers** | Configurable up to 128KB | Hardcoded thresholds | Add configurable stdout ceilings in `tools/executor.py` and terminal tiles. |
| **Context Diagnostics** | `/skill-doctor` | Static prompt builder | Add capability/skill token auditing to Halbert's settings and diagnostic tabs. |
| **Dev Preview Loop** | `.claude/launch.json` + preview proxy | Manual browser testing | Add `.halbert/launch.json` runner and preview pane in Tauri dashboard. |
