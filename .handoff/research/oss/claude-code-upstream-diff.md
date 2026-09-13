# Claude Code Upstream Evolution & Diffs (v2.1.243 → v2.1.269)

**Document Path**: `.handoff/research/oss/claude-code-upstream-diff.md`  
**Date**: 2026-09-12  
**Repositories Analyzed**:
- `/Volumes/Thunderbolt/AI/OSS/open-claude-code` (Git commits `22a47be` to `e482312`)
- `@anthropic-ai/claude-code` npm releases (v2.1.243 through v2.1.269)
- Official Documentation & Changelog: `https://code.claude.com/docs/en/`

---

## 1. Scope & Release Velocity

Between August 24, 2026 and September 11, 2026, Anthropic published **26 distinct minor versions** of `@anthropic-ai/claude-code`:

```
2.1.243 (Aug 24) ──> 2.1.246 ──> 2.1.247 ──> 2.1.250 ──> 2.1.251 ──> 2.1.252 ──>
2.1.258 (Sep 01) ──> 2.1.259 ──> 2.1.260 (Sep 03: /diff panel) ──> 2.1.261 (Sep 04: /skill-doctor) ──>
2.1.263 (Sep 06) ──> 2.1.266 ──> 2.1.267 ──> 2.1.268 (Sep 10) ──> 2.1.269 (Sep 11)
```

This release velocity reflects rapid consolidation around desktop-grade interactive terminal features, out-of-band context inspection, and token cost hygiene.

---

## 2. Local Codebase Analysis: `open-claude-code`

The repository at `/Volumes/Thunderbolt/AI/OSS/open-claude-code` acts as an open-source mirror and tracking harness. 

### 2.1 Git Sync State
- Fast-forwarded local `main` branch from `22a47be` to `e482312` (`v2.0.0-nightly.20260912`).
- 13 automated daily bot commits updated `scripts/last-known-claude-version.txt` from `2.1.243` to `2.1.269`.

### 2.2 Substantive Code Change: API Key Normalization (PR #24, commit `65d45b9`)
Located in `v2/src/core/providers.mjs`:
```javascript
export function readApiKey(...envKeys) {
    for (const envKey of envKeys) {
        const value = (process.env[envKey] || '').trim();
        if (value) return value;
    }
    return '';
}
```
**Key Mechanisms**:
1. **Whitespace Trimming**: Strips `\n` and trailing spaces commonly introduced when developers copy keys via `$(cat ~/.anthropic_key)` or `pbpaste`.
2. **Whitespace-Only Fallback**: Treats `"   "` as unset, automatically falling through to alternate environment names (e.g. `GOOGLE_API_KEY` falling back to `GEMINI_API_KEY`).
3. **No Brittle Local Regex**: Leaves format validation to the provider API, avoiding false rejections of new provider key formats.
4. **Pre-Network Short-Circuiting** (`v2/src/core/agent-loop.mjs`): Emits a local `{ type: 'error' }` event immediately if required credentials are empty, bypassing socket creation and HTTP timeout latency.

### 2.3 Automated Pipeline Throttling
In `.github/workflows/nightly.yml`, automated nightly discovery reports yielded:
> `Decompilation was not available for this release.`  
> `AI analysis was unavailable for this release.`

**Root Cause**: The workflow requires the `rudevolution` submodule (`path = rudevolution`), which is uninitialized in CI, and `ANTHROPIC_API_KEY` was omitted from repository secrets. The build fails-open to keep the nightly tag green, meaning manual decompilation passes are required to extract code into `v2/src/`.

---

## 3. Upstream Anthropic Feature Teardown

### 3.1 Live Diff Panel (`/diff`) (Introduced in v2.1.260)
Replaces the classic modal diff view with an interactive, docked side panel in fullscreen terminals.

```
┌──────────────────────────────────────┬──────────────────────────────────────┐
│ Conversation Stream                  │ Diff Panel (Active Working Tree)     │
│                                      │ 3 files changed (+45, -12)           │
│ User: "Refactor the config parser"   ├──────────────────────────────────────┤
│                                      │ ▼ src/config.py (+30, -8)            │
│ Claude:                              │   45   def load_config():            │
│   "I'll update the loader to support │ + 46       path = resolve_path()     │
│    strict typing."                   │ - 47       path = "default.json"     │
│                                      │ ▼ tests/test_config.py (+15, -4)     │
│                                      │                                      │
├──────────────────────────────────────┴──────────────────────────────────────┤
│ Composer > In lines 45-47, please use Pathlib instead.                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Technical Specifications:
- **Display Constraint**: Requires at least 110 terminal columns.
- **Auto-Open Heuristic**: Automatically opens upon Claude's first file edit if the viewport width $\ge 144$ columns.
- **Dynamic Refresh**: Hooks into the post-tool execution lifecycle; automatically triggers git status re-evaluation after `write_file`, `replace_file_content`, and `bash` commands.
- **Line Selection Prompt Context Attachment**: Users can highlight lines with the mouse in the diff panel; the UI automatically injects a structured reference chip (`[Diff lines 45-47]`) into the composer input.
- **3-Way Comparison Baseline Toggle (`Ctrl+X B`)**:
  1. *Session Turn*: Diffs only edits made during the active turn.
  2. *Uncommitted Working Tree*: Diffs all uncommitted changes across the git status.
  3. *Branch Split-Point*: Diffs working tree against the commit where the current branch diverged from `main`.
- **Smart Filtering**: Automatically collapses test files, lockfiles, and generated files to keep the review focused on primary business logic.

---

### 3.2 Ephemeral Side-Questions (`/btw`) (v2.1.260)
Solves the issue of querying code currently held in context without permanently polluting the conversation trajectory.

#### Operational Invariants:
1. **Zero History Contamination**: The query and answer are never appended to the session's durable JSONL/SQLite transcript.
2. **Strict Zero-Tool Gate**: Tools (`bash`, `read_file`, `web_search`) are disallowed. The model must answer solely from memory and context already ingested.
3. **Near-Zero Marginal Cost**: Hits warm provider prompt cache. Only output tokens are billed.
4. **Overlay UI & Forking**: Renders in an ephemeral popover overlay (dismissed via `Esc` or `Enter`). Pressing `f` forks the query and its answer into a new background subagent with full tool access.
5. **In-Memory Ring Buffer**: Stores up to 20 recent side exchanges in process memory for reference during the session.

---

### 3.3 Configurable Output Ceilings (v2.1.261)
- Introduces `bashOutputMaxChars` and `taskOutputMaxChars` configuration settings.
- Increases the maximum inline terminal output buffer up to 128,000 characters before writing spillover to a temporary file.
- Prevents unnecessary file-read tool round-trips for medium-sized compiler warnings, test runners, or linter outputs.

---

### 3.4 Skill Context Hygiene (`/skill-doctor`) (v2.1.261)
- Calculates and displays the exact system prompt token cost for every installed skill.
- Tracks skill invocation frequency across sessions; identifies skills with 0 calls as candidates for uninstallation to preserve context budget.
- Reports prompt-cache miss attribution (diagnosing whether a miss was caused by a schema edit, system prompt change, or TTL expiration).
