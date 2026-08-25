# Third Pass: Scrutiny — What Breaks, What Works, What's Actually Missing

**Date:** August 25, 2026
**Purpose:** Third-pass scrutiny. Read the tests, compare against Halbert's actual code, identify what will break in production, and list the smallest concrete steps to de-risk the vision. This is the "are we bullshitting ourselves?" pass.

---

## Executive Summary

After two passes of pattern mining and assumption reversal, this pass asks the hard question: **Can Halbert's current code actually support the sovereign-host-vision, and what are the specific failure modes?**

The answer is **no, not as written** — but the gaps are well-defined and smaller than they appear. The biggest risks are not in the novel features (Somatic Blocks, subagents, Living Reflexes) but in the **unsexy infrastructure** between them:

1. **Context assembly will silently eat the conversation history** — the current `_compress_with_cascade()` is a per-source semantic compression that does not preserve turn boundaries or tool call structure.
2. **The terminal route is a `subprocess` time bomb** — `dashboard/routes/terminal.py` uses `asyncio.create_subprocess_shell()` with a 30s timeout, no PTY, no real sandbox, and a naive sudo-stripping hack.
3. **The approval engine has no link to execution** — `ApprovalRequest` and `Proposal` exist but the state machine doesn't wait for approval; it just produces a `pending` proposal and moves on.
4. **The tier router has no memory** — it picks models by heuristic but never records whether they succeeded.
5. **The agent state machine conflates processing state and conversation status** — there's no way to represent "the agent is waiting for a subagent" or "retrying after a model API error."
6. **There are no persisted agent cycles** — `StateContext` is a throwaway scratchpad. There is no `SomaticBlock`, no task tree, no conversation restoration plan.

The good news: the existing modules (`findings/`, `approval/`, `autonomy/`, `context/`, `model/`, `agents/`) are real, tested, and provide the **substrate** for the vision. The work is integration, not invention.

---

## 1. What the Tests Actually Tell Us

### 1.1 open-claude-code v2 `test/test.mjs` — a working reference

The OCC test file is the most valuable artifact from the codebase scan. It proves that the patterns we want to steal are **implemented and tested**, not aspirational. The key findings:

**Context Manager (lines 239-275, 1123-1147):**
- Tested with `new ContextManager(1000)` and synthetic 50-message histories
- `getTokenCount()` uses 4 chars/token heuristic
- `compact()` reduces 100-message arrays to ≤5 messages
- `microCompact()` is tested separately: old tool results (>200 chars) get truncated with `[truncated]` marker
- **Crucial:** the tests use `content` as an array of blocks (not just strings), exactly like Anthropic's API

**What this means for Halbert:** Our `context/assembler.py` does NOT use block arrays. It assembles a single string and then runs the compression cascade on that string. We cannot port OCC's micro-compaction without first representing the conversation as a list of block-typed messages.

**MetaHarness router (lines 1847-1899):**
- `estimateComplexity('what is 2+2')` returns 0
- `estimateComplexity('refactor the distributed concurrency architecture...')` returns >0.5
- Easy tasks route to `claude-haiku-4-5` and **clear the 0.7 quality bar**
- Hard tasks escalate to `claude-opus-4-6`
- `escalate()` is tested as a simple ladder walk
- Recorded stats override the prior: a model with 5 attempts and 0 successes gets routed away from

**What this means for Halbert:** We can port this entire pattern. It is pure code, no dependencies. But we need to decide what our ladder is. Currently `model/tier_router.py` has Guide/Specialist/Vision tiers based on Ollama/Anthropic/OpenAI. We need to map these to a cost/capability ladder.

**Permission / path / injection checks (lines 1256-1430):**
- `Sandbox.wrapCommand()` is tested as a **string transformation**: does the output contain `bwrap`, `--ro-bind`, `sandbox-exec`, etc.
- `checkInjection()` is tested with 10+ dangerous patterns
- `validatePath()` blocks `.env`, `credentials.json`, `.key`, `.pem`, and writes to `/etc`, `/usr`
- `RateLimiter` is tested against 200/429/529 with a 3-retry cap

