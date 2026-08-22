# Consolidated Next Steps — Post-Research Action Plan

**Created:** 2026-08-22
**Status:** Recommendation for founder review
**Purpose:** Synthesize the two existing next-steps documents (`NEXT-STEPS-2026-08-22.md` and `RECOMMENDED-NEXT-STEPS-2026-08-22.md`) into a single authoritative plan, resolve discrepancies between them, and identify what's still missing.

---

## 0. Document inventory (what exists)

| Document | Lines | Status | Role |
|----------|-------|--------|------|
| `FOUNDATIONAL-RESEARCH-2026-08-21.md` | 888 | Complete | RQ1-RQ8 + phased plan |
| `CHAT-ARCHITECTURE-VALIDATION-2026-08-22.md` | 578 | Complete | Task FSM + cognitive tick design, §9 open questions, §11 reconciliation |
| `DEEP-RESEARCH-QUESTIONS-2026-08-22.md` | 1670 | Complete | RQ-A through RQ-E findings + RQ-A audit + RQ-B findings (scrutinized) + RQ-E findings + RQ-E audit |
| `RQ-B-SCRUTINY-2026-08-22.md` | 252 | Complete | 8 corrections to RQ-B (1 critical, 1 medium, 4 low, 2 trivial) |
| `RQ-C-SYSTEM-EVENT-TRIGGERS-2026-08-22.md` | 1067 | Complete + scrutinized | Trigger extensibility, event mapping, SystemEventMapper draft, §9 scrutiny |
| `RQ-D-CHAT-AUDIT-2026-08-22.md` | 266 | Complete | Port/discard/refactor table for chat.py |
| `RQ-D-SCRUTINY-2026-08-22.md` | 293 | Complete | 6 material errors + 5 omissions in original RQ-D audit |
| `FRAMEWORK-GENERALIZATION-2026-08-22.md` | 470 | Design exploration | Maps hardcoded vs generic, evaluates options A-D |
| `HALOYSIUS-FRAMEWORK-GENERALIZATION-2026-08-22.md` | 496 | Founder-approved handoff | Implementation spec for 4 backward-compatible Haloysius changes |
| `NEXT-STEPS-2026-08-22.md` | 351 | Recommendation | 5-step plan, Phase 1 first, parallelization map |
| `RECOMMENDED-NEXT-STEPS-2026-08-22.md` | 402 | Recommendation | 10-step plan, framework generalization first, detailed dependency graph |

**Problem:** Two next-steps documents exist with different orderings and different granularities. They agree on the dependency graph but disagree on what goes first and how to slice the work.

---

## 1. Reconciling the two existing plans

### Where they agree
- Framework generalization is a prerequisite for Phase 4.
- SourcePrep integration (Phase 2) is needed before the context assembler can work.
- Phase 1 chat collapse must happen before cutting chat.py.
- Three founder decisions are needed (RQ4 MVP capability, RQ-C core fix, RQ-D canonical context system).
- The RQ-D audit needs a re-do against `state_machine.py` internal handlers (not dead external classes).

### Where they disagree

| Question | NEXT-STEPS says | RECOMMENDED-NEXT-STEPS says | Resolution |
|----------|----------------|------------------------------|------------|
| What goes first? | Step 1: Finish Phase 1 (chat collapse) | Step 1: Framework generalization | **Both, in parallel.** They're in different repos with no shared files. Start both immediately. |
| How granular? | 5 steps, Phase-level | 10 steps, sub-task-level | **Use the 10-step granularity for execution, the 5-step for status reporting.** |
| Does Phase 1 chat collapse block Phase 2? | Yes (need single chat path) | No (Phase 2a is Halbert-side, independent) | **RECOMMENDED-NEXT-STEPS is correct.** The SourcePrep HTTP client (2a) and project registration (2b) are Halbert-side and don't need the chat collapse. The RetrievalBackend adapter (2b/3) does need to know where it'll be called from, but can be built against the seam protocol without the chat path being unified. |
| Is the RQ-D re-audit a separate step? | Yes, part of Step 1 | Not explicitly called out | **Make it an explicit sub-task.** The RQ-D scrutiny found 6 material errors because the audit compared against dead code. This re-audit must happen before any chat.py cutting. |

### What neither document mentions

