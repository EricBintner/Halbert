# Implementation Plan — Halbert Being Overhaul

**Created:** 2026-08-23
**Status:** Task-level implementation plan, ready for execution.
**Reads with:**
- `.handoff/ROADMAP-2026-08-23.md` (the phased roadmap — this document is its task-level decomposition)
- `.handoff/INTAKE-PIPELINE-DESIGN-2026-08-23.md` (intake pipeline design)
- `documentation/design/the-being.md` (the vision)
- `documentation/design/explorations.md` (the design-to-implementation catalog)

**Scope:** This plan covers Phases 0–8. Phase 0 (SourcePrep doc ingestion / RAG corpus cleanup) is detailed in `.handoff/RAG-OPTIMIZATION-PLAN-2026-08-23.md` and its tasks are included here for completeness. Phases 1–8 are the infrastructure spine and being layers. Each phase is broken into tasks with: file paths, interfaces, acceptance criteria, dependencies, and estimated effort.

**Convention:** Each task has an ID (e.g. `T0a.1`, `T1a.1`), a one-line summary, the files to create or modify, the interface or behavior to implement, and an acceptance check. Tasks are ordered within each phase.

---

## Phase 0: SourcePrep Doc Ingestion (the RAG corpus)

**Goal:** Clean the RAG corpus, convert to markdown, build the SourcePrep index. Detailed in `.handoff/RAG-OPTIMIZATION-PLAN-2026-08-23.md`.

**Verified corpus state (2026-08-23):**
- 30,749 docs across 57 JSONL files (manifest claims 59,878 — inflated for Linux sources)
- 1,902 empty docs (6.2%), concentrated in `man_pages.jsonl` (1,656) and `combined_all_output.jsonl` (246)
- 7,307 exact duplicates (23.8% — much higher than initially estimated)
- ~21,540 unique non-empty documents after cleanup
- 5 distinct JSONL schemas (verified by scanning all 57 files)
- `data/common/` directory exists with README but no JSONL files yet

---

### T0a.1 — Register "halbert-knowledge" as a SourcePrep project

**Create:** SourcePrep project config for the RAG corpus

**Implementation:**
- Create a SourcePrep project "halbert-knowledge" pointing at `data/staging/sourceprep/` (the markdown output from T0d.1)
- Configure `include_globs: ["**/*.md"]`
- Define scopes for platform routing:
  - `linux` → `linux-*/`
  - `macos` → `macos-*/`
  - `bsd` → `bsd-*/`
  - `common` → `common-*/`
- This is separate from "halbert-host" (T5a.1) which indexes the live config tree

**Acceptance:**
- SourcePrep project "halbert-knowledge" exists
- Scopes are defined for platform routing
- `prep build` succeeds on the project

**Dependencies:** T0d.1 (markdown files must exist first)

---

### T0b.1 — Remove empty documents from all JSONL files

**Create:** `scripts/remove_empty_docs.py`

**Implementation:**
- Scan all 57 JSONL files, remove docs with <50 chars of content
- Removes 1,902 empty docs (concentrated in `man_pages.jsonl` and `combined_all_output.jsonl`)
- Delete stale merged files entirely:
  - `data/linux/merged/rag_corpus_merged.jsonl` (2,990 docs, stale)
  - `data/linux/merged/combined_all_output_converted.jsonl` (246 docs, stale)
  - `data/linux/commands/combined_all_output.jsonl` (246 docs, 100% empty)
- Verify HF datasets for content quality (may not all be empty as initially thought)
- Dry-run mode: print counts without modifying

**Acceptance:**
- Zero docs with <50 chars remain
- Stale merged files deleted
- Non-empty doc count preserved
- Dry-run mode works

---

### T0b.2 — Clean Linux man page formatting

**Use:** `scripts/clean_man_pages.py` (already exists)

**Implementation:**
- Run the existing `clean_man_pages.py` on `data/linux/man-pages/man_pages.jsonl`
- Removes backspace (`\b`) formatting artifacts from 5,703 non-empty docs
- Same fix that was already applied to macOS man pages

**Acceptance:**
- No `\b` characters remain in man page content
- Man page text is human-readable

---

### T0b.3 — Normalize schema across all JSONL

**Create:** `scripts/normalize_schema.py`

**Implementation:**
- Convert all 5 schemas to a unified schema: `{"id", "url", "title", "content", "source", "category", "tags", "scraped_at", "metadata"}`
- Map from each schema:
  - `{text, metadata}` → content=text, title=metadata.man_page, source=metadata.source_type
  - `{name, section, description, full_text, metadata}` → content=full_text, title=name, source=metadata.source_type
  - `{content, description, metadata, name}` → content=content, title=name, source=metadata.source_type
  - `{commands, distro, explanation, goal, ...}` → content=explanation+commands, title=goal, source=metadata.source_type
  - `{id, url, title, content, source, category, tags, scraped_at, metadata}` → already unified
- Dry-run mode

**Acceptance:**
- All JSONL files use the unified schema
- No data loss (all fields mapped)
- Dry-run mode works

**Dependencies:** T0b.1 (clean empties first)

---

### T0c.1 — Cross-source exact dedup

**Create:** `scripts/dedup_corpus.py`

**Implementation:**
- Hash full content across ALL sources (not per-source)
- Remove exact duplicates, keeping the first occurrence
- Expected: ~7,307 duplicates removed (23.8% of corpus)
- Report: which sources had the most duplicates, what was duplicated

**Acceptance:**
- Zero exact content duplicates remain
- Report shows what was removed
- Non-duplicate doc count preserved

**Dependencies:** T0b.3 (normalized schema first)

---

### T0c.2 — Man page near-duplicate resolution

**Create:** `scripts/manpage_near_dedup.py`

**Implementation:**
- For the 91 commands in both macOS and FreeBSD man pages:
  - If content is >85% similar (Jaccard on word sets): keep the longer version
  - If content differs significantly: keep both
- Manual spot-check of a few examples

**Acceptance:**
- Near-duplicate man pages resolved
- Both versions kept when they differ significantly
- Spot-check documented

**Dependencies:** T0c.1

---

### T0d.1 — Convert JSONL to grouped markdown files

**Create:** `halbert_core/halbert_core/rag/jsonl_to_markdown.py`

**Implementation:**
- One `.md` file per JSONL source (or split large sources — see roadmap §3)
- **Split large sources into multiple files** (500 docs or 500KB per file) to avoid SourcePrep's large-file truncation
- Each doc as an H2 section with metadata as HTML comment header
- Output to `data/staging/sourceprep/` with directory structure mirroring source
- Handles the unified schema from T0b.3

**Acceptance:**
- All JSONL files converted to markdown
- H2 headings match doc count
- Large sources are split (no file >500KB)
- Metadata preserved in HTML comments

**Dependencies:** T0c.1 (deduped first)

---

### T0e.1 — Corpus quality gate

**Create:** `scripts/corpus_quality_gate.py`

**Implementation:**
- A set of ~20 test queries with expected source matches
- Run against the built SourcePrep index
- Verify retrieval returns relevant results (not empty docs, not duplicates)
- Measure: precision (right source in top-k?), coverage (any source from expected domain?)

**Acceptance:**
- All 20 test queries return relevant results
- No empty docs in results
- No exact duplicates in results

**Dependencies:** T0a.1 (SourcePrep project built)

---

### T0e.2 — Create retrieval eval script

**Create:** `scripts/retrieval_eval.py`

**Implementation:**
- 20-50 test queries spanning domains (storage, network, security, macOS, Linux, BSD)
- For each query, the expected source(s) that should be retrieved
- Run retrieval, measure precision and coverage
- Run before cleanup, after cleanup, after SourcePrep wiring — to quantify improvement

**Acceptance:**
- Eval script runs end-to-end
- Reports precision and coverage metrics
- Can be run before and after changes

**Dependencies:** T0a.1

---

### T0f.1 — Create data/common/ for cross-platform docs

**Modify:** `data/common/` (directory exists, needs content)

**Implementation:**
- Move cross-platform content from `linux/` to `common/`:
  - git, ssh, bash, grep, sed, awk, curl, wget, vim, emacs
- These work identically on Linux and macOS
- Update platform loader to load `common/` for all platforms
- Avoids duplicating these docs in both platform-specific corpora

**Acceptance:**
- Cross-platform docs in `data/common/`
- Platform loader includes `common/` for all platforms
- No duplication of cross-platform docs

**Dependencies:** T0b.3 (normalized schema first)

---

### T0g.1 — Replace empty HF datasets with clean ones

**Implementation:**
- Download `hannah-eee/arch-wiki-docs` from HuggingFace (~10K clean pages)
- Download TLDR pages from `tldr-pages/tldr` GitHub repo (~6K summaries)
- Convert to JSONL with unified schema
- Verify content quality before replacing

**Acceptance:**
- New datasets have content (not empty)
- Unified schema
- Replaces stale HF datasets

**Dependencies:** T0b.1 (empties removed first)

---

### T0g.2 — Update manifest and configs

**Modify:** `data/manifest.json`, `config/approved_sources.yml`

**Implementation:**
- Update `manifest.json` with actual document counts (not inflated)
- Remove deleted sources
- Add new sources (arch-wiki-docs, tldr-pages)
- Bump version to 2.0.0 (breaking change to corpus)
- Add HuggingFace and tldr-pages GitHub as approved sources

**Acceptance:**
- Manifest counts match actual JSONL line counts
- New sources listed
- Version bumped

**Dependencies:** All above tasks

---

## Phase 1: Intake Pipeline (parallel with Phase 0, no dependencies)

**Goal:** A standalone `intake/` module that analyzes incoming messages before the cognitive tick runs. Zero-LLM signal detection, LLM-based complexity routing, model-tier context budgeting.

