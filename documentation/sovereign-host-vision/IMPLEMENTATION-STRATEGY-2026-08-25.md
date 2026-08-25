# Implementation Strategy v2.0: Sovereign Host Vision

**Version:** 2.0.0
**Date:** August 25, 2026
**Status:** De-risked strategy grounded in three-pass codebase audit
**Supersedes:** [IMPLEMENTATION-STRATEGY-2026-08-24.md](IMPLEMENTATION-STRATEGY-2026-08-24.md) (v1.0)

**Reads with:**
- [CROSS-CODEBASE-PATTERN-INVENTORY.md](CROSS-CODEBASE-PATTERN-INVENTORY.md) — 25 patterns mined from OCC and Warp
- [SECOND-PASS-REVERSE-ENGINEERING.md](SECOND-PASS-REVERSE-ENGINEERING.md) — line-by-line re-examination of 8 key patterns
- [THIRD-PASS-SCRUTINY.md](THIRD-PASS-SCRUTINY.md) — tests-vs-implementation scrutiny, 5 highest-risk gaps
- [FEASIBILITY-AND-ENGINEERING-REALITIES.md](FEASIBILITY-AND-ENGINEERING-REALITIES.md) — engineering constraints
- [SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md](SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md) — block lifecycle spec
- [SUBAGENTS-AND-TASK-DAEMONS.md](SUBAGENTS-AND-TASK-DAEMONS.md) — subagent spec
- [STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md](STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md) — terminal UI spec

---

## 1. What Changed Since v1.0

The v1.0 strategy (August 24) was written from a single-pass pattern inventory. Since then, two more passes have grounded the strategy in the actual code:

| Pass | What it did | Impact on strategy |
|---|---|---|
| **First pass** (pattern inventory) | Mined 25 patterns from OCC and Warp | Identified what to steal |
| **Second pass** (reverse-engineering) | Re-read 8 patterns line-by-line, challenged assumptions | Corrected 10 assumptions; found that OCC's cost-cascade has a blending cap, Warp's Block is terminal-specific not generic, only 4 of 6 hook events are implemented, bubblewrap doesn't isolate network |
| **Third pass** (scrutiny) | Read OCC's test suite, Warp's task_store, Halbert's actual code | Found 5 critical gaps: PTY is a subprocess wrapper, context compression destroys turn structure, approval isn't wired to execution, tier router has no memory, no conversation-level status |

### Key corrections from v1.0

1. **Effort estimate was too low.** v1.0 estimated ~2,670 lines. The third pass found the PTY alone is 600-800 lines (not 260), and the conversation state rework touches many files. Revised estimate: **~4,500-5,000 lines**.

2. **Stage order didn't respect actual risks.** v1.0 said Stages 1-3 can all start in parallel. The third pass found that Stage 1 (Somatic Blocks) depends on a conversation representation change (strings → block-typed messages) that v1.0 didn't mention at all. The new order has a Foundation phase (A) before anything else.

3. **13 open questions are now answerable.** v1.0 listed 13 open questions. The second and third passes resolved all of them. See §3 below.

4. **The "do not rewrite" list is new.** v1.0 didn't explicitly call out which existing modules to preserve. The third pass identified `findings/`, `approval/`, `autonomy/`, `intake/signals.py`, and `agents/state_machine.py` as solid substrates that should be wrapped, not rewritten.

5. **The cut list is new.** v1.0 deferred 7 features. The third pass added 7 more cuts for v1 de-risking, including Windows PTY, multi-provider dispatch, remote subagents, and the Dream Cycle 03:00 scheduler.

---

## 2. The De-Risked Implementation Order

v1.0 had 9 stages in a flat dependency graph. v2.0 has 6 phases in a strict order that respects the actual risks identified in the third pass.

```
Phase A: Foundation (must be first)
  A1. Conversation as block-typed messages
  A2. Conversation status state machine
  A3. Outcome store
       │
       ▼
Phase B: PTY (the hard part — blocks everything downstream)
  B1. Real PTY backend
       │
       ├─── Phase C: Somatic Blocks (after A1-A3)
       │    C1. Somatic Block dataclass + store
       │    C2. Cost-cascade router
       │         │
       │         ▼
       │    Phase D: Subagents (after B1 + C1)
       │    D1. Subagent task store + spawn
       │         │
       │         ▼
       │    Phase E: Frontend (after B1 + C1)
       │    E1. Terminal tiles and docking
       │         │
       │         ▼
       │    Phase F: Advanced features (after C, D, E)
       │    F1. SQLite session store + FTS5
       │    F2. Session affinity router
       │    F3. Living Reflexes
       │    F4. Context watermark
```

**Why this order:**
- **A1 must be first** because Somatic Blocks, context compaction, and conversation restoration all need block-typed messages. Without this, every downstream stage has to work around the string-based representation.
- **A2 must be before subagents** because `WaitingForEvents` and `Blocked` conversation statuses are how the primary agent waits for subagent completion and user approval.
- **A3 must be before the cost-cascade router** because the router needs outcome data to self-tune.
- **B1 blocks D1 and E1** because subagents run in PTYs and the frontend renders PTY output. Without a real PTY, both are built on sand.
- **C1 blocks D1** because subagent completion emits a Somatic Block.
- **F1-F4 are integration work** that can proceed once the foundation is solid.

