# Implementation Strategy: Sovereign Host Vision

**Version:** 1.0.0 (initial pass)
**Date:** August 24, 2026
**Status:** Initial strategy — pending design tightening pass
**Reads with:**
- [README.md](README.md) — vision overview + codebase reality check
- [FEASIBILITY-AND-ENGINEERING-REALITIES.md](FEASIBILITY-AND-ENGINEERING-REALITIES.md) — engineering constraints
- [SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md](SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md) — block lifecycle spec
- [SUBAGENTS-AND-TASK-DAEMONS.md](SUBAGENTS-AND-TASK-DAEMONS.md) — subagent spec
- [STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md](STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md) — terminal UI spec
- [CONTINUOUS-ORCHESTRATOR-AND-SESSION-ENGINE.md](CONTINUOUS-ORCHESTRATOR-AND-SESSION-ENGINE.md) — session engine spec
- [ORGANIC-INTERACTIONS-AND-WORKFLOWS.md](ORGANIC-INTERACTIONS-AND-WORKFLOWS.md) — interaction spec
- `/.handoff/ROADMAP-2026-08-23.md` — existing Phases 0-8 roadmap (infrastructure spine + being layers)

---

## 1. Where We Are: Two Roadmaps, One Codebase

There are two planning documents that need reconciling:

1. **The existing ROADMAP** (`/.handoff/ROADMAP-2026-08-23.md`): Phases 0-8 covering the infrastructure spine (SourcePrep ingestion, intake pipeline, RAG consolidation, chat.py retirement, boot-test gate) and the being layers (why data model, config brain, proactive channel, reactive slice). Per session history, **Phases 0-5 are complete and committed**. Phase 4 (chat.py retirement) is done. Phase 4.5 (boot-test gate) passed on macOS, pending Linux verification. Phases 6-8 are the remaining being-layer work.

2. **The Sovereign Host Vision** (this directory): Halbert 2.0 — Somatic Blocks, streaming terminals, subagents, continuous orchestrator, living reflexes. This is the *next evolution* beyond the being layers. It assumes the infrastructure spine and being layers exist.

**The strategy below covers the sovereign-host-vision work.** It assumes Phases 0-5 of the existing roadmap are complete (they are) and identifies where Phases 6-8 of the existing roadmap overlap with or are subsumed by the vision stages.

### What's Already Built (from the existing roadmap)

| Existing Roadmap Phase | Status | Relevant to Vision |
|---|---|---|
| Phase 0: SourcePrep doc ingestion | **Complete** | SourcePrep retrieval backend operational |
| Phase 1: Intake pipeline | **Complete** | `intake/signals.py`, `intake/budget.py` — Tier 0 spinal reflexes |
| Phase 2: RAG consolidation | **Complete** | SourcePrep is sole retrieval backend |
| Phase 3: Intake wiring | **Complete** | Agent path uses intake pipeline |
| Phase 4: chat.py retirement | **Complete** (commit `5141cfe`) | One conversation path (agent.py) |
| Phase 4.5: Boot-test gate | **macOS passed**, Linux pending | Agent path boots end-to-end |
| Phase 5: Why data model + config brain | **Complete** | `findings/`, `approval/`, `autonomy/` — the pieces that Somatic Blocks will unify |
| Phase 6: Being config + voice | Not started | Voice setting needed for Somatic Block expression |
| Phase 7: Proactive channel | Not started | SSE push transport needed for subagent completion receipts |
| Phase 8: Reactive slice + modules | Not started | Module registry needed for Lasso-to-Mind and subagent output |

---

## 2. The Strategy: Six Stages

The vision breaks into six stages with clear dependencies. Each stage is independently shippable — you get something working at the end of each one.

### Dependency Graph