1. **The RQ-B scrutiny C4 packaging dependency.** The consumer-side predicate approach depends on `memory_v2.temporal_graph` being available. In a subtractive core-only install before WP-12, this import may fail. This is a timing constraint: if Halbert uses a subtractive Haloysius install, the predicate work (Phase 4b) is blocked until WP-12 moves `memory_v2` to core. If Halbert uses the full install, it works today. **Decision needed: does Halbert use the full Haloysius install or a subtractive core-only wheel?**

2. **The RQ-B scrutiny C5 persona_id collision risk.** Halbert should use a separate `db_path` for the ledger to avoid collision with Haloysius persona names. This is a one-line implementation detail (`get_state_ledger(db_path=...)`) but should be decided upfront.

3. **The RQ-C scrutiny §6 gap: BELIEF and VALUE triggers are defined but never checked.** The trigger detector has enum values for belief and value triggers but no detection logic. This is a known gap in Haloysius that affects Halbert if we want config-belief-driven triggers (e.g., "I believe nginx should be running, but it's not → worry"). This is not a blocker for MVP but should be tracked.

4. **No verification step.** Neither plan includes a "run the test suite and verify nothing broke" step after each implementation step. Given the scrutiny found real bugs in the research, the implementation should be verified against tests at each step.

5. **No integration test plan.** The plans describe building pieces but don't describe how to verify the pieces compose correctly. An integration test that exercises the full path (system event → ledger → cognitive tick → prompt assembly → response) should be defined before implementation starts.

---

## 2. The consolidated plan

### Phase A: Parallel unblocking (start immediately)

**A1. Haloysius framework generalization** (Haloysius repo)
- Follow `HALOYSIUS-FRAMEWORK-GENERALIZATION-2026-08-22.md` §11 sequencing
- 4 changes: StateTracker protocol, clothing/location adapters, continuity.py tracker registry, state_renderer.py extensible predicates, identity.py default_identity parameter
- Merge gate: full test suite passes, H2/H3 behavior unchanged
- **Verification:** run Haloysius test suite after each change

**A2. RQ-D re-audit against state_machine.py** (Halbert repo)
- Re-do the port/discard/refactor table comparing chat.py against `state_machine.py` internal handlers (L332-719), NOT the dead external handler classes
- Incorporate `ContextInjector` (`prompts/context.py`) as the third context system
- Produce a corrected table that identifies which context system is canonical
- **Output:** Corrected port/discard/refactor table + canonical context system recommendation
- **This is a research task, not a code change** — it produces the blueprint for Phase C

**A3. SourcePrep HTTP client** (Halbert repo, `integrations/sourceprep_client.py`)
- Sync HTTP client wrapping the SourcePrep daemon API
- Endpoints: project status, context search, concept search, observation save, impact trace
- Use HTTP API, NOT MCP tool (MCP drops `chunks` list — RQ-A audit finding)
- **Verification:** unit tests against a mock SourcePrep daemon

**A4. PersonaMemoryStore wrapper adapter** (Halbert repo, `integrations/haloysius_memory_adapter.py`)
- Converts dict→PersonaMemory dataclass, string→MemoryType enum
- Wires `memory_store_add`/`memory_store_search` callbacks to PersonaMemoryStore
- ~20 lines, no dependencies
- **Verification:** unit test that a dict passed to the wrapper arrives as a PersonaMemory in the store

**A5. Identity setup** (Halbert repo)
- Set `HALOYSIUS_PROMPTS_DIR` to Halbert's prompts directory
- Create `human-identity.txt` with machine identity text
- Add startup check that verifies the file exists and is not the default human fallback
- **Depends on:** A1 (the `default_identity` parameter makes this cleaner, but it works even without it)
- **Verification:** startup check fires if file is missing

**Decision needed before A1 starts:** Import-time vs lazy tracker registration (handoff §10). Recommendation: import-time with `clear_state_trackers()`.

### Phase B: SourcePrep integration (after A3)

**B1. Register OS/config tree as SourcePrep project** (Halbert + SourcePrep daemon)
- Use `config/snapshot.py` to emit a synthesized config tree
- Register with custom include globs (`*.conf`, `*.service`, `*.yaml`, `*.toml`, extensionless files)
- Set up re-indexing on config change (Halbert-triggered, not SourcePrep-watched, for MVP)
- **Open questions from CoDRAG handoff §4:** chunking heuristics for config formats, extensionless file handling, secrets hygiene (redaction). These need resolution — may require a CoDRAG-side session.
- **Verification:** SourcePrep can search the index and return config file chunks

