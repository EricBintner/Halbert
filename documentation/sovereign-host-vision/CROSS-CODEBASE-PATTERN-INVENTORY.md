# Cross-Codebase Pattern Inventory

**Date:** August 25, 2026
**Sources:**
- `open-claude-code/v2/` — Node.js reimplementation of Claude Code (~70 files, ~8K lines)
- `warp/` — Rust terminal emulator + AI agent platform (~60 crates, ~500K+ lines)
**Purpose:** Mine both codebases for patterns, features, and architectural decisions that should inform the Halbert sovereign-host-vision. Each finding maps to a vision stage or identifies a missing feature.

---

## 1. Findings Summary

| # | Pattern | Source | Vision Stage | Status in Halbert |
|---|---------|--------|-------------|-------------------|
| 1 | Cost-cascade model router with outcome store | OCC v2 | Stage 1 (Somatic Blocks) | Partial (`intake/budget.py` has tiers, no outcome feedback loop) |
| 2 | Micro-compaction before full compaction | OCC v2 | Stage 9 (Context Watermark) | Missing |
| 3 | Session teleport (export/import) | OCC v2 | New feature | Missing |
| 4 | File checkpointing with undo stack | OCC v2 | Stage 1 (Action blocks) | Partial (`autonomy/recovery.py` has rollback, no per-file checkpoint stack) |
| 5 | Hook engine (6 event types) | OCC v2 | New feature | Missing |
| 6 | Platform-specific command sandboxing | OCC v2 | Stage 2 (PTY) | Missing — critical gap |
| 7 | Command injection pattern detection | OCC v2 | Stage 2 (PTY) | Partial (`dashboard/routes/terminal.py` has safety tiers, no injection regex) |
| 8 | Agent teams with message queue | OCC v2 | Stage 5 (Subagents) | Missing |
| 9 | Cron/scheduled tasks with persistence | OCC v2 | Stage 7 (Living Reflexes) | Partial (`proactive/morning_report.py` exists, no scheduler) |
| 10 | Remote trigger tool (distributed agents) | OCC v2 | Stage 5 (Subagents) | Missing |
| 11 | Rate limiter with exponential backoff + jitter | OCC v2 | Cross-cutting | Missing |
| 12 | Block-based terminal model (BlockState lifecycle) | Warp | Stage 1 + Stage 6 | Partial (xterm.js has no block concept) |
| 13 | Ambient agent spawn + session join | Warp | Stage 5 (Subagents) | Missing — gold-standard pattern |
| 14 | Scheduled ambient agents (cloud-synced) | Warp | Stage 7 | Missing |
| 15 | Orchestration config state machine (local/cloud/harness) | Warp | Stage 5 | Missing |
| 16 | Conversation restoration into block list | Warp | Stage 6 (Frontend) | Missing — critical for session resume |
| 17 | Codebase auto-indexing with feature flags | Warp | Cross-cutting (SourcePrep) | Partial (SourcePrep exists, no auto-index trigger) |
| 18 | Workflows as cloud objects (AgentMode + Command) | Warp | Stage 7 (Living Reflexes) | Missing — Warp's equivalent of reflexes |
| 19 | PTY with mio event loop + signal handling | Warp | Stage 2 (PTY) | Missing — reference implementation |
| 20 | Multi-agent API with task store + transactions | Warp | Stage 5 (Subagents) | Missing |
| 21 | Conversation status state machine (7 states) | Warp | Stage 1 (Somatic Blocks) | Partial — Halbert has agent states, not conversation-level |
| 22 | Optimistic task creation (CLI subagent) | Warp | Stage 5 | Missing |
| 23 | Skills as injectable prompts | OCC v2 | Cross-cutting | Partial (Halbert has skills, no prompt-injection runner) |
| 24 | Tool search / dynamic tool discovery | OCC v2 | Cross-cutting | Missing |
| 25 | Multi-provider support (Anthropic/OpenAI/Google) | OCC v2 | Cross-cutting | Partial (`model/client.py` has Ollama + OpenAI) |

---

## 2. Detailed Findings

### 2.1 Cost-Cascade Model Router with Outcome Store

**Source:** `open-claude-code/v2/src/optimize/router.mjs`, `cascade.mjs`, `store.mjs`

**What it does:**
- `MetaHarnessRouter` routes each task to the CHEAPEST model that's "good enough"
- Model ladder: cheapest → most capable (e.g. Haiku → Sonnet → Opus)
- `estimateComplexity(text)` — heuristic 0..1 score from prompt text (length, hard/easy signal words, code fences, question count)
- `predict(model, complexity)` — blends a tier-based prior with recorded outcome stats
- Quality bar (default 0.7) — if a cheap model's predicted success clears the bar, use it
- `escalate(failedModelId)` — step up one tier after a failure
- `OutcomeStore` — JSONL append-only log of real outcomes (model, success, latency, tokens, cost)
- Self-tuning: as samples accumulate (min 3), recorded stats override the prior
- **Opt-in** — default behavior is byte-identical without `--self-optimize`

**Relevance to Halbert:**
- Halbert has `intake/budget.py` with 4-tier allocation, but NO outcome feedback loop
- The cascade pattern is exactly what the Somatic Block "Deliberation" phase needs: route to the cheapest model that can handle this block, escalate on failure
- The `OutcomeStore` JSONL pattern is directly portable to Halbert's SQLite stores
- The complexity heuristic (signal words + length + code fences) could replace or augment `intake/complexity.py`