---

## 3. Resolved Open Questions (from v1.0 §8)

The v1.0 strategy listed 13 open questions. All are now resolved by the second and third passes.

### Architecture-Level

**Q1: Does `SomaticBlock` reference or absorb?**
**Resolved: Reference.** The `Proposal` already has `finding_id` and `approval_request_id` fields. `SomaticBlock` follows the same pattern: it carries `finding_id`, `proposal_id`, `approval_request_id`, `action_id`, `reflection_id` as foreign keys. The existing data models stay in their modules. `SomaticBlock` is a thin orchestrator that references them. This is cleaner for the frontend (one query to get the block, then lazy-load linked entities) and preserves the existing SQLite schemas.

**Q2: Does the lifecycle state machine extend `AgentStateMachine`?**
**Resolved: Separate, but coordinated.** `SomaticLifecycle` is a separate state machine in `somatic/lifecycle.py`. It does NOT extend `AgentStateMachine`. The two coordinate via the `StateContext`: when `AgentStateMachine` enters REFLECTING, it calls `SomaticLifecycle.advance_to_reflection()`. When `SomaticLifecycle` reaches the Action phase, it sets `StateContext.pending_confirmation` which triggers `AgentStateMachine` to enter AWAITING_CONFIRMATION. This avoids bloating `AgentStateMachine` with block-specific transitions while keeping the two in sync.

**Q3: How do existing ROADMAP Phases 6-8 fold in?**
**Resolved: As stated in v1.0 §6.** Phase 6 (being config + voice) builds in parallel with Phase C. Phase 7 (SSE transport) folds into Phase C (Somatic Blocks need push transport). Phase 8 (module registry) folds into Phase D (subagent output is the first module). No hidden dependencies found.

### Stage 1 (Somatic Blocks)

**Q4: How does the Haloysius cognitive tick feed the Reflection block?**
**Resolved: The block wraps the tick's output.** The cognitive tick runs in `AgentStateMachine.REFLECTING` and produces a `PersonaCognition` result. `SomaticLifecycle.advance_to_reflection()` takes that result and creates a `SomaticBlock(type=Reflection, reflection_data=tick_output)`. The block is the persistence layer for the tick; the tick doesn't know about blocks.

**Q5: SSE event type for Somatic Blocks?**
**Resolved: New event type with somatic metadata.** Add `StreamEvent.somatic_block(block)` which emits `{type: "somatic_block", block_type: "finding", block_id: "...", status: "detected", ...}`. The frontend handles this as a new event type in `useAgentStream.ts`. Don't overload existing event types — the frontend needs to distinguish Somatic Blocks from tool calls and agent messages.

### Stage 2 (PTY)

**Q6: Which PTY library?**
**Resolved: Raw `os.openpty()` + `aiofiles`.** The third pass confirmed that OCC's command-wrapper sandbox approach is fragile (shell escaping, nested quoting, doesn't work with PTY-based execution). We need process-level sandboxing, not command-string wrapping. Raw `os.openpty()` gives us the file descriptors directly; `aiofiles` wraps them for async I/O. No dependency risk. `aiopty` is unmaintained; `pexpect` adds a thread-bridge latency. The raw approach is more code but zero risk.

**Q7: How does sudo work in a web PTY?**
**Resolved: Don't strip sudo; route password prompts to the frontend.** The current code strips `sudo` and runs without it, which is dangerous (silent privilege escalation failure). A real PTY can handle password prompts — the PTY master sees the `Password:` prompt and forwards it to the frontend via SSE. The frontend shows a password input. The user types the password, which goes back through the PTY stdin. This is how Warp handles it. For polkit-based prompts on Linux, the PTY will show the polkit dialog text; the user responds in the terminal.

### Stage 3 (SQLite)

**Q8: Keep `Conversation` dataclass or replace with `Session`?**
**Resolved: Replace with `Session` that maps to SQLite.** The `Conversation` dataclass is a thin wrapper around JSON file data. `Session` will be the SQLite-backed replacement with the same fields plus `compacted_summary`, `topic_category`, `entities_json`, `parent_session_id`. The `ConversationStore` interface stays the same (get_or_create, add_message, search) but delegates to `SessionStore` internally.

**Q9: Create `session_somatic_blocks` table now or in Stage 1?**
**Resolved: Create it in Phase C (Somatic Blocks).** The table is meaningless without the `SomaticBlock` dataclass. Creating it early would be an empty schema. Create it when `SomaticStore` is built.

### Stage 5 (Subagents)

**Q10: Does `StorageAuditorAgent` run a full ReAct loop or a deterministic script?**
**Resolved: Deterministic script for v1.** The third pass confirmed that a deterministic script (run command → parse output → emit block) is the right starting point. A full ReAct loop adds non-determinism (the agent might do something different each time) which is dangerous for automated triggers. `StorageAuditorAgent` runs `smartctl -a` / `zpool status` / `lsblk` in a PTY, parses the output with regex, and emits a Finding Somatic Block if anomalies are detected. No LLM call. Full ReAct loops are for `IncidentInvestigatorAgent` (post-v1).

