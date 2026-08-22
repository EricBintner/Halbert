# Halbert Chat Architecture — Validation & Composed-Loop Design

**Date:** 2026-08-22
**Origin:** A validation session (Devin, GLM-5.2) commissioned by the founder.
**Purpose:** Validate the chat-architecture plan implied by
`FOUNDATIONAL-RESEARCH-2026-08-21.md` and `GEMINI-Opinion.md` against the
actual code in both Halbert and Haloysius, and produce a concrete wiring
design that is not "cram this into one of the existing chats."
**Audience:** **The next AI session.** This is a design-validation artifact.
It documents what is right, what is lazy, and what the chat should actually
do. It is not an implementation plan — no scope has been chosen by the
founder. It is a corrective to two prior docs that conflated two different
state machines.

---

## 0. How to use this document

- **What's settled:** the diagnosis (§1–§3) is evidence-based, verified
  against the code in both `/Volumes/4TB-BAD/Halbert` and
  `/Volumes/4TB-BAD/Haloysius` this session. Treat it as ground truth.
- **What's proposed:** §4 (the composed-loop architecture) and §5 (the
  per-turn flow) are the payload — a concrete wiring design the founder
  can approve, reject, or revise before any code changes.
- **What's corrective:** §6 documents where the two prior docs are right
  and where they are lazy, so the next session does not inherit their
  blind spots.
- **Do not** treat this as an implementation plan. The founder has not
  chosen a scope (see RQ1 in the foundational research). This doc
  informs that choice; it does not make it.

---

## 1. The core confusion in both prior docs

Both `FOUNDATIONAL-RESEARCH-2026-08-21.md` and `GEMINI-Opinion.md`
conflate two different state machines. The conflation is what makes the
plan feel fuzzy and is what leads to "replace one chat with the other"
thinking.

| | Task-execution FSM | Cognitive tick |
|---|---|---|
| **What it is** | ReAct + CRAG loop: "what action do I take next?" | Per-turn self-model evolution: "how do my beliefs/worries/drives/emotions change based on what just happened?" |
| **Where it lives** | Halbert `halbert_core/halbert_core/agents/state_machine.py` | Haloysius `src/haloysius/persona/cognition_tick.py` (`advance_turn`) |
| **What it decides** | plan → search → execute → observe → respond | decay → detect → reinforce → promote → conflicts → persist |
| **Scope** | One request lifecycle (task scratchpad) | Cross-session (persistent self-model) |
| **State object** | `StateContext` (plan, tool_calls, observations) | `PersonaCognition` (beliefs, worries, drives, emotions, thoughts) |

These are **orthogonal axes**, not alternatives. The lazy approach —
implicit in both prior docs — is to treat them as competing replacements.
Gemini says "retire `chat.py` in favor of the agent stream" and "leverage
the cognitive tick" as if swapping one for the other. The foundational
research says "the tick is implemented but NOT wired to any chat path" —
which is the real gap — but then frames the solution as "adopt Haloysius"
rather than "compose the two machines."

**The correct architecture is composition, not replacement:**
- The task FSM drives the loop (what to do next)
- The cognitive tick runs *at specific points in that loop* to evolve the
  self-model
- The self-model feeds back into context assembly for the next iteration

---

## 2. What's wrong with the current Halbert state machine

Verified against `halbert_core/halbert_core/agents/state_machine.py`,
`agents/states.py`, `agents/handlers/`, and `dashboard/routes/agent.py`
this session.

### 2.1 The states are generic ReAct, not "I AM the computer"

Current states (`agents/states.py:14-24`):

```
IDLE → PLANNING → SEARCHING/READING/EXECUTING → OBSERVING → RESPONDING
```

This is a textbook agent loop from any LangChain tutorial. Nothing about
it reflects the founding vision (Self-Identification, Biography,
Configuration as Physiology — see `documentation/design/philosophy.md`).
There is no state where the agent *reflects on what it learned about
itself*, no state where it *consolidates a system event into a
first-person memory*, no state where it *reasons about config physiology*.