**What to steal:**
- The `estimateComplexity()` heuristic — adapt for host-mind tasks (storage audit vs. config refactor vs. incident investigation)
- The outcome store pattern — record every Somatic Block's model choice + success + latency + cost
- The escalation ladder — Tier 0 (heuristic) → Tier 1 (local model) → Tier 2 (specialist) → Tier 3 (frontier)
- The opt-in default — don't change behavior until the user enables self-optimization

---

### 2.2 Micro-Compaction Before Full Compaction

**Source:** `open-claude-code/v2/src/core/context-manager.mjs` (lines 66-113)

**What it does:**
- `microCompact()` — removes verbose tool results older than 5 turns, keeping the tool call reference but truncating result content to 100 chars + `...[truncated]`
- Only runs full compaction (summarize old messages) if micro-compaction doesn't get under the threshold
- Token estimation: 4 chars ≈ 1 token, with per-block-type overhead (16 chars for role, 20 chars for tool_use JSON)
- Threshold: 80% of max tokens (not 75% like our vision spec)

**Relevance to Halbert:**
- Our Stage 9 (Context Watermark) specifies a 75% trigger but doesn't distinguish micro vs. full compaction
- Micro-compaction is critical for Somatic Blocks — old Action blocks' tool output (command stdout, file diffs) is the bulk of context but rarely needed after a few turns
- The two-tier approach (micro first, full second) prevents unnecessary summarization

**What to steal:**
- Two-tier compaction: truncate old tool results before summarizing
- Per-block-type token estimation (different overhead for text vs. tool_use vs. tool_result)
- Keep last N turns intact during micro-compaction

---

### 2.3 Session Teleport (Export/Import)

**Source:** `open-claude-code/v2/src/core/session.mjs` (lines 87-142)

**What it does:**
- `exportForTeleport(state)` — base64-encodes session (messages, turn count, model) for transfer between machines
- `importFromTeleport(data, state)` — decodes with validation:
  - Messages filtered to `{role, content}` shape only
  - Turn count validated as non-negative integer
  - Model validated against regex `^[\w.:/-]{3,80}$` (no shell injection)
  - Session ID reset to `sess_teleport_{timestamp}`

**Relevance to Halbert:**
- The vision mentions "migration/death" (identity export to a new host) as post-MVP
- But session teleport is more immediate — when Halbert moves from one host to another (e.g. laptop → server), the active session should come with it
- The validation patterns (regex model check, message shape filter) are directly reusable

**What to steal:**
- Base64 session export/import with strict validation
- The "reset session ID on import" pattern (prevent ID collisions across hosts)
- This could be a Stage 3 (SQLite Session Store) extension — export SQLite DB + import with schema validation

---

### 2.4 File Checkpointing with Undo Stack

**Source:** `open-claude-code/v2/src/core/checkpoints.mjs`

**What it does:**
- `CheckpointManager` — before any file edit, saves original content to `.claude/checkpoints/{id}.json`
- Stack-based undo: `undo()` pops the last checkpoint and restores the file
- Max 50 checkpoints, FIFO trim when exceeded
- Each checkpoint: id, filePath, relativePath, content, timestamp, size

**Relevance to Halbert:**
- Halbert has `autonomy/recovery.py` with `RecoveryAction.ROLLBACK`, but it's proposal-level (rollback an entire approved change), not file-level
- For Somatic Block Action blocks, we need per-file checkpoints BEFORE the action runs, so we can undo individual file changes if the action partially fails
- The stack pattern is exactly right — each Action block pushes checkpoints, rollback pops them

**What to steal:**
- Per-file checkpoint stack (not just proposal-level rollback)
- FIFO trim with configurable max
- Checkpoint metadata: file path, timestamp, size (for display in the undo UI)
- Wire into Somatic Block Action phase: before executing commands, checkpoint all affected files

---

### 2.5 Hook Engine (6 Event Types)

**Source:** `open-claude-code/v2/src/hooks/engine.mjs`

