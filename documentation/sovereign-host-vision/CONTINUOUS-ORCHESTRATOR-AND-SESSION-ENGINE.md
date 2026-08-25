# The Continuous Orchestrator Mind & Autonomous Session Engine

**Version:** 1.0.0  
**Date:** August 2026  
**Status:** Core Architectural Specification  
**Reads with:**
- [README.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/README.md)
- [SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md)
- [SUBAGENTS-AND-TASK-DAEMONS.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/SUBAGENTS-AND-TASK-DAEMONS.md)
- [STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md)
- [ORGANIC-INTERACTIONS-AND-WORKFLOWS.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/ORGANIC-INTERACTIONS-AND-WORKFLOWS.md)

---

## 1. Executive Summary: The "Zero-Manual-Session" Paradigm

In today's AI tools (ChatGPT, Claude, Claude Code, Cursor, Warp AI), session management is a tedious manual burden:
1. **The Session Dumpster:** Users are forced to manage a sidebar list of dozens of cryptic, auto-titled chat sessions (`"Help with config"`, `"Docker fix"`, `"Debug network"`).
2. **The `--resume` Chore:** In CLI agents like Claude Code, users must manually remember session IDs or pass flags like `--resume <uuid>` to continue past work; otherwise, the tool boots with total amnesia.
3. **Context Fragmentation:** If you need to run a background diagnostic while asking a question, you must open a second tab or new window manually.

### The Halbert Breakthrough: The Continuous Orchestrator Mind
Halbert eliminates manual session management entirely:
* **One Lifelong Host Timeline:** You never click "New Chat" and you never pass `--resume`. You just start speaking to your computer.
* **Autonomous Session Affinity Router:** The top-level **Orchestrator Mind** evaluates your intent in real-time. If you reference a past task (*"Let's finish that WireGuard MTU tuning from last week"*), Halbert automatically identifies the relevant thread, retrieves its compacted state, and re-anchors the context without human intervention.
* **Autonomous Subagent Forking:** If you ask Halbert to perform a deep diagnostic while continuing to chat (*"Run a full disk audit while we review these firewall rules"*), the Orchestrator automatically forks a background subagent in an isolated PTY without breaking the active conversation.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE CONTINUOUS ORCHESTRATOR ENGINE                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│               [ User Input: "Let's finish the WireGuard MTU fix" ]           │
│                                    │                                        │
│                                    ▼                                        │
│               ┌─────────────────────────────────────────┐                   │
│               │       TOP-LEVEL ORCHESTRATOR MIND       │                   │
│               │    (Intent & Session Affinity Router)   │                   │
│               └────────────────────┬────────────────────┘                   │
│                                    │                                        │
│       ┌────────────────────────────┼────────────────────────────┐           │
│       ▼                            ▼                            ▼           │
│  [ MATCH FOUND ]           [ NEW TASK/TOPIC ]           [ ASYNC DAEMON ]    │
│  Affinity > 0.85           Affinity < 0.30              Intent: Background  │
│  • Auto-rehydrates         • Inserts ambient topic      • Forks Subagent    │
│    `sess_wg_tuning`          divider in timeline        • Spawns background │
│  • Injects MemoryLOD       • Preserves biographical       PTY tile          │
│    compacted context         continuity                 • Primary chat stays│
│  • Resumes immediately     • Zero manual "New Chat"       free & responsive │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Deconstructing the Precedents: How Claude Code & Warp Work

To understand how Halbert achieves this, we analyze how underlying agent systems manage sessions:

### 2.1 Claude Code / Open-Claude Session Mechanics
* **Session Storage:** Serializes full conversation JSON transcripts to disk (`~/.claude/sessions/{session_id}.json`) containing raw messages, tool invocations, and tool results.
* **Resume Mechanism:** Passing `--resume` loads the raw JSON transcript, reconstructs the message history, and calculates token counts.
* **Compaction / Summarization:** Uses progressive summarization when history exceeds context limits.
* **Limitation:** The user must explicitly choose *which* session to resume from a CLI picker or command-line flag. The tool cannot infer session continuity from natural language.

### 2.2 Warp AI Mechanics
* **Block History:** Groups terminal commands and outputs into an indexed SQLite database.
* **Workflows (Warp Drive):** Static parameterizable runbooks loaded on-demand.
* **Limitation:** Conversational AI is tied to isolated ephemeral panels rather than an autonomous orchestrator managing multi-session context.

### 2.3 Halbert's Synthesis: The Autonomous Autobiographical Graph
Halbert combines **SourcePrep's structural graph**, **Haloysius's turn engine**, and a **Hierarchical SQLite Session Catalog** to turn raw session transcripts into an **Associative Knowledge Graph**.