**What this means for Halbert:** The OCC tests treat sandboxing as a string-wrapping operation. This is fine for a Node.js prototype but **not** for production. Our PTY needs real sandboxing, not command-string wrapping. However, the path/injection checks are directly portable.

**Agent teams (lines 1547-1612):**
- `AgentTeams` is tested with a mock async generator `run(message)`
- `sendMessage()` collects all events from the agent
- `broadcast()` sends to all teammates in parallel
- Duplicate registration throws; unknown teammate throws

**What this means for Halbert:** We don't need to invent a multi-agent protocol. We can implement `SubagentManager` with the same API: `register(name, agent_loop, role)`, `send_message(to, message)`, `broadcast(message)`.

**Scheduler (lines 1691-1738):**
- `create('5m', 'Run tests')` creates a task with `intervalMs=300000`
- `runDue()` checks `now - lastRun >= intervalMs`
- `setEnabled()` toggles without deleting
- Cron expressions default to 5 minutes

**What this means for Halbert:** The scheduler is a JSON file with `setInterval`-style checks. For the sovereign host, we need a persistent scheduler that survives process restarts. JSON is fine for v1, but the **cognitive tick** must call `runDue()` on every cycle.

### 1.2 Warp `task_store.rs` — the production reality

The Warp `TaskStore` (471 lines) is much more sophisticated than OCC's `AgentTeams`:

- It stores a **hash map of tasks** keyed by `TaskId`
- It maintains a **linearized exchange index** (`IndexMap<AIAgentExchangeId, ExchangeRef>`) for O(1) first/last access
- It handles **optimistic root task ID upgrades** (`optimistic_root_task_id`) — when the client creates a task with a temporary ID and the server returns a real ID
- `append_exchange()` has a fast path for DFS-tail appends and a slow path (rebuild index) when an exchange has subagent output
- `modify_task()` accepts a closure, rebuilds the index only if exchange count changed

**What this means for Halbert:** If we want to support nested subagents (subagents spawning subagents) and conversation restoration, we need a task store with an exchange index. SQLite with proper indexing is fine; we don't need Rust's `IndexMap`, but we do need the same semantics.

---

## 2. Halbert's Actual Code vs. the Vision

This section compares the current Halbert implementation against the vision stages. It is intentionally blunt.

### 2.1 Stage 1: Somatic Block Unification

**What the vision assumes:**
- A `SomaticBlock` lifecycle wraps `findings/`, `approval/`, `autonomy/`
- Blocks have 5 phases: Sensory, Deliberation, Proposal, Action, Reflection
- The lifecycle state machine transitions through these phases

**What Halbert actually has:**
- `findings/store.py` — `Finding` with SQLite persistence, 163+ lines
- `findings/proposals.py` — `Proposal` with full status lifecycle (pending → approved → applied → rolled_back)
- `approval/engine.py` — `ApprovalRequest` with PENDING/APPROVED/REJECTED/EXPIRED
- `approval/simulator.py` — `DryRunSimulator` for before/after/diffs
- `autonomy/recovery.py` — `RecoveryExecutor` with rollback/restart/alert/safe-mode
- `autonomy/guardrails.py` — `GuardrailEnforcer` with confidence thresholds

**The gap:**
These are **separate data models** in separate files. There is no unified `SomaticBlock` that references all of them. The `Proposal` has `finding_id` and `approval_request_id`, so the linkage exists at the data level, but there is no lifecycle orchestrator that drives a finding through detection → deliberation → proposal → approval → action → reflection.

**What will break:**
If we try to emit "Somatic Block" SSE events without a unified model, we'll end up with duplicate event types: `finding_detected`, `proposal_created`, `approval_pending`, `action_executed`, `reflection_generated`. The frontend will have to glue them together. This is exactly what we should avoid.

