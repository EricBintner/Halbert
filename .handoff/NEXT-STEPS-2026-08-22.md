# Next Steps — Post-Research Synthesis

**Created:** 2026-08-22
**Status:** Recommendation document for founder review
**Context:** All five deep research questions (RQ-A through RQ-E) have been researched, scrutinized, and audited. The Haloysius framework generalization design has been approved by the founder. This document synthesizes the findings into a concrete action plan.

---

## 1. Where we are now

### 1.1 Research completed

| RQ | Status | Output document | Key finding | Scrutiny |
|----|--------|----------------|-------------|----------|
| RQ-A | Complete + audited | In DEEP-RESEARCH-QUESTIONS §RQ-A | WRAP SourcePrep behind existing RetrievalBackend seam; do not extend the protocol | 1 bug in draft adapter, 2 claims corrected. Recommendation survives. |
| RQ-B | Complete + scrutinized | In DEEP-RESEARCH-QUESTIONS §RQ-B + RQ-B-SCRUTINY | Consumer-side predicates feasible; ledger is schema-free; use medium renderer tier | 8 corrections (1 critical: _render_natural drops system subjects) |
| RQ-C | Complete + scrutinized | RQ-C-SYSTEM-EVENT-TRIGGERS-2026-08-22.md | Consumer-side mapping (Option D): system events map to existing worries/drives/emotions, not new trigger types | 7 corrections (1 critical: thought generation doesn't receive cognitive state content) |
| RQ-D | Complete + scrutinized | RQ-D-CHAT-AUDIT-2026-08-22.md + RQ-D-SCRUTINY | Port/discard/refactor table for chat.py; missed ContextInjector (third context system) and compared against dead handler classes | 6 material errors, 5 omissions. Audit needs partial re-do against state_machine.py internal handlers. |
| RQ-E | Complete + audited | In DEEP-RESEARCH-QUESTIONS §RQ-E | Three-layer self-model: SourcePrep (objective) + Haloysius (subjective) + Halbert (glue). Split existing SelfKnowledge across layers. | 4 corrections, 3 gaps. Architecture survives; framework generalization needed. |

### 1.2 Framework generalization approved

The founder approved the Haloysius framework generalization design
(documented in HALOYSIUS-FRAMEWORK-GENERALIZATION-2026-08-22.md). This is
a **prerequisite for Phase 4** -- without it, Halbert cannot register
system-state trackers, system predicates, or a machine identity.

### 1.3 Phase status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0 | DONE | Founder confirmations complete |
| Phase 1 | IN PROGRESS | Dead-code cut done on `phase1-cleanup` branch. Frontend rebuilt. Some items remain (collapse two chat systems). |
| Phase 2 | NOT STARTED | SourcePrep as awareness layer. No external gate. Can start after Phase 1. |
| Phase 3 | NOT STARTED | Config-physiology brain. Depends on Phase 2 + SourcePrep-side work. |
| Phase 4 | NOT STARTED | Haloysius mind wiring. Depends on framework generalization + Phase 1. |

---

## 2. Recommended next steps (ordered by dependency)

### Step 1: Finish Phase 1 -- collapse the two chat systems

**Why first:** Everything downstream depends on a single chat path. The
RQ-D audit and scrutiny revealed three parallel context-injection systems
(chat.py, ContextInjector, and the agent state machine's internal
assembler). This tangle must be resolved before any new architecture can
be wired in.

**What to do:**
1. Re-do the RQ-D comparison against `state_machine.py` internal handlers
   (L332-719), not the dead external handler classes. The RQ-D scrutiny
   explicitly flagged this as Error 1.
2. Incorporate the ContextInjector (`prompts/context.py`) into the
   port/discard/refactor table. The scrutiny flagged this as Error 2 --
   an entire third context-injection system was missed.
3. Decide: which of the three context systems becomes the canonical one?
   The research points toward the state machine's internal assembler as
   the survivor, with ContextInjector's RAG formatting, project context
   loading, and discovery summary ported into it.
4. Cut chat.py's context-injection blocks that are superseded.
5. Cut the dead external handler classes (`handlers/planning.py`,
   `handlers/searching.py`, etc.) -- they are never instantiated.

**Output:** A single chat path with one context assembler. The
port/discard/refactor table is the blueprint.

**Estimated effort:** Medium-large (the re-audit of state_machine.py is
the bulk; the actual cutting is mechanical once the table is corrected).

### Step 2: Implement the Haloysius framework generalization

**Why second:** This is the founder-approved prerequisite for Phase 4.
It can run in parallel with Step 1 (different repo, no shared files).

**What to do:** Follow the implementation handoff at
HALOYSIUS-FRAMEWORK-GENERALIZATION-2026-08-22.md. The sequencing is
already specified in §11 of that document:

1. Create `state_tracker.py` (protocol + enum)
2. Create `clothing_tracker.py` and `location_tracker.py` (adapters)
3. Modify `continuity.py` (tracker registry, replace hardcoded `_advance()`)
4. Modify `state_renderer.py` (predicate registration, prose templates)
5. Modify `identity.py` (`default_identity` parameter)
6. Write tests + run full suite (backward compat is the merge gate)

**Constraints:** No app names in Haloysius code. H2/H3 behavior unchanged.
MIT license. All documented in the handoff.

**Estimated effort:** Medium (4 small files to create, 3 to modify, all
backward-compatible).

### Step 3: Start Phase 2 -- SourcePrep as awareness layer

**Why third:** No external gate. Can start as soon as Phase 1's chat
collapse is done. This is the foundation for the self-model's objective
layer (RQ-E).

**What to do:**
1. Register a synthesized host-config tree (from `config/snapshot.py` +
   `config/parser.py`) as a SourcePrep project with custom globs.
2. Implement the `SourcePrepRetrievalAdapter` per RQ-A findings (WRAP
   approach -- implement `RetrievalBackend` protocol, call `prep_search`
   internally). Fix the bug identified in the RQ-A audit (the draft
   adapter's `format_context()` doesn't handle empty results).
3. Replace dual-RAG with `prep_search`.
4. Replace isolated-session memory with `prep_observe`/`prep_concepts`.

**Dependency:** RQ-A's audited adapter design. The audit found one bug
and two corrections but the WRAP recommendation survives.

**Estimated effort:** Medium (adapter is ~100 lines; the config-tree
registration and RAG replacement are the bulk).

### Step 4: Begin Phase 4 -- Haloysius mind wiring

**Why fourth:** Depends on Steps 2 and 3. The framework generalization
(Step 2) provides the tracker/predicate/identity seams. SourcePrep
(Step 3) provides the retrieval backend. Phase 4 wires them together.

**What to do (in order, based on research findings):**

**4a. Wire the seam implementations** (RQ-A):
- `ModelBackend` -> Ollama/local LLM adapter
- `RetrievalBackend` -> `SourcePrepRetrievalAdapter` (from Step 3)
- `GovernancePolicy` -> approval/autonomy/dry-run gate
- `AppSeam` -> routes, config tools, schema loader
- Register at startup via `register_app_seam()`

**4b. Register Halbert's state trackers** (RQ-B + framework generalization):
- `clear_state_trackers()` to remove clothing/location defaults
- Register `SystemHealthTracker` (disk, service, thermal predicates)
- Register `ConfigStateTracker` (config drift predicates)
- Use medium renderer tier (RQ-B scrutiny found `_render_natural` drops
  system subjects at the natural/large tier)
- Use a separate `db_path` for the ledger to avoid persona_id collision
  (RQ-B scrutiny correction C5)

**4c. Set the machine identity** (RQ-E + framework generalization):
- Pass `default_identity="machine"` to `IdentityPromptBuilder`
- Ship a `machine-identity.txt` prompt override (RQ-E audit E2: the
  filename is hardcoded as `human-identity.txt` -- either rename or
  add a `machine-identity.txt` lookup; the framework generalization
  handoff specifies the `default_identity` parameter approach)
- Bootstrap `PersonaCognition` with hardware realities, config beliefs,
  and system worries from `SelfKnowledge.bootstrap_from_profile()`

**4d. Build the SystemEventMapper** (RQ-C):
- Reads from `DiscoveryEngine` cache (NOT `scan_all()` at tick time --
  that blocks 30+ seconds per the RQ-C scrutiny)
- Background scan thread populates the cache on a 5-minute interval
- Called EVERY turn before `advance_turn()` to counteract worry decay
- Maps CRITICAL discoveries to worries (intensity 0.9, intrusion_rate
  configurable -- use 1.0 for deterministic-ish firing)
- Maps WARNING discoveries to worries (intensity 0.6) or emotions
- Uses `trigger_from_event("worry_trigger", ...)` as the designed
  integration point (RQ-C scrutiny finding 9.4)
- Deduplicates by discovery ID; intensifies existing worries by 0.03/
  turn (above the 0.02 decay rate); resolves cleared worries
- Uses `queue.Queue` for pending config events (thread safety, 9.6)
- All content in embodied first-person ("my disk /dev/sda1")

**4e. Fix the thought generation gap** (RQ-C scrutiny finding 9.1):
- **Preferred:** Propose the 4-line core change to `advance_turn()` in
  Haloysius to pass cognitive state to the generator. This benefits all
  consumers.
- **Fallback:** Implement `HalbertThoughtGenerator` subclass that
  extracts worry content from `trigger_data["intrusions"]` in
  `_describe_trigger()`.
- Without either fix, WORRY triggers produce generic thoughts ("I can't
  stop thinking about it...") with no system-specific content.

**4f. Build the memory store wrapper** (RQ-E audit finding E3):
- `advance_turn()`'s `memory_store_add` callback receives a dict, but
  `PersonaMemoryStore.smart_add()` expects a `PersonaMemory` dataclass
  with `MemoryType` enum
- Build a wrapper adapter that converts dict-to-dataclass and
  string-to-enum
- Wire `memory_store_add`/`memory_store_search` to the wrapper, which
  calls `PersonaMemoryStore`

**4g. Build the context assembler** (RQ-D + RQ-E audit finding E8):
- Orchestrates three layers into a single prompt:
  - SourcePrep concepts (`prep_search` + `prep_concepts`)
  - Haloysius state block (`render_state_block()`)
  - Halbert identity (`IdentityPromptBuilder` with machine identity)
- This is the replacement for chat.py's context-injection blocks
- Port the ContextInjector's RAG formatting (with citations), project
  context loading, and discovery summary from the RQ-D scrutiny findings
- The assembler lives in the state machine's internal handler path
  (not the dead external handler classes)

**4h. Wire the cognitive tick into the REFLECTING state** (chat architecture validation):
- Add REFLECTING and SENSING states to the agent FSM
- `StateContext` gets `persona_cognition`, `continuity_ledger`,
  `session_memory` fields
- SENSING: load PersonaCognition from disk, run SystemEventMapper,
  read continuity ledger
- REFLECTING: call `advance_turn()`, persist cognition to disk
- RESPONDING: inject `cognition.get_prompt_blocks()` into response prompt

**Estimated effort:** Large. This is the biggest phase. Sub-steps 4a-4c
can be done first (wiring the seams and registering trackers). Sub-steps
4d-4h are the integration work that makes the self-model actually tick.

### Step 5: Phase 3 -- config-physiology brain (the differentiator)

**Why last:** Depends on Phase 2 (SourcePrep index) and partially on
Phase 4 (the cognitive tick can worry about config drift once wired).
This is the product differentiator but not a prerequisite for the
self-model architecture.

**What to do:**
- Misconfig detection (config drift -> SourcePrep concepts assertion
  violation)
- Config deduplication (scattered settings consolidation)
- Live config model (queryable current state)
- Dry-run -> approval -> apply -> rollback pipeline
- This needs a founder product decision (RQ4 reframed): which capability
  is the MVP?

**Estimated effort:** Large (new build, not porting).

---

## 3. Parallelization opportunities

```
Timeline (not to scale):

Step 1: Finish Phase 1 (chat collapse)     [================]
Step 2: Haloysius framework generalization  [========]           <- parallel with Step 1
Step 3: Phase 2 (SourcePrep)                      [========]     <- after Step 1
Step 4: Phase 4 (Haloysius wiring)                       [========================]  <- after Steps 2+3
Step 5: Phase 3 (config brain)                                      [================]  <- after Step 3, partial dep on Step 4
```

- **Steps 1 and 2 can run in parallel** (different repos, no shared files)
- **Step 3 starts after Step 1** (needs single chat path)
- **Step 4 starts after Steps 2 and 3** (needs framework seams + retrieval backend)
- **Step 5 starts after Step 3** (needs SourcePrep index), with partial dependency on Step 4 (cognitive tick worry about config drift)

---

## 4. Open items requiring founder decisions

### 4.1 RQ4 -- MVP config capability (product decision)

The founder needs to pick which config-physiology capability is the MVP:
- Detect misconfigurations or drift
- Explain why a setting is set the way it is
- Deduplicate or consolidate scattered settings
- Propose changes under safe autonomy (dry-run -> approval -> apply -> rollback)
- Maintain a live, queryable model of the system's config state

This gates Phase 3 scope. Not a research item -- it's a product call.

### 4.2 RQ-C scrutiny -- core change to advance_turn() (Haloysius)

The RQ-C scrutiny found that `advance_turn()` doesn't pass cognitive
state to the thought generator, producing generic thoughts for WORRY
triggers. Two options:

- **Option A (preferred):** 4-line core change in Haloysius to pass
  `cognition.emotional_state.to_prompt_block()`, `cognition.drives.to_prompt_block()`,
  and `cognition.scene_context` to `generator.generate()`. Benefits all
  consumers.
- **Option B (fallback):** Halbert implements a `ThoughtGenerator`
  subclass. No core change, but Halbert-specific.

This is a Haloysius repo decision. If the founder wants to keep
Haloysius changes minimal for now, Option B is fine. If the founder
wants to fix the gap for all consumers, Option A is a small, clean
change.

### 4.3 RQ-D -- which context system is canonical

The RQ-D scrutiny found three parallel context-injection systems:
1. `chat.py` (the old chat route)
2. `ContextInjector` in `prompts/context.py`
3. The agent state machine's internal assembler

The founder needs to confirm: is the state machine's internal assembler
the canonical survivor, with ContextInjector's unique logic (RAG
formatting, project context, discovery summary) ported into it? Or is
there a reason to keep ContextInjector as a separate layer?

### 4.4 User-facing terminal (RQ5 residual)

The founder said the user-facing terminal in the dashboard is
"questionable; can be revisited but is not a priority." This should be
confirmed as either "keep for now" or "cut during Phase 1" to close
the open item.

---

## 5. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| RQ-D audit is partially wrong (compared against dead code) | Re-audit against state_machine.py internal handlers before cutting anything |
| Framework generalization breaks H2/H3 | Backward compatibility checklist in the handoff is the merge gate; run full test suite |
| SystemEventMapper blocks the conversation tick | Background scan thread is required for MVP, not Phase 2+ (RQ-C scrutiny 9.7) |
| Worries decay during rapid conversation | Mapper runs every turn, intensifies by 0.03 (above 0.02 decay rate) (RQ-C scrutiny 9.5) |
| Thought generation produces generic content | Fix advance_turn() or use HalbertThoughtGenerator (RQ-C scrutiny 9.1) |
| Memory store callback type mismatch | Build wrapper adapter for dict-to-PersonaMemory conversion (RQ-E audit E3) |
| Triple-write to prep_observe + PersonaMemoryStore | Resolve in Phase 4 wiring -- decide if promoted thoughts go to both stores or just one (RQ-E audit E10) |
| Config dependency edges don't exist in SourcePrep yet | Phase 3 depends on SourcePrep-side work (CoDRAG handoff); coordinate with that team |

---

## 6. Document map (what to read for each step)

| Step | Primary document | Scrutiny/audit | Code to read |
|------|-----------------|----------------|-------------|
| 1 (Phase 1 finish) | RQ-D-CHAT-AUDIT | RQ-D-SCRUTINY | `state_machine.py` L332-719, `prompts/context.py`, `chat.py` |
| 2 (Framework gen) | HALOYSIUS-FRAMEWORK-GENERALIZATION | FRAMEWORK-GENERALIZATION (design exploration) | Haloysius `continuity.py`, `state_renderer.py`, `identity.py` |
| 3 (Phase 2) | DEEP-RESEARCH-QUESTIONS §RQ-A | §RQ-A Audit (in same doc) | `seam.py`, `context/adapters.py`, SourcePrep MCP tools |
| 4a (Seam wiring) | DEEP-RESEARCH-QUESTIONS §RQ-A | §RQ-A Audit | `seam.py`, `adapters.py` |
| 4b (Trackers) | DEEP-RESEARCH-QUESTIONS §RQ-B | RQ-B-SCRUTINY | `continuity.py`, `state_renderer.py`, `discovery/engine.py` |
| 4c (Identity) | DEEP-RESEARCH-QUESTIONS §RQ-E | §RQ-E Audit (E2, E4) | `identity.py`, `realities.py`, `knowledge/self_knowledge.py` |
| 4d (Event mapper) | RQ-C-SYSTEM-EVENT-TRIGGERS | §9 Scrutiny (in same doc) | `thought_triggers.py`, `cognition_tick.py`, `discovery/scanners/` |
| 4e (Thought gen fix) | RQ-C-SYSTEM-EVENT-TRIGGERS §9.1 | (same) | `cognition_tick.py` L466-468, `thought_generator.py` |
| 4f (Memory wrapper) | DEEP-RESEARCH-QUESTIONS §RQ-E Audit E3 | (same) | `cognition_tick.py` L394-395, `memory_v2/store.py` |
| 4g (Context assembler) | RQ-D-CHAT-AUDIT + RQ-D-SCRUTINY | (both) | `prompts/context.py`, `state_machine.py`, `chat.py` |
| 4h (FSM wiring) | CHAT-ARCHITECTURE-VALIDATION §4-5 | (none needed) | `agents/state_machine.py`, `agents/states.py` |
| 5 (Phase 3) | FOUNDATIONAL-RESEARCH §RQ4 | (needs founder decision) | `config/drift.py`, SourcePrep `prep_concepts` assertions |

---

## 7. Summary

The research phase is complete. All five RQs have findings, and all
have been scrutinized against the actual code. The key corrections
from scrutiny are documented and don't change the fundamental
architecture -- they refine the implementation details.

The next action is **Step 1 (finish Phase 1)** and **Step 2 (Haloysius
framework generalization)** in parallel. These are the two unblocking
items: Step 1 gives us a single chat path to wire into; Step 2 gives
us the framework seams for Halbert to register its identity, trackers,
and predicates.

After those, Step 3 (SourcePrep integration) and Step 4 (Haloysius
wiring) are the main build phases, with Step 5 (config-physiology
brain) as the product differentiator that can follow.

Three founder decisions are needed before Phase 3 can be scoped:
1. RQ4: which config capability is the MVP?
2. RQ-C: approve the 4-line Haloysius core change (or use fallback)?
3. RQ-D: confirm the state machine assembler as the canonical context system?
