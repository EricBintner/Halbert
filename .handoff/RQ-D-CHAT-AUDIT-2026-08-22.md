# RQ-D: chat.py Context-Injection Audit

**Created:** 2026-08-22
**Research question:** RQ-D from DEEP-RESEARCH-QUESTIONS-2026-08-22.md
**Audited file:** `halbert_core/dashboard/routes/chat.py` (4,099 lines)
**New architecture files compared:**
- `halbert_core/context/assembler.py` — ContextAssembler (token budget, parallel retrieval, position-aware ordering, compression cascade)
- `halbert_core/context/adapters.py` — RAGServiceAdapter, DiscoveryServiceAdapter, MemoryServiceAdapter, `create_wired_context_assembler()`
- `halbert_core/agents/handlers/planning.py` — PlanningHandler (calls `context_assembler.assemble()`, builds planning prompt, CRAG eval, routes)
- `halbert_core/agents/handlers/searching.py` — SearchingHandler (parallel RAG + memory + web search, results to `ctx.retrieved_context`)

---

## Summary

`chat.py` contains **69 distinct blocks** related to context injection, prompt assembly, model routing, safety, and memory management. The file is a monolithic FastAPI route module that combines:

1. **Context retrieval functions** (module-level helpers)
2. **Keyword-based discovery injection** (20+ keyword categories in `send_message()`)
3. **Relationship-based correlation** (service-storage, error-service, thermal-process)
4. **Prompt assembly** (v2 PromptBuilder + legacy fallbacks)
5. **Model routing** (guide/specialist complexity scoring)
6. **Safety validation** (input/output filtering)
7. **Memory management** (ChromaDB store/query endpoints)
8. **Config editor** (SEARCH/REPLACE edit blocks)
9. **Streaming** (SSE with reasoning parser)

The new `ContextAssembler` covers **5 sources** (conversation, rag, memory, discovery, observations) with token budgeting and position-aware ordering. It lacks: self-knowledge/CRAG, telemetry, system identity, custom rules, topic detection, failure correlation, relationship-based retrieval, web search, page context, @mention resolution, docs context, safety validation, and prompt building.

**Verdict:** The new assembler is a clean foundation but covers roughly 20% of what `chat.py` does. Most of the gap is keyword-based discovery injection (which should be **REFACTORED** into a declarative topic-router, not ported as-is) and prompt assembly (which belongs in the assembler or a dedicated prompt builder, not scattered across route handlers).

---

## Port/Discard/Refactor Table

### A. Module-Level Context Retrieval Functions

