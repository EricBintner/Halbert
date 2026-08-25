# v2.0 Strategy Scrutiny — Factual Audit and Corrected Task Assignments

**Date:** August 25, 2026
**Purpose:** Verify the v2.0 implementation strategy against the actual codebase. Find factual errors, hidden dependencies, and missing preliminary work. Assign model tier and effort level to each task.

---

## Executive Summary

The v2.0 strategy is **structurally correct** — the phase ordering, risk ranking, and "wrap don't rewrite" principle are all sound. But it contains **8 factual errors** about what exists in the codebase, **understates what's already built**, and **misses 6 hidden dependencies**. The corrected estimate is **~3,800 lines (down from ~4,500)** because more infrastructure exists than the plan assumed.

The test suite is healthy: **395 passed, 18 skipped, 0 failed** across 413 collected tests.

---

## 1. Factual Errors in the v2.0 Plan

### Error 1: Phases 6-8 are marked "not started" — they're COMPLETE

**The plan says (v1.0 §1, v2.0 §6):** "Phase 6: Being config + voice — Not started. Phase 7: Proactive channel — Not started. Phase 8: Module registry — Not started."

**The actual state:** Git log shows all three phases committed:
- `da5d801 feat(config): being config schema + API endpoints (T6a.1, T6a.2)`
- `5159014 feat(prompts): wire voice setting into prompt layer (T6b.1)`
- `94b1534 feat(ui): add Being tab to Settings page (T6c.1)`
- `628a989 feat(proactive): event bus + SSE push transport (T7a.1, T7b.1)`
- `c9f8b6e feat(proactive): frontend SSE hook + proactive gate (T7b.2, T7c.1)`
- `87156bf feat(proactive): morning report generator + scheduler task (T7d.1, T7d.2)`
- `bd88f19 feat(proactive): wire detector triggers to event bus (T7e.1)`
- `43c233f feat(modules): module registry + API endpoints (T8b.1)`
- `269096d feat(agents): module invocation protocol (T8b.2)`
- `24c557c feat(ui): module renderer + 4 context modules (T8b.3, T8c.1-T8c.4)`
- `c5f34c6 feat(agents): wire reactive slice end-to-end (T8d.1)`

**Impact on plan:** The plan's §6 ("fold Phases 6-8 into the vision stages") is moot — they're already folded. The SSE push transport, proactive gate, morning report scheduler, module registry, and module invocation protocol all exist. This means:
- Phase C1 (Somatic Blocks) can use the existing `ProactiveEventBus` instead of building a new event channel
- Phase D1 (Subagents) can use the existing module invocation protocol for subagent output rendering
- Phase F3 (Living Reflexes) can use the existing morning report scheduler instead of building a new one

### Error 2: "Approval engine has no link to execution"

**The plan says (THIRD-PASS-SCRUTINY.md §3.5):** "ApprovalEngine and ProposalStore exist, but the state machine doesn't wait for user approval. It just produces a pending proposal and moves on."

**The actual state:** `findings/proposal_generator.py` (634 lines) implements the full flow:
- `ProposalGenerator.generate()` creates a Finding, calculates blast radius, creates a Proposal, creates an ApprovalRequest (PENDING)
- `handle_approval_decision(request_id, approved, reason)` is the entry point for approval decisions
- Approved → executes ALL changes via `WriteConfig.execute(backup=True, dry_run=False, confirm=True)`
- Rejected → marks proposal rejected with the real reason
- Execution failure → rollback, proposal marked ROLLED_BACK
- Idempotency guard: terminal-status proposals are not re-executed
- The `dashboard/routes/approvals.py` route calls `handle_approval_decision()` on approve/reject

**Impact on plan:** The approval-to-execution gap is **smaller than stated**. The flow exists and works. The real gap is that the **agent state machine** uses a separate, simpler confirmation flow (`pending_confirmation` dict + `AWAITING_CONFIRMATION` state) that is NOT connected to the proposal_generator. The fix is to wire the two together, not build a new flow.

### Error 3: "The state machine doesn't wait for approval"

**The plan says (THIRD-PASS-SCRUTINY.md §3.5):** "There is no AWAITING_CONFIRMATION → execute flow."