### 2.2 StateContext is task-scratchpad, not self-model

`StateContext` (`agents/states.py:76-175`) carries:
`plan`, `tool_calls`, `observations`, `retrieved_context`, `confidence`,
`crag_action`, `loop_count`, `state_history`.

It does **not** carry:
- `PersonaCognition` (the evolving self-model)
- the continuity ledger
- any persistent identity

Each request creates a fresh `StateContext`. The "I AM" identity is a
prompt string injected by `AgentPromptBuilder`, not an evolving model
that persists across sessions. This is the deepest gap: **the task FSM's
scratchpad has no place for the self-model, so wiring the cognitive tick
is structurally impossible without changing `StateContext`.**

### 2.3 The "new" agent path secretly depends on the "old" chat path

`LLMClientAdapter` (`dashboard/routes/agent.py:134-148`) imports directly
from `chat.py`:

```python
from .chat import (
    get_specialist_model, get_configured_model, get_ollama_endpoint,
    _score_query_complexity, call_llm_chat
)
```

So the agent path that's supposed to replace `chat.py` still calls into
it for every LLM request. **Killing `chat.py` breaks the agent path.**
Gemini's "retire `chat.py`" recommendation, taken literally, breaks the
live chat before the replacement is built.

### 2.4 The agent path is thinner than the chat path it replaces

Per the foundational research (§3): the old `chat.py` (4,240 lines) has
rich context-injection logic (telemetry, self-knowledge, keyword-based
discovery). The new `agent.py` (716 lines) "does not replicate the old
path's context-injection logic." Switching to `agent.py` *loses
capability*. The context richness must be ported into the new path, not
discarded.

### 2.5 No cognitive layer at all

The `get_agent()` factory (`dashboard/routes/agent.py:104-114`) wires:
`llm_client`, `tool_executor`, `crag_evaluator`, `context_assembler`,
`prompt_builder`, `rag_service`, `memory_service`.

Zero persona cognition. Zero continuity. Zero Haloysius. The agent has
hands and eyes but no mind.

---

## 3. What Haloysius actually provides (verified this session)

Read against `/Volumes/4TB-BAD/Haloysius/` — the repo exists and is
further along than the foundational research implies.

### 3.1 The seam Protocols already exist (WP-13 discrepancy)

The foundational research (§7b) says: *"the full
`ModelBackend` / `RetrievalBackend` / `GovernancePolicy` / app-seam
Protocols are NOT yet defined (WP-13, the architectural keystone, not
started)."*

**This is stale.** `src/haloysius/seam.py` (169 lines) defines all four
Protocols as `runtime_checkable` Protocol classes, plus a registry
(`register_app_seam` / `get_app_seam`). The `ImageBackend` +
`ImagePromptSpec` precursor lives in `persona/image_prompt_spec.py`. The
seam contract Halbert would build against **exists today.** This needs
reconciliation in the next session — either the foundational research is
out of date, or WP-13 was completed after the research was written.

### 3.2 The cognitive tick is implemented and self-contained

`src/haloysius/persona/cognition_tick.py` implements `advance_turn()` —
the six-step per-turn cognitive evolution (decay → detect → reinforce →
promote → conflicts → persist). It operates on a `PersonaCognition`
object (four layers: Realities, Context, Prism [BeliefState +
ValueHierarchy], Experience [EmotionalStateV2, DriveState, WorryState,
ThoughtState]). Each layer has `to_prompt_block()` and `to_dict()` for
round-trip persistence. **This is the cross-session "I AM" object.**

### 3.3 Continuity is a write-before-read ledger

`src/haloysius/context/continuity.py` implements a write-before-read
ledger: `advance_from_user_message` → `render_state_block` →
`advance_from_response`. A change the user states this turn appears in
*this* turn's prompt. The state ledger lives in
`memory_v2/temporal_graph.py`; the `AdaptiveStateRenderer` renders ledger
triples into a prompt block.