```
                    ┌─────────────────────────────────────────────────────┐
                    │                                                     │
                    ▼                                                     │
    Stage 1: Somatic Block Unification                                    │
    (unify findings/approval/autonomy under one lifecycle)                │
                    │                                                     │
                    ├──→ Stage 3: SQLite Session Store                     │
                    │    (migrate JSON → SQLite + FTS5)                    │
                    │              │                                      │
                    │              ▼                                      │
                    │    Stage 4: Session Affinity Router                  │
                    │    (FTS5 keyword routing, no embeddings)             │
                    │                                                     │
                    ▼                                                     ▼
    Stage 2: Real PTY Backend                              Stage 5: Subagent Forking
    (replace subprocess.run with async PTY)               (one StorageAuditor, then generalize)
                    │                                         │
                    ├──→ Stage 5: Subagent Forking ◄──────────┘
                    │
                    ▼
    Stage 6: Frontend Terminal Docking
    (IntersectionObserver + accordion dock + tether chips)

    Parallel (no deps):
    Stage 7: Living Reflexes (after Stage 1)
    Stage 8: Lasso-to-Mind (after Stage 2, frontend)
    Stage 9: Context Watermark (after Stage 3)
```

---

## 3. Stage Details

### Stage 1: Somatic Block Unification

**Goal:** Wrap the existing `findings/`, `approval/`, `autonomy/` modules under a single `SomaticBlock` lifecycle dataclass + state machine. This gives the vision a concrete spine.

**Why first:** Everything else builds on this. Subagents emit Somatic Blocks. The frontend renders Somatic Blocks. Living Reflexes are synthesized from the Reflection block. The session store indexes Somatic Blocks.

**What exists:**
- `findings/store.py` — `Finding` dataclass + `FindingStore` (SQLite, 163+ lines)
- `findings/proposals.py` — `Proposal` dataclass + `ProposalStore` (SQLite, 302 lines, full status lifecycle: pending → approved → applied → rolled_back)
- `findings/blast_radius.py` — blast-radius scoring (88 lines)
- `findings/precedence.py` — sshd/systemd precedence resolution (353 lines)
- `approval/engine.py` — `ApprovalRequest` + `ApprovalEngine` (417 lines, PENDING/APPROVED/REJECTED/EXPIRED)
- `approval/simulator.py` — `DryRunSimulator` + `SimulationResult` (380 lines, before/after/diffs)
- `autonomy/recovery.py` — `RecoveryExecutor` + `RecoveryAction.ROLLBACK` (307 lines)
- `autonomy/guardrails.py` — `GuardrailEnforcer` (292 lines, confidence thresholds)
- `proactive/detector_runner.py` — detector execution
- `discovery/engine.py` — `DiscoveryEngine` with 34 scanners
- `agents/state_machine.py` — REFLECTING state runs Haloysius cognitive tick (line 733)

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `SomaticBlock` dataclass | `halbert_core/somatic/block.py` (new) | Unified dataclass with 5 block types (Sensory, Deliberation, Proposal, Action, Reflection), status lifecycle, links to finding/proposal/approval IDs | ~80 |
| `SomaticLifecycle` state machine | `halbert_core/somatic/lifecycle.py` (new) | State machine: Sensory → Deliberation → Proposal → Action → Reflection. Each transition calls the existing module (detector → cognitive tick → proposal gen → approval + simulator → recovery + guardrails → reflection) | ~120 |
| `SomaticStore` | `halbert_core/somatic/store.py` (new) | SQLite store for Somatic Blocks, linked to sessions and findings | ~60 |
| Wire into state machine | `agents/state_machine.py` | REFLECTING state emits a Reflection block; EXECUTING state emits Action blocks; proposals generate Proposal blocks | ~40 |
| Wire into SSE stream | `streaming/emitter.py` | New `StreamEvent.somatic_block()` class method for frontend rendering | ~20 |

**Total: ~320 lines new + ~60 lines modified**