**Code seams verified:**
- `dashboard/routes/chat.py:862` — `should_use_tools()` (keyword matching, being replaced)
- `dashboard/routes/chat.py:963` — `TOPIC_KEYWORDS` dict (5 categories, being replaced)
- `dashboard/routes/chat.py:983` — `should_use_web_search()` (keyword + freshness, being replaced)
- `dashboard/routes/chat.py:1059` — `detect_query_topics()` (keyword matching, being replaced)
- `dashboard/routes/chat.py:2320` — inline `unclear_query` check (being replaced)
- `model/client.py:260` — `_score_query_complexity()` (keyword/regex heuristic, being replaced)
- `model/client.py:206` — `_truncate_messages_for_context()` (crude 4 chars/token estimate)
- `model/client.py:130` — `call_llm_chat()` (the LLM call interface the complexity router will use)
- `context/assembler.py:91` — `assemble()` with `max_tokens: int = 8000` (the flat budget being replaced)
- `context/assembler.py:233` — `_allocate_budget()` (already takes `max_tokens` as parameter)
- `config/models.yml` — model config (orchestrator: `qwen2.5:14b-instruct-q4_0`, specialist: `qwen2.5:32b`, vision: `qwen3-v1:32b`)

---

### T1a.1 — Create `intake/signals.py`: signal detection dataclass

**Create:** `halbert_core/halbert_core/intake/__init__.py`, `halbert_core/halbert_core/intake/signals.py`

**Interface:**
```python
@dataclass
class MessageSignals:
    intent: str = "informational"  # question|command|troubleshooting|informational|greeting|farewell
    is_question: bool = False
    is_greeting: bool = False
    is_farewell: bool = False
    is_troubleshooting: bool = False
    message_length: str = "normal"    # short|normal|long
    detected_domains: list[str] = field(default_factory=list)  # storage|network|security|service|backup|config
    has_error_indicators: bool = False
    has_code_blocks: bool = False
    has_file_paths: bool = False
```

**Implementation:**
- `GREETING_PATTERNS`: regex for "hi", "hello", "hey", "good morning", "what's up", "howdy"
- `FAREWELL_PATTERNS`: regex for "bye", "goodnight", "talk later", "heading out", "see ya"
- `ERROR_INDICATORS`: "error", "failed", "broken", "not working", "won't start", "traceback", "panic", "segfault"
- `DOMAIN_KEYWORDS`: dict mapping domain → keyword list (reuse the 5 categories from `chat.py:963` TOPIC_KEYWORDS, add "config")
- `FILE_PATH_REGEX`: `/[a-zA-Z0-9._~/-]+` pattern, `~/.config/` patterns
- `CODE_BLOCK_REGEX`: ```` ``` ```` fences, 4-space indented blocks
- `COMMAND_VERBS`: show, list, check, run, install, configure, enable, disable, restart, stop, start, update, remove, create, delete
- `analyze_message(message: str) -> MessageSignals`: pure function, <1ms, zero LLM, zero external deps
- Intent derivation: greeting > farewell > troubleshooting/error > question > command (starts with verb) > informational
- Message length: <=3 words → short, >50 words → long, else normal

**Acceptance:**
- `analyze_message("hi")` → intent="greeting", is_greeting=True, message_length="short"
- `analyze_message("why is nginx failing after the update?")` → intent="troubleshooting", is_troubleshooting=True, detected_domains=["service"], has_error_indicators=True, is_question=True
- `analyze_message("show me disk usage")` → intent="command", detected_domains=["storage"]
- `analyze_message("bye")` → intent="farewell", is_farewell=True
- `analyze_message("check /etc/nginx/nginx.conf")` → has_file_paths=True, detected_domains=["service"]
- Runs in <1ms (no I/O, no LLM)
- Zero imports from `chat.py`, `agent.py`, `model/`, `context/`, `integrations/`

---

### T1a.2 — Create `intake/signals.py`: tests

**Create:** `halbert_core/halbert_core/tests/test_intake_signals.py`

**Tests:** One test per signal type, covering the acceptance cases above plus edge cases:
- Empty string → intent="informational", all flags False
- Multi-domain: "check ssh config and disk space" → detected_domains=["security", "storage", "config"]
- Code block inside message → has_code_blocks=True
- Stack trace → has_error_indicators=True
- Long message (60 words) → message_length="long"
- "what's the latest version of nginx" → is_question=True, detected_domains=["service"]

**Acceptance:** All tests pass. `pytest tests/test_intake_signals.py -v` green.

---

### T1b.1 — Create `intake/budget.py`: ModelTier enum and ContextBudget dataclass

**Create:** `halbert_core/halbert_core/intake/budget.py`

**Interface:**
```python
class ModelTier(Enum):
    TINY = "tiny"        # 1-3B
    SMALL = "small"      # 4-8B
    MEDIUM = "medium"    # 9-20B
    LARGE = "large"      # 21-40B
    XLARGE = "xlarge"    # 40B+
    MASSIVE = "massive"  # MoE 262K+

@dataclass
class ContextBudget:
    tier: ModelTier
    total: int
    system_identity: int
    user_rules: int
    retrieval: int
    memory: int
    discovery: int
    conversation: int
    observations: int
```

**Implementation:**
- `CONTEXT_BUDGETS: dict[ModelTier, ContextBudget]` — the v1 table from the intake design §4.5 (reconciled: no `self_knowledge`, `rag` renamed to `retrieval`)
- `detect_model_tier(model_name: str) -> ModelTier`: parse model name for size hints
  - `qwen2.5:14b` → MEDIUM, `qwen2.5:32b` → LARGE, `llama3.1:8b` → SMALL, `llama3.1:70b` → XLARGE
  - Match patterns: `:Nb` or `-Nb` suffix, `MoE`/`moe` → MASSIVE
  - Fallback: MEDIUM (safe default)
- `get_context_budget(model_name: str) -> ContextBudget`: `detect_model_tier` → lookup `CONTEXT_BUDGETS`
- No VRAM detection, no GPU queries, no external deps

**Budget table (v1):**

| Tier | Total | sys_id | rules | retrieval | memory | discovery | conv | obs |
|------|-------|--------|-------|-----------|--------|-----------|------|-----|
| tiny | 400 | 50 | 50 | 50 | 25 | 50 | 100 | 75 |
| small | 800 | 75 | 75 | 100 | 75 | 75 | 200 | 100 |
| medium | 2000 | 100 | 100 | 300 | 225 | 200 | 500 | 275 |
| large | 4000 | 150 | 150 | 600 | 450 | 400 | 1000 | 550 |
| xlarge | 8000 | 200 | 200 | 1200 | 900 | 800 | 2000 | 1100 |
| massive | 16000 | 400 | 400 | 2400 | 1800 | 1600 | 4000 | 2200 |

**Acceptance:**
- `detect_model_tier("qwen2.5:14b-instruct-q4_0")` → MEDIUM
- `detect_model_tier("qwen2.5:32b")` → LARGE
- `detect_model_tier("llama3.1:8b")` → SMALL
- `get_context_budget("qwen2.5:14b-instruct-q4_0").total` → 2000
- `get_context_budget("llama3.1:8b").retrieval` → 100
- Budget fields sum to `total` for every tier
- Zero imports from `chat.py`, `agent.py`, `model/`, `context/`, `integrations/`

---

### T1b.2 — Create `intake/budget.py`: tests

**Create:** `halbert_core/halbert_core/tests/test_intake_budget.py`

**Tests:**
- Tier detection for all model patterns: `:8b`, `:14b`, `:32b`, `:70b`, `:405b`, `-8b`, `-70b`
- Unknown model → MEDIUM fallback
- Budget allocation sums correctly for every tier
- `get_context_budget` returns the right tier's allocation

**Acceptance:** `pytest tests/test_intake_budget.py -v` green.

---

### T1c.1 — Create `intake/complexity.py`: complexity router

**Create:** `halbert_core/halbert_core/intake/complexity.py`

**Interface:**
```python
class ComplexityLevel(Enum):
    TRIVIAL = 1
    SIMPLE = 2
    MODERATE = 3
    COMPLEX = 4
    VERY_COMPLEX = 5

@dataclass
class ComplexityResult:
    score: int           # 1-5
    level: ComplexityLevel
    reasoning: str = ""
    latency_ms: float = 0.0
    cached: bool = False

class ComplexityRouter:
    def __init__(self, llm_caller: Callable, guide_model: str, endpoint: str):
        ...
    def assess(self, message: str, signals: MessageSignals) -> ComplexityResult:
        ...
