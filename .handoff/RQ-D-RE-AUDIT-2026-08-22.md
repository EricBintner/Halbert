# RQ-D Re-Audit: State Machine Internal Handlers vs chat.py

**Created:** 2026-08-22
**Task:** A2 from FINAL-PLAN-2026-08-22.md
**Corrects:** RQ-D-SCRUTINY-2026-08-22.md Error 1 — original audit compared against dead external handler classes. This re-audit compares against the actual internal handlers in `state_machine.py`.

---

## 1. What the state machine actually does

The `AgentStateMachine` (`agents/state_machine.py`, 797 lines) uses internal async generator methods dispatched via `_get_handler()` (L314-326):

| State | Handler | Lines | What it does |
|-------|---------|-------|--------------|
| PLANNING | `_handle_planning` | 332-428 | Calls `self.context.assemble()` → builds prompt via `self.prompts.build_planning_prompt()` → LLM chat → parse plan/tool calls → CRAG eval → route |
| SEARCHING | `_handle_searching` | 430-484 | Parallel `self.rag.search()` + `self.memory.recall()` → results to `ctx.retrieved_context` → OBSERVING |
| READING | `_handle_reading` | 486-537 | `self.tools.execute("read_file", ...)` → result to context → OBSERVING |
| EXECUTING | `_handle_executing` | 539-624 | `self.tools.execute(tool_name, ...)` → confirmation gate → OBSERVING |
| OBSERVING | `_handle_observing` | 626-665 | CRAG eval → route to RESPONDING (confidence high) or PLANNING (need more) |
| RESPONDING | `_handle_responding` | 667-719 | `self.prompts.build_response_prompt()` → LLM stream → `self.memory.store_interaction()` → IDLE |
| ERROR | `_handle_error` | 721-737 | Retry to PLANNING or give up to RESPONDING |
| AWAITING_CONFIRMATION | `_handle_awaiting_confirmation` | 739-749 | Blocking — waits for external `confirm_action()` |

---

## 2. Context injection: what the state machine does vs what chat.py does

### 2.1 Context assembly (PLANNING state)

**State machine** (L338-353):
```python
if self.context:
    assembled = await self.context.assemble(
        query=self.ctx.user_query,
        conversation=self.ctx.conversation_history,
        observations=self.ctx.observations,
        max_tokens=8000
    )
    context_content = assembled.content
```

**chat.py** (L1633-2443 in send_message):
- Manual context injection: 20+ keyword blocks, failure correlation, relationship correlation, @mention resolution
- `build_system_prompt_v2()` which calls ContextInjector (system context, project context, discovery summary, user prefs, RAG formatting)
- `get_system_identity()`, `get_custom_ai_rules()`, `get_self_knowledge_context()`, `get_telemetry_context()`, `get_docs_context()`, `get_memory_context()`

**Gap:** The state machine's `ContextAssembler` handles 5 sources (conversation, rag, memory, discovery, observations). chat.py + ContextInjector handle ~15+ sources. The gap list from RQ-D-SCRUTINY remains accurate.

### 2.2 Prompt building

**State machine** uses `AgentPromptBuilder` (instantiated at `agent.py` L95 with no args):
- `build_planning_prompt(query, context, plan)` — hardcoded identity/capabilities/constraints + context + plan
- `build_response_prompt(query, context, observations)` — hardcoded identity + context + observations
- NO system identity, NO project context, NO model-specific overrides, NO user preferences, NO RAG formatting with citations

**chat.py** uses `PromptBuilder.build_prompt()` (via `build_system_prompt_v2()`):
- Base prompt from XML templates
- Model-specific overrides (small model constraints, reasoning model thinking blocks)
- System context (XML via ContextInjector)
- User preferences (XML)
- Project context (HALBERT.md, agents.md)
- RAG results (XML with citations, dedup, CRAG metadata)
- Conversation history (tier-budgeted XML)

**Gap:** Confirmed from scrutiny — `AgentPromptBuilder` is significantly less capable than `PromptBuilder`. The fix is either wire state machine to `PromptBuilder` or extend `AgentPromptBuilder`.

### 2.3 LLM calls

**State machine** (L368-371, L692-707):
```python
response = await self.llm.chat(messages=[...], tools=tool_schemas)
# and
async for chunk in self.llm.stream(messages=[...]):
```

**LLM client** is `LLMClientAdapter` (`agent.py` L134-160+) which imports from chat.py:
```python
from .chat import (
    get_specialist_model, get_configured_model, get_ollama_endpoint,
    _score_query_complexity, call_llm_chat
)
```

**Confirmed from scrutiny:** The state machine has a circular dependency on chat.py for LLM calls. This must be broken before chat.py can be cut. The model routing functions (`_score_query_complexity`, `get_configured_model`, `get_specialist_model`, `get_ollama_endpoint`, `call_llm_chat`) need to be extracted into a shared `model/client.py` module.

### 2.4 Memory

**State machine** (L710-716):
```python
if self.memory:
    await self.memory.store_interaction(
        query=self.ctx.user_query,
        response=full_response,
        session_id=self.ctx.session_id
    )
```

Uses `MemoryServiceAdapter` which wraps `memory.store.get_memory_store()`. chat.py uses ChromaDB's `index.upsert_conversation()`. Different stores — confirmed from scrutiny.

### 2.5 Search

**State machine** (L448-452):
```python
if self.rag:
    tasks.append(("rag", self.rag.search(search_query, limit=5)))
if self.memory:
    tasks.append(("memory", self.memory.recall(search_query, limit=3)))
```