**What it does:**
- 6 hook event types: `PreToolUse`, `PostToolUse`, `Stop`, `Notification`, `PrePrompt`, `PostResponse`
- `PreToolUse` — can block tool execution (return `decision: 'deny'`)
- `PostToolUse` — can modify tool results (return `modifiedResult`)
- `Stop` — can prevent the agent from stopping (return `preventStop: true`)
- Hooks defined in `settings.json` under `hooks` key
- Hook execution: shell command with context passed via env vars (NOT interpolated into command string — security)
- `failOpen` config: default true (hook errors don't block), can be set to false
- Timeout: 10s default per hook

**Relevance to Halbert:**
- This is a governance layer we're completely missing
- For the sovereign host, hooks could:
  - `PreToolUse` on Bash: run the injection check + safety tier validation before any command
  - `PostToolUse` on file edits: trigger SourcePrep re-indexing of changed files
  - `Stop`: prevent the agent from stopping if there are unresolved findings
  - `Notification`: push to the proactive channel when a long-running subagent completes
- The env-var-only context passing is a critical security pattern

**What to steal:**
- The 6-event-type taxonomy
- Env-var context passing (never interpolate tool input into hook commands)
- `failOpen` default — hooks shouldn't break the agent when they error
- Per-hook timeout

---

### 2.6 Platform-Specific Command Sandboxing

**Source:** `open-claude-code/v2/src/permissions/sandbox.mjs`

**What it does:**
- `Sandbox.wrapCommand(command, options)` — wraps commands in platform-specific sandboxes
- **Linux:** bubblewrap (`bwrap`) — read-only root, `/dev`, `/proc`, `/tmp` tmpfs, explicit writable dirs
- **macOS:** sandbox-exec (seatbelt) — deny default, allow process-exec/fork/file-read, explicit file-write subpaths
- **Windows/other:** passthrough (no sandbox)
- Path validation: must be absolute, no shell metacharacters, no null bytes
- `check()` — reports whether sandbox tooling is available on the current platform

**Relevance to Halbert:**
- This is a **critical gap** in Stage 2 (PTY Backend)
- Our current `dashboard/routes/terminal.py` has safety tiers (SAFE/CAUTION/DANGEROUS/BLOCKED) but no actual sandboxing — it just refuses dangerous commands
- A real PTY needs real sandboxing — the agent can run commands, but they should be contained
- For subagents (Stage 5), each subagent's PTY should be sandboxed with scoped writable dirs

**What to steal:**
- The platform detection + dispatch pattern
- bubblewrap for Linux, seatbelt for macOS
- Path validation regex (absolute, no metacharacters, no null bytes)
- Per-subagent sandbox profiles (StorageAuditor gets `/dev/sda*` + `/tmp`, ConfigRefactor gets `/etc/` + `/tmp`)

---

### 2.7 Command Injection Pattern Detection

**Source:** `open-claude-code/v2/src/permissions/injection-check.mjs`

**What it does:**
- 16 dangerous patterns: `rm -rf /`, pipe to shell, backtick execution, `$()`, write to `/etc/`, curl pipe to shell, mkfs, dd to device, fork bomb, chmod 777 root, eval variable, exec fd redirect
- `checkInjection(command)` → `{ safe, pattern, label }`
- `usesElevation(command)` — detects `sudo`, `su -`, `doas`

**Relevance to Halbert:**
- Our `dashboard/routes/terminal.py` has safety tiers but the pattern list isn't documented
- This is a battle-tested list of injection vectors that we should adopt verbatim
- The `usesElevation()` check is important for the PTY — sudo in a web PTY needs special handling (password prompt routing)

**What to steal:**
- The 16-pattern list (adapt for host-mind context — add `zpool destroy`, `lvremove`, `ip link delete`)
- Separate elevation detection (sudo/su/doas) from injection detection
- Return labeled results for UI display ("Blocked: pipe to shell")

---

### 2.8 Agent Teams with Message Queue

**Source:** `open-claude-code/v2/src/agents/teams.mjs`, `tools/send-message.mjs`

**What it does:**
- `AgentTeams` class — register named agents with roles, communicate via messages
- `sendMessage(to, message)` — send to one teammate, collect all events
- `broadcast(message)` — send to all teammates in parallel
- `SendMessageTool` — in-agent tool for inter-agent communication
- Message types: `request`, `response`, `notification`, `handoff`
- Message queue: per-agent Map of messages, `receive(agentId)` drains the queue
- Cryptographic message IDs (`randomBytes(6)`)
- Message log with timestamp + result count

**Relevance to Halbert:**
- Our Stage 5 (Subagent Forking) describes subagents but not how they communicate WITH EACH OTHER
- The `StorageAuditorAgent` might find a disk issue and need to notify the `IncidentInvestigatorAgent`
- The `handoff` message type is exactly right for subagent-to-subagent task transfer
- The broadcast pattern is useful for the Dream Cycle — broadcast "consolidate your findings" to all subagents

**What to steal:**
- Named agent registration with roles
- 4 message types (request/response/notification/handoff)
- Per-agent message queue with drain-on-receive
- Broadcast for parallel fan-out
- This becomes the `SubagentManager` communication layer in Stage 5

---

### 2.9 Cron/Scheduled Tasks with Persistence

**Source:** `open-claude-code/v2/src/core/scheduler.mjs`, `tools/cron-create.mjs`

**What it does:**
- `Scheduler` class — cron-based task scheduling persisted to `~/.claude/scheduled_tasks.json`
- Tasks: id, name, cron expression, prompt, model, enabled, createdAt, lastRun, runCount, intervalMs
- `runDue()` — checks all tasks, returns those due to run, updates lastRun + runCount
- `setEnabled(taskId, enabled)` — toggle without deleting
- Cron parsing: shorthand (`5m`, `1h`, `30s`, `1d`) or full cron expression (defaults to 5 min)
- `CronCreateTool` / `CronDeleteTool` / `CronListTool` — agent can create/list/delete scheduled tasks
- `CLAUDE_CODE_DISABLE_CRON` env var to globally disable

**Relevance to Halbert:**
- This is the scheduler infrastructure that `proactive/morning_report.py` needs
- For Living Reflexes (Stage 7), reflexes need to be checked on a schedule — "check SMART stats every 6 hours"
- The `runDue()` pattern is exactly right — the cognitive tick can call `scheduler.runDue()` and execute any due tasks
- The disable env var is important for safety — the user should be able to globally disable scheduled agent actions

**What to steal:**
- JSON-persisted scheduler with enable/disable per task
- Shorthand cron parsing (`5m`, `1h`, etc.)
- `runDue()` pattern for the cognitive tick to call
- Global disable env var
- Agent-creatable scheduled tasks (the being schedules its own follow-ups)

---

### 2.10 Remote Trigger Tool

**Source:** `open-claude-code/v2/src/tools/remote-trigger.mjs`

**What it does:**
- `RemoteTriggerTool` — sends a task to a remote agent endpoint for execution
- Supports sync (wait for result) and async (fire-and-forget) modes
- Auth via `REMOTE_AGENT_TOKEN` env var (Bearer token)
- Configurable timeout (default 5 min)
- `AbortController` for timeout enforcement

**Relevance to Halbert:**
- For multi-host Halbert (the "society of beings" post-MVP), this is how one Halbert instance asks another to do something
- More immediately: a subagent could run on a different machine (e.g. storage audit on the NAS, network audit on the router)
- The async mode is critical — fire off a long-running audit and get notified when it completes

**What to steal:**
- Remote task execution with sync/async modes
- Bearer token auth
- AbortController timeout pattern
- This extends Stage 5 (Subagents) to remote hosts

---

### 2.11 Rate Limiter with Exponential Backoff + Jitter

**Source:** `open-claude-code/v2/src/core/rate-limiter.mjs`

**What it does:**
- Handles HTTP 429 (rate limited) and 529 (overloaded) responses
- Exponential backoff: `baseDelay * 2^retryCount` + random jitter
- Respects `Retry-After` header for 429s
- Max 5 retries, max 60s delay
- `shouldWait()` / `remainingWait()` — check before making requests
- `reset()` — clear state on success

**Relevance to Halbert:**
- Halbert's `model/client.py` doesn't have rate limiting — it will hammer the API and get throttled
- For subagents (Stage 5), multiple concurrent model calls need a shared rate limiter
- The 529 handling is important — model providers overload, and the agent should back off gracefully

**What to steal:**
- Exponential backoff with jitter (prevents thundering herd)
- `Retry-After` header respect
- Shared rate limiter instance across all model calls (primary + subagents)

---

### 2.12 Block-Based Terminal Model

**Source:** `warp/app/src/terminal/model/block.rs` (1098+ lines), `block.rs:297` `Block` struct, `block.rs:623` `BlockState` enum

**What it does:**
- `Block` — the fundamental unit of terminal output. Each command + its output is one block.
- `BlockState` enum: `BeforeExecution`, `Executing`, `DoneWithExecution`, `DoneWithNoExecution`, `Background`, `Static`
- Block metadata: `pwd`, `git_branch`, `git_branch_name`, `virtual_env`, `conda_env`, `node_version`, `exit_code`, `session_id`, `shell_host`
- Timestamps: `creation_ts`, `start_ts`, `completed_ts`
- `InteractionMode` — how the block interacts with the AI agent
- `BlockMetadata` — session_id + cwd for context
- `SerializedBlock` — for persistence/restoration

**Relevance to Halbert:**
- This is the **gold-standard pattern** for Somatic Blocks (Stage 1)
- Warp's `Block` is literally a Somatic Block for terminal commands — it has lifecycle states, metadata, timestamps, and serialization
- Our `SomaticBlock` should follow this structure but extend it to non-terminal blocks (findings, proposals, reflections)
- The `InteractionMode` concept is critical — blocks can be in different modes relative to the agent (autonomous, supervised, observed)

**What to steal:**
- The `BlockState` lifecycle pattern (BeforeExecution → Executing → DoneWithExecution)
- Block metadata fields (pwd, git_branch, exit_code, session_id)
- `InteractionMode` — agent interaction modes per block
- `SerializedBlock` for persistence and conversation restoration
- The `BlockId` / `BlockIndex` type system

---

### 2.13 Ambient Agent Spawn + Session Join

**Source:** `warp/app/src/ai/ambient_agents/spawn.rs` (338 lines), `mod.rs`

**What it does:**
- `AmbientAgentEvent` enum: `TaskSpawned`, `StateChanged`, `SessionStarted`, `TimedOut`, `AtCapacity`
- Stream-based API: spawn an ambient agent and monitor its lifecycle as a stream of events
- `SessionJoinInfo` — when the agent's shared session is ready, provides a join link
- Polling with bounded retry: `TASK_STATUS_POLLING_DURATION` (80s), `MAX_STALE_POLLS_BEFORE_FAILURE` (10)
- `AmbientConversationStatus`: `Success`, `Error`, `Cancelled`, `Blocked`
- `AtCapacity` — cloud agent capacity limit reached, task queues but doesn't block

**Relevance to Halbert:**
- This is the **gold-standard pattern** for Stage 5 (Subagent Forking)
- "Ambient agent" = our subagent — runs in the background, doesn't block the primary conversation
- The stream-based lifecycle API is exactly right — the primary agent watches a stream of events from the subagent
- `SessionJoinInfo` is critical — the user should be able to "join" a subagent's session to see what it's doing
- `AtCapacity` — our concurrency ceiling (Semaphore(2)) should emit this same signal

**What to steal:**
- Stream-based spawn API (not just a function call)
- Lifecycle events: spawned → state changed → session started → timed out / at capacity
- Session join links for subagent observation
- Bounded retry with stale poll detection
- `Blocked` status — subagent can be blocked on a user action

---

### 2.14 Scheduled Ambient Agents (Cloud-Synced)

**Source:** `warp/app/src/ai/ambient_agents/scheduled.rs` (396 lines)

**What it does:**
- `ScheduledAmbientAgent` — a cloud object that schedules ambient agent runs
- `CloudScheduledAmbientAgent` — the cloud-synced version
- `UpdateScheduleParams` — update name, cron schedule, prompt, enabled state
- Revision-enforced (optimistic concurrency control)
- Sync queue integration — updates go through a queue with retry
- `should_show_activity_toasts()` — false (scheduled agents are quiet)
- `warn_if_unsaved_at_quit()` — true (don't lose scheduled tasks)

**Relevance to Halbert:**
- This is the production-grade version of OCC's cron scheduler
- For Living Reflexes (Stage 7), reflexes need scheduled execution — "check SMART stats every 6 hours"
- The revision-enforced cloud sync is overkill for single-host Halbert, but the pattern is right for multi-host
- The "quiet" toast setting is important — scheduled tasks shouldn't spam notifications

**What to steal:**
- Scheduled agent as a first-class object (not just a cron entry)
- Enable/disable without delete
- Revision control for concurrent modifications
- Quiet mode for scheduled tasks

---

### 2.15 Orchestration Config State Machine

**Source:** `warp/app/src/ai/orchestration/edit_state.rs` (268 lines), `config_state.rs` (286 lines), `providers.rs` (350 lines)

**What it does:**
- `OrchestrationConfigState` — tracks harness, execution mode (local/cloud), model, auth secret, environment
- `apply_execution_mode_change()` — toggling Local ↔ Cloud cascades into dependent fields (model fallback, environment pre-fill, auth re-resolution)
- `apply_auth_secret_change()` — records and persists auth secret selection
- `revalidate_after_catalog_change()` — when available models change, resets vanished models to default, drops deleted secrets
- `OptionSnapshot` — plain-data option lists for UI rendering (rows, ordering, badges, disabled reasons, load state, selection)
- `OptionBadge` — Default, Recent, Connected, Recommended

**Relevance to Halbert:**
- For Stage 5 (Subagents), each subagent type needs its own orchestration config — which model, which harness, which auth, which environment
- The cascade pattern is critical: changing the subagent type should cascade into model/environment/auth re-resolution
- The `OptionSnapshot` pattern is exactly right for the frontend — render subagent config as option lists with badges

**What to steal:**
- Config state machine with cascading field updates
- `OptionSnapshot` for frontend-neutral config rendering
- Revalidation after catalog changes (models appear/disappear)
- Badge system (Default, Recent, Connected, Recommended)

---

### 2.16 Conversation Restoration into Block List

**Source:** `warp/app/src/terminal/conversation_restoration.rs`

**What it does:**
- `prepare_conversation_block_restoration()` — rebuilds persisted command blocks in the terminal model, then plans agent-block placement
- `ConversationBlockRestorationPlan` — frontend-neutral plan of which exchanges go where
- `RestoredConversationExchange` — one exchange + its position relative to command blocks
- `command_block_indices_for_exchanges()` — maps exchanges to their position in the block list
- Filters conversation down to visible exchanges

**Relevance to Halbert:**
- This is the **critical missing piece** for Stage 6 (Frontend Terminal Docking)
- When a user resumes a session, the terminal needs to reconstruct the block list (commands + agent exchanges) in the right order
- Our current session resume (JSON files) just loads messages — it doesn't reconstruct the visual block layout
- The frontend-neutral plan pattern is exactly right — the plan is computed once, both GUI and TUI render from it

**What to steal:**
- `ConversationBlockRestorationPlan` — compute the plan once, render in any frontend
- Block-to-exchange mapping (which agent exchange belongs before which command block)
- Serialized block list items for terminal reconstruction

---

### 2.17 Codebase Auto-Indexing with Feature Flags

**Source:** `warp/app/src/ai/codebase_auto_indexing.rs`

**What it does:**
- `CodebaseAutoIndexingSurface` — Local vs. Remote indexing
- `should_use_codebase_indexing()` — checks feature flag + user setting
- `should_auto_index_codebase()` — checks feature flag + user setting + auto-indexing setting
- `auto_index_candidate_roots()` — deduplicates roots and filters by should-request-index predicate
- Feature flags: `FullSourceCodeEmbedding`, `RemoteCodebaseIndexing`

**Relevance to Halbert:**
- SourcePrep indexing should be automatic when a new project is opened, but gated by user settings
- The feature flag pattern allows gradual rollout — enable for testing, disable if it causes problems
- The candidate roots deduplication is important — don't re-index the same directory twice

**What to steal:**
- Auto-indexing gated by feature flag + user setting
- Surface distinction (local vs. remote indexing)
- Candidate root deduplication
- This should be wired into the SourcePrep integration in Halbert's AGENTS.md

---

### 2.18 Workflows as Cloud Objects (AgentMode + Command)

**Source:** `warp/crates/cloud_object_models/src/workflow.rs`, `warp/app/src/workflows/`

**What it does:**
- `Workflow` enum: `AgentMode { name, query, description, arguments }` | `Command { name, command, tags, description, arguments, source_url, author, shells, environment_variables }`
- `Argument` struct: name, arg_type (Text, etc.), description, default_value
- Workflows are cloud-synced objects with revision control
- `local_workflows.rs` — local workflow file management
- `workflow_view/` — UI for browsing and invoking workflows
- `command_parser.rs` — parses workflow command templates with argument substitution

**Relevance to Halbert:**
- This is **exactly** the Living Reflexes pattern (Stage 7), but for user-created workflows instead of self-synthesized reflexes
- A Living Reflex is a `Workflow::Command` with a trigger signature instead of manual invocation
- The `AgentMode` variant is a workflow that runs as an agent prompt — this is the "1-click fix" pattern
- The argument system (name, type, description, default) is directly reusable for reflex parameters

**What to steal:**
- Workflow as a first-class object with two variants (command + agent mode)
- Argument system with types and defaults
- Local + cloud-synced storage
- Command template parsing with argument substitution
- This IS the Living Reflex data model — reflexes are workflows with trigger signatures

---

### 2.19 PTY with mio Event Loop + Signal Handling

**Source:** `warp/app/src/terminal/local_tty/unix.rs` (1098 lines), `spawner.rs` (334 lines)

**What it does:**
- `make_pty(size)` — calls `nix::pty::openpty()` with winsize, sets `FD_CLOEXEC` on both fds
- `PtySpawner` — spawns child process in the PTY slave, handles shell detection, Docker sandbox mode
- `EventedPty` / `EventedReadWrite` — mio-based event loop for PTY I/O
- Signal handling: `SIGWINCH` (terminal resize), `signal_hook_mio` for signal integration
- Shell startup: bootstrap script injection, history size configuration, environment setup
- Docker sandbox mode: mounts init dir read-only, starts bash with custom rcfile

**Relevance to Halbert:**
- This is the **reference implementation** for Stage 2 (Real PTY Backend)
- We can't copy it directly (Rust vs. Python), but the patterns are directly translatable:
  - `openpty()` + `FD_CLOEXEC` → Python `os.openpty()` + `fcntl.F_SETFD`
  - mio event loop → Python `asyncio` + `aiofiles` on the master fd
  - `SIGWINCH` handling → Python `signal.signal(signal.SIGWINCH, handler)`
  - Docker sandbox → Python `subprocess` with docker args
- The bootstrap script injection is important — the PTY needs to set up the shell environment correctly

**What to steal:**
- `openpty()` with winsize + `FD_CLOEXEC`
- Event-loop-based I/O (not blocking reads)
- `SIGWINCH` → resize the PTY
- Shell bootstrap script injection
- Docker sandbox mode for isolated subagent PTYs

---

### 2.20 Multi-Agent API with Task Store + Transactions

**Source:** `warp/app/src/ai/agent/task.rs` (1022 lines), `task_store.rs` (471 lines), `warp/crates/warp_multi_agent_client/`

**What it does:**
- `Task` — the unit of work in the multi-agent system
- `TaskStore` — persists tasks with optimistic concurrency
- `Transaction` / `SavedTask` — atomic task updates
- `SubagentParams` — tool call ID + subagent call metadata
- `ServerTask` — task sourced from the server
- `CLIAgentSubtask` — optimistic task creation for CLI subagents (before server confirms)
- `UpgradeOptimisticTaskError` — error handling for optimistic → real task upgrades
- `derive_todo_lists_from_root_task()` — todo lists extracted from task hierarchy
- `compute_task_depths()` — depth calculation for nested subagent tasks

**Relevance to Halbert:**
- This is the **production-grade pattern** for Stage 5 (Subagent Forking)
- The task store + transaction pattern is critical — subagent state changes must be atomic
- Optimistic task creation is important for responsiveness — show the subagent in the UI immediately, confirm with the backend later
- Todo list derivation from task hierarchy is exactly right — subagent todos should roll up to the parent

**What to steal:**
- Task as a first-class persisted object (not just a function call)
- Transaction-based updates for atomicity
- Optimistic creation pattern (show in UI before backend confirms)
- Todo list derivation from task hierarchy
- Task depth computation for nested subagents

---

### 2.21 Conversation Status State Machine (7 States)

**Source:** `warp/app/src/ai/agent/conversation.rs:4721` `ConversationStatus` enum

**What it does:**
- 7 states: `InProgress`, `Success`, `Error`, `TransientError`, `Cancelled`, `Blocked { blocked_action }`, `WaitingForEvents`
- `TransientError` — non-terminal: automatic recovery (retry or resume) is pending
- `Blocked` — agent action blocked by user (carries the blocked action string)
- `WaitingForEvents` — agent yielded via `wait_for_events`, listening for input (quiescent but not terminal)
- Each state has a display string + icon + color
- `render_icon()` and `status_icon_and_color()` — UI rendering helpers

**Relevance to Halbert:**
- Our `agents/state_machine.py` has agent states (PLANNING, EXECUTING, REFLECTING) but not conversation-level states
- The `TransientError` state is critical — model API failures should trigger automatic retry, not a hard error
- `Blocked` is exactly right for the approval workflow — when a proposal is pending approval, the conversation is `Blocked { blocked_action: "pending approval for /etc/ssh/sshd_config change" }`
- `WaitingForEvents` is the quiescent state — the being is alive but waiting for input (telemetry, user, subagent completion)

**What to steal:**
- 7-state conversation status machine (separate from agent state machine)
- `TransientError` for automatic retry (not terminal)
- `Blocked { blocked_action }` for approval-gated actions
- `WaitingForEvents` for quiescent state
- Per-state icon + color for UI

---

### 2.22 Optimistic Task Creation

**Source:** `warp/app/src/ai/agent/task.rs:92-100` `optimistic` module, `CLIAgentSubtask`

**What it does:**
- When a CLI agent spawns a subtask, an optimistic task is created immediately (before server confirms)
- `CLIAgentSubtask { block_id }` — links the optimistic task to a terminal block
- `UpgradeOptimisticTaskError` — error variants for invalid upgrade scenarios:
  - `RootWithUnexpectedParent` — root task shouldn't have a parent
  - `CLISubagentMissingParent` — CLI subagent must have a parent
  - `CLISubagentMissingSubagentCall` — must have a subagent call to upgrade
  - `UnexpectedUpgrade` — can't upgrade a task that already has server data

**Relevance to Halbert:**
- For Stage 5 (Subagents), when the primary agent decides to spawn a subagent, the UI should show the subagent immediately — not wait for the PTY to start
- The optimistic pattern: create the subagent handle + render the terminal tile, then actually spawn the PTY
- If the spawn fails, upgrade the optimistic task to an error state
- The error variants are directly reusable

**What to steal:**
- Optimistic subagent creation (show in UI before PTY starts)
- Upgrade path: optimistic → confirmed | error
- Error variants for invalid upgrade scenarios

---

### 2.23 Skills as Injectable Prompts

**Source:** `open-claude-code/v2/src/skills/runner.mjs`, `loader.mjs`

**What it does:**
- `SkillRunner.execute(name, args)` — loads skill, injects its prompt as a user message, runs the agent loop
- Skill prompt: `$ARGUMENTS` placeholder replaced with args
- Message format: `[Invoking skill: {name}]\n\n{prompt}\n\nArguments: {args}`
- `listAvailable()` — returns name, description, aliases for display

**Relevance to Halbert:**
- Halbert has skills (the `.devin/skills/` system) but they're not integrated into the agent loop
- The prompt-injection pattern is the simplest possible skill execution — no special tool, just context injection
- For the sovereign host, skills could be "reflexes" — inject the reflex prompt when a trigger matches

**What to steal:**
- Skill = prompt template + `$ARGUMENTS` substitution
- Injection as a user message (not a system message — keeps it in the conversation history)
- `listAvailable()` for UI display

---

### 2.24 Tool Search / Dynamic Tool Discovery

**Source:** `open-claude-code/v2/src/tools/tool-search.mjs`, `registry.mjs:96-109`

**What it does:**
- `ToolSearchTool` — searches available tools by name/description
- `registerMcpTools(mcpTools, callFn)` — dynamically registers MCP tools into the registry
- MCP tools wrapped in a standard interface: `{ name, description, inputSchema, validateInput, call }`
- `_mcpTools` reference on ToolSearchTool for search
- `_registry` back-reference for dynamic registration

**Relevance to Halbert:**
- As Halbert grows, the tool list will exceed what fits in the system prompt
- Tool search lets the agent discover tools on demand — "I need to check ZFS status, what tool does that?"
- MCP tool registration is critical for the plugin system — external tools should register dynamically

**What to steal:**
- Tool search tool (agent can query available tools)
- Dynamic MCP tool registration with wrapper interface
- Standard tool interface: name, description, inputSchema, validateInput, call

---

### 2.25 Multi-Provider Support

**Source:** `open-claude-code/v2/src/core/agent-loop.mjs:263-271`, `providers.mjs`

**What it does:**
- `detectProvider(model)` — routes based on model name prefix (`gpt-` → OpenAI, `gemini` → Google, else Anthropic)
- Per-provider call functions: `callAnthropic`, `callOpenAI`, `callGoogle`
- Per-provider response converters: `convertOpenAIResponse`, `convertGoogleResponse`
- Streaming support per provider
- OpenAI: converts tool_use blocks to `function` type tools, maps `tool_result` to `tool` role
- Google: converts to `contents`/`parts` format

**Relevance to Halbert:**
- Halbert's `model/client.py` has Ollama + OpenAI but the abstraction is ad-hoc
- The provider detection + dispatch pattern is cleaner — one entry point, per-provider implementations
- For the cost-cascade router (finding 2.1), the router needs to know which providers are available

**What to steal:**
- Provider detection by model name
- Per-provider call + convert functions
- Standard internal message format (Anthropic's content blocks) as the lingua franca
- Convert to/from provider-specific formats at the boundary

---

## 3. New Features Identified (Not in Current Vision)

These are patterns from the two codebases that aren't in the sovereign-host-vision at all:

### 3.1 Hook Engine (Governance Layer)
- 6 event types: PreToolUse, PostToolUse, Stop, Notification, PrePrompt, PostResponse
- User-configurable shell commands that run on agent events
- Env-var-only context passing (security)
- **Should be added as a new stage or folded into Stage 1**

### 3.2 Platform Sandboxing (bubblewrap + seatbelt)
- Every command the agent runs should be sandboxed
- Linux: bubblewrap with read-only root + explicit writable dirs
- macOS: sandbox-exec with seatbelt profile
- **Should be folded into Stage 2 (PTY Backend) — it's a critical safety layer**

### 3.3 Session Teleport (Export/Import)
- Export active session as portable format
- Import with strict validation
- **Should be added to Stage 3 (SQLite Session Store) as an export/import feature**

### 3.4 Rate Limiter (Cross-Cutting)
- Exponential backoff with jitter for API calls
- Shared across primary agent + all subagents
- **Should be added as infrastructure, not a stage — fold into `model/client.py`**

### 3.5 Remote Subagent Execution
- Subagents can run on remote hosts
- Sync + async modes
- Bearer token auth
- **Should be noted as a Stage 5 extension for multi-host scenarios**

---

## 4. SourcePrep Question

The user asked: should both repos be added to SourcePrep so it can trace relationships between them?

**Recommendation:** Yes, but with a caveat.

**Why yes:**
- SourcePrep's trace expansion can find cross-repo dependencies (e.g. Halbert imports Haloysius, Haloysius defines protocols that Halbert implements)
- The structural overview would show the seam points between the two repos
- `prep_impact` would catch breaking changes — "if you change this Haloysius protocol, here's what breaks in Halbert"
- `prep_search` could find "where is the RetrievalBackend protocol implemented" across both repos

**The caveat:**
- SourcePrep traces file-level dependencies, not conceptual patterns
- The patterns we found above (cost-cascade, hook engine, sandboxing) are conceptual — SourcePrep won't find them
- SourcePrep is best used for the IMPLEMENTATION phase (tracing dependencies before changes), not the DISCOVERY phase (finding patterns to steal)
- For this discovery work, manual reading + grep was the right approach

**How to set it up:**
- Create a SourcePrep project at `/Volumes/4TB-BAD/` that includes both `Halbert/` and `Haloysius/` as source roots
- OR create two separate projects and use `prep_search` with cross-project scope
- The first approach is simpler and lets SourcePrep find cross-repo imports

---

## 5. Updated Stage Recommendations

Based on these findings, here are the changes to the implementation strategy:

### Stage 1 (Somatic Blocks) — Add:
- **Cost-cascade router** with outcome store (from finding 2.1) — the Deliberation block routes to the cheapest model
- **Conversation status state machine** (from finding 2.21) — 7 states including TransientError and Blocked
- **File checkpointing** (from finding 2.4) — Action blocks checkpoint affected files before execution
- **Hook engine** (from finding 2.5) — PreToolUse/PostToolUse hooks on Somatic Block transitions

### Stage 2 (PTY Backend) — Add:
- **Platform sandboxing** (from finding 2.6) — bubblewrap on Linux, seatbelt on macOS
- **Injection pattern detection** (from finding 2.7) — 16 dangerous patterns + elevation detection
- **mio event loop pattern** (from finding 2.19) — async I/O, not blocking reads
- **Docker sandbox mode** (from finding 2.19) — for isolated subagent PTYs

### Stage 3 (SQLite Session Store) — Add:
- **Session teleport** (from finding 2.3) — export/import with validation
- **Conversation restoration plan** (from finding 2.16) — reconstruct block layout on resume

### Stage 5 (Subagents) — Add:
- **Stream-based spawn API** (from finding 2.13) — lifecycle events, not just function calls
- **Agent teams + message queue** (from finding 2.8) — inter-subagent communication
- **Optimistic task creation** (from finding 2.22) — show in UI before PTY starts
- **Task store + transactions** (from finding 2.20) — atomic subagent state updates
- **Orchestration config state machine** (from finding 2.15) — per-subagent config with cascading fields
- **Remote trigger** (from finding 2.10) — subagents on remote hosts

### Stage 7 (Living Reflexes) — Add:
- **Workflow data model** (from finding 2.18) — reflexes are workflows with trigger signatures
- **Scheduled agent objects** (from finding 2.14) — first-class scheduled tasks, not just cron entries
- **Scheduler with runDue()** (from finding 2.9) — cognitive tick calls runDue() each cycle

### Stage 9 (Context Watermark) — Add:
- **Micro-compaction** (from finding 2.2) — truncate old tool results before full summarization
- **Per-block-type token estimation** (from finding 2.2) — different overhead for different block types

### Cross-Cutting (New):
- **Rate limiter** (from finding 2.11) — shared across all model calls
- **Tool search** (from finding 2.24) — dynamic tool discovery
- **Multi-provider dispatch** (from finding 2.25) — per-provider call + convert functions
- **Codebase auto-indexing** (from finding 2.17) — SourcePrep indexing on project open

---

## 6. Revised Effort Estimate

| Stage | Original Lines | Added Patterns | Revised Lines |
|---|---|---|---|
| 1. Somatic Blocks | ~380 | +120 (cascade, status, checkpoints, hooks) | ~500 |
| 2. PTY Backend | ~410 | +150 (sandbox, injection check, docker mode) | ~560 |
| 3. SQLite Session Store | ~160 | +60 (teleport, restoration plan) | ~220 |
| 4. Session Router | ~140 | — | ~140 |
| 5. Subagents | ~320 | +200 (teams, optimistic, task store, orchestration) | ~520 |
| 6. Frontend Docking | ~810 | +80 (restoration rendering) | ~890 |
| 7. Living Reflexes | ~250 | +100 (workflow model, scheduler) | ~350 |
| 8. Lasso-to-Mind | ~130 | — | ~130 |
| 9. Context Watermark | ~70 | +40 (micro-compaction) | ~110 |
| Cross-cutting | — | +200 (rate limiter, tool search, providers) | ~200 |
| **Total** | **~2,670** | **~950** | **~3,620** |

The cross-codebase audit adds ~950 lines (~36% increase) but significantly de-risks the implementation by providing proven patterns for every stage.