```

**Implementation:**
- `COMPLEXITY_PROMPT`: a 5-token-output prompt — "Rate the complexity of this sysadmin query as a single digit 1-5 (1=trivial, 5=very complex). Query: {message}\nRating:"
- `llm_caller`: injected callable wrapping `call_llm_chat` (for testability — tests pass a mock)
- LRU cache: `functools.lru_cache(maxsize=100)` keyed on message hash
- Fast paths (skip LLM):
  - `signals.is_greeting or signals.is_farewell` → score=1, cached=True, no LLM call
  - `signals.is_troubleshooting` → minimum score=3 (troubleshooting is never trivial)
- LLM call: `call_llm_chat(endpoint, guide_model, [{"role":"user","content": prompt}], options={"num_predict": 5, "temperature": 0.1})`
- Parse response: extract first digit 1-5 from response text; fallback to 3 on parse failure or timeout
- Stats tracking: `cache_hits`, `cache_misses`, `avg_latency_ms`, `score_distribution` (dict 1-5 → count)
- `get_stats() -> dict`: returns the tracked stats for the observability endpoint

**Threshold mapping (configurable, defaults in `models.yml`):**
- Score 1-2 → guide model (orchestrator)
- Score 3-5 → specialist model
- The threshold lives in `config/models.yml` under `routing.complexity_threshold` (default: 3)

**Acceptance:**
- Greeting → score=1, no LLM call, cached=True, latency <1ms
- Farewell → score=1, no LLM call
- Troubleshooting → score >= 3 (even if LLM returns 1, floor is 3)
- LLM returns "4" → score=4, level=COMPLEX
- LLM returns garbage → fallback score=3
- LLM times out → fallback score=3, no exception raised
- Repeated message → cache hit (cached=True, latency <1ms)
- `get_stats()` returns non-empty dict after assessments

---

### T1c.2 — Create `intake/complexity.py`: tests

**Create:** `halbert_core/halbert_core/tests/test_intake_complexity.py`

**Tests (all with mocked LLM caller):**
- Mock returns "3" → score=3, level=MODERATE
- Mock returns "5" → score=5, level=VERY_COMPLEX
- Mock returns "garbage" → fallback score=3
- Mock raises TimeoutError → fallback score=3, no exception
- Greeting signals → score=1, mock not called
- Farewell signals → score=1, mock not called
- Troubleshooting signals + mock returns "1" → score=3 (floor applied)
- Same message twice → second call cached=True
- Stats accumulate correctly

**Acceptance:** `pytest tests/test_intake_complexity.py -v` green.

---

### T1d.1 — Create `intake/pipeline.py`: orchestrator

**Create:** `halbert_core/halbert_core/intake/pipeline.py`

**Interface:**
```python
@dataclass
class MessageIntake:
    # From signals
    intent: str
    is_question: bool
    is_greeting: bool
    is_farewell: bool
    is_troubleshooting: bool
    message_length: str
    detected_domains: list[str]
    has_error_indicators: bool
    has_code_blocks: bool
    has_file_paths: bool
    # From complexity
    complexity_score: int
    complexity_level: str
    complexity_cached: bool
    complexity_latency_ms: float
    # From budget
    model_tier: str
    context_budget: ContextBudget
    recommended_model: str  # "guide" | "specialist" | "vision"
    # Derived
    needs_retrieval: bool
    needs_tools: bool
    needs_web_search: bool  # transitional, deferred to F4

class IntakePipeline:
    def __init__(self, complexity_router: ComplexityRouter, budget_fn: Callable, model_config: dict):
        ...
    def analyze(self, message: str) -> MessageIntake:
        ...