**Design decisions to make (for the tightening pass):**
1. Does `SomaticBlock` wrap the existing `Finding`/`Proposal`/`ApprovalRequest` by reference (block carries their IDs), or does it absorb them (block carries their data inline)?
2. Does the lifecycle state machine live in `somatic/lifecycle.py` or extend `AgentStateMachine` with new sub-states?
3. How does the Haloysius cognitive tick (REFLECTING) feed into the Reflection block — does it generate the block, or does the block wrap the tick's output?

**Can start immediately:** Yes. No dependencies. All underlying modules exist.

---

### Stage 2: Real PTY Backend

**Goal:** Replace `subprocess.run()` in `dashboard/routes/terminal.py` with a real async PTY + ring buffer + TTL reaper. This is the single highest-leverage infrastructure gap.

**Why second:** Subagents (Stage 5) and the frontend terminal docking (Stage 6) both hard-depend on this. The frontend xterm.js is already wired and waiting.

**What exists:**
- `dashboard/routes/terminal.py` (299 lines) — `subprocess.run()` stub with safety tiers (SAFE/CAUTION/DANGEROUS/BLOCKED), command validation, history
- `dashboard/frontend/src/pages/Terminal.tsx` (482 lines) — xterm.js + FitAddon + WebLinksAddon, WebSocket connection ready
- `streaming/sse.py` — SSE streaming infrastructure
- `streaming/emitter.py` — `EventEmitter` with session-scoped queues

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `PTYSession` class | `halbert_core/streaming/pty.py` (new) | Async PTY wrapper using `aiofiles` + `os.openpty()` or `aiopty`. Manages master/slave fds, reads stdout in chunks, writes stdin. Handles `SIGWINCH` for resize. | ~120 |
| `TerminalSessionManager` | `halbert_core/streaming/session_manager.py` (new) | Singleton managing all active PTY sessions. 1MB ring buffer per session (circular `bytearray`). Overflow to `/tmp/halbert/terminals/{id}.log`. 60s idle reaper. Max 2 concurrent sessions (concurrency ceiling from feasibility doc). | ~80 |
| Replace terminal route | `dashboard/routes/terminal.py` | Replace `subprocess.run()` with `TerminalSessionManager.spawn()`. Add `/sessions` (list active), `/{id}/input` (write stdin), `/{id}/resize` (SIGWINCH), `/{id}/stream` (SSE output stream). Keep existing safety tier checks. | ~90 (rewrite) |
| WebSocket bridge | `dashboard/routes/websocket.py` | Upgrade the 37-line stub to bridge xterm.js ↔ PTY session (bidirectional: stdin/stdout/resize). | ~60 |

**Total: ~260 lines new + ~90 lines rewritten + ~60 lines upgraded**

**Library choice (for the tightening pass):**
1. `aiopty` — purpose-built async PTY, but may be unmaintained
2. `pexpect` + `asyncio.to_thread` — battle-tested, but thread-bridge adds latency
3. Raw `os.openpty()` + `aiofiles` — no dependency, more code
4. Recommendation: start with raw `os.openpty()` + `aiofiles` to avoid dependency risk; upgrade to `aiopty` if it proves stable

**Can start immediately:** Yes. No dependencies on other stages.

---

### Stage 3: SQLite Session Store + FTS5

**Goal:** Migrate `ConversationStore` from JSON files to SQLite with FTS5 on session summaries. Foundation for the zero-manual-session paradigm.

**Why parallel with Stage 2:** No dependency on PTY or Somatic Blocks. Can be built independently.

**What exists:**
- `agents/conversation.py` (538 lines) — `Conversation`, `ConversationStore` (JSON files), `Session` dataclass. `search()` is a linear scan of JSON files.
- `findings/store.py` and `findings/proposals.py` — already use SQLite, can reference their patterns

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| SQLite schema | `agents/conversation.py` | `host_sessions` table (id, created_at, updated_at, status, title, topic_category, entities_json, compacted_summary, parent_session_id). `session_messages` table (id, session_id, role, content, metadata_json, created_at). FTS5 virtual table on `compacted_summary` + `title`. | ~40 |
| `SessionStore` class | `agents/conversation.py` | Replace `ConversationStore`. Methods: `create()`, `get()`, `add_message()`, `list_sessions()`, `search_fts(query)` → ranked results, `update_summary()`, `archive()`. Backward-compatible `get_or_create()` interface. | ~80 |
| Migration script | `tools/migrate_conversations.py` (new) | Read all JSON files, write to SQLite. One-time run. | ~40 |