**Q11: How does subagent output flow back?**
**Resolved: SSE event → frontend → user approves → primary agent context updated.** The subagent emits a `SomaticBlock` via SSE. The frontend renders it. If the block has a Proposal, the user approves/rejects. On approval, the primary agent's context is updated with the block's findings. This is NOT automatic — the user is in the loop. The primary agent's conversation status is `WaitingForEvents` while the subagent runs, and returns to `InProgress` when the subagent completes.

### Stage 6 (Frontend)

**Q12: Does the accordion dock replace or coexist with ContextBar?**
**Resolved: Coexist.** The ContextBar shows retrieval/memory/discovery sources. The accordion dock shows terminal sessions. They serve different purposes. The dock sits below the ContextBar in the right column. If screen space is tight, the ContextBar collapses to a chip and the dock expands.

**Q13: How many xterm.js instances simultaneously?**
**Resolved: Max 3 visible (1 inline + 2 in dock), rest headless.** Each xterm.js instance is a WebGL canvas. Memory limit: 3 visible instances. Additional sessions are "headless" — output is buffered in the `TerminalSessionManager`, and an xterm.js instance is created on demand when the user expands a docked session. The buffer is replayed into the new instance. This is the same pattern Warp uses for background terminal blocks.

---

## 4. Phase Details

### Phase A: Foundation

This phase must be done first. It changes the conversation representation, adds conversation-level status, and adds the outcome store. These are prerequisites for everything else.

#### A1. Conversation as Block-Typed Messages

**Goal:** Change `StateContext.conversation_history` from a list of string-content messages to a list of block-typed messages, matching Anthropic's content block format.

**Why first:** Somatic Blocks, context compaction (micro-compaction), and conversation restoration all need to distinguish between text, tool_use, and tool_result blocks. The current string-based representation loses this structure.

**What exists:**
- `agents/states.py:StateContext.conversation_history` — `List[Dict[str, Any]]` where each dict has `role` and `content` (string)
- `model/providers/anthropic.py` — already sends block-typed content to the Anthropic API
- `context/assembler.py` — assembles a single string from sources, loses block structure

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `MessageBlock` types | `agents/blocks.py` (new) | `TextBlock`, `ToolUseBlock`, `ToolResultBlock` dataclasses. Each has `type`, `text`/`name`/`input`/`content` fields. Matches Anthropic's content block format. | ~60 |
| Update `StateContext` | `agents/states.py` | Change `conversation_history` type hint. Add `add_text_block()`, `add_tool_use_block()`, `add_tool_result_block()` helpers. | ~30 |
| Update context assembler | `context/assembler.py` | `_combine_sources()` preserves block structure for conversation source. Other sources (retrieval, memory) stay string-based. | ~40 |
| Update agent loop | `agents/react_agent.py` | `_call_llm_with_tools()` already sends block-typed content to Anthropic. Update to store the blocks in `StateContext` instead of flattening to strings. | ~20 |

**Total: ~110 lines new + ~90 lines modified**

**Pattern to steal:** OCC's `ContextManager.getTokenCount()` (lines 34-53) — per-block-type token estimation with different overhead for text vs. tool_use vs. tool_result.

#### A2. Conversation Status State Machine

**Goal:** Add a `ConversationStatus` enum separate from `AgentState`. This gives the UI a user-facing status that distinguishes "retrying after API error" from "done with error."

**Why before subagents:** `WaitingForEvents` is how the primary agent waits for subagent completion. `Blocked { blocked_action }` is how the approval gate works. Without these, subagent completion and approval gating have no clean representation.

**What exists:**
- `agents/states.py:AgentState` — 10 processing states (IDLE, PLANNING, SEARCHING, READING, EXECUTING, OBSERVING, REFLECTING, RESPONDING, AWAITING_CONFIRMATION, ERROR)
- `agents/state_machine.py:TRANSITIONS` — state transition table

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `ConversationStatus` enum | `agents/states.py` | 7 states: `InProgress`, `Success`, `Error`, `TransientError`, `Cancelled`, `Blocked(blocked_action)`, `WaitingForEvents`. Terminal: Success, Error, Cancelled. Non-terminal: TransientError, Blocked, WaitingForEvents. | ~30 |
| `ConversationStatusMachine` | `agents/conversation_status.py` (new) | State machine with transitions. `InProgress → TransientError` (on API failure), `TransientError → InProgress` (on retry), `TransientError → Error` (on max retries). `InProgress → Blocked` (on approval needed), `Blocked → InProgress` (on approval). `InProgress → WaitingForEvents` (on subagent spawn), `WaitingForEvents → InProgress` (on subagent completion). | ~80 |
| Wire into agent state machine | `agents/state_machine.py` | Each `AgentState` transition also updates `ConversationStatus`. ERROR state → check if transient (API failure) or terminal (logic error). AWAITING_CONFIRMATION → `Blocked { blocked_action }`. | ~40 |
| Wire into SSE | `streaming/emitter.py` | `StreamEvent.conversation_status(status)` — frontend renders status badge. | ~20 |
| Add rate limiter | `model/rate_limiter.py` (new) | Exponential backoff with jitter for 429/529 responses. Shared across all model calls. Steal OCC's `RateLimiter` (119 lines) directly. | ~120 |