```

**Implementation:**
- `analyze()` chains: `signals.analyze_message(message)` → `complexity_router.assess(message, signals)` → `budget.get_context_budget(selected_model)` → derive flags
- Model selection: complexity score vs threshold from `model_config["routing"]["complexity_threshold"]` (default 3)
- `needs_retrieval`: False for greeting/farewell, True for everything else
- `needs_tools`: True if `intent == "troubleshooting" AND complexity_score >= 3`
- `needs_web_search`: transitional — True if message contains "latest version", "cve", "compare" patterns (marked for removal when F4 lands)
- `recommended_model`: "guide" if score < threshold, "specialist" if score >= threshold and specialist enabled, "vision" if image attachment detected (future)

**Acceptance:**
- `analyze("hi")` → intent="greeting", complexity_score=1, needs_retrieval=False, recommended_model="guide"
- `analyze("why is nginx failing after the update?")` → intent="troubleshooting", complexity_score>=3, needs_retrieval=True, needs_tools=True, recommended_model="specialist"
- `analyze("show me disk usage")` → intent="command", detected_domains=["storage"], needs_tools=True (if complexity >= 3)
- `analyze("bye")` → intent="farewell", complexity_score=1, needs_retrieval=False
- Total latency: <100ms for uncached messages, <2ms for cached

---

### T1d.2 — Create `intake/pipeline.py`: tests

**Create:** `halbert_core/halbert_core/tests/test_intake_pipeline.py`

**Tests:** Integration tests using a real `IntakePipeline` with mocked complexity router.
- All acceptance cases from T1d.1
- Verify `MessageIntake` fields are populated correctly from all three stages
- Verify derived flags are correct

**Acceptance:** `pytest tests/test_intake_pipeline.py -v` green.

---

### T1e.1 — Create `intake/__init__.py`: public API

**Create:** `halbert_core/halbert_core/intake/__init__.py`

**Exports:**
```python
from .signals import MessageSignals, analyze_message
from .budget import ModelTier, ContextBudget, detect_model_tier, get_context_budget
from .complexity import ComplexityLevel, ComplexityResult, ComplexityRouter
from .pipeline import MessageIntake, IntakePipeline
```

**Acceptance:** `from halbert_core.intake import IntakePipeline, MessageIntake` works.

---

## Phase 2: RAG Consolidation (depends on Phase 0)

**Goal:** SourcePrep becomes the sole retrieval backend on the chat path. ChromaDB is retired from the chat path (kept for eval + non-chat producers).

**Code seams verified:**
- `context/adapters.py:18` — `RAGServiceAdapter` (ChromaDB-backed, async `search()`)
- `integrations/sourceprep_retrieval_backend.py:29` — `SourcePrepRetrievalBackend` (SourcePrep-backed, sync `search()`)
- `integrations/app_seam.py:154` — `HalbertAppSeam` already wires `SourcePrepRetrievalBackend` as the Haloysius `RetrievalBackend`
- `integrations/app_seam.py:213` — `wire_halbert_seam()` already calls `register_app_seam(seam)`
- `index/chroma_index.py:369` — 7 collections: `self_knowledge_all`, `self_conversations`, `self_hwmon`, `self_journald`, `self_dbus`, `linux_docs`, `discoveries`
- `context/assembler.py:552` — source_type "rag" handling in `_format_source()`
- `context/assembler.py:635` — source_type "rag" handling in compression cascade

---

### T2a.1 — Wire SourcePrepRetrievalBackend into ContextAssembler

**Modify:** `halbert_core/halbert_core/context/assembler.py`

**Changes:**
- The assembler currently uses `RAGServiceAdapter` for the "rag" source type
- Add a `SourcePrepAdapter` class (or reuse `SourcePrepRetrievalBackend` directly) as the retrieval adapter
- The `SourcePrepRetrievalBackend.search()` is sync but the assembler expects async — wrap with `asyncio.to_thread()` or make a thin async wrapper
- In `_retrieve_rag()` (line 372), replace the `RAGServiceAdapter` call with the SourcePrep adapter
- The adapter maps `query` → `SourcePrepRetrievalBackend.search(query, k=5, figure_id=scope)` and formats results into the assembler's expected dict shape: `{"content": str, "tokens": int, "source": "rag", "items": [...]}`

**Acceptance:**
- `assemble()` with a query returns context that includes SourcePrep results
- SourcePrep daemon down → graceful degradation (empty results, warning log, no crash)
- ChromaDB `RAGServiceAdapter` is no longer called on the chat path
- Existing tests still pass (backward compat for `include_sources`)

---

### T2a.2 — Update assembler source model

**Modify:** `halbert_core/halbert_core/context/assembler.py`

**Changes:**
- Rename source type "rag" → "retrieval" in `_format_source()` and compression cascade
- Remove "self_knowledge" source type (no longer a retrieval source after Phase 2c)
- Keep: "conversation", "memory", "discovery", "observations", "system_identity", "telemetry", "safety"
- Update `self.priorities` dict to reflect new source names

**Acceptance:**
- Assembler produces context with "retrieval" source type (not "rag")
- No "self_knowledge" source type in output
- All other source types unchanged

---

### T2b.1 — Retire ChromaDB from the chat path

**Modify:** `halbert_core/halbert_core/context/adapters.py`

**Changes:**
- `RAGServiceAdapter`: add deprecation warning in `__init__` ("RAGServiceAdapter is deprecated on the chat path, use SourcePrepAdapter. Kept for CLI eval only.")
- Do not remove the class — it's kept for eval tooling per the roadmap

**Acceptance:**
- `RAGServiceAdapter` still importable and functional (for eval)
- Deprecation warning logged on instantiation
- No chat-path code imports `RAGServiceAdapter`

---

### T2c.1 — Migrate `self_knowledge_all` → SourcePrep observations

**Create:** `halbert_core/halbert_core/tools/migrate_self_knowledge.py`

**Implementation:**
- Read all records from ChromaDB `self_knowledge_all` collection
- For each record, call `SourcePrepClient.save_observation()` with:
  - `content`: the record's text/content
  - `file_path`: the record's source path (if available)
  - `tags`: ["self_knowledge", "migrated"]
  - `metadata`: the record's metadata dict
- Track success/failure counts
- Dry-run mode: print what would be migrated, don't write

**Acceptance:**
- Script runs without errors
- All `self_knowledge_all` records appear in SourcePrep observations
- `SourcePrepClient.search_observations()` returns migrated content
- Dry-run mode prints counts without writing

---

### T2c.2 — Migrate `self_conversations` → memory_v2

**Create:** `halbert_core/halbert_core/tools/migrate_conversations.py`

**Implementation:**
- Read all records from ChromaDB `self_conversations` collection
- For each record, write to Haloysius memory_v2 store via the memory API
- Map ChromaDB record fields → memory_v2 entry fields
- Dry-run mode

**Acceptance:**
- All `self_conversations` records appear in memory_v2
- Haloysius memory retrieval returns migrated content
- Dry-run mode prints counts without writing

---

### T2c.3 — Document the 4 collections that stay on ChromaDB

**Modify:** `halbert_core/halbert_core/index/chroma_index.py`

**Changes:**
- Add a comment block at the top documenting that `self_hwmon`, `self_journald`, `self_dbus`, and `discoveries` stay on ChromaDB (off chat path) until their producers are rewired
- No code changes — just documentation

**Acceptance:** Comment block present and accurate.

---

## Phase 3: Intake Wiring (depends on Phase 1 + Phase 2)

**Goal:** Wire the intake pipeline into the agent path. Skip chat.py entirely.

**Code seams verified:**
- `dashboard/routes/agent.py:414` — `send_message()` handler (the entry point)
- `agents/state_machine.py:24` — `AgentStateMachine` class
- `agents/state_machine.py:135` — `process()` method (yields StreamEvents)
- `agents/states.py:14` — `AgentState` enum (IDLE, PLANNING, SEARCHING, READING, EXECUTING, OBSERVING, REFLECTING, RESPONDING, AWAITING_CONFIRMATION, ERROR)
- `agents/state_machine.py:155` — cognition tick injection point (already wired via `cognition_wiring.py`)
- `dashboard/routes/agent.py:181` — inline complexity routing (`score_query_complexity`, threshold 0.5)
- `dashboard/routes/agent.py:257` — duplicate inline complexity routing in `stream()` method

---

### T3a.1 — Wire intake into `AgentStateMachine.process()`

**Modify:** `halbert_core/halbert_core/agents/state_machine.py`

**Changes:**
- In `process()` (line 135), after creating `StateContext` (line 155), call `intake_pipeline.analyze(query)`:
  ```python
  from ..intake import IntakePipeline, MessageIntake
  # ... in __init__:
  self.intake = intake_pipeline  # injected dependency
  # ... in process():
  intake_result = self.intake.analyze(query) if self.intake else None
  self.ctx.intake = intake_result  # store on context for downstream states
  ```
- Add `intake: Optional[MessageIntake]` field to `StateContext`
- The PLANNING state uses `intake_result.intent` and `intake_result.complexity_score` to shape the plan
- The `recommended_model` from intake replaces the inline complexity routing at `agent.py:181` and `agent.py:257`

**Acceptance:**
- A message sent to the agent path triggers `intake.analyze()` before PLANNING state
- `StateContext.intake` is populated and accessible to all states
- Greeting messages skip retrieval (needs_retrieval=False)
- Troubleshooting messages route to specialist (recommended_model="specialist")

---

### T3a.2 — Wire intake into model selection

**Modify:** `halbert_core/halbert_core/dashboard/routes/agent.py`

**Changes:**
- In `AgentLLM.chat()` (line 163) and `AgentLLM.stream()` (line 229), replace the inline `score_query_complexity` + threshold 0.5 logic with:
  ```python
  if intake_result:
      model = specialist_model if intake_result.recommended_model == "specialist" else guide_model
  else:
      # fallback to old logic for backward compat
      complexity_score = score_query_complexity(prompt)
      model = specialist_model if complexity_score >= 0.5 else guide_model
  ```
- The intake result is passed from `process()` → `AgentLLM.chat()`/`stream()` via the context

**Acceptance:**
- Model selection uses intake's `recommended_model` when available
- Falls back to old logic when intake is None (backward compat)
- Specialist is selected for complex queries, guide for simple ones

---

### T3b.1 — Wire intake budget into ContextAssembler

**Modify:** `halbert_core/halbert_core/context/assembler.py`

**Changes:**
- `assemble()` gains optional parameter: `intake: Optional[MessageIntake] = None`
- When `intake` is provided:
  - Use `intake.context_budget.total` as `max_tokens` instead of default 8000
  - Use `intake.needs_retrieval` to gate the retrieval source (skip retrieval if False)
  - Use per-category budgets from `intake.context_budget` to override the flat `_allocate_budget` ratios
- When `intake` is None: fall back to current behavior (backward compat)

**Acceptance:**
- With intake: `max_tokens` matches the model tier's budget (e.g. 800 for small, 2000 for medium)
- With intake: greeting messages produce context with no retrieval source
- Without intake: behavior unchanged (8000 token default, all sources)

---

### T3b.2 — Wire intake into `AgentStateMachine` context assembly

**Modify:** `halbert_core/halbert_core/agents/state_machine.py`

**Changes:**
- When the state machine calls `assembler.assemble()`, pass `intake=self.ctx.intake`
- This is a one-line change in the state that triggers context assembly

**Acceptance:**
- Assembler receives the intake result and uses the model-tier budget
- Context size varies by model tier (smaller for guide, larger for specialist)

---

## Phase 4: chat.py Deprecation (depends on Phase 3)

**Goal:** Port chat.py's remaining unique features to agent.py, then retire chat.py endpoint-by-endpoint.

**Code seams verified:**
- `dashboard/routes/chat.py` — 3,914 lines
- `dashboard/routes/agent.py` — 736 lines (the survivor)
- `context/adapters.py:124` — `DiscoveryAdapter` (discovery context injection)
- `context/adapters.py` — extra adapters for telemetry, system_identity, safety (Phase C)

---

### T4a.1 — Inventory chat.py's unique features

**Create:** `halbert_core/halbert_core/tools/chat_audit.py` (temporary script)

**Implementation:**
- Scan `chat.py` for features that exist in chat.py but NOT in agent.py
- Categories: telemetry injection, failure correlation, config-edit blocks, vision/image handling, keyword→discovery injection
- For each feature, document: the function name, line range, what it does, and whether it's already replaced by Phase 2/3 work
- Output a markdown table

**Acceptance:** Audit document produced. Features clearly categorized as "port" vs "already replaced" vs "cut".

---

### T4a.2 — Port telemetry injection to agent path

**Modify:** `halbert_core/halbert_core/context/adapters.py` (or `extra_adapters.py`)

**Changes:**
- chat.py injects telemetry context (journald logs, hardware metrics) inline
- Port this to a `TelemetryAdapter` (may already exist in `extra_adapters.py` — verify)
- Register the adapter in the assembler's adapter list for the agent path

**Acceptance:**
- Agent path responses include telemetry context when relevant
- Telemetry injection works without chat.py

---

### T4a.3 — Port failure correlation to agent path

**Modify:** `halbert_core/halbert_core/agents/state_machine.py` or new handler

**Changes:**
- chat.py has logic to correlate multiple error indicators into a diagnosis
- Port this as a pre-processing step or a dedicated state in the state machine
- May fit as a new handler in the PLANNING state

**Acceptance:**
- Agent path can correlate multiple errors into a diagnosis
- Works without chat.py

---

### T4a.4 — Port config-edit blocks to agent path

**Modify:** `halbert_core/halbert_core/agents/state_machine.py`

**Changes:**
- chat.py has special handling for config-edit responses (diff blocks, apply/rollback)
- The agent path already has `write_config` tool access
- Port the response formatting for config edits

**Acceptance:**
- Agent path can propose and apply config edits with diff display
- Works without chat.py

---

### T4a.5 — Port vision/image handling to agent path

**Modify:** `halbert_core/halbert_core/agents/state_machine.py` or new handler

**Changes:**
- chat.py handles image attachments (vision model routing)
- Port the image detection and vision model routing to the agent path
- The intake pipeline's `has_attachments` field (future) can gate this

**Acceptance:**
- Agent path can process image attachments
- Vision model is selected for image queries

---

### T4b.1 — Retire chat.py endpoints one by one

**Modify:** `halbert_core/halbert_core/dashboard/routes/chat.py`, `halbert_core/halbert_core/dashboard/app.py`

**Changes:**
- For each endpoint in chat.py:
  1. Verify the equivalent functionality exists in agent.py
  2. Add a deprecation header to the chat.py endpoint response
  3. After verification period, remove the endpoint from the router
  4. Eventually delete chat.py entirely
- Update `app.py` router registration to remove chat.py routes as they're retired

**Acceptance:**
- Each chat.py endpoint is either deprecated or removed
- No frontend code calls retired endpoints
- Agent path handles all conversation traffic

---

## Phase 4.5: Boot-Test Gate (depends on Phase 4)

**Goal:** Verify the full stack boots end-to-end. Hard gate — Phases 5+ don't start until this passes.

---

### T4.5a.1 — Boot test on Ubuntu (target host)

**Manual verification:**
1. `pip install` the full stack: halbert-core + haloysius + SourcePrep daemon running
2. Start the dashboard: `python -m halbert_core.dashboard.app`
3. Send a message via the agent endpoint: `POST /api/agent/send` with `{"message": "hello"}`
4. Verify the full flow:
   - Intake runs (check logs for `IntakePipeline.analyze`)
   - Context assembled from SourcePrep (check logs for `SourcePrepRetrievalBackend.search`)
   - Cognitive tick fires (check logs for `advance_turn`)
   - LLM responds (SSE stream returns response)
5. Verify no ChromaDB dependency on the chat path:
   - Stop ChromaDB: `systemctl stop chromadb`
   - Send another message — should still work (degraded retrieval if SourcePrep is down, but no crash)
6. Verify intake routing:
   - Send "hi" → should use guide model, no retrieval
   - Send "why is nginx failing?" → should use specialist model, with retrieval

**Acceptance:**
- Full stack boots without errors
- Agent path responds end-to-end
- No ChromaDB dependency on chat path
- Intake routing works (guide for simple, specialist for complex)

---

### T4.5b.1 — Boot test on macOS (development host)

**Manual verification:**
- Same as T4.5a.1 but on macOS
- Note degraded sensors: journald unavailable (use log instead), MLX vs Ollama
- The being should still work — "I can't see journald on this body" is an honest answer

**Acceptance:**
- Full stack boots on macOS
- Agent path responds (may use MLX instead of Ollama)
- Graceful degradation for macOS-specific gaps

---

## Phase 5: The Why Data Model + Config Brain v1 (depends on Phase 4.5)

**Goal:** The being can detect config problems, attach their why, and propose fixes through the existing approval flow.

**Code seams verified:**
- `approval/engine.py:21` — `ApprovalStatus` enum (PENDING, APPROVED, REJECTED, EXPIRED)
- `approval/engine.py:30` — `ApprovalRequest` dataclass (id, task, action, reasoning, confidence, risk_level, system_state, affected_resources, simulation_result, timing, decision, audit)
- `approval/engine.py:78` — `ApprovalEngine` class (manages approval workflows)
- `approval/engine.py:132` — `request_approval()` method
- `tools/write_config.py:14` — `WriteConfig` tool (backup, dry_run, rollback, policy gate, audit)
- `config/edge_extractor.py:122` — `ConfigEdgeExtractor` class (extracts dependency edges from systemd, ini files, includes, fstab)
- `config/watcher.py:35` — `ConfigWatcher` class (watchdog-based file watcher with poll fallback)
- `config/snapshot.py:29` — `snapshot()` function (snapshots config files per manifest)
- `config/parser.py:34` — `parse()` function (parses config files: ini-like, yaml, json, text)
- `integrations/sourceprep_client.py:133` — `save_observation()` (writes to SourcePrep observations)
- `integrations/sourceprep_client.py:175` — `search_concepts()` (queries SourcePrep rationale store)
- `integrations/sourceprep_client.py:191` — `save_concept()` (writes to SourcePrep rationale store)
- `integrations/app_seam.py:213` — `wire_halbert_seam()` (already wires SourcePrep for the host config project)

---

### T5a.1 — Register host config tree as a SourcePrep project

**Create:** `halbert_core/halbert_core/tools/register_host_project.py`

**Implementation:**
- Create a SourcePrep project pointing at the config snapshot directory (from `config/snapshot.py`)
- Configure `include_globs` for OS-specific config paths:
  - Linux: `/etc/**/*.conf`, `/etc/**/*.cfg`, `/etc/**/*.yml`, `/etc/**/*.yaml`, `/etc/**/*.service`, `/etc/**/*.mount`, `/etc/fstab`, `/etc/ssh/sshd_config*`
  - macOS: `/Library/LaunchDaemons/**/*.plist`, `~/Library/LaunchAgents/**/*.plist`, `/etc/ssh/sshd_config*`
- Run `prep build` on the project
- Verify: `prep search "sshd config"` returns results from the host config tree

**Acceptance:**
- SourcePrep project "halbert-host" exists and is built
- Semantic search over host config returns relevant results
- SourcePrep concepts and observations are available for the config brain

---

### T5a.2 — Wire config watcher to re-index on changes

**Modify:** `halbert_core/halbert_core/config/watcher.py`

**Changes:**
- `ConfigWatcher` already calls `on_snapshot` callback when files change
- Add a callback that triggers SourcePrep re-indexing for the "halbert-host" project
- Use SourcePrep's incremental rebuild API (if available) or a debounced full rebuild

**Acceptance:**
- Editing a config file triggers a SourcePrep re-index within 5 seconds
- Search results reflect the new config after re-index

---

### T5b.1 — Create findings store

**Create:** `halbert_core/halbert_core/findings/__init__.py`, `halbert_core/halbert_core/findings/store.py`

**Interface:**
```python
class FindingStatus(Enum):
    OPEN = "open"
    SNOOZED = "snoozed"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"