| # | Lines | Block | Verdict | Notes / Destination |
|---|-------|-------|---------|---------------------|
| A1 | 302-336 | `get_memory_context()` — ChromaDB conversation search | REFACTOR | Conceptually covered by `MemoryServiceAdapter.recall()` in adapters.py. But chat.py searches *conversation* collection specifically; the adapter uses `memory.store.get_memory_store()` which is a different store. **Unify:** the assembler's memory source should encompass both conversation history and semantic memory. Port the conversation-collection query into the MemoryServiceAdapter or a dedicated ConversationAdapter. |
| A2 | 339-364 | `store_conversation_memory()` — Store messages in ChromaDB | PORT | Belongs in a memory-write path, not the assembler (assembler is read-only). Port to a `MemoryStore.store_interaction()` method or a post-response hook in the agent state machine. The assembler's `MemoryServiceAdapter.store_interaction()` already exists (adapters.py L246-276) but uses a different store. **Unify the store.** |
| A3 | 367-423 | `get_telemetry_context()` — journald/hwmon from ChromaDB | PORT | New source type needed: `telemetry`. Add a `TelemetryServiceAdapter` to adapters.py and a `_retrieve_telemetry()` method to ContextAssembler. The keyword-gating logic (error/thermal keywords) should become a filter in the adapter, not in the route handler. |
| A4 | 426-481 | `get_docs_context()` — man pages/Arch Wiki via ChromaDB with Self-RAG filtering | REFACTOR | The RAGServiceAdapter currently wraps the generic ChromaDB `index.query()`. Docs are a specific collection. Either: (a) extend RAGServiceAdapter to accept a `collection` parameter, or (b) create a `DocsServiceAdapter`. The Self-RAG distance filtering (L443-453) is valuable — port that as a post-retrieval filter in the adapter. |
| A5 | 484-518 | `get_discovery_context()` — semantic search over discoveries | DISCARD | Superseded by `DiscoveryServiceAdapter.search()` in adapters.py, which is already wired into the assembler's `_retrieve_discovery()`. The chat.py version returns formatted strings; the adapter returns structured dicts that the assembler formats. The adapter is better. |
| A6 | 521-568 | `get_self_knowledge_context()` — Self-RAG reflection with CRAG | PORT | **Critical gap.** This is the system's self-model retrieval. Add a `SelfKnowledgeAdapter` to adapters.py and a `_retrieve_self_knowledge()` method to ContextAssembler. The CRAG evaluation metadata (crag_action, confidence) should be preserved in the AssembledContext sources for debugging. This feeds RQ-E (self-model architecture). |
| A7 | 105-153 | `build_system_prompt_v2()` — PromptBuilder + ContextInjector | REFACTOR | The v2 prompt system (PromptLoader/PromptBuilder/ContextInjector) is a separate module (`prompts/`). It should not be called from the route handler. **Move prompt building into the assembler or a dedicated `PromptAssembler`** that composes system prompt + assembled context. The route handler should call one method. The ContextInjector's `get_system_context()` and `format_system_context()` overlap with what the assembler does — these should merge. |
| A8 | 1392-1476 | `get_system_identity()` — "Who Am I" system profile | PORT | This is the system's identity context (hostname, OS, package manager, filesystems, services). Add as a new source type `system_identity` in the assembler, or inject as a fixed prefix in the prompt builder. The SystemProfiler fallback logic is valuable. **This is a core part of the "AI identifies as the computer" identity (RQ-E).** |
| A9 | 1479-1521 | `get_custom_ai_rules()` — User-defined rules from ai_rules.yml | PORT | Add as a new source type `user_rules` or inject in the prompt builder. These are high-priority instructions that should always be included. Low token cost, high importance. |
| A10 | 1330-1389 | `get_topic_context()` — Topic-based discovery injection (Phase 12b) | REFACTOR | The topic detection (`detect_query_topics`, `TOPIC_KEYWORDS`) is a crude keyword matcher. The assembler already does semantic discovery search which is strictly better. **Discard the keyword matching; keep the concept of topic-filtered discovery retrieval** as an optional filter on the DiscoveryServiceAdapter (e.g., `search(query, limit, discovery_type_filter=...)`). |
| A11 | 1244-1283 | `should_use_web_search()` — Web search trigger detection | DISCARD (from assembler) | Web search triggering is a **routing decision**, not a context-injection concern. The SearchingHandler already handles web search as a tool call. The freshness check (L1272-1281) is interesting but belongs in the search handler or a retrieval router, not the assembler. |
| A12 | 1286-1309 | `get_web_search_context()` — SearXNG web search | DISCARD (from assembler) | Already handled by `SearchingHandler._search_web()`. The assembler should not do web search — it's a retrieval action that happens in the SEARCHING state, not during context assembly. |

### B. send_message() Handler — Context Injection Section (L1633-2443)