**The actual state:** `agents/state_machine.py` line 927-937:
```python
async def _handle_awaiting_confirmation(self) -> AsyncIterator[StreamEvent]:
    """AWAITING_CONFIRMATION state: Wait for user to confirm/reject.
    This is a blocking state - processing pauses until confirm_action() is called."""
    logger.info(f"AWAITING_CONFIRMATION: {self.ctx.pending_confirmation}")
    return  # Blocks until external input
    yield  # Make it an async generator
```

The state machine DOES block. `confirm_action(action_id)` (line 295-313) resumes execution. The gap is that this is **tool-level confirmation** (from `result.requires_confirmation`), not **proposal-level approval** (from `ApprovalEngine`). The fix is to bridge the two, not build a new blocking mechanism.

### Error 4: "Add a dependency on aiofiles"

**The plan says (v2.0 §4 B1):** "Add a dependency on aiofiles or aiopty."

**The actual state:** `aiofiles` is already installed in the `.venv`. Verified by `python3 -c "import aiofiles"`.

**Impact:** Remove the dependency-addition step from B1. Saves ~1 hour of dependency management.

### Error 5: "No scheduler exists"

**The plan says (v2.0 §2.7, F3):** "No scheduler, no reflex store. The morning report is a one-off, not a cron job."

**The actual state:** `proactive/morning_report.py` (8.5KB) includes a scheduler task. Git commit `87156bf` says "morning report generator + scheduler task (T7d.1, T7d.2)". The scheduler is wired into the proactive channel.

**Impact:** Phase F3 (Living Reflexes) can use the existing scheduler infrastructure. The reflex store and matcher still need to be built, but the scheduling layer exists.

### Error 6: "No proactive channel / SSE push transport"

**The plan says (v1.0 §6):** "Phase 7: Proactive channel — Not started. SSE push transport needed for subagent completion receipts."

**The actual state:**
- `proactive/events.py` (178 lines) — `ProactiveEventBus` with thread-safe pub/sub, ring buffer, async subscribers, cross-loop dispatch
- `proactive/gate.py` (123 lines) — `ProactiveGate` with per-category overrides
- `proactive/detector_runner.py` (184 lines) — runs detectors, publishes events
- `dashboard/frontend/src/hooks/useBeingEvents.ts` — frontend SSE consumer for proactive events
- `dashboard/frontend/src/components/agent/ProactiveEventsBadge.tsx` — UI badge for proactive events

**Impact:** The SSE push transport is built. Subagent completion receipts (Phase D1) should use `ProactiveEventBus.publish()` with `type="subagent_complete"`, not a new event channel.

### Error 7: "No module registry"

**The plan says (v1.0 §6):** "Phase 8: Module registry — Not started. Module registry needed for Lasso-to-Mind and subagent output."

**The actual state:** `modules/registry.py` (128 lines) — `ModuleRegistry` with 4 registered modules (config-diff, vitals, drive-health, evidence). The agent state machine validates LLM-emitted module invocations against this registry (`state_machine.py:_parse_module_invocations()`). The frontend has a module renderer.

**Impact:** The module registry is built. Subagent output (Phase D1) can be a new module type, not a new rendering system. Lasso-to-Mind (v1.0 Stage 8) can use the existing `config-diff` module.

### Error 8: "No config snapshot infrastructure"

**The plan says (v2.0 §5 cut list):** "'What Changed?' Biographical Diff — Requires config snapshot infrastructure."

**The actual state:** `config/snapshot.py` (65 lines) — takes snapshots, writes raw text + canonical JSON to `data/config/snapshots/`, maintains `latest.json` pointer. `config/drift.py` (3KB) exists for drift detection. `config/watcher.py` (10KB) watches for config changes and re-indexes SourcePrep.

**Impact:** The snapshot infrastructure exists. The "What Changed?" diff feature is a UI layer on top of existing snapshots, not a new subsystem. It could be promoted out of the cut list if we want it.

---

## 2. Hidden Dependencies the Plan Misses

### Hidden Dependency 1: Two `StreamEvent` classes

**The problem:** There are TWO `StreamEvent` classes:
- `agents/events.py` (395 lines) — 20+ factory methods, used by the agent state machine
- `streaming/emitter.py` (347 lines) — used by the SSE streaming layer