Current predicates: `wearing, at_location, feeling, occupation,
time_of_day, weather, atmosphere, lighting, relationship_to_user,
current_activity`. **Notably absent for Halbert's use case:** system-state
predicates (`disk_health, service_status, config_state, thermal_state`).
The ledger is extensible but Halbert would need to define its own
predicates or extend the core's.

### 3.4 What Haloysius deliberately does NOT provide

Per `CHARTER.md` and `README.md`: no routes, no Flask/FastAPI, no `api/`
imports, no frontend, no model provider, no corpus, no product name. The
**conversation-flow FSM is not in the core** — by design. The core ships
the cognitive tick *function* and the autonomous-thought tick *function*;
the **driver loop that calls them on a schedule is the consumer's job.**
This is correct: the loop boundary (server tick, SSE heartbeat, client
poll) and the task states (what to do next) are product-shaped decisions
that belong in Halbert, not in the agnostic core.

The closest thing to a state machine inside the core is
`conversation/state.py`'s `ConversationPhase` enum (GREETING → WARMING_UP
→ ENGAGED → DEEP/PLAYFUL/SUPPORTIVE → WINDING_DOWN → FAREWELL). Even that
is deliberately minimal — a phase *label* derived from signals, not a
transition-gated FSM with guarded actions. The actual state machines in
the tree (`clothing_state_machine.py`, `location_state_machine.py`) are
domain-specific continuity trackers for image prompts, not conversation
control.

---

## 4. The composed-loop architecture

### 4.1 Diagram

```
User message
    |
    v
+-----------------------------------------------------+
|  Halbert Agent Driver (the task FSM, rebuilt)       |
|                                                     |
|  IDLE -> SENSING -> PLANNING -> ACTING -> OBSERVING |
|              ^                          |           |
|              |          REFLECTING <----+           |
|              |              |                      |
|              |          RESPONDING -> IDLE          |
|              +--------------------------------+      |
|                                                     |
|  Each state calls through Haloysius seam Protocols  |
+------------------+----------------------------------+
                   |
         +---------+----------+
         v                    v
+-----------------+  +--------------------------------+
|  Haloysius Core |  |  Halbert Seam Implementations  |
|  (the mind)     |  |  (the body)                    |
|                 |  |                                |
|  PersonaCognition|  |  ModelBackend -> Ollama/local |
|  advance_turn() |  |  RetrievalBackend -> SourcePrep|
|  Continuity     |  |  GovernancePolicy -> approval/ |
|  Memory_v2      |  |    autonomy/dry-run            |
|  Conversation   |  |  AppSeam -> routes, config tools|
+-----------------+  +--------------------------------+
```

### 4.2 The key change: add REFLECTING and SENSING states

The current states are purely task-oriented. The rebuilt states should
reflect the vision:

| State | What happens | Haloysius involvement |
|---|---|---|
| **IDLE** | Waiting for user | Autonomous cognition engine can tick (background thoughts, worry intrusion about system state) |
| **SENSING** (NEW) | Gather system state (replaces generic SEARCHING for self-introspection queries) | Continuity ledger reads current system predicates; PersonaCognition's Realities layer loads |
| **PLANNING** | Decide what to do | PersonaCognition's Prism (beliefs, values) + Experience (drives, worries) inform the plan — e.g., a worry about `/dev/sda1` health prioritizes disk checks |
| **ACTING** | Execute tools (search, read, write_config) | GovernancePolicy checks blast-radius before any config write; AWAITING_CONFIRMATION for destructive ops |
| **OBSERVING** | Evaluate tool results | CRAG confidence scoring (existing) |
| **REFLECTING** (NEW) | Run `advance_turn()` — the cognitive tick evolves the self-model based on what was observed | **This is the wiring point.** Beliefs reinforced/challenged, worries updated, drives decay/activate, thoughts promoted |
| **RESPONDING** | Generate response with persona voice | PersonaCognition's `to_prompt_block()` injected into the response prompt; continuity ledger updated |

