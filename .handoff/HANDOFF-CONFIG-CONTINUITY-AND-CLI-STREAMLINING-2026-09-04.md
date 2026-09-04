# HANDOFF: Config-Centric Continuity & Streamlined CLI Feedback Architecture

**Date**: 2026-09-04  
**Author**: Antigravity / Pair Programming with Founder  
**Status**: Ready for Implementation  
**Target Subsystems**:
- Frontend: `halbert_core/dashboard/frontend/src/components/agent/` (`ToolExecutionCard.tsx`, `Timeline.tsx`, `AgentChat.tsx`)
- Backend Continuity: `halbert_core/continuity/` (`state_store.py`, `recall.py`, `provenance.py`)
- Editor Routes & UI: `halbert_core/dashboard/routes/editor.py` & `ConfigEditor.tsx`

---

## 1. Executive Context & Core Intentions

### 1.1 The Host-Steward Dilemma: Why Chat Sessions Don't Fit
Conventional AI developer tools (ChatGPT, Claude Desktop, Cursor, and `open-claude-code`) treat conversations as **disposable, isolated sessions** (`Chat 1`, `Debug script`, `Refactor test`). In those tools, the primary historical navigation is a sidebar list of chat session titles.

Halbert intentionally rejected this model. Halbert is a **living host steward and companion**. There is only one host machine. Halbert's conversation is an unbroken, day-grouped timeline of the machine's life ([`Timeline.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.tsx)). Partitioning interactions into isolated chat sessions breaks Halbert's holistic understanding of how an edit on Monday impacts system stability on Friday.

### 1.2 The Resulting Blindspot
Because Halbert lacks disposable chat sessions in the sidebar:
1. **The user loses quick historical breadcrumbs**: There is no fast way to see what Halbert recently touched without scrolling through days of timeline turns.
2. **The AI treats history as a flat linear transcript**: Long-running conversation turns fill up with raw inspection logs, making it hard for the AI to retain a sharp mental model of the previous time it interacted with a specific configuration.

### 1.3 The Founder's Architectural Realization
In system administration, users do not remember conversations by prompt name or arbitrary date. **Users remember system surfaces and configuration files**:
- *"What did we change in `/etc/fstab`?"*
- *"Where did we set up the `bcachefs` mount flags and compression?"*
- *"What did we touch in `/etc/samba/smb.conf`?"*
- *"Why did we change the `systemd` restart policy for `sshd`?"*

> **The Core Paradigm**:  
> Instead of a sidebar of chat sessions, Halbert will feature a **"Recent & Managed Configs"** surface (e.g. `fstab`, `bcachefs`, `samba`, `nginx`, `systemd`).  
> These config files become the **continuity anchors** for both the user and Halbert AI:
> - **For the User**: Fast navigation to recent interventions, 1-click Monaco diff/editor access, and temporal jump back into the exact conversation turns where that config was touched.
> - **For the AI**: Clean prompt hydration with the last known change, actor, and reason without having to re-read thousands of lines of chat history.

---

## 2. Reverse Engineering & Scrutiny of Existing Halbert Systems

A central constraint from the founder was: **"I don't want to overbuild this and we have a memory system (or two) already plus other systems..."**

Our deep inspection revealed that **Halbert already owns the required backend foundation**:

### A. The Machine-State Ledger ([`halbert_core/continuity/state_store.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/continuity/state_store.py))
- An immutable SQLite ledger storing triples in `state_triples`:
  - `subject` (e.g. `file:/etc/samba/smb.conf`)
  - `predicate` (`content_sha256`, `mode_octal`)
  - `valid_from` / `valid_to`
  - `reason` ("why") and `actor` (`user`, `agent`, `system`)
  - `thread_id` and `request_id`
- **Mandatory Reason & Actor**: Keyword-only parameters with no defaults. Provenance is never fabricated; if unrecorded, it explicitly stores `UNRECORDED`.
- Methods: `current_state()`, `state_history()`, `why()`.

### B. Deterministic Ledger Recall ([`halbert_core/continuity/recall.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/continuity/recall.py) & [`recall_memory.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/tools/recall_memory.py))
- `recall_state(path="/etc/samba/smb.conf")` answers deterministically:
  *What is currently true, since when, who changed it, and what reason was captured at the time?*
- `recorded_subjects()` returns every file and service subject ever recorded in the ledger.
- `recall_memory` is already exposed to the agent as a deterministic tool.