Both define `type`, `session_id`, `data`, `timestamp`, `to_dict()`, `to_sse()`, and overlapping factory methods (`state_change`, `response_chunk`, `error`, etc.).

**Impact:** Before adding new event types (`somatic_block`, `subagent_event`, `conversation_status`, `terminal_spawn`), we must either:
1. Unify into one `StreamEvent` class (breaking change, touches many files), OR
2. Add new event types to BOTH classes (duplication, maintenance burden), OR
3. Make `streaming/emitter.py:StreamEvent` inherit from `agents/events.py:StreamEvent` (least disruptive)

**Recommendation:** Option 3. Make `streaming/emitter.py` import from `agents/events.py` and add new factory methods there only. This is a ~30 line refactor that should be done in Phase A1.

### Hidden Dependency 2: State handlers are in separate files

**The problem:** The plan says "Wire into `agents/state_machine.py`" for several phases, but the state machine delegates to handlers in `agents/handlers/`:
- `agents/handlers/executing.py`
- `agents/handlers/observing.py`
- `agents/handlers/planning.py`
- `agents/handlers/reading.py`
- `agents/handlers/responding.py`
- `agents/handlers/searching.py`

**Impact:** When the plan says "wire Somatic Blocks into the REFLECTING state," the actual change is in `agents/handlers/` (or the equivalent reflecting handler), not directly in `state_machine.py`. The state machine file is 1,140 lines — it's the coordinator, but the per-state logic lives in handlers.

**Recommendation:** Update the plan's file targets. Phase A2 and C1 changes go into `agents/handlers/` files, not just `state_machine.py`.

### Hidden Dependency 3: `error_recovery.py` already has retry/backoff

**The problem:** The plan proposes creating `model/rate_limiter.py` (120 lines) with "exponential backoff with jitter for 429/529 responses." But `agents/error_recovery.py` (284 lines) already has:
- `ErrorType` enum with `LLM_RATE_LIMIT`, `LLM_TIMEOUT`, `LLM_API_ERROR`
- `RecoveryStrategy` with `retry`, `max_retries`, `backoff_seconds`
- `execute_with_retry()` — async retry with exponential backoff
- `classify_error()` — classifies exceptions by error string matching
- Circuit breaker with threshold and reset

**Impact:** The rate limiter should integrate with the existing error recovery, not duplicate it. The existing system handles agent-level retry; the new rate limiter handles HTTP-response-level retry (429/529 with `Retry-After` header). They're complementary, not overlapping, but the plan should acknowledge the existing system and wire them together.

**Recommendation:** `model/rate_limiter.py` should be ~60 lines (not 120) — just the HTTP-specific 429/529 handling with `Retry-After` header parsing. The retry loop and backoff should delegate to `ErrorRecoveryManager.execute_with_retry()`.

### Hidden Dependency 4: `proposal_generator.py` is the real approval orchestrator

**The problem:** The plan treats `approval/engine.py` as the approval system and says it's not wired to execution. But `findings/proposal_generator.py` (634 lines) is the actual orchestrator that:
- Creates Finding → calculates blast radius → creates Proposal → creates ApprovalRequest
- Handles approval decisions → executes changes → rolls back on failure
- Has idempotency guards

**Impact:** Phase C1 (Somatic Blocks) should wrap `ProposalGenerator`, not just `ApprovalEngine`. The `SomaticLifecycle` state machine should call `ProposalGenerator.generate()` in the Proposal phase and `handle_approval_decision()` in the Action phase. The plan's "do not rewrite" list mentions `approval/engine.py` but not `findings/proposal_generator.py`.

**Recommendation:** Add `findings/proposal_generator.py` to the "do not rewrite" list. The SomaticLifecycle wraps it.

### Hidden Dependency 5: `compression/` package already exists

**The problem:** The plan proposes context watermark features (F4) as if compression is new. But `compression/` package exists with:
- `compression/compressor.py` — abstract base + `NoopCompressor`
- `compression/factory.py` — `create_compressor()` factory
- `compression/lingua_compressor.py` — Lingua-based compression
- `compression/memory_lod.py` — memory LOD compression
- `compression/semantic_compressor.py` — semantic compression
- `context/assembler.py:_compress_with_cascade()` already uses this package