**Concrete step to de-risk:**
Write a `SomaticBlock` dataclass with `block_type`, `status`, `finding_id`, `proposal_id`, `approval_request_id`, `action_id`, `reflection_id`. Don't absorb the existing models — reference them. Add a `SomaticStore` and a `SomaticLifecycle` that calls the existing modules. This is ~150 lines and can be done without changing `findings/`, `approval/`, or `autonomy/`.

### 2.2 Stage 2: Real PTY Backend

**What the vision assumes:**
- Async PTY with ring buffer
- 1MB output limit per session
- TTL reaper
- Bidirectional stdin/stdout WebSocket

**What Halbert actually has (`dashboard/routes/terminal.py` lines 1-220):**\n- `asyncio.create_subprocess_shell()` — NOT a PTY\n- 30-second timeout, then `process.kill()`\n- Safety tiers: SAFE/CAUTION/DANGEROUS/BLOCKED based on substring matching\n- Naive sudo stripping: `command.startswith('sudo ')` → run without sudo\n- No stdin after command submission\n- No resize handling\n- No sandboxing (the "safety" is just a warning and a hard block list)\n\n**The gap:**\nThis is not a PTY. It is a `subprocess` wrapper. The comment at line 5 literally says "Uses subprocess for now - can be upgraded to full PTY later." That is the current state. We cannot build Stage 6 (frontend terminal docking) on top of this because:\n- No real interactive shell — you can't run `vim` or `top`\n- No streaming output — the command runs, then the output is returned\n- No session persistence across commands — each `/exec` call is a new `subprocess`\n- No resize — the frontend can't report terminal dimensions\n- No pseudo-terminal state — no cursor, no ANSI processing, no scrollback\n\n**What will break:**\nEverything that depends on a real PTY. Subagents (Stage 5) that run `smartctl -t long` or `zpool scrub` will block for minutes and the user will see nothing until the command completes. The frontend terminal tile (Stage 6) will show a static output block, not a live stream.\n\n**Concrete step to de-risk:**\nThis is the highest-risk stage. We cannot do a quick wrapper. We need to:\n1. Add a dependency on `aiofiles` or `aiopty`\n2. Implement `PTYSession` with `os.openpty()` on Unix and `winpty`/ConPTY on Windows (or defer Windows)\n3. Replace `create_subprocess_shell()` with `PTYSession`\n4. Add WebSocket route for stdin/stdout/resize\n5. Add ring buffer + TTL reaper\n\n**Estimated real effort:** 600-800 lines, not the 410 I estimated earlier. This is the make-or-break stage.\n\n### 2.3 Stage 3: SQLite Session Store\n\n**What the vision assumes:**\n- Migrate `ConversationStore` from JSON files to SQLite + FTS5\n- `session_somatic_blocks` table for block history\n\n**What Halbert actually has (`agents/conversation.py` lines 1-538):**\n- `ConversationStore` uses JSON files in `~/.local/share/halbert/conversations/`\n- `search()` does a linear scan of JSON files\n- `Session` dataclass with id, topic, created_at, messages, summary\n\n**The gap:**\nThe JSON store works for small numbers of sessions but will degrade as the conversation history grows. FTS5 is a clear win. However, the bigger issue is that **sessions are not linked to Somatic Blocks**. Even after we migrate to SQLite, we need to add the `session_somatic_blocks` table and the `conversation_blocks` table.\n\n**What will break:**\nSession affinity routing (Stage 4) cannot work on a linear JSON scan. It will be too slow for 100+ sessions. Also, session restoration (Stage 6) needs block-level data, not just message lists.\n\n**Concrete step to de-risk:**\nThis is lower risk than PTY. The migration is mechanical:\n1. Define SQLite schema for `sessions`, `session_messages`, `session_blocks`\n2. Write `SessionStore` with CRUD + `search_fts(query)`\n3. Write one-time migration script\n4. Update `ConversationStore` to delegate to `SessionStore`\n\n### 2.4 Stage 4: Session Affinity Router\n\n**What the vision assumes:**\n- Deterministic 3-tier routing: explicit reference → FTS5 search → current session\n- No embeddings on every keystroke\n\n**What Halbert actually has:**\n- `intake/signals.py` — entity extraction (domains, paths, error indicators)\n- `agents/conversation.py:ConversationStore.search()` — linear scan, no ranking\n\n**The gap:**\nWe don't have the router. We don't have the explicit-reference regex. We don't have FTS5. We don't have the ambiguous-match tier (0.45-0.75 score).\n\n**What will break:**\nThe "zero manual session" UX. If a user says "continue that disk issue from yesterday," the agent won't find the right session. Every query will start a new session unless the user explicitly names the old one.\n\n**Concrete step to de-risk:**\nWait for Stage 3 (SQLite + FTS5). Then implement the router in ~100 lines. The regex for explicit references is the tricky part — we should enumerate the patterns: "that X", "the X from Y", "last Z", "continue X", "resume X", "yesterday", "earlier".\n\n### 2.5 Stage 5: Subagent Forking\n\n**What the vision assumes:**\n- `SubagentManager` with `spawn()`, `cancel()`, `list_active()`\n- Concurrency ceiling with FIFO queue\n- `StorageAuditorAgent` as the first subagent\n- Subagent output flows back as Somatic Blocks\n\n**What Halbert actually has:**\n- `agents/react_agent.py` — single ReAct loop, no subagent concept\n- `discovery/scanners/storage.py` — runs `smartctl`, `lsblk`, but synchronously\n- `streaming/emitter.py` — `EventEmitter` with session-scoped queues\n\n**The gap:**\nNo subagent system. The scanner runs in the main agent thread. Long-running audits block the conversation. There is no task tree, no optimistic task creation, no lifecycle event stream.\n\n**What will break:**\nEverything. If `StorageAuditorAgent` runs `smartctl -t long` (which takes minutes), the main agent will block. The user will think the UI is frozen.\n\n**Concrete step to de-risk:**\nBuild the PTY backend (Stage 2) first. Then:\n1. `SubagentManager` with a SQLite task queue (not just `asyncio.Semaphore`)\n2. `StorageAuditorAgent` as a deterministic script that runs in a PTY and streams output\n3. Subagent completion emits a `SomaticBlock` via SSE\n4. Primary agent waits on `WaitingForEvents` conversation status\n\n### 2.6 Stage 6: Frontend Terminal Docking\n\n**What the vision assumes:**\n- `TerminalTile` component in conversation stream\n- `TerminalAccordionDock` in right column\n- `IntersectionObserver` docking at <25% visibility\n- Tether chips\n\n**What Halbert actually has:**\n- `dashboard/frontend/src/pages/Terminal.tsx` — standalone xterm.js page\n- `dashboard/frontend/src/components/SidePanel.tsx` — conversation panel with `PanelMode = 'terminal'`\n- `dashboard/frontend/src/hooks/useAgentStream.ts` — SSE stream consumer\n\n**The gap:**\nThe Terminal page is standalone, not integrated into the conversation stream. The SidePanel has a `PanelMode` toggle but no accordion dock. There is no `IntersectionObserver` logic. There is no `TerminalSessionManager` on the frontend.\n\n**What will break:**\nIf we build the frontend docking without a real PTY (Stage 2), we'll have a beautiful UI over a `subprocess` that returns output after the command finishes. No live streaming, no interaction.\n\n**Concrete step to de-risk:**\nBuild Stage 2 first. Then the frontend is mostly React plumbing:\n1. `useTerminalSessions.ts` — singleton store with WebSocket per session\n2. `TerminalTile.tsx` — inline xterm.js in conversation stream\n3. `TerminalAccordionDock.tsx` — right-column accordion\n4. `useIntersectionDock.ts` — visibility watcher\n\n### 2.7 Stage 7: Living Reflexes\n\n**What the vision assumes:**\n- YAML reflex store\n- Tier 0 trigger matching\n- Reflex synthesis from Reflection blocks\n- Scheduler integration\n\n**What Halbert actually has:**\n- `proactive/morning_report.py` — generates a morning report\n- `proactive/detector_runner.py` — runs discovery scanners\n- No scheduler, no reflex store\n\n**The gap:**\nNo persistence for reflexes. No trigger matching engine. No scheduler to run them. The morning report is a one-off, not a cron job.\n\n**What will break:**\n"When disk health degrades, run this reflex" won't work because there's no persistent trigger matcher or scheduler.\n\n**Concrete step to de-risk:**\n1. Scheduler with JSON persistence (steal from OCC)\n2. `Reflex` YAML/JSON store\n3. `ReflexMatcher` with regex + threshold matching\n4. Wire into `proactive/detector_runner.py` — after detectors run, check reflex triggers\n\n### 2.8 Stage 9: Context Watermark\n\n**What the vision assumes:**\n- 75% token watermark trigger\n- 2-hour temporal gate\n- Topic boundary gate\n- Micro-compaction\n\n**What Halbert actually has (`context/assembler.py` lines 90-725):**\n- `_compressor_threshold = 4000` tokens\n- `_compress_with_cascade()` runs per-source semantic compression\n- It operates on a single assembled string, not a list of message blocks\n- No 2-hour gate, no topic boundary gate, no micro-compaction\n\n**The gap:**\nThe current compression is **content-aware** (per source type) but **turn-agnostic**. It will compress the conversation history into a single blob, losing the distinction between user messages, assistant messages, and tool results. It does not preserve the structure needed for context re-anchoring or reflection synthesis.\n\n**What will break:**\nLong conversations will lose tool call history. The agent won't remember what it did 20 turns ago because the tool results were compressed away. The `SomaticBlock` history will be incomplete.\n\n**Concrete step to de-risk:**\n1. Change the conversation representation from a single string to a list of block-typed messages\n2. Add micro-compaction: truncate old tool results >200 chars\n3. Add full-compaction with LLM summary when micro isn't enough\n4. Add 2-hour and topic-boundary gates\n5. Keep the existing semantic compression for retrieval/memory sources\n\n---

