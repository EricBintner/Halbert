# Recommended Next Steps

**Created:** 2026-08-22
**Status:** Planning document — awaiting founder approval before execution
**Scope:** Synthesizes findings from all five research questions (RQ-A through RQ-E), their audits/scrutinies, and the Haloysius framework generalization handoff into a concrete action plan.

---

## 1. Where we are now

All five deep-research questions have been investigated, audited, and scrutinized. The research phase is complete. Here is the status of each:

| RQ | Verdict | Audit/Scrutiny outcome | Feeds |
|----|---------|------------------------|-------|
| **RQ-A** (seam shape) | WRAP SourcePrep behind existing `RetrievalBackend` | Audit found 1 bug (MCP tool drops `chunks` — must use HTTP API), 1 wrong mapping (`prep_impact` is not `GovernancePolicy`), 2 overlooked prerequisites (no SourcePrep client exists; pre-seam.py pattern still live in `scenario/generator.py`). Recommendation survives. | Phase 2, Phase 4 |
| **RQ-B** (system-state predicates) | Consumer-side, zero core changes for storage | Scrutiny confirmed ledger is schema-free. Found 8 issues: C1 critical (`_render_natural` silently drops unknown subjects), C3 (continuity functions not called by any Haloysius code), C4 (packaging dependency on WP-12). Predicate schema revised. | Phase 4 |
| **RQ-C** (system-event triggers) | Consumer-side mapping (Option D), populate `PersonaCognition` before tick | Scrutiny found "no core changes" is overstated for thought quality (4-line core fix or custom `ThoughtGenerator` needed). Found thread safety gap, scan latency blocker, worry decay counteraction needed. | Phase 4 |
| **RQ-D** (chat.py audit) | New assembler covers ~20% of chat.py; most gap is keyword discovery + prompt assembly | Scrutiny found 6 material errors (compared against dead handler classes, missed `ContextInjector` as third system, model routing is actively used). Corrected architecture map and porting priority produced. | Phase 4 |
| **RQ-E** (self-model architecture) | Three-layer composition (SourcePrep objective + Haloysius subjective + Halbert glue) | Audit found 4 imprecise claims, 3 overlooked gaps. Key corrections: identity file is `human-identity.txt` not `machine-identity.txt`; `memory_store_add` needs wrapper adapter (dict→PersonaMemory); `advance_from_response()` does NOT write episodic memories; `prep_observe` is for objective events only, not thought promotion. | Phase 2, Phase 4 |

**Additionally:** The Haloysius framework generalization handoff (`HALOYSIUS-FRAMEWORK-GENERALIZATION-2026-08-22.md`) is a founder-approved design for making Haloysius's state tracking pluggable (StateTracker protocol, extensible predicate rendering, configurable identity). This is a **prerequisite for clean Phase 4 work** — it unblocks Halbert from forking or working around hardcoded human-persona assumptions.

---

## 2. The dependency graph

```
                    ┌─────────────────────────────────┐
                    │  Haloysius Framework             │
                    │  Generalization                  │
                    │  (founder-approved,              │
                    │   4 backward-compatible changes) │
                    └──────────────┬──────────────────┘
                                   │ unblocks
                    ┌──────────────┴──────────────────┐
                    │                                 │
                    v                                 v
         ┌──────────────────┐              ┌──────────────────┐
         │  Phase 2:         │              │  Phase 4:         │
         │  SourcePrep       │              │  Haloysius        │
         │  Integration      │              │  Wiring           │
         └────────┬─────────┘              └────────┬─────────┘
                  │                                  │
         ┌────────┴─────────┐              ┌────────┴─────────┐
         │ 2a: Build         │              │ 4a: PersonaMemory  │
         │ SourcePrep HTTP   │              │ wrapper adapter    │
         │ client            │              │ (E3 correction)    │
         └────────┬─────────┘              └────────┬─────────┘
                  │                                  │
         ┌────────┴─────────┐              ┌────────┴─────────┐
         │ 2b: Build         │              │ 4b: Identity       │
         │ SourcePrep-       │              │ setup (env var +   │
         │ backed             │              │ human-identity.txt │
         │ RetrievalBackend  │              │ + startup check)   │
         └────────┬─────────┘              └────────┬─────────┘
                  │                                  │
                  │                      ┌────────┴─────────┐
                  │                      │ 4c: SystemEvent   │
                  │                      │ Mapper (RQ-C)     │
                  │                      │ + background scan │
                  │                      │ thread            │
                  │                      └────────┬─────────┘
                  │                                 │
                  │           ┌─────────────────────┘
                  │           │
         ┌────────┴───────────┴─────────┐
         │ 4d: Context assembler         │
         │ (orchestrates SourcePrep +    │
         │  Haloysius state + Halbert    │
         │  identity → additional_context)│
         └────────┬─────────────────────┘
                  │
         ┌────────┴─────────┐
         │ 4e: Cognitive tick │
         │ wiring (advance_   │
         │ turn + memory      │
         │ callbacks +        │
         │ episodic writes)   │
         └────────┬─────────┘
                  │
         ┌────────┴─────────┐
         │ 4f: Chat handler   │
         │ rebuild (state     │
         │ machine + SENSING/ │
         │ REFLECTING states) │
         └────────┬─────────┘
                  │
         ┌────────┴─────────┐
         │ 4g: Harvest + cut  │
         │ chat.py (RQ-D      │
         │ port/discard table)│
         └──────────────────┘
```

