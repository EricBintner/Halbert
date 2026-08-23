# Intake Pipeline Design — Message Analysis, Model Routing, and Context Budgeting

**Created:** 2026-08-23
**Status:** Design document, pre-implementation. Ready for review.
**Author:** Session analysis comparing two codebases' message intake approaches.
**Reads with:**
- `documentation/design/the-being.md` (the vision this serves)
- `documentation/design/explorations.md` (the design-to-implementation catalog, especially A1, F4)
- `.handoff/RQ-D-CHAT-AUDIT-2026-08-22.md` (the prior audit of chat.py context injection)
- `.handoff/FOUNDATIONAL-RESEARCH-2026-08-21.md` (the diagnosis this builds on)

---

## 0. Purpose of This Document

This is a **review-ready design handoff** for another AI to evaluate before implementation
begins. It captures:

1. What we found by comparing Halbert's message intake to a more mature codebase's intake
   (referred to throughout as "the other codebase" — app names are intentionally omitted since
   that repo is not part of this project).
2. A prioritization of what to port, what to skip, and why.
3. A concrete structural design for a new `intake/` module.
4. How it fits into the existing design documents (`the-being.md`, `explorations.md`).

**The reviewer should evaluate:**
- Are the tier assignments (essential / important / nice-to-have / not-worth-it) correct?
- Is the proposed module structure right? Are there missing pieces?
- Does this conflict with anything in the design docs or the foundational research?
- Is the implementation order correct?
- Are there risks or edge cases not addressed?

---

## 1. The Problem

When a user sends a message to Halbert today, the "first steps" of processing that message are
scattered, shallow, and in some cases actively degrading response quality. Specifically:

### 1.1 What Halbert does today (the current intake)

The intake logic lives inline in `dashboard/routes/chat.py` (3,914 lines). When a message
arrives, the following happens in sequence, all inside the `send_message()` handler:

1. **Topic detection** (`detect_query_topics`, L1059-1066): Pure keyword matching against 5
   hardcoded topic categories (storage, backup, service, network, security). Returns a list of
   matched topic strings. Used to inject discovery context.

2. **Unclear query detection** (inline, L2318-2327): A heuristic — `len(query_words) <= 5` AND
   no sysadmin keywords present → flagged as "unclear." If unclear, RAG retrieval is skipped and
   a "ask for clarification" hint is appended to the prompt.

3. **Tool-use detection** (`should_use_tools`, L862-879): Keyword matching against ~15 phrases
   ("disk space", "is running", "check logs", etc.). If matched AND complexity ≥ 0.4, auto-
   enables the ReAct reasoning loop.

4. **Web search detection** (`should_use_web_search`, L983-1022): Keyword matching against ~12
   patterns ("latest version", "cve", "compare", etc.) plus a RAG freshness check. If matched,
   performs a SearXNG web search and injects results.

5. **Complexity scoring** (`_score_query_complexity` in `model/client.py`, L260-360): Pure
   keyword/regex heuristics. Scores 0.0–1.0 based on word count, diagnostic keywords, code
   keywords, multi-step keywords, analysis keywords, and simple-indicator penalties. Threshold
   0.5 → route to specialist (70b), below → guide (8b). **No LLM assessment, no caching, no
   stats, no model-tier awareness.**

6. **Context assembly** (`context/assembler.py`): Token-budget-aware assembly from conversation,
   RAG, memory, discovery, observations, and extra sources. Dynamic budget ratios based on
   conversation length. Position-aware ordering ("Lost in the Middle"). Compression cascade
   (LLMLingua-2 → semantic → noop) when >4000 tokens. **But `max_tokens` defaults to 8000
   regardless of which model is selected — no per-model budget.**

7. **Message history truncation** (`_truncate_messages_for_context` in `model/client.py`,
   L206-257): Rough token estimate (4 chars/token), preserves system message + recent messages,
   truncates at 12000 tokens. Crude — no sentence-boundary preservation, no category awareness.

### 1.2 What the other codebase does (the mature intake)

The other codebase has a **multi-stage intake pipeline** that runs before the main LLM sees the
message:

**Stage 1 — Signal Detection** (`conversation/signals.py`): Zero-LLM, pure regex, <1ms.
Detects: is_question, is_farewell, is_greeting, is_affectionate, emotion (6 categories), topics
(7 categories), message_length (short/normal/long). Returns a `MessageSignals` dataclass.

**Stage 2 — Epistemic Parser** (`conversation/epistemic.py`): Uses a fast small LLM (the
"parser"). Sends the raw message to a small model with a structured parsing prompt that wraps
content into epistemic layers: `**actions**`, `[thoughts]`, `++hidden states++`, `^scene^`,
`"dialogue"`. The parser **also outputs a COMPLEXITY score (1-5)** in the same call — no extra
round-trip. A regex reclassification pass catches user mistakes (e.g., `**I can't believe**` →
reclassified as `[thought]`).

**Stage 3 — Scene Change Detection** (`detect_scene_change`): Regex, no LLM. High/medium
confidence pattern matching for location/time/mood/activity transitions. Has a sophisticated
skip filter that avoids false positives (questions, future plans, hypotheticals, past
recounting, negations, desires).

**Stage 4 — Scene Memory**: Persistent per-conversation state. Stores hidden states for later
discovery moments. Tracks environment, persona observations, clothing changes. Custom discovery
triggers from scenario config.

**Stage 5 — Complexity-Based Model Routing** (`model/complexity_router.py` +
`model/model_cycling.py`): A dedicated `ComplexityRouter` uses a tiny model (qwen3:4b) to score
complexity 1-5. Has an LRU cache (100 entries) for repeated messages. Routes to different model
tiers: trivial→small model, complex→large model. Combined with `ModelManager` that merges
complexity routing + model cycling (round-robin, DI-based, or interval-based). Tracks stats:
cache hit rate, avg latency, complexity distribution.