**Total: ~120 lines modified + ~40 lines new**

**Design decisions (for the tightening pass):**
1. Do we keep the `Conversation` dataclass as the in-memory representation, or replace it with a `Session` that maps directly to the SQLite row?
2. Should `session_somatic_blocks` table (from the orchestrator doc §7) be created now or deferred to Stage 1? Recommendation: create it now as an empty table; Stage 1 populates it.
3. FTS5 tokenizer: use the default `unicode61` or configure `tokenize='porter unicode61'` for better English stemming?

**Can start immediately:** Yes. No dependencies.

---

### Stage 4: Session Affinity Router

**Goal:** Implement the deterministic 3-tier routing pipeline from the feasibility doc. FTS5-only, no embeddings on every prompt.

**Depends on:** Stage 3 (SQLite + FTS5 must exist)

**What exists:**
- `intake/signals.py` — entity extraction (domains, file paths, error indicators) in <1ms
- `agents/state_machine.py` — `StateContext` carries `session_id`

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `SessionRouter` | `agents/session_router.py` (new) | `route(user_query, current_session_id)` → `session_id`. Step 1: check for explicit past reference (regex for "last week", "that issue", "yesterday"). Step 2: if found, FTS5 search on session summaries. Step 3: if score > 0.80, return matched session. Step 4: else return current session. | ~80 |
| Entity extraction | `agents/session_router.py` | Extend `intake/signals.py` output with temporal anchors ("last Tuesday", "yesterday", "last week") and topic keywords. Reuse existing domain detection. | ~40 |
| Wire into agent route | `dashboard/routes/agent.py` | Before `agent.process()`, call `router.route()`. If different session, load its compacted summary into context. | ~20 |

**Total: ~120 lines new + ~20 lines modified**

**Design decisions (for the tightening pass):**
1. What's the exact regex for "explicit past reference"? Need to enumerate patterns: "that X", "the X from Y", "last Z", "continue X", "resume X".
2. Should the router emit an SSE event when it re-anchors to a past session, so the frontend can show "Resuming: WireGuard MTU tuning"?
3. Should the ambiguous-match tier (0.45 ≤ score < 0.75) show a UI chip, or just silently stay in the current session? Recommendation: UI chip, non-intrusive.

**Can start after Stage 3.**

---

### Stage 5: Subagent Forking

**Goal:** Build one real subagent (`StorageAuditorAgent`) end-to-end. Runs `smartctl`/`zpool scrub` in isolated PTY, streams output, emits a Somatic Block on completion.

**Depends on:** Stage 1 (Somatic Blocks) + Stage 2 (PTY backend)

**What exists:**
- `agents/react_agent.py` (442 lines) — ReAct agent with `_call_llm_with_tools()`, but no `spawn_subagent()`
- `discovery/scanners/storage.py` — `StorageScanner` already runs `smartctl`, `lsblk`
- `findings/proposals.py` — `Proposal` dataclass for subagent output
- `streaming/emitter.py` — `EventEmitter` with session-scoped queues

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `SubagentHandle` dataclass | `agents/subagent.py` (new) | id, agent_type, task_goal, scoped_sources, model_tier, pty_session_id, status, started_at, completed_at, result_block_id | ~30 |
| `SubagentManager` | `agents/subagent.py` | `spawn(agent_type, task_goal, scoped_sources)` → `SubagentHandle`. Enforces concurrency ceiling (`asyncio.Semaphore(2)`). FIFO queue in SQLite for overflow. `cancel(handle_id)`. `list_active()`. | ~80 |
| `StorageAuditorAgent` | `agents/subagents/storage_auditor.py` (new) | Runs `smartctl -t long` / `zpool scrub` via `TerminalSessionManager`. Streams output. On completion, generates a `SomaticBlock` (Finding + Proposal if issues found). | ~70 |
| `spawn_subagent()` in ReActAgent | `agents/react_agent.py` | Add method that creates scoped `ContextAssembler` + isolated PTY + calls `SubagentManager.spawn()`. | ~40 |
| Wire into state machine | `agents/state_machine.py` | PLANNING state can emit `spawn_subagent` tool call. EXECUTING state handles the spawn. Subagent completion emits a Somatic Block via SSE. | ~30 |
| Concurrency limiter | `agents/subagent.py` | `asyncio.Semaphore(2)` + SQLite-backed FIFO queue for overflow tasks. | ~30 |