**Impact:** Phase F4 (Context Watermark) should use the existing compression infrastructure, not invent new compression. The micro-compaction (truncating old tool results) is new, but the full-compaction (LLM summary) can use `compression/semantic_compressor.py`.

**Recommendation:** F4 effort is ~60 lines (not 110) — just the watermark trigger, temporal gate, and topic boundary gate. The compression itself is already built.

### Hidden Dependency 6: `config/snapshot.py` + `config/drift.py` exist

**The problem:** The plan defers "What Changed? Biographical Diff" because it "requires config snapshot infrastructure." But `config/snapshot.py` (65 lines) and `config/drift.py` (3KB) already exist.

**Impact:** The biographical diff is a UI feature (rendering snapshot diffs), not a backend feature. The backend exists. This could be promoted from the cut list to a post-v1 polish item with ~100 lines of frontend work.

---

## 3. Preliminary Work Verification

### What's actually complete (verified by tests + git log)

| Roadmap Phase | Status | Evidence |
|---|---|---|
| Phase 0: SourcePrep doc ingestion | COMPLETE | `rag/jsonl_to_markdown.py`, `test_jsonl_to_markdown.py` |
| Phase 1: Intake pipeline | COMPLETE | `intake/pipeline.py`, `intake/signals.py`, `intake/budget.py`, `intake/complexity.py`, all tested |
| Phase 2: RAG consolidation | COMPLETE | SourcePrep is sole retrieval backend |
| Phase 3: Intake wiring | COMPLETE | `test_intake_pipeline.py`, `test_intake_signals.py`, `test_intake_budget.py`, `test_intake_complexity.py` |
| Phase 4: chat.py retirement | COMPLETE | commit `5141cfe` |
| Phase 4.5: Boot-test gate | COMPLETE (code) | `scripts/boot_smoke.py` exists, 5 checks. Server not running so fails — but code is there |
| Phase 5: Why data model + config brain | COMPLETE | `findings/`, `approval/`, `autonomy/`, `config/being_config.py`, all tested |
| Phase 6: Being config + voice | COMPLETE | `config/being_config.py` (167 lines), voice setting wired into prompt layer, Being tab in Settings |
| Phase 7: Proactive channel | COMPLETE | `proactive/events.py`, `proactive/gate.py`, `proactive/morning_report.py`, `proactive/detector_runner.py`, frontend SSE hook |
| Phase 8: Module registry + reactive slice | COMPLETE | `modules/registry.py` (128 lines, 4 modules), module invocation protocol in state machine, frontend module renderer |

**All 8 phases of the existing roadmap are complete.** The sovereign-host-vision work starts from a fully-built foundation, not from "Phases 6-8 not started" as the plan states.

### Test suite health

```
413 tests collected
395 passed, 18 skipped, 0 failed
21.07 seconds runtime
```

The 18 skipped tests are async tests that need `pytest-asyncio` plugin (not installed). This is a **test infrastructure gap** — not a code gap. Installing `pytest-asyncio` would activate 16 of the 18 skipped tests (the agent integration and phase-D integration tests).

**Action item:** Install `pytest-asyncio` before starting Phase A. The async tests cover the agent state machine and Phase D integration — exactly the code we're about to change.

### Dependencies verified

| Dependency | Status |
|---|---|
| `sqlite3` | Available (stdlib) |
| `aiofiles` | Available (already installed) |
| `fastapi` | Available |
| `pytest` | Available |
| `pytest-asyncio` | NOT installed — needed for 18 skipped tests |

---

## 4. Corrected Task List with Model Tier and Effort Level

**Model tier scale:** fable (trivial) → sonnet (standard) → opus (hardest)
**Effort scale:** med → high → xhigh → max → ultracode

### Phase A: Foundation

