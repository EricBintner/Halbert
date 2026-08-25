# Second Pass: Reverse-Engineering Assumptions

**Date:** August 25, 2026
**Purpose:** Re-examine the first-pass pattern inventory with the actual code open. Challenge every assumption. Describe what the code REALLY does, not what I assumed it does. Then describe what Halbert's code could be doing differently — with specific, grounded detail.

---

## Methodology

In the first pass (`CROSS-CODEBASE-PATTERN-INVENTORY.md`), I read files and summarized them at a high level. That's useful for inventory but dangerous for design — summaries hide the implementation decisions that matter. In this pass, I re-read the actual code line by line and ask three questions for each pattern:

1. **What does the code ACTUALLY do?** (not what I said it does)
2. **What assumption did I make that was wrong or oversimplified?**
3. **What could Halbert's code be doing differently, specifically?**

---

## 1. Cost-Cascade Router (OCC v2 `optimize/router.mjs`)

### What I said in the first pass
"Routes each task to the cheapest model that clears a quality bar. Self-tunes from recorded outcomes."

### What the code ACTUALLY does

The router is a **pure decision function** — it makes zero API calls. It takes a task string, estimates complexity, and returns a model ID. The actual model call happens elsewhere. This separation is the key design decision I glossed over.

**`estimateComplexity(text)`** (lines 45-76) is a **deterministic heuristic**, not an LLM call. It works like this:

```
score = 0
score += clamp(text.length / 4000, 0, 0.35)    // length is weak signal, capped at 0.35
for each hardSignal in ['refactor', 'architecture', 'design', 'debug', ...]:
    if text.includes(signal): score += 0.12     // each hard signal adds 0.12
for each easySignal in ['what is', 'rename', 'typo', 'format', ...]:
    if text.includes(signal): score -= 0.10     // each easy signal subtracts 0.10
if codeFences >= 2: score += 0.08
if questions >= 3: score += 0.08
return clamp(score, 0, 1)
```

This is a **bag-of-words heuristic** — no embeddings, no LLM, no semantic understanding. A 4000-char message about "renaming a typo" gets `0.35 - 0.10 - 0.10 = 0.15`. A 2000-char message about "debug a race condition in the distributed architecture" gets `0.5 + 0.12 + 0.12 + 0.12 + 0.12 = ~0.98`.

**`predict(model, complexity)`** (lines 115-132) blends a **tier-based prior** with **recorded stats**:

```
tierStrength = tier / maxTier           // e.g. Haiku=1/3=0.33, Opus=3/3=1.0
prior = 1 - complexity * (1 - tierStrength) - 0.05 * (1 - tierStrength)
```

For Haiku (tier 1 of 3) on a complexity-0.8 task:
```
prior = 1 - 0.8 * (1 - 0.33) - 0.05 * 0.67 = 1 - 0.536 - 0.0335 = 0.43
```
For Opus on the same task:
```
prior = 1 - 0.8 * (1 - 1.0) - 0.05 * 0 = 1.0
```

So Haiku's prior is 0.43 (below the 0.7 quality bar) and Opus's is 1.0 (above). The router picks Opus.

**But** once enough samples accumulate (min 3), recorded stats override the prior:
```
w = clamp(attempts / (attempts + minSamples), 0, 0.9)   // evidence weight, capped at 0.9
return w * stats.successRate + (1 - w) * prior
```

If Haiku has been tried 10 times on similar tasks with 80% success:
```
w = 10 / (10 + 3) = 0.77
prediction = 0.77 * 0.8 + 0.23 * 0.43 = 0.617 + 0.099 = 0.716
```
Now Haiku clears the 0.7 bar — the router picks Haiku instead of Opus. **The router learned that Haiku is good enough for this task type.**

**`route(taskText)`** (lines 141-172) iterates the ladder cheapest-first and returns the first model that clears the bar. If none clear it, it escalates to the top of the ladder.

**`escalate(failedModelId)`** (lines 181-185) is a simple ladder step-up: find the failed model's index, return the next one. No re-routing, no re-complexity estimation — just step up one tier.

### What I assumed wrong

1. **I said "self-tunes from recorded outcomes"** — true, but I didn't explain the **blending formula**. The prior is never fully replaced; it's blended with a weight capped at 0.9. This prevents overfitting from a handful of lucky runs. A model that succeeded 3 out of 3 times doesn't get a 1.0 prediction — it gets `0.5 * 1.0 + 0.5 * prior`.

2. **I said "the outcome store is JSONL"** — true, but I didn't mention the **honesty rule** (store.mjs line 8): "this records only what happened. Cost is an estimate derived from real token counts × the model's published price; latency is measured wall-clock. Nothing is fabricated." The `summary()` method even sets `estimatedSavingsUsd: 0` when it doesn't have enough data, rather than guessing.

3. **I didn't mention that the entire system is opt-in** (cascade.mjs line 122-128): `isSelfOptimizeEnabled()` checks CLI flag > env var > setting, default OFF. When disabled, the agent loop never imports the cascade module. This is a **byte-identical default** guarantee — enabling self-optimization doesn't change behavior until the user explicitly turns it on.

### What Halbert's code could be doing differently

Halbert has TWO separate complexity systems that don't talk to each other:

**`intake/complexity.py`** — uses an LLM call to rate complexity 1-5. It has an LRU cache, fast paths for greetings, and a troubleshooting floor. But it **doesn't record outcomes**. It calls the guide model every cache miss, gets a score, and throws away the result after caching.

**`model/tier_router.py`** — has `_score_complexity(query)` which is a bag-of-words heuristic (lines 464-502) almost identical to OCC's `estimateComplexity()`. It scores 0.0-1.0 based on word count, code indicators, multi-step indicators, and sysadmin keywords. Then `route_request()` uses the score to pick Guide vs. Specialist tier. But it **doesn't record outcomes either** — it has `_model_health` (is the model alive?) but no `_model_success_rate` (did the model succeed on similar tasks?).

