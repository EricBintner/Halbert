# Halbert — Foundational Research & Realignment Options

**Date:** 2026-08-21
**Origin:** A strategic review session (Claude, ultracode) commissioned by the founder.
**Purpose:** Step back from the codebase, read the founding vision, and assess where the
current app misaligns from it — then map the leverage available from two sibling codebases
under the same LLC.
**Audience:** **The next AI session.** This is a research/handoff artifact, not a decision.
The founder explicitly asked that findings be documented and that the strategic options be
framed as **foundational research questions** for a future session to investigate further,
rather than decided now.

> **Naming convention (from the founder):** Three apps share one chat-engine lineage —
> **Halbert** (this app, the original) and **H2 / H3** (the two siblings, kept secret —
> never write their real product names; refer to them only as H2 and H3). The agnostic
> chat core being extracted from H2's repo is called **Haloysius** (safe to name). The
> structural-intelligence tool is **SourcePrep** (repo: `CoDRAG`; safe to name). This doc
> never writes H2/H3's real names. Sibling-repo file paths are intentionally omitted; the
> founder can point the next session at the relevant repos.

---

## 0. How to use this document

- **What's settled:** the diagnosis (§1–§6) is evidence-based and verified against the
  code this session. Treat it as ground truth, but verify file paths before acting.
- **What's open:** §9 (Foundational Research Questions) is the payload. Each RQ is a
  self-contained research fork with context, what to investigate, and decision criteria.
  Pick one, research it, and expand.
- **What to verify:** §10 lists the unknowns the founder and the sibling program have not
  confirmed — most importantly whether Halbert *is* the "sysadmin near-peer consumer" the
  Haloysius extraction program is already designing for.
- **Do not** treat this as an implementation plan. No scope has been chosen. The founder
  wants options researched, not built.

---

## 1. The founding vision (the ethos)

Source: `documentation/design/philosophy.md` (read it in full — it is the single best
articulation of what Halbert is supposed to be).

**Core thesis** (philosophy.md:3):
> *"an LLM that identifies as the computer itself is fundamentally more useful than an
> LLM that merely answers questions about computers."*

**Four pillars:**

1. **Self-Identification** (philosophy.md:21-25) — The LLM's identity *is* the computer.
   "I am `ubuntu-server-01`. I run Ubuntu 24.04. My primary storage is bcachefs on
   `/dev/nvme0n1`…" — "This isn't role-playing or creative writing. Every claim is
   grounded in actual system data retrieved in real-time."

2. **System State as Biography** (philosophy.md:29-37) — Logs become first-person memories.
   `[Error] /dev/sda1 I/O error` → "I experienced a read error on my primary drive at
   08:00." Personality emerges from data, not a creative prompt. "When the LLM retrieves
   these memories during conversation, its responses are naturally cautious about past
   failures."

3. **Configuration as Physiology** (philosophy.md:40-52) — "The LLM understands its own
   configuration files as its body." Example: "I checked my configuration (`/etc/fstab`)
   and I'm currently mounted with `background_compression=none`…"

4. **Safe Autonomy** (philosophy.md:124-143) — Dry-run default, human approval, rollback
   tracking, budgets, cooling-off, kill switch. "Prefers configuration changes over
   restarts; restarts over reinstalls."

**Three functional roles sharing one memory store** (philosophy.md:56-96):
- **The Guide** — the conversational interface.
- **The Deep Thinker** — background analysis, "morning reports."
- **The Eyes** — the deterministic sensor layer (Python).

**The Autobiography Loop** (philosophy.md:113-119): Ingestion → Indexing (ChromaDB) →
Retrieval → Response. "This creates a system that genuinely 'remembers' its past."