---

## 3. Recommended next steps (ordered)

### Step 1: Execute the Haloysius Framework Generalization

**What:** Implement the 4 changes in `HALOYSIUS-FRAMEWORK-GENERALIZATION-2026-08-22.md`:
1. `state_tracker.py` — StateTracker protocol + InternalStateCategory enum
2. `clothing_tracker.py` + `location_tracker.py` — adapters wrapping existing state machines
3. Modify `continuity.py` — tracker registry, replace hardcoded `_advance()`
4. Modify `state_renderer.py` — extensible predicate rendering with prose templates
5. Modify `identity.py` — `default_identity` parameter

**Why first:** This is the keystone. Every Phase 4 item depends on Haloysius being able to accept non-human-persona state trackers, predicates, and identity. Without this, Halbert must fork or work around hardcoded human assumptions. The founder has approved this design. It's backward-compatible (H2/H3 see no change).

**Where:** Haloysius repo (`/Volumes/4TB-BAD/Haloysius/`)
**Effort:** Medium (4 small changes, all backward-compatible, with tests)
**Can run in parallel with:** Step 2 (Phase 2a is Halbert-side, independent of Haloysius changes)

**Sequencing within this step (per handoff §11):**
1. Create `state_tracker.py` (no dependencies)
2. Create clothing/location tracker adapters (depend on step 1)
3. Modify `continuity.py` (depends on steps 1-2)
4. Modify `state_renderer.py` (independent of steps 1-3)
5. Modify `identity.py` (independent of steps 1-4)
6. Write tests + run full suite

Steps 4 and 5 can be done in parallel with steps 1-3.

**Open questions to resolve before starting (per handoff §10):**
- Import-time registration vs. lazy registration (recommendation: import-time, with `clear_state_trackers()`)
- `sync_to_ledger()` on the protocol (recommendation: keep it)
- Subject label grouping (recommendation: keep existing for MVP)
- Prose template complexity (recommendation: no conditionals)

---

### Step 2: Build the SourcePrep HTTP client (Phase 2a)

**What:** Create `halbert_core/integrations/sourceprep_client.py` — a sync HTTP client wrapping the SourcePrep daemon API:
- `GET /projects/{id}` — index status
- `POST /projects/{id}/context` — semantic search (structured, with chunks)
- `POST /projects/{id}/concepts/search` — concept queries
- `POST /projects/{id}/observations` — save observations
- `GET /projects/{id}/trace/impact` — blast radius (for future Phase 3)

**Why second:** This is the prerequisite for the `SourcePrepRetrievalBackend` adapter (Step 3) and for the context assembler (Step 6). Without a client, no SourcePrep integration is possible. The RQ-A audit found that Halbert has zero SourcePrep integration code today.

**Where:** Halbert repo (`halbert_core/halbert_core/integrations/`)
**Effort:** Small (one module, sync HTTP calls, error handling)
**Can run in parallel with:** Step 1 (independent — Halbert-side, no Haloysius dependency)

**Design notes from RQ-A audit:**
- Must use HTTP API, NOT MCP tool (MCP tool drops `chunks` list)
- Sync (not async) — matches the Haloysius `RetrievalBackend` protocol
- The daemon runs at `localhost:8400` by default
- Project ID for the OS/config index needs to be resolved (may need SourcePrep-side project registration first — see Step 2b)