**B2. Build SourcePrepRetrievalBackend adapter** (Halbert repo, `context/sourceprep_retrieval.py`)
- Implements `RetrievalBackend` protocol from `seam.py`
- Uses HTTP client from A3 to call `POST /projects/{id}/context`
- Maps `chunks` to `List[Dict[str, Any]]` with `text`/`score`/`metadata`
- `format_context()` renders structured chunks with citations
- Fix the bug from RQ-A audit (empty results handling)
- **Depends on:** A3 (HTTP client), B1 (index exists)
- **Verification:** adapter returns results when queried, empty results don't crash

### Phase C: Chat path collapse (after A2)

**C1. Choose canonical context system** (foundator decision)
- Three systems: chat.py, ContextInjector, state machine internal assembler
- Research points toward state machine internal assembler as survivor
- ContextInjector's RAG formatting, project context, discovery summary get ported into it
- **This is a founder confirmation, not a research item**

**C2. Port ContextInjector logic into the canonical assembler** (Halbert repo)
- RAG formatting with citations and confidence thresholds
- Project context loading (HALBERT.md, agents.md, etc.)
- Discovery summary with critical issues
- User preferences formatting
- Model-specific prompt overrides
- **Depends on:** C1 (decision made), A2 (corrected table)
- **Verification:** the canonical assembler produces context blocks equivalent to ContextInjector for the same inputs

**C3. Cut dead code** (Halbert repo)
- Cut dead external handler classes (`handlers/planning.py`, `handlers/searching.py`, etc.)
- Cut chat.py context-injection blocks that are superseded by the canonical assembler
- Cut chat.py entirely once all PORT items are moved (this is the final step, after Phase D)
- **Depends on:** C2 (porting complete), Phase D (new chat handler working)
- **Verification:** test suite passes, no import errors

### Phase D: Haloysius wiring (after A1, B2, A4, A5)

**D1. Register seam implementations** (Halbert repo, startup code)
- `ModelBackend` → Ollama/local LLM adapter
- `RetrievalBackend` → `SourcePrepRetrievalBackend` (from B2)
- `GovernancePolicy` → approval/autonomy/dry-run gate
- `AppSeam` → routes, config tools, schema loader
- Call `register_app_seam()` at startup
- **Verification:** `get_app_seam()` returns the registered seam

**D2. Register Halbert's state trackers** (Halbert repo)
- `clear_state_trackers()` to remove clothing/location defaults
- Register `SystemHealthTracker` (disk, service, thermal predicates per RQ-B §6 schema)
- Register `ConfigStateTracker` (config drift predicates)
- Use medium renderer tier (RQ-B scrutiny C1: `_render_natural` drops unknown subjects)
- Use separate `db_path` for the ledger (RQ-B scrutiny C5: collision risk)
- **Depends on:** A1 (framework generalization provides StateTracker protocol)
- **Verification:** `render_state_block("halbert")` returns system-state block, not clothing/location

**D3. Build SystemEventMapper** (Halbert repo, `integrations/system_event_mapper.py`)
- Background scan thread (scan latency 30+ seconds, cannot block tick — RQ-C scrutiny 9.7)
- Reads from `DiscoveryEngine` cache, NOT `scan_all()` at tick time
- Maps CRITICAL discoveries → worries (intensity 0.9, intrusion_rate=1.0)
- Maps WARNING discoveries → worries (intensity 0.6) or emotions
- Uses `EmotionalStateV2.trigger_from_event()` — the designed integration point
- Runs EVERY TURN before `advance_turn()` to counteract worry decay (0.02/turn; intensify by 0.03/turn)
- Deduplicates by discovery ID; resolves cleared worries
- Uses `queue.Queue` for pending config events (thread safety)
- All content in embodied first-person ("my disk /dev/sda1")
- **Depends on:** A1 (framework generalization for tracker integration)
- **Verification:** a mock CRITICAL discovery produces a worry in PersonaCognition