**What we should do:**

1. **Merge the two complexity systems.** `intake/complexity.py` (LLM-based, 1-5 scale) and `model/tier_router.py:_score_complexity()` (heuristic, 0-1 scale) are doing the same job twice. The LLM call in `complexity.py` is expensive (a full model round-trip for a 5-token response) and adds latency to every message. OCC's heuristic is zero-latency and good enough as a prior. Use the heuristic as the primary signal, fall back to the LLM only when the heuristic is uncertain (score near the tier boundary).

2. **Add an outcome store.** Steal OCC's `OutcomeStore` pattern directly — JSONL append-only, one line per routed task with `{model, success, latencyMs, inputTokens, outputTokens, costUsd, complexity, task}`. Wire it into `tier_router.py:generate()` — after the model responds, record whether it succeeded (did the CRAG evaluator say CORRECT?), the latency, and the token usage. Then `select_model()` can blend the prior with recorded stats, exactly like OCC's `predict()`.

3. **Add the escalation ladder.** Currently `tier_router.py` has fallback chains (if specialist is down, try guide), but no **failure-based escalation** — if the guide model produces a low-confidence response, we don't automatically retry with the specialist. OCC's `escalate(failedModelId)` is a one-liner that steps up the ladder. We should add this to the state machine: if CRAG says INCORRECT and we used the guide model, retry with the specialist.

4. **Make it opt-in.** The outcome recording should be opt-in (like OCC's `--self-optimize`), not default. The complexity heuristic can stay on by default (it's zero-cost), but the outcome store and the stats-based routing should only activate when the user enables it.

---

## 2. Context Compaction (OCC v2 `context-manager.mjs`)

### What I said in the first pass
"Two-tier compaction: micro-compact old tool results before full summarization."

### What the code ACTUALLY does

**`microCompact(messages, recentTurns=5)`** (lines 72-113) is more surgical than I described:

1. Count user messages from the end of the array. If there are ≤5 user messages, return unchanged (not enough history to compact).
2. Find the **boundary index** — the position of the 5th-most-recent user message. Everything before this boundary is compactable; everything after is preserved.
3. For messages before the boundary, if a message has `content` as an array (multi-block messages), map over the blocks. For each `tool_result` block with content >200 chars, replace with `content.slice(0, 100) + '...[truncated]'`.
4. Tool **calls** (tool_use blocks) are NOT truncated — only results. This preserves the "what did the agent do" trace while dropping the "what did the tool return" bulk.

**`compact(messages, keepRecent=6)`** (lines 124-171) tries micro-compaction first:
1. Run `microCompact()`. If the result is under the threshold, return it.
2. If still over, do **full compaction**: slice off the last 6 messages (keep them), summarize the rest.
3. The summary is crude: for each old message, take the first 200 chars of text content, or for tool_use blocks just `[tool:name]`, or for tool_result blocks `[result:first80chars]`. Join with newlines, cap at 2000 chars.
4. Insert as a single user message: `[Context compacted — summary of N earlier messages]\n...`.

**`getTokenCount(messages)`** (lines 34-53) is a **character-based heuristic**: 4 chars ≈ 1 token, plus 16 chars of overhead per message for the role tag. For content blocks, it adds 20 chars for tool_use JSON overhead. No tokenizer dependency.

### What I assumed wrong

1. **I said "truncating result content to 100 chars"** — true, but I didn't mention the **200-char threshold**. Tool results under 200 chars are left alone. Only results >200 chars get truncated. This means short results (like `"OK"` or `exit code: 0`) are preserved; long results (like a 5000-line file dump) get cut.

2. **I said the threshold is 80%** — true for OCC, but I didn't explain **why**. The 80% threshold (not 75%) leaves headroom for the next user message + the assistant's response. If you compact at 75%, you might immediately need to compact again after the next exchange. The 80% threshold gives you ~20% of the context window for one more exchange before the next compaction.

3. **I didn't mention that the summary is terrible.** OCC's full-compaction summary is a crude concatenation of first-200-chars per message, capped at 2000 chars. It loses ordering, context, and most of the content. This is a **known weakness** — the comment doesn't claim it's good. It's a "better than nothing" fallback when micro-compaction isn't enough.

### What Halbert's code could be doing differently

Halbert's `context/assembler.py` has `_compress_with_cascade()` but no **micro-compaction tier**. It goes straight to full summarization when the context is too large. This means every compaction event loses the tool output from early turns — even if the tool calls themselves are still relevant.

**What we should do:**

1. **Add micro-compaction before full compaction.** Steal OCC's two-tier approach: first truncate old tool results (>200 chars → first 100 chars + `...[truncated]`), then if still over threshold, do full summarization. This preserves the tool call trace (what the agent did) while dropping the tool output bulk (what the tools returned).

2. **Use the 80% threshold, not 75%.** The vision spec says 75%, but OCC's 80% is better — it gives headroom for one more exchange. With Somatic Blocks, each block has tool output that could be large; we need the headroom more than OCC does.

3. **Make the full-compaction summary better than OCC's.** OCC's summary is a crude 200-char-per-message concatenation. Halbert has an LLM available — use it. When full compaction is needed, call the guide model with "Summarize this conversation, preserving key decisions, tool calls, and outcomes" and use the LLM's summary instead of the crude concatenation. This is more expensive but produces a much better summary.

4. **Track compaction statistics.** OCC's `getStats()` returns `{compactionCount, lastPreCompactTokens, lastPostCompactTokens}`. Halbert should track the same — how many times has compaction fired, what was the token count before and after. This is critical for tuning the threshold.

---

## 3. Block-Based Terminal Model (Warp `terminal/model/block.rs`)

### What I said in the first pass
"Warp's Block is literally a Somatic Block for terminal commands."