| Task | What | Model Tier | Effort | Lines | Why |
|---|---|---|---|---|---|
| **A0a** | Install `pytest-asyncio`, activate 18 skipped tests | fable | med | 0 | Trivial dep install; verifies async tests pass before we change anything |
| **A0b** | Unify `StreamEvent` classes (make emitter import from events) | sonnet | high | ~30 | Must be done before adding new event types; touches 2 files + all imports |
| **A1** | Conversation as block-typed messages | opus | xhigh | ~200 | Changes the core data representation; touches `states.py`, `assembler.py`, `react_agent.py`, `handlers/`; high risk of breaking agent loop |
| **A2a** | `ConversationStatus` enum + state machine | sonnet | high | ~110 | New enum + state machine; coordinates with existing `AgentState`; moderate complexity |
| **A2b** | Rate limiter (HTTP 429/529 only, delegate to error_recovery) | sonnet | high | ~60 | Smaller than v2.0 estimated (120→60) because error_recovery.py already has retry/backoff |
| **A2c** | Wire ConversationStatus into state machine + SSE | sonnet | high | ~60 | Touches `state_machine.py` + handlers + emitter; moderate integration work |
| **A3** | Outcome store | sonnet | high | ~130 | New SQLite table + recording logic; straightforward but needs async-safe writes |

**Phase A total: ~590 lines (v2.0 said 490 — close, but A0a/A0b add ~30)**

### Phase B: PTY Backend

| Task | What | Model Tier | Effort | Lines | Why |
|---|---|---|---|---|---|
| **B1a** | `PTYSession` (os.openpty + aiofiles + resize + ring buffer) | opus | max | ~200 | Hardest single component; raw fd management, async I/O, SIGWINCH, signal handling; no library to lean on |
| **B1b** | `TerminalSessionManager` (singleton, TTL reaper, max sessions) | sonnet | xhigh | ~120 | Concurrent session management, background reaper task, overflow handling |
| **B1c** | Sandbox integration (bwrap/sandbox-exec + path validation) | opus | xhigh | ~100 | Platform-specific, security-critical; getting sandbox profiles right is hard |
| **B1d** | Injection check (16+ dangerous patterns + host-specific) | sonnet | high | ~80 | Pattern enumeration + testing; moderate complexity |
| **B1e** | Rewrite terminal route (replace subprocess, add session endpoints) | sonnet | xhigh | ~120 | Route rewrite, backwards compat with existing safety tiers, new endpoints |
| **B1f** | WebSocket bridge (bidirectional stdin/stdout/resize) | sonnet | high | ~80 | WebSocket handling, message protocol, error recovery |

**Phase B total: ~700 lines (v2.0 said 780 — slightly lower because aiofiles is already installed and no dep management needed)**

### Phase C: Somatic Blocks and Integration

| Task | What | Model Tier | Effort | Lines | Why |
|---|---|---|---|---|---|
| **C1a** | `SomaticBlock` dataclass + `SomaticStore` | sonnet | high | ~150 | New dataclass + SQLite store; straightforward but needs to reference existing models correctly |
| **C1b** | `SomaticLifecycle` state machine | opus | xhigh | ~120 | Orchestrates 5 phases, calls existing modules (proposal_generator, approval_engine, recovery); getting the transitions right is complex |
| **C1c** | Per-file checkpoints (stack-based undo) | sonnet | high | ~80 | New checkpoint system; moderate complexity |
| **C1d** | Wire into state machine handlers + SSE + ProactiveEventBus | sonnet | xhigh | ~80 | Integration across handlers, emitter, and existing event bus; touches many files |
| **C2a** | `MetaHarnessRouter` (complexity + cost-cascade + outcome blending) | opus | xhigh | ~120 | The blending formula + ladder walk + opt-in flag; math-heavy, needs careful testing |
| **C2b** | Merge complexity systems + wire into tier router | sonnet | high | ~90 | Removing duplicate `_score_complexity`, wiring new router; moderate integration |

**Phase C total: ~540 lines (v2.0 said 600 — lower because proposal_generator.py already has the approval flow)**

### Phase D: Subagents

| Task | What | Model Tier | Effort | Lines | Why |
|---|---|---|---|---|---|
| **D1a** | `SubagentHandle` + `SubagentManager` (SQLite queue) | sonnet | xhigh | ~170 | Task queue with concurrency ceiling, FIFO overflow, cancel; moderate-high complexity |
| **D1b** | `StorageAuditorAgent` (deterministic script) | sonnet | high | ~100 | Command execution + regex parsing + block emission; deterministic, no LLM |
| **D1c** | Lifecycle event stream (SubagentEvent types) | sonnet | high | ~60 | Event types + SSE emission via existing ProactiveEventBus |
| **D1d** | Wire into state machine + ConversationStatus::WaitingForEvents | sonnet | xhigh | ~60 | Integration with A2's ConversationStatus; primary agent waits, resumes on completion |

