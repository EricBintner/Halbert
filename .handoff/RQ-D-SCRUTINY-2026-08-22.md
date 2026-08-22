# RQ-D Audit Scrutiny — Errors and Omissions Found

**Created:** 2026-08-22
**Scrutinized document:** `RQ-D-CHAT-AUDIT-2026-08-22.md`
**Method:** Reverse-engineered the audit by reading the files the audit referenced but didn't fully examine, and traced the actual wiring of the new architecture.

---

## Summary

The original audit has **6 material errors** and **5 significant omissions** that change the port/discard/refactor recommendations and the proposed architecture. The most serious: the audit compared chat.py against **dead code** (external handler classes that are never instantiated), missed an **entire third context-injection system** (`ContextInjector` in `prompts/context.py`), and incorrectly categorized chat.py's model routing functions as DISCARD when they are actively used by the new architecture via `LLMClientAdapter`.

---

## Material Errors

### Error 1: Compared against dead code (external handler classes)

**What the audit said:** "The new architecture's PlanningHandler calls `context_assembler.assemble()`" and compared chat.py against `agents/handlers/planning.py` and `agents/handlers/searching.py`.

**What's actually true:** The `AgentStateMachine` uses its own **internal handler methods** (`_handle_planning`, `_handle_searching`, etc. at `state_machine.py` L332, L430, L667) dispatched via `_get_handler()` (L314-326). The external `PlanningHandler`/`SearchingHandler` classes in `handlers/` are **never instantiated**. They reference `self.agent.context_assembler` and `self.agent.prompt_builder`, but the state machine stores these as `self.context` and `self.prompts` (L88-89) with **no property aliases** for those names. The existing property aliases (L106-124) cover `tool_executor`, `llm_client`, `rag_service`, `memory_service` — but NOT `context_assembler` or `prompt_builder`.

**Impact:** The audit's comparison against `handlers/planning.py` and `handlers/searching.py` is misleading. The actual new architecture code is in `state_machine.py`'s internal handlers, which I didn't read during the original audit. The internal handlers are simpler and use different patterns than the external handler classes.

**Fix:** Re-do the comparison against `state_machine.py` L332-719 (the internal handlers). The external handler classes should be noted as dead code to be cleaned up.

### Error 2: Missed the ContextInjector — a third context-injection system

**What the audit said:** Treated `build_system_prompt_v2()` (chat.py L105-153) as a simple REFACTOR target and noted "the ContextInjector's `get_system_context()` and `format_system_context()` overlap with what the assembler does — these should merge."

**What's actually true:** `prompts/context.py` contains a full `ContextInjector` class (L230-565) that is a **parallel context-injection system** with significant logic the audit never examined:

- `get_system_context()` (L247-277) — gathers OS info, hostname, username, shell, package manager, init system, enriches from discovery engine. **Second system identity implementation** overlapping with chat.py's `get_system_identity()`.
- `format_system_context()` (L279-326) — formats as XML for prompt injection.
- `format_user_preferences()` (L328-352) — formats user prefs as XML.
- `format_conversation_history()` (L354-421) — formats conversation with tier-specific token budgets. **Third conversation formatting implementation** (alongside assembler's `_format_conversation()` and chat.py's manual concatenation).
- `load_project_context()` (L423-459) — loads HALBERT.md, agents.md, GEMINI.md, claude.md. **Completely missed in the audit.**
- `get_discovery_summary()` (L537-565) — XML-formatted discovery summary with critical issues. **Third discovery context implementation.**
- `RAGFormatter` class (L32-194) — formats RAG results as XML with citations, confidence thresholds, deduplication, and CRAG metadata. **No equivalent in the assembler.**

**Impact:** The audit's gap analysis is incomplete. The ContextInjector contains project context loading, RAG formatting with citations, and discovery summary with critical issues — none of which are in the assembler. The proposed architecture diagram is wrong because it doesn't account for this third system.