---

### Step 2b: Register the OS/config tree as a SourcePrep project

**What:** Use Halbert's existing config snapshotter (`config/snapshot.py`) to emit a synthesized config tree, then register it as a SourcePrep project with custom include globs (for `*.conf`, `*.service`, `*.yaml`, `*.toml`, extensionless files like `fstab`).

**Why:** Before the retrieval adapter can search, SourcePrep needs an index to search. This is the "index the OS as a project" ask from the CoDRAG handoff.

**Where:** Halbert repo (tree emission) + SourcePrep daemon (project registration)
**Effort:** Medium (tree emission exists via snapshotter; registration + custom globs + freshness loop is new)
**Depends on:** Step 2 (the HTTP client)
**Can run in parallel with:** Step 1 (Haloysius changes)

**Open questions from CoDRAG handoff §4 that need resolution:**
- OS project profile (config/OS project type vs. custom globs only)
- Freshness model (Halbert re-indexes on change vs. SourcePrep watches)
- Chunking heuristics for config formats
- Extensionless file handling
- Secrets hygiene (redaction for OS-scope index)
- Multi-project per host (one project or per-domain)

These are SourcePrep-side questions. Some may need a session in the CoDRAG repo. For MVP, custom globs + Halbert-triggered re-indexing is the simplest path.

---

### Step 3: Build the SourcePrepRetrievalBackend adapter (Phase 2b)

**What:** Create `halbert_core/context/sourceprep_retrieval.py` — the corrected adapter from RQ-A audit §A7. Uses the HTTP client from Step 2 to call `POST /projects/{id}/context`, maps `chunks` to `List[Dict[str, Any]]` with `text`/`score`/`metadata`, and renders `format_context()` from structured chunks.

**Why:** This is the `RetrievalBackend` implementation that the Haloysius core will call during SENSING/PLANNING context assembly. It's the concrete wiring of SourcePrep into the seam.

**Where:** Halbert repo (`halbert_core/halbert_core/context/`)
**Effort:** Small (one module, ~80 lines, using the HTTP client from Step 2)
**Depends on:** Step 2 (HTTP client), Step 2b (index exists)
**Can run in parallel with:** Step 1 (Haloysius changes)

---

### Step 4: Build the PersonaMemoryStore wrapper adapter (Phase 4a)

**What:** Create the dict-to-PersonaMemory adapter identified in RQ-E audit E3. The cognitive tick's `memory_store_add` callback receives a dict; `PersonaMemoryStore.smart_add()` expects a `PersonaMemory` dataclass with `MemoryType` enum. The wrapper converts dict→dataclass and string→enum.

**Why:** Without this, the cognitive tick's thought promotion crashes when it tries to persist a promoted thought. This is a hard prerequisite for wiring `advance_turn()`.

**Where:** Halbert repo (likely `halbert_core/halbert_core/integrations/haloysius_memory_adapter.py`)
**Effort:** Small (one function pair, ~20 lines)
**Depends on:** Nothing (can be built immediately)
**Can run in parallel with:** Steps 1-3

---

### Step 5: Identity setup (Phase 4b)

**What:** Set `HALOYSIUS_PROMPTS_DIR` to Halbert's prompts directory. Create `human-identity.txt` there with machine identity text ("I am Halbert, the computer..."). Add a startup check that verifies the file exists and is not the default human fallback.

**Why:** The RQ-E audit E2 found that the identity file must be named `human-identity.txt` (hardcoded in `identity.py`), and the fallback is silently human. Without this, Halbert would get human-body identity with no error.

**Where:** Halbert repo (prompts directory + startup code)
**Effort:** Small (one file + one check)
**Depends on:** Step 1 (the `default_identity` parameter in `identity.py` — though this works even without the framework generalization, the generalization makes it cleaner)
**Can run in parallel with:** Steps 2-4

---

### Step 6: Build the SystemEventMapper (Phase 4c)

**What:** Create `halbert_core/integrations/system_event_mapper.py` — reads from `DiscoveryEngine` and `ConfigWatcher`, maps system events to cognitive state mutations (worries, emotions, drives) on `PersonaCognition` before `advance_turn()` is called. Includes a background scan thread (scan latency is 30+ seconds, cannot block the conversation tick).