### What the code ACTUALLY does

Warp's `Block` struct (line 297) is **not** a generic lifecycle container — it's specifically a **terminal command block**. It represents one command + its output. The fields tell the story:

- `header_grid: HeaderGrid` — the prompt line (command text, cwd, git branch)
- `output_grid: BlockGrid` — the command's stdout/stderr
- `rprompt_grid: BlockGrid` — the right-prompt (git status, virtual env)
- `exit_code: ExitCode` — the command's exit code
- `pwd: Option<String>` — working directory when the command ran
- `git_branch: Option<String>` — git branch at execution time
- `shell_host: Option<ShellHost>` — which shell (bash, zsh, fish) ran it

`BlockState` (line 623) is a **5-state lifecycle**:
- `BeforeExecution` — command sent to PTY but preexec hasn't fired yet (shell is echoing characters)
- `Executing` — between preexec and precmd (command is running)
- `DoneWithExecution` — command finished, has an exit code
- `DoneWithNoExecution` — block was created but no command ran (user pressed enter on empty prompt)
- `Background` — holds background process output, not associated with a specific command
- `Static` — programmatically added content (not from a command)

The `InteractionMode` field (line 369) is the most interesting — it tracks **how the AI agent interacts with this block**. This is Warp's equivalent of our Somatic Block's "phase" — a block can be in autonomous mode (agent acts on it without asking), supervised mode (agent proposes, user approves), or observed mode (agent watches but doesn't act).

### What I assumed wrong

1. **I said "Block is literally a Somatic Block"** — it's not. It's a **terminal command block**, not a generic lifecycle container. A Somatic Block needs to represent findings, proposals, reflections, and actions — not just commands. Warp's Block only represents commands. The pattern is reusable (lifecycle states + metadata + timestamps), but the data model is different.

2. **I said "InteractionMode is how the block interacts with the AI agent"** — true, but I didn't explain the **directionality**. InteractionMode is about **what the agent is allowed to do with this block**, not what the block does to the agent. It's a permission system, not a behavior system. The block doesn't change how the agent thinks; it changes whether the agent can act.

3. **I didn't mention `SerializedBlock`** — the block has a serialization form for persistence and conversation restoration. This is critical: blocks need to be saved to disk and restored when the user resumes a session. The serialization form strips the live grids (which are GPU/memory-heavy) and keeps only the text content + metadata.

### What Halbert's code could be doing differently

Halbert has no concept of a "block" at all. The agent state machine (`state_machine.py`) processes requests through states (PLANNING → EXECUTING → OBSERVING → REFLECTING), but each state transition is ephemeral — there's no persisted record of "what happened in this cycle." The `StateContext` (states.py:80) is a scratchpad that accumulates data during a request but is discarded after the response is sent.

**What we should do:**

1. **Don't copy Warp's Block directly.** Warp's Block is terminal-specific (header_grid, output_grid, rprompt_grid). Our Somatic Block needs to be more general — it represents any cognitive event (finding, proposal, action, reflection), not just a command. But we should steal the **structural pattern**: lifecycle states, metadata, timestamps, interaction mode, serialized form.

2. **Steal the InteractionMode concept.** Halbert's `autonomy/guardrails.py` has confidence thresholds, but it doesn't have a per-block interaction mode. A finding about a failing disk should be in "observed" mode (the agent watches but doesn't act). A proposal to change sshd_config should be in "supervised" mode (agent proposes, user approves). An action to restart a failed service should be in "autonomous" mode (agent acts without asking, if confidence is high enough). The InteractionMode field on each Somatic Block is what makes this work.

3. **Steal the SerializedBlock pattern.** Somatic Blocks need to be persisted to SQLite and restored when the user resumes a session. The serialized form should strip the live data (the full tool output, the full LLM response) and keep only the summary + metadata + status. This is what `findings/store.py` already does for findings — we need to extend it to all block types.

4. **Steal the `BeforeExecution` state.** Our state machine goes IDLE → PLANNING, but there's no "the agent has decided to do something but hasn't started yet" state. Warp's `BeforeExecution` is exactly this — the command has been sent to the PTY but preexec hasn't fired. For Somatic Blocks, this is the "proposal has been approved but the action hasn't started executing" state. Our `ProposalStatus` enum has APPROVED but not "approved-and-pending-execution."

---

## 4. Ambient Agent Spawn (Warp `ambient_agents/spawn.rs` + `task.rs`)

### What I said in the first pass
"Stream-based spawn API with lifecycle events."

### What the code ACTUALLY does

The spawn API is a **stream of `AmbientAgentEvent` values** that the caller consumes as a Rust async stream. The events are:

1. `TaskSpawned { task_id, run_id }` — the server accepted the task and assigned IDs
2. `StateChanged { state, status_message }` — the task's state changed (queued → working → completed)
3. `SessionStarted { session_join_info }` — the task's shared terminal session is ready to join
4. `TimedOut` — the polling timeout expired before the session was ready
5. `AtCapacity` — the cloud is at capacity; the task is queued but not started

The polling loop (`spawn.rs:100+`) is more sophisticated than I described:

- `TASK_STATUS_POLLING_DURATION = 80 seconds` — how long to poll for the session to be ready
- `TASK_STATUS_POLL_INTERVAL = 3 seconds` (production), `1ms` (test)
- `MAX_STALE_POLLS_BEFORE_FAILURE = 10` — if the task state doesn't change for 10 consecutive polls (~30s), give up. This catches the case where the server is wedged and never transitions the task off its prior state.

The `AmbientAgentTask` struct (task.rs:204) is **not** just a task description — it's a **full task record** with:

- `task_id`, `parent_run_id` — for task hierarchy (subagents of subagents)
- `state: AmbientAgentTaskState` — the lifecycle state
- `source: AgentSource` — 16 sources! (Linear, Slack, CLI, ScheduledAgent, Interactive, GitHubAction, GitLabWebhook, Jira, Autofix, BenchmarkTrial, etc.)
- `execution_location: ExecutionLocation` — Local vs. Remote
- `session_id`, `session_link` — for joining the shared terminal session
- `creator`, `executor` — who created and who is running the task
- `is_sandbox_running: bool` — is the execution sandbox active?
- `agent_config_snapshot: AgentConfigSnapshot` — frozen copy of the agent config used to create this task
- `artifacts: Vec<Artifact>` — outputs produced by the task
- `last_event_sequence: i64` — for event delivery resume (cursor-based replay)
- `children: Vec<String>` — run IDs of direct children (for nested orchestration)

The `AgentSource` enum (task.rs:39-57) is particularly revealing. Warp doesn't just have "user-initiated" and "agent-initiated" — it has **16 distinct sources**, each with different rules:
- `blocks_cloud_followups()` — GitHub Actions, webhooks, scorers, and autofix can't accept user follow-ups (they're automated, not conversational)
- `is_user_initiated()` — Linear, Slack, Interactive, WebApp, CloudMode, Jira are user-initiated; everything else is programmatic

### What I assumed wrong

1. **I said "stream-based spawn API"** — true, but I didn't explain **why** it's a stream instead of a function call. The stream exists because spawning an ambient agent is a **multi-step asynchronous process**: submit to server → server queues → server starts sandbox → sandbox starts shell → session is joinable. Each step can fail independently. A function call would have to block until the session is ready (up to 80 seconds) or return a future that the caller has to poll. The stream lets the caller react to each step as it happens — show "Task spawned" immediately, show "Session starting..." when the sandbox boots, show "Click to join" when the session is ready.

2. **I said "AtCapacity — concurrency ceiling signal"** — true, but I didn't explain that `AtCapacity` is **non-blocking**. The task is still queued; it will start when capacity frees up. The stream doesn't end on `AtCapacity` — it continues polling. This is different from our `Semaphore(2)` approach, which would block the 3rd subagent until one of the first two finishes. Warp's approach queues the 3rd task on the server and lets it start when capacity frees up, while still streaming status updates.

3. **I didn't mention `agent_config_snapshot`** — when a task is spawned, the agent config (model, harness, auth secret, environment) is **frozen** into the task record. This means if the user changes their model preference after spawning a task, the running task keeps its original config. This is critical for reproducibility — you can look at a completed task and know exactly what model and config it used.

4. **I didn't mention `last_event_sequence`** — this is a **cursor for event delivery resume**. If the client disconnects and reconnects, it sends `last_event_sequence` to the server, which replays all events after that sequence number. This is exactly the pattern we need for SSE reconnection after a network blip.

### What Halbert's code could be doing differently

Halbert has no subagent system at all. The `react_agent.py` (442 lines) is a single-agent ReAct loop with `_call_llm_with_tools()`. When the agent needs to run a long-running command (like `smartctl -t long`), it blocks the entire conversation.

**What we should do:**

1. **Don't use `Semaphore(2)` as the concurrency ceiling.** Use a **queue-based approach** like Warp: spawn the subagent, if capacity is full, queue it and stream `AtCapacity`. The user sees "2 subagents running, 1 queued" instead of "waiting for a slot." This is a better UX and doesn't block the primary conversation.

2. **Freeze the agent config into the subagent handle.** When we spawn a `StorageAuditorAgent`, snapshot the model, tier, endpoint, and sandbox config into the `SubagentHandle`. If the user changes their model preference mid-audit, the running audit keeps its original config. This is critical for reproducibility — "this finding was produced by llama3.1:70b at 2026-08-25T14:32:00Z" should be answerable from the task record.

3. **Add `last_event_sequence` to SSE events.** Each SSE event the subagent emits should carry a sequence number. If the frontend disconnects and reconnects, it sends the last sequence number it saw, and the backend replays all events after that. Without this, a network blip during a long subagent run means the user misses all the output.

4. **Steal the `AgentSource` enum.** Halbert's subagents should have a source field: `UserInitiated`, `ScheduledAgent`, `ProactiveFinding`, `ReflexTriggered`, `DreamCycle`. Each source has different rules — a `ProactiveFinding` subagent (spawned because the being noticed a failing disk) should not require user approval to start, but a `UserInitiated` subagent (user asked "audit my storage") should show in the UI immediately.

5. **Steal the `children` field.** If `StorageAuditorAgent` spawns `IncidentInvestigatorAgent` to investigate a disk error it found, the parent task should record the child's run ID. This gives us a **task tree** — we can render the full hierarchy of "the being noticed a failing disk → spawned a storage auditor → the auditor found a ZFS error → spawned an incident investigator → the investigator produced a fix proposal."

---

## 5. Conversation Status State Machine (Warp `conversation.rs:4721`)

### What I said in the first pass
"7 states including TransientError and Blocked."

### What the code ACTUALLY does

The `ConversationStatus` enum is **separate from the agent state machine**. It tracks the status of the **conversation** (the user-facing entity), not the agent's internal processing state. This is a critical distinction:

- Agent state: "I'm currently planning my next action" (internal)
- Conversation status: "The last turn finished with an error, and I'm retrying" (external)

The 7 states:
- `InProgress` — agent is running
- `Success` — last turn finished successfully
- `Error` — last turn finished with an error (terminal)
- `TransientError` — last turn failed, but automatic recovery is pending (NON-terminal — returns to InProgress when recovery sends, or falls to Error if recovery is exhausted)
- `Cancelled` — user cancelled the last turn
- `Blocked { blocked_action: String }` — agent action is blocked by the user (carries the specific blocked action)
- `WaitingForEvents` — agent yielded via `wait_for_events`, listening for input (quiescent but not terminal)

The `TransientError` state is the most interesting. It's **non-terminal** — the conversation is not done, it's recovering. The display string is "Reconnecting" (not "Error"), and the icon is the in-progress icon (not the error icon). This is a UX decision: the user sees "Reconnecting..." not "Error" when the model API fails and the system is retrying.

The `Blocked` state carries the `blocked_action` string — this is what the agent tried to do that was blocked. For example: `Blocked { blocked_action: "Write to /etc/ssh/sshd_config" }`. The UI can show "Agent blocked: wants to write to /etc/ssh/sshd_config. Approve? Deny?"

The `WaitingForEvents` state is for **agent-initiated waiting**. The agent calls `wait_for_events` and yields control. It's not done — it's listening for something (a subagent completion, a telemetry threshold, a user input). This is the "quiescent but alive" state — the being is present but not actively processing.

### What I assumed wrong

1. **I said "7 states"** — true, but I didn't explain the **terminal vs. non-terminal distinction**. `Error`, `Success`, and `Cancelled` are terminal (the conversation is done). `TransientError`, `Blocked`, and `WaitingForEvents` are non-terminal (the conversation is still alive). `InProgress` is the active state. This distinction matters for the UI — terminal states show a final result; non-terminal states show a spinner or a "waiting" indicator.

2. **I said "TransientError is for automatic retry"** — true, but I didn't explain the **recovery flow**. `TransientError` returns to `InProgress` when the recovery request sends (the retry is in flight), or falls to `Error` if recovery is exhausted (max retries hit). This is a **state transition with a timeout**, not just a flag.

3. **I didn't mention that `Blocked` is the approval-gate state.** When the agent proposes a config change and the user hasn't approved it yet, the conversation is `Blocked { blocked_action: "..." }`. This is exactly the state our approval workflow needs — the conversation is paused, not done, and the UI shows what's being waited on.

### What Halbert's code could be doing differently

Halbert's `AgentState` enum (states.py:18) has 10 states: `IDLE`, `PLANNING`, `SEARCHING`, `READING`, `EXECUTING`, `OBSERVING`, `REFLECTING`, `RESPONDING`, `AWAITING_CONFIRMATION`, `ERROR`. These are **agent processing states** — what the agent is doing right now. But there's no **conversation-level status** — what's the overall state of this conversation?

The `AWAITING_CONFIRMATION` state is the closest analog to Warp's `Blocked`, but it's an **agent state**, not a conversation status. This means:
- The UI can't easily show "Conversation: Blocked (waiting for approval)" as a top-level status
- There's no `TransientError` equivalent — when the model API fails, Halbert goes to `ERROR` state, which is terminal. There's no "retrying" state.
- There's no `WaitingForEvents` equivalent — when the agent is waiting for a subagent to complete, it's in... what state? `IDLE`? `OBSERVING`? Neither is right.

**What we should do:**

1. **Add a `ConversationStatus` enum separate from `AgentState`.** The agent state tracks what the agent is doing internally (planning, executing, reflecting). The conversation status tracks what the conversation looks like to the user (in progress, blocked, waiting, error, success). Both can be active simultaneously — the agent can be in `PLANNING` state while the conversation is `InProgress` status.

2. **Add `TransientError` with automatic retry.** When the model API fails, don't go to `ERROR` — go to `TransientError`, show "Reconnecting..." in the UI, and retry with exponential backoff (steal OCC's `RateLimiter`). Only go to `Error` after max retries are exhausted. This is critical for the sovereign host — the being should be resilient to transient API failures, not crash on every 429.