**Total: ~250 lines new + ~40 lines modified**

**Pattern to steal:** Warp's `ConversationStatus` (7 states, terminal vs. non-terminal distinction). OCC's `RateLimiter` (exponential backoff with jitter, Retry-After header respect, max 5 retries).

#### A3. Outcome Store

**Goal:** Record every model call's outcome (model, success, latency, tokens, cost, complexity) so the cost-cascade router can self-tune.

**Why before the router:** The router needs ≥3 samples per model before stats override the heuristic prior. Starting the store early means data accumulates during Phase B and C.

**What exists:**
- `model/tier_router.py` — `_model_health` dict tracks if models are alive, but not success rates
- `agents/metrics.py` — tracks some metrics but not per-model outcomes

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `OutcomeStore` | `model/outcome_store.py` (new) | SQLite table `model_outcomes` (id, model, success, latency_ms, input_tokens, output_tokens, cost_usd, complexity, task, ts). `record(outcome)` appends. `stats_for(model)` returns `{attempts, successes, successRate}`. `summary()` returns per-model rollup. | ~80 |
| Wire into tier router | `model/tier_router.py` | After `generate()` returns, record the outcome. Success = CRAG evaluator says CORRECT. Latency = wall-clock. Tokens = from response. Cost = tokens × published price. | ~30 |
| Wire into agent loop | `agents/react_agent.py` | After each LLM call, if CRAG evaluation is available, record the outcome. | ~20 |

**Total: ~130 lines new + ~50 lines modified**

**Pattern to steal:** OCC's `OutcomeStore` (JSONL append-only, tolerant of corrupt lines, best-effort recording that never throws). The honesty rule: "records only what happened. Cost is an estimate derived from real token counts × the model's published price. Nothing is fabricated."

---

### Phase B: PTY Backend

This is the hardest phase and blocks everything downstream. It cannot be shortcut.

#### B1. Real PTY Backend

**Goal:** Replace `asyncio.create_subprocess_shell()` with a real async PTY using `os.openpty()` + `aiofiles`. Add ring buffer, TTL reaper, WebSocket bridge, and sandbox integration.

**Why this is the critical path:** Subagents (Phase D) run commands in PTYs. The frontend (Phase E) renders PTY output. Without a real PTY, both are built on a `subprocess` that returns output after the command finishes — no streaming, no interaction, no session persistence.

**What exists:**
- `dashboard/routes/terminal.py` (299 lines) — `asyncio.create_subprocess_shell()` with 30s timeout, safety tiers, sudo stripping
- `dashboard/frontend/src/pages/Terminal.tsx` (482 lines) — xterm.js + FitAddon + WebLinksAddon
- `streaming/sse.py` — SSE infrastructure

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `PTYSession` | `streaming/pty.py` (new) | `os.openpty()` → master/slave fds. `aiofiles` for async I/O. `spawn(command, cwd, env, size)` → child process in slave. `read_chunk()` → async generator of stdout chunks. `write_stdin(data)`. `resize(cols, rows)` → `ioctl TIOCSWINSZ`. `SIGWINCH` handling. 1MB ring buffer (`bytearray`). | ~200 |
| `TerminalSessionManager` | `streaming/session_manager.py` (new) | Singleton. `spawn()` → `PTYSession` + session ID. `get(id)`, `list_active()`, `kill(id)`. 60s idle reaper (background task). Max 2 concurrent sessions (configurable). Overflow to `/tmp/halbert/terminals/{id}.log`. | ~120 |
| Sandbox integration | `streaming/sandbox.py` (new) | Platform detection. Linux: `bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --bind {writable} {writable}`. macOS: `sandbox-exec -p '(deny default) (allow process-exec) (allow file-read* (deny file-read* (subpath "/etc/ssh"))) (allow file-write* (subpath "{writable}"))'`. Path validation regex (absolute, no metacharacters, no null bytes). | ~100 |
| Injection check | `streaming/injection_check.py` (new) | 16 dangerous patterns (rm -rf /, pipe to shell, backtick, $(), write to /etc/, curl pipe to bash, mkfs, dd to device, fork bomb, chmod 777 root, eval, exec fd redirect). Plus host-specific: `zpool destroy`, `lvremove`, `ip link delete`. `uses_elevation()` for sudo/su/doas. | ~80 |
| Replace terminal route | `dashboard/routes/terminal.py` | Replace `create_subprocess_shell()` with `TerminalSessionManager.spawn()`. Add `/sessions` (list), `/{id}/input` (write stdin), `/{id}/resize` (SIGWINCH), `/{id}/stream` (SSE output). Keep safety tier checks but add sandbox wrapping. Remove sudo stripping — route password prompts to frontend. | ~120 (rewrite) |
| WebSocket bridge | `dashboard/routes/websocket.py` | Bidirectional: stdin (frontend → PTY), stdout/resize (PTY → frontend). | ~80 |

**Total: ~580 lines new + ~120 lines rewritten + ~80 lines upgraded = ~780 lines**