### C. Backup Store & Editor Routes ([`halbert_core/dashboard/routes/editor.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/editor.py))
- Every file save in `editor.py` snapshots the original file to `~/.config/halbert/backups/<encoded_path>/<timestamp>.bak` with metadata JSON files containing hashes, labels, and timestamps.
- Saves call `_record_editor_change()`, linking the write directly to the audit log and state ledger via [`continuity/provenance.py:record_file_change()`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/continuity/provenance.py#L130).

### D. Timeline Anchoring ([`Timeline.tsx:54`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.tsx#L54))
- `Timeline.tsx` already has an `anchored={true}` prop and `"Back to latest"` button, designed specifically to focus a window of turns around an entity or past intervention.

### Where the Gaps Actually Lie:
1. **Frontend Isolation**: There is no UI surface or drawer exposing recently touched config files.
2. **Command Line & Tool Leakage in `ToolExecutionCard.tsx`**:
   - `ToolExecutionCard.tsx:140-142` renders `<pre>{JSON.stringify(execution.args, null, 2)}</pre>`, leaking raw `{ "command": "systemctl status smbd" }` with curly braces `{}`.
   - Header displays the raw internal Python tool name (`run_command`) rather than the semantic shell command.
3. **Tool Card Clutter**:
   - Every single internal read/inspection call (`read_file`, `grep_search`, `list_dir`, `recall_memory`) renders as an identical, heavy boxed card. Running 5 inspection steps before 1 command produces 6 large stacked cards in the chat feed.

---

## 3. Lessons from Open-Claude-Code (`v2/`) & Desktop/Antigravity

Evaluating `/Volumes/Thunderbolt/AI/OSS/open-claude-code` highlights specific mechanics to adopt:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          CROSS-SYSTEM PATTERN COMPARISON                               │
├──────────────────────┬─────────────────────────────┬───────────────────────────────────┤
│ Open-Claude-Code v2  │ Claude Desktop / Antigravity│ Halbert Decision                  │
├──────────────────────┼─────────────────────────────┼───────────────────────────────────┤
│ • Pure terminal stream│ • Dual-pane: chat on left,  │ • Dual-pane hybrid:               │
│ • Single-line spinner │   artifacts/diff on right.  │   - Ephemeral pills for inspect.  │
│   (>> [Bash] running)│ • Collapsible action pills. │   - Clean $ <cmd> cards for bash. │
│ • 1MB output cap     │ • Rich Monaco diff editor.  │   - Docked Monaco ConfigEditor.   │
│ • CheckpointManager  │ • Rendered markdown & plans.│   - Recent Configs as continuity. │
└──────────────────────┴─────────────────────────────┴───────────────────────────────────┘
```

1. **Clean Command Presentation ([`open-claude-code/v2/src/tools/bash.mjs`](file:///Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src/tools/bash.mjs))**:
   Never prints JSON schemas. Extracts `command` and displays `$ <command>` with exit status code and elapsed time.
2. **Pre-Read Verification ([`open-claude-code/v2/src/tools/read.mjs:hasBeenRead`](file:///Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src/tools/read.mjs#L21-L27))**:
   Requires a file to be read before it can be edited, preventing blind writes.
3. **Micro-Compaction ([`open-claude-code/v2/src/core/context-manager.mjs`](file:///Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src/core/context-manager.mjs))**:
   Truncates stale tool results older than 3–5 turns while preserving user prompts and assistant reasoning, keeping long conversations fast and responsive.

---

## 4. The Unified Architecture

### 4.1 "Recent & Managed Configs" (Lightweight Continuity)

We do **not** create a new database. We add a single read route that unifies `StateStore` and the backup directory:

#### Route: `GET /api/continuity/recent-configs`
Implemented in `halbert_core/dashboard/routes/editor.py`:
- Queries `StateStore` for distinct `subject` entries starting with `file:` ordered by `valid_from DESC`.
- For each file:
  - Fetches the current triple (`object` = sha256, `reason`, `actor`, `valid_from`).
  - Checks backup count in `~/.config/halbert/backups/<encoded_path>/`.
  - Determines status: clean vs. modified externally.
- Returns JSON payload:
  ```json
  [
    {
      "filePath": "/etc/samba/smb.conf",
      "displayName": "Samba Configuration",
      "lastModified": 1725423800.0,
      "lastActor": "agent",
      "lastReason": "Added [backups] share with path /mnt/storage/backups",
      "backupCount": 3,
      "sha256": "8f1a2b...",
      "threadId": "thread_abc123"
    }
  ]
  ```

#### Frontend Surface: The Managed Configs Dock
- Placed in a collapsible drawer or secondary navigation bar in [`Layout.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx) / [`AgentChat.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx).
- Displays list of recently edited/managed config files with relative timestamps and actor badges.
- **Actions per item**:
  1. **"Edit in Monaco"**: Opens the right-pane [`ConfigEditor.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/ConfigEditor.tsx) overlay/drawer with live diff and backup selector.
  2. **"Jump to Conversation"**: Triggers `Timeline.tsx`'s `anchored={true}` mode, navigating directly to the conversation turns where that config was modified.