3. **Add `Blocked { blocked_action }` as the approval-gate state.** When a proposal is pending approval, the conversation status should be `Blocked { blocked_action: "Write to /etc/ssh/sshd_config" }`. The UI shows the blocked action and an approve/deny button. When approved, the status returns to `InProgress`. This replaces the current `AWAITING_CONFIRMATION` agent state with a more expressive conversation-level status.

4. **Add `WaitingForEvents` for subagent completion.** When the primary agent spawns a subagent and is waiting for it to complete, the conversation status should be `WaitingForEvents`. The UI shows "Waiting for Storage Auditor to complete..." with a spinner. This is different from `InProgress` (the agent is actively processing) and from `Blocked` (the agent is waiting for user input).

---

## 6. Hook Engine (OCC v2 `hooks/engine.mjs`)

### What I said in the first pass
"6 event types, env-var context passing, failOpen default."

### What the code ACTUALLY does

The hook engine is a **user-configured governance layer** that runs shell commands on agent events. The hooks are defined in `settings.json` and executed via `execSync` with a timeout.

The 6 event types and what they can do:

1. **`PreToolUse`** — runs BEFORE a tool is called. Can return `{ decision: 'deny', message: '...' }` to block the tool call. The agent sees "Blocked by hook: ..." as the tool result. This is a **veto** — the hook can prevent the agent from doing something.