## 3. The 5 Highest-Risk Gaps (Ranked)

### 3.1 PTY Backend (Stage 2) — CRITICAL

**Risk:** The current `dashboard/routes/terminal.py` is a `subprocess` wrapper, not a PTY. Subagents, terminal streaming, and frontend docking all depend on this.

**Why it will break in production:**
- `asyncio.create_subprocess_shell()` cannot run interactive programs (`vim`, `top`, `sudo` password prompts)
- No streaming — output is returned when the process exits
- No session state — each call is a new process
- No resize — the frontend terminal dimensions don't affect the child process
- Sudo stripping is dangerous: `sudo apt update` becomes `apt update` and fails with a confusing message

**What we must build:**
A real `PTYSession` using `os.openpty()` or `aiofiles` + `fcntl`. This is not a small feature. It needs:
- Master/slave file descriptors
- Async read loop
- Resize (`SIGWINCH`) handling
- Ring buffer for scrollback
- TTL reaper for idle sessions
- WebSocket bridge for stdin/stdout/resize
- Sandbox integration (bubblewrap/seatbelt)

**Minimum viable:** Unix-only PTY with `aiofiles`, 1MB buffer, 60s TTL, WebSocket bridge. Skip Windows for v1.

### 3.2 Conversation State Representation — CRITICAL