### 4.3 Updated transition table

```
IDLE:                   [SENSING]
SENSING:                [PLANNING, RESPONDING, ERROR]
PLANNING:               [SEARCHING, READING, EXECUTING, RESPONDING, ERROR]
SEARCHING:              [OBSERVING, ERROR]
READING:                [OBSERVING, ERROR]
EXECUTING:              [OBSERVING, AWAITING_CONFIRMATION, ERROR]
AWAITING_CONFIRMATION:  [EXECUTING, PLANNING]
OBSERVING:              [PLANNING, REFLECTING, ERROR]    # was: [PLANNING, RESPONDING, ERROR]
REFLECTING:             [RESPONDING, PLANNING, ERROR]    # NEW
RESPONDING:             [IDLE]
ERROR:                  [PLANNING, RESPONDING, IDLE]
```

The two changes: OBSERVING now transitions to REFLECTING (instead of
directly to RESPONDING), and REFLECTING transitions to RESPONDING (the
normal path) or back to PLANNING (if reflection surfaces a new concern
that warrants another action loop).

### 4.4 StateContext must carry the self-model

This is the structural change that makes everything else possible. Add
to `StateContext` (`agents/states.py`):

```python
# Haloysius cognitive state (persistent across sessions, loaded at SENSING)
persona_cognition: Optional["PersonaCognition"] = None
continuity_ledger: Optional["ContinuityLedger"] = None
session_memory: Optional["MemoryStore"] = None
```

Without this, `advance_turn()` has nothing to evolve. The self-model is
loaded from disk at SENSING (deserialized via `PersonaCognition.from_dict`
or equivalent), evolved at REFLECTING, and persisted at RESPONDING. This
is what makes the "I AM" identity *evolving* rather than *static prompt
string*.

---

## 5. The per-turn flow, concretely

1. **User sends message** → `agent.py` route receives it, creates/retrieves
   session.
2. **Load persistent self-model**: `PersonaCognition` loaded from disk
   (serialized via `to_dict()`), not created fresh. This is the
   cross-session "I AM" that survives between conversations.
3. **IDLE → SENSING**: Continuity ledger's `advance_from_user_message()`
   runs — the user's message updates the ledger *before* this turn's
   prompt (the write-before-read pattern from `context/continuity.py`).
   System-state predicates are read (disk health, service status, etc.).