2. **`PostToolUse`** — runs AFTER a tool is called. Can return `{ modifiedResult: ... }` to change what the agent sees as the tool result. This is a **filter** — the hook can redact secrets, truncate output, or inject warnings.

3. **`Stop`** — runs when the agent wants to stop (end of turn). Can return `{ preventStop: true }` to force the agent to continue. The agent gets a system message: "[System: A hook prevented stopping. Please continue with the task.]" This is a **continuation forcing** — the hook can prevent the agent from giving up.

4. **`Notification`** — fire-and-forget. Runs on notification events. Can't block or modify anything. This is for **external integration** — send a Slack message, update a dashboard, trigger a webhook.

5. **`PrePrompt`** — modify user input before the agent sees it. (Mentioned in the comment but not implemented in the engine — only 4 of the 6 event types have handlers.)

6. **`PostResponse`** — modify assistant output before the user sees it. (Also mentioned but not implemented.)

The **security model** is the most important detail (lines 126-145):

```javascript
const env = {
    ...process.env,
    HOOK_EVENT: String(context.event || ''),
    HOOK_TOOL: String(context.toolName || ''),
    HOOK_INPUT: JSON.stringify(context.input || {}),
};
const output = execSync(hook.command, { encoding: 'utf-8', timeout: hook.timeout || 10000, env });
```