**Pattern to steal:** Warp's `unix.rs:make_pty()` — `openpty()` with winsize + `FD_CLOEXEC`. Warp's `EventedPty` — event-loop-based I/O (translate mio to asyncio). OCC's `injection-check.mjs` — 16 dangerous patterns. OCC's `sandbox.mjs` — path validation regex.

**Library choice:** Raw `os.openpty()` + `aiofiles`. No dependency on `aiopty` (unmaintained) or `pexpect` (thread-bridge latency). More code, zero risk.

**Platform support:** Unix-only for v1 (macOS + Linux). Windows (ConPTY) is post-v1.

---

### Phase C: Somatic Blocks and Integration

After Phase A (foundation) is complete, build the Somatic Block layer and the cost-cascade router.

#### C1. Somatic Block Dataclass + Store + Lifecycle

**Goal:** Wrap the existing `findings/`, `approval/`, `autonomy/` modules under a unified `SomaticBlock` lifecycle.

**What exists (DO NOT REWRITE):**
- `findings/store.py` — `Finding` + `FindingStore` (SQLite)
- `findings/proposals.py` — `Proposal` + `ProposalStore` (SQLite, full status lifecycle)
- `findings/blast_radius.py` — blast-radius scoring
- `findings/precedence.py` — sshd/systemd precedence resolution
- `approval/engine.py` — `ApprovalRequest` + `ApprovalEngine`
- `approval/simulator.py` — `DryRunSimulator`
- `autonomy/recovery.py` — `RecoveryExecutor` with rollback/restart/alert/safe-mode
- `autonomy/guardrails.py` — `GuardrailEnforcer` with confidence thresholds

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `SomaticBlock` dataclass | `somatic/block.py` (new) | `block_type` (Sensory, Deliberation, Proposal, Action, Reflection), `status`, `session_id`, `finding_id`, `proposal_id`, `approval_request_id`, `action_id`, `reflection_id`, `created_at`, `updated_at`. References existing models by ID. | ~80 |
| `SomaticStore` | `somatic/store.py` (new) | SQLite table `somatic_blocks`. CRUD + `list_for_session()` + `list_by_type()`. | ~70 |
| `SomaticLifecycle` | `somatic/lifecycle.py` (new) | State machine: Sensory → Deliberation → Proposal → Action → Reflection. Each transition calls the existing module. Sensory: `detector_runner.run()`. Deliberation: `intake/complexity.py` + cognitive tick. Proposal: `findings/proposals.py`. Action: `approval/engine.py` + `autonomy/recovery.py`. Reflection: cognitive tick output. | ~120 |
| Wire into agent state machine | `agents/state_machine.py` | REFLECTING → `SomaticLifecycle.advance_to_reflection()`. EXECUTING → `SomaticLifecycle.advance_to_action()`. Proposals → `SomaticLifecycle.advance_to_propal()`. Sets `ConversationStatus::Blocked` when approval needed. | ~40 |
| Wire into SSE | `streaming/emitter.py` | `StreamEvent.somatic_block(block)` — new event type. | ~20 |
| Per-file checkpoints | `somatic/checkpoints.py` (new) | Before any Action block executes, save original file content to `~/.local/share/halbert/checkpoints/{id}.json`. Stack-based undo. Max 50 checkpoints, FIFO trim. Steal OCC's `CheckpointManager` pattern. | ~80 |

**Total: ~370 lines new + ~60 lines modified**

**Pattern to steal:** OCC's `CheckpointManager` — per-file checkpoint stack with FIFO trim. Warp's `Block.InteractionMode` — per-block permission system (autonomous, supervised, observed).

#### C2. Cost-Cascade Router

**Goal:** Merge the two existing complexity systems, add the outcome store integration, and implement the cost-cascade routing pattern from OCC.