@dataclass
class Finding:
    id: str
    detector: str           # which detector found this
    severity: str           # info | warning | critical
    title: str
    description: str
    # The four whys
    why_now: str            # what triggered this detection right now
    why_care: str           # consequence if ignored
    why_so: str             # the reasoning / evidence
    why_trust: list[str]    # provenance refs (log cursors, snapshot ids, path:lines)
    # Config refs
    affected_paths: list[str]
    affected_services: list[str]
    # State
    status: str = "open"
    created_at: str = ""
    snoozed_until: str = ""
    resolved_at: str = ""
    # Link to proposal if one exists
    proposal_id: Optional[str] = None

class FindingStore:
    def __init__(self, db_path: str): ...
    def add(self, finding: Finding) -> str: ...
    def get(self, finding_id: str) -> Optional[Finding]: ...
    def list_open(self) -> list[Finding]: ...
    def list_by_severity(self, severity: str) -> list[Finding]: ...
    def update_status(self, finding_id: str, status: str, **kwargs) -> bool: ...
    def snooze(self, finding_id: str, days: int) -> bool: ...
    def dismiss(self, finding_id: str, reason: str) -> bool: ...
```

**Implementation:**
- SQLite-backed (consistent with the approval engine's storage pattern)
- `db_path` defaults to `~/.local/share/halbert/findings.db`
- Auto-creates table on init
- `add()` generates UUID if not provided, sets `created_at` timestamp
- `snooze()` sets `snoozed_until` to now + N days, status to SNOOZED
- `dismiss()` sets status to DISMISSED, records the reason as a SourcePrep concept (why the user said it's not a problem)

**Acceptance:**
- Create, read, list, update operations work
- Snooze sets the correct future date
- Dismiss records the reason
- Zero imports from `chat.py`, `agent.py`

---

### T5b.2 — Create proposals store (extends approval engine)

**Create:** `halbert_core/halbert_core/findings/proposals.py`

**Interface:**
```python
class ProposalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"

@dataclass
class Proposal:
    id: str
    finding_id: str         # the finding this proposes to fix
    action: str             # what to do
    changes: list[dict]     # the config changes (path, key, old_value, new_value)
    dry_run_result: dict    # preview of the change
    blast_radius: list[str]  # affected paths/services from edge extractor
    # State
    status: str = "pending"
    created_at: str = ""
    approved_at: str = ""
    applied_at: str = ""
    rolled_back_at: str = ""
    rejection_reason: str = ""

class ProposalStore:
    def __init__(self, db_path: str): ...
    def add(self, proposal: Proposal) -> str: ...
    def get(self, proposal_id: str) -> Optional[Proposal]: ...
    def list_pending(self) -> list[Proposal]: ...
    def list_for_finding(self, finding_id: str) -> list[Proposal]: ...
    def update_status(self, proposal_id: str, status: str, **kwargs) -> bool: ...
```

**Integration with approval engine:**
- When a proposal is created, also create an `ApprovalRequest` via `ApprovalEngine.request_approval()`
- The `ApprovalRequest.task` = "Apply config change", `action` = proposal action, `reasoning` = finding's why_so, `affected_resources` = blast_radius
- When the approval is decided, update the proposal status accordingly
- When approved, execute via `WriteConfig.execute()` with `backup=True, dry_run=False, confirm=True`
- If execution fails, auto-rollback and set status to ROLLED_BACK

**Acceptance:**
- Proposals link to findings and to approval requests
- Approval flow works end-to-end: propose → approve → apply → verify
- Rollback works on failure
- Zero imports from `chat.py`

---

### T5b.3 — Tests for findings + proposals stores

**Create:** `halbert_core/halbert_core/tests/test_findings.py`, `halbert_core/halbert_core/tests/test_proposals.py`

**Tests:**
- Finding CRUD operations
- Snooze/dismiss with date verification
- Proposal CRUD operations
- Proposal-finding linkage
- Proposal-approval integration (mocked approval engine)

**Acceptance:** `pytest tests/test_findings.py tests/test_proposals.py -v` green.

---

### T5c.1 — Drop-in conflict detector

**Create:** `halbert_core/halbert_core/findings/detectors/dropin_conflicts.py`

**Interface:**
```python
class DropinConflictDetector:
    def __init__(self, config_dir: str, precedence_engine: PrecedenceEngine): ...
    def detect(self) -> list[Finding]: ...
```

**Implementation:**
- Scan for systemd drop-in directories (`*.service.d/`, `*.mount.d/`)
- Scan for sshd_config.d/ drop-ins
- For each service with drop-ins:
  - Use the precedence engine (T5d.1) to determine effective config
  - Check for conflicting directives (same key, different values across drop-in files)
  - If conflict found: create a Finding with:
    - `why_now`: "drop-in file X overrides Y with conflicting value"
    - `why_care`: "the effective config may not match intent — service may behave unexpectedly"
    - `why_so`: "drop-in Z sets Key=Value, but base file sets Key=OtherValue; drop-in wins by precedence"
    - `why_trust`: [path:lines for both files, snapshot id]
    - `affected_paths`: [both file paths]
    - `affected_services`: [service name]

**Acceptance:**
- Detects a simple sshd_config.d conflict (Port set in both base and drop-in)
- Detects a systemd drop-in conflict (ExecStart overridden)
- No false positives on non-conflicting drop-ins (additive directives)
- Findings have all four whys populated

---

### T5c.2 — fstab phantom detector

**Create:** `halbert_core/halbert_core/findings/detectors/fstab_phantom.py`

**Implementation:**
- Parse `/etc/fstab` (using `config/parser.py`)
- For each entry, check if the referenced device exists:
  - UUID=xxx → `blkid -U xxx` or check `/dev/disk/by-uuid/`
  - LABEL=xxx → `blkid -L xxx`
  - /dev/sdXN → check if device node exists
- If device not found: create a Finding with:
  - `why_now`: "fstab entry references device that does not exist"
  - `why_care`: "boot may hang or fail waiting for this device; or the mount will be skipped"
  - `why_so`: "fstab line N references UUID=xxx, but no block device with that UUID was found"
  - `why_trust`: [fstab path:line, blkid output snapshot]
  - `severity`: "warning" (boot may hang) or "critical" (root filesystem)

**Acceptance:**
- Detects a missing UUID in fstab
- No false positive on existing devices
- Finding has all four whys

---

### T5c.3 — Permissions hygiene detector

**Create:** `halbert_core/halbert_core/findings/detectors/permissions_hygiene.py`

**Implementation:**
- Check `~/.ssh/` directory and file permissions:
  - `~/.ssh/` should be 700
  - Private keys (`id_rsa`, `id_ed25519`, etc.) should be 600
  - `authorized_keys` should be 600
  - `config` should be 644 or 600
- Check for world-readable files in `/etc/` that contain secrets:
  - Files matching `*key*`, `*secret*`, `*password*`, `*.pem` with mode > 640
- For each violation: create a Finding with appropriate severity and whys

**Acceptance:**
- Detects a private key with mode 644
- Detects `~/.ssh/` with mode 755
- No false positive on correctly-permissioned files
- Findings have all four whys

---

### T5d.1 — Precedence resolution engine

**Create:** `halbert_core/halbert_core/findings/precedence.py`

**Interface:**
```python
class PrecedenceEngine:
    def __init__(self, config_dir: str = "/etc"): ...
    def resolve_sshd(self) -> dict: ...
    def resolve_systemd_unit(self, unit_name: str) -> dict: ...