The tool input is passed via **environment variables**, NOT interpolated into the command string. This is critical — if the agent calls `Bash({ command: "rm -rf /" })`, the hook command is NOT `my-hook.sh "rm -rf /"`. It's `my-hook.sh` with `HOOK_INPUT='{"command":"rm -rf /"}'` in the environment. The hook script can read `HOOK_INPUT` from the environment and parse it, but the command string itself is never exposed to shell injection.

The `failOpen` config (line 163) is also critical: by default, if a hook script errors (exits non-zero, times out, or crashes), the hook returns `null`, which means "allow." The agent continues. Only if `failOpen: false` is set does a hook error block the tool call.

### What I assumed wrong

1. **I said "6 event types"** — but only 4 are actually implemented (`PreToolUse`, `PostToolUse`, `Stop`, `Notification`). `PrePrompt` and `PostResponse` are mentioned in the comment but have no handlers. This is a **documented aspiration**, not a working feature.

2. **I said "env-var context passing"** — true, but I didn't explain **why** this matters. The alternative (interpolating tool input into the command string) would be a shell injection vulnerability. If the agent calls `Bash({ command: "'; rm -rf /; '" })`, and the hook command is `my-hook.sh "$HOOK_INPUT"`, the shell would execute `my-hook.sh ""; rm -rf /; ""`. The env-var approach prevents this — the tool input is in the environment, not in the command string.

3. **I didn't mention that hooks are synchronous.** `execSync` blocks the agent loop. A hook with a 10-second timeout blocks the agent for up to 10 seconds. There's no async hook support. This is a scalability concern — if you have 5 PreToolUse hooks, each tool call waits for all 5 to complete before executing.

### What Halbert's code could be doing differently

Halbert has no hook system at all. The closest thing is `autonomy/guardrails.py` (292 lines), which has confidence thresholds and safety checks, but these are **hardcoded in Python**, not user-configurable. The user can't add "run this shell command before any file write" without modifying the Python code.

**What we should do:**

1. **Implement the 4 working event types, not all 6.** `PreToolUse`, `PostToolUse`, `Stop`, and `Notification` are the proven patterns. `PrePrompt` and `PostResponse` are aspirational in OCC and add complexity without clear value. Skip them.

2. **Use the env-var security model.** This is non-negotiable. Never interpolate tool input into hook commands. Pass context via environment variables (`HOOK_EVENT`, `HOOK_TOOL`, `HOOK_INPUT`, `HOOK_SESSION_ID`, `HOOK_BLOCK_ID`).

3. **Make hooks async.** Use `asyncio.create_subprocess_exec` instead of `execSync`. Run hooks concurrently with `asyncio.gather`. Set a per-hook timeout and cancel if exceeded. This prevents a slow hook from blocking the entire agent.