**D4. Fix thought generation gap** (Haloysius repo OR Halbert repo)
- **Option A (preferred):** 4-line core change in Haloysius `advance_turn()` to pass cognitive state to `generator.generate()`. Benefits all consumers.
- **Option B (fallback):** Halbert implements `HalbertThoughtGenerator` subclass that extracts worry content from `trigger_data["intrusions"]`.
- **Decision needed:** founder approves Option A (core change) or Option B (consumer-side)?
- **Verification:** WORRY trigger produces a thought with system-specific content, not generic "I can't stop thinking about it"

**D5. Build context assembler** (Halbert repo)
- Orchestrates three layers into `additional_context` for `IdentityPromptBuilder.build_full_prompt()`:
  1. SourcePrep concepts + observations (`prep_search` via HTTP client)
  2. Haloysius state block (`render_state_block("halbert")`)
  3. Halbert identity + CRAG reflection (`SelfReflector.reflect()`)
- Port ContextInjector's unique logic (from C2) into this assembler
- Token budgeting + position-aware ordering
- **Depends on:** B2 (SourcePrep adapter), D2 (state trackers registered), C2 (ContextInjector ported)
- **Verification:** assembler produces a coherent context string with all three layers

**D6. Wire cognitive tick into FSM** (Halbert repo)
- Add SENSING and REFLECTING states to agent state machine
- `StateContext` gets `persona_cognition`, `continuity_ledger`, `session_memory` fields
- SENSING: load PersonaCognition from disk, run SystemEventMapper (D3), read continuity ledger
- REFLECTING: call `advance_turn()` with memory callbacks (via A4 wrapper), persist cognition
- RESPONDING: inject `cognition.get_prompt_blocks()` into response prompt
- Write episodic memory of the conversation (separate from thought promotion — RQ-E audit E5)
- **Depends on:** D3 (event mapper), A4 (memory wrapper), D5 (context assembler)
- **Verification:** integration test — full path from system event → tick → prompt → response

**D7. Rebuild chat handler** (Halbert repo)
- Wire the state machine with new states into the agent route
- SSE integration for streaming
- Replace chat.py's monolithic route with the state machine + assembler + Haloysius wiring
- **Depends on:** D5, D6
- **Verification:** chat works end-to-end through the new path

**D8. Harvest and cut chat.py** (Halbert repo)
- Using the corrected port/discard/refactor table from A2/C2
- Port remaining valuable logic (keyword discovery, failure correlation, model routing)
- Cut chat.py entirely
- **Depends on:** D7 (new chat handler working), C2 (porting complete)
- **Verification:** all chat.py functionality is covered by the new path; test suite passes

### Phase E: Config-physiology brain (after B1, partial D)

**E1. Founder product decision: MVP config capability** (RQ4 reframed)
- Detect misconfigurations or drift
- Explain why a setting is set the way it is
- Deduplicate or consolidate scattered settings
- Propose changes under safe autonomy (dry-run → approval → apply → rollback)
- Maintain a live, queryable model of the system's config state
- **This is a product call, not a research item**

**E2. Implement chosen MVP capability** (Halbert repo)
- Depends on E1 decision
- Uses SourcePrep concepts (assertion violation = misconfiguration)
- Uses config drift detection (`config/drift.py`)
- Uses the cognitive tick (worry about config drift once D6 is wired)
- **Depends on:** E1, B1 (SourcePrep index), D6 (cognitive tick)

---

## 3. Parallelization map

```
Time →  Week 1          Week 2          Week 3          Week 4          Week 5+

A1: Framework Gen    [========]
A2: RQ-D re-audit    [====]                                (feeds C1-C3)
A3: SourcePrep client[====]
A4: Memory wrapper   [==]
A5: Identity setup      [==]
                       ↓
B1: SourcePrep project   [========]
B2: Retrieval adapter       [====]
                               ↓
C1: Canonical system decision [↓ founder]
C2: Port ContextInjector       [========]
                                       ↓
D1: Register seams                [====]
D2: Register trackers             [====]
D3: SystemEventMapper             [========]
D4: Thought gen fix               [====]
D5: Context assembler                [========]
D6: Cognitive tick wiring                [========]
D7: Chat handler rebuild                     [========]
D8: Harvest + cut chat.py                       [========]
                                                        ↓
E1: Founder MVP decision                            [↓ founder]
E2: Config brain                                       [========]
```

**Parallel tracks in Week 1:**
- Track 1 (Haloysius): A1 (framework generalization)
- Track 2 (Halbert): A2 (RQ-D re-audit) + A3 (SourcePrep client) + A4 (memory wrapper) + A5 (identity setup)

