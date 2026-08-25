# Feasibility, Context Compaction & Resource Engineering Realities

**Version:** 1.0.0  
**Date:** August 2026  
**Status:** Engineering Reality Check & Critical Feasibility Assessment  
**Reads with:**
- [README.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/README.md)
- [CONTINUOUS-ORCHESTRATOR-AND-SESSION-ENGINE.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/CONTINUOUS-ORCHESTRATOR-AND-SESSION-ENGINE.md)
- [SUBAGENTS-AND-TASK-DAEMONS.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/SUBAGENTS-AND-TASK-DAEMONS.md)
- [STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md)

---

## 1. Executive Reality Check: De-Mystifying the Orchestrator

The concept of a *"Continuous Orchestrator Mind that manages all sessions automatically"* sounds ambitious, but if architected naively as a swarm of autonomous LLMs polling in loops, it will quickly suffer from:
1. **Context Window Exhaustion:** Unbounded message histories causing latency spikes, token cost explosion, and severe model amnesia/hallucination.
2. **RAM / VRAM Zombie Bleed:** Background subagents, orphaned PTY terminal pipes, and resident model weights holding gigabytes of host RAM.
3. **Over-Engineered Routing:** Fragile, slow AI routers trying to guess user intent on every keystroke and misrouting conversations.

This document presents the **deterministic, lightweight engineering realities** that make this architecture robust, resource-safe, and straightforward to implement.

---

## 2. Hurdle 1: Context Compaction & "When to Clear"

### How Claude Code Solves It Under the Hood
In Claude Code:
1. **Token Watermark Trigger:** It continuously calculates `current_tokens / max_context_tokens`. When context reaches **75%** of the model limit:
   - It pauses the agentic loop.
   - Dispatches a compact summarization prompt: `"Summarize the key decisions, modified files, and pending goals so far."`
   - Replaces all older messages with the single summary block.
2. **Immediate Tool Output Truncation:** Large bash command outputs (e.g. 500 lines of `grep` or `ls`) are **not** kept in active prompt memory. Once the turn completes, the raw stdout is dropped from prompt context, leaving only `{command, exit_code, 3-line summary}`.

### The Halbert "Stateless Assembler" Pattern (Zero-Manual-Clear)
In Halbert, the user experiences a continuous lifelong timeline, but **the LLM prompt never sees more than 4,000–8,000 tokens**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE ASSEMBLED CONTEXT SLICE (4,000 TOKENS)               │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. SYSTEM IDENTITY & HOST BIO (~600 tokens)                                 │
│    "You are Halbert on halbert-node-01 (Ubuntu 24.04, 64GB RAM)..."         │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. SOURCEPREP EPIDEMIOLOGICAL KNOWLEDGE & AST (~1,200 tokens)               │
│    Relevant config chunks, sysctl params, man pages for active query.       │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. ROLLING SESSION SUMMARY (~600 tokens)                                    │
│    Compact summary of previous turns in current topic (Level 2/3 MemoryLOD).│
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. RAW RECENT TURNS (~1,600 tokens)                                         │
│    Last 6 to 10 messages word-for-word.                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### When Does Halbert "Clear" Context Under the Hood?
"Clearing context" does **not** mean wiping the database. It means resetting the **Prompt Assembly Window**:
1. **Temporal Inactivity Gate:** If $> 2 \text{ hours}$ pass between messages, the assembler starts a fresh working context slice. Old turns are committed to SQLite, and only the latest summary is passed.
2. **Topic Boundary Gate:** If the user shifts domain (e.g. finishes SSH debugging and starts asking about ZFS scrubs), the assembler archives the SSH context and initializes a fresh focus window.
3. **Hard Token Cap (The 4,000 Token Ceiling):** Implemented directly in `halbert_core/context/assembler.py` using `_compress_with_cascade()`. If context exceeds threshold, `MemoryLOD` and `SemanticCompressor` prune old turns automatically.

---

## 3. Hurdle 2: RAM, VRAM & Subagent Lifecycle Gates