**Risk:** Halbert has `AgentState` (processing states) but no `ConversationStatus` (user-facing states). The vision's `TransientError`, `Blocked`, `WaitingForEvents` have no equivalent.

**Why it will break in production:**
- Model API failures go to `ERROR` state and stop. There's no retry state.
- Pending approvals don't pause the conversation. The agent moves on.
- Subagent completion is not a first-class state. The agent has no clean way to wait.

**What we must build:**
A separate `ConversationStatus` enum and state machine. It must coexist with `AgentState`. The UI renders conversation status; the agent engine uses agent state.

### 3.3 Context Compaction — HIGH

**Risk:** The current compression cascade destroys conversation turn structure.

**Why it will break in production:**
- Tool results are compressed into a single semantic blob
- The agent loses the trace of "I ran X and got Y"
- Long-running sessions (the whole point of the sovereign host) will forget their own history

**What we must build:**
A two-tier compaction that preserves block structure: micro-compaction (truncate old tool results) + full-compaction (LLM summary). The conversation must be represented as a list of block-typed messages, not a single string.

### 3.4 Model Router Has No Memory — HIGH

**Risk:** `model/tier_router.py` picks a model by heuristic but never learns from outcomes.

**Why it will break in production:**
- The specialist model may be overused for trivial queries
- The guide model may be used for tasks it consistently fails
- No cost optimization over time