**Parallel tracks in Week 2-3:**
- Track 1 (Halbert): B1 + B2 (SourcePrep integration)
- Track 2 (Halbert): C1 + C2 (chat path collapse, gated by A2 completion)

**Week 3+ is mostly sequential** through the D steps, but D1/D2/D3/D4 can overlap with D5 preparation.

---

## 4. Founder decisions needed (with timing)

| Decision | When needed | Options | Recommendation |
|----------|-------------|---------|----------------|
| **D-A: Tracker registration mode** | Before A1 starts | Import-time vs lazy | Import-time with `clear_state_trackers()` |
| **D-B: Full vs subtractive Haloysius install** | Before D2 | Full install (works today) vs subtractive (needs WP-12) | Full install for MVP; subtractive after WP-12 |
| **D-C: Ledger db_path isolation** | Before D2 | Shared default db vs separate Halbert db | Separate `db_path` for isolation (RQ-B C5) |
| **D-D: Thought generation fix** | Before D4 | 4-line core change (Option A) vs Halbert subclass (Option B) | Option A (core fix benefits all consumers) |
| **D-E: Canonical context system** | Before C2 | State machine assembler vs ContextInjector vs new | State machine internal assembler (research recommendation) |
| **D-F: RQ4 MVP config capability** | Before E2 | Drift detection, config explanation, dedup, safe autonomy, live model | Founder product call |
| **D-G: User-facing terminal** | Phase 1 cleanup | Keep or cut | Cut (founder said "questionable, not a priority") |

---

## 5. Integration test plan (missing from both prior documents)

Before any Phase D implementation, define an integration test that exercises the full composed path:

```
1. SystemEventMapper detects a mock CRITICAL discovery (disk SMART failure)
2. SystemEventMapper writes worry to PersonaCognition
3. SystemEventMapper writes predicate to TemporalStateLedger
4. Cognitive tick (advance_turn) fires:
   a. Trigger detection sees the worry → fires WORRY trigger
   b. Thought generator produces a system-specific thought
   c. Thought promoter promotes to PersonaMemoryStore (via wrapper adapter)
5. Context assembler composes:
   a. SourcePrep returns config context for the failing disk
   b. render_state_block returns "Disk Health: SMART failure"
   c. IdentityPromptBuilder produces machine-identity prompt
6. LLM receives the composed prompt
7. Response includes awareness of the disk failure
8. Episodic memory of this conversation is written
9. PersonaCognition is persisted to disk
```

This test should be written BEFORE implementation starts (TDD-style) and should fail until all Phase D pieces are wired. It serves as the acceptance criterion for the entire wiring phase.

---

## 6. What to do right now

1. **Founder reviews this document and makes decisions D-A through D-G** (7 decisions, most are quick confirmations)
2. **Start A1 (framework generalization) and A2 (RQ-D re-audit) in parallel** — these are the two unblocking items in different repos
3. **Start A3, A4, A5 in parallel** — these are small Halbert-side tasks with no dependencies
4. **Write the integration test** (§5) before any Phase D implementation begins
5. **Schedule the RQ4 product decision** (D-F) — it doesn't block Phases A-D but blocks Phase E

---

## 7. Comparison to prior documents

| Aspect | NEXT-STEPS (5-step) | RECOMMENDED-NEXT-STEPS (10-step) | This document (consolidated) |
|--------|---------------------|----------------------------------|------------------------------|
| First step | Phase 1 chat collapse | Framework generalization | **Both in parallel** (different repos) |
| Granularity | Phase-level | Sub-task-level | Sub-task-level with explicit dependencies |
| RQ-D re-audit | Part of Step 1 | Not explicitly called out | **Explicit sub-task (A2)** |
| Packaging dependency (RQ-B C4) | Not mentioned | Not mentioned | **Listed as decision D-B** |
| Ledger isolation (RQ-B C5) | Not mentioned | Not mentioned | **Listed as decision D-C** |
| Integration test | Not mentioned | Not mentioned | **§5 defines the full-path test** |
| Verification steps | Not mentioned | Not mentioned | **Each step has a verification criterion** |
| Founder decisions | 3 listed | 3 listed | **7 listed with timing** |
| Belief/Value trigger gap | Not mentioned | Not mentioned | **Tracked as known gap (§1 item 3)** |