| # | Lines | Block | Verdict | Notes / Destination |
|---|-------|-------|---------|---------------------|
| B1 | 1604-1618 | Safety validation on input | PORT | Move to a pre-assembly safety gate. The `SafetyValidator` from `prompts/safety.py` should be called before context assembly, not inside the route handler. The agent state machine's entry point should validate input. |
| B2 | 1646-1653 | Self-knowledge context injection | PORT | Same as A6 — port to assembler as `self_knowledge` source. |
| B3 | 1656-1666 | Page context injection (UI awareness) | REFACTOR | The concept of "current page" is a UI concern. In the new architecture, this becomes an optional `page_context` parameter to `assembler.assemble()`. Add as a new source type `ui_context` with low priority. Only relevant if the chat interface is embedded in the dashboard. |
| B4 | 1669-1676 | Memory context injection | DISCARD | Superseded by assembler's `memory` source via MemoryServiceAdapter. |
| B5 | 1679-1685 | Telemetry context injection | PORT | Same as A3 — port to assembler as `telemetry` source. |
| B6 | 1689-1698 | Docs context injection (keyword-gated) | REFACTOR | Same as A4. The keyword gating (`doc_keywords`) should be replaced by the assembler always attempting docs retrieval with a low priority/budget. If no docs match, the adapter returns empty. |
| B7 | 1701-1708 | Discovery semantic search | DISCARD | Superseded by assembler's `discovery` source. |
| B8 | 1710-1748 | Failure correlation injection | PORT | **Valuable logic.** When the query mentions failures, inject ALL failed/error discoveries with correlation hints. This is not just retrieval — it's cross-type correlation. Port as a `FailureCorrelationAdapter` or as a post-retrieval enrichment step in the assembler. The correlation hint (L1741) is a prompt-engineering detail that should live in the prompt builder. |
| B9 | 1750-1770 | Storage keyword injection | REFACTOR | Replace with topic-filtered discovery retrieval. The assembler's discovery source should accept a `type_filter` parameter. See A10. |
| B10 | 1772-1790 | Backup keyword injection | REFACTOR | Same as B9. |
| B11 | 1792-1809 | Service keyword injection | REFACTOR | Same as B9. |
| B12 | 1811-1854 | Network keyword injection (detailed) | REFACTOR | Same as B9. The detailed formatting (IP, bridge, config_path) is valuable — port the formatting logic into the DiscoveryServiceAdapter's result formatting. |
| B13 | 1856-1875 | Security keyword injection | REFACTOR | Same as B9. |
| B14 | 1877-1895 | Container/Docker keyword injection | REFACTOR | Same as B9. |
| B15 | 1897-1915 | GPU keyword injection | REFACTOR | Same as B9. |
| B16 | 1917-1935 | Sharing keyword injection | REFACTOR | Same as B9. |
| B17 | 1937-1957 | Development/Process keyword injection | REFACTOR | Same as B9. |
| B18 | 1959-1983 | Performance/thermal keyword injection | REFACTOR | Same as B9. The cross-type logic (process + hardware) is a correlation concern — see B8. |
| B19 | 1985-2001 | Package keyword injection | REFACTOR | Same as B9. |
| B20 | 2003-2018 | Boot keyword injection | REFACTOR | Same as B9. |
| B21 | 2020-2035 | Error keyword injection | REFACTOR | Same as B9. Overlaps with B8 (failure correlation). |
| B22 | 2037-2052 | Disk space keyword injection | REFACTOR | Same as B9. |
| B23 | 2054-2069 | Laptop/battery keyword injection | REFACTOR | Same as B9. |
| B24 | 2071-2087 | Display/monitor keyword injection | REFACTOR | Same as B9. |
| B25 | 2089-2105 | Audio keyword injection | REFACTOR | Same as B9. |
| B26 | 2107-2123 | WiFi keyword injection | REFACTOR | Same as B9. |
| B27 | 2125-2140 | USB keyword injection | REFACTOR | Same as B9. |
| B28 | 2142-2158 | GRUB/bootloader keyword injection | REFACTOR | Same as B9. |
| B29 | 2160-2175 | Docker/container keyword injection (duplicate) | DISCARD | Exact duplicate of B14. Dead code. |
| B30 | 2177-2192 | VM/virtualization keyword injection | REFACTOR | Same as B9. |
| B31 | 2194-2209 | Cron/scheduled task keyword injection | REFACTOR | Same as B9. |
| B32 | 2211-2387 | Relationship-based retrieval (6 correlation patterns) | PORT | **Valuable logic.** Six correlation patterns: (1) service→storage, (2) storage→service, (3) error→service, (4) process→service, (5) thermal→process, (6) boot-slow→service. Port as a `RelationshipCorrelator` that runs as a post-retrieval enrichment step. This is the kind of cross-entity reasoning that makes the system useful. Should be a pluggable enricher in the assembler pipeline. |
| B33 | 2389-2443 | @mention resolution | PORT | Move to a `MentionResolver` that runs before context assembly. The resolved discovery data becomes an injected context source. In the new chat architecture, mentions are part of the chat request, not the route handler. |