**Phase D total: ~390 lines (v2.0 said 410 — close)**

### Phase E: Frontend

| Task | What | Model Tier | Effort | Lines | Why |
|---|---|---|---|---|---|
| **E1a** | `useTerminalSessions` hook (WebSocket per session, singleton) | sonnet | xhigh | ~120 | State management, WebSocket lifecycle, buffer management; moderate-high |
| **E1b** | `TerminalTile` component (inline xterm.js) | sonnet | xhigh | ~150 | xterm.js integration in conversation stream, status badge, quick actions |
| **E1c** | `TerminalAccordionDock` component | sonnet | high | ~200 | Accordion UI, session list, expand/collapse, jump-to-origin; UI-heavy |
| **E1d** | `useIntersectionDock` hook | fable | med | ~60 | IntersectionObserver wrapper; trivial |
| **E1e** | `TetherChip` component | fable | med | ~40 | Small inline chip; trivial |
| **E1f** | Integrate into SidePanel + SSE event handling | sonnet | high | ~140 | SidePanel modifications, new event types in useAgentStream |

**Phase E total: ~710 lines (v2.0 said 770 — close)**

### Phase F: Advanced Features

| Task | What | Model Tier | Effort | Lines | Why |
|---|---|---|---|---|---|
| **F1** | SQLite session store + FTS5 + migration | sonnet | high | ~160 | Schema + CRUD + FTS5 + migration script; mechanical |
| **F2** | Session affinity router (3-tier routing) | sonnet | high | ~140 | Regex + FTS5 + entity extraction reuse; moderate |
| **F3** | Living Reflexes (reflex store + matcher + scheduler wire) | sonnet | xhigh | ~200 | New YAML store + trigger matching + scheduler integration; moderate-high |
| **F4** | Context watermark (trigger + gates + micro-compaction) | opus | xhigh | ~60 | Smaller than v2.0 said (110→60) because compression/ package already exists; just gates + trigger |

**Phase F total: ~560 lines (v2.0 said 530 — close)**

---

## 5. Corrected Total Effort Estimate

| Phase | v2.0 Estimate | Corrected Estimate | Delta | Reason |
|---|---|---|---|---|
| A (Foundation) | 490 | 590 | +100 | Added A0a (pytest-asyncio) + A0b (StreamEvent unification) |
| B (PTY) | 780 | 700 | -80 | aiofiles already installed, no dep management |
| C (Somatic Blocks) | 600 | 540 | -60 | proposal_generator.py already has approval flow |
| D (Subagents) | 410 | 390 | -20 | ProactiveEventBus already exists |
| E (Frontend) | 770 | 710 | -60 | Minor corrections |
| F (Advanced) | 530 | 560 | +30 | F4 slightly larger, F3 slightly larger |
| **Total** | **~4,500** | **~3,490** | **-1,010** | More infrastructure exists than assumed |

**Plus ~300 lines for integration glue, tests, and migration scripts: ~3,800 lines total.**

This is **15% lower than v2.0's estimate** and **42% higher than v1.0's estimate**. The correction is primarily because Phases 6-8 are already complete, `proposal_generator.py` already links approval to execution, and the compression/proactive/scheduler infrastructure already exists.

---

## 6. Corrected Risk Register

| Risk | v2.0 Assessment | Corrected Assessment | Change |
|---|---|---|---|
| PTY implementation harder than estimated | High/High | High/High | No change — still the critical path |
| Block-typed message change breaks agent loop | Medium/High | Medium/High | No change — still risky |
| Conversation status conflicts with agent state | Medium/Medium | Low/Medium | Lower risk — `AWAITING_CONFIRMATION` already proves the state machine can block and resume |
| Approval-to-execution gap | High/High | **Low/Low** | **Resolved** — `proposal_generator.py:handle_approval_decision()` already does this; we just need to wire the state machine to it |
| Rate limiter duplicates error recovery | Not identified | Low/Low | New risk, but mitigated by delegating to existing `error_recovery.py` |
| StreamEvent class duplication causes confusion | Not identified | Medium/Medium | New risk — must unify before adding new event types |
| Compression cascade destroys turn structure | High/High | Medium/Medium | Lower — `compression/` package has multiple strategies; we can add a turn-preserving one |
| Scheduler doesn't survive restarts | Not identified | Low/Low | Existing scheduler is in-process; for v1 this is fine |