**Total: ~250 lines new + ~70 lines modified**

**Design decisions (for the tightening pass):**
1. Does the subagent run its own `AgentStateMachine` instance (full ReAct loop), or is it a simpler deterministic script (run command → parse output → emit block)? Recommendation: start with deterministic script for `StorageAuditorAgent`; full ReAct loop for `IncidentInvestigatorAgent` later.
2. How does the subagent's output flow back to the primary conversation? Via SSE event → frontend renders Somatic Block → user can approve/reject. Or does the primary agent's context get updated automatically?
3. Should the subagent have its own LLM call, or is it pure command execution + pattern matching? For `StorageAuditorAgent`: pure command + pattern matching (Tier 0/1). For `IncidentInvestigatorAgent`: LLM-assisted fault tree analysis (Tier 2).

**Can start after Stage 1 + Stage 2.**

---

### Stage 6: Frontend Terminal Docking

**Goal:** Build the flowing-terminal-with-accordion-dock UI. IntersectionObserver-based docking, tether chips, terminal session manager on the frontend.

**Depends on:** Stage 2 (PTY backend must be real for streaming)

**What exists:**
- `dashboard/frontend/src/pages/Terminal.tsx` (482 lines) — xterm.js wired, but standalone page not integrated into conversation
- `dashboard/frontend/src/components/SidePanel.tsx` (2,334 lines) — conversation panel with `PanelMode = 'agent' | 'chat' | 'terminal'` toggle
- `dashboard/frontend/src/components/agent/` — 13 agent components (AgentChat, AgentPanel, ToolExecutionCard, DiffBlock, etc.)
- `dashboard/frontend/src/hooks/useAgentStream.ts` (643 lines) — SSE stream consumer with typed events

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `TerminalSessionManager` (frontend) | `hooks/useTerminalSessions.ts` (new) | Singleton store for active terminal sessions. WebSocket connection per session. Tracks session state (running/done/idle), output buffer, scrollback. | ~120 |
| `TerminalTile` component | `components/agent/TerminalTile.tsx` (new) | Inline terminal tile rendered in conversation stream. xterm.js instance. Status badge, timer, PID, quick actions (Pin, Terminate, Copy). | ~150 |
| `TerminalAccordionDock` | `components/agent/TerminalAccordionDock.tsx` (new) | Right-column accordion. Lists all terminal sessions (active and completed). Expand/collapse. Jump-to-origin. Full PTY interactivity on expand. | ~200 |
| `IntersectionObserver` hook | `hooks/useIntersectionDock.ts` (new) | Watches terminal tile visibility. At <25% visibility, triggers docking. At >25% (scroll back), triggers restoration. | ~60 |
| `TetherChip` component | `components/agent/TetherChip.tsx` (new) | Inline chip in conversation stream when terminal is docked: `[Terminal #1: zfs scrub → DOCKED IN STAGE]`. Hover highlights docked card. Click scrolls back. | ~40 |
| Integrate into SidePanel | `components/SidePanel.tsx` | Add right-column dock to the agent mode layout. Render `TerminalTile` in conversation stream when agent executes a command. | ~80 |
| SSE event handling | `hooks/useAgentStream.ts` | Handle `terminal_spawn`, `terminal_output`, `terminal_complete` events. | ~40 |