### C. send_message() Handler — Prompt Assembly & LLM Call (L2445-2917)

| # | Lines | Block | Verdict | Notes / Destination |
|---|-------|-------|---------|---------------------|
| C1 | 2452-2483 | Persona/name loading from preferences.yml | PORT | Move to the prompt builder. The AI name and user name are identity concerns (RQ-E). The PersonaManager integration should happen in the prompt assembly layer. |
| C2 | 2486-2489 | System identity + custom rules injection | PORT | Same as A8 + A9. These go into the prompt builder or assembler. |
| C3 | 2491-2496 | v2 prompt building (tier selection) | REFACTOR | Same as A7. The tier selection (guide/specialist/vision) is a model-routing concern, not a prompt concern. Separate these. |
| C4 | 2498-2567 | Legacy fallback prompts (coder/guide) | DISCARD | The v2 prompt system exists. Legacy fallbacks are dead weight once v2 is confirmed working. The command-formatting and uncertainty instructions in these prompts should be in the v2 XML templates, not hardcoded fallbacks. |
| C5 | 2570-2577 | Context + topic context appended to prompt | REFACTOR | The assembler should produce the context string. The prompt builder should compose system_prompt + assembled_context. This manual concatenation in the route handler is what the assembler replaces. |
| C6 | 2579-2605 | Unclear query detection + docs/web search | REFACTOR | The unclear-query heuristic is crude. The docs/web search gating should be a retrieval routing decision. Move to the PlanningHandler or a retrieval router. |
| C7 | 2608-2621 | Conversation history formatting | DISCARD | Superseded by assembler's `_format_conversation()`. The chat.py version manually concatenates history into the prompt string; the assembler formats it as a structured source with token budgeting. |
| C8 | 2623-2691 | ReAct reasoning loop | DISCARD (from context injection) | ReAct is an agent execution pattern, not context injection. The new agent state machine (PLANNING→SEARCHING→OBSERVING→RESPONDING) replaces ReAct. The ReActAgent class is legacy. |
| C9 | 2696-2705 | Tool calling (Ollama tools API) | DISCARD (from context injection) | Tool calling is an agent execution concern, handled by the state machine's EXECUTING state. Not context injection. |
| C10 | 2708-2736 | Vision model handling | DISCARD (from context injection) | Vision is a model capability concern. The agent state machine should handle image inputs at the entry point, not in the context injection path. |
| C11 | 2742-2770 | Messages array assembly | DISCARD | The new architecture uses the assembler + prompt builder to produce the system message, and the conversation history is handled by the state machine's `ctx.conversation_history`. This manual message assembly is replaced. |
| C12 | 2779-2800 | Model routing (guide/specialist complexity scoring) | DISCARD (from context injection) | Model routing is an agent/LLM-client concern. The `_score_query_complexity()` function (L779-844) is useful but belongs in a `ModelRouter` or the PlanningHandler, not the context injection path. |
| C13 | 2802-2859 | LLM call with fallback | DISCARD (from context injection) | LLM calling is the agent's job, not the context assembler's. The state machine handles LLM calls and fallbacks. |
| C14 | 2890-2907 | Memory storage (post-response) | PORT | Same as A2. This is a post-response hook that should run after the agent produces a response. Port to the state machine's RESPONDING state or a post-response callback. |
| C15 | 2909-2917 | Safety output filtering | PORT | Move to a post-response safety gate. The `OutputFilter` from `prompts/safety.py` should be called after the agent produces a response, before returning to the user. |

### D. send_message_stream() Handler (L2931-3280)