---

## 3. The 3-Layer Orchestrator Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       THE 3-LAYER ORCHESTRATOR STACK                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ LAYER 1: THE CONTINUOUS TIMELINE (The Single Stream UI)             │   │
│   │ • No "New Chat" button. The conversation is continuous over days.   │   │
│   │ • Subtle temporal dividers: [Monday, Aug 24] [System Boot 08:30]    │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                      │
│   ┌──────────────────────────────────┴──────────────────────────────────┐   │
│   │ LAYER 2: THE CEREBELLAR SESSION ROUTER (Tier 1 Fast Model + FTS5)   │   │
│   │ • Runs a 15ms affinity pass on every user prompt.                   │   │
│   │ • Computes entity overlap (files, packages, PIDs, dates, intents).  │   │
│   │ • Decides: Re-anchor existing thread vs. Branch new topic.          │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                      │
│   ┌──────────────────────────────────┴──────────────────────────────────┐   │
│   │ LAYER 3: AUTONOMOUS SUBAGENT FORKER & CONTEXT COMPACTOR             │   │
│   │ • Dispatches asynchronous tasks into isolated PTY subagents.        │   │
│   │ • Applies 3-tier compression (MemoryLOD + Semantic) to past threads.│   │
│   │ • Nightly 03:00 "Dream Cycle" synthesizes threads into Concepts.    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. How the Session Affinity Router Works (The Math & Mechanics)

When a user submits a prompt, before the main conversational model is invoked, the **Cerebellar Session Router** executes a rapid triage:

### Step 1: Entity & Temporal Extraction
* Input: *"Can we continue the WireGuard MTU tuning we started last Tuesday?"*
* Extracted Entities: `topic: wireguard`, `parameter: MTU`, `time_anchor: last Tuesday (2026-08-18)`, `action: continue`.

### Step 2: Affinity Scoring ($S_{\text{affinity}}$)
The router queries the SQLite Session Catalog and SourcePrep concepts using hybrid search (FTS5 + ONNX embedding cosine similarity + temporal decay):

$$S_{\text{affinity}} = 0.4 \cdot S_{\text{semantic}} + 0.3 \cdot S_{\text{entity}} + 0.3 \cdot S_{\text{temporal}}$$

* **Result for `thread_wg_20260818`:** $S_{\text{affinity}} = 0.92$ (High Confidence Match).

### Step 3: Execution Routing Policy
1. **High Match ($S_{\text{affinity}} \ge 0.75$):** 
   - Halbert automatically re-hydrates the thread's compacted summary (Level 2 LOD: decisions made, files modified, pending tasks).
   - Halbert responds in-line:
     > *"Resuming our WireGuard MTU tuning from August 18. We last verified that MTU 1420 resolved packet fragmentation on `wg0`. Here is where we left off: [View Previous Diff]."*
2. **Ambiguous Match ($0.45 \le S_{\text{affinity}} < 0.75$):**
   - Halbert presents a non-intrusive ambient chip in the prompt gutter:
     `[Link to Aug 18 WireGuard Thread?]`.
3. **Low Match ($S_{\text{affinity}} < 0.45$):**
   - Treated as a fresh topic within the continuous timeline. Halbert inserts an ambient topic marker (`─── Topic: Storage Optimization ───`) and allocates a clean working context buffer.

---

## 5. Autonomous Subagent Forking: Multitasking Without Window Clutter

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PARALLEL EXECUTION WITHOUT AMNESIA                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User: "Run a full SMART scan on /dev/nvme0n1 while we fix this firewall." │
│                                                                             │
│   Orchestrator Mind Analysis:                                               │
│   • Intent 1: "Run full SMART scan" -> Asynchronous, I/O heavy (Subagent)   │
│   • Intent 2: "Fix firewall"        -> Synchronous, Conversational (Primary)│
│                                                                             │
│   Execution Action:                                                         │
│   1. Spawns `StorageAuditorAgent` in isolated background PTY.               │
│   2. Docks subagent terminal tile into Right-Column Accordion.              │
│   3. Halbert immediately answers Intent 2 in chat:                          │
│      "I have dispatched `StorageAuditor` to run the extended SMART test on  │
│       /dev/nvme0n1 in the background. Now, regarding your firewall:         │
│       I see port 22 is currently open to all interfaces..."                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why This Is Better Than Traditional CLI Tools:
* In Claude Code or standard terminals, running a 10-minute scan blocks the user from continuing to interact unless they open a separate terminal window and lose their AI session context.
* In Halbert, the **Orchestrator Mind seamlessly multiplexes**: heavy background tasks run as child daemons, while the conversational spine remains instant, attentive, and fully context-aware.

---

## 6. The Subconscious Consolidation ("Dream Cycle")