**Total: ~690 lines new frontend + ~120 lines modified**

**Design decisions (for the tightening pass):**
1. Does the right-column dock replace the existing ContextBar, or sit alongside it? The current `SidePanel.tsx` agent mode has a ContextBar — the dock would need to coexist or absorb it.
2. How many xterm.js instances can we have simultaneously? Each is a WebGL canvas — memory concern. Recommendation: max 3 visible (1 inline + 2 in dock), rest are headless (output buffered, xterm instance created on expand).
3. Should the dock be a Tauri webview panel or a React component in the main layout? Recommendation: React component — simpler, and the Tauri shell already hosts the main layout.

**Can start after Stage 2.**

---

### Stage 7: Living Reflexes (parallel with Stage 5+)

**Goal:** Self-synthesizing 1-click recovery runbooks. The Reflection block writes reflexes; Tier 0 trigger matching recognizes them.

**Depends on:** Stage 1 (Somatic Blocks — specifically the Reflection block)

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| `Reflex` dataclass | `reflexes/reflex.py` (new) | id, name, trigger_signature (telemetry thresholds + regex), actions (commands), rollback, rationale, provenance (incident_id, concept_id), created_at | ~40 |
| `ReflexStore` | `reflexes/store.py` (new) | YAML file store at `~/.config/halbert/reflexes/{id}.yml`. CRUD operations. | ~50 |
| `ReflexMatcher` | `reflexes/matcher.py` (new) | Tier 0 trigger matching: compare incoming telemetry/events against reflex trigger_signatures. Regex + threshold comparison. <1ms. | ~60 |
| Reflex synthesis | `somatic/lifecycle.py` | Reflection block: if the resolved incident matches a recurring pattern (seen ≥2 times), prompt user to save as reflex. Generate YAML from the action block's commands + the deliberation block's rationale. | ~40 |
| Wire into proactive channel | `proactive/detector_runner.py` | Before running detectors, check `ReflexMatcher`. If match found, emit proactive suggestion: "I detected X. [Run Reflex Y (1-Click)]" | ~30 |

**Total: ~180 lines new + ~70 lines modified**

**Can start after Stage 1.**

---

### Stage 8: Lasso-to-Mind (parallel with Stage 6)

**Goal:** Highlight any error in a terminal tile → 1-click grounded fix proposal.

**Depends on:** Stage 2 (PTY backend — need real terminal tiles) + Stage 6 (frontend terminal tiles exist)

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| Selection extraction | `components/agent/TerminalTile.tsx` | On text selection in xterm.js, show floating pill `[Fix with Halbert]`. Extract selected text + PID + cwd + exit code + recent command history. | ~50 frontend |
| Fix proposal endpoint | `dashboard/routes/agent.py` | New `POST /lasso-fix` endpoint. Takes selected text + terminal context. Runs `intake/signals.py` for error classification. Generates `Proposal` Somatic Block via `findings/proposals.py` + `approval/simulator.py`. Returns proposal for inline rendering. | ~50 backend |
| Proposal rendering | `components/agent/DiffBlock.tsx` | Existing DiffBlock component renders the proposal. Add `[Approve & Run]` button that executes the fix via PTY. | ~30 frontend |

**Total: ~80 lines frontend + ~50 lines backend**

**Can start after Stage 6.**

---

### Stage 9: Context Watermark (parallel with Stage 3)

**Goal:** 75% token watermark trigger + 2hr temporal inactivity gate + topic boundary gate in the context assembler.

**Depends on:** Stage 3 (SQLite session store — summaries persist there)

**What to build:**