**What we must build:**
Outcome store (JSONL or SQLite) + blending formula from OCC. Record every model call: model, success, latency, tokens, cost, complexity. After 3+ samples, stats override the heuristic prior.

### 3.5 Approval-to-Execution Gap — HIGH

**Risk:** `ApprovalEngine` and `ProposalStore` exist, but the state machine doesn't wait for user approval.

**Why it will break in production:**
- The agent creates a proposal and immediately tries to execute (or moves on)
- There is no `AWAITING_CONFIRMATION` → execute flow
- The user gets a proposal notification but no chance to approve before execution

**What we must build:**
A state machine transition that stops at `AWAITING_CONFIRMATION`, emits a `ConversationStatus::Blocked { blocked_action }` event, and only proceeds to `EXECUTING` when the user approves. This needs to be wired through the SSE stream and the frontend.

---

## 4. What Is Actually Working and Should Not Be Replaced

### 4.1 `findings/` module

`findings/store.py`, `findings/proposals.py`, `findings/blast_radius.py`, and `findings/precedence.py` are real, tested, and functional. The `Proposal` lifecycle (pending → approved → applied → rolled_back) is exactly what the Somatic Block Action phase needs. **Do not rewrite.** Wrap.

### 4.2 `approval/engine.py`

The approval workflow dataclasses are solid. The gap is integration, not the data model. **Do not rewrite.** Add a `ConversationStatus::Blocked` event and a state machine transition.

### 4.3 `autonomy/recovery.py`

The `RecoveryExecutor` has the right actions (rollback, restart, alert, safe-mode). The rollback implementation uses `.bak` files. **Do not rewrite.** Add per-file checkpoints (OCC pattern) before actions, and wire rollback into the Somatic Block reflection phase.

### 4.4 `intake/signals.py`

Entity extraction is fast and works. It detects domains, paths, and error indicators. **Do not rewrite.** Use it for the session router's entity extraction step.

### 4.5 `agents/state_machine.py`

The state machine has the right structure. The gap is conversation-level status and subagent integration. **Do not rewrite.** Extend.

---

## 5. Revised, De-Risked Implementation Order

The original 9-stage strategy is theoretically correct but the dependencies are too loose. This is a more realistic order that respects the actual risks:

### Phase A: Foundation (do these first, in order)

**A1. Conversation as blocks (1-2 days)**
- Change `StateContext.conversation_history` from list of strings to list of block-typed messages
- This unblocks context compaction, Somatic Blocks, and conversation restoration