**Fix:** Add ContextInjector as a separate section in the audit. Document the three parallel systems and their overlaps. Add project context, RAG formatting, and discovery summary to the gap analysis.

### Error 3: Incorrectly categorized model routing functions as DISCARD

**What the audit said:** Categorized `call_llm_chat` (H3), `_score_query_complexity` (H5), and model config getters (H1) as DISCARD with "LLM calling is the agent's job" and "Model routing is an agent/LLM-client concern."

**What's actually true:** The state machine's LLM client is a `LLMClientAdapter` (`dashboard/routes/agent.py` L134-154) that **imports and calls** chat.py's functions:

```python
from .chat import (
    get_specialist_model, get_configured_model, get_ollama_endpoint,
    _score_query_complexity, call_llm_chat
)
```

The state machine's LLM calls go **through chat.py** for model routing and API calls. These functions are actively used by the new architecture.

**Impact:** The audit says these functions can be discarded, but cutting them would break the state machine. They need to be PORTed to a proper model client module, not discarded.

**Fix:** Recategorize H1, H3, H5 as PORT (to a model client module). Note that the LLMClientAdapter creates a circular dependency: the state machine (new architecture) depends on chat.py (old architecture) for LLM calls. This dependency must be broken before chat.py can be cut.

### Error 4: Proposed creating a "PromptAssembler" that already exists

**What the audit said:** Proposed creating a new `PromptAssembler` that "composes system prompt + assembled context" as part of the recommended architecture.

**What's actually true:** `PromptBuilder.build_prompt()` (`prompts/builder.py` L86-155) already does exactly this — it composes base prompt + model overrides + tier additions + system_context + user_prefs + project_context + rag_results + conversation_history. The real issue is that the **state machine doesn't use it** — it uses the simpler `AgentPromptBuilder` which lacks system context, project context, RAG formatting, and model overrides.

**Impact:** The recommendation is redundant. The real work is wiring the state machine to use `PromptBuilder` (or extending `AgentPromptBuilder` to include the missing capabilities), not creating a new class.

**Fix:** Replace the "PromptAssembler (NEW)" recommendation with "Wire the state machine to use `PromptBuilder.build_prompt()` instead of `AgentPromptBuilder`, or extend `AgentPromptBuilder` with system context, project context, and RAG formatting capabilities."

### Error 5: Missed that the streaming endpoint has a subset of context injection

**What the audit said:** Treated the streaming endpoint (D1-D10) as having equivalent context injection to `send_message()`, just with different formatting.