`documentation/design/future.md` is explicitly **not a roadmap** ("These are not planned
features") — speculative enhancements only. "Not Planned: Cloud-hosted version, Windows
support, Mobile apps."

**The founder's reframing (this session):** Halbert should be *delicate* — "not really like
[Warp] but it could be" — a focused tool scoped to **one repo: the computer's OS itself**,
"not a developer of the kernel," but "the AI assistant as the computer." It should be a
**multi-session LLM interface** with understanding of the whole, should **own the config
files and settings** (going well beyond Ubuntu's settings management), and the computer
should be **aware of "I AM"** — its components, software, and capabilities.

---

## 2. Where Halbert stands today — and how it misaligns

**Tech stack:** Python 3.11+ backend (FastAPI + ChromaDB + Ollama), React/TypeScript/Vite
frontend, Tauri v2 desktop wrapper. Local-first by design.

**Layout:**
- `Halbert/main.py` — 94 KB monolithic CLI entry point (`ask`, `dashboard`,
  `ingest-journald`, `snapshot-configs`, scheduler, persona, models, etc.).
- `halbert_core/halbert_core/` — the main package, ~30 submodules (agents, alerts,
  approval, autonomy, config, context, dashboard, discovery, eval, index, ingestion,
  knowledge, memory, model, obs, persona, platform, policy, prompts, rag, runtime,
  scheduler, storage, streaming, tools, utils, web).
- `halbert_core/halbert_core/dashboard/` — FastAPI app (`app.py`) + `routes/` (23 route
  modules, ~16,600 lines) + `frontend/` (React app).
- `halbert-linux/`, `halbert-mac/` — platform adapter packages.
- `data/` — 43 MB Linux RAG corpus + 1.4 MB macOS.

**What it became:** a 17-page IT-operations dashboard
(`frontend/src/pages/`: Dashboard, Services, Storage, Backups, Security, Network, Sharing,
Containers, GPU, Development, Approvals, Settings, Terminal, Memory, Jobs, Apps, Agent)
with chat as a side panel. The dashboard auto-starts ingestion + APScheduler on startup
(`app.py:227-278`). By volume, discovery scanners and per-page REST routes dominate; the
self-aware agent is an afterthought.

**Per-pillar misalignment:**

| Pillar | Vision | Reality | Gap |
|---|---|---|---|
| Self-Identification | identity *is* the computer, grounded in real-time data | a prompt string + a thin `self_knowledge` module (Mem0-style facts, a KnowledgeGraph, CRAG reflection) | bolted on, not load-bearing; not an *evolving* self-model |
| Biography / unified memory | one memory across sessions; logs → first-person memories | conversations are isolated JSON files; cross-session = raw ChromaDB snippet retrieval | no synthesis layer; no consolidation into an evolving awareness |
| Configuration as Physiology | config = the body, proactively maintained | config *tracking* (manifest/snapshot/drift/watcher/indexer/parser) + editor + `write_config` tool | no organizing intelligence; hands but no brain |
| Safe Autonomy | dry-run, approval, rollback, kill switch | approval/autonomy/policy code exists but autonomy endpoints + WebSocket are stubs (`GAPS.md` admits it) | documented-but-not-implemented |

**Recent effort went to the wrong layer:** ~30 commits are almost entirely RAG retrieval
plumbing (RAPTOR, GraphRAG, Self-RAG/CRAG, BM25, reranking, freshness, trending discovery)
plus the new Agent state-machine UI. Almost nothing on config organization, cross-session
synthesis, or the identity layer — i.e., the differentiating vision.

---

## 3. Dead & disconnected code (inventory)

The founder's suspicion ("a lot of written code that's not even connected fully") is
confirmed. Verified findings:

- **CRITICAL — the frontend cannot build from a fresh clone.** `src/lib/` (where
  `api.ts`/`utils.ts` live) is gitignored (`.gitignore:13` has a bare `lib/` rule) and
  absent from the tree. `Layout.tsx`, `SidePanel.tsx`, `ChatPanel.tsx` import `@/lib/api`
  and `@/lib/utils` and are therefore dead. The old side-panel chat UI is non-functional.
- **Two chat systems, one live:**
  - Old: `dashboard/routes/chat.py` (4,239 lines, `/api/chat/send`, `/api/chat/send/stream`)
    — still registered (`app.py:175`), rich context-injection logic, but its frontend
    consumers are broken.
  - New: `dashboard/routes/agent.py` (716 lines, `/api/agent/message`, Phase 36 state
    machine with SSE) — live via `useAgentStream.ts` (raw `fetch()`), rendered by
    `AgentChat.tsx`/`AgentPanel.tsx`. Does **not** replicate the old path's
    context-injection logic.
  - Net: ~4,200 lines of `chat.py` route logic is API-reachable but UI-dead; the live
    agent path is thinner.
- **Dead runtime scaffolds:** `runtime/langgraph_engine.py` (`LGEngine` — never imported
  anywhere; the README still advertises "Runtime Engine (LangGraph)"), `runtime/engine.py`
  (`FallbackEngine` — used by the CLI, not the dashboard chat), `runtime/graph.py`,
  `runtime/state.py` (minimal "Phase 1" scaffolds, unused).
- **`context/` module** (`assembler.py`, `prioritizer.py`, `adapters.py`, `cache.py`,
  `tokens.py`) — consumed only by the new `agent.py` route (`agent.py:81`); the main
  `chat.py` path does its own ad-hoc context assembly and ignores it.
- **`halbert-linux/` / `halbert-mac/` adapters** — referenced by `platform/linux.py` and
  `platform/macos.py` via `sys.path` manipulation, but live system-introspection goes
  through `discovery/scanners/` instead. Early-architecture leftovers, superseded.
- **`web/search.py`** — not registered; `web_search.py` is the registered route. Appears
  unused.
- **Stubbed:** `GET /api/autonomy/*` (documented, not implemented), the WebSocket
  (`ws://localhost:8000/ws`) — a 37-line stub (`websocket.py`). Both flagged in
  `documentation/GAPS.md`.

---

## 4. RAG audit — "isn't really working" is accurate

Source: the codebase's own `documentation/RAG_AUDIT_REPORT.md` plus code inspection.

- **Two disconnected RAG systems, both on the chat hot path:**
  - `rag/pipeline.py` (`RAGPipeline`) — in-memory BM25 + dense embeddings. Its own
    docstring: **"DEPRECATED … Use document_indexer.py + chroma_index.py for production
    RAG."** Yet it is still instantiated and queried at `chat.py:1240-1263` and invoked in
    the stream path (`chat.py:2732`) for non-"unclear" queries.
  - `rag/document_indexer.py` + `index/chroma_index.py` — ChromaDB-backed "production"
    path, called by `get_docs_context()` (`chat.py:426`), gated by keyword detection.
  - A single chat query can trigger **both**, doubling work and producing inconsistent
    context. The audit marked this "FIXED" by deprecating `RAGPipeline`, but the
    deprecated singleton is still live.
- **RAPTOR + GraphRAG are wired but fragile:** `rag/raptor.py` (556 lines) and
  `rag/graphrag.py` (659 lines) are imported by `document_indexer.query_docs()` with
  `use_raptor=True`/`use_graphrag=True` defaults, wrapped in try/except — so they **fail
  silently** if their indexes are empty (commit `c40ec45`).
- **Self-RAG / CRAG reflection** (`knowledge/reflection.py`) IS wired into chat via
  `get_self_knowledge_context()` (`chat.py:521-567`), called first in context-injection
  order (`chat.py:1783`). But it only queries `self_knowledge`, not the 14K Linux docs.
- **Corpus exists:** 43 MB in `data/linux/`, including `merged/rag_corpus_merged.jsonl`.

**Verdict:** RAG is wired end-to-end with real data, but quality is inconsistent and hard to
reason about: dual competing systems, a deprecated path still live, and RAPTOR/GraphRAG
layers that silently no-op. "Not really working" in the user's sense is plausible.

---

## 5. Session model — isolation vs. the synthesis gap

- **Conversations are file-isolated:** `dashboard/routes/conversations.py` stores each
  conversation as a standalone JSON file at `~/.config/halbert/conversations/{uuid}.json`
  (messages, persona, timestamps). No inter-conversation linking, no summary, no shared
  state. A new conversation gets a canned greeting and exists in isolation. This is the
  "each session in isolation" the founder describes.
- **Cross-session memory exists but is unsynthesized:** `get_memory_context()`
  (`chat.py:302-335`) calls `index.query_conversations()` against the `self_conversations`
  ChromaDB collection — retrieving semantically relevant *past* conversations as raw
  embedded snippets, not a synthesized model of the system.
- **A self-knowledge layer exists:** `halbert_core/halbert_core/knowledge/` —
  `self_knowledge.py` (Mem0-style ADD/UPDATE/DELETE/NOOP), `graph.py` (KnowledgeGraph with
  RelationType), `reflection.py` (Self-RAG/CRAG), `hierarchical.py`. This is the "aware of
  the whole system" layer — persistent facts about components, bootstrap from profile,
  learn from config comments. It is wired in as the *first* context injected (`chat.py:1783`).
- **Two parallel session models:** the old `chat.py` path (`conversation_id` + ChromaDB
  memory) vs. the new `agent.py` path (`session_id` state machine, `agents/conversation.py`,
  separate store).
- **The Deep Thinker / "morning reports"** exists in `scheduler/autonomous_tasks.py` and is
  started by the dashboard, but there is no evidence it writes back into a session-aware
  narrative the Guide then uses seamlessly.

**Verdict:** "Built as each session in isolation" is accurate at the storage layer, but
*understates* the cross-session ChromaDB retrieval and the self-knowledge graph. What's
missing is **synthesis**: no layer consolidates across sessions into an evolving self-model
that shapes the next session. The pieces exist but aren't unified into one "awareness."

---

## 6. Config capabilities — what exists, what's missing

**Exists (tracking / editing / indexing):**
- `config/manifest.py` — YAML-driven registry of include/exclude globs ("config-registry")
  for which config files to watch.
- `config/snapshot.py` — snapshots tracked configs to raw text + canonical JSON under
  `data/config/`.
- `config/drift.py` — diffs two snapshots.
- `config/watcher.py` — `watchdog`-based file watcher, re-snapshots on change.
- `config/indexer.py` — indexes canonical config records into ChromaDB for semantic search.
- `config/parser.py` — parses ini/systemd/yaml/json into canonical JSON.
- CLI `snapshot-configs` command (`Halbert/main.py:1784`).
- `tools/write_config.py` — an LLM-callable tool that writes config files with backup,
  dry-run diff, and rollback.
- `dashboard/routes/editor.py` + `frontend/src/components/ConfigEditor.tsx` — Monaco-based
  config editor with AI-assisted SEARCH/REPLACE blocks and inline diff.
- `dashboard/routes/chat.py:3976` `/api/chat/config` — AI-assisted config editing chat.

**Missing (the "physiology brain" — the founder is correct there is no organization
capability):**
- Nothing scans for **misconfigurations** or drift anomalies.
- Nothing **deduplicates** settings scattered across files.
- Nothing **migrates** scattered configs to canonical locations.
- Nothing maintains a **coherent model** of the system's configuration state.
- The "Configuration as Physiology" vision has read/snapshot/edit primitives but no
  organizing intelligence on top. The LLM can be *asked* to edit a config; nothing
  proactively maintains the body.

---

## 7. The sibling tools

### 7a. SourcePrep (repo: `CoDRAG`) — the awareness engine

**What it is:** a mature, local-first "structural codebase intelligence" platform. Tagline:
*"Prepare the context before any AI call — epistemic trace intelligence for autonomous
agents."* It builds a persistent semantic + structural + epistemic index of a codebase (or
many repos) and serves bounded, source-cited, LLM-ready context on demand.

**Lineage:** RunPrep → SourcePrep (author: Eric Bintner, `MagneticAnomaly` GitHub org).
**Not** code-descended from Halbert — zero Halbert references in the repo. It is a sibling
tool, not a spinoff. (The founder believed it was spun off Halbert; the code says
otherwise. Lineage doesn't affect leverageability.)

**Maturity:** well beyond early-stage. 149 numbered phase docs, 952 test files, Apache-2.0,
actively iterated through Aug 2026, dogfooded on its own repo (live `.sourceprep/` index
present). Self-classified Alpha, but surface area, tests, docs, and live dogfooding
indicate a working, leverageable tool.

**Six MCP tools** (defined in `src/prep/mcp_tools.py`, implemented in
`src/prep/mcp/server.py`):
| Tool | Purpose |
|---|---|
| `prep` | Ambient structural context — call FIRST at task start. Module summaries, hub files, role-scoped atlas. |
| `prep_search` | Semantic code search with structural trace expansion + LOD compression. |
| `prep_impact` | Blast-radius / dependency-graph analysis (call before editing). |
| `prep_audit` | Structural health (coupling, cycles, hub concentration, concept violations) + SARIF enrichment. |
| `prep_observe` | Cross-session memory (save/get observations; categories: note/decision/bug/pattern/assumption). |
| `prep_concepts` | Epistemic knowledge layer (save/get concepts; the "why" — rationale, decisions, constraints). |

**How it builds its index — a 15-stage pipeline** (`src/prep/services/pipeline/stages.py`):
Sync (Structural → InferredEdges → Catalogue → Validation → Knowledge) → Enrich
(Enrichment → GroupReasoning → Clustering → Deepening → DeepKnowledge) → Finalize (Atlas →
Rules → Concepts → Audit → Antibodies). Uses all three of:
- **Static analysis (Rust, no LLM):** tree-sitter-style parsers for Python, TypeScript,
  JavaScript, Go, Java, Rust, C/C++, + a Markdown scanner. Builds the trace graph
  (nodes/edges), hashes content, walks files.
- **Embeddings (RAG):** vector index per project; Ollama (`nomic-embed-code`) with a
  **built-in zero-dependency ONNX fallback** (`nomic-embed-text-v1.5`, ~132 MB, CPU-only) so
  it works with no Ollama. Stored as `embeddings.npy` + `documents.json` + `fts.sqlite3`
  (FTS5). Primary `code_index` + secondary `knowledge_index`.
- **LLM enrichment (optional, multi-pass):** Pass 1 (fast 3B) catalogues every file; Pass 0.5
  (Rust) validates hypotheses against the graph and discards hallucinations; Pass 2 (14B)
  adds domain tags, architecture layer, design patterns; Pass 3 clusters files into
  subsystem modules; Pass 4+ re-enriches changed nodes, converging when all **epistemic
  scores** ≥ 0.95 (scores decay on change).

**Knowledge base storage:** Concepts and Observations both persist in SQLite + FTS5, are
anchored to file paths, and are **flagged stale when anchored files change**. Concepts have
a status lifecycle (seed → active → archived → superseded). This is the cross-session,
file-anchored memory layer.

**The underlying engine is separable from MCP:**
- **Rust engine** (`engine/`, ~10K lines, 7-crate Cargo workspace) exposed to Python via
  PyO3 as the `prep_engine` module: `walk_repo`, `parse_file`, `parse_files_parallel`,
  `build_trace`, `load_trace`, `chunk_code`, `extract_lod`, `score_files_for_role`,
  `sanitize_code_fences`, `detect_secrets`, etc.
- **Python core** (`src/prep/core/`, ~80 modules): `index.py` (hybrid semantic+keyword
  search), `embedder.py`, `knowledge.py`, `trace/`, `audit/`, `atlas/`, `enrichment.py`,
  `epistemic_score.py`, `concept_*`, `antibodies.py`.
- **Consumable at four levels:** (1) MCP server (lightest — zero code coupling), (2) HTTP
  API (FastAPI `:8400`), (3) CLI (`prep serve | add | build | search | context | ui | mcp`),
  (4) embedded library (`import prep_engine` + `from prep.core import …` + `from
  prep.services import concept_store, observation_store` — no separate process for hot
  paths).

**Why it matters for Halbert:** SourcePrep already has the two layers Halbert is missing
most — a persistent **knowledge base** (concepts = the "why"; observations = cross-session
memory, both file-anchored and stale-flagged) and **structural intelligence** (semantic
search, code graph, impact, audit). That is the "aware of my components, software, and
capabilities" substrate. It is currently aimed at *code repos*; the open question (RQ2) is
how much adaptation pointing it at the OS — config files, services, logs, system state —
requires.

### 7b. Haloysius core — the mind

**What it is:** a shared, app-agnostic cognitive stack being extracted out of H2's repo into
a workspace package (`packages/core/`), to be split to its own repo ("Haloysius") at WP-15.
Three apps will consume it: Halbert, H2, H3. The core carries the cognitive stack —
context/continuity/temporal, the persona cognition model, the memory store, the
conversation/thought pipeline, the cognitive tick. It deliberately does **not** carry any
app's routes, frontend, schema loader, corpus, or model provider — those plug in behind
Protocol seams.

**The cognitive tick (`advance_turn`)** — the heart. Per-turn cognitive evolution in six
steps: Decay → Detect → Reinforce → Promote → Conflicts → Persist. The central state object
is `PersonaCognition` (four layers: Realities, Context, Prism [BeliefState + ValueHierarchy],
Experience [EmotionalStateV2, DriveState, WorryState, ThoughtState]). Each layer has
`to_prompt_block()` and `to_dict()` for round-trip persistence. This is the "whole-app
understanding" object. **Implemented and defect-closed (MED-1..4), but NOT wired to any chat
path.**

**Memory & continuity — the most mature part of the core, and the cross-session awareness
layer:**
- `context/continuity.py` (in the core, pure stdlib) — write-before-read ledger:
  `advance_from_user_message` → `render_state_block` → `advance_from_response`. A change
  the user states this turn appears in *this* turn's prompt.
- The state ledger lives in `memory_v2/temporal_graph.py`; the `AdaptiveStateRenderer`
  renders ledger triples into a prompt block. Current predicates: `wearing, at_location,
  feeling, occupation, time_of_day, weather, atmosphere, lighting, relationship_to_user,
  current_activity`. **Notably absent:** `believes, wants, worries_about, conflicted_about`
  — those four are WP-8 (planned, not done), the mechanism that would carry the tick's
  evolved state to the prompt.
- `temporal/` — InteractionLogger, PatternLearner, TemporalContextBuilder,
  TemporalOrchestrator, TemporalEventStore (time-based context + user-activity-pattern
  learning).
- `memory_v2/` (not yet in core) — the larger memory spine: epistemic-aware scoring, FTS5
  hybrid search, confirm/correct_memory, semantic subject dedupe, graded decay,
  consolidation, integration.

**The seam contract — only the precursor exists today.** The full
`ModelBackend` / `RetrievalBackend` / `GovernancePolicy` / app-seam Protocols are **NOT yet
defined** (WP-13, the architectural keystone, not started). What exists is the
`ImageBackend` + `ImagePromptSpec` precursor (`persona/image_prompt_spec.py`) — the pattern
WP-13 inherits: **the spec carries state, not prompt strings; the Protocol is a single
method; omission is the default and capability is opt-in.** The core calls back into app
concerns only through injected callables/Protocols, never by importing the app
(`grep -rn 'import flask' packages/core/` must return nothing).

**What stays consumer-side (confirmed by the program's WP-22 decision):** the sysadmin
consumer is a **near-peer**, not a thin consumer — so the published core is the
**intersection**, not the union. `model/`, `rag/`, `governance` stay as Protocol seams
because the sysadmin consumer's versions are *stronger* than the core's (the sysadmin
consumer has an 18-file model layer with provider ABC + 4 providers + router + tier_router +
hw_detector; a 41-module RAG stack with RAPTOR + GraphRAG + hybrid + 22 scrapers; and a
governance stack with `approval/`, `autonomy/`, `policy/`, `tools/safety.py`). The core's
default governance is a no-op pass-through so a governance-free consumer installs nothing
extra. Licensing consequence: no GPL-3.0 code enters the MIT core.

**Maturity — real but early:** ~30% extracted by volume (3 of ~20 subpackages physically in
`packages/core/`: `context/`, `errors/`, `temporal/`), 0% wired. 401 tests pass. Work
packages: WP-11 (scaffold) ✅; WP-7 (tick) implemented, defects being closed, **not wired**;
WP-12 (move mid-tier into core) not started; WP-13 (define the seam — the contract Halbert
builds against) not started; WP-14 (wire app against workspace member) not started; WP-15
(split to own repo) gated on WP-14 + licensing (licensing ✅ closed).

**Halbert's adoption profile (image-free, sysadmin-flavored near-peer):** implement
`ModelBackend` + `RetrievalBackend` + `GovernancePolicy` + the app-seam; omit
`ImageBackend`; consume Haloysius as an external pinned package (not vendored); keep all
seam implementations in the Halbert repo; wire the tick's `memory_store_add` /
`memory_store_search` callbacks so thought promotion actually persists. What Halbert
**inherits**: persona/cognition + the tick, memory_v2, continuity, conversation,
structured_personas, compression, temporal, errors. What Halbert does **not** inherit: the
core's (weaker) model/ and rag/.

---

## 8. The strategic opportunity — the three-way mapping

The founder's vision needs three things. Halbert has one (partially). The two siblings
supply the other two. And one genuinely new piece remains to build.

| The vision needs | Halbert today | The leverage | Status |
|---|---|---|---|
| A **mind** — unified cross-session self-model, persona cognition, the "I AM" synthesis | thin, bolted-on, isolated sessions | **Haloysius** — persona cognition + the tick + continuity + memory_v2 | gated (WP-13/15) |
| **Awareness** — "aware of my components, software, capabilities" | tangled dual-RAG + scattered self-knowledge | **SourcePrep** — structural + epistemic index + knowledge base (concepts/observations) | ready now |
| A **body + action** — own & organize config/settings, act safely | read/snapshot/edit primitives, no organizing brain, stubbed autonomy | **Halbert itself** keeps its stronger model/RAG/governance + adds the config-organization intelligence | to build |

**The one genuinely new thing to build — the piece neither sibling has — is the
config-organization action layer:** the "physiology brain" that scans for misconfigs,
dedupes settings, migrates scattered configs to canonical locations, maintains a coherent
model of the system's configuration state, and proposes changes under safe autonomy. This
is Halbert's unique contribution. It is what turns "awareness" into "ownership."

**Sequencing tension:** SourcePrep is ready now; Haloysius is not (the seam contract Halbert
would build against does not exist yet). A phased path is natural — but the founder has not
chosen a scope (see §9, RQ1).

---

## 9. Foundational research questions for the next AI

Each RQ is a self-contained research fork. **Pick one, research it, expand this doc with
findings.** None is decided.

---

### RQ1 — How big a move: rebuild on the sibling foundation, or repair what's here?

**Context:** The three-way mapping (§8) is attractive, but Haloysius is gated (WP-13/15) and
a full rebuild is a large commitment. The founder is open to a big move ("take a step back,"
"leverage the tools") but has not committed.

**Three candidate scopes:**
1. **Rebuild on the foundation** — adopt SourcePrep (now) + Haloysius (when its seam lands)
   as Halbert's core; cut dashboard bloat and dead code aggressively; refocus around the
   self-aware agent + config ownership. Biggest move, clearest payoff, longest timeline.
2. **SourcePrep now, Haloysius later** — immediately replace the tangled dual-RAG +
   self-knowledge with SourcePrep's index + knowledge base; defer cognitive-core adoption
   until WP-13. Medium move, lower risk, ships value fast.
3. **Surgical repair first** — on the current stack, no siblings yet: cut dead code,
   collapse to one chat path, fix the dual-RAG, wire self-knowledge into a real synthesis
   loop. Smallest move, fastest to a working baseline, defers the leverage question.

**Investigate:**
- Realistic timeline and dependency map for each (especially Haloysius WP-13/14/15 dates).
- What each scope *throws away* vs. *keeps* from the current Halbert stack (cross-ref §3, §6).
- Risk of building against a pre-seam Haloysius (scope 1/2) vs. the cost of rework later.
- Whether scope 3 is a prerequisite for scope 1/2 regardless (i.e., must cut dead code first).

**Decision criteria:** founder's risk appetite; how much of the current 17-page dashboard
survives; whether the differentiating vision (self-aware agent + config ownership) can be
realized within scope 3 at all, or fundamentally requires the siblings.

---

### RQ2 — Can SourcePrep index the OS (config/settings/logs) as its "repo," or only code?

**Context:** This is the most novel and highest-leverage unknown. SourcePrep is built for
*code repos* (tree-sitter parsers for Python/TS/Go/Java/Rust/C++/Markdown). Halbert's vision
needs it to understand the OS — config files (`/etc`, systemd, ini, yaml, json, toml),
services, logs, system state — as the "body." If SourcePrep can be repurposed to index the
OS, it becomes the "awareness of my components" substrate directly.

**Investigate:**
- How much of SourcePrep's 15-stage pipeline is code-specific vs. generic? The Rust walker,
  chunking, embeddings, FTS5, epistemic scoring, concepts/observations stores are
  format-agnostic. The tree-sitter *parsers* are code-specific.
- Which config formats does SourcePrep already parse? Markdown scanner exists. YAML/JSON
  likely handled as text/embeddings even without a tree-sitter parser. INI/systemd/TOML?
- What would a "system repo" look like as SourcePrep input? A synthesized tree of `/etc`
  files + service manifests + snapshot records + log excerpts? Could Halbert's existing
  `config/snapshot.py` + `config/parser.py` (which already canonicalizes ini/systemd/yaml/json)
  feed SourcePrep's embedder/indexer directly, bypassing the code parsers?
- Does the `knowledge_index` (secondary, conceptual) work without the `code_index` (primary,
  structural)? I.e., can Halbert use SourcePrep's concepts + observations + semantic search
  over config text without needing symbol graphs?
- What breaks: role projection, LOD compression, trace edges, audit (coupling/cycles) all
  assume code structure. Which are meaningful for config, which are noise?

**Decision criteria:** whether the awareness substrate can be reused as-is, needs a thin
adapter, or needs a fork. This determines whether SourcePrep is "the awareness engine" or
just "a code tool we also run."

---

### RQ3 — How does Halbert consume Haloysius — now, or after the seam (WP-13/15)?

**Context:** The handoff doc says "you don't need to wait for the split" — start orienting
to the seam shape against the `ImageBackend` precursor, inventory overlap, decide the
backend profile. But the full seam contract does not exist yet.

**Investigate:**
- Can Halbert build against the workspace member now (the WP-14 subtractive-install pattern)
  using only `context/`/`errors/`/`temporal/` + the unwired tick? What's usable today vs.
  what's blocked on WP-12 (mid-tier move) and WP-13 (seam definition)?
- Risk of building against a pre-seam core: how volatile is the `PersonaCognition` /
  continuity / memory_v2 surface? Will WP-13 break adapters?
- Should Halbert **influence WP-13's seam design** to fit its needs (the program explicitly
  invites the consumer to validate the seam against its shape)? What would Halbert want in
  `ModelBackend` / `RetrievalBackend` / `GovernancePolicy` / the app-seam that the
  image-free sysadmin shape implies?
- Halbert's backend profile: implement model + retrieval + governance, omit image. Confirm
  against the WP-22 near-peer decision. What's the thinnest Halbert that installs the core
  with none of its backends and the core still imports (the subtractive thesis)?

**Decision criteria:** whether to wait, build-against-workspace-now, or actively co-design
the seam. The founder has standing to shape WP-13 if Halbert is the sysadmin consumer (§10).

---

### RQ4 — What is the "config-organization action layer" concretely?

**Context:** This is the one piece neither sibling has and the founder's stated
differentiator ("a focus that owns the config file and settings," "go way beyond [Ubuntu]").
The vision calls it "Configuration as Physiology." Today there are read/snapshot/edit
primitives but no organizing intelligence.

**Investigate — what does "organize config files" mean in practice?**
- **Detect misconfigurations / drift** — beyond `config/drift.py`'s raw diff: semantic
  validation against known-good schemas, anomaly detection, "this setting contradicts that
  one."
- **Deduplicate settings** — find the same knob set in three files and consolidate.
- **Migrate scattered configs** — move dotfiles/scattered configs to canonical locations
  (XDG, `/etc`), with the awareness layer tracking the move.
- **Maintain a coherent config model** — a live, queryable model of the system's
  configuration state (what's set, where, why, when it changed, what depends on it). This is
  the "physiology" the LLM reasons over.
- **Propose changes under safe autonomy** — dry-run, diff, approval, rollback (the
  `write_config.py` tool + the stubbed autonomy layer, made real).

**Investigate — architecture:**
- How does this layer relate to SourcePrep's index (is the config model a SourcePrep
  "concept" / knowledge graph?) and to Haloysius's continuity ledger (does a config change
  write a first-person "biography" memory)?
- What's the MVP? A single high-value capability (e.g., misconfig detection across tracked
  configs) that proves the "ownership" thesis, vs. a broad organizer.