```

**Implementation:**
- `resolve_sshd()`: reads `/etc/ssh/sshd_config` + all files in `/etc/ssh/sshd_config.d/*.conf` in alphabetical order; later files override earlier; returns a dict of effective key→value pairs
- `resolve_systemd_unit(unit_name)`: reads the base unit file + all drop-ins in `*.d/` directories; systemd precedence: drop-ins override base; within drop-ins, alphabetical order; returns a dict of effective directives
- Uses `config/parser.py` for parsing

**Acceptance:**
- `resolve_sshd()` returns the effective sshd config when drop-ins exist
- `resolve_systemd_unit("nginx.service")` returns effective directives with drop-ins
- Correctly handles: base-only (no drop-ins), drop-in-only overrides, additive directives (e.g., `ExecStartPost=` adds, doesn't replace)

---

### T5e.1 — Wire blast-radius from edge extractor

**Create:** `halbert_core/halbert_core/findings/blast_radius.py`

**Interface:**
```python
class BlastRadiusCalculator:
    def __init__(self, edge_extractor: ConfigEdgeExtractor): ...
    def calculate(self, path: str) -> list[str]: ...
```

**Implementation:**
- Uses `config/edge_extractor.py:ConfigEdgeExtractor` (already extracts dependency edges)
- `calculate(path)`: returns all paths/services that depend on the given path (direct dependents only — shallow)
- Example: `/etc/nginx/nginx.conf` → [nginx.service, websites that depend on nginx]

**Acceptance:**
- Changing a config file returns its known dependents
- Returns empty list for paths with no known dependents
- Does not traverse deeply (shallow only — deep traversal is future)

---

### T5f.1 — Wire propose-through-approval end-to-end

**Create:** `halbert_core/halbert_core/findings/proposal_generator.py`

**Interface:**
```python
class ProposalGenerator:
    def __init__(self, finding_store: FindingStore, proposal_store: ProposalStore,
                 approval_engine: ApprovalEngine, write_config: WriteConfig,
                 blast_radius: BlastRadiusCalculator): ...
    def generate_for_finding(self, finding_id: str) -> Optional[str]: ...
```

**Implementation:**
- For a given finding, generate a proposed config change:
  - Use the finding's `affected_paths` and `why_so` to determine the fix
  - For drop-in conflicts: propose removing or correcting the conflicting drop-in
  - For fstab phantoms: propose commenting out the entry
  - For permissions: propose `chmod` command
- Generate a dry-run preview via `WriteConfig.execute()` with `dry_run=True`
- Calculate blast radius via `BlastRadiusCalculator`
- Create a `Proposal` in the store
- Create an `ApprovalRequest` via the approval engine
- Return the proposal ID

**Acceptance:**
- A finding produces a proposal with a dry-run preview
- The proposal is linked to an approval request
- Approval → apply → verification works end-to-end
- Rejection → proposal status updated, no changes applied

---

## Phase 6: Being Config + Voice (depends on Phase 4.5, parallel with Phase 5)

**Goal:** The user can configure how they live with their computer — voice, proactivity, purpose.

**Code seams verified:**
- `dashboard/routes/settings.py:23` — `router = APIRouter()` (settings route)
- `dashboard/routes/settings.py:76` — `get_model_settings()` (existing settings endpoint pattern)
- `dashboard/frontend/src/pages/Settings.tsx:1070` — Tabs component with 6 tabs (system, ai, knowledge, safety, alerts, about)
- `dashboard/frontend/src/lib/api.ts` — API client
- `config/models.yml` — model config (where complexity threshold lives)

---

### T6a.1 — Create `being.yml` config schema

**Create:** `halbert_core/halbert_core/config/being_config.py`

**Interface:**
```python
@dataclass
class BeingConfig:
    voice: str = "first_person"       # first_person | the_computer | hybrid
    proactivity: str = "balanced"     # off | quiet | balanced | assertive
    purpose: str = ""                 # free text v1
    quiet_hours: Optional[dict] = None  # {"start": "22:00", "end": "07:00"}
    morning_report: Optional[dict] = None  # {"enabled": True, "time": "08:00"}
    category_overrides: dict = field(default_factory=dict)  # per-category proactivity overrides

def load_being_config(path: str = None) -> BeingConfig: ...
def save_being_config(config: BeingConfig, path: str = None) -> None: ...
```

**Implementation:**
- Default path: `~/.config/halbert/being.yml`
- YAML format, human-readable
- `load_being_config()`: reads YAML, returns `BeingConfig` with defaults for missing fields
- `save_being_config()`: writes YAML
- Validation: voice must be one of the 3 options, proactivity must be one of the 4 options

**Acceptance:**
- Default config loads when no file exists
- Round-trip: save → load preserves all fields
- Invalid values raise a clear error

---

### T6a.2 — Add being config API endpoints

**Modify:** `halbert_core/halbert_core/dashboard/routes/settings.py`

**Add endpoints:**
- `GET /api/settings/being` → returns current `BeingConfig` as JSON
- `POST /api/settings/being` → updates `BeingConfig` (validates, writes to `being.yml`)
- Follow the existing pattern of `get_model_settings()` / `update_model_settings()`

**Acceptance:**
- GET returns the current config (or defaults if no file)
- POST validates and persists
- Invalid values return 400 with a clear error message

---

### T6b.1 — Wire voice setting into prompt layer

**Modify:** `halbert_core/halbert_core/prompts/` (the prompt builder files)

**Changes:**
- Load `BeingConfig.voice` at prompt assembly time
- `first_person`: prompts use "I", "my", "me" (current behavior)
- `the_computer`: prompts use "this system", "the computer", "it"
- `hybrid`: mix — "I" for subjective experience, "the system" for objective facts
- The voice setting affects the system prompt's self-reference instructions, not the data
- The continuity renderer (Haloysius) renders state blocks in the configured voice

**Acceptance:**
- Setting voice to "the_computer" changes the being's self-reference in responses
- Setting voice to "first_person" restores current behavior
- Setting voice to "hybrid" produces a mix
- Voice setting persists across sessions

---

### T6c.1 — Add "Being" tab to Settings UI

**Modify:** `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx`

**Changes:**
- Add a 7th tab: "Being" (after "About")
- Tab content:
  - Voice picker: radio buttons for first_person / the_computer / hybrid
  - Proactivity dial: select for off / quiet / balanced / assertive
  - Quiet hours: time pickers for start/end
  - Morning report: toggle + time picker
  - Purpose: free-text textarea
- Save button calls `POST /api/settings/being`
- Load on mount calls `GET /api/settings/being`

**Acceptance:**
- Being tab appears in Settings
- Changing voice and saving persists the change
- Reloading the page shows the saved values
- UI is responsive and uses existing component library (Radix/Tailwind)

---

## Phase 7: The Proactive Channel (depends on Phase 5 + Phase 6)

**Goal:** The being can open the conversation on its own when it finds something worth saying.

**Code seams verified:**
- `dashboard/routes/websocket.py` — 37-line stub (being replaced by SSE)
- `dashboard/frontend/src/hooks/useWebSocket.ts` — existing WebSocket hook (being supplemented by SSE hook)
- `dashboard/frontend/src/hooks/useAgentStream.ts` — existing SSE hook for agent stream (pattern to follow)
- `autonomy/guardrails.py:22` — `GuardrailEnforcer` (confidence thresholds, budgets, safe mode)
- `scheduler/autonomous_tasks.py:39` — `AutonomousTask` base class
- `scheduler/engine.py` — scheduler engine
- `config/watcher.py:35` — `ConfigWatcher` (triggers on config changes)

---

### T7a.1 — Create the proactive event flow

**Create:** `halbert_core/halbert_core/proactive/__init__.py`, `halbert_core/halbert_core/proactive/events.py`

**Interface:**
```python
@dataclass
class ProactiveEvent:
    id: str
    type: str           # finding | morning_report | approval_request | system_anomaly
    severity: str       # info | warning | critical
    title: str
    body: str
    finding_id: Optional[str] = None
    proposal_id: Optional[str] = None
    created_at: str = ""

class ProactiveEventBus:
    def __init__(self): ...
    def publish(self, event: ProactiveEvent) -> None: ...
    def subscribe(self, callback: Callable[[ProactiveEvent], None]) -> str: ...
    def unsubscribe(self, sub_id: str) -> None: ...
    def get_recent(self, limit: int = 50) -> list[ProactiveEvent]: ...
```

**Implementation:**
- In-memory event bus (asyncio-compatible)
- `publish()` calls all subscribed callbacks asynchronously
- `get_recent()` returns the last N events from an internal ring buffer
- Thread-safe via asyncio locks

**Acceptance:**
- Published events reach all subscribers
- Recent events are retrievable
- No blocking on publish

---

### T7b.1 — Create SSE push transport

**Create:** `halbert_core/halbert_core/dashboard/routes/being.py`

**Interface:**
```python
router = APIRouter()

@router.get("/api/being/events")
async def being_events(request: Request):
    """SSE stream of proactive events."""
    # Subscribe to ProactiveEventBus
    # Yield events as SSE: data: {json}\n\n
    # Heartbeat every 15 seconds
    ...

@router.post("/api/being/events/{event_id}/snooze")
async def snooze_event(event_id: str, days: int = 7): ...

@router.post("/api/being/events/{event_id}/dismiss")
async def dismiss_event(event_id: str, reason: str = ""): ...
```

**Modify:** `halbert_core/halbert_core/dashboard/app.py` — register the new router

**Implementation:**
- SSE format: `data: {"type": "finding", "severity": "warning", ...}\n\n`
- Heartbeat: `: keepalive\n\n` every 15 seconds
- Snooze endpoint: calls `FindingStore.snooze(event_id, days)`
- Dismiss endpoint: calls `FindingStore.dismiss(event_id, reason)`
- Follow the pattern from `useAgentStream.ts` (existing SSE consumer)

**Acceptance:**
- `GET /api/being/events` returns an SSE stream
- Publishing an event on the bus pushes it to the SSE stream
- Snooze and dismiss endpoints work
- Heartbeat prevents connection timeout

---

### T7b.2 — Create frontend SSE hook for being events

**Create:** `halbert_core/halbert_core/dashboard/frontend/src/hooks/useBeingEvents.ts`

**Interface:**
```typescript
export interface BeingEvent {
  id: string;
  type: 'finding' | 'morning_report' | 'approval_request' | 'system_anomaly';
  severity: 'info' | 'warning' | 'critical';
  title: string;
  body: string;
  findingId?: string;
  proposalId?: string;
  createdAt: string;
}

export function useBeingEvents(): {
  events: BeingEvent[];
  snooze: (eventId: string, days?: number) => void;
  dismiss: (eventId: string, reason?: string) => void;
}
```

**Implementation:**
- Opens an `EventSource` connection to `/api/being/events`
- Parses SSE events into `BeingEvent` objects
- Maintains a list of recent events in state
- `snooze()` and `dismiss()` call the POST endpoints
- Auto-reconnects on connection loss
- Pattern follows `useAgentStream.ts`

**Acceptance:**
- Hook receives events in real-time
- Events list updates on new events
- Snooze and dismiss work
- Auto-reconnects after disconnection

---

### T7c.1 — Create the proactive gate

**Create:** `halbert_core/halbert_core/proactive/gate.py`

**Interface:**
```python
class ProactiveGate:
    def __init__(self, being_config: BeingConfig, guardrail_enforcer: GuardrailEnforcer): ...
    def should_notify(self, event: ProactiveEvent) -> tuple[bool, str]:
        """Returns (should_notify, reason_if_suppressed)."""
```

**Implementation:**
- Check severity vs proactivity dial:
  - `off`: suppress everything (return False, "proactivity is off")
  - `quiet`: only critical severity
  - `balanced`: warning + critical
  - `assertive`: info + warning + critical
- Check quiet hours: if current time is in quiet hours, suppress non-critical
- Check category overrides: if the event's category has an override, use that instead of the dial
- Check guardrails: if `GuardrailEnforcer.safe_mode_active`, suppress non-critical
- Check snooze: if the finding is snoozed and the snooze hasn't expired, suppress
- Check dismissal: if the finding was dismissed and the condition hasn't changed, suppress

**Acceptance:**
- `off` suppresses everything
- `quiet` allows only critical
- `balanced` allows warning + critical
- `assertive` allows everything
- Quiet hours suppress non-critical
- Snoozed findings are suppressed until snooze expires
- Dismissed findings are suppressed if condition unchanged

---

### T7d.1 — Create the morning report

**Create:** `halbert_core/halbert_core/proactive/morning_report.py`

**Interface:**
```python
class MorningReportGenerator:
    def __init__(self, finding_store: FindingStore, proposal_store: ProposalStore,
                 sourceprep_client: SourcePrepClient): ...
    async def generate(self) -> ProactiveEvent: ...
```

**Implementation:**
- Consolidate the last 24 hours:
  - Open findings (grouped by severity)
  - Pending proposals awaiting approval
  - Config changes detected by the watcher
  - Telemetry anomalies (if available)
- Use the LLM to generate a natural-language summary in the configured voice
- Publish as a `ProactiveEvent` of type "morning_report"
- Scheduled by the scheduler engine at the configured time (from `being.yml`)

**Acceptance:**
- Morning report contains findings, proposals, and changes from the last 24h
- Report is in natural language (not just a data dump)
- Report respects the voice setting
- Published at the configured time

---

### T7d.2 — Schedule the morning report

**Modify:** `halbert_core/halbert_core/scheduler/autonomous_tasks.py`

**Changes:**
- Add a `MorningReportTask(AutonomousTask)` subclass
- Schedule it to run at the configured time from `being.yml` (default 08:00)
- The task calls `MorningReportGenerator.generate()` and publishes the event

**Acceptance:**
- Task appears in the scheduler
- Runs at the configured time
- Publishes a morning report event

---

### T7e.1 — Wire detector triggers to the event bus

**Modify:** `halbert_core/halbert_core/config/watcher.py`, `halbert_core/halbert_core/findings/detectors/*.py`

**Changes:**
- When `ConfigWatcher` detects a change, trigger the detectors
- Each detector runs, produces findings, and publishes `ProactiveEvent`s on the bus
- The gate filters events before they reach the SSE stream
- Also run detectors on a scheduled sweep (e.g. every 6 hours, matching the existing health check)

**Acceptance:**
- Editing a config file triggers detector runs within 5 seconds
- Findings are created and events are published
- The gate filters events based on the proactivity dial
- Scheduled sweep runs detectors periodically

---

### T7e.2 — Wire snooze/dismiss to SourcePrep concepts

**Modify:** `halbert_core/halbert_core/findings/store.py`

**Changes:**
- When a finding is dismissed, save a SourcePrep concept:
  - `save_concept(content=f"User dismissed {finding.title}: {reason}", tags=["dismissal", "user_feedback"], anchors=[finding.affected_paths])`
- This becomes part of the rationale store — the being learns what's noise for this user
- When a finding is snoozed, save an observation:
  - `save_observation(content=f"Snoozed {finding.title} for {days} days", tags=["snooze"])`

**Acceptance:**
- Dismissal creates a SourcePrep concept
- Snooze creates a SourcePrep observation
- Future detector runs can query concepts to avoid re-reporting dismissed issues

---

## Phase 8: The Reactive Slice + Module Invocation (depends on Phase 5 + Phase 6 + Phase 7)

**Goal:** "How are you?" answered as itself, with evidence and a summoned module.

**Code seams verified:**
- `dashboard/frontend/src/pages/Agent.tsx` — the agent page (conversation surface)
- `dashboard/frontend/src/components/SidePanel.tsx:189` — `SidePanel` component (the conversation UI)
- `dashboard/frontend/src/hooks/useAgentStream.ts` — SSE hook with `StreamEvent` interface (line 91)
- `dashboard/frontend/src/components/ConfigEditor.tsx` — existing config editor component
- `dashboard/frontend/src/pages/Dashboard.tsx` — dashboard with vitals/metrics
- `dashboard/frontend/src/pages/Storage.tsx` — storage page (drive health data)
- `dashboard/frontend/src/lib/api.ts` — API client

---

### T8a.1 — Create provenance ref data model

**Create:** `halbert_core/halbert_core/proactive/provenance.py`

**Interface:**
```python
@dataclass
class ProvenanceRef:
    type: str           # log_cursor | snapshot_id | metric_window | path_lines | memory_id | observation_id
    ref: str            # the reference value (e.g. "journald:2026-08-23:10:30:00", "/etc/sshd_config:42-50")
    label: str = ""     # human-readable label for the UI
    url: str = ""       # deep-link if applicable

def attach_provenance(response: str, refs: list[ProvenanceRef]) -> dict:
    """Package a response with its provenance refs for the frontend."""
    return {"content": response, "provenance": [r.__dict__ for r in refs]}
```

**Implementation:**
- The backend validates refs before attaching (e.g. `path_lines` ref must point to a real file)
- The LLM expresses intent to cite (via structured output or post-processing); the backend validates and attaches real refs
- Never trust the LLM to fabricate evidence — the hybrid approach from explorations.md §A2

**Acceptance:**
- Provenance refs are structured and validated
- Invalid refs are rejected
- The response package is JSON-serializable

---

### T8a.2 — Wire provenance into agent responses

**Modify:** `halbert_core/halbert_core/agents/state_machine.py`

**Changes:**
- In the RESPONDING state, after generating the response text:
  - Extract claim markers from the response (sentences that reference system state)
  - For each claim, find the matching provenance ref (log cursor, snapshot, metric, path:lines)
  - Attach provenance refs to the SSE event
- The SSE event gains a `provenance` field:
  ```json
  {"type": "response", "content": "...", "provenance": [{"type": "path_lines", "ref": "/etc/sshd_config:42-50", "label": "sshd_config line 42-50"}]}
  ```

**Acceptance:**
- Responses to "how are you?" include provenance refs
- Refs point to real data (not fabricated)
- SSE events carry the provenance field

---

### T8a.3 — Create WhyChip UI component

**Create:** `halbert_core/halbert_core/dashboard/frontend/src/components/WhyChip.tsx`

**Interface:**
```typescript
interface WhyChipProps {
  provenance: ProvenanceRef[];
  onExpand?: (ref: ProvenanceRef) => void;
}
```

**Implementation:**
- A small chip/icon next to claims in the conversation
- On hover/click, shows a popover with the provenance refs
- Each ref is clickable — opens the source (file viewer, log viewer, metric chart)
- Uses existing Radix UI popover component

**Acceptance:**
- Chip appears next to claims with provenance
- Popover shows the refs
- Clicking a ref opens the source

---

### T8b.1 — Create module registry

**Create:** `halbert_core/halbert_core/dashboard/modules/__init__.py`, `halbert_core/halbert_core/dashboard/modules/registry.py`

**Interface:**
```python
@dataclass
class ModuleDef:
    name: str                   # "config-diff", "drive-health", "vitals", "evidence"
    component: str              # React component name (frontend)
    data_fetcher: str           # API endpoint path for data
    prop_contract: dict         # expected props
    standalone_route: str       # route for full-page view (e.g. "/modules/config-diff")
    icon: str = ""              # icon name

class ModuleRegistry:
    def __init__(self): ...
    def register(self, module: ModuleDef) -> None: ...
    def get(self, name: str) -> Optional[ModuleDef]: ...
    def list_all(self) -> list[ModuleDef]: ...
```

**Implementation:**
- In-memory registry, populated at startup
- The frontend calls `GET /api/modules` to list available modules
- The frontend calls `GET /api/modules/{name}/data` to fetch module data

---

### T8b.2 — Create module invocation protocol

**Modify:** `halbert_core/halbert_core/agents/state_machine.py`, `halbert_core/halbert_core/dashboard/routes/being.py`

**Changes:**
- The LLM can express intent to invoke a module via a structured action:
  ```json
  {"action": "invoke_module", "module": "vitals", "props": {"timeframe": "1h"}}
  ```
- The backend validates the module exists in the registry
- The SSE event carries a `module_invoke` type:
  ```json
  {"type": "module_invoke", "module": "vitals", "props": {"timeframe": "1h"}}
  ```
- The frontend receives the event and renders the module in the context region
- Three invocation paths:
  1. LLM-initiated: LLM emits the structured action, backend validates
  2. Backend-initiated: proactive findings carry their module (e.g. a drop-in conflict finding carries the config-diff module)
  3. User-initiated: a module palette (future — not in v1)

**Acceptance:**
- LLM can invoke a module via structured action
- Backend validates the module exists
- SSE event reaches the frontend
- Module renders in the context region

---

### T8b.3 — Create frontend module renderer

**Create:** `halbert_core/halbert_core/dashboard/frontend/src/components/ModuleRenderer.tsx`

**Interface:**
```typescript
interface ModuleRendererProps {
  module: string;
  props: Record<string, any>;
}
```

**Implementation:**
- Receives a module name and props
- Looks up the component in a local registry (maps module name → React component)
- Renders the component with the props
- Falls back to a "module not found" message

**Acceptance:**
- Renders the correct component for a given module name
- Passes props through
- Handles unknown modules gracefully

---

### T8c.1 — Curate minimal module set: config-diff

**Create/Modify:** `halbert_core/halbert_core/dashboard/frontend/src/components/modules/ConfigDiffModule.tsx`

**Implementation:**
- Reuses the existing `ConfigEditor.tsx` + `DiffBlock` components
- Accepts props: `path` (the config file path), `findingId` (optional)
- Fetches data from `GET /api/modules/config-diff/data?path=...`
- Renders the diff view inline in the conversation

**Acceptance:**
- Module renders a config diff inline
- Shows the file path and changes
- Works when invoked from a finding or from the LLM

---

### T8c.2 — Curate minimal module set: vitals

**Create:** `halbert_core/halbert_core/dashboard/frontend/src/components/modules/VitalsModule.tsx`

**Implementation:**
- A compact version of the Dashboard page (CPU, memory, disk, network)
- Accepts props: `timeframe` (e.g. "1h", "24h")
- Fetches data from `GET /api/modules/vitals/data?timeframe=...`
- Renders a compact metrics view inline in the conversation

**Acceptance:**
- Module renders vitals inline
- Shows real-time metrics
- Works when summoned by "how are you?"

---

### T8c.3 — Curate minimal module set: drive-health

**Create:** `halbert_core/halbert_core/dashboard/frontend/src/components/modules/DriveHealthModule.tsx`

**Implementation:**
- A compact version of the Storage page (drive SMART status, temperature, capacity)
- Fetches data from `GET /api/modules/drive-health/data`
- Renders a compact drive health view inline

**Acceptance:**
- Module renders drive health inline
- Shows SMART status and temperature
- Works when summoned

---

### T8c.4 — Curate minimal module set: evidence

**Create:** `halbert_core/halbert_core/dashboard/frontend/src/components/modules/EvidenceModule.tsx`

**Implementation:**
- A log excerpt viewer
- Accepts props: `source` (journald/log file), `cursor` (timestamp or line range), `query` (optional filter)
- Fetches data from `GET /api/modules/evidence/data?source=...&cursor=...`
- Renders log excerpts with highlighting

**Acceptance:**
- Module renders log excerpts inline
- Shows the source and time range
- Works when a provenance ref is clicked

---

### T8d.1 — Wire the reactive slice end-to-end

**Modify:** `halbert_core/halbert_core/agents/state_machine.py`, prompt layer

**Changes:**
- When the user asks "how are you?":
  1. Intake classifies: intent="informational", complexity=1-2, needs_retrieval=True
  2. Retrieval fetches biography: recent logs (observations), config changes (SourcePrep host project), self-knowledge (SourcePrep observations), memory (memory_v2)
  3. Cognitive tick renders through continuity in the configured voice
  4. Response carries provenance refs (log cursors, snapshot ids, metric windows)
  5. Vitals module is summoned alongside the narrative answer
- The system prompt includes: "When the user asks about your state, answer as yourself, ground every claim in real data, and summon the vitals module."
- The response is in the configured voice (first_person / the_computer / hybrid)

**Acceptance:**
- "How are you?" produces a natural-language response in the configured voice
- Response includes real data (not generic)
- Every claim has a provenance ref (WhyChip appears)
- Vitals module renders alongside the response
- Response is grounded in actual system state (logs, config, metrics)

---

## Summary: Task Dependency Graph

```
Phase 0 (RAG Corpus):
  T0b.1 → T0b.2 → T0b.3 (cleanup: empties, formatting, schema)
  T0c.1 → T0c.2 (dedup: exact + near-duplicate)
  T0d.1 (convert to markdown) — depends on T0c.1
  T0a.1 (register SourcePrep project) — depends on T0d.1
  T0e.1, T0e.2 (quality gate + eval) — depends on T0a.1
  T0f.1 (cross-platform docs) — depends on T0b.3
  T0g.1 (replace empty datasets) — depends on T0b.1
  T0g.2 (update manifest) — depends on all above

Phase 1 (Intake) — parallel with Phase 0:
  T1a.1 → T1a.2 (signals + tests)
  T1b.1 → T1b.2 (budget + tests)
  T1c.1 → T1c.2 (complexity + tests) — depends on T1a.1 (needs MessageSignals)
  T1d.1 → T1d.2 (pipeline + tests) — depends on T1a.1, T1b.1, T1c.1
  T1e.1 (__init__) — depends on all above

Phase 2 (RAG Consolidation) — depends on Phase 0:
  T2a.1 → T2a.2 (wire SourcePrep + update source model)
  T2b.1 (retire ChromaDB on chat path)
  T2c.1, T2c.2 (migration scripts) — independent of each other
  T2c.3 (documentation)

Phase 3 (Intake Wiring) — depends on Phase 1 + Phase 2:
  T3a.1 → T3a.2 (wire into state machine + model selection)
  T3b.1 → T3b.2 (wire budget into assembler + state machine)

Phase 4 (chat.py Deprecation) — depends on Phase 3:
  T4a.1 (audit) → T4a.2-T4a.5 (port features, can parallelize) → T4b.1 (retire endpoints)

Phase 4.5 (Boot-Test Gate) — depends on Phase 4:
  T4.5a.1 (Ubuntu) + T4.5b.1 (macOS) — can parallelize

Phase 5 (Config Brain) — depends on Phase 4.5:
  T5a.1 → T5a.2 (register host project + wire watcher)
  T5b.1 → T5b.2 → T5b.3 (findings + proposals + tests)
  T5c.1, T5c.2, T5c.3 (3 detectors) — can parallelize, depend on T5b.1
  T5d.1 (precedence engine) — T5c.1 depends on this
  T5e.1 (blast radius) — T5f.1 depends on this
  T5f.1 (propose-through-approval) — depends on T5b.2, T5e.1

Phase 6 (Being Config + Voice) — depends on Phase 4.5, parallel with Phase 5:
  T6a.1 → T6a.2 (config schema + API)
  T6b.1 (voice in prompts) — depends on T6a.1
  T6c.1 (Settings UI) — depends on T6a.2

Phase 7 (Proactive Channel) — depends on Phase 5 + Phase 6:
  T7a.1 (event bus)
  T7b.1 → T7b.2 (SSE transport + frontend hook)
  T7c.1 (gate) — depends on T6a.1
  T7d.1 → T7d.2 (morning report + scheduling)
  T7e.1 → T7e.2 (wire triggers + snooze/dismiss)

Phase 8 (Reactive Slice + Modules) — depends on Phase 5 + Phase 6 + Phase 7:
  T8a.1 → T8a.2 → T8a.3 (provenance model + wiring + UI)
  T8b.1 → T8b.2 → T8b.3 (registry + protocol + frontend renderer)
  T8c.1-T8c.4 (4 modules) — can parallelize, depend on T8b.3
  T8d.1 (end-to-end wiring) — depends on all above
```

---

## Effort Summary

| Phase | Tasks | New files | Modified files | Est. lines | Est. effort |
|-------|-------|-----------|----------------|------------|-------------|
| 0 (RAG Corpus) | 12 | 6 scripts + 1 converter | 2 configs + manifest | ~1,500 | Medium |
| 1 (Intake) | 9 | 9 | 0 | ~1,200 | Small-medium |
| 2 (RAG Consolidation) | 6 | 2 | 3 | ~400 | Small-medium |
| 3 (Intake Wiring) | 4 | 0 | 3 | ~150 | Small |
| 4 (chat.py Deprecation) | 6 | 1 | 4 | ~600 | Medium-large |
| 4.5 (Boot-Test Gate) | 2 | 0 | 0 | 0 (verification) | Small |
| 5 (Config Brain) | 12 | 10 | 2 | ~2,500 | Medium-large |
| 6 (Being Config + Voice) | 5 | 2 | 3 | ~600 | Small-medium |
| 7 (Proactive Channel) | 8 | 5 | 3 | ~1,200 | Medium |
| 8 (Reactive Slice + Modules) | 10 | 7 | 3 | ~1,500 | Medium |
| **Total** | **74** | **43** | **23** | **~9,650** | |

---

## Slice Landing Points

- **Slice 1 (proactive config worry):** Phase 7 complete (T7e.2). The being detects a config problem, opens the conversation with its why, and proposes a fix through approval.
- **Slice 2 (reactive "how are you"):** Phase 8 complete (T8d.1). The being answers as itself, grounded in real data, with evidence and a summoned vitals module.

---

*This plan is the task-level decomposition of the roadmap. Each task is independently verifiable. Phase 0 tasks are detailed in `.handoff/RAG-OPTIMIZATION-PLAN-2026-08-23.md` and included here for completeness. Phases 1–8 can proceed once T0a.1 and T0e.1 are complete (SourcePrep built, quality verified).*