**Why:** This is the RQ-C implementation. System events (disk failures, service crashes, config drift) need to map onto the cognitive tick's existing trigger mechanism. The mapper populates worries/emotions/drives; the existing trigger detector fires naturally.

**Where:** Halbert repo
**Effort:** Medium (mapper logic + background thread + thread-safe event queue)
**Depends on:** Step 1 (framework generalization — for clean state tracker integration)
**Can run in parallel with:** Steps 2-5

**Key corrections from RQ-C scrutiny to incorporate:**
- Background scan thread is REQUIRED for MVP (not Phase 2+) — `scan_all()` blocks 30+ seconds
- Mapper must run EVERY TURN to counteract worry decay (0.02/turn); intensify by 0.03/turn for persistent issues
- Use `EmotionalStateV2.trigger_from_event()` — the designed integration point
- Use `queue.Queue` for `_pending_config_events` (thread safety)
- Set `intrusion_rate=1.0` for CRITICAL events (deterministic firing)
- Custom `ThoughtGenerator` subclass is MANDATORY if the 4-line core fix to `advance_turn()` is not applied (thoughts would be generic otherwise)

**Decision needed:** Propose the 4-line core fix to Haloysius's `advance_turn()` (pass cognitive state to the generator), OR build a Halbert-side `HalbertThoughtGenerator` subclass. The core fix is cleaner; the subclass avoids touching Haloysius. Recommend: propose the core fix first; if rejected, use the subclass.

---

### Step 7: Build the context assembler (Phase 4d)

**What:** Build the Halbert-side context assembler that orchestrates all three layers into `additional_context` for `IdentityPromptBuilder.build_full_prompt()`:
1. Call SourcePrep (`prep_search` via HTTP client) for relevant config/system context
2. Call Haloysius's `render_state_block()` for current continuity state
3. Call `SelfReflector.reflect()` for CRAG evaluation
4. Combine into a single `additional_context` string

**Why:** This is where the three layers compose (RQ-E audit E8). The prompt assembly is a Halbert-side responsibility — it orchestrates SourcePrep (objective), Haloysius (subjective), and Halbert (glue) into one context string.

**Where:** Halbert repo (likely extends `halbert_core/context/assembler.py` or creates a new `self_model_assembler.py`)
**Effort:** Medium (orchestration logic + token budgeting + position-aware ordering)
**Depends on:** Steps 2-3 (SourcePrep client + adapter), Step 1 (Haloysius state rendering)
**Can run in parallel with:** Steps 4-6 (those are independent wiring pieces)

**Key input from RQ-D scrutiny:**
- The existing `ContextAssembler` covers 5 sources but lacks: self-knowledge/CRAG, telemetry, system identity, topic detection, failure correlation, web search, safety validation, prompt building
- The existing `ContextInjector` in `prompts/context.py` is a THIRD context-injection system that was missed in the original audit — it needs to be merged into the new assembler
- The external handler classes (`handlers/planning.py`, `handlers/searching.py`) are dead code — the real handlers are internal methods in `state_machine.py`
- Model routing functions in `chat.py` are actively used (via `LLMClientAdapter`) — should be PORTED, not discarded

---

### Step 8: Wire the cognitive tick (Phase 4e)

**What:** Wire `advance_turn()` into the Halbert chat flow:
1. Load `PersonaCognition` from disk at session start (the cross-session "I AM")
2. Before the tick: run `SystemEventMapper` (Step 6) to populate cognitive state from system events
3. Call `advance_turn()` with `memory_store_add`/`memory_store_search` pointing to the `PersonaMemoryStore` wrapper adapter (Step 4)
4. After the tick: write episodic memory of the conversation (separate from thought promotion — RQ-E audit E5)
5. Save `PersonaCognition` to disk at session end

**Why:** This is the actual "the cognitive tick runs, the self-model persists, the response voice reflects the evolved self-model" thesis from CHAT-ARCHITECTURE-VALIDATION §8.

**Where:** Halbert repo (state machine + new `reflecting.py` handler)
**Effort:** Medium (wiring + persistence + handler integration)
**Depends on:** Steps 1, 4, 6 (framework generalization + memory adapter + event mapper)
**Can run in parallel with:** Step 7 (context assembler) — they touch different parts of the flow