4. **SENSING → PLANNING**: Context assembly pulls from three sources:
   - **SourcePrep** (via `RetrievalBackend`): host awareness — config
     graph, system state, past observations/concepts.
   - **Haloysius continuity**: what's true about the system right now
     (ledger predicates).
   - **Haloysius PersonaCognition**: beliefs/worries/drives about the
     system (the self-model's current state).
5. **PLANNING → ACTING**: ReAct loop with CRAG. Tool calls go through
   `GovernancePolicy` (blast-radius check, dry-run, approval gate). For
   config writes: `AWAITING_CONFIRMATION` with diff preview.
6. **ACTING → OBSERVING**: CRAG evaluates confidence. If
   `INCORRECT`/`AMBIGUOUS`, loop back to PLANNING.
7. **OBSERVING → REFLECTING** (the new state): `advance_turn()` runs the
   six-step cognitive tick:
   - **Decay**: emotions/drives/worries decay toward baseline.
   - **Detect**: trigger detection — did this observation challenge a
     belief? Activate a drive? Trigger a worry?
   - **Reinforce**: beliefs supported/challenged by the observation get
     evidence.
   - **Promote**: thoughts that crossed threshold get promoted to the
     thought stream.
   - **Conflicts**: belief conflicts detected.
   - **Persist**: updated `PersonaCognition` saved to disk.
8. **REFLECTING → RESPONDING**: Response generated with
   `PersonaCognition.to_prompt_block()` injected — the agent speaks *as*
   the computer, with its current beliefs/worries/drives shaping the
   voice. Not a prompt string; an evolved self-model.
9. **RESPONDING → IDLE**: Continuity ledger's `advance_from_response()`
   runs. `memory_v2` persists the turn. SourcePrep `prep_observe` records
   what happened ("I changed wg0 MTU to 1420 because..."). The self-model
   is now updated for the next session.

---

## 6. What dies, what stays

| Current Halbert code | Verdict | Why |
|---|---|---|
| `dashboard/routes/chat.py` (4,240 lines) | **Replace** — but harvest its context-injection logic first | The context richness (telemetry injection, self-knowledge, keyword discovery) needs to be ported into the new context assembler, not lost. The route itself dies. |
| `dashboard/routes/agent.py` route | **Keep and rebuild** | This is the right path (state machine + SSE), but it needs the new states, the Haloysius wiring, and to stop importing from `chat.py`. |
| `agents/state_machine.py` | **Keep and extend** | The ReAct+CRAG transition logic is sound. Add REFLECTING and SENSING states. Add `PersonaCognition` to `StateContext`. |
| `agents/states.py` | **Extend** | Add `REFLECTING`, `SENSING` to the enum. Add `persona_cognition`, `continuity_ledger`, `session_memory` fields to `StateContext`. |
| `agents/handlers/*` | **Keep** | The per-state handler pattern is good. Add `sensing.py` and `reflecting.py` handlers. |
| `runtime/langgraph_engine.py` | **Cut** | Dead, never imported (foundational research §3). |
| `rag/pipeline.py` (deprecated) | **Cut** | Replaced by SourcePrep `RetrievalBackend`. |
| `rag/document_indexer.py` + RAPTOR + GraphRAG | **Replace with SourcePrep** | Per RQ2 — if SourcePrep can index the OS. Needs validation. |
| `knowledge/self_knowledge.py` + graph + reflection | **Fuse into Haloysius PersonaCognition + SourcePrep concepts** | The self-knowledge layer becomes the PersonaCognition self-model, backed by SourcePrep's concepts/observations. |
| `config/*` (snapshot, drift, watcher, parser, indexer) | **Keep** — these are the "body" primitives | They feed SourcePrep's index and the continuity ledger. |
| `tools/write_config.py` + `approval/` + `autonomy/` + `policy/` | **Keep and wire** | These become the `GovernancePolicy` implementation. |
| `LLMClientAdapter` (imports from `chat.py`) | **Replace** — direct Ollama/API client via `ModelBackend` | Break the dependency on the dead path. |

---

## 7. Where the two prior docs are right and where they are lazy

### Right

- **The three-way mapping** (Haloysius = mind, SourcePrep = awareness,
  Halbert = body/action) is correct and is the right framing.
- **The diagnosis** of dual-chat, dual-RAG, dead scaffolding is accurate
  and verified against the code.
- **The "config-organization action layer"** as Halbert's unique
  contribution is the right framing (RQ4 in the foundational research).
- **The seam Protocol approach** (`ModelBackend`, `RetrievalBackend`,
  `GovernancePolicy`) is the right contract — and it already exists in
  `haloysius/seam.py`.
- **The "delicate, not a 17-page dashboard"** reframing is correct.

### Lazy / needs pushback

1. **"Retire `chat.py` in favor of the agent stream" (Gemini)** — lazy
   because the agent stream is *thinner* and *secretly imports from
   `chat.py`* (§2.3, §2.4). You can't just switch paths; you have to build
   a new path that has the state machine of `agent.py` + the context
   richness of `chat.py` + the cognitive layer of Haloysius. Neither doc
   acknowledges this.

2. **"Leverage the cognitive tick" (both docs)** — lazy because neither
   doc says *where in the loop the tick runs*. "Adopt Haloysius" is not a
   wiring plan. The tick needs a specific state (REFLECTING) at a
   specific point (after OBSERVING, before RESPONDING) in the task FSM.
   Without that, the tick is still orphaned — just orphaned inside a
   different route. §4 and §5 of this doc close that gap.

3. **"The cognitive tick is the heart" (foundational research §7b)** —
   misleading. The tick is the *self-model evolution*, not the *loop
   driver*. The loop driver is the task FSM. Conflating them leads to
   "replace the state machine with the tick," which doesn't work because
   the tick doesn't decide what action to take next. The two machines
   compose; they don't compete.

4. **Neither doc addresses that `StateContext` has no self-model (§2.2).**
   This is the deepest gap. The task FSM's scratchpad carries plan steps
   and tool calls but not beliefs, worries, or drives. Without adding
   `PersonaCognition` to `StateContext`, wiring the tick is structurally
   impossible — there's nothing for it to evolve.

5. **RQ7 (is Halbert the sysadmin near-peer consumer?) is treated as
   open, but the code confirms it.** The `agent.py` wiring (FastAPI,
   RAPTOR+GraphRAG, governance stack, sysadmin scope) matches the WP-22
   description exactly. The foundational research should close this RQ
   and move to "co-design the seam" (RQ3) with confidence.

6. **The foundational research says WP-13 (seam definition) is "not
   started," but `haloysius/seam.py` defines all four Protocols (§3.1).**
   Either the research is stale or WP-13 was completed after the research
   was written. The next session should reconcile this — it affects
   whether Halbert is building against a foreign core or co-designing one
   it's already a consumer of.

---

## 8. Sequencing — what to do first (if the founder approves)

The sequencing tension the foundational research flags (SourcePrep ready
now, Haloysius gated) is real but smaller than it looks. The Haloysius
seam Protocols already exist (§3.1). What's missing is Halbert-side
wiring, not Haloysius-side work.

### Smallest first step that proves the thesis

Wire `advance_turn()` into the existing `agent.py` path at the
OBSERVING → RESPONDING transition, with a stub `PersonaCognition` that
persists across sessions. Don't rebuild the states yet — just prove the
tick runs and the self-model evolves. Then iterate on the states.

Concretely:
1. Add `persona_cognition` field to `StateContext` (load from disk at
   session start, save at session end).
2. Add a `reflecting.py` handler that calls `haloysius.persona.cognition_tick.advance_turn()`.
3. Insert REFLECTING between OBSERVING and RESPONDING in the transition
   table.
4. Inject `PersonaCognition.to_prompt_block()` into the response prompt
   at RESPONDING.
5. Implement a minimal `ModelBackend` (Ollama, direct — no `chat.py`
   import) so the LLM path is clean.

This proves: the tick runs, the self-model persists across sessions, the
response voice reflects the evolved self-model. It does not yet prove:
SourcePrep integration, config physiology, the full state redesign.

### After the thesis is proven

- Add SENSING state and wire SourcePrep as `RetrievalBackend` (RQ2).
- Port context-injection logic from `chat.py` into the new context
  assembler, then cut `chat.py`.
- Implement `GovernancePolicy` from the existing `approval/` +
  `autonomy/` + `policy/` code.
- Build the config-organization action layer (RQ4) — the one piece
  neither sibling has.

---

## 9. Open questions for the next session

These extend the foundational research's RQs with what this validation
surfaced:

- **RQ3-update:** The seam Protocols exist in `haloysius/seam.py`. Does
  Halbert build against them now, or does it want to influence their
  shape first? Specifically: does `RetrievalBackend` need to change to
  accommodate SourcePrep's `prep_search` / `prep_impact` / `prep_concepts`
  primitives, or does Halbert wrap SourcePrep behind the existing
  `search` / `format_context` interface?
- **RQ-ledger:** The continuity ledger's current predicates
  (`wearing, at_location, feeling, ...`) are persona-chat-shaped. Halbert
  needs system-state predicates (`disk_health, service_status,
  config_state, thermal_state`). Does Halbert define its own predicates
  (consumer-side, behind the seam) or does it propose extending the
  core's predicate set? This is a WP-8-adjacent question.
- **RQ-tick-trigger:** The cognitive tick's trigger detection
  (`thought_triggers.py`) is persona-emotion-shaped. How do system events
  map onto triggers? (e.g., a failing drive → `worries_about /dev/sda1`).
  Is this a Halbert-side trigger extension or a core extension?
- **RQ-context-port:** Exactly which context-injection logic from
  `chat.py` (4,240 lines) is worth porting into the new context
  assembler, and what is discarded? This needs a line-by-line audit
  before `chat.py` is cut.

---

## 10. References

- `FOUNDATIONAL-RESEARCH-2026-08-21.md` (this directory) — the diagnosis
  and research questions this doc validates and corrects.
- `GEMINI-Opinion.md` (repo root) — the strategic blueprint this doc
  validates and corrects.
- `documentation/design/philosophy.md` — the founding vision (read in
  full per the foundational research's recommendation).
- `halbert_core/halbert_core/agents/state_machine.py` — the current task
  FSM.
- `halbert_core/halbert_core/agents/states.py` — `AgentState` enum and
  `StateContext` (the scratchpad that needs a self-model field).
- `halbert_core/halbert_core/dashboard/routes/agent.py` — the live agent
  route (the path to rebuild, not the path to replace).
- `halbert_core/halbert_core/dashboard/routes/chat.py` — the dead-but-
  rich legacy route (harvest context logic, then cut).
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/seam.py` — the seam Protocols
  (exist today, despite the foundational research saying WP-13 not
  started).
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/cognition_tick.py` —
  `advance_turn()`, the cognitive tick.
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/context/continuity.py` — the
  write-before-read continuity ledger.
- `/Volumes/4TB-BAD/Haloysius/CHARTER.md` — the agnostic-core invariant
  (why the conversation FSM is not in the core, by design).

---

## 11. Phase 1 reconciliation (2026-08-22, after this doc was written)

**This section was added after a Phase 1 cleanup session (Cascade) that
executed some of §6's recommendations and corrected a few items.** The
prior sections (§1–§10) are unchanged — they remain the design payload.
This section reconciles the doc against what actually happened.

### What §6 recommended that is now DONE

| §6 row | Status | What happened |
|---|---|---|
| `runtime/langgraph_engine.py` → Cut | **DONE** | Deleted in commit `202c900` (branch `phase1-cleanup`). CLI import in `Halbert/main.py` removed; `cmd_runtime_tick` now uses the fallback engine directly. |
| `rag/pipeline.py` (deprecated) → Cut | **PARTIALLY DONE** | The deprecated RAGPipeline was removed from the *chat streaming hot path* (`chat.py`'s `get_rag_pipeline` / `get_rag_context` / `check_rag_freshness` deleted; stream endpoint now uses `get_docs_context` / ChromaDB). The `rag/pipeline.py` *module itself* is kept — still used by CLI eval tooling (`main.py:2026`, `rag/evaluation.py`, `rag/index_builder.py`). It should still be cut from the chat path entirely when SourcePrep replaces it, but it is no longer in the hot path. |
| `dashboard/routes/chat.py` → Replace (harvest context logic first) | **NOT STARTED** — but the dual-RAG problem inside it is fixed | The deprecated BM25 pipeline was only on the `/send/stream` endpoint; the `/send` endpoint already used ChromaDB. Phase 1 unified both to ChromaDB. The route itself (4,240 lines → now ~4,090) still needs to be harvested and replaced per §6. |

### What §6 did NOT mention that is now DONE

- **Frontend `src/lib/` reconstructed.** The four missing modules (`utils.ts`, `api.ts`, `tauri.ts`, `generationQueue.ts`) were never committed anywhere — not in any branch or stash. They were rebuilt from consumer call sites + backend route shapes. `tsc && vite build` passes. **Both chat UIs (old SidePanel/ChatPanel AND the Agent page) now compile and would render.** This means §2.4's "the agent path is thinner" is still true, but the *frontend* for both paths is now alive — the choice of which to invest in is a real choice, not a default.
- **`platform/` bridge + `halbert-linux`/`halbert-mac` adapters cut.** Zero live callers (only tests). Not in §6 because it's not chat-related, but it removes a dead abstraction layer that was confusing the architecture picture.
- **Deprecated RAGPipeline removed from chat stream path.** §4 of the foundational research flagged "dual-RAG" but didn't note the split was *per-endpoint* (`/send` used ChromaDB, `/send/stream` used BM25). Now unified to ChromaDB on both.

### New finding not in §1–§10

- **`saveWhy` has no backend.** The WhyBrain/WhyOverlay UI (live in `DiscoveryCard.tsx` and `GPU.tsx`) calls `api.saveWhy()` → `POST /api/why`, an endpoint that does not exist anywhere in the backend. Dead feature end-to-end. This is a natural fit for SourcePrep's `prep_concepts` (persist "why" annotations as concepts) or Haloysius's continuity ledger (system-state predicates with human-authored rationale). The next session should decide which.

### Corrections to §6 items

- **`rag/pipeline.py` → Cut**: The doc says "Replaced by SourcePrep `RetrievalBackend`." This is still the target, but Phase 1 proved the pipeline can't be fully cut yet — the CLI eval tooling (`main.py cmd_rag_eval`, `rag/evaluation.py`, `rag/index_builder.py`) still imports it. The cut must be staged: (1) remove from chat paths (DONE), (2) port eval tooling to SourcePrep or ChromaDB directly, (3) then delete the module.
- **`runtime/langgraph_engine.py` → Cut**: Done, but note that `runtime/engine.py` + `runtime/graph.py` + `runtime/state.py` were KEPT (the foundational research called graph/state "unused scaffolds" — wrong; `engine.py` imports both, and the CLI uses `engine.py`). These are not dead; they're the fallback runtime the CLI uses today.

### What remains from §8 (sequencing)

§8's "smallest first step" is unchanged and still the right call:

1. Add `persona_cognition` field to `StateContext` (load/save across sessions).
2. Add `reflecting.py` handler calling `advance_turn()`.
3. Insert REFLECTING between OBSERVING and RESPONDING.
4. Inject `PersonaCognition.to_prompt_block()` into the response prompt.
5. Implement minimal `ModelBackend` (Ollama direct — no `chat.py` import).

**What Phase 1 added to this:** step 5 is now slightly easier because the deprecated RAG pipeline is no longer entangled with the chat path. The `LLMClientAdapter` in `agent.py` still imports from `chat.py` (§2.3 — unchanged), but the imports are now to a cleaner `chat.py` (no BM25 pipeline code).

### Branch state

- Branch `phase1-cleanup` (commit `202c900`) contains all Phase 1 work.
- Not yet merged to `main`. Merge after backend boot verification on the
  Ubuntu host (no fastapi/chromadb env on this Mac).
- The `frontend/src/lib/` reconstruction is the highest-risk change —
  the API client was rebuilt from call-site inference, not from the
  original source. Runtime testing may surface signature mismatches
  that `tsc` couldn't catch (e.g., a backend endpoint returning a
  different shape than the reconstructed TypeScript interface expects).

### One-line summary for the next AI

> Phase 1 made both chat UIs compile and removed the deprecated RAG from
> the hot path. The composed-loop architecture (§4–§5) is still the
> design. The smallest next step (§8) is wiring `advance_turn()` into
> the agent state machine via a new REFLECTING state — and that work is
> unblocked by Phase 1.