| # | Lines | Block | Verdict | Notes / Destination |
|---|-------|-------|---------|---------------------|
| D1 | 2948-2957 | Streaming safety validation | PORT | Same as B1. Safety validation should happen before streaming starts, at the agent entry point. |
| D2 | 2986-3023 | Streaming system prompt (v2 + legacy fallback) | REFACTOR | Same as A7/C3/C4. The streaming endpoint duplicates the prompt-building logic from send_message(). This duplication is the core problem — **the prompt builder should be shared**. The command-execution instructions (L3013-3023) are streaming-specific UX guidance that should be in the v2 prompt template, conditionally included for streaming mode. |
| D3 | 3034-3042 | Streaming self-knowledge injection | PORT | Same as A6/B2. Port to assembler. |
| D4 | 3045-3051 | Streaming discovery context | DISCARD | Superseded by assembler. |
| D5 | 3054-3059 | Streaming keyword imports (BACKUP_KEYWORDS, STORAGE_KEYWORDS) | REFACTOR | Same as B9-B31. The keyword lists should be centralized in a topic-router, not imported from config prompts. |
| D6 | 3062-3078 | Streaming backup context injection | REFACTOR | Same as B10. |
| D7 | 3081-3095 | Streaming storage context injection | REFACTOR | Same as B9. |
| D8 | 3097-3102 | Streaming context assembly into system prompt | DISCARD | Replaced by assembler + prompt builder. |
| D9 | 3104-3138 | Streaming messages array (DeepSeek-R1 handling) | REFACTOR | The DeepSeek-R1 system-prompt-injection logic is model-specific. Move to the LLM client layer. The history formatting is replaced by the assembler. |
| D10 | 3140-3261 | Streaming reasoning parser (thinking blocks) | DISCARD (from context injection) | This is SSE streaming logic, not context injection. Belongs in the streaming response handler, which is a transport concern separate from context assembly. |

### E. Config Editor Chat (L3547-3959)

| # | Lines | Block | Verdict | Notes / Destination |
|---|-------|-------|---------|---------------------|
| E1 | 3551-3614 | ConfigChatRequest/Response models + CONFIG_EDITOR_SYSTEM_PROMPT | PORT | The config editor is a separate chat mode. The system prompt template (SEARCH/REPLACE format) should be a v2 prompt template. The models should be in a separate config-chat module, not in the main chat route. |
| E2 | 3617-3677 | `parse_edit_blocks()` — Parse SEARCH/REPLACE from AI response | PORT | This is response parsing, not context injection. Move to a response processor in the config editor module. |
| E3 | 3680-3762 | `normalize_whitespace()` + `find_best_match()` — Fuzzy matching | PORT | Utility functions for the config editor. Move to a `config_editor/utils.py` or similar. |
| E4 | 3765-3809 | `apply_edit_blocks()` — Apply edits to file content | PORT | Core config editor logic. Move to the config editor module. |
| E5 | 3812-3831 | `extract_summary_from_response()` — Summary extraction | PORT | Response processing for the config editor. |
| E6 | 3836-3959 | `config_chat()` endpoint | REFACTOR | The endpoint itself stays as a route, but the context assembly (file content as context, custom rules, history) should use the assembler with a `file_content` source. The LLM call should go through the agent state machine or a dedicated config-editing agent. |

### F. Memory Management Endpoints (L3962-4099)

| # | Lines | Block | Verdict | Notes / Destination |
|---|-------|-------|---------|---------------------|
| F1 | 3962-4099 | Memory stats/query/collections/entries CRUD endpoints | DISCARD (from context injection) | These are admin/debug endpoints for the memory system. Not context injection. They should stay as routes but in a separate `memory_routes.py` module, not in chat.py. |

### G. Fallback Response Generators (L3432-3544)

| # | Lines | Block | Verdict | Notes / Destination |
|---|-------|-------|---------|---------------------|
| G1 | 3432-3504 | `generate_guide_response()` — Rule-based fallback | DISCARD | The new architecture uses the agent state machine with LLM calls. Rule-based fallbacks are not needed unless the LLM is completely unavailable, in which case a simple error message suffices. |
| G2 | 3507-3530 | `generate_coder_response()` — Rule-based fallback | DISCARD | Same as G1. |
| G3 | 3533-3544 | `get_suggested_actions()` — Action suggestions | DISCARD | UI concern. If needed, move to the frontend or a separate suggestions service. |