**Key corrections from RQ-E audit to incorporate:**
- `memory_store_add` → `PersonaMemoryStore` (NOT `prep_observe`) — E10
- Episodic memory writes are the chat handler's job, NOT `advance_from_response()` — E5
- `prep_observe` is for objective system events only, written by the event detection layer — E10

---

### Step 9: Rebuild the chat handler with new states (Phase 4f)

**What:** Rebuild the agent route (`dashboard/routes/agent.py`) with the new state machine from CHAT-ARCHITECTURE-VALIDATION §4:
- Add SENSING state (system state gathering)
- Add REFLECTING state (calls `advance_turn()`)
- Add `persona_cognition`, `continuity_ledger`, `session_memory` to `StateContext`
- Wire SENSING → PLANNING → ACTING → OBSERVING → REFLECTING → RESPONDING → IDLE
- Inject `PersonaCognition.to_prompt_block()` into the response prompt at RESPONDING

**Why:** This is the composed-loop architecture that replaces the monolithic `chat.py` route. The state machine already exists (`agents/state_machine.py`); it needs the new states and the Haloysius wiring.

**Where:** Halbert repo
**Effort:** Large (state machine extension + handler refactoring + SSE integration)
**Depends on:** Steps 7-8 (context assembler + cognitive tick wiring)
**Can run in parallel with:** Nothing in this sequence (this is the integration point)

---

### Step 10: Harvest and cut chat.py (Phase 4g)

**What:** Using the corrected port/discard/refactor table from RQ-D scrutiny, harvest the remaining valuable context-injection logic from `chat.py` into the new context assembler, then cut `chat.py` entirely.

**Why:** `chat.py` is 4,099 lines of monolithic route code. The new architecture replaces it with the state machine + context assembler + Haloysius wiring. But `chat.py` contains logic that the new architecture lacks (keyword discovery, failure correlation, model routing, safety validation). These need to be ported before the file is cut.

**Where:** Halbert repo
**Effort:** Large (line-by-line port + testing + cutting 4K lines)
**Depends on:** Step 9 (new chat handler is working)
**Can run in parallel with:** Nothing (this is the final step)

**Key input from RQ-D scrutiny:**
- 6 material errors in the original audit were corrected
- The corrected architecture map identifies 3 context-injection systems (not 2): `ContextAssembler`, `ContextInjector`, and `chat.py`'s inline injection
- Model routing functions are actively used — PORT, not DISCARD
- The corrected porting priority is in RQ-D-SCRUTINY §"Corrected Porting Priority"

---

## 4. What can run in parallel

```
Time →  ──────────────────────────────────────────────────────────────

Step 1: [Haloysius Framework Generalization ████████████████]
Step 2: [SourcePrep HTTP client ███████]                              ← parallel with Step 1
Step 2b:[OS tree registration ███████████████]                        ← after Step 2
Step 3: [RetrievalBackend adapter ████]                               ← after Step 2b
Step 4: [PersonaMemory wrapper ██]                                    ← parallel with all
Step 5: [Identity setup ██]                                           ← parallel with all
Step 6: [SystemEventMapper ████████████]                              ← after Step 1, parallel with 2-5
Step 7: [Context assembler ████████████████]                          ← after Steps 1-3, 6
Step 8: [Cognitive tick wiring ████████████]                          ← after Steps 1, 4, 6
Step 9: [Chat handler rebuild ████████████████████████]               ← after Steps 7-8
Step 10:[Harvest + cut chat.py ████████████████████]                  ← after Step 9
```

**Three parallel tracks initially:**
- Track A: Haloysius framework generalization (Step 1) → SystemEventMapper (Step 6)
- Track B: SourcePrep client (Step 2) → OS tree registration (Step 2b) → RetrievalBackend adapter (Step 3)
- Track C: PersonaMemory wrapper (Step 4) + Identity setup (Step 5) — quick wins, can be done immediately

Tracks A and B converge at Step 7 (context assembler). Track C converges at Step 8 (cognitive tick wiring).

---

## 5. Decisions needed from the founder before starting

1. **RQ-C thought quality fix:** Propose the 4-line core fix to Haloysius's `advance_turn()` (pass cognitive state to the generator), or build a Halbert-side `HalbertThoughtGenerator` subclass? (Recommend: propose core fix first; subclass as fallback.)