**Stage 6 — Context Budget Manager** (`context/budget_manager.py`): 6 model tiers (TINY →
MASSIVE) with empirically-tuned token budgets per category (identity_core, personality,
background, scenario, memory, history, formatting). Based on "Pass 1.5 findings": 8B models
degrade >1000 tokens, 30B handle 1500+, MoE with 262K context handle 8000+. Per-category budgets
with sentence-boundary-preserving truncation. VRAM detection → auto-selects appropriate tier.

### 1.3 The gaps in Halbert

| Gap | Impact | Severity |
|-----|--------|----------|
| Complexity scoring is keyword-only, no LLM assessment | Misses nuanced complexity ("ZFS pool won't import after kernel update" has no diagnostic keywords but is clearly complex). Routes to wrong model. | High |
| Context budget is model-agnostic (flat 8000 tokens) | Over-stuffs 8B guide model (degrades quality), under-utilizes 70B specialist. The other codebase proved 8B models degrade >1000 tokens. | High |
| No signal/intent detection pre-pass | No instant metadata (is_question, intent type, domains) to feed routing and context assembly. Everything goes through keyword matching scattered across 5 functions. | Medium |
| No caching of complexity assessment | Recomputes every time. The other codebase caches (LRU, 100 entries). | Low |
| No stats/observability on routing decisions | Can't tune thresholds. Can't see distribution. | Low |
| Complexity score not used for context sizing | Complex query to specialist gets same 8000-token context as trivial query to guide. | Medium |
| No message pre-processing layer | Raw user message goes straight to LLM. No entity extraction, no intent classification, no structured metadata for downstream consumers. | Medium |

---

## 2. How the Design Docs Change the Course

Two items in the design documents are decisive for this analysis:

### 2.1 A1 — Collapse to one conversation path

From `explorations.md` §A1:

> `dashboard/routes/chat.py` (3,914 lines — legacy, rich context injection, still has live UI
> consumers) vs `dashboard/routes/agent.py` (736 lines — Phase 36 state machine, SSE, already
> wired to the cognitive core via `integrations/cognition_wiring.py`, and to the wired context
> assembler via `context/`).
> **Direction:** the agent path is the survivor.

**Implication:** Any intake logic built inline in `chat.py` is throwaway. The intake pipeline
must be a **standalone module** that the agent path calls before the cognitive tick
(`advance_turn`). This is a hard constraint on the design.

### 2.2 F4 — Keyword heuristics get replaced by semantic retrieval

From `explorations.md` §F4:

> What this replaces: `rag/pipeline.py` (deprecated but alive in CLI eval tooling — keep for
> eval, off the chat path), the self-knowledge ChromaDB collections (migrate to memory_v2 +
> observations), **keyword→injection heuristics in `chat.py` (replaced by semantic retrieval
> over the system tree)**.

**Implication:** `detect_query_topics`, `get_topic_context`, `should_use_tools`,
`should_use_web_search` — all of these keyword heuristics are *scheduled for replacement* by
SourcePrep semantic retrieval. Building more keyword heuristics is working against the design.
The intake pipeline should not double down on keyword matching; it should provide the
*structural* pieces (signal detection, complexity assessment, budget management) that semantic
retrieval won't subsume.

### 2.3 The reframing

The question is not "port everything from the other codebase." The question is:

> **What intake processing does the being need that semantic retrieval won't subsume?**

Answer:
- **Model-tier context budgeting** — model capability concern, not retrieval concern. Essential.
- **LLM-based complexity routing** — query property, not system state. Essential.
- **Signal/intent detection** — user goal classification, not system knowledge. Essential.
- **Entity extraction** — may be subsumed by SourcePrep semantic search. Nice-to-have, defer.
- **Epistemic parsing / scene detection / scene memory / model cycling** — roleplay-specific,
  no sysadmin analog. Not worth porting.

---

## 3. Prioritized Assessment

### Tier 1 — Essential (directly serves the vision, not replaced by SourcePrep)

#### 3.1 Model-tier context budgeting

**What:** Port the `ContextBudgetManager` pattern. Map Halbert's guide/specialist/vision models
to tiers (tiny/small/medium/large/xlarge/massive). Scale the assembler's `max_tokens` per tier.
Per-category budgets (identity, personality, background, scenario, memory, history,
formatting) adapted for sysadmin context (system_identity, user_rules, rag, memory, discovery,
conversation, observations).

**Why essential:** The current flat 8000-token budget is actively degrading the 8B guide model.
The other codebase's "Pass 1.5 findings" empirically demonstrated that 8B models degrade
above ~1000 tokens. The design says "model layer + routing" is load-bearing and kept (§9 of
the-being.md). This is the single highest-impact change for response quality.

**Why not replaced by SourcePrep:** SourcePrep replaces *what* gets retrieved, not *how much*
context the target model can handle. Budget sizing is a model-capability concern, not a
retrieval concern.

**Design fit:** The assembler (`context/assembler.py`) already has budget allocation — it just
needs to be told the budget by the model tier, not hardcoded. The `_allocate_budget` method
already takes `max_tokens` as a parameter; the issue is that callers pass 8000 unconditionally.

**Source reference:** `context/budget_manager.py` in the other codebase (641 lines). Key
structures to port:
- `ModelTier` enum (6 tiers)
- `ContextBudget` dataclass (per-category allocation)
- `CONTEXT_BUDGETS` lookup table (empirically tuned)
- `detect_model_tier()` function (model name → tier)
- `ContextBudgetManager` class (fit text to category budget, track usage)
- `truncate_to_tokens()` with sentence-boundary preservation

**What to skip from the source:**
- VRAM detection (`detect_vram`, `auto_select_tier_from_vram`) — Halbert already has model
  config in `models.yml`; the budget manager reads the model name and maps to a tier. VRAM
  detection is a future enhancement, not v1.