To prevent Halbert from consuming host memory or leaking background processes, we enforce **strict deterministic boundaries**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       RESOURCE GOVERNANCE & GATES                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ GATE 1: STATELESS IDLE SESSIONS (0 Bytes RAM)                       │   │
│   │ Sessions are NOT resident in RAM. They are rows in SQLite on disk.  │   │
│   │ An idle session consumes 0 bytes of RAM and 0 CPU cycles.           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ GATE 2: CONCURRENCY CEILING (Max 2 Background Workers)              │   │
│   │ Halbert limits active background subagents to N=2. Additional       │   │
│   │ audit tasks are queued in SQLite (FIFO).                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ GATE 3: HARD EXECUTION TIMEOUTS (TTL Reaper)                        │   │
│   │ • Diagnostic Subagents: 5-minute hard timeout.                      │   │
│   │ • Long-Running Task Daemons: 30-minute hard timeout.                │   │
│   │ • Inactive PTYs: Auto-suspended if idle for >60 seconds.            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ GATE 4: RING-BUFFERED PTY OUTPUT (1 MB Max RAM)                     │   │
│   │ Terminal stdout streams into a 1MB circular memory buffer.          │   │
│   │ Overflow is flushed to `/tmp/halbert/terminals/{id}.log` on disk.   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Hurdle 3: Pragmatic Session Routing (Avoiding Over-Engineering)

We must **never** run an expensive, slow, non-deterministic LLM classifier on every keystroke just to guess session routing. That is a guaranteed failure mode.

### The 3-Tier Deterministic Routing Pipeline:

```python
# Conceptual Routing Logic in ContextAssembler
async def route_session_context(user_query: str, current_session_id: str) -> str:
    # 1. Default Case (90% of turns): Stay in active thread
    if not contains_explicit_past_reference(user_query):
        return current_session_id

    # 2. Fast Exact/FTS5 Search (10% of turns):
    # Query SQLite thread summaries for keywords ("wireguard", "MTU", "last Tuesday")
    matched_session = sqlite_search_threads(user_query)
    
    if matched_session and matched_session.score > 0.80:
        # Seamlessly load the past session's compacted summary
        return matched_session.id
    
    # 3. Fallback: Stay in current session and let model search via SourcePrep
    return current_session_id
```

1. **Default Rule (90% of user turns):** The prompt simply appends to the current working session. Zero routing overhead.
2. **Explicit Keyword Rule (10% of user turns):** If the user mentions a specific past topic (*"that WireGuard issue"*, *"the backup error from yesterday"*), SQLite FTS5 searches thread summaries in $<5\text{ms}$.
3. **Subagent Spawning:** Subagents are **never** spawned by ambient guessing. They are spawned **only** when:
   - The primary agent explicitly issues an `invoke_subagent` tool call (e.g. when instructed to run a full system audit).
   - The user explicitly clicks a button (`[🔍 Spawn Investigator Subagent]`).

---

## 5. Concrete Implementation Roadmap in `halbert_core`

All necessary building blocks already exist in the codebase. Here is where the work lives:

| Component | Target File | What to Implement | Lines of Code |
|---|---|---|---|
| **Context Watermark & Truncation** | `halbert_core/context/assembler.py` | Add 75% token watermark check and wire `conversation/summarization.py` to compact turns older than $N=6$. | ~60 lines |
| **Stateless SQLite Session Store** | `halbert_core/agents/conversation.py` | Persist conversation turns directly into SQLite with auto-generated thread summaries. | ~120 lines |
| **PTY Process Reaper & Ring Buffer** | `halbert_core/dashboard/routes/terminal.py` | Add 5-minute TTL reaper and 1MB circular buffer for streaming PTYs. | ~90 lines |
| **Ephemeral Subagent Loop** | `halbert_core/agents/react_agent.py` | Implement `spawn_subagent()` method that executes a scoped child ReAct loop in a child PTY. | ~150 lines |

### Summary Feasibility Verdict:
* **Is it feasible?** **Yes, 100%.**
* **Why it's tractable:** By making sessions stateless in SQLite, enforcing strict PTY timeouts, using the existing 3-tier compression cascade (`MemoryLOD`), and relying on fast FTS5 keyword lookups instead of slow AI routers, the implementation requires only **~420 lines of clean Python code** across 4 existing modules.