| Component | Target file | What | Lines |
|---|---|---|---|
| Token watermark | `context/assembler.py` | After `_combine_sources()`, check if combined tokens > 75% of `max_tokens`. If so, call `_compress_with_cascade()` on older turns. If still over, trigger summarization. | ~30 |
| Temporal gate | `context/assembler.py` | Check timestamp of last message in session. If >2 hours, start fresh context slice. Archive old turns to SQLite summary. | ~20 |
| Topic boundary gate | `context/assembler.py` | Compare `intake/signals.py` detected_domains of current message vs. previous message. If domain shift (e.g. storage → network), archive current context and start fresh. | ~20 |

**Total: ~70 lines modified**

**Can start after Stage 3.**

---

## 4. What Can Start Immediately (No Dependencies)

| Stage | Effort | Blocks |
|---|---|---|
| **Stage 1: Somatic Block Unification** | ~320 lines new + ~60 modified | Stages 5, 7 |
| **Stage 2: Real PTY Backend** | ~260 lines new + ~150 modified | Stages 5, 6, 8 |
| **Stage 3: SQLite Session Store** | ~120 lines modified + ~40 new | Stages 4, 9 |

**All three can start in parallel today.** They have zero dependencies on each other.

---

## 5. What's Deferred (and Why)

| Feature | Why Deferred | Revisit After |
|---|---|---|
| **Parametric Headroom Sliders** | Requires live RAM/headroom simulation engine that doesn't exist. `approval/simulator.py` computes static before/after, not live parameter sweeps. | Stage 1 + a new simulation engine |
| **"What Changed?" Biographical Diff** | Requires config snapshot infrastructure (periodic `/etc` snapshots, package version tracking, port state baselines). `config/snapshot.py` may exist but the diff comparison UI doesn't. | A new snapshot subsystem |
| **GSAP FLIP Docking Animation** | Ship the dock first (Stage 6), animate later. The 300ms FLIP transition is polish, not function. | Stage 6 complete |
| **Dream Cycle 03:00 Scheduler** | Requires opt-in scheduler that survives reboots. `proactive/morning_report.py` exists but isn't scheduled. Must be opt-in, not default. | Stage 7 + scheduler work |
| **ONNX Embedding Session Routing** | FTS5 alone handles 90% of routing (Stage 4). Embeddings are for the ambiguous-match tier only. | Stage 4 stable + embedding infra |
| **4 More Subagents** | Build `StorageAuditorAgent` first (Stage 5). If the pattern works, ConfigRefactor / IncidentInvestigator / SecurityHardening / EphemeralTask are mechanical variations. | Stage 5 validated |
| **Host-Aware Predictive Ghosting** | Requires Tier 1 local model running on every keystroke. Latency-sensitive. | Local model infra + Stage 6 |

---

## 6. Relationship to Existing ROADMAP Phases 6-8

The existing ROADMAP has Phases 6-8 (being config + voice, proactive channel, reactive slice + modules) that are not yet started. These overlap with the sovereign-host-vision stages:

| Existing Roadmap Phase | Vision Stage Overlap | Resolution |
|---|---|---|
| **Phase 6: Being config + voice** | Needed by Stage 1 (Somatic Block expression uses voice) | Build Phase 6 first or in parallel with Stage 1 — it's small (~350 lines) |
| **Phase 7: Proactive channel** | Stage 7 (Living Reflexes) uses the proactive channel for reflex suggestions. Stage 5 (Subagents) uses SSE push for completion receipts. | Build Phase 7's SSE transport as part of Stage 1 (Somatic Blocks need to be pushed to the frontend). Phase 7's gate + morning report can follow. |
| **Phase 8: Module registry** | Stage 8 (Lasso-to-Mind) needs module invocation for the fix proposal. Stage 5 (Subagents) emit modules. | Build Phase 8's module registry as part of Stage 5 — subagent output is the first module invocation use case. |

**Recommendation:** Fold the existing ROADMAP Phases 6-8 into the sovereign-host-vision stages rather than treating them as separate tracks. Specifically:
- Phase 6 (being config + voice) → build in parallel with Stage 1
- Phase 7 (SSE transport) → fold into Stage 1 (Somatic Blocks need push transport)
- Phase 7 (gate + morning report) → fold into Stage 7 (Living Reflexes need the gate)
- Phase 8 (module registry) → fold into Stage 5 (subagent output is the first module)