- `compress_persona_for_model` — persona-specific, no sysadmin analog.
- `_build_identity_text` / `_build_personality_text` — persona-specific.

**Adaptation for Halbert:** The category names need to change. The other codebase uses
identity_core, personality, background, scenario, memory, history, formatting (roleplay
persona categories). Halbert's categories (from the existing assembler) are: conversation,
rag, memory, discovery, observations, plus extra sources (system_identity, self_knowledge,
telemetry, safety, user_rules). The budget table should map these.

#### 3.2 LLM-based complexity routing with caching

**What:** A `ComplexityRouter` that uses the guide model (already loaded) for a 1-digit
complexity score (1-5), with LRU cache and stats. Fast path: if signal detection says
"greeting," skip the LLM call (score=1, cached).

**Why essential:** The keyword heuristic misses nuanced complexity. A query like "the ZFS pool
won't import after the kernel update" has no diagnostic keywords but is clearly complex. The
being needs to route correctly to fulfill "the most helpful colleague" framing. Wrong routing
means either (a) a complex query gets the 8B guide and produces a shallow answer, or (b) a
trivial query gets the 70B specialist and wastes 10x the compute for no quality gain.

**Why not replaced by SourcePrep:** Complexity is a property of the *query*, not the retrieval.
SourcePrep tells you what's relevant; complexity tells you which model should reason about it.

**Design fit:** Feeds directly into model selection for the cognitive tick. The complexity
score becomes an input to `advance_turn` — the cognitive core can use it to decide reasoning
depth.

**Source reference:** `model/complexity_router.py` in the other codebase (331 lines). Key
structures to port:
- `ComplexityLevel` enum (5 levels with descriptions)
- `ComplexityResult` dataclass (level, score, reasoning, latency_ms)
- `ComplexityRouter` class (assess_complexity, select_model, cache, stats)
- `COMPLEXITY_PROMPT` template (1-5 rating, single digit output)
- LRU cache with eviction

**What to skip from the source:**
- `ModelConfig` / `RouterConfig` / `create_router_from_settings` — the other codebase has a
  multi-model pool with per-model complexity ranges. Halbert has a simpler 2-model setup
  (guide + specialist). The router should return a score; the caller maps score→model.
- `ModelManager` (complexity routing + cycling) — cycling was for roleplay repetition
  breaking. Not relevant for sysadmin chat. The design's "one mind" principle (§6 of
  the-being.md) means one consistent model identity, not cycling.
- Separate analyzer model — the other codebase loads a separate 4B model for complexity
  assessment. Halbert should use the guide model itself with a 5-token prompt (it's already
  loaded in VRAM), avoiding a second model load.

**Key design decision:** The complexity router uses the guide model, not a separate analyzer.
The other codebase loads a separate 4B model (qwen3:4b) for complexity assessment. This makes
sense when you have many models and want a tiny fast one. Halbert should use the guide model
(already loaded) with a 5-token prompt (`num_predict=5`, `temperature=0.1`). This avoids a
second model load and keeps the architecture simpler. The latency cost is ~50-100ms on the
first call, <1ms on cache hits.