### H. Model Configuration Helpers (L571-936)

| # | Lines | Block | Verdict | Notes / Destination |
|---|-------|-------|---------|---------------------|
| H1 | 571-644 | Model config getters (ollama endpoint, configured model, specialist model) | DISCARD (from context injection) | Model configuration is not context injection. Move to `model/router.py` or a config module. |
| H2 | 647-691 | Token estimation + message truncation | DISCARD | Superseded by `TokenCounter` in `context/tokens.py` and the assembler's budget management. |
| H3 | 694-751 | `call_llm_chat()` — LLM API call | DISCARD (from context injection) | LLM calling is the agent's job. Move to the LLM client layer. |
| H4 | 754-776 | Vision model getter | DISCARD (from context injection) | Model config, not context injection. |
| H5 | 779-844 | `_score_query_complexity()` — Complexity scoring | PORT (to model router) | Useful function for model routing. Move to `model/router.py` or the PlanningHandler. Not context injection. |
| H6 | 847-936 | Model status helpers (loaded models, is_model_loaded, get_model_status) | DISCARD (from context injection) | Model status endpoints. Move to a model management module. |

### I. Guardrails & Policy (L155-300)

| # | Lines | Block | Verdict | Notes / Destination |
|---|-------|-------|---------|---------------------|
| I1 | 159-300 | Guardrail enforcer, policy cache, approval engine, tool authorization | DISCARD (from context injection) | These are execution-time safety controls, not context injection. They belong in the agent's EXECUTING state handler or a dedicated guardrails module. Already exists as `autonomy/guardrails.py` and `policy/engine.py`. |

---

## Gap Analysis: What the New Assembler Lacks

The current `ContextAssembler` (assembler.py) handles 5 sources: conversation, rag, memory, discovery, observations. The following capabilities exist in `chat.py` but are **missing** from the new assembler:

### Critical Gaps (must port before cutting chat.py)

| Gap | chat.py Location | Proposed Solution |
|-----|------------------|-------------------|
| **Self-knowledge / CRAG** | L521-568, L1646-1653 | Add `SelfKnowledgeAdapter` + `_retrieve_self_knowledge()` to assembler. Returns CRAG-evaluated self-model context. Feeds RQ-E. |
| **System identity** | L1392-1476 | Add `SystemIdentityAdapter` or inject as fixed prompt prefix. Contains hostname, OS, package manager, filesystems, services. Core to "AI identifies as computer" (RQ-E). |
| **Custom AI rules** | L1479-1521 | Add `UserRulesAdapter` or inject in prompt builder. Loads from `ai_rules.yml`. Always included, high priority. |
| **Telemetry** | L367-423 | Add `TelemetryAdapter` + `_retrieve_telemetry()`. Queries journald/hwmon collections with keyword gating. |
| **Failure correlation** | L1710-1748 | Add `FailureCorrelationAdapter` or post-retrieval enricher. Injects ALL failed discoveries with correlation hints when query mentions failures. |
| **Relationship correlation** | L2211-2387 | Add `RelationshipCorrelator` as post-retrieval enricher. 6 patterns: service↔storage, error→service, process→service, thermal→process, boot-slow→service. |
| **Safety validation (input)** | L1604-1618 | Add pre-assembly safety gate using `SafetyValidator.validate_input()`. |
| **Safety filtering (output)** | L2909-2917 | Add post-response safety gate using `OutputFilter.filter_output()`. |
| **Memory storage (post-response)** | L2890-2907 | Add post-response memory store hook in the agent state machine. |
| **@mention resolution** | L2389-2443 | Add `MentionResolver` that runs before assembly. Resolved discoveries become a context source. |

### Important Gaps (should port, lower priority)

| Gap | chat.py Location | Proposed Solution |
|-----|------------------|-------------------|
| **Docs context (man pages/wiki)** | L426-481 | Extend `RAGServiceAdapter` with `collection` parameter, or create `DocsAdapter`. Port the Self-RAG distance filter. |
| **Page context (UI awareness)** | L1656-1666 | Add optional `page_context` parameter to `assembler.assemble()`. Low-priority `ui_context` source. |
| **Persona/name loading** | L2452-2483 | Move to prompt builder. Identity concern (RQ-E). |
| **Prompt building (v2)** | L105-153 | Move `build_system_prompt_v2()` out of route handler into a `PromptAssembler` that composes system prompt + assembled context. |