- Safe-autonomy envelope: what actions are read-only vs. propose-only vs. apply-with-approval
  vs. autonomous? Cross-ref the stubbed `autonomy/` + `approval/` + `policy/` code.

**Decision criteria:** a crisp definition of the first organizating capability that
distinguishes Halbert from "a config editor with an LLM."

---

### RQ5 — What is the primary interaction surface, and does it gate on the core?

**Context:** The founder wants Halbert "delicate, not really like [Warp] but it could be" —
drawn to a focused CLI/terminal feel — but the current app is a 17-page web dashboard +
Tauri desktop shell with chat as a side panel. This is a large fork but may be separable
from the core realignment.

**Investigate:**
- **CLI-first focused tool** (Warp-like): a polished terminal as the primary surface; the
  self-aware agent converses there; the dashboard shrinks to optional/secondary. Aligns
  with "delicate" and "one repo = the OS."
- **Trimmed desktop app, agent-centric:** keep the Tauri shell but cut the 17 pages to a
  few; make the self-aware chat the center, dashboards secondary.
- **Headless core + thin UI:** Halbert becomes a multi-session backend (Haloysius +
  SourcePrep under the hood) with a minimal UI; CLI and dashboard plug in as thin clients.
- Does the surface decision **gate** on the core realignment, or can it be deferred? (I.e.,
  is "delicate" a property of the interaction layer, independent of what's behind it?)
- What does "delicate" mean concretely to the founder — minimal UI, narrow scope, polished
  feel, or all three?

**Decision criteria:** whether the surface is a phase-1 concern or a phase-2 concern; and
which surface best expresses "the AI assistant as the computer."

---

### RQ6 — What of the current stack is salvageable vs. replaceable?

**Context:** Any scope decision (RQ1) depends on knowing what's worth keeping. The dead-code
inventory (§3) is a start; this RQ turns it into a migration plan.

**Investigate — categorize every major module as keep / repair / replace / cut:**
- **Keep (working, on-vision, worth retaining):** discovery scanners? config
  snapshot/parser/indexer primitives? the model layer (providers, router — the WP-22
  "stronger" layer)? the governance stack (approval/autonomy/policy — once wired)?
- **Repair (working but tangled):** the ChromaDB RAG path (if SourcePrep doesn't replace it
  entirely); the self-knowledge graph (fuse into SourcePrep concepts? or Haloysius
  memory_v2?).
- **Replace:** the dual chat systems → one chat path on Haloysius; the dual RAG → SourcePrep
  (or a single repaired path); the bolt-on self-knowledge → Haloysius persona cognition.
- **Cut:** `src/lib/` gap (fix or remove the dead frontend), `runtime/langgraph_engine.py`
  and dead scaffolds, deprecated `rag/pipeline.py`, superseded `halbert-linux`/`halbert-mac`
  adapters, stubbed WebSocket/autonomy routes (or wire them).
- Migration path for each kept module into the new architecture.

**Decision criteria:** a keep/repair/replace/cut table the founder can sign off on, with
effort estimates.

---

### RQ7 — Is Halbert the "sysadmin near-peer consumer" the Haloysius program is designing for?

**Context:** The Haloysius program's WP-22 decision describes a "sysadmin near-peer
consumer" — image-free, FastAPI, RAPTOR+GraphRAG, 41-module RAG, 18-file model layer,
governance stack, GPL-3.0, parked ~7 months, public GitHub, 243 package files. This maps
*very closely* onto Halbert (FastAPI, RAPTOR+GraphRAG, sysadmin/OS focus, "old abandoned,"
recent RAPTOR/GraphRAG commits). If confirmed, the core program is **already** designing
for Halbert as a first-class consumer, and Halbert's migration work is partly "already
done" by the program's assumptions.

**Investigate:**
- Confirm or refute: is the WP-22 sysadmin consumer Halbert, or a different/reference app?
- The handoff's **open question for Halbert**: (1) where does Halbert's cognitive stack
  currently live — private fork, sibling-tree import, or greenfield? (2) is Halbert
  image-free? Both determine how much migration work is Halbert's vs. already done.
- If Halbert is the consumer: what does the program already assume Halbert has, and does
  Halbert actually have it (vs. the dead/disconnected code in §3)?

**Decision criteria:** confirms Halbert's relationship to the core program and how much
adapter work is already anticipated. **This is likely the highest-leverage RQ to resolve
first**, because it determines whether RQ3 is "build against a foreign core" or "co-design
the core you're already a consumer of."

---

### RQ8 — How does the "I AM" self-model actually get built and maintained?

**Context:** The deepest vision question. Self-Identification + Biography require an
evolving self-model that no current layer synthesizes. The pieces exist in three places:
Haloysius (persona cognition + continuity + memory_v2), SourcePrep (concepts +
observations, file-anchored, stale-flagged), and Halbert (self_knowledge graph + CRAG
reflection + system introspection). None alone is the self-model.

**Investigate:**
- How do Haloysius's persona cognition + continuity ledger combine with SourcePrep's
  concepts/observations to form the evolving self-model? Are they redundant, complementary,
  or layered (e.g., SourcePrep = "what's true about me," Haloysius = "how I feel/think about
  it")?
- The **biography loop** (logs → first-person memories): today logs are ingested into
  ChromaDB as snippets. How should a log event become "I experienced a read error on my
  primary drive at 08:00" — an LLM reframe pass? A SourcePrep observation? A Haloysius
  memory_v2 entry with epistemic scoring? Who writes it, when, and how does the Guide
  retrieve it?
- The **Deep Thinker / morning reports** role: how does background analysis feed back into
  the self-model the Guide uses next session? (Today it barely does — §5.)
- The four missing ledger predicates (`believes, wants, worries_about, conflicted_about` —
  WP-8) are the mechanism that makes the tick visible to the prompt. How do config/system
  events map onto these (e.g., a failing drive → `worries_about /dev/sda1`)?

**Decision criteria:** a concrete data-flow for the self-model: which layer owns what, how
they sync, and how a system event becomes a first-person memory that shapes the next turn.

---

## 10. Open unknowns to verify

- **Is the WP-22 sysadmin consumer Halbert?** (RQ7) — strongest leverage if yes.
- **Where does Halbert's cognitive stack currently live?** Private fork, sibling-tree
  import, or greenfield? (The handoff's open question.)
- **Is Halbert image-free?** (The handoff's open question — the adoption profile assumes
  yes.)
- **Is SourcePrep's code lineage actually independent of Halbert?** This session found
  zero Halbert references and a RunPrep→SourcePrep lineage, contradicting the founder's
  belief that it was spun off Halbert. Verify with the founder; it doesn't affect
  leverageability but does affect the "shared foundation" framing.
- **What is `.gitignore`'s bare `lib/` rule doing?** Is `src/lib/` intentionally gitignored
  (a local-only secret) or a mistake that broke the frontend? The answer changes whether
  the old chat UI is "dead" or "recoverable."

---

## 11. Key file paths for verification (Halbert repo)

**Vision:**
- `documentation/design/philosophy.md` — the ethos (read in full).
- `documentation/design/future.md` — explicitly not a roadmap.
- `README.md` — architecture diagram (still advertises LangGraph — stale).

**Architecture / state:**
- `Halbert/main.py` — 94 KB monolithic CLI entry point.
- `halbert_core/halbert_core/dashboard/app.py` — FastAPI app, route registration, startup
  (`:175` chat routes, `:227-278` auto-start).
- `halbert_core/halbert_core/dashboard/routes/chat.py` — old chat (4,239 lines); note
  `:426` `get_docs_context`, `:521-567` `get_self_knowledge_context`, `:1240-1263`
  deprecated RAGPipeline, `:1276` `get_rag_context`, `:1783` context-injection order,
  `:2732` stream path, `:3976` `/api/chat/config`.
- `halbert_core/halbert_core/dashboard/routes/agent.py` — new live chat (716 lines).
- `halbert_core/halbert_core/dashboard/routes/conversations.py` — isolated JSON sessions.
- `halbert_core/halbert_core/dashboard/routes/editor.py` + `frontend/src/components/ConfigEditor.tsx`
  — config editor.

**RAG:**
- `halbert_core/halbert_core/rag/pipeline.py` — deprecated, still on hot path.
- `halbert_core/halbert_core/rag/document_indexer.py` + `halbert_core/halbert_core/index/chroma_index.py`
  — production ChromaDB path.
- `halbert_core/halbert_core/rag/raptor.py`, `rag/graphrag.py` — wired, silent-no-op risk.
- `halbert_core/halbert_core/knowledge/` — `self_knowledge.py`, `graph.py`, `reflection.py`,
  `hierarchical.py`.
- `documentation/RAG_AUDIT_REPORT.md` — the codebase's own audit.

**Config:**
- `halbert_core/halbert_core/config/` — `manifest.py`, `snapshot.py`, `drift.py`,
  `watcher.py`, `indexer.py`, `parser.py`.
- `halbert_core/halbert_core/tools/write_config.py` — LLM config-write tool.

**Dead/disconnected:**
- `frontend/src/lib/` — missing (gitignored at `.gitignore:13`).
- `frontend/src/` — `Layout.tsx`, `SidePanel.tsx`, `ChatPanel.tsx` (broken imports);
  `pages/` (17 dashboard pages).
- `halbert_core/halbert_core/runtime/` — `langgraph_engine.py`, `engine.py`, `graph.py`,
  `state.py`.
- `halbert_core/halbert_core/context/` — used only by `agent.py`.
- `halbert-linux/`, `halbert-mac/` — superseded by `discovery/scanners/`.
- `documentation/GAPS.md` — documents stubbed autonomy + WebSocket.

**Siblings (paths intentionally omitted — founder to point the next session at the repos):**
- The Haloysius handoff doc (in the core-extraction repo's `.handoff/`).
- The authoritative core-extraction spec: `docs/superpowers/specs/2026-08-20-core-extraction-program.md`
  (in that repo).
- The WP-22 near-peer decision doc (in that repo's `.handoff/`).
- SourcePrep: `CoDRAG/` — `README.md`, `CHARTER.md`, `docs/ARCHITECTURE.md`,
  `src/prep/mcp_tools.py`, `src/prep/mcp/server.py`, `src/prep/services/pipeline/stages.py`,
  `src/prep/core/` (`index.py`, `embedder.py`, `knowledge.py`), `engine/` (Rust, PyO3
  `prep_engine`).

---

## 12. Suggested research order (for the next session)

1. **RQ7** (is Halbert the sysadmin consumer?) — highest leverage, unblocks RQ3 and frames
   the whole core relationship. Verify with the founder.
2. **RQ2** (can SourcePrep index the OS?) — the novel leverage; determines whether
   SourcePrep is "the awareness engine" or "a code tool we also run."
3. **RQ1** (rebuild vs. repair) — once RQ7 + RQ2 are clear, the scope choice is much better
   informed.
4. **RQ4** (the config-organization layer) — the differentiator; can be designed in parallel
   once the awareness + mind substrates are understood.
5. **RQ8** (the self-model data-flow) — the deepest; benefits from all the above.
6. **RQ5** (surface) and **RQ6** (salvage inventory) — separable, can come last.

---

*End of foundational research document. This is a research artifact, not a decision or a
plan. Expand it as RQs are investigated.*

---

## 13. Addendum — findings from the 2026-08-21 evening session

A follow-up session verified several RQs against the actual sibling code on this machine.

### RQ2 — ANSWERED (provisionally): SourcePrep can index the OS with a thin adapter, not a fork

Verified by direct inspection of the CoDRAG repo (present at `/Volumes/4TB-BAD/HumanAI/CoDRAG`,
live `.sourceprep/` self-index, actively developed):

- **Walker is glob-configurable per project.** `engine/crates/prep-walker/src/lib.rs`
  `WalkConfig.include_globs` defaults to code + markdown + shell only, but
  `src/prep/core/team_config.py` exposes `.sourceprep/team_config.json` with custom
  `include_globs`/`exclude_globs`. Config formats need no engine changes to be included.
- **Chunking/embedding is format-agnostic.** `src/prep/core/chunking.py` `chunk_code()`
  (~:315) is language-agnostic size-based chunking; files without tree-sitter parsers embed
  as plain text. Embeddings keep working with no Ollama via the ONNX fallback.
- **Concepts/observations (SQLite + FTS5, file-anchored, stale-flagged) assume nothing
  about code.** Reusable over a config tree as-is.
- **What does not transfer:** symbol-graph features — trace edges, `prep_impact`, audit
  coupling/cycles, role projection, LOD compression. Parsers exist only for code languages
  + Markdown (`engine/crates/prep-parser/src/`).
- **Net:** SourcePrep as Halbert's search + memory + knowledge substrate = thin adapter
  (project registration + custom globs + a freshness loop driven by Halbert's existing
  `config/snapshot.py` + `config/watcher.py`). Blast-radius over config dependencies =
  new capability, handed to the SourcePrep side as a design agenda (see the handoff file
  at `.handoff/HALBERT-INTEGRATION-2026-08-21.md` in the CoDRAG repo).

### RQ7 — CONFIRMED (founder, 2026-08-22): Halbert IS the sysadmin consumer

The founder confirmed: "Halbert is an app designed to be a system admin helper AI" and
pointed at the Haloysius repo directly (`/Volumes/4TB-BAD/Haloysius`). The code evidence
from yesterday also matched the WP-22 description point-for-point: GPL-3.0 (`LICENSE`),
FastAPI, sysadmin/OS focus, image-free (the only image-generation reference in
`halbert_core` is a service *scanner* detecting such services, not generation).
**Consequence:** the core program is already designing for Halbert's shape; Halbert's
migration is partly pre-planned by the program's assumptions (image-free near-peer,
keeps its own stronger model/RAG/governance behind the seams).

### RQ3 — UNBLOCKED + VERIFIED (2026-08-22): Haloysius is at `/Volumes/4TB-BAD/Haloysius`

The founder pointed at the repo. It is far further along than this document assumed
(all commits dated 2026-08-21):

- **WP-15 done:** split into its own repo, standalone-ready ("regular package, lazy PIL,
  verified green"; post-split cleanup replaces `__file__` walk-ups with env vars +
  `data_home()`). Apache-2.0. Subtractively installable (`pip install .` = pyyaml +
  requests only; embeddings extra optional).
- **WP-13 done in substance:** `src/haloysius/seam.py` defines `ModelBackend`,
  `RetrievalBackend`, `GovernancePolicy`, `AppSeam` + `register_app_seam()` registry,
  exactly the contract the handoff predicted (spec carries state, omission is default).
  **Caveat:** nothing inside the core calls through the registry yet (zero usages of
  `get_app_seam` outside `seam.py`) — the contract exists; internal consumption is ahead.
- **The tick is real and callable:** `persona/cognition_tick.py:385` `advance_turn()` —
  decay → detect → reinforce → promote → conflicts → persist, with
  `memory_store_add`/`memory_store_search` injected callables (None = honest
  "logged_only" degradation).
- **memory_v2 IS in core** (34 py files) — this doc had said "not yet in core." Also in:
  `persona/` (50), `conversation/` (20), `context/` (12, incl. `continuity.py`),
  `temporal/`, `crag/`, `compression/`, `structured_personas/`, `grounding/`,
  `background/`, thin `model/` (7) and `rag/` (3) — consistent with "intersection, not
  union"; Halbert keeps its stronger versions behind the seams.
- Consumer configuration is env-var based (`HALOYSIUS_DATA_HOME` etc.); consumer prompts
  injectable via `configure_*` functions.
- **Net:** Phase 4's gate is effectively open. Halbert can be wired against Haloysius
  now: register an `AppSeam`, inject its model/governance, drive `advance_turn` +
  continuity + memory_v2 per conversation turn. (The stale pre-extraction clone of the
  H-sibling repo at `/Volumes/4TB-BAD/HumanAI/LinuxBrain`, last commit 2026-04-08, is
  superseded by this repo.)

### §3 item confirmed: the frontend breakage is a one-line `.gitignore` bug

`.gitignore:13` has a bare `lib/` rule (standard Python template) that swallows
`frontend/src/lib/`. Scoping it (e.g. `/lib/` + `lib64/`, or a `!frontend/src/lib/`
negation) restores frontend buildability from a fresh clone.

### Recommended phased plan (endorsed by the founder as "we likely need a phased approach")

- **Phase 0 — founder confirmations: DONE (2026-08-22).** Halbert confirmed as the
  sysadmin consumer; Haloysius repo located at `/Volumes/4TB-BAD/Haloysius` (WP-13/15
  effectively complete — see RQ3 above). Phase 4 is no longer externally gated; Phases 2
  and 4 can now be planned in parallel after Phase 1.
- **Phase 1 — clean the house (Halbert only, ~1 wk):** fix `.gitignore`, cut dead code
  (§3 inventory), collapse the two chat systems into one. Prerequisite for everything.
- **Phase 2 — SourcePrep as awareness layer:** register a synthesized host-config tree
  (produced by `config/snapshot.py` + `config/parser.py`) as a SourcePrep project with
  custom globs; replace dual-RAG with `prep_search`; replace isolated-session memory with
  `prep_observe`/`prep_concepts`. No external gate — can start immediately after Phase 1.
- **Phase 3 — config-physiology brain (the differentiator, new build):** misconfig
  detection → dedupe → coherent live config model, under dry-run/approval. Depends on
  SourcePrep-side work on config dependency edges (see the CoDRAG handoff file).
- **Phase 4 — Haloysius mind:** implement `ModelBackend`/`RetrievalBackend`/
  `GovernancePolicy` when WP-13 lands; `RetrievalBackend` plugs into the Phase 2 index,
  so no rework. Gated on Phase 0 locating the repo + WP-13 existing.

### Phase 1 progress (2026-08-22, branch `phase1-cleanup`)

Executed the dead-code cut. Results, with corrections to §3 where verification
contradicted the original inventory:

- **FIXED — frontend builds again.** The `lib/` gitignore rule was scoped (`/lib/`), but
  `frontend/src/lib/` had never been committed anywhere (not in any branch/stash), so the
  four modules were **reconstructed from consumer call sites + backend route shapes**:
  `utils.ts` (cn), `api.ts` (26-method API client), `tauri.ts` (HTTP helpers: system
  metrics via `/api/settings/metrics`, approvals via `/api/settings/approvals/*`, scheduler
  via `/api/settings/scheduler/*`), `generationQueue.ts` (serial LLM generation queue for
  service explanations/diagnoses). `tsc && vite build` passes. **The old chat UI
  (SidePanel/ChatPanel) is alive again** — which changes the §3 "UI-dead" framing.
- **CUT — `runtime/langgraph_engine.py`** + its guarded import in `Halbert/main.py`
  (`cmd_runtime_tick` now uses the fallback engine directly); stale LangGraph claim removed
  from README.
- **KEPT — `runtime/engine.py` + `graph.py` + `state.py`**: §3 called graph/state "unused
  scaffolds" — wrong; `engine.py` (used by the CLI) imports both.
- **CUT — `platform/` bridge + `halbert-linux/` + `halbert-mac/` adapters +
  `tests/platform_tests/`**: `get_platform_bridge` had zero live callers (only tests).
- **KEPT — `web/search.py`**: §3 said unregistered/unused — wrong; `web/__init__.py` and
  `routes/gpu.py:418` use it. (`web_search.py` is the *route*; `web/search.py` is the
  library.)
- **FIXED — deprecated RAGPipeline off the chat hot path.** Nuance §4 missed: the two RAG
  systems were split across *different endpoints* — `/api/chat/send` used the production
  ChromaDB path (`get_docs_context`), `/api/chat/send/stream` used the deprecated BM25
  pipeline. The stream endpoint now uses `get_docs_context`; `get_rag_pipeline` /
  `get_rag_context` / `check_rag_freshness` deleted from `chat.py`. `rag/pipeline.py`
  itself kept (still used by CLI eval tooling: `main.py:2026`, `rag/evaluation.py`,
  `rag/index_builder.py`).
- **New finding — `saveWhy` has no backend.** The WhyBrain/WhyOverlay UI (live in
  DiscoveryCard/GPU page) persists "why" annotations to `/api/why`, an endpoint that does
  not exist anywhere in the backend. Dead feature end-to-end; a natural Phase-2 fit for
  SourcePrep concepts.
- **Chat-path collapse (RQ-adjacent): DEFERRED to Phase 4.** With the old UI alive again,
  `chat.py` endpoints have live consumers (send/stream/config/models); `agent.py` is the
  Phase 36 state machine behind the Agent page. Neither can drive Haloysius's
  `advance_turn` today, and both get replaced when the cognitive core is wired. Collapsing
  now would port features into a path that Phase 4 retires anyway.
- **Not verified:** backend runtime boot — no Python env with fastapi/chromadb exists on
  this machine (the app targets the Ubuntu host). Run `pytest halbert_core/tests` and a
  dashboard boot on the target host.

### Artifacts produced this session

- `.handoff/HALBERT-INTEGRATION-2026-08-21.md` **in the CoDRAG repo** — the SourcePrep-side
  handoff: what Halbert needs, the verified feasibility findings, and seven open design
  questions (OS project profile, freshness model, config-aware chunking, dependency-edge
  sources, extensionless files, secrets hygiene, multi-project layout) for a future
  session in that repo.