**What exists (MERGE, don't preserve both):**
- `intake/complexity.py` — `ComplexityRouter` with LLM-based 1-5 scoring, LRU cache, fast paths
- `model/tier_router.py:_score_complexity()` — bag-of-words heuristic, 0-1 scoring

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `MetaHarnessRouter` | `model/cascade_router.py` (new) | `estimate_complexity(text)` — bag-of-words heuristic (steal OCC's `estimateComplexity()`). `predict(model, complexity)` — blends tier-based prior with recorded stats (evidence weight capped at 0.9). `route(task_text)` — iterates ladder cheapest-first, returns first model that clears quality bar (0.7). `escalate(failed_model_id)` — step up one tier. | ~120 |
| Merge complexity systems | `intake/complexity.py` | Keep the LLM-based assessment as a fallback for uncertain cases (heuristic score near tier boundary). Remove the duplicate `_score_complexity()` from `tier_router.py`. Use the heuristic as primary, LLM as secondary. | ~40 (modify) |
| Wire into tier router | `model/tier_router.py` | `route_request()` delegates to `MetaHarnessRouter.route()`. `select_model()` uses `predict()` instead of just health checks. After `generate()`, record outcome via `OutcomeStore`. | ~50 (modify) |
| Opt-in flag | `model/cascade_router.py` | `is_self_optimize_enabled()` — checks config flag, default OFF. When disabled, behavior is byte-identical to current (heuristic only, no outcome-based routing). | ~20 |

**Total: ~230 lines new + ~90 lines modified**

**Pattern to steal:** OCC's `MetaHarnessRouter` — the entire pattern is directly portable. The blending formula (`w = clamp(attempts / (attempts + minSamples), 0, 0.9)`) prevents overfitting. The opt-in default (byte-identical when disabled) is critical for user trust.

---

### Phase D: Subagents

After Phase B (PTY) and Phase C1 (Somatic Blocks), build the subagent system.

#### D1. Subagent Task Store + Spawn

**Goal:** Build `SubagentManager` with a SQLite task queue, `StorageAuditorAgent` as the first deterministic subagent, and lifecycle event streaming.

**What exists:**
- `agents/react_agent.py` — single ReAct loop, no subagent concept
- `discovery/scanners/storage.py` — `StorageScanner` runs `smartctl`, `lsblk` synchronously
- `streaming/emitter.py` — `EventEmitter` with session-scoped queues

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `SubagentHandle` | `agents/subagent.py` (new) | id, agent_type, task_goal, scoped_sources, model_tier, pty_session_id, status, started_at, completed_at, result_block_id, agent_config_snapshot (frozen config for reproducibility), parent_task_id, children (for nested subagents). | ~50 |
| `SubagentManager` | `agents/subagent.py` | `spawn(agent_type, task_goal, scoped_sources)` → `SubagentHandle`. SQLite task queue (not just `asyncio.Semaphore`). `AtCapacity` event when queue is full (non-blocking — task queues, stream continues). `cancel(handle_id)`. `list_active()`. `list_queued()`. | ~120 |
| `StorageAuditorAgent` | `agents/subagents/storage_auditor.py` (new) | Deterministic script: runs `smartctl -a` / `zpool status` / `lsblk` via `TerminalSessionManager`. Parses output with regex. Emits Finding Somatic Block if anomalies detected. No LLM call. | ~100 |
| Lifecycle event stream | `agents/subagent.py` | Stream of `SubagentEvent`: `TaskSpawned`, `StateChanged`, `SessionStarted`, `TimedOut`, `AtCapacity`, `Completed`. Steal Warp's `AmbientAgentEvent` pattern. | ~60 |
| Wire into state machine | `agents/state_machine.py` | PLANNING state can emit `spawn_subagent` tool call. Primary agent enters `ConversationStatus::WaitingForEvents`. Subagent completion emits Somatic Block via SSE. Primary agent returns to `InProgress`. | ~40 |
| Wire into SSE | `streaming/emitter.py` | `StreamEvent.subagent_event(event)` — frontend renders subagent lifecycle. | ~20 |

**Total: ~350 lines new + ~60 lines modified**

**Pattern to steal:** Warp's `AmbientAgentEvent` stream — lifecycle events, not function calls. Warp's `agent_config_snapshot` — freeze config into the task record. Warp's `AtCapacity` — non-blocking queue, not `Semaphore`. OCC's `AgentTeams` — `register()`, `send_message()`, `broadcast()` API.

---

### Phase E: Frontend

After Phase B (PTY) and Phase C1 (Somatic Blocks), build the frontend terminal docking.

#### E1. Terminal Tiles and Docking

**Goal:** Integrate xterm.js into the conversation stream with IntersectionObserver-based docking and an accordion dock in the right column.

**What exists:**
- `dashboard/frontend/src/pages/Terminal.tsx` (482 lines) — standalone xterm.js page
- `dashboard/frontend/src/components/SidePanel.tsx` (2,334 lines) — conversation panel with `PanelMode` toggle
- `dashboard/frontend/src/hooks/useAgentStream.ts` (643 lines) — SSE stream consumer

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `useTerminalSessions` | `hooks/useTerminalSessions.ts` (new) | Singleton store. WebSocket per session. Tracks session state (running/done/idle), output buffer, scrollback. Max 3 visible xterm.js instances; rest headless. | ~120 |
| `TerminalTile` | `components/agent/TerminalTile.tsx` (new) | Inline terminal in conversation stream. xterm.js instance. Status badge, timer, PID, quick actions (Pin, Terminate, Copy). | ~150 |
| `TerminalAccordionDock` | `components/agent/TerminalAccordionDock.tsx` (new) | Right-column accordion. Lists all sessions. Expand/collapse. Jump-to-origin. Full PTY interactivity on expand. Coexists with ContextBar (sits below it). | ~200 |
| `useIntersectionDock` | `hooks/useIntersectionDock.ts` (new) | Watches terminal tile visibility. At <25% visibility, triggers docking. At >25% (scroll back), triggers restoration. | ~60 |
| `TetherChip` | `components/agent/TetherChip.tsx` (new) | Inline chip when terminal is docked. Hover highlights docked card. Click scrolls back. | ~40 |
| Integrate into SidePanel | `components/SidePanel.tsx` | Add right-column dock below ContextBar. Render `TerminalTile` in conversation stream. | ~80 |
| SSE event handling | `hooks/useAgentStream.ts` | Handle `somatic_block`, `subagent_event`, `conversation_status`, `terminal_spawn`, `terminal_output`, `terminal_complete` events. | ~60 |

**Total: ~630 lines new frontend + ~140 lines modified**

**Pattern to steal:** Warp's `ConversationBlockRestorationPlan` — compute the block layout plan once, render in any frontend. Warp's `BlockList` — block-based terminal model for scrollback.

---

### Phase F: Advanced Features

After Phases C, D, and E are complete, these are integration work:

#### F1. SQLite Session Store + FTS5 (~160 lines)
Migrate `ConversationStore` from JSON to SQLite + FTS5. Create `session_somatic_blocks` table. One-time migration script.

#### F2. Session Affinity Router (~140 lines)
3-tier routing: explicit reference regex → FTS5 search → current session. Reuse `intake/signals.py` for entity extraction. Emit SSE event on re-anchoring.

#### F3. Living Reflexes (~250 lines)
`Reflex` dataclass (extends Warp's `Workflow::Command` with `trigger`, `rollback`, `provenance`). `ReflexStore` (YAML). `ReflexMatcher` (regex + threshold). Scheduler with JSON persistence (steal OCC's `Scheduler`). Wire into `proactive/detector_runner.py`.

#### F4. Context Watermark (~110 lines)
80% token watermark trigger (not 75% — leaves headroom for one more exchange). 2-hour temporal gate. Topic boundary gate. Micro-compaction (truncate tool results >200 chars before full summarization). LLM-based full-compaction summary (not crude concatenation). Track compaction statistics.

---

## 5. What to Cut for v1

| Feature | Why Cut | Revisit After |
|---|---|---|
| Windows PTY support | Huge additional effort (ConPTY). macOS + Linux covers 95% of homelab servers. | v2 |
| Multi-provider dispatch | OCC's OpenAI/Google/Bedrock/Vertex abstraction is nice but not critical. Stick with existing Ollama/Anthropic providers. | v2 |
| Remote subagents | Run all subagents on local host for v1. Remote execution adds auth, network, and latency complexity. | v2 |
| Workflow sharing / source_url | Keep reflexes local for v1. Sharing is a social feature, not a core feature. | v2 |
| Embedding-based session routing | FTS5 handles 90% of routing. Embeddings are for the ambiguous-match tier only. | F2 stable |
| GSAP FLIP docking animation | Ship the dock first, animate later. 300ms FLIP is polish, not function. | E1 complete |
| Dream Cycle 03:00 scheduler | Require explicit user opt-in. The 03:00 default is a bad idea without robust scheduling and user trust. | F3 + user opt-in |
| Parametric Headroom Sliders | Requires live RAM/headroom simulation engine that doesn't exist. | New simulation engine |
| "What Changed?" Biographical Diff | Requires config snapshot infrastructure. | New snapshot subsystem |
| Host-Aware Predictive Ghosting | Requires Tier 1 local model on every keystroke. Latency-sensitive. | Local model infra + E1 |
| 4 More Subagents | Build `StorageAuditorAgent` first. If the pattern works, others are mechanical. | D1 validated |
| Full ReAct subagent loop | `StorageAuditorAgent` is deterministic. Full ReAct is for `IncidentInvestigatorAgent`. | D1 validated |
| Hook engine (PrePrompt, PostResponse) | Only 4 of 6 OCC hook events are implemented and useful. Skip the 2 aspirational ones. | Post-v1 |
| `Workflow::AgentMode` reflexes | Reflexes should be deterministic commands, not agent prompts. Non-deterministic automated triggers are dangerous. | Post-v1 |

---

## 6. What Not to Rewrite

These modules are real, tested, and provide the substrate for the vision. Wrap them, do not rewrite them:

| Module | Why it's solid | What to add |
|---|---|---|
| `findings/store.py` | `Finding` + `FindingStore` (SQLite, 163+ lines) | Reference from `SomaticBlock` |
| `findings/proposals.py` | `Proposal` with full status lifecycle (302 lines) | Reference from `SomaticBlock` |
| `findings/blast_radius.py` | Blast-radius scoring (88 lines) | Call from `SomaticLifecycle.Proposal` |
| `findings/precedence.py` | sshd/systemd precedence (353 lines) | Call from `SomaticLifecycle.Action` |
| `approval/engine.py` | `ApprovalRequest` + `ApprovalEngine` (417 lines) | Wire to `ConversationStatus::Blocked` |
| `approval/simulator.py` | `DryRunSimulator` (380 lines) | Call from `SomaticLifecycle.Proposal` |
| `autonomy/recovery.py` | `RecoveryExecutor` with rollback (307 lines) | Add per-file checkpoints before actions |
| `autonomy/guardrails.py` | `GuardrailEnforcer` with thresholds (292 lines) | Call from `SomaticLifecycle.Action` |
| `intake/signals.py` | Entity extraction, <1ms | Use for session router |
| `agents/state_machine.py` | 10-state ReAct loop with CRAG | Add `ConversationStatus` layer |
| `model/tier_router.py` | Multi-provider with fallback chains | Add outcome store + cascade router |
| `model/providers/` | Ollama, Anthropic, MLX, llamacpp | Don't add OpenAI/Google for v1 |

---

## 7. Revised Effort Estimate

| Phase | New Lines | Modified Lines | Effort |
|---|---|---|---|
| A1. Conversation as blocks | ~110 | ~90 | Small |
| A2. Conversation status + rate limiter | ~250 | ~40 | Small-medium |
| A3. Outcome store | ~130 | ~50 | Small |
| B1. Real PTY backend | ~580 | ~200 | **Large (critical path)** |
| C1. Somatic Blocks | ~370 | ~60 | Medium |
| C2. Cost-cascade router | ~230 | ~90 | Medium |
| D1. Subagents | ~350 | ~60 | Medium |
| E1. Frontend docking | ~630 | ~140 | Medium-large (frontend) |
| F1. SQLite session store | ~120 | ~40 | Small |
| F2. Session affinity router | ~120 | ~20 | Small |
| F3. Living Reflexes | ~200 | ~50 | Small-medium |
| F4. Context watermark | ~80 | ~30 | Small |
| **Total** | **~3,170** | **~870** | **~4,040 lines** |

Plus ~500 lines for integration glue, tests, and migration scripts: **~4,500 lines total**.

This is **70% higher than v1.0's estimate** (~2,670 lines). The increase is primarily in Phase B (PTY: 780 vs. 410 lines) and Phase A (foundation: 490 lines that v1.0 didn't include at all).

**Timeline:** 6-8 weeks of focused work. Phase B is the longest (5-7 days). Phases A and C are 2-3 days each. Phases D and E are 3 days each. Phase F is 5-7 days total.

---

## 8. Concrete Next Steps

### This week: Phase A (Foundation)

1. **A1: Conversation as blocks** (1-2 days)
   - Create `agents/blocks.py` with `TextBlock`, `ToolUseBlock`, `ToolResultBlock`
   - Update `StateContext.conversation_history` to use block-typed messages
   - Update `context/assembler.py` to preserve block structure for conversation source
   - Update `agents/react_agent.py` to store blocks instead of flattening to strings

2. **A2: Conversation status + rate limiter** (1-2 days)
   - Add `ConversationStatus` enum to `agents/states.py`
   - Create `agents/conversation_status.py` with state machine
   - Wire into `agents/state_machine.py`
   - Create `model/rate_limiter.py` (steal OCC's `RateLimiter`)
   - Add `StreamEvent.conversation_status()` to `streaming/emitter.py`

3. **A3: Outcome store** (1 day)
   - Create `model/outcome_store.py` with SQLite table
   - Wire into `model/tier_router.py:generate()`
   - Wire into `agents/react_agent.py` after CRAG evaluation

### Next week: Phase B (PTY)

4. **B1: Real PTY backend** (5-7 days)
   - Create `streaming/pty.py` with `PTYSession`
   - Create `streaming/session_manager.py` with `TerminalSessionManager`
   - Create `streaming/sandbox.py` with platform-specific sandboxing
   - Create `streaming/injection_check.py` with 16+ dangerous patterns
   - Rewrite `dashboard/routes/terminal.py` to use `TerminalSessionManager`
   - Upgrade `dashboard/routes/websocket.py` for bidirectional PTY bridge

### After that: Phase C (Somatic Blocks)

5. **C1: Somatic Block dataclass + store + lifecycle** (2 days)
6. **C2: Cost-cascade router** (2 days)

### Then: Phases D, E, F in parallel where possible

7. **D1: Subagents** (3 days, after B1 + C1)
8. **E1: Frontend docking** (3 days, after B1 + C1)
9. **F1-F4: Advanced features** (5-7 days, after C, D, E)

---

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| PTY implementation is harder than estimated | High | High | Start with minimum viable (no sandbox, no resize), add features incrementally |
| Block-typed message change breaks existing agent loop | Medium | High | Keep string fallback for non-conversation sources; test agent loop end-to-end after A1 |
| Conversation status state machine conflicts with agent state machine | Medium | Medium | Keep them separate; coordinate via `StateContext` only |
| Outcome store adds latency to model calls | Low | Low | Use async SQLite writes; best-effort recording that never blocks |
| Sandbox profiles break legitimate commands | Medium | Medium | Start with permissive profiles; tighten based on testing |
| Frontend xterm.js memory pressure with multiple instances | Medium | Medium | Max 3 visible instances; headless buffering for the rest |
| Subagent deterministic script doesn't handle edge cases | Medium | Medium | Start with `StorageAuditorAgent` only; add error handling for common failures (command not found, permission denied, timeout) |

---

## 10. Success Criteria

The v1 sovereign host is "done" when:

1. **A user can have a long-running conversation** that doesn't lose context (block-typed messages + micro-compaction)
2. **The agent can run commands in a real PTY** with streaming output and interactive shells (Phase B)
3. **The agent can spawn a StorageAuditorAgent** that runs in the background and emits a Finding Somatic Block (Phase D)
4. **The frontend shows terminal tiles in the conversation stream** with docking (Phase E)
5. **The agent waits for user approval** before executing dangerous actions, with `ConversationStatus::Blocked` in the UI (Phase A2 + C1)
6. **The model router learns from outcomes** and routes to cheaper models when they succeed (Phase A3 + C2)
7. **The user can resume a past session** by saying "continue that disk issue" (Phase F1 + F2)
8. **The being can run scheduled reflexes** when telemetry thresholds are crossed (Phase F3)

If all 8 are true, the sovereign host is alive. Everything else is polish.