### Discardable (superseded or wrong layer)

| Gap | chat.py Location | Reason |
|-----|------------------|--------|
| Keyword-based discovery injection (20+ blocks) | L1750-2209 | Replaced by semantic discovery search in assembler. Topic filtering should be a parameter on the discovery adapter, not 20 hardcoded keyword blocks. |
| Legacy fallback prompts | L2498-2567 | v2 prompt system exists. |
| ReAct loop | L2623-2691 | Replaced by agent state machine. |
| Tool calling | L2696-2705 | Handled by EXECUTING state. |
| Vision model handling | L2708-2736 | Model capability, not context injection. |
| Messages array assembly | L2742-2770 | Replaced by assembler + prompt builder. |
| Model routing | L2779-2800 | Agent/LLM-client concern. |
| LLM call + fallback | L2802-2859 | Agent's job. |
| Streaming reasoning parser | L3140-3261 | Transport concern. |
| Rule-based fallback responses | L3432-3530 | Not needed with agent state machine. |
| Memory CRUD endpoints | L3962-4099 | Admin routes, not context injection. Move to separate module. |
| Guardrails/policy/approval | L155-300 | Execution-time safety, not context injection. Already in separate modules. |
| Model config helpers | L571-936 | Model management, not context injection. |

---

## Recommended Assembler Architecture (Post-Port)

```
ContextAssembler
├── Sources (parallel retrieval, token-budgeted)
│   ├── conversation        (existing)
│   ├── rag                 (existing — extend with collection param for docs)
│   ├── memory              (existing — unify conversation + semantic memory)
│   ├── discovery           (existing — add type_filter param)
│   ├── observations        (existing)
│   ├── self_knowledge      (NEW — SelfKnowledgeAdapter + CRAG)
│   ├── system_identity     (NEW — SystemIdentityAdapter, fixed prefix)
│   ├── telemetry           (NEW — TelemetryAdapter, keyword-gated)
│   └── user_rules          (NEW — UserRulesAdapter, always included)
├── Enrichers (post-retrieval, cross-source)
│   ├── failure_correlation (NEW — inject failed discoveries with hints)
│   ├── relationship_correlator (NEW — 6 cross-entity patterns)
│   └── mention_resolver    (NEW — @mention → discovery data)
├── Position-aware ordering (existing — "Lost in the Middle")
├── Compression cascade (Phase 72, replaces CLaRa)
└── Safety gates
    ├── input_validation    (NEW — SafetyValidator.validate_input)
    └── output_filtering    (NEW — OutputFilter.filter_output, post-response)

PromptAssembler (NEW — separate from ContextAssembler)
├── PromptBuilder (v2, from prompts/ module)
├── Composes: system_prompt + assembled_context + user_rules
├── Persona/name injection (from preferences.yml)
└── Tier selection (guide/specialist/vision) — delegates to ModelRouter
```

---

## Porting Priority (for Phase 4)

1. **Self-knowledge adapter** — unblocks RQ-E, core to identity
2. **System identity adapter** — unblocks RQ-E, core to "AI is the computer"
3. **User rules adapter** — simple, high value, always included
4. **Failure correlation enricher** — high value for system admin use case
5. **Relationship correlator** — high value, complex but worth it
6. **Telemetry adapter** — needed for system monitoring queries
7. **Safety gates** — needed before chat.py can be cut
8. **Mention resolver** — needed for @mention feature parity
9. **Docs adapter (RAG extension)** — needed for documentation queries
10. **Prompt assembler** — needed to replace scattered prompt building
11. **Page context** — low priority, only if dashboard chat is retained
12. **Memory storage hook** — needed for conversation persistence

Once items 1-9 are ported, the assembler has feature parity with chat.py's context injection. Items 10-12 complete the migration. Then chat.py can be cut (Phase 4).