---

## 7. Total Effort Estimate

| Stage | New Lines | Modified Lines | Effort |
|---|---|---|---|
| 1. Somatic Block Unification | ~320 | ~60 | Medium |
| 2. Real PTY Backend | ~260 | ~150 | Medium |
| 3. SQLite Session Store | ~40 | ~120 | Small |
| 4. Session Affinity Router | ~120 | ~20 | Small |
| 5. Subagent Forking (one agent) | ~250 | ~70 | Medium |
| 6. Frontend Terminal Docking | ~690 | ~120 | Medium-large (frontend) |
| 7. Living Reflexes | ~180 | ~70 | Small-medium |
| 8. Lasso-to-Mind | ~80 | ~50 | Small |
| 9. Context Watermark | ~0 | ~70 | Small |
| **Total** | **~1,940** | **~730** | **~2,670 lines** |

For comparison, the existing ROADMAP Phases 0-5 were ~3,000+ lines across 74 tasks. This vision is a similar scope — achievable in the same order of effort.

---

## 8. Open Questions for the Design Tightening Pass

These are the questions that need resolution before implementation can begin. They're grouped by stage:

### Architecture-Level
1. **Does `SomaticBlock` reference or absorb?** Does the block carry Finding/Proposal/ApprovalRequest IDs (reference), or does it inline their data (absorb)? Reference is cleaner; absorb is simpler for the frontend.
2. **Does the lifecycle state machine extend `AgentStateMachine`?** Or is it a separate `SomaticLifecycle` that runs alongside? Extending risks bloating the state machine; separating risks two state machines to coordinate.
3. **How do the existing ROADMAP Phases 6-8 fold in?** The recommendation in §6 needs validation — are there dependencies I'm missing?

### Stage 1 (Somatic Blocks)
4. How does the Haloysius cognitive tick feed the Reflection block?
5. Should Somatic Blocks be emitted as SSE events with a new event type, or as existing event types with somatic metadata?

### Stage 2 (PTY)
6. Which PTY library? Raw `os.openpty()` + `aiofiles` (no dep) vs `aiopty` (purpose-built) vs `pexpect` (battle-tested but threaded)?
7. How does sudo work in a web PTY? The current code strips `sudo` and runs without it. A real PTY can handle password prompts, but the web context may not have a polkit agent.

### Stage 3 (SQLite)
8. Do we keep the `Conversation` dataclass or replace it with `Session`?
9. Should `session_somatic_blocks` table be created now or in Stage 1?

### Stage 5 (Subagents)
10. Does `StorageAuditorAgent` run a full ReAct loop or a deterministic script?
11. How does subagent output flow back — SSE event → frontend, or auto-injected into primary agent context?

### Stage 6 (Frontend)
12. Does the accordion dock replace or coexist with the existing ContextBar?
13. How many xterm.js instances can we render simultaneously before memory becomes a problem?

---

## 9. Proposed Next Step

Take this strategy document and the codebase audit findings back to the vision docs for a **design tightening pass**. Specifically:

1. **Resolve the 13 open questions** above — some need code investigation, some need user input, some need design decisions.
2. **Update the vision specs** with the resolved answers — the specs currently describe aspirational behavior; they need to describe the actual implementation approach.
3. **Write per-stage design docs** for Stages 1-3 (the three that can start immediately), with enough detail that an executor can build without further design input.
4. **Validate the dependency graph** — confirm that no stage has a hidden dependency I missed.

The strategy is intentionally conservative: it builds on what exists, defers what doesn't, and ships something working at each stage. The risk is not in the code volume (~2,670 lines is tractable) but in the design decisions — getting the Somatic Block lifecycle right determines whether the rest of the vision composes cleanly or fights itself.