---

## 7. Corrected "Do Not Rewrite" List

Add these to the v2.0 list:

| Module | Why | What to add |
|---|---|---|
| `findings/proposal_generator.py` | 634 lines, full Finding→Proposal→Approval→Execute→Rollback flow | Wrap in SomaticLifecycle; do not rewrite |
| `agents/error_recovery.py` | 284 lines, retry/backoff/circuit breaker | Delegate rate limiter retry to this; do not duplicate |
| `proactive/events.py` | 178 lines, thread-safe event bus | Use for subagent events; do not create a new bus |
| `proactive/gate.py` | 123 lines, per-category gate | Use for reflex gating; do not rewrite |
| `proactive/morning_report.py` | 8.5KB, scheduler task | Use existing scheduler for reflexes; do not create a new one |
| `modules/registry.py` | 128 lines, 4 registered modules | Register subagent output as a new module; do not create a new registry |
| `config/snapshot.py` | 65 lines, config snapshots | Use for biographical diff; do not create a new snapshot system |
| `compression/` package | 5 files, multiple compressors | Use for context watermark; do not invent new compression |
| `agents/handlers/` | 6 handler files | Edit these for per-state changes, not just `state_machine.py` |

---

## 8. Corrected Implementation Order

The phase order doesn't change, but two new tasks are inserted at the start:

```
A0a. Install pytest-asyncio (fable/med, 0 lines, 10 minutes)
A0b. Unify StreamEvent classes (sonnet/high, ~30 lines, 2 hours)
A1.  Conversation as block-typed messages (opus/xhigh, ~200 lines)
A2a. ConversationStatus enum + state machine (sonnet/high, ~110 lines)
A2b. Rate limiter — HTTP only, delegate to error_recovery (sonnet/high, ~60 lines)
A2c. Wire ConversationStatus into state machine + SSE (sonnet/high, ~60 lines)
A3.  Outcome store (sonnet/high, ~130 lines)
B1.  Real PTY backend (opus/max, ~700 lines, 5-7 days)
C1.  Somatic Blocks (opus/xhigh, ~540 lines)
C2.  Cost-cascade router (opus/xhigh, ~210 lines)
D1.  Subagents (sonnet/xhigh, ~390 lines)
E1.  Frontend docking (sonnet/high, ~710 lines)
F1-F4. Advanced features (sonnet/high, ~560 lines)
```

**Total: ~3,800 lines, 5-7 weeks** (down from 6-8 weeks, because more infrastructure exists).

---

## 9. The Real Verdict

The v2.0 strategy is **directionally correct** but **factually outdated**. It was written from the pattern-inventory passes, not from a fresh audit of the codebase. The codebase is further along than the plan assumes:

- **All 8 existing roadmap phases are complete** (not 5 of 8)
- **The approval-to-execution flow exists** (via `proposal_generator.py`)
- **The SSE push transport exists** (via `proactive/events.py`)
- **The module registry exists** (via `modules/registry.py`)
- **The scheduler exists** (via `proactive/morning_report.py`)
- **The compression infrastructure exists** (via `compression/` package)
- **The config snapshot system exists** (via `config/snapshot.py`)
- **`aiofiles` is already installed**

The real work is:
1. **Block-typed conversation representation** (A1) — the true foundation
2. **Real PTY** (B1) — still the critical path, still 700 lines
3. **Somatic Block wrapper** (C1) — wraps existing modules, doesn't replace them
4. **Subagent task queue** (D1) — uses existing event bus and module registry
5. **Frontend docking** (E1) — React plumbing on top of the PTY

Everything else is integration work on existing infrastructure. The plan is sound; the estimates just need to come down by ~15%.