**What's actually true:** The streaming `send_message_stream()` does NOT inject:
- Memory context (no `get_memory_context()` call)
- Telemetry context (no `get_telemetry_context()` call)
- Docs context (no `get_docs_context()` call)
- Failure correlation (no failed-discovery injection)
- 18+ keyword-based discovery injections (only backup and storage)
- Relationship-based retrieval (no correlation patterns)
- @mention resolution (no mention handling)
- Page context (no current_page injection)
- Custom AI rules (no `get_custom_ai_rules()` call)
- System identity via `get_system_identity()` (only gets ContextInjector's system context via `build_system_prompt_v2()`)

The streaming endpoint injects only: self-knowledge, discovery (semantic), backup keywords, storage keywords.

**Impact:** The audit doesn't note this inconsistency. When porting to the assembler, this inconsistency would be fixed automatically (both paths would use the same assembler), but the audit should explicitly call this out as a current bug/inconsistency that the migration would fix.

**Fix:** Add a section noting the streaming/non-streaming context injection inconsistency. Note that migrating to the assembler fixes this.

### Error 6: Stated memory storage is missing from the new architecture

**What the audit said:** Listed "Memory storage (post-response)" as a critical gap that must be ported.

**What's actually true:** The state machine's `_handle_responding()` (`state_machine.py` L709-716) already calls `self.memory.store_interaction()` after generating a response. The `MemoryServiceAdapter.store_interaction()` (`adapters.py` L246-276) exists and works. The gap is not that memory storage is missing — it's that the state machine uses `MemoryServiceAdapter` (which wraps `memory.store.get_memory_store()`) while chat.py uses ChromaDB's `index.upsert_conversation()`. These are **different stores**.

**Impact:** The audit overstates the gap. The real issue is store unification, not missing functionality.

**Fix:** Recategorize from "critical gap, must port" to "REFACTOR — unify the two memory stores." The state machine already stores interactions; it just uses a different store than chat.py.

---

## Significant Omissions

### Omission 1: Project context loading (HALBERT.md, agents.md, etc.)

**What was missed:** `ContextInjector.load_project_context()` (`prompts/context.py` L423-459) loads project context from HALBERT.md, .halbert/context.md, agents.md, GEMINI.md, claude.md. This is called from `build_system_prompt_v2()` at chat.py L143. The audit doesn't mention project context at all.

**Impact:** Project context is a context source that the assembler completely lacks. It should be in the gap analysis and the porting priority list.

**Fix:** Add "Project context loading" to the gap analysis. Add a `ProjectContextAdapter` or inject in the prompt builder. Add to porting priority list.

### Omission 2: RAG formatting with citations and confidence thresholds

**What was missed:** `RAGFormatter` (`prompts/context.py` L32-194) formats RAG results as XML with:
- Source URIs (`man://`, `arch://`, etc.)
- Relevance scores with confidence threshold descriptions
- Citation instructions ("Cite using [source:index] format")
- Deduplication (exact + near-duplicate detection)
- CRAG metadata integration

The assembler's `_retrieve_rag()` just does plain text formatting (`[source]: content`). The `PromptBuilder._format_rag_results()` does XML formatting but without citations or deduplication.

**Impact:** The assembler's RAG formatting is significantly less sophisticated than what exists in the ContextInjector. Citation support and deduplication are valuable features that would be lost if chat.py is cut without porting.

**Fix:** Add RAG formatting to the gap analysis. Port `RAGFormatter` into the assembler's RAG retrieval path or the prompt builder.

### Omission 3: Model-specific prompt overrides

**What was missed:** `PromptBuilder._get_model_overrides()` (`prompts/builder.py` L249-286) generates model-specific constraints:
- Small models (7b-14b): stronger constraints against fabricating output, one command at a time
- Reasoning models (deepseek-r1, qwq, o1): thinking block handling instructions

The `AgentPromptBuilder` used by the state machine has no model-specific overrides.

**Impact:** The state machine's prompts don't adapt to model capabilities. Small models may hallucinate command output without the constraints. Reasoning models don't get thinking block instructions.

**Fix:** Add model-specific overrides to the gap analysis. Port into `AgentPromptBuilder` or wire the state machine to use `PromptBuilder`.

### Omission 4: User preferences formatting

**What was missed:** Both `ContextInjector.format_user_preferences()` (`prompts/context.py` L328-352) and `PromptBuilder._format_user_prefs()` (`prompts/builder.py` L167-178) format user preferences as XML. The `AgentPromptBuilder` has a simpler `_format_preferences()` (`agent_prompts.py` L320-327) that formats as markdown. The `UserPreferences` dataclass (`prompts/context.py` L218-227) defines a structured preference schema (verbosity, confirmation_level, expertise_level, preferred_shell, preferred_editor, show_reasoning, auto_execute_safe).

The state machine's `AgentPromptBuilder.build_system_prompt()` accepts a `user_preferences` dict but the state machine never passes one (checking `agent.py` L95, it instantiates `AgentPromptBuilder()` with no arguments, and the internal handlers never pass user_preferences).

**Impact:** User preferences are never injected in the state machine path. The chat.py path loads preferences from `preferences.yml` (L2464-2481) but only for AI name/user name, not for the full UserPreferences schema.

**Fix:** Add user preferences to the gap analysis. Wire the state machine to load and pass user preferences.

### Omission 5: Discovery summary with critical issues

**What was missed:** `ContextInjector.get_discovery_summary()` (`prompts/context.py` L537-565) generates an XML-formatted summary with total discovery count, last scan time, critical issues (top 5), and warning count. This is a different format than the assembler's `_retrieve_discovery()` which does semantic search and returns individual results.

**Impact:** The state machine gets individual discovery results from semantic search but never gets a summary of critical issues. For system administration, knowing "there are 3 critical issues" is valuable even if the query isn't about failures.

**Fix:** Add discovery summary to the gap analysis. Could be a fixed low-priority source in the assembler or part of the system identity context.

---

## Corrected Architecture Map

The actual architecture has **three parallel context-injection/prompt-building systems**, not two:

```
System A: chat.py route handler (send_message / send_message_stream)
├── Manual context injection (20+ keyword blocks, correlation, mentions)
├── build_system_prompt_v2()
│   ├── ContextInjector (prompts/context.py)
│   │   ├── get_system_context() → format_system_context() (XML)
│   │   ├── load_project_context() (HALBERT.md, agents.md, etc.)
│   │   ├── format_conversation_history() (tier-budgeted XML)
│   │   └── get_discovery_summary() (XML with critical issues)
│   └── PromptBuilder.build_prompt() (prompts/builder.py)
│       ├── Base prompt from XML templates
│       ├── Model-specific overrides (small model, reasoning model)
│       ├── RAG results formatting (XML with citations)
│       └── Conversation history formatting (XML)
├── get_system_identity() (rich, markdown, "what's NOT present")
├── get_custom_ai_rules() (from ai_rules.yml)
├── get_self_knowledge_context() (CRAG-evaluated)
├── get_telemetry_context() (journald/hwmon)
├── get_docs_context() (man pages, Arch Wiki)
├── get_memory_context() (ChromaDB conversation search)
├── Failure correlation + relationship correlation
├── Model routing (_score_query_complexity, guide/specialist)
├── LLM calling (call_llm_chat)
├── Safety validation (input + output)
└── Memory storage (ChromaDB upsert_conversation)

System B: State machine (agents/state_machine.py)
├── _handle_planning()
│   ├── self.context.assemble() → ContextAssembler
│   │   ├── conversation (budget-allocated)
│   │   ├── rag (via RAGServiceAdapter)
│   │   ├── memory (via MemoryServiceAdapter)
│   │   ├── discovery (via DiscoveryServiceAdapter)
│   │   └── observations
│   └── self.prompts.build_planning_prompt() → AgentPromptBuilder
│       └── Hardcoded identity/capabilities/constraints + context + plan
├── _handle_searching()
│   ├── self.rag.search() (RAGServiceAdapter)
│   └── self.memory.recall() (MemoryServiceAdapter)
│   └── NO web search (unlike external SearchingHandler dead code)
├── _handle_responding()
│   ├── self.prompts.build_response_prompt() → AgentPromptBuilder
│   └── self.memory.store_interaction() (MemoryServiceAdapter)
├── LLM calls via LLMClientAdapter → imports from chat.py (!!!)
│   ├── get_specialist_model, get_configured_model, get_ollama_endpoint
│   ├── _score_query_complexity
│   └── call_llm_chat
└── CRAG evaluation

System C: External handler classes (agents/handlers/) — DEAD CODE
├── PlanningHandler, SearchingHandler, RespondingHandler, etc.
├── Never instantiated by the state machine
├── Reference self.agent.context_assembler (no property alias exists)
├── Reference self.agent.prompt_builder (no property alias exists)
└── Would crash with AttributeError if ever used
```

**Key dependency:** System B depends on System A for LLM calls (via `LLMClientAdapter`). This circular dependency must be broken before System A can be cut.

---

## Corrected Port/Discard/Refactor Changes

| Original | Item | Corrected | Reason |
|----------|------|-----------|--------|
| DISCARD | H1: Model config getters | **PORT** | Used by LLMClientAdapter |
| DISCARD | H3: `call_llm_chat` | **PORT** | Used by LLMClientAdapter |
| DISCARD | H5: `_score_query_complexity` | **PORT** | Used by LLMClientAdapter |
| PORT (new) | A7: `build_system_prompt_v2` | **REFACTOR** (already exists as PromptBuilder) | PromptBuilder.build_prompt() already does this; wire state machine to use it |
| Critical gap | Memory storage | **REFACTOR** (not a gap) | State machine already stores via MemoryServiceAdapter; issue is store unification |
| Not mentioned | Project context loading | **PORT** (new gap) | ContextInjector.load_project_context() — HALBERT.md, agents.md |
| Not mentioned | RAG formatting with citations | **PORT** (new gap) | RAGFormatter — XML, citations, dedup, CRAG metadata |
| Not mentioned | Model-specific overrides | **PORT** (new gap) | PromptBuilder._get_model_overrides — small model, reasoning model |
| Not mentioned | User preferences | **PORT** (new gap) | UserPreferences dataclass + formatting |
| Not mentioned | Discovery summary | **PORT** (new gap) | ContextInjector.get_discovery_summary — critical issues |
| Not mentioned | External handler classes | **DISCARD** (dead code) | Never instantiated, would crash with AttributeError |
| Not mentioned | LLMClientAdapter circular dependency | **REFACTOR** (new blocker) | State machine imports from chat.py; must extract to shared module |

---

## Corrected Porting Priority

The original porting priority list had 12 items. Corrected list:

**Blockers (must fix before chat.py can be cut):**
0. **Break LLMClientAdapter circular dependency** — extract `call_llm_chat`, `_score_query_complexity`, model config getters from chat.py into a shared `model/client.py` module. The state machine currently imports these from chat.py.
1. **Self-knowledge adapter** — unblocks RQ-E, core to identity
2. **System identity adapter** — unblocks RQ-E, core to "AI is the computer"
3. **User rules adapter** — simple, high value, always included
4. **Failure correlation enricher** — high value for system admin use case
5. **Relationship correlator** — high value, complex but worth it
6. **Telemetry adapter** — needed for system monitoring queries
7. **Safety gates** — needed before chat.py can be cut
8. **Mention resolver** — needed for @mention feature parity

**Important (should port, lower priority):**
9. **Project context adapter** — HALBERT.md, agents.md loading (from ContextInjector)
10. **RAG formatting with citations** — port RAGFormatter into assembler or prompt builder
11. **Model-specific overrides** — port PromptBuilder._get_model_overrides into state machine path
12. **User preferences** — wire state machine to load and pass UserPreferences
13. **Docs adapter (RAG extension)** — needed for documentation queries
14. **Discovery summary** — critical issues summary (from ContextInjector)
15. **Unify memory stores** — ChromaDB conversation store vs memory.store
16. **Wire state machine to PromptBuilder** — or extend AgentPromptBuilder with missing capabilities
17. **Page context** — low priority, only if dashboard chat is retained

**Cleanup:**
18. **Delete external handler classes** — dead code in `agents/handlers/`
19. **Delete duplicate conversation formatters** — 4 implementations, keep 1

---

## What the Original Audit Got Right

Despite the errors above, the original audit correctly identified:
- The 20+ keyword-based discovery injection blocks should be REFACTORED into a declarative topic-router (not ported as-is)
- The failure correlation and relationship correlation logic is valuable and should be PORTed
- Self-knowledge/CRAG, system identity, custom AI rules, and telemetry are critical gaps
- Safety validation (input + output) needs to be PORTed
- @mention resolution needs to be PORTed
- The config editor endpoints should be separated into their own module
- The memory CRUD endpoints should be separated into their own module
- The ReAct loop, tool calling, and vision handling are execution concerns, not context injection
- The rule-based fallback responses are not needed with the state machine
- The position-aware ordering and CLaRa compression in the assembler are good foundations