**A2. Conversation status state machine (1-2 days)**
- Add `ConversationStatus` enum: `InProgress`, `Success`, `Error`, `TransientError`, `Cancelled`, `Blocked { blocked_action }`, `WaitingForEvents`
- Wire into `agents/state_machine.py` and SSE events
- This unblocks approval gating and subagent waiting

**A3. Outcome store (1 day)**
- Add `OutcomeStore` JSONL/SQLite
- Record every model call
- This unblocks the cost-cascade router

### Phase B: PTY (the hard part)

**B1. Real PTY backend (5-7 days)**
- Implement `PTYSession` with `os.openpty()`
- `TerminalSessionManager` with ring buffer + TTL reaper
- WebSocket bridge for stdin/stdout/resize
- This is the longest stage and blocks subagents and frontend docking

### Phase C: Somatic Blocks and integration (after A1-A3)

**C1. Somatic Block dataclass + store (2 days)**
- `SomaticBlock` references `finding_id`, `proposal_id`, `approval_request_id`
- `SomaticStore` SQLite
- `SomaticLifecycle` state machine

**C2. Cost-cascade router (2 days)**
- Merge `intake/complexity.py` and `model/tier_router.py:_score_complexity()`
- Add `MetaHarnessRouter` pattern
- Add `OutcomeStore` integration

### Phase D: Subagents (after B1)

**D1. Subagent task store + spawn (3 days)**
- `SubagentManager` with SQLite queue
- `StorageAuditorAgent` deterministic script
- Subagent lifecycle event stream

### Phase E: Frontend (after B1 and C1)

**E1. Terminal tiles and docking (3 days)**
- `TerminalTile`, `TerminalAccordionDock`, `IntersectionObserver` hook
- Frontend `TerminalSessionManager` WebSocket

### Phase F: Advanced features (after C, D, E)

**F1. SQLite session store + FTS5 (2 days)**
**F2. Session affinity router (1-2 days)**
**F3. Living Reflexes (2-3 days)**
**F4. Context watermark (2 days)**

---

## 6. What to Cut to De-Risk v1

If the goal is a working v1 sovereign host, cut these:

1. **Windows PTY support** — support macOS and Linux only for v1. Windows is a huge additional effort.
2. **Multi-provider dispatch** — stick with the existing `model/tier_router.py` providers. OCC's multi-provider abstraction is nice but not critical.
3. **Remote subagents** — run all subagents on the local host for v1. Remote execution is a future feature.
4. **Workflow sharing / source_url** — keep reflexes local for v1.
5. **Embedding-based session routing** — use FTS5 only, as the feasibility doc already recommends.
6. **GSAP FLIP animations** — ship the dock first, animate later.
7. **Dream Cycle 03:00 scheduler** — require explicit user opt-in and use a simple cron. The 03:00 default is a bad idea without robust scheduling.

---

## 7. The Honest Verdict

The sovereign-host-vision is **feasible** but **not a 9-stage checklist**. It is a small number of hard infrastructure problems (PTY, conversation state, context compaction) plus a larger number of integration steps.

The current Halbert codebase is **not a greenfield project**. It has real, working modules that provide 60-70% of the substrate. The biggest mistake would be to rewrite `findings/`, `approval/`, `autonomy/`, or `agents/state_machine.py`. The right approach is to:

1. **Add a `ConversationStatus` layer** on top of the existing agent state machine
2. **Add a `SomaticBlock` layer** that references the existing data models
3. **Replace the `subprocess` terminal with a real PTY**
4. **Fix the context representation** to preserve block-typed messages
5. **Add a subagent task queue** on top of the PTY

If we do these five things, the rest of the vision (reflexes, session routing, frontend docking) becomes integration work, not invention.

The estimate should be revised upward: **~4,500-5,000 lines and 6-8 weeks of focused work**, not the 3,620 lines I estimated earlier. The PTY alone is 600-800 lines. The conversation state rework touches many files. But the foundation is solid.