#### AI Prompt Hydration:
When Halbert is prompted about a file (e.g. *"Check our samba shares"*), the agent loop injects a 3-line continuity block from `recall_state()`:
```
[Context: /etc/samba/smb.conf]
Last modified: 2026-09-01 by agent
Reason: "Added [backups] share with path /mnt/storage/backups"
Current sha256: 8f1a2b... (verified intact on disk)
```

---

### 4.2 Streamlining the Conversation CLI & Tool Feedback

#### A. Elimination of Raw JSON & `{}` in `ToolExecutionCard.tsx`
- Remove `<pre>{JSON.stringify(execution.args, null, 2)}</pre>`.
- Extract `command = execution.args.command || execution.args.cmd || String(execution.args)`.
- Reformat the header:
  ```tsx
  <div className="flex items-center justify-between font-mono text-xs">
    <div className="flex items-center gap-2">
      <span className="text-emerald-400 font-bold">$</span>
      <span className="text-foreground font-medium truncate">{command}</span>
    </div>
    <div className="flex items-center gap-2">
      <Badge variant={exitCode === 0 ? "success" : "destructive"}>
        {exitCode === 0 ? "✓ 0" : `✗ ${exitCode}`}
      </Badge>
      {duration && <span className="text-muted-foreground">{duration.toFixed(1)}s</span>}
    </div>
  </div>
  ```

#### B. Two-Tier Tool Categorization
1. **Tier 1: Ephemeral Inspection Group (Under-the-Hood)**
   - Includes: `read_file`, `grep_search`, `list_dir`, `recall_memory`, `check_drift`.
   - While running: Displays a subtle animated status strip (`⟳ Reading /etc/fstab...`).
   - When finished: Aggregates consecutive inspection calls into a single collapsible summary pill:
     `⚡ Inspected 3 files · 🧠 Recalled 2 memories (click to expand)`
   - Eliminates the wall of 5–10 giant boxes in the chat feed.
2. **Tier 2: Persistent Action Cards**
   - Includes: `run_command`, `write_config`, `apply_diff`, `systemctl_action`.
   - Formatted as clean monospace command cards with collapsible output drawers (>6 lines).

---

## 5. Implementation Roadmap & Checklist

### Phase 1: CLI Feedback Streamlining (Frontend)
- [ ] **`ToolExecutionCard.tsx`**:
  - [ ] Strip raw JSON `<pre>` blocks and curly braces `{}`.
  - [ ] Format `run_command` as prompt header: `$ <command>`.
  - [ ] Add auto-collapsing stdout drawer for output $> 6$ lines.
  - [ ] Add one-click copy button for command and output.
- [ ] **`InspectionGroup.tsx` (New Component)**:
  - [ ] Intercept sequential inspection tools (`read_file`, `grep_search`, `recall_memory`).
  - [ ] Render as a single collapsible summary pill.

### Phase 2: Recent Configs API (Backend)
- [ ] **`halbert_core/dashboard/routes/editor.py`**:
  - [ ] Implement `GET /api/continuity/recent-configs`.
  - [ ] Query `StateStore` for `file:` subjects ordered by `valid_from DESC`.
  - [ ] Query backup directories in `~/.config/halbert/backups/` for snapshot counts.
  - [ ] Unit tests in `halbert_core/tests/test_recent_configs.py`.

### Phase 3: Recent Configs Surface & Navigation (Frontend)
- [ ] **`RecentConfigsDock.tsx` (New Component)**:
  - [ ] Collapsible dock in `Layout.tsx` or `AgentChat.tsx`.
  - [ ] Displays recent configs with relative timestamps, actors, and reasons.
  - [ ] Connects click to open `ConfigEditor.tsx` with diff view.
  - [ ] Connects "Jump to Chat" click to trigger `Timeline.tsx` anchored turn jump.

### Phase 4: Safe Surgery & Rollback
- [ ] Connect `editor.py` automatic backups to all agent file writes (`apply_diff` / `write_file`).
- [ ] Add 1-click **"Rollback Change"** button on `DiffBlock.tsx` and turn articles.

---

## 6. Verification Plan

1. **CLI Rendering**: Run commands in `AgentChat` (`systemctl status`, `ls -la`, `cat /etc/hosts`). Verify no `{}` brackets appear, headers display `$ <cmd>`, and outputs $> 6$ lines collapse cleanly.
2. **Inspection Grouping**: Trigger a multi-file read/grep turn. Verify that individual cards do not flood the chat; verify the `InspectionGroup` pill summarizes the steps.
3. **Recent Configs Route**: `curl -s http://localhost:8000/api/continuity/recent-configs` returns valid JSON with paths, timestamps, actors, and reasons.
4. **Dock & Anchored Jump**: Edit `/etc/samba/smb.conf` via chat. Verify it appears in the Recent Configs dock. Clicking "Jump to Chat" scrolls to the exact turn and activates `anchored={true}` mode.