**Threshold mapping:** The other codebase uses 1-5 integer scores mapped to model tiers.
Halbert currently uses 0.0-1.0 float scores with a 0.5 threshold. The new router should use
1-5 (matching the cognitive core's complexity input) and map: 1-2 → guide, 3-5 → specialist
(adjustable threshold). The 0.5 float threshold in the current code is a guess; the 1-5 scale
is more interpretable and tunable.

#### 3.3 Signal/intent detection pre-pass (zero-LLM)

**What:** A lightweight regex pass that classifies the message into structured signals:
`intent` (question | command | troubleshooting | informational | greeting | farewell),
`is_question`, `message_length` (short | normal | long), `detected_domains`
(storage | network | security | service | backup | config).

**Why essential:** This runs in microseconds, feeds the complexity router (as a fast pre-filter
— greetings don't need LLM assessment), feeds the cognitive tick (intent shapes the response
state), and feeds context assembly (troubleshooting queries get more retrieval budget).

**Why not replaced by SourcePrep:** Intent classification is about the *user's goal*, not
about system state. SourcePrep retrieves system knowledge; it doesn't tell you whether the user
is asking a question or issuing a command.

**Design fit:** This is the bridge between "message arrives" and "advance_turn runs." The
cognitive tick needs to know what kind of turn this is. The `MessageSignals` from the other
codebase is the right pattern, adapted for sysadmin context.

**Source reference:** `conversation/signals.py` in the other codebase (167 lines). Key
structures to port:
- `MessageSignals` dataclass (adapted fields for sysadmin)
- Pattern lists (FAREWELL, GREETING patterns — universal; emotion/topic patterns — adapt)
- `analyze_message()` function (the zero-LLM analyzer)
- `signals_to_dict()` for serialization

**What to skip from the source:**
- Affection patterns, emotion detection (positive/negative/playful/vulnerable) — roleplay-
  specific. A sysadmin assistant doesn't need to detect "is_affectionate" or emotional tone.
  (Though "frustrated" detection could be useful for tuning response patience — consider for
  Tier 2.)
- Topic keywords (work, family, health, food, entertainment, relationship, plans) —
  roleplay-specific. Replace with sysadmin domains (storage, network, security, service,
  backup, config).

**Adaptation for Halbert:** The `MessageSignals` dataclass should become:

```python
@dataclass
class MessageSignals:
    intent: str = "informational"  # question|command|troubleshooting|informational|greeting|farewell
    is_question: bool = False
    is_greeting: bool = False
    is_farewell: bool = False
    is_troubleshooting: bool = False  # reports a problem/error
    message_length: str = "normal"    # short|normal|long
    detected_domains: list[str] = field(default_factory=list)  # storage|network|security|service|backup|config
    has_error_indicators: bool = False  # contains "error", "failed", "broken", stack trace markers
    has_code_blocks: bool = False       # contains ``` or indented code
    has_file_paths: bool = False        # contains /path/to/something patterns
```

The `intent` field is derived from the other fields:
- `is_greeting` → intent = "greeting"
- `is_farewell` → intent = "farewell"
- `is_troubleshooting` or `has_error_indicators` → intent = "troubleshooting"
- `is_question` → intent = "question"
- starts with a verb (show, list, check, run, install, configure, enable, disable, restart,
  stop, start) → intent = "command"
- else → intent = "informational"

The `detected_domains` replace the current `detect_query_topics` / `TOPIC_KEYWORDS` in
chat.py. These are the same 5 domains already in use, plus "config" — but structured as part
of the signal detection, not a separate function.

### Tier 2 — Important (build after Tier 1, before the slices)

#### 3.4 Complexity-aware context assembly

**What:** Extend the assembler's `_allocate_budget` to take complexity as a second axis
alongside conversation length. Complex queries get more retrieval budget; trivial queries get
minimal context.

**Why important:** The assembler already adjusts by conversation length — this is a natural
extension. But it's not blocking because the model-tier budget (Tier 1 item 3.1) already
handles the most damaging case (over-stuffing small models).

**Design fit:** Directly serves "triages, not monitors" (§1 of the-being.md) — the being
should give deep context to complex queries and minimal context to "thanks."

**Implementation note:** This is a small change to `_allocate_budget` — add a `complexity`
parameter and adjust the ratio tables. The existing short/medium/long conversation ratios
become a 2D matrix (conversation_length × complexity).

#### 3.5 Routing observability

**What:** Track complexity distribution, cache hit rate, avg assessment latency, model
selection counts. Expose via a dashboard endpoint (`/api/intake/stats` or similar).

**Why important:** Needed for tuning the complexity threshold (currently a guess). Not
blocking but cheap to add alongside the complexity router.

**Design fit:** The dashboard already has model status endpoints. This is a natural extension.

### Tier 3 — Nice to have (post-MVP)

#### 3.6 Entity extraction pre-pass

**What:** Extract hostnames, service names, commands, file paths, error messages from the user
message before retrieval.

**Why nice-to-have:** Would improve RAG query quality. But the design says SourcePrep semantic
retrieval replaces keyword injection — once that's wired, entity extraction may be redundant.
Build only if semantic retrieval proves insufficient.

**Risk:** Building this now might create a keyword-extraction layer that becomes throwaway
when SourcePrep lands (same problem as the current keyword heuristics in F4).

### Not worth porting

#### 3.7 Epistemic parsing (actions/thoughts/hidden states/scene)

Roleplay-specific. The other codebase separates observable actions, private thoughts, hidden
states, and scene descriptions. Halbert is a sysadmin assistant — there is no sysadmin analog
to "private thoughts the persona can't see." The *pattern* of pre-processing the message
before the main LLM sees it is valuable (captured in Tier 1 item 3.3), but the specific
epistemic layering has no application here.

#### 3.8 Scene change detection

Roleplay-specific (location/time/mood transitions). No sysadmin equivalent. The closest analog
would be "the user switched topics" detection, but that's better handled by the cognitive
core's conversation state tracking, not a regex pre-pass.

#### 3.9 Scene memory / discovery triggers

Roleplay-specific (hidden states for later reveal). Halbert's findings store (C1 in
explorations.md) is the analog, and it's already designed separately as part of the config
physiology brain. No need to port the roleplay version.

#### 3.10 Model cycling (round-robin, DI-based, interval-based)

Was for deterioration prevention in long roleplay conversations (breaking repetition patterns
by swapping models). Not relevant for sysadmin chat. The design's "one mind" principle (§6 of
the-being.md) means one consistent model identity, not cycling through models. The
`ModelManager` class that combines complexity routing + cycling is overkill — Halbert needs
only the complexity routing part.

---

## 4. Proposed Design: The Intake Module

### 4.1 Module structure

```
halbert_core/halbert_core/intake/
    __init__.py
    signals.py          # zero-LLM signal/intent detection (Tier 1.3)
    complexity.py       # LLM-based complexity router with cache (Tier 1.2)
    budget.py           # model-tier context budget manager (Tier 1.1)
    pipeline.py         # orchestrates the three, produces MessageIntake
```

**Why a new top-level module:** The intake logic is currently scattered across
`dashboard/routes/chat.py` (topic detection, unclear query, tool-use detection, web search
detection) and `model/client.py` (complexity scoring, token estimation, message truncation).
It doesn't belong in either — it's a pre-processing step that feeds both. A standalone module
is agent-path-ready (A1 constraint) and doesn't create a dependency on the route handler.

**Why not in `context/`:** The context assembler assembles *retrieved* context. The intake
module processes the *incoming message* and produces metadata that *informs* assembly. They're
different concerns. The intake module's output feeds the assembler; it doesn't replace it.

**Why not in `model/`:** The model client handles LLM API calls. The intake module decides
*which* model to call and *how much* context to give it. The budget manager is model-aware but
not a model client. Keeping them separate avoids circular dependencies.

### 4.2 The `MessageIntake` data structure

```python
@dataclass
class MessageIntake:
    """Complete intake analysis of a user message.

    Produced by the intake pipeline. Consumed by:
    - Model selection (recommended_model, model_tier)
    - Context assembler (context_budget, needs_retrieval)
    - Cognitive tick / advance_turn (intent, complexity_score, signals)
    - ReAct agent (needs_tools)
    """

    # === From signals.py (zero-LLM, <1ms) ===
    intent: str                     # question|command|troubleshooting|informational|greeting|farewell
    is_question: bool
    is_greeting: bool
    is_farewell: bool
    is_troubleshooting: bool
    message_length: str             # short|normal|long
    detected_domains: list[str]     # storage|network|security|service|backup|config
    has_error_indicators: bool
    has_code_blocks: bool
    has_file_paths: bool

    # === From complexity.py (LLM, ~50ms with cache; <1ms on cache hit) ===
    complexity_score: int           # 1-5
    complexity_level: str           # trivial|simple|moderate|complex|very_complex
    complexity_cached: bool
    complexity_latency_ms: float

    # === From budget.py (lookup, <1ms) ===
    model_tier: str                 # tiny|small|medium|large|xlarge|massive
    context_budget: ContextBudget   # per-category token allocation
    recommended_model: str          # guide|specialist|vision

    # === Derived ===
    needs_retrieval: bool           # False for greetings/farewells, True for everything else
    needs_tools: bool               # True if intent=troubleshooting AND complexity >= 3
    needs_web_search: bool          # True if signals suggest current-info needed (defer to F4)
```

### 4.3 The pipeline flow

```
user message
    │
    ▼
signals.analyze(message)                  # <1ms, zero LLM
    │  → intent, is_question, domains, length, error indicators, code blocks, file paths
    │
    ▼
complexity.assess(message, signals)       # ~50ms (cache hit: <1ms)
    │  → 1-5 score
    │  Fast path: if signals.intent == "greeting" or "farewell" → score=1, skip LLM call
    │  Fast path: if signals.is_troubleshooting → minimum score=3 (troubleshooting is never trivial)
    │
    ▼
budget.for_model(selected_model)          # <1ms, lookup table
    │  → model_tier, per-category token allocation
    │  Model selection: score 1-2 → guide, 3-5 → specialist (if configured)
    │
    ▼
MessageIntake → feeds advance_turn + context assembler + model selection
```

### 4.4 Key design decisions

**Decision 1: The complexity router uses the guide model, not a separate analyzer.**
The other codebase loads a separate 4B model for complexity assessment. This makes sense when
you have many models and want a tiny fast one. Halbert should use the guide model (already
loaded in VRAM) with a 5-token prompt. This avoids a second model load and keeps the
architecture simpler. The latency cost is ~50-100ms on the first call, <1ms on cache hits.

**Decision 2: Signals gate the complexity router.**
If `signals.analyze()` detects a greeting or farewell, skip the LLM complexity call entirely
(score=1, cached). If it detects troubleshooting, set a minimum score of 3 (troubleshooting is
never trivial — even a short "nginx won't start" needs the specialist). This eliminates
unnecessary LLM calls for the most common message types and ensures troubleshooting always
gets adequate reasoning capacity.

**Decision 3: The budget manager is model-name-driven, not VRAM-driven.**
The other codebase has VRAM detection and auto-tier selection. Halbert already has model
config in `models.yml` — the budget manager reads the model name and maps to a tier. VRAM
detection is a future enhancement, not v1. This keeps the budget manager dependency-free and
testable without a GPU.

**Decision 4: The module is agent-path-ready.**
It doesn't import from `chat.py` or `agent.py`. Both paths call it. When chat.py retires (A1),
the agent path already uses it. No throwaway. The pipeline produces a `MessageIntake` that
both paths can consume identically.

**Decision 5: `needs_retrieval` replaces `unclear_query`.**
The current `unclear_query` heuristic (≤5 words + no keywords) becomes a proper signal:
greetings and farewells don't need retrieval; everything else does. This is what F4 is
pointing at — but until SourcePrep lands, retrieval still goes through the existing RAG path.
The `needs_retrieval` flag is the stable interface; the retrieval implementation behind it
changes when SourcePrep arrives.

**Decision 6: `needs_web_search` is deferred.**
The current `should_use_web_search` keyword heuristic is scheduled for replacement (F4). The
intake module should not replicate it. Instead, `needs_web_search` is a derived flag based on
signals (e.g., "latest version" patterns) that the SearchingHandler can check. The actual web
search execution stays in the handler, not the intake module. This flag may be removed
entirely when SourcePrep's freshness checking is wired.

**Decision 7: 1-5 integer complexity scale, not 0.0-1.0 float.**
The current code uses a 0.0-1.0 float with a 0.5 threshold. The other codebase uses 1-5
integers. The 1-5 scale is more interpretable, matches the cognitive core's complexity input
format, and is easier to tune (you can see the distribution). The mapping: 1-2 → guide, 3-5 →
specialist (adjustable threshold in config).

### 4.5 Budget categories for Halbert

The other codebase uses roleplay persona categories (identity_core, personality, background,
scenario, memory, history, formatting). Halbert's categories should match the existing
assembler's source types:

| Category | What it contains | Preserve strategy |
|----------|-----------------|-------------------|
| `system_identity` | Hostname, OS, hardware, role | Always include (small, fixed) |
| `user_rules` | Custom AI rules from ai_rules.yml | Always include (small, fixed) |
| `rag` | Retrieved documents | Preserve top results (start position) |
| `memory` | Retrieved memories | Preserve most relevant |
| `discovery` | System discovery facts | Preserve most relevant |
| `conversation` | Conversation history | Preserve recent (end position) |
| `observations` | Tool execution outputs | Preserve recent |
| `self_knowledge` | Self-RAG reflection | Preserve if retrieved |

**Budget table (v1, to be tuned empirically):**

| Model tier | Total | system_identity | user_rules | rag | memory | discovery | conversation | observations | self_knowledge |
|-----------|-------|-----------------|------------|-----|--------|-----------|-------------|-------------|----------------|
| tiny (1-3B) | 400 | 50 | 50 | 50 | 0 | 50 | 100 | 50 | 50 |
| small (4-8B) | 800 | 75 | 75 | 100 | 50 | 75 | 200 | 75 | 50 |
| medium (9-20B) | 2000 | 100 | 100 | 300 | 150 | 200 | 500 | 200 | 150 |
| large (21-40B) | 4000 | 150 | 150 | 600 | 300 | 400 | 1000 | 400 | 300 |
| xlarge (40B+) | 8000 | 200 | 200 | 1200 | 600 | 800 | 2000 | 800 | 600 |
| massive (MoE 262K+) | 16000 | 400 | 400 | 2400 | 1200 | 1600 | 4000 | 1600 | 1200 |

**Note:** These are starting values. The other codebase's "Pass 1.5 findings" were empirically
derived for roleplay persona accuracy. Halbert needs its own empirical tuning for sysadmin
task accuracy. The table should be marked as "v1, needs tuning" and adjusted based on
observability data (Tier 2 item 3.5).

### 4.6 Integration points

**Current chat path (`chat.py`):**
The `send_message()` handler calls `intake.pipeline.analyze(message)` at the top, replacing
the scattered calls to `detect_query_topics`, `should_use_tools`, `should_use_web_search`,
`_score_query_complexity`, and the inline `unclear_query` check. The `MessageIntake` result
feeds:
- Model selection: `intake.recommended_model` replaces the inline complexity routing
- Context assembly: `intake.context_budget.total` replaces the hardcoded `max_tokens=8000`
- RAG decision: `intake.needs_retrieval` replaces `unclear_query`
- ReAct decision: `intake.needs_tools` replaces `should_use_tools` + complexity ≥ 0.4

**Agent path (`agent.py`):**
The agent state machine calls `intake.pipeline.analyze(message)` before entering the PLANNING
state. The `MessageIntake` feeds:
- `advance_turn`: intent and complexity score shape the cognitive tick
- Context assembler: budget and needs_retrieval
- Model selection: recommended_model
- Tool routing: needs_tools

**Context assembler (`context/assembler.py`):**
The `assemble()` method gains an optional `intake: MessageIntake = None` parameter. When
provided, it uses `intake.context_budget.total` as `max_tokens` instead of the default 8000,
and `intake.complexity_score` to adjust budget ratios (Tier 2 item 3.4). When not provided
(legacy callers), it falls back to current behavior.

---

## 5. Implementation Order

### Phase 1: Foundation (no LLM dependency, fully testable)

1. **`intake/signals.py`** — Zero-LLM signal detection. Adapt the other codebase's
   `signals.py` for sysadmin context. No external dependencies. Write tests for each signal
   type (greeting, farewell, question, troubleshooting, domains, error indicators, code
   blocks, file paths).

2. **`intake/budget.py`** — Model-tier context budget manager. Adapt the other codebase's
   `budget_manager.py`. No external dependencies (no VRAM detection in v1). Write tests for
   tier detection (model name → tier) and budget allocation (tier → per-category budgets).

3. **`intake/__init__.py`** — Export the public API.

### Phase 2: Complexity routing (needs a running model)

4. **`intake/complexity.py`** — LLM-based complexity router with cache. Adapt the other
   codebase's `complexity_router.py`. Uses the guide model (via `model/client.py`'s
   `call_llm_chat`). Write tests with mocked LLM responses (test caching, fast-path gating,
   threshold mapping).

### Phase 3: Orchestration

5. **`intake/pipeline.py`** — The `analyze()` function that chains signals → complexity →
   budget and produces `MessageIntake`. Write integration tests.

### Phase 4: Wiring

6. **Wire into `context/assembler.py`** — Add optional `intake` parameter to `assemble()`.
   Use budget total as `max_tokens`. (Tier 2 complexity-aware ratios can come later.)

7. **Wire into `dashboard/routes/chat.py`** — Replace scattered intake logic with a single
   `intake.pipeline.analyze(message)` call at the top of `send_message()`. This is the
   migration step — the old functions stay as thin wrappers during transition.

8. **Wire into `dashboard/routes/agent.py`** — Add intake call before PLANNING state. Feed
   `MessageIntake` to `advance_turn` and context assembly.

### Phase 5: Observability (Tier 2)

9. **Stats endpoint** — `/api/intake/stats` returning complexity distribution, cache hit rate,
   avg latency, model selection counts.

10. **Complexity-aware budget ratios** — Extend `_allocate_budget` with complexity axis.

### What NOT to do in this phase

- Do not port epistemic parsing, scene detection, scene memory, or model cycling.
- Do not add VRAM detection to the budget manager (defer to v2).
- Do not add entity extraction (defer until SourcePrep integration proves whether it's
  needed).
- Do not build a separate analyzer model loader — use the guide model.
- Do not replicate `should_use_web_search` keyword logic in the intake module — defer to F4.
- Do not add emotion detection — sysadmin assistant doesn't need it (yet).

---

## 6. Risks and Edge Cases

### 6.1 Latency budget

The intake pipeline adds latency before the first LLM response:
- Signals: <1ms (negligible)
- Complexity: ~50-100ms first call, <1ms cache hit
- Budget: <1ms (negligible)
- Total: ~50-100ms for uncached messages, <2ms for cached

This is acceptable — the current code already makes RAG/web search calls that take 100-500ms
before the LLM responds. The complexity call can run in parallel with retrieval if needed
(future optimization).

**Mitigation:** The fast-path gating (greetings skip LLM call) ensures the most common trivial
messages have zero added latency.

### 6.2 Complexity router failure

If the guide model is down or times out, the complexity router must fail gracefully:
- Default to score=3 (moderate) — same as the other codebase's fallback
- Log the failure
- Continue with the guide model (safe default)

### 6.3 Budget table accuracy

The v1 budget table is adapted from the other codebase's roleplay findings, not empirically
tuned for sysadmin tasks. It may over- or under-allocate for Halbert's use cases.

**Mitigation:** Mark as "v1, needs tuning." The observability endpoint (Phase 5) provides the
data to tune. The table is a simple dict — easy to adjust without code changes.

### 6.4 Migration risk

Replacing the scattered intake logic in `chat.py` with a single pipeline call is a behavioral
change. The current logic has been tuned through use and may have implicit behaviors not
captured in the new pipeline.

**Mitigation:** Phase 4 step 7 keeps old functions as thin wrappers during transition. The new
pipeline and old logic can run side-by-side with logging to compare decisions. Full cutover
only after verification.

### 6.5 Agent path not yet boot-tested

From the-being.md §G1: "the full stack booting with the cognitive core installed (never yet
boot-tested end-to-end on the Ubuntu host)." The intake pipeline feeds `advance_turn`, which
hasn't been tested end-to-end on the target host.

**Mitigation:** The intake module is independently testable without the cognitive core. It
produces a `MessageIntake` that can be inspected and verified before the agent path is
boot-tested. The chat path wiring (Phase 4 step 7) provides a working integration without
requiring the agent path.

### 6.6 The `needs_web_search` question

The current `should_use_web_search` has two components: keyword pattern matching and RAG
freshness checking. The keyword patterns ("latest version", "cve", etc.) are exactly the kind
of heuristic F4 says to replace. The freshness check is more principled but lives in
`rag/freshness.py`.

**Decision:** The intake module sets `needs_web_search` based on signals only (keyword
patterns as a temporary bridge). The actual freshness-based decision stays in the
SearchingHandler. When SourcePrep lands, the keyword-based `needs_web_search` flag is removed
and the freshness check moves to SourcePrep's retrieval layer. This flag is explicitly marked
as "transitional, will be removed when F4 lands."

---

## 7. Relationship to Existing Design Documents

### 7.1 the-being.md

- **§1 "It triages, not monitors"** → The intake pipeline's `intent` classification
  (troubleshooting vs informational) directly supports triage. The complexity score ensures
  triage queries get the specialist model.
- **§2 "Everything carries its why"** → The `MessageIntake` carries the *why* of model
  selection (complexity_score) and context sizing (model_tier). This is the intake-level
  provenance for routing decisions.
- **§6 "One mind, many hands"** → The intake pipeline feeds the one mind (cognitive tick).
  It doesn't create a separate decision-maker — it produces metadata that the mind uses.
- **§9 "Keep: model layer + routing"** → This work deepens the model routing layer. It's
  explicitly in the "keep" list.

### 7.2 explorations.md

- **§A1 "Collapse to one conversation path"** → The intake module is agent-path-ready by
  design. It doesn't depend on `chat.py`. When chat.py retires, the agent path already uses
  it.
- **§F4 "What this replaces"** → The intake module does NOT replicate the keyword heuristics
  that F4 replaces. It provides the structural pieces (signals, complexity, budget) that
  survive the F4 transition. `needs_retrieval` and `needs_web_search` are explicitly
  transitional flags.
- **§G1 "Already wired"** → The intake pipeline feeds `advance_turn` (already wired via
  `cognition_wiring.py`). The `MessageIntake` provides the intent and complexity inputs that
  the cognitive tick needs.
- **§G2 "The missing predicates"** → The intake's `is_troubleshooting` signal is a precursor
  to the `worries_about` predicate. When the predicates land, the intake can feed them: a
  troubleshooting message about `/dev/sda1` → `worries_about(/dev/sda1)`.

### 7.3 RQ-D-CHAT-AUDIT-2026-08-22.md

The prior audit identified `chat.py` as having 69 distinct blocks of context injection logic.
This intake pipeline addresses the audit's "REFACTOR" verdicts for:
- A10 (`get_topic_context`) → replaced by `signals.detected_domains`
- A11 (`should_use_web_search`) → replaced by `intake.needs_web_search` (transitional)
- B7 (unclear query detection) → replaced by `intake.needs_retrieval`
- The complexity scoring in `model/client.py` → replaced by `intake.complexity.py`

The audit's "PORT" verdicts (telemetry, self-knowledge, system identity, custom rules) are
separate from this work — they belong in the context assembler's extra sources, not the intake
pipeline.

---

## 8. Test Strategy

### 8.1 Unit tests (`tests/test_intake_signals.py`)

Test each signal detector independently:
- Greeting detection: "hi", "hello", "hey", "good morning", "what's up"
- Farewell detection: "bye", "goodnight", "talk later", "heading out"
- Question detection: ends with "?", starts with wh-words
- Troubleshooting detection: "error", "failed", "broken", "not working", "won't start"
- Domain detection: "disk space" → storage, "ssh" → security, "nginx" → service
- Error indicators: "Error:", stack trace markers, "Traceback"
- Code blocks: ``` fences, indented code
- File paths: `/etc/nginx/nginx.conf`, `~/.config/halbert/models.yml`
- Message length: ≤3 words → short, >50 words → long

### 8.2 Unit tests (`tests/test_intake_budget.py`)

Test tier detection and budget allocation:
- `detect_model_tier("llama3.1:8b")` → SMALL
- `detect_model_tier("llama3.1:70b")` → XLARGE
- `detect_model_tier("qwen3:4b")` → TINY
- `get_context_budget("llama3.1:8b").total` → 800
- Budget allocation sums correctly
- Truncation preserves sentence boundaries

### 8.3 Unit tests (`tests/test_intake_complexity.py`)

Test with mocked LLM responses:
- LLM returns "3" → score=3, level=MODERATE
- LLM returns "5" → score=5, level=VERY_COMPLEX
- LLM returns garbage → fallback to 3
- LLM times out → fallback to 3
- Cache hit → cached=True, latency <1ms
- Fast path: greeting → score=1, no LLM call
- Fast path: troubleshooting → minimum score=3

### 8.4 Integration tests (`tests/test_intake_pipeline.py`)

Test the full pipeline:
- "hi" → intent=greeting, complexity=1, needs_retrieval=False, recommended_model=guide
- "why is nginx failing after the update?" → intent=troubleshooting, complexity≥3,
  needs_retrieval=True, recommended_model=specialist
- "show me disk usage" → intent=command, detected_domains=[storage], needs_tools=True
- "bye" → intent=farewell, complexity=1, needs_retrieval=False

---

## 9. Files to Create / Modify

### Create

| File | Purpose | Lines (est.) |
|------|---------|-------------|
| `halbert_core/halbert_core/intake/__init__.py` | Public API exports | ~20 |
| `halbert_core/halbert_core/intake/signals.py` | Zero-LLM signal detection | ~200 |
| `halbert_core/halbert_core/intake/budget.py` | Model-tier context budget manager | ~250 |
| `halbert_core/halbert_core/intake/complexity.py` | LLM-based complexity router | ~200 |
| `halbert_core/halbert_core/intake/pipeline.py` | Orchestrator, produces MessageIntake | ~100 |
| `tests/test_intake_signals.py` | Signal detection tests | ~150 |
| `tests/test_intake_budget.py` | Budget manager tests | ~100 |
| `tests/test_intake_complexity.py` | Complexity router tests (mocked) | ~120 |
| `tests/test_intake_pipeline.py` | Integration tests | ~80 |

### Modify

| File | Change | Risk |
|------|--------|------|
| `halbert_core/halbert_core/context/assembler.py` | Add optional `intake` parameter to `assemble()` | Low — additive, backward compatible |
| `halbert_core/halbert_core/dashboard/routes/chat.py` | Replace scattered intake logic with pipeline call | Medium — behavioral change, use wrappers during transition |
| `halbert_core/halbert_core/dashboard/routes/agent.py` | Add intake call before PLANNING state | Low — additive |
| `halbert_core/halbert_core/model/client.py` | Complexity scoring moves to `intake/complexity.py`; keep `_score_query_complexity` as deprecated wrapper | Low — backward compatible |

### Do not modify

| File | Reason |
|------|--------|
| `halbert_core/halbert_core/integrations/cognition_wiring.py` | The intake feeds advance_turn's inputs; it doesn't change the wiring |
| `halbert_core/halbert_core/prompts/` | Voice/prompt settings are separate from intake (A4 in explorations.md) |
| `config/models.yml` | Model config stays as-is; the budget manager reads it, doesn't change it |

---

## 10. Open Questions for the Reviewer

1. **Is the budget table's category set correct?** The proposed categories
   (system_identity, user_rules, rag, memory, discovery, conversation, observations,
   self_knowledge) match the assembler's current source types. Should `safety` be a separate
   category or folded into `user_rules`? Should `telemetry` be separate from `observations`?

2. **Should the complexity threshold be configurable?** The current design hardcodes 1-2 →
   guide, 3-5 → specialist. Should this be in `models.yml` or `being.yml`? The design docs put
   model config in `models.yml` and being preferences in `being.yml` — complexity threshold is
   arguably a model config concern, but it could also be a being preference ("I want the
   specialist for everything").

3. **Should `needs_tools` consider the domain?** Currently: `intent=troubleshooting AND
   complexity >= 3`. Should it also check `detected_domains`? E.g., a storage troubleshooting
   query should always consider tools (disk space check), but a "why is my config wrong"
   troubleshooting query might not need tools (it needs config analysis).

4. **Should the intake pipeline run on proactive messages too?** When the being initiates
   (proactive channel, §D), there's no user message to analyze. But the being's own message
   has an intent (finding report, morning report) and complexity. Should the pipeline have a
   separate entry point for self-generated messages, or is that a different flow entirely?

5. **Is the 1-5 complexity scale the right granularity?** The other codebase uses 1-5. Some
   systems use 1-3 (simple/moderate/complex). 1-5 gives more routing flexibility but requires
   more LLM calibration. The cognitive core's complexity input format should be checked — if
   it expects 1-3, we should match that.

6. **Should signals detect frustration?** The other codebase detects emotional tone. For a
   sysadmin assistant, detecting user frustration ("this is the third time I've asked",
   "why doesn't this work", "I'm so done with this") could tune response patience and
   thoroughness. Not in v1, but worth deciding whether to leave room for it in the
   `MessageSignals` dataclass.

7. **Does the intake pipeline need to handle multi-modal messages?** The current chat path
   handles images separately (vision model). Should the intake pipeline be aware of
   attachments, or is that a separate flow? The `MessageIntake` currently has no
   `has_attachments` field.

8. **Should the budget manager handle the compression cascade threshold?** The assembler
   compresses when context >4000 tokens (hardcoded `_compressor_threshold`). Should this
   threshold scale with model tier? A tiny model might need compression at 300 tokens; a
   massive model might not need it until 12000.

---

## 11. Summary

The intake pipeline is a **structural upgrade** that brings three essential capabilities from
a more mature codebase, adapted for sysadmin context:

1. **Model-tier context budgeting** — stop degrading the 8B guide model with 8000 tokens
2. **LLM-based complexity routing** — stop missing nuanced complexity with keyword heuristics
3. **Signal/intent detection** — give the cognitive tick structured metadata about each turn

It deliberately skips roleplay-specific features (epistemic parsing, scene detection, scene
memory, model cycling) and defers features that SourcePrep will subsume (entity extraction,
keyword-based retrieval triggers).

The module is designed to survive the A1 chat path collapse and the F4 keyword heuristic
replacement — it's agent-path-ready and doesn't depend on the code that's scheduled for
removal.

Implementation is phased: foundation (signals + budget, no LLM needed) → complexity routing
(needs model) → orchestration → wiring → observability. Each phase is independently testable.

---

*This document is a design handoff for review. Implementation should not begin until the
reviewer has evaluated the open questions in §10 and confirmed the tier assignments in §3.*