2. **RQ4 (reframed):** What is the first concrete config-physiology capability for MVP? The candidates from the founder decisions section are: detect misconfigurations/drift, explain why a setting is set, deduplicate settings, propose changes under safe autonomy, maintain a live config model. This is a product decision, not a research item. (Recommend: "explain why a setting is set" — it leverages SourcePrep concepts directly and is the lowest-risk first capability.)

3. **SourcePrep OS project questions (CoDRAG handoff §4):** How to handle freshness, chunking, extensionless files, secrets hygiene, and multi-project per host. Some of these may need a session in the CoDRAG repo. (Recommend: start with custom globs + Halbert-triggered re-indexing for MVP; defer the rest.)

4. **Haloysius framework generalization open questions (handoff §10):** Import-time vs. lazy registration, `sync_to_ledger()` on protocol, subject grouping, prose template complexity. (Recommend: accept the handoff's recommendations — import-time, keep `sync_to_ledger`, keep existing grouping, no conditionals.)

5. **User-facing terminal:** RQ5 says the user-facing terminal in the dashboard is "questionable; can be revisited but is not a priority." Should it be removed in Phase 4, or left as-is? (Recommend: leave as-is for now; removing it is scope creep.)

---

## 6. What NOT to do yet

- **Do not build config dependency edges (Phase 3).** This is the genuinely new SourcePrep capability that needs design work in the CoDRAG repo. It's future scope. `KnowledgeGraph.impact_analysis()` remains the bridge until Phase 3.
- **Do not migrate `SelfKnowledge` store entirely.** RQ-E audit says "thinned" means "bootstrap functions kept, store deprecated after migration." The store stays active alongside SourcePrep + Haloysius during Phase 4. Full migration is post-Phase-4.
- **Do not implement multiple personalities.** Founder decision (RQ8): one personality, helper/assistant. Multi-personality is "seriously unimportant" for now.
- **Do not build the user-facing terminal.** Chat-first interface. Terminal is agent-facing only.
- **Do not cut `chat.py` before the new handler is working.** RQ-D scrutiny showed the new architecture covers ~20% of what `chat.py` does. The harvest must be complete before the cut.

---

## 7. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Haloysius framework generalization breaks H2/H3 | Low | High | Backward compatibility checklist (handoff §7) is the merge gate. Default trackers + default identity unchanged. |
| SourcePrep can't index config formats well | Medium | Medium | CoDRAG handoff §3 confirms format-agnostic chunking/embedding. Quality may be lower without config-aware chunker, but functional. |
| Cognitive tick produces generic thoughts | High | Medium | RQ-C scrutiny identified this. Fix: 4-line core change OR custom `ThoughtGenerator`. Must be addressed in Step 6. |
| `chat.py` harvest misses critical logic | Medium | High | RQ-D scrutiny corrected the audit. Use the corrected port/discard table, not the original. |
| Background scan thread destabilizes the app | Low | Medium | Use `queue.Queue` for thread-safe event passing. Scan runs on a timer, not on every turn. |
| Identity fallback fires silently | Medium | High | RQ-E audit E2: add startup check that verifies `human-identity.txt` exists and is not the default. |
| `PersonaMemoryStore` wrapper has type mismatches | Low | Medium | RQ-E audit E3 identified the exact mismatch. The wrapper adapter is straightforward. |

---

## 8. Success criteria for Phase 2+4

When this work is complete, the following should be true:

1. **The cognitive tick runs.** `advance_turn()` is called after each conversation turn. Beliefs are reinforced/challenged, worries updated, drives decay/activate, thoughts promoted.
2. **The self-model persists across sessions.** `PersonaCognition` is loaded from disk at session start and saved at session end. The "I AM" object survives between conversations.
3. **The response voice reflects the evolved self-model.** `PersonaCognition.to_prompt_block()` is injected into the response prompt. The agent speaks as the computer, with its current beliefs/worries/drives shaping the voice.
4. **SourcePrep is the retrieval backend.** `prep_search` results flow through the `RetrievalBackend` seam into the context assembler. The old dual-RAG is gone.
5. **System events trigger cognitive responses.** A disk failure produces a worry. A config change produces a notice. The cognitive tick processes these.
6. **`chat.py` is cut.** The monolithic route is gone. The state machine + context assembler + Haloysius wiring replace it.
7. **H2/H3 are unaffected.** The Haloysius framework generalization is backward-compatible. Default trackers, predicates, and identity are unchanged.

---

*End of recommended next steps. Awaiting founder approval and decisions on §5 before execution begins.*