How does Halbert keep this session graph clean without requiring manual human maintenance?

Every night at **03:00** (or during system idle periods):
1. **Thread Compaction:** Completed threads are compressed using the 3-tier cascade (`MemoryLOD`). Raw log dumps are pruned; key decisions, file diffs, and rationale are preserved.
2. **SourcePrep Concept Ingestion:** Any resolved config rationale (e.g. *"Why is MTU set to 1420 on wg0?"*) is anchored into SourcePrep's `concepts/` directory.
3. **Session Auto-Graphing:** The SQLite catalog automatically tags and clusters threads by system subsystem (`network`, `storage`, `docker`, `security`), building a rich knowledge web of the machine's life.

---

## 7. Data Contract: SQLite Session Graph Schema

```sql
CREATE TABLE host_sessions (
    id TEXT PRIMARY KEY,               -- e.g. "sess_01J5K99"
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL,              -- "active", "paused", "completed"
    title TEXT NOT NULL,               -- Auto-generated summary title
    topic_category TEXT NOT NULL,      -- "network", "storage", "security", etc.
    entities_json TEXT NOT NULL,       -- Touched files, services, packages, PIDs
    compacted_summary TEXT NOT NULL,   -- MemoryLOD Level 2/3 summary
    embedding BLOB,                    -- 384-dim vector for semantic search (deferred)
    parent_session_id TEXT             -- For subagent / forked threads
);

CREATE TABLE session_somatic_blocks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES host_sessions(id),
    block_type TEXT NOT NULL,          -- "sensory", "deliberation", "proposal", "action"
    payload_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

---

## 8. Codebase Reality Check (August 2026 Audit)

### 8.1 Sessions Are JSON Files, Not SQLite

`agents/conversation.py` `ConversationStore` (lines 201-355) writes conversations to `~/.halbert/conversations/{id}.json` — individual JSON files on disk. The `search()` method (line 326) is a **linear scan** of all JSON files, loading and parsing each one. There is:
- No SQLite database
- No FTS5 index
- No embedding column
- No affinity scoring
- No `host_sessions` or `session_somatic_blocks` tables

The schema in §7 above is the **target**, not the current state. Migrating from JSON to SQLite + FTS5 is ~120 lines and is Stage 3 of the build plan.

### 8.2 The Session Affinity Router Does Not Exist

The 3-step routing pipeline (§4: entity extraction → affinity scoring → execution routing) is pure spec. No code implements:
- Entity & temporal extraction from user prompts (though `intake/signals.py` could be extended for this)
- $S_{\text{affinity}}$ scoring with FTS5 + ONNX embeddings + temporal decay
- The high/ambiguous/low match routing policy

### 8.3 Contradiction With the Feasibility Doc — Resolved

**The orchestrator doc (§4) prescribes** a 15ms affinity pass with ONNX embeddings + FTS5 + temporal decay on every prompt.

**The feasibility doc (§4) prescribes** deterministic FTS5-only routing and explicitly warns: *"never run an expensive, slow, non-deterministic LLM classifier on every keystroke."*

**Resolution: The feasibility doc is correct.** The routing pipeline should be:
1. **Default (90% of turns):** Stay in current session. Zero routing overhead.
2. **Explicit keyword (10%):** FTS5 search on session summaries in <5ms. No embeddings.
3. **Embeddings deferred:** Only use ONNX cosine similarity for the ambiguous-match tier (0.45 ≤ score < 0.75), and only when FTS5 returns candidates. Do not run embeddings on every prompt.

The `embedding BLOB` column in the §7 schema is marked `(deferred)` to reflect this.

### 8.4 Subagent Forking Does Not Exist

The autonomous subagent forking described in §5 is not implemented. See the SUBAGENTS-AND-TASK-DAEMONS doc §5 for the full reality check. The orchestrator cannot multiplex synchronous chat + asynchronous background tasks until the PTY backend and `spawn_subagent()` method are built.

### 8.5 The Dream Cycle Is Not Scheduled

`proactive/morning_report.py` (225 lines) exists but is not wired to a 03:00 scheduler. The `scheduler/` directory exists but the dream cycle consolidation (thread compaction, SourcePrep concept ingestion, session auto-graphing) is not implemented. This must be **opt-in, not default** — a 03:00 background job that consumes LLM tokens without explicit user consent is a footgun.

### 8.6 The Continuous Timeline UI Does Not Exist

The "no New Chat button, continuous lifelong timeline" (Layer 1, §3) requires frontend changes to `SidePanel.tsx` that have not been made. The current UI has standard conversation list + conversation view. Temporal dividers (`[Monday, Aug 24]`, `[System Boot 08:30]`) are spec only.