No web search. No docs search. No telemetry search. The external `SearchingHandler` class that had web search is dead code — confirmed.

### 2.6 Safety

**State machine:** No input safety validation. No output safety filtering. The `ToolSafetyFramework` handles tool execution safety, but not content safety. chat.py has `SafetyValidator.validate_input()` and `OutputFilter.filter_output()`.

### 2.7 Streaming

**State machine** (L692-707): Native async streaming via `self.llm.stream()`. Clean implementation. chat.py's streaming (L2931-3280) has a reasoning parser for thinking blocks (DeepSeek-R1) that the state machine lacks — but that's a model-specific concern, not context injection.

---

## 3. External handler classes — confirmed dead

The `agents/handlers/` directory contains:
- `planning.py` — `PlanningHandler` 
- `searching.py` — `SearchingHandler`
- (possibly others)

These are **never instantiated**. The state machine uses internal methods. The external classes reference `self.agent.context_assembler` and `self.agent.prompt_builder` — no property aliases exist for these names (L106-124 aliases `tool_executor`, `llm_client`, `rag_service`, `memory_service` only).

**Action:** Delete `agents/handlers/` directory. It's dead code that would crash with `AttributeError` if ever used.

---

## 4. Corrected gap analysis (state machine vs chat.py)

### What the state machine ALREADY does (no port needed):
- Context assembly from 5 sources (conversation, rag, memory, discovery, observations)
- CRAG evaluation at OBSERVING state
- Tool execution with safety gates (ToolSafetyFramework)
- Confirmation flow for high-risk actions
- Memory storage post-response (via MemoryServiceAdapter)
- Native streaming
- Plan parsing from LLM response
- Parallel search (rag + memory)

### What the state machine LACKS (must port before cutting chat.py):

| # | Gap | Source | Priority |
|---|-----|--------|----------|
| 0 | **LLMClientAdapter circular dep** | `agent.py` L145-148 imports from chat.py | BLOCKER |
| 1 | Self-knowledge / CRAG context | chat.py L521-568 | Critical |
| 2 | System identity | chat.py L1392-1476 | Critical |
| 3 | Custom AI rules | chat.py L1479-1521 | Critical |
| 4 | Failure correlation | chat.py L1710-1748 | Critical |
| 5 | Relationship correlation | chat.py L2211-2387 | Critical |
| 6 | Telemetry | chat.py L367-423 | Critical |
| 7 | Safety gates (input + output) | chat.py L1604-1618, L2909-2917 | Critical |
| 8 | @mention resolution | chat.py L2389-2443 | Critical |
| 9 | Project context (HALBERT.md) | ContextInjector L423-459 | Important |
| 10 | RAG formatting with citations | RAGFormatter in context.py | Important |
| 11 | Model-specific overrides | PromptBuilder._get_model_overrides | Important |
| 12 | User preferences | UserPreferences dataclass | Important |
| 13 | Docs (man pages/wiki) | chat.py L426-481 | Important |
| 14 | Discovery summary (critical issues) | ContextInjector L537-565 | Important |
| 15 | Unify memory stores | ChromaDB vs memory.store | Important |
| 16 | Wire to PromptBuilder (or extend AgentPromptBuilder) | prompts/builder.py | Important |

### What can be DISCARDED entirely:
- External handler classes (`agents/handlers/`) — dead code
- Keyword-based discovery injection (20+ blocks in chat.py) — replaced by semantic search
- Legacy fallback prompts — v2 prompt system exists
- ReAct loop — state machine replaces it
- Rule-based fallback responses — state machine + LLM handles it
- Model config helpers in chat.py — port to shared module, then discard from chat.py
- Memory CRUD endpoints — admin routes, not context injection
- Guardrails/policy/approval — execution-time safety, already in separate modules

---

## 5. Updated porting sequence

1. **Extract LLM client** — move `call_llm_chat`, `_score_query_complexity`, model config getters from chat.py to `model/client.py`. Update `LLMClientAdapter` to import from new location.
2. **Port critical gaps (1-8)** — add new sources/adapters to ContextAssembler + safety gates
3. **Wire PromptBuilder** — replace `AgentPromptBuilder` with `PromptBuilder` or extend it with missing capabilities
4. **Port important gaps (9-16)** — project context, RAG formatting, model overrides, user prefs, docs, discovery summary, memory unification
5. **Delete dead code** — `agents/handlers/`, duplicate conversation formatters
6. **Cut chat.py** — once all critical + important gaps are ported and the LLM dependency is broken

---

## 6. What changes from the original RQ-D audit

The original audit's port/discard/refactor verdicts are mostly correct — the scrutiny's corrections (Error 1-6) still apply. The main change from this re-audit is:

- **The comparison baseline is now correct.** We're comparing against the actual internal handlers, not dead code.
- **The state machine is simpler than the external handlers suggested.** It does less than the external `PlanningHandler`/`SearchingHandler` implied. The gap is wider, not narrower.
- **The LLMClientAdapter circular dependency is confirmed** as the #0 blocker. The state machine literally imports from chat.py at call time.
- **The streaming path is clean** in the state machine — no need to port the reasoning parser from chat.py's streaming endpoint (that's model-specific logic that belongs in the LLM client layer).
- **The state machine has no REFLECTING state** — the chat architecture validation doc (§8) specified a new REFLECTING state between OBSERVING and RESPONDING for the cognitive tick. This state doesn't exist yet and must be added for Phase D6.