4. **Wire hooks into Somatic Block transitions.** Instead of (or in addition to) hooking tool calls, hook **block transitions**: `PreBlockTransition(from_phase, to_phase)` can block a transition (e.g., prevent Action phase from starting without user approval), `PostBlockTransition` can modify the block after a transition (e.g., redact secrets from the block's output).

5. **Default `failOpen: true`.** Hook errors should not break the agent. If a hook script crashes, log the error and continue. Only block if `failOpen: false` is explicitly set.

6. **Add Halbert-specific hook events.** OCC's events are generic agent events. Halbert needs host-specific events: `PreConfigChange` (before writing to /etc/), `PreServiceRestart` (before systemctl restart), `PostFinding` (after a detector finds something), `PostReflection` (after the cognitive tick produces a reflection). These are the governance points that matter for a sovereign host.

---

## 7. Platform Sandboxing (OCC v2 `permissions/sandbox.mjs`)

### What I said in the first pass
"bubblewrap on Linux, seatbelt on macOS."

### What the code ACTUALLY does

The `Sandbox` class is a **command wrapper**, not a process isolator. It takes a command string and returns a NEW command string that wraps the original in sandbox tooling. The caller then executes the wrapped command.

**Linux (bubblewrap):**
```javascript
bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --bind /writable/dir /writable/dir -- ${command}
```
- Root filesystem is read-only (`--ro-bind / /`)
- `/dev` and `/proc` are mounted (needed for most commands)
- `/tmp` is a tmpfs (writable but ephemeral)
- Explicit writable directories via `--bind` (not `--ro-bind`)
- No network restriction (bubblewrap doesn't do network — use firejail or network namespaces for that)

**macOS (seatbelt):**
```javascript
sandbox-exec -p '(version 1)
(deny default)
(allow process-exec)
(allow process-fork)
(allow file-read*)
(allow sysctl-read)
(allow mach-lookup)
(allow file-write* (subpath "/tmp"))
(allow file-write* (subpath "/writable/dir"))
(allow network*)
' ${command}
```
- Default deny (everything is blocked unless explicitly allowed)
- Process execution and fork allowed (the command can run and spawn children)
- All file reads allowed (the command can read anything)
- File writes restricted to explicit subpaths
- Network is denied by default, allowed only if `allowNet` is set

**Path validation** (lines 47-53 for Linux, 82-88 for macOS):
- Must be a non-empty string
- Must start with `/` (absolute path)
- No shell metacharacters: `[\s'"`$\\;|&<>(){}!]` (Linux) or `['"\\;(){}]` (macOS)
- No null bytes

This validation is **defense-in-depth** — even though the paths are passed as discrete `--bind` arguments (not shell-interpolated), the validation prevents a malicious path from breaking out of the sandbox profile syntax.

### What I assumed wrong

1. **I said "bubblewrap with read-only root"** — true, but I didn't mention that **network is not restricted** on Linux. bubblewrap doesn't do network isolation. A sandboxed command can still make network connections. For Halbert, this means a subagent running in a bubblewrap sandbox can still phone home. We'd need to combine bubblewrap with network namespaces (`ip netns`) or firejail for network isolation.

2. **I said "seatbelt with deny default"** — true, but I didn't mention that **all file reads are allowed**. The seatbelt profile allows `file-read*` globally. Only writes are restricted. This means a sandboxed command can read `/etc/shadow`, `~/.ssh/id_rsa`, or any other sensitive file. For Halbert, this is a problem — a subagent shouldn't be able to read SSH keys unless explicitly granted.

3. **I didn't mention that `sandbox-exec` is deprecated.** Apple has been deprecating `sandbox-exec` since macOS 10.15. It still works, but Apple has warned that it may be removed. The long-term alternative is the `App Sandbox` (entitlements-based), but that requires a proper macOS app bundle. For a Python daemon like Halbert, `sandbox-exec` is the only practical option, but it's a known risk.

4. **I didn't mention the Windows fallback.** The code has `return command; // fallback: no sandbox` for Windows/other platforms. This means on Windows, there's NO sandboxing at all. The command runs with full permissions. For Halbert, this is acceptable (Halbert is Linux/macOS only), but it's worth noting.

### What Halbert's code could be doing differently

Halbert's `dashboard/routes/terminal.py` has safety tiers (SAFE/CAUTION/DANGEROUS/BLOCKED) but no actual sandboxing. A CAUTION command runs with full permissions — the safety tier just means "show a warning to the user." A DANGEROUS command is blocked entirely. There's no middle ground where a dangerous command runs in a sandbox.

**What we should do:**

1. **Don't steal OCC's sandbox directly.** OCC's sandbox is a command wrapper — it produces a new command string. This is fragile (shell escaping, nested quoting) and doesn't work well with PTY-based execution (the PTY gets the wrapped command, which includes the sandbox tooling's output). Instead, use **process-level sandboxing**: spawn the child process with restricted permissions, then apply the sandbox to the process, not the command.

2. **On macOS, use `sandbox-exec` but tighten the profile.** OCC's profile allows all file reads. Halbert's profile should deny reads to `~/.ssh/`, `~/.config/halbert/secrets/`, and other sensitive paths unless explicitly granted. The profile should look like:
```
(deny default)
(allow process-exec)
(allow process-fork)
(allow file-read* (subpath "/usr"))
(allow file-read* (subpath "/bin"))
(allow file-read* (subpath "/etc") (deny file-read* (subpath "/etc/ssh")))
(allow file-write* (subpath "/tmp"))
(allow file-write* (subpath "${writable_dir}"))
```

3. **On Linux, use bubblewrap + network namespaces.** bubblewrap alone doesn't restrict network. For subagents that shouldn't have network access (e.g., a storage auditor that only reads SMART data), combine bubblewrap with `unshare --net` to create a network namespace. For subagents that need network (e.g., a security hardening agent that checks for updates), allow network but restrict outbound to specific hosts.

4. **Add per-subagent sandbox profiles.** Each subagent type should have its own sandbox profile:
   - `StorageAuditorAgent`: read access to `/dev/sd*`, `/dev/nvme*`, `/dev/zvol/*`; write access to `/tmp` only; no network
   - `ConfigRefactorAgent`: read access to `/etc/`, write access to `/etc/` (with approval); no network
   - `SecurityHardeningAgent`: read access to everything; write access to `/etc/` (with approval); network access to specific security update hosts
   - `IncidentInvestigatorAgent`: read access to everything; write access to `/tmp` only; network access for log retrieval

5. **Steal the path validation.** The regex validation for writable paths is directly reusable. Add it to the sandbox profile generator to prevent path injection in the sandbox configuration.

---

## 8. Warp's Workflow Data Model (Warp `cloud_object_models/src/workflow.rs`)

### What I said in the first pass
"Workflows are exactly the Living Reflex data model."

### What the code ACTUALLY does

The `Workflow` enum has two variants, and they're more different than I described:

**`Workflow::Command`** — a parameterized shell command template:
```rust
Command {
    name: String,
    command: String,           // e.g. "git checkout {{branch}} && git pull origin {{branch}}"
    tags: Vec<String>,         // for search/categorization
    description: Option<String>,
    arguments: Vec<Argument>,  // [{name: "branch", arg_type: Text, default_value: "main"}]
    source_url: Option<String>,// where this workflow came from (GitHub, etc.)
    author: Option<String>,
    author_url: Option<String>,
    shells: Vec<Shell>,        // which shells this works with (bash, zsh, fish)
    environment_variables: Option<SyncId>, // cloud-synced env vars
}
```

**`Workflow::AgentMode`** — a parameterized agent prompt:
```rust
AgentMode {
    name: String,
    query: String,             // e.g. "Review the changes in {{branch}} and suggest improvements"
    description: Option<String>,
    arguments: Vec<Argument>,  // [{name: "branch", arg_type: Text, default_value: "main"}]
}
```

The key difference: `Command` runs a shell command directly. `AgentMode` injects the query as an agent prompt — the agent processes it through its full ReAct loop. A Living Reflex should be a `Command` with a trigger signature — when the trigger fires, the command runs automatically.

The `Argument` struct (line 278) is the parameter system:
```rust
Argument {
    name: String,
    arg_type: ArgumentType,    // Text, Integer, Float, Boolean, etc.
    description: Option<String>,
    default_value: Option<String>,
}
```

Arguments are substituted into the command/query template via `{{argument_name}}` syntax. The `command_parser.rs` handles this substitution.

### What I assumed wrong

1. **I said "reflexes are workflows with trigger signatures"** — true, but I didn't explain that Warp's workflows **don't have trigger signatures**. They're manually invoked — the user types the workflow name or selects it from a menu. A Living Reflex needs an additional field: `trigger: TriggerSignature` (telemetry thresholds + regex patterns). Without this, a workflow is just a saved command, not a reflex.

2. **I said "the argument system is directly reusable"** — true, but I didn't mention that the argument substitution is **template-based** (`{{argument_name}}`), not programmatic. This means the command string is a template that gets string-substituted before execution. This is simpler than a function call but less flexible — you can't do conditional logic in the template. For Living Reflexes, this is fine (the reflex is a fixed command with parameters), but for more complex reflexes, we'd need a programmatic approach.

3. **I didn't mention `source_url` and `author`** — these fields enable **workflow sharing**. A workflow can be published to a GitHub repo, and other users can install it. This is Warp's equivalent of an app store for terminal workflows. For Halbert, this could be a "reflex library" — users share reflexes for common host maintenance tasks ("when ZFS pool health degrades, run `zpool scrub` and notify").

### What Halbert's code could be doing differently

Halbert has no workflow or reflex system. The closest thing is `proactive/detector_runner.py`, which runs detectors that produce findings, and `findings/proposals.py`, which proposes fixes. But there's no way for the user to define "when X happens, do Y" as a reusable, parameterized, shareable artifact.

**What we should do:**

1. **Define the Reflex data model as an extension of Warp's Workflow.** A Reflex is a `Workflow::Command` with three additional fields:
   - `trigger: TriggerSignature` — telemetry thresholds + regex patterns that fire the reflex
   - `rollback: Vec<String>` — commands to undo the reflex's actions
   - `provenance: Provenance` — which incident(s) this reflex was synthesized from, when it was created, who approved it

2. **Use Warp's argument system for reflex parameters.** A ZFS scrub reflex might have `{{pool_name}}` as an argument, with the pool name detected from the trigger's telemetry data. The argument substitution is the same `{{name}}` template pattern.

3. **Add `source_url` and `author` for reflex sharing.** Users should be able to publish reflexes to a Git repo and install them on other hosts. This is how a "society of beings" shares knowledge — Host A's reflex for handling SMART failures can be installed on Host B.

4. **Don't implement `Workflow::AgentMode` for reflexes.** Reflexes should be deterministic commands, not agent prompts. An agent-prompt reflex would be non-deterministic (the agent might do something different each time), which is dangerous for automated triggers. If we need agent-assisted reflexes, they should be a separate type ("reflex-assisted workflows") that requires user confirmation.

---

## 9. Revised Assumptions Table

| First-pass assumption | Second-pass reality | Impact on design |
|---|---|---|
| "Cost-cascade self-tunes from outcomes" | The blending formula caps evidence weight at 0.9, preventing overfitting from lucky runs | Our outcome store needs the same cap |
| "Micro-compaction truncates old tool results" | Only results >200 chars are truncated; tool calls are preserved | Our threshold should be 200 chars, not arbitrary |
| "Warp's Block is a Somatic Block" | It's a terminal command block, not a generic lifecycle container | Steal the pattern (lifecycle + metadata + serialization), not the data model |
| "Stream-based spawn API" | The stream exists because spawning is a 5-step async process (submit → queue → sandbox → shell → joinable) | Our subagent spawn needs the same multi-step stream, not a function call |
| "7 conversation states" | Only 4 are terminal; 3 are non-terminal (TransientError, Blocked, WaitingForEvents) | Our conversation status needs the terminal/non-terminal distinction |
| "6 hook event types" | Only 4 are implemented; 2 are aspirational | Implement 4, skip 2 |
| "bubblewrap isolates commands" | bubblewrap doesn't do network isolation; seatbelt allows all file reads | Need network namespaces on Linux, tighter read restrictions on macOS |
| "Workflows are the reflex data model" | Workflows don't have trigger signatures; they're manually invoked | Reflexes = Workflows + trigger + rollback + provenance |
| "Halbert has 4-tier model allocation" | It has TWO separate complexity systems (intake/complexity.py LLM + tier_router.py heuristic) that don't talk to each other | Merge them, add outcome store |
| "Halbert has agent states" | Agent states (PLANNING, EXECUTING) are processing states, not conversation statuses | Add a separate ConversationStatus enum |

---

## 10. What This Changes About the Implementation Strategy

The second pass doesn't invalidate the first-pass strategy, but it sharpens it:

1. **Stage 1 (Somatic Blocks):** Don't copy Warp's Block data model. Steal the pattern (lifecycle states + metadata + timestamps + interaction mode + serialized form) but design the data model for cognitive events, not terminal commands. Add a `ConversationStatus` enum separate from `AgentState`.

2. **Stage 2 (PTY Backend):** Don't use OCC's command-wrapper sandbox approach. Use process-level sandboxing with tighter restrictions (deny reads to sensitive paths on macOS, add network namespaces on Linux). Steal the path validation regex.

3. **Stage 5 (Subagents):** Don't use `Semaphore(2)`. Use a queue-based approach with `AtCapacity` events. Freeze agent config into the subagent handle. Add `last_event_sequence` to SSE events for reconnection. Add `AgentSource` enum with Halbert-specific sources.

4. **Stage 7 (Living Reflexes):** Don't copy Warp's Workflow directly. Extend it with trigger signatures, rollback commands, and provenance. Use the argument system for parameters. Add `source_url` and `author` for sharing.

5. **Stage 9 (Context Watermark):** Use 80% threshold (not 75%). Add micro-compaction tier (truncate tool results >200 chars before full summarization). Use LLM for full-compaction summaries (not crude concatenation). Track compaction statistics.

6. **Cross-cutting:** Merge `intake/complexity.py` and `model/tier_router.py:_score_complexity()`. Add outcome store. Add rate limiter. Add hook engine with 4 event types (not 6), async execution, env-var security model.
