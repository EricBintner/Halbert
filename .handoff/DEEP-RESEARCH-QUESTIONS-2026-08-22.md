# Deep Research Questions for Multi-Session Investigation

**Created:** 2026-08-22
**Status:** Open — designed for parallel investigation by multiple AI sessions
**Prerequisite reading:**
- `.handoff/FOUNDATIONAL-RESEARCH-2026-08-21.md` (RQ1-RQ8 + phased plan)
- `.handoff/CHAT-ARCHITECTURE-VALIDATION-2026-08-22.md` (§9 open questions + §11 reconciliation)

---

## Founder decisions captured (2026-08-22)

These RQs have been answered or narrowed by the founder and are **not** open for research:

### RQ5 — Interaction surface: RESOLVED

**Decision:** Chat-first, not terminal-first. The app is not a Warp competitor.

- The user-facing interface is **chat**. SourcePrep is the knowledge layer (what the system is and why it's set up that way); chat is how the user interacts with that knowledge.
- The **agent-facing terminal** is required (the agent must execute commands to understand and manipulate config files). The **user-facing terminal** may not be needed — open to removal.
- The app's scope is **owning and maintaining the system and itself** — not the OS, but "all the stuff a user actually does within the OS."
- "Terminal-first" has no real boundaries and is a much larger scope than what we're building.
- The existing user-facing terminal in the dashboard is questionable; can be revisited but is not a priority.

### RQ6 — Salvageable vs. replaceable: RESOLVED (not a question)

**Decision:** This is a work item, not a research question. Phase 1 completed the dead-code cut. Any remaining keep/repair/replace/cut decisions will be made during the relevant phase work (Phase 2, 3, 4) as implementation proceeds.

### RQ4 — Config-physiology brain: REFRAMED

**Original framing was unclear.** Restated simply:

The app's differentiator is that it **owns and maintains the system's configuration**. The question is: **what is the first concrete thing the app does with config that proves this ownership?**

Candidate capabilities (not all needed for MVP):
- Detect misconfigurations or drift (something is wrong)
- Explain why a setting is set the way it is (SourcePrep concepts/observations)
- Deduplicate or consolidate scattered settings
- Propose changes under safe autonomy (dry-run → approval → apply → rollback)
- Maintain a live, queryable model of the system's config state

This RQ needs founder input on which capability is the MVP. It is **not** a deep-research item — it is a product decision. Flagged for the next founder discussion.

### RQ8 — Self-model / identity: PARTIALLY RESOLVED

**Decisions:**
- The AI identifies **as the computer**. Default name is "Halbert"; users can rename it (this setting already exists).
- **One personality** is needed: a helper/assistant that understands itself. Simple personality.
- Multiple personalities are possible with Haloysius but **seriously unimportant** compared to the primary identity. Can be revisited much later.
- How the self-model interfaces with Haloysius's persona cognition is **not yet clear** — this becomes a research sub-question (see RQ-identity below).

---

## Open research questions for multi-session investigation

Each section below is designed to be independently researchable by a separate AI session. Each includes: context, what to investigate, what to read, and what the output should be.

---

### RQ-A: Seam shape — wrap SourcePrep or extend RetrievalBackend?

**Origin:** RQ3-update from CHAT-ARCHITECTURE-VALIDATION §9

**Context:** Haloysius's `seam.py` defines `RetrievalBackend` with `search(query) -> results` and `format_context(results) -> str`. SourcePrep exposes richer primitives: `prep_search` (semantic + structural expansion), `prep_impact` (dependency blast radius), `prep_concepts` (knowledge graph), `prep_observe` (cross-session memory). The question is whether Halbert wraps SourcePrep behind the existing simple interface, or whether the seam's `RetrievalBackend` protocol should evolve to expose SourcePrep's richer primitives.

**Investigate:**
1. Read `src/haloysius/seam.py` — the exact `RetrievalBackend` protocol signature and what the core actually calls on it.
2. Read `src/haloysius/` for any internal consumers of `RetrievalBackend` — does the core ever call anything beyond `search`/`format_context`?
3. Read Halbert's `context/adapters.py` — how `RAGServiceAdapter` currently works, and how a SourcePrep-backed adapter would look.
4. Read the CoDRAG handoff (`.handoff/HALBERT-INTEGRATION-2026-08-21.md`) for the SourcePrep-side view of this question.
5. Determine: can `prep_search` results be formatted into the `search() -> results` + `format_context() -> str` contract without loss? Or does the core's cognitive tick need access to structural metadata (dependencies, concepts) that the current protocol doesn't carry?
6. If the protocol needs to change: draft the proposed `RetrievalBackend` v2 signature and identify what breaks in the core.

**Read:**
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/seam.py`
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/` (grep for `RetrievalBackend` usage)
- `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/context/adapters.py`
- `/Volumes/4TB-BAD/HumanAI/CoDRAG/.handoff/HALBERT-INTEGRATION-2026-08-21.md`

**Output:** A recommendation (wrap vs. extend) with a concrete protocol diff if extending, and a draft adapter implementation if wrapping.

---

### RQ-A Findings: WRAP — do not extend `RetrievalBackend`

**Researched:** 2026-08-22
**Recommendation:** Wrap `prep_search` behind the existing `RetrievalBackend` protocol unchanged. Do not extend the protocol. Route SourcePrep's other primitives (`prep_impact`, `prep_concepts`, `prep_observe`) to their natural seams, not into `RetrievalBackend`.

#### 1. What the core actually calls on `RetrievalBackend`

**Finding: the core never calls it.** A repo-wide grep of `/Volumes/4TB-BAD/Haloysius/` for `RetrievalBackend`, `get_retrieval_backend`, `get_app_seam`, `register_app_seam`, and `AppSeam` returns matches only inside `seam.py` itself (plus doc references in `README.md`, `CHARTER.md`, `LICENSING-REVIEW.md`). No core module imports or invokes the seam. The protocol is a forward-looking WP-13 contract that has not been wired into any code path yet.

The core has two retrieval-adjacent paths, both currently isolated:

1. **`rag/historical_rag.py`** — a concrete `HistoricalRAG` class with `load()`, `search(query, figure_id, k) -> List[Dict]`, `format_context(results, max_chars) -> str`, and `get_citations(results) -> List[Dict]`. It matches the `RetrievalBackend` protocol shape exactly (same method names, same signatures modulo `figure_id`). But it is only referenced within its own file — no other core module imports `get_historical_rag()` or `retrieve_historical_context()`. It is a legacy figure-scoped RAG that predates the seam abstraction.

2. **`memory_v2/integration.py`** — calls `knowledge.search_text(query, k, embed_fn)` for memory-anchored retrieval. This is a separate path (memory store, not corpus retrieval) and maps to the `memory_store_search` callback, not `RetrievalBackend`.

**Implication:** Because the seam is unconsumed, the contract is free to be shaped correctly before first wiring. There is no existing core call site that would break if the protocol changed — but there is also no evidence that the core needs anything beyond `search` / `format_context`.

#### 2. The cognitive tick does not consume retrieval

`advance_turn()` in `persona/cognition_tick.py` (495 lines, read in full) takes: `cognition`, `user_message`, `assistant_response`, `signals`, `base_path`, `belief_decay_manager`, `thought_generator`, `memory_store_add`, `memory_store_search`. **No retrieval backend parameter.** The tick's six steps (decay → detect → reinforce → promote → conflicts → persist) operate on text and in-memory cognition state. Retrieval is a prompt-assembly concern that happens BEFORE the LLM call (in the SENSING/PLANNING states per CHAT-ARCHITECTURE-VALIDATION §5), not inside the tick.

**Implication:** The question "does the core's cognitive tick need access to structural metadata?" is answered: **no, the tick doesn't need retrieval at all.** Retrieval feeds the prompt; the tick feeds on the prompt's inputs and outputs. The `RetrievalBackend` contract only needs to satisfy the context-assembly step, which needs text to inject into the prompt.

#### 3. Can `prep_search` results fit the existing contract without loss?

**Yes.** SourcePrep's `prep_search` MCP tool (verified in `CoDRAG/src/prep/mcp/server.py`) returns a dict containing:
- `chunks` / `sources`: a list of dicts, each with `source_path` / `file_path`, `score`, `text` / `content`
- `context`: a pre-formatted context string
- `_to_markdown`: a markdown-formatted string with concept hints + subsystem hints
- `concepts`: related concepts (title, content, category) — already injected into `_to_markdown`

This maps cleanly to the protocol:
- `search(query, k) -> List[Dict[str, Any]]` ← the `chunks` list. Each chunk dict gets `text` (from `content`), `score`, `metadata` (file_path, concepts). The protocol's return type is `List[Dict[str, Any]]` — intentionally permissive, no mandated keys beyond `text`.
- `format_context(results, max_chars) -> str` ← the `_to_markdown` field (already formatted by SourcePrep with concept + subsystem hints), truncated to `max_chars`.

**No structural metadata is lost.** The chunk dicts carry `file_path`, `score`, and `concepts` as metadata. If the core's context assembler (or a future core consumer) wants to access `file_path` for citation rendering, it's in the dict. The protocol doesn't mandate it, but it doesn't prohibit it either — `Dict[str, Any]` is open.

#### 4. Why the other SourcePrep primitives do NOT belong on `RetrievalBackend`

The RQ-A question frames SourcePrep's richer primitives (`prep_impact`, `prep_concepts`, `prep_observe`) as candidates for extending `RetrievalBackend`. They are not retrieval-shaped; they map to different seams:

| SourcePrep primitive | Shape | Natural seam | Why not `RetrievalBackend` |
|---|---|---|---|
| `prep_search` | query → text results | `RetrievalBackend` | This IS retrieval. Clean wrap. |
| `prep_impact` | file/symbol → dependency blast radius | `GovernancePolicy` (or new `ImpactBackend`) | This is a safety/dependency query, not corpus search. It answers "what breaks if I change X?" — consumed by the ACTING state before config writes, alongside `GovernancePolicy.check()`. Adding it to `RetrievalBackend` violates single-responsibility and would force every retrieval backend to implement blast-radius. |
| `prep_concepts` | query → rationale/knowledge entries | `RetrievalBackend.search()` (sufficient for MVP) | Concepts have `title` + `content` + `category` — all text. They can be retrieved as text via `prep_search` (SourcePrep's search already surfaces related concepts in `_to_markdown`). A separate `KnowledgeBackend` protocol for structured concept queries is over-engineering for MVP; revisit if the core needs to query concepts by category or assert concept constraints. |
| `prep_observe` | content + file_path → stored observation; query → observations | `memory_store_add` / `memory_store_search` callbacks | This IS memory write/read. The cognitive tick already accepts `memory_store_add` and `memory_store_search` callables. Halbert wires these to SourcePrep's `prep_observe` save/retrieve. No protocol change needed. |

**Key insight:** The question's binary framing (wrap vs. extend `RetrievalBackend`) misses that SourcePrep exposes four distinct capabilities, only one of which is retrieval. The right architecture is a one-to-one mapping from each SourcePrep primitive to its natural seam, not a mega-protocol that bundles all four into `RetrievalBackend`.

#### 5. The async/sync discrepancy

The existing `RetrievalBackend` protocol is synchronous (`def search(...)`). Halbert's current `RAGServiceAdapter` and `ContextAssembler` use `async def search(...)` and `await self.rag.search(...)`. This is a mismatch: Halbert's adapter does not currently satisfy the Haloysius protocol.

**Resolution:** The Haloysius seam should stay synchronous (the core is sync — `advance_turn` is sync, `HistoricalRAG.search` is sync). Halbert's `SourcePrepRetrievalBackend` adapter should be sync and call SourcePrep via the MCP stdio/HTTP interface synchronously (the MCP server processes requests synchronously from the caller's perspective even if internally async). The existing async `RAGServiceAdapter` is a separate Halbert-internal adapter for the legacy ChromaDB path and does not need to satisfy the Haloysius protocol — it will be replaced.

#### 6. Draft adapter implementation

```python
# halbert_core/halbert_core/context/sourceprep_retrieval.py
"""SourcePrep-backed RetrievalBackend for the Haloysius seam.

Wraps SourcePrep's prep_search MCP tool behind the existing
RetrievalBackend protocol (load / search / format_context). No
protocol extension needed — prep_search results carry structural
metadata (file_path, score, concepts) inside the permissive
List[Dict[str, Any]] return type.

The other SourcePrep primitives route to different seams:
- prep_impact  -> GovernancePolicy (blast-radius before config writes)
- prep_observe -> memory_store_add / memory_store_search callbacks
- prep_concepts -> served through prep_search (concepts surface in
  _to_markdown); structured concept queries are a future concern.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.context.sourceprep_retrieval")


class SourcePrepRetrievalBackend:
    """RetrievalBackend implementation backed by SourcePrep prep_search.

    Satisfies haloysius.seam.RetrievalBackend (sync protocol):
    - load() -> bool
    - search(query, k, figure_id) -> List[Dict[str, Any]]
    - format_context(results, max_chars) -> str

    figure_id is ignored (SourcePrep is not figure-scoped; it is
    project-scoped, and the project is resolved at adapter init time).
    """

    def __init__(self, project_id: Optional[str] = None, mcp_client=None):
        """
        Args:
            project_id: SourcePrep project ID for the OS/config index.
                If None, SourcePrep auto-detects from the workspace.
            mcp_client: Optional injected MCP client (for testing).
                If None, the adapter calls SourcePrep via the MCP
                stdio interface on first use.
        """
        self._project_id = project_id
        self._mcp = mcp_client
        self._loaded = False

    def _ensure_mcp(self):
        """Lazy-init the MCP client on first use."""
        if self._mcp is not None:
            return
        # Lightest coupling: call SourcePrep as an MCP server.
        # The MCP client is process-local; requests are synchronous
        # from the caller's perspective.
        from ..integrations.sourceprep_mcp import get_sourceprep_client
        self._mcp = get_sourceprep_client()

    # -- RetrievalBackend protocol ----------------------------------------

    def load(self, figure_id: Optional[str] = None) -> bool:
        """Verify the SourcePrep index is built and ready."""
        self._ensure_mcp()
        try:
            result = self._mcp.call("prep", project_id=self._project_id)
            ready = bool(result.get("index_loaded", False))
            self._loaded = ready
            if not ready:
                logger.warning(
                    "SourcePrep index not loaded for project %s — "
                    "retrieval will return empty results until a build "
                    "completes.",
                    self._project_id or "<auto>",
                )
            return ready
        except Exception as e:
            logger.error("SourcePrep load check failed: %s", e)
            return False

    def search(
        self,
        query: str,
        k: int = 3,
        figure_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search the OS/config corpus via prep_search.

        Returns a list of result dicts with at least a 'text' key,
        plus 'score', 'file_path', and 'concepts' as metadata.
        figure_id is accepted for protocol compatibility but ignored
        (SourcePrep is project-scoped, not figure-scoped).
        """
        self._ensure_mcp()
        try:
            raw = self._mcp.call(
                "prep_search",
                query=query,
                k=k,
                project_id=self._project_id,
            )
        except Exception as e:
            logger.error("SourcePrep prep_search failed: %s", e)
            return []

        if not isinstance(raw, dict):
            return []

        chunks = raw.get("chunks") or raw.get("sources") or []
        results: List[Dict[str, Any]] = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            text = chunk.get("text") or chunk.get("content") or ""
            if not text:
                continue
            results.append({
                "text": text,
                "score": chunk.get("score", 0.0),
                "metadata": {
                    "file_path": chunk.get("source_path")
                        or chunk.get("file_path", ""),
                    "concepts": raw.get("concepts", []),
                },
                # Stash the pre-formatted markdown so format_context can
                # use SourcePrep's own rendering (with concept + subsystem
                # hints) instead of re-formatting from chunks.
                "_sourceprep_markdown": raw.get("_to_markdown", ""),
            })
        return results

    def format_context(
        self,
        results: List[Dict[str, Any]],
        max_chars: int = 1500,
    ) -> str:
        """Format results into a context string for prompt injection.

        Prefers SourcePrep's own _to_markdown rendering (which includes
        concept and subsystem hints) when available; falls back to a
        simple chunk listing otherwise.
        """
        if not results:
            return ""

        # Use SourcePrep's pre-formatted markdown if the first result
        # carries it (all results from one prep_search call share it).
        sourceprep_md = results[0].get("_sourceprep_markdown", "")
        if sourceprep_md:
            if len(sourceprep_md) > max_chars:
                return sourceprep_md[:max_chars].rsplit("\n", 1)[0] + "\n…"
            return sourceprep_md

        # Fallback: render from chunks.
        lines = ["## System Context (SourcePrep)"]
        total = 0
        for i, r in enumerate(results, 1):
            text = r.get("text", "").strip()
            meta = r.get("metadata", {})
            path = meta.get("file_path", "")
            if not text:
                continue
            if total + len(text) > max_chars:
                remaining = max_chars - total
                if remaining > 100:
                    text = text[:remaining] + "…"
                else:
                    break
            citation = f" [{path}]" if path else ""
            lines.append(f"[{i}]{citation} {text}")
            total += len(text)
        return "\n".join(lines) if len(lines) > 1 else ""
```

#### 7. What breaks if the protocol is later extended

Nothing in the core breaks today (the seam is unconsumed). If a future core consumer needs structured concept access beyond text retrieval, the right move is a new optional protocol (`KnowledgeBackend`) alongside `RetrievalBackend`, not an extension of `RetrievalBackend` itself. The `AppSeam` protocol's `get_retrieval_backend() -> Optional[RetrievalBackend]` pattern extends naturally: add `get_knowledge_backend() -> Optional[KnowledgeBackend]` and `get_impact_backend() -> Optional[ImpactBackend]` as separate accessors. Consumers that don't implement them get `None` and the core degrades gracefully — the same pattern already used for `get_model_backend` / `get_retrieval_backend` / `get_governance`.

#### 8. Summary

| Question | Answer |
|---|---|
| Does the core call `RetrievalBackend` beyond `search`/`format_context`? | **No** — the seam is defined but unconsumed. Zero core call sites. |
| Does the cognitive tick need structural metadata from retrieval? | **No** — the tick doesn't call retrieval at all. Retrieval feeds the prompt (SENSING/PLANNING states), not the tick. |
| Can `prep_search` results fit `search() -> List[Dict]` + `format_context() -> str` without loss? | **Yes** — chunks map to result dicts (text + metadata), `_to_markdown` maps to `format_context` output. Structural metadata rides inside `Dict[str, Any]`. |
| Should `RetrievalBackend` be extended for `prep_impact` / `prep_concepts` / `prep_observe`? | **No** — these are not retrieval. `prep_impact` → `GovernancePolicy`; `prep_observe` → memory callbacks; `prep_concepts` → served through `prep_search` text. |
| Wrap or extend? | **Wrap.** `prep_search` behind the unchanged `RetrievalBackend`. Draft adapter above. |

**Feeds:** Phase 2 (SourcePrep integration — build the adapter, register it via `register_app_seam`) and Phase 4 (Haloysius wiring — the adapter is the `RetrievalBackend` the core calls during SENSING/PLANNING context assembly).

---

### RQ-A Audit — Reverse-engineering the plan (2026-08-22)

**Purpose:** Scrutinize every claim in the RQ-A findings above against the actual code. Document what holds, what is wrong, what is imprecise, and what was overlooked. The recommendation (WRAP) survives the audit, but the draft adapter has a real bug and two claims need correction.

---

#### A1. Claims that HOLD under scrutiny

| Claim | Verification | Status |
|---|---|---|
| The seam is unconsumed — no core module imports `RetrievalBackend` or calls `get_app_seam()` | Repo-wide grep of `/Volumes/4TB-BAD/Haloysius/` for `RetrievalBackend`, `get_app_seam`, `register_app_seam`, `AppSeam`, `ModelBackend`, `GovernancePolicy` returns matches only in `seam.py` itself + docs (`README.md`, `CHARTER.md`, `LICENSING-REVIEW.md`). Zero source-code consumers. | **HOLDS** |
| The cognitive tick has no retrieval parameter | Read `cognition_tick.py` in full (495 lines). `advance_turn()` signature: `(cognition, user_message, assistant_response, signals, *, base_path, belief_decay_manager, thought_generator, memory_store_add, memory_store_search)`. No retrieval backend. The tick operates on text and in-memory cognition state. | **HOLDS** |
| `prep_search` results can fit `search() -> List[Dict]` + `format_context() -> str` | The HTTP API (`POST /projects/{id}/context` with `structured: true`) returns `chunks` (list of dicts with `source_path`, `section`, `score`, `text`) and `context` (formatted string). These map to the protocol. | **HOLDS** (but see A2 — the MCP tool path does NOT work) |
| `figure_id` can be ignored | SourcePrep is project-scoped, not figure-scoped. The protocol's `figure_id` parameter is a legacy from `HistoricalRAG`'s figure-filtering. Halbert has no figures. Ignoring it is safe. | **HOLDS** |
| `prep_observe` maps to `memory_store_add` / `memory_store_search` callbacks | The cognitive tick accepts these as optional callables. `prep_observe` save = `memory_store_add`; `prep_observe` retrieve = `memory_store_search`. No protocol change needed. | **HOLDS** |
| `prep_concepts` is served through `prep_search` text retrieval for MVP | SourcePrep's search already surfaces related concepts in the `_to_markdown` output. Structured concept queries (by category, with constraint assertions) are a future concern. | **HOLDS** |
| The `RetrievalBackend` protocol should stay sync | The Haloysius core is sync (`advance_turn` is sync, `HistoricalRAG.search` is sync). A sync adapter calling a local HTTP daemon via `requests` is consistent. | **HOLDS** |

---

#### A2. BUG: The draft adapter uses the MCP tool path, which does NOT return `chunks`

**The error:** The draft adapter (§6 above) does `raw = self._mcp.call("prep_search", ...)` then `raw.get("chunks") or raw.get("sources")`. This would return `None`/empty.

**The root cause:** The SourcePrep MCP `tool_search` method (`CoDRAG/src/prep/mcp/server.py:900`) calls the HTTP API and gets `data` (which includes `chunks`), but then passes it through `_format_context_response` (`server.py:1551`), which extracts only:
- `context` (string)
- `chunks_used` (int — **count**, not the list)
- `total_chars`, `estimated_tokens`
- `compression` (optional metadata)

**The `chunks` list is dropped.** The MCP tool then augments the result with `_to_markdown` (a pre-formatted string with concept + subsystem hints), `applied_scope`, `applied_role`. The final MCP return dict has no `chunks` key.

**The fix:** The adapter must call the **HTTP API directly** (`POST http://localhost:8400/projects/{id}/context` with `structured: true, include_sources: true`), not the MCP tool. The HTTP API response includes the full `chunks` list with `source_path`, `section`, `score`, `text` — exactly what `search() -> List[Dict[str, Any]]` needs.

This is consistent with the CoDRAG handoff (`HALBERT-INTEGRATION-2026-08-21.md` §5): *"Halbert will consume SourcePrep as an MCP server (lightest coupling) initially, possibly moving to the HTTP API or embedded library for hot paths."* The retrieval adapter IS a hot path (called every turn), so the HTTP API is the right choice from the start.

**Corrected adapter design:** Replace the MCP client with a sync HTTP client (`requests` or `urllib`) calling `POST /projects/{project_id}/context`. The response's `chunks` list maps directly to `search()` results; the response's `context` string (or a re-formatted version) maps to `format_context()`.

---

#### A3. IMPRECISE: `prep_impact` does NOT map to `GovernancePolicy`

**The error:** §4 of the findings maps `prep_impact` → `GovernancePolicy`, calling it "a safety/dependency query, consumed by the ACTING state before config writes, alongside `GovernancePolicy.check()`."

**The correction:** `GovernancePolicy` in `seam.py` is a **content safety** protocol — `check(message) -> {safe, on_topic, redirect_suggestion}`. It answers "is this message safe and on-topic?" It is NOT a config-safety or blast-radius protocol. `prep_impact` answers "what breaks if I change this file?" — a fundamentally different question.

**The right mapping:** `prep_impact` is **Halbert-internal**, not a Haloysius seam concern. Halbert's ACTING handler calls `prep_impact` directly (via HTTP API) before config writes, alongside Halbert's own `approval/` + `autonomy/` + `policy/` modules. The Haloysius `GovernancePolicy` is about content governance (is the AI's response safe); Halbert's config-safety layer is about action governance (is this config change safe). These are separate concerns at separate layers.

If a future Haloysius consumer needs blast-radius as a seam, the right protocol would be a new `ImpactBackend` (not overloading `GovernancePolicy`). But for Halbert's MVP, `prep_impact` is called directly — no seam needed.

---

#### A4. OVERLOOKED: The core has a pre-`seam.py` injection pattern still in use

**Finding:** `scenario/generator.py` (line 17-25) has its own ad-hoc provider injection:
```python
# WP-13: Provider registry — the app registers its model provider factory
# here so the core never imports from api/.  This is a temporary seam
# until the full ModelBackend Protocol is defined.
_provider_factory = None

def set_provider_factory(factory):
    global _provider_factory
    _provider_factory = factory
```

This is a **live, pre-`seam.py` seam** that hasn't been migrated to `seam.py`'s `ModelBackend` protocol. It shows that:
1. The core has a prior pattern for capability injection (factory callable, sync, module-global registry).
2. `seam.py` was written as the replacement (`ModelBackend` protocol) but the migration hasn't happened — `scenario/generator.py` still uses `set_provider_factory`, not `get_app_seam().get_model_backend()`.
3. This is consistent with the "seam is unconsumed" finding — `seam.py` is the intended future contract, not the current one.

**Impact on RQ-A:** None directly. The `RetrievalBackend` is still unconsumed. But this tells us that when Halbert wires the seam, it should verify whether the core has been migrated to `seam.py` or still uses the ad-hoc patterns. If the core still uses `set_provider_factory` for model access, Halbert may need to register via BOTH the old pattern AND `seam.py` during the transition.

---

#### A5. OVERLOOKED: Halbert has NO SourcePrep client — the adapter references a nonexistent module

**Finding:** The draft adapter imports `from ..integrations.sourceprep_mcp import get_sourceprep_client`. A grep of `halbert_core/` for `sourceprep`, `SourcePrep`, `prep_search`, `MCPClient` returns zero source-code matches (all hits are in `.handoff/` docs and `documentation/`).

**Impact:** The adapter cannot work as written. Halbert needs to build a SourcePrep HTTP client first. This is a Phase 2 prerequisite, not a Phase 4 item.

**Corrected prerequisite chain:**
1. **Phase 2a:** Build `halbert_core/integrations/sourceprep_client.py` — a sync HTTP client wrapping `POST /projects/{id}/context`, `POST /projects/{id}/concepts/search`, `POST /projects/{id}/observations`, `GET /projects/{id}/trace/impact`. This is Halbert-internal, not a Haloysius seam.
2. **Phase 2b:** Build `SourcePrepRetrievalBackend` (the adapter from §6, corrected per A2 to use the HTTP client, not MCP).
3. **Phase 4:** Register the adapter via `register_app_seam()` so the core can call it.

---

#### A6. OVERLOOKED: The `_to_markdown` stashing trick is unsound

**The error:** The draft adapter stashes `_to_markdown` on the first result dict (`results[0]["_sourceprep_markdown"]`), then `format_context` reads it from there. This assumes all results come from one `prep_search` call and share the same `_to_markdown`.

**Why it's unsound:** The `RetrievalBackend` protocol's `search()` returns a list, and `format_context()` receives that list. The caller (the core's context assembler) may merge, filter, or re-order results from multiple `search()` calls. If results from two calls are merged, only the first call's `_to_markdown` survives — and it may not correspond to the results being formatted. If results are filtered, the stashed `_to_markdown` may be on a result that was dropped.

**The fix:** With the A2 correction (HTTP API, not MCP), this trick is no longer needed. The HTTP API returns `chunks` (structured) AND `context` (pre-formatted string). The adapter's `format_context()` should format from the `chunks` list directly, not rely on a stashed pre-formatted string. If SourcePrep's own formatting is desired, the adapter can call the HTTP API's `context` field directly — but that's a single-call concern, not a multi-call merge concern.

---

#### A7. The audited recommendation

**The WRAP recommendation survives.** The core never calls `RetrievalBackend`, the cognitive tick doesn't need retrieval, and `prep_search` (via HTTP API) fits the existing protocol. The errors found are in the adapter implementation details, not the architectural decision.

**Corrected summary:**

| Original claim | Audit verdict |
|---|---|
| Seam is unconsumed | **HOLDS** — zero core consumers. Pre-seam.py pattern in `scenario/generator.py` noted but doesn't change the conclusion. |
| Cognitive tick doesn't need retrieval | **HOLDS** — verified by full file read. |
| `prep_search` fits the contract | **HOLDS via HTTP API, NOT via MCP tool.** The MCP tool drops `chunks`. Adapter must use HTTP API. |
| `prep_impact` → `GovernancePolicy` | **WRONG** — `GovernancePolicy` is content safety, not config safety. `prep_impact` is Halbert-internal, called directly. |
| `prep_observe` → memory callbacks | **HOLDS.** |
| `prep_concepts` → served through `prep_search` | **HOLDS for MVP.** |
| Draft adapter implementation | **HAS BUG** — uses MCP tool (no `chunks` in return), references nonexistent module, uses unsound `_to_markdown` stashing. Must be rewritten to use HTTP API. |
| WRAP vs EXTEND | **WRAP survives.** No reason to extend `RetrievalBackend` emerged from the audit. |

**Corrected adapter design (replaces §6):**

```python
# halbert_core/halbert_core/context/sourceprep_retrieval.py
"""SourcePrep-backed RetrievalBackend for the Haloysius seam.

Calls the SourcePrep HTTP API directly (not the MCP tool — the MCP
tool drops the chunks list, returning only a pre-formatted string).
The HTTP API returns structured chunks with source_path, score, and
text, which map cleanly to the RetrievalBackend protocol.

Prerequisite: halbert_core/integrations/sourceprep_client.py must
exist (Phase 2a). This adapter is Phase 2b.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.context.sourceprep_retrieval")


class SourcePrepRetrievalBackend:
    """RetrievalBackend backed by SourcePrep's HTTP API.

    Satisfies haloysius.seam.RetrievalBackend (sync):
    - load() -> bool
    - search(query, k, figure_id) -> List[Dict[str, Any]]
    - format_context(results, max_chars) -> str

    figure_id is accepted for protocol compatibility but ignored
    (SourcePrep is project-scoped, not figure-scoped).
    """

    def __init__(self, project_id: Optional[str] = None, http_client=None):
        """
        Args:
            project_id: SourcePrep project ID for the OS/config index.
                If None, SourcePrep auto-detects from the workspace.
            http_client: Optional injected HTTP client (for testing).
                If None, creates one from integrations.sourceprep_client.
        """
        self._project_id = project_id
        self._http = http_client
        self._loaded = False

    def _ensure_client(self):
        if self._http is not None:
            return
        from ..integrations.sourceprep_client import get_sourceprep_client
        self._http = get_sourceprep_client()

    # -- RetrievalBackend protocol ----------------------------------------

    def load(self, figure_id: Optional[str] = None) -> bool:
        """Verify the SourcePrep index is built and ready."""
        self._ensure_client()
        try:
            result = self._http.get(f"/projects/{self._project_id}")
            ready = bool(result.get("index", {}).get("exists", False))
            self._loaded = ready
            return ready
        except Exception as e:
            logger.error("SourcePrep load check failed: %s", e)
            return False

    def search(
        self,
        query: str,
        k: int = 3,
        figure_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search the OS/config corpus via SourcePrep HTTP API.

        Calls POST /projects/{id}/context with structured=true,
        include_sources=true. Returns the chunks list, each mapped
        to a result dict with 'text', 'score', and 'metadata'.
        """
        self._ensure_client()
        try:
            data = self._http.post(
                f"/projects/{self._project_id}/context",
                json={
                    "query": query,
                    "k": k,
                    "structured": True,
                    "include_sources": True,
                    "include_scores": True,
                },
            )
        except Exception as e:
            logger.error("SourcePrep context search failed: %s", e)
            return []

        if not isinstance(data, dict):
            return []

        chunks = data.get("chunks", [])
        results: List[Dict[str, Any]] = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            text = chunk.get("text", "")
            if not text:
                continue
            results.append({
                "text": text,
                "score": chunk.get("score", 0.0),
                "metadata": {
                    "file_path": chunk.get("source_path", ""),
                    "section": chunk.get("section", ""),
                    "lod": chunk.get("lod"),
                    "truncated": chunk.get("truncated", False),
                },
            })
        return results

    def format_context(
        self,
        results: List[Dict[str, Any]],
        max_chars: int = 1500,
    ) -> str:
        """Format results into a context string for prompt injection.

        Renders from the structured chunks (not a pre-formatted string),
        so it works correctly even if the caller merges/filters results
        from multiple search() calls.
        """
        if not results:
            return ""

        lines = ["## System Context (SourcePrep)"]
        total = 0
        for i, r in enumerate(results, 1):
            text = r.get("text", "").strip()
            meta = r.get("metadata", {})
            path = meta.get("file_path", "")
            if not text:
                continue
            if total + len(text) > max_chars:
                remaining = max_chars - total
                if remaining > 100:
                    text = text[:remaining] + "..."
                else:
                    break
            citation = f" [{path}]" if path else ""
            lines.append(f"[{i}]{citation} {text}")
            total += len(text)

        return "\n".join(lines) if len(lines) > 1 else ""
```

**Key changes from the original draft:**
1. Uses HTTP API (`POST /projects/{id}/context`), not MCP tool — fixes the missing-`chunks` bug.
2. `format_context` renders from structured chunks, not a stashed `_to_markdown` string — fixes the unsound stashing.
3. No `_sourceprep_markdown` field on result dicts — results are clean `Dict[str, Any]` with `text`, `score`, `metadata`.
4. Prerequisite noted: `integrations/sourceprep_client.py` must be built first (Phase 2a).

---

### RQ-B: System-state predicates — consumer-side or core extension?

**Origin:** RQ-ledger from CHAT-ARCHITECTURE-VALIDATION §9

**Context:** Haloysius's continuity ledger uses persona-chat-shaped predicates (`wearing`, `at_location`, `feeling`, `relationship_with`). Halbert needs system-state predicates (`disk_health`, `service_status`, `config_state`, `thermal_state`). Haloysius is designed to be agnostic. The founder leans toward consumer-side (Halbert defines its own predicates behind the seam) because this is an unusual case ("AI must identify as the computer") whereas most Haloysius consumers will have standard persona-shaped predicates.

**Investigate:**
1. Read `src/haloysius/context/continuity.py` — how predicates are defined, stored, and queried. Are they hardcoded or extensible via configuration/injection?
2. Read `src/haloysius/persona/` — do any persona cognition functions depend on specific predicate names, or are predicates generic key-value pairs?
3. Read `src/haloysius/memory_v2/` or equivalent — does the memory store care about predicate shape, or is it schema-free?
4. Determine: can Halbert define its own predicate set without touching core code? If yes, how (env vars? config file? injected callable?). If no, what's the minimal core change?
5. Draft Halbert's initial predicate set: what system states does the continuity ledger need to track? Map each to a source (e.g., `disk_health` ← config/snapshot.py + SMART data, `service_status` ← systemd, `config_state` ← SourcePrep concepts).

**Read:**
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/context/continuity.py`
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/` (grep for predicate usage)
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/` (grep for `predicate` or `ledger`)
- `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/config/snapshot.py`
- `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/discovery/` (for system state sources)

**Output:** A predicate extensibility assessment (consumer-side feasible or not) + Halbert's draft predicate schema with data sources mapped.

---

## RQ-B Findings — System-state predicates: consumer-side or core extension?

**Researched:** 2026-08-22
**Verdict:** **Consumer-side is feasible with ZERO core changes for storage and rendering.** One optional, minimal core enhancement (injectable renderer) is recommended for first-person prose quality, but is not required for MVP.

> **SCRUTINY NOTE (2026-08-22):** These findings were reverse-engineered and verified against source code. The core verdict holds, but one critical correction was found: `_render_natural` (xlarge/large tier) silently drops subjects other than `persona`/`user`/`scene`/`world` — the original §1 claim that "unknown predicates fall into an `other` bucket" was true only for unknown predicates *within the `persona` subject*, not for unknown subjects. This is a non-issue at the medium tier (the default), which renders all subjects. Full scrutiny with 8 corrections (1 critical, 1 medium, 4 low, 2 trivial) is documented in `<ref_file file="/Volumes/4TB-BAD/Halbert/.handoff/RQ-B-SCRUTINY-2026-08-22.md" />`. Key corrections: (C1) use medium tier or fix `_render_natural` for natural tier, (C4) packaging depends on WP-12 for subtractive install, (C5) use separate `db_path` to avoid persona_id collision.

---

### 1. How the continuity ledger actually works

The ledger is a **generic (subject, predicate, object) triple store** — not a persona-shaped schema. Three layers, each with a different degree of hardcoding:

**Layer 1 — Storage (`memory_v2/temporal_graph.py`): FULLY GENERIC.**
`TemporalStateLedger.record(persona_id, subject, predicate, object, source, confidence, priority)` takes five free-form strings plus a priority enum (`critical`/`high`/`medium`/`low`). The SQLite schema (`<ref_file file="/Volumes/4TB-BAD/Haloysius/src/haloysius/memory_v2/temporal_graph.py" />`) is:
```sql
CREATE TABLE state_triples (
    persona_id TEXT, subject TEXT, predicate TEXT, object TEXT,
    valid_from TEXT, valid_to TEXT, source TEXT, confidence REAL, priority TEXT
);
```
No enum, no validation, no foreign key on predicate names. Any consumer can `record()` any predicate string. `get_current(persona_id)` returns whatever triples exist, ordered by priority. **A Halbert predicate like `("self", "disk_health", "sda: SMART warning, 1 reallocated sector")` stores and retrieves identically to a persona predicate like `("persona", "wearing", "red dress")`.**

**Layer 2 — Rendering (`context/state_renderer.py`): GENERIC WITH PERSONA-SHAPED PROSE SPECIAL-CASES.**
`AdaptiveStateRenderer` (`<ref_file file="/Volumes/4TB-BAD/Haloysius/src/haloysius/context/state_renderer.py" />`) has three tiers:
- **`_render_minimal`** (small/tiny tiers): pipe-separated `[STATE]` line. Fully generic — just joins `t.object` values. Unknown predicates work.
- **`_render_structured`** (medium tier, the default `DEFAULT_TIER = "medium"`): `Label: value` lines. Fully generic via `_label()` fallback: `predicate.replace("_", " ").title()`. So `disk_health` → "Disk Health: …". Unknown predicates work.
- **`_render_natural`** (xlarge/large tiers): prose under `[CURRENT STATE]`. **This is the only tier with hardcoded predicate names.** It special-cases `at_location` → "You are at …", `wearing` → "wearing …", `feeling` → "You feel …", `current_activity` → "You are …". **All other predicates fall into an `other` bucket** that renders as `f"{_label(t.predicate)}: {t.object}"` — the same generic fallback. So `disk_health` renders as "Disk Health: sda: SMART warning" even in the natural tier.

The `_PREDICATE_LABELS` dict (`wearing`→`Wearing`, `at_location`→`Location`, etc.) is only a cosmetic label map. Unknown predicates get the title-case fallback. **No predicate name is ever rejected or mishandled.**

**Layer 3 — Writers (the state machines + `persona_state.sync_to_ledger`): HARDCODED, but these are *writers*, not the ledger.**
- `clothing_state_machine.py` writes `("persona", "wearing", …)` — hardcoded.
- `location_state_machine.py` writes `("persona", "at_location", …)` — hardcoded.
- `persona_state.sync_to_ledger()` writes `("persona", "feeling", …)` and `("persona", "relationship_warmth", …)` — hardcoded.

These writers are persona-shaped because they extract persona state from chat text. **Halbert does not need them.** Halbert's writers will extract system state from monitors, not from chat text, and will record different predicates. The writers are consumer-side code; the ledger doesn't know or care who writes to it.

---

### 2. Does persona cognition depend on specific predicate names? NO.

`advance_turn()` in `cognition_tick.py` (`<ref_file file="/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/cognition_tick.py" />`) operates on `PersonaCognition` (drives, worries, emotions, beliefs, thoughts). **It never reads from or writes to the state ledger.** The ledger is touched only by:
1. The three writers above (called from `continuity._advance()`).
2. `continuity.render_state_block()` (read-only, for prompt injection).

The cognitive tick's trigger detection (`thought_triggers.py`), belief evidence extraction, thought promotion, and conflict detection all work on in-memory cognition objects, not ledger triples. **Predicate names are invisible to the cognitive tick.** Halbert can define any predicate set without affecting cognition.

---

### 3. Does the seam expose the ledger? NO — and that's the one gap.

`seam.py` (`<ref_file file="/Volumes/4TB-BAD/Haloysius/src/haloysius/seam.py" />`) exposes four protocols: `ModelBackend`, `RetrievalBackend`, `GovernancePolicy`, `AppSeam`. **There is no `StateLedger` or `StateRenderer` protocol.** The ledger is accessed directly via `get_state_ledger()` from `memory_v2.temporal_graph`, and the renderer via `AdaptiveStateRenderer()` from `context.state_renderer`.

This means Halbert currently has two ways to access the ledger:
1. **Direct import** — `from haloysius.memory_v2.temporal_graph import get_state_ledger`. This works today, no core change. Halbert calls `get_state_ledger().record(...)` with its own predicates and `render_state_block()` for rendering. This is the consumer-side path the founder leaned toward.
2. **Via a new seam protocol** — add a `StateBackend` protocol to `seam.py` so the ledger is accessed through the registered `AppSeam` rather than by direct import. This is a cleaner separation but not required for MVP.

**`continuity.render_state_block(persona_id)` is already generic and callable as-is.** Halbert passes its own `persona_id` (e.g., `"halbert"`) and gets back whatever triples exist for that ID. No core change needed for rendering at the medium tier (the default).

---

### 4. The one coupling point: `continuity._advance()`

`continuity.advance_from_user_message()` and `advance_from_response()` (`<ref_file file="/Volumes/4TB-BAD/Haloysius/src/haloysius/context/continuity.py" />`) hardcode calls to `update_clothing_from_message` and `update_location_from_message`. These are persona-shaped: they parse chat text for clothing/location changes.

**Halbert should NOT call these.** Halbert's system state doesn't change based on chat text — it changes based on system events (disk failures, service restarts, config drift). Halbert's equivalent of `_advance()` will be a system-state sync that reads from monitors/scanners and writes to the ledger. This is pure consumer-side code; Halbert simply doesn't invoke the persona-shaped advance functions.

`render_state_block()` remains usable as-is because it's generic.

---

### 5. Predicate extensibility assessment

| Question | Answer |
|----------|--------|
| Can Halbert define its own predicate set without touching core code? | **YES.** `record()` accepts any string. |
| How does Halbert inject its predicates? | Direct call: `get_state_ledger().record("halbert", subject, predicate, object, source, priority=…)`. No config file, no env var, no injected callable needed — just call the function. |
| Does the renderer handle unknown predicates? | **YES** at medium (default) and minimal tiers. At natural tier (xlarge/large), unknown predicates fall into a generic `Label: value` bucket — readable but not first-person prose. |
| Does persona cognition depend on predicate names? | **NO.** The cognitive tick never reads the ledger. |
| Does the memory store care about predicate shape? | **NO.** The ledger is schema-free SQLite; `memory_v2` has no predicate validation. |
| What's the minimal core change if we want first-person prose? | Make `AdaptiveStateRenderer` injectable (see §7 below). ~15 lines in `continuity.py` + a protocol in `seam.py`. Optional, not MVP-blocking. |

**Conclusion: consumer-side is fully feasible with zero core changes.** The founder's lean was correct. The ledger was designed to be agnostic, and it is.

---

### 6. Halbert's draft predicate schema with data sources mapped

Halbert's `persona_id` in the ledger will be `"halbert"` (or the user-renamed value). Subjects group predicates by what they describe. The predicate names follow the existing snake_case convention so the renderer's title-case fallback produces clean labels.

#### Subject: `self` (the computer's own state)

| Predicate | Example object | Source (Halbert module) | Priority |
|-----------|----------------|------------------------|----------|
| `disk_health` | `sda: SMART warning, 1 reallocated sector` | `discovery/scanners/storage.py` (`smart_status` field) | critical/warning/medium based on severity |
| `thermal_state` | `CPU 72°C, approaching throttle threshold` | `discovery/scanners/thermal.py` (`_scan_hwmon_sensors`, `_scan_thermal_zones`) | high when near threshold, medium otherwise |
| `power_state` | `on battery, 42% remaining` | `discovery/scanners/laptop.py` (battery) / `power.py` | high on battery, low on AC |
| `boot_state` | `last boot 3d ago, uptime stable` | `discovery/scanners/boot.py` | low |
| `load_state` | `load avg 4.2 on 8 cores` | `discovery/scanners/process.py` / `system_profile.py` | medium when high |

#### Subject: `service` (per-service status)

| Predicate | Example object | Source | Priority |
|-----------|----------------|--------|----------|
| `service_status` | `nginx: failed (exit code 1)` | `discovery/scanners/service.py` (`service_discovery` factory, `status` field) | critical if failed, medium if running |
| `service_enabled` | `nginx: enabled` | `discovery/scanners/service.py` (`enabled` field) | low |

Each service gets its own triple with `subject = f"service:{name}"` so the ledger tracks per-service history. The renderer groups by subject, so services cluster naturally.

#### Subject: `config` (configuration state)

| Predicate | Example object | Source | Priority |
|-----------|----------------|--------|----------|
| `config_state` | `42 files tracked, last snapshot 2h ago` | `config/snapshot.py` (`snapshot()` return value) | low |
| `config_drift` | `3 files changed since last snapshot: /etc/nginx/nginx.conf, …` | `config/drift.py` (`diff_snapshots()` return value) | high when drift detected |
| `config_managed` | `nginx.conf: managed by Halbert (applied 2026-08-20)` | SourcePrep `prep_observe` / Halbert's applied-changes log | medium |

#### Subject: `network` (network state)

| Predicate | Example object | Source | Priority |
|-----------|----------------|--------|----------|
| `network_state` | `2 interfaces up, default route via 192.168.1.1` | `discovery/scanners/network.py` | low |
| `connectivity` | `internet reachable, DNS resolving` | `discovery/scanners/network.py` | high when down |

#### Subject: `security` (security posture)

| Predicate | Example object | Source | Priority |
|-----------|----------------|--------|----------|
| `security_state` | `no anomalies, last scan 1h ago` | `discovery/scanners/security.py` | medium |
| `security_anomaly` | `unauthorized SSH login attempts: 47 in last hour` | `discovery/scanners/security.py` / `error_log.py` | critical |

#### Subject: `backup` (backup state)

| Predicate | Example object | Source | Priority |
|-----------|----------------|--------|----------|
| `backup_state` | `rsync-home: last run 6h ago, success` | `discovery/scanners/backup.py` (`backup_discovery` factory) | medium |
| `backup_stale` | `rsync-home: last run 3d ago, expected daily` | `discovery/scanners/backup.py` (schedule vs. last_run) | high when stale |

#### Rendering example (medium tier, what the LLM sees)

With the above predicates recorded, `render_state_block("halbert")` produces:
```
[CURRENT STATE]
Disk Health: sda: SMART warning, 1 reallocated sector
Thermal State: CPU 72°C, approaching throttle threshold
Service Status: nginx: failed (exit code 1)
Config Drift: 3 files changed since last snapshot: /etc/nginx/nginx.conf, ...
Security Anomaly: unauthorized SSH login attempts: 47 in last hour
Backup Stale: rsync-home: last run 3d ago, expected daily
```
This is exactly the kind of system-state block Halbert needs in the prompt — and it required zero core changes.

---

### 7. Optional core enhancement: injectable renderer (NOT required for MVP)

The one place the core's renderer is persona-shaped is `_render_natural` (xlarge/large tiers), which produces prose like "You are at the cafe, wearing a red dress. You feel happy." For Halbert, the equivalent first-person prose would be "I am experiencing a SMART warning on my primary drive. My CPU is running hot at 72°C." The generic fallback produces "Disk Health: …" instead — readable but not first-person.

**If first-person prose is desired at the xlarge/large tier**, the minimal core change is:

1. Add a `StateRenderer` protocol to `seam.py` (~10 lines):
   ```python
   @runtime_checkable
   class StateRenderer(Protocol):
       def render(self, triples: List["StateTriple"], tier: str, budget_pressure: float) -> str: ...
   ```
2. In `continuity.render_state_block()`, check `get_app_seam()` for a registered renderer before falling back to `AdaptiveStateRenderer()` (~5 lines).
3. Halbert implements `StateRenderer` with first-person system-state prose and registers it at startup.

**This is ~15 lines of core code and is strictly optional.** The medium tier (default) already works generically. Recommendation: **ship MVP with the generic renderer; add the injectable renderer only if the xlarge/large prose quality becomes a priority.** The founder's "AI identifies as the computer" framing (RQ8) makes first-person prose desirable, but it's a polish item, not a blocker.

---

### 8. Implementation path for Phase 4

1. **Halbert creates a `SystemStateSync` class** (consumer-side, in `halbert_core/`) that:
   - Runs after each discovery scan cycle (or on a timer).
   - Reads from `DiscoveryEngine.get_all()` and the config snapshot/drift modules.
   - Maps discoveries to predicates per the schema in §6.
   - Calls `get_state_ledger().record("halbert", subject, predicate, object, source, priority)`.
2. **Halbert calls `render_state_block("halbert")`** during prompt assembly (in the new context assembler, replacing the system-state injection blocks in `chat.py` — see RQ-D).
3. **Halbert does NOT call** `continuity.advance_from_user_message()` or `advance_from_response()` — those are persona-shaped. System state advances from monitors, not chat.
4. **Optional later:** implement a `StateRenderer` for first-person prose and register via the seam (if the §7 enhancement is added to core).

**No Haloysius core changes are required for this path.** The founder's consumer-side lean is confirmed correct.

---

### RQ-C: System-event triggers for the cognitive tick

**Origin:** RQ-tick-trigger from CHAT-ARCHITECTURE-VALIDATION §9

**Context:** Haloysius's cognitive tick (`advance_turn` in `persona/cognition_tick.py`) uses trigger detection (`thought_triggers.py`) that is persona-emotion-shaped (e.g., `worries_about`, `curious_about`). Halbert needs system events to map onto triggers — e.g., a failing drive triggers `worries_about /dev/sda1`, a config change triggers `notices config drift in /etc/nginx/`. The founder says this requires deep research and sees many opportunities to investigate.

**Investigate:**
1. Read `src/haloysius/persona/thought_triggers.py` — the full trigger detection mechanism. How are triggers defined, evaluated, and fired? Are they hardcoded or injectable?
2. Read `src/haloysius/persona/cognition_tick.py` — how `advance_turn` uses triggers in the detect step. What happens when a trigger fires?
3. Map system event sources to trigger semantics:
   - Disk SMART warnings → `worries_about <device>`
   - Service failures → `alarmed_by <service>`
   - Config drift detected → `notices <drift_description>`
   - New device discovered → `curious_about <device>`
   - High temperature → `uncomfortable_with <thermal_state>`
   - Security anomaly → `concerned_about <anomaly>`
4. Determine: are triggers extensible via injection (consumer-side) or do they require core changes?
5. Investigate: should system triggers be periodic (polled from system state) or event-driven (pushed from monitors)? How does this interact with the tick's cadence?
6. Consider: the "AI identifies as the computer" framing — when a drive fails, is the trigger "I am experiencing disk failure" (first-person) or "I notice /dev/sda1 is failing" (observer)? This affects the trigger language and the self-model.

**Read:**
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/thought_triggers.py`
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/cognition_tick.py` (especially the detect step)
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/` (grep for `trigger`)
- `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/discovery/` (system event sources)
- `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/config/drift.py` (config drift detection)

**Output:** A trigger extensibility assessment + a draft mapping of system events to cognitive triggers + a recommendation on first-person vs. observer trigger language.

---

### RQ-D: chat.py context-injection audit

**Origin:** RQ-context-port from CHAT-ARCHITECTURE-VALIDATION §9

**Context:** `chat.py` is 4,240 lines and contains context-injection logic that may be worth porting into the new context assembler (the one that will feed the composed-loop architecture). Before `chat.py` is cut (Phase 4), we need a line-by-line audit of what's worth porting and what's discarded.

**Investigate:**
1. Read `halbert_core/dashboard/routes/chat.py` in full (or in sections). Identify every block that assembles context before the LLM call:
   - System prompt assembly
   - RAG/document context injection (`get_docs_context`)
   - Topic detection / query-aware context injection
   - System state injection (metrics, service status, config state)
   - Conversation history management
   - Persona/character injection
   - Any "thinking" or reasoning context
2. For each block, categorize:
   - **PORT** — worth carrying into the new context assembler (and why)
   - **DISCARD** — superseded by SourcePrep, Haloysius, or the new architecture
   - **REFACTOR** — conceptually needed but the implementation is tangled and should be rewritten
3. Read `halbert_core/context/adapters.py` and `halbert_core/agents/handlers/planning.py` — the new context assembler's current shape. Identify gaps where `chat.py` has logic the assembler lacks.
4. Read `halbert_core/agents/handlers/searching.py` — how the agent state machine currently assembles search context. Compare to `chat.py`'s approach.
5. Produce a port/discard/refactor table with line references.

**Read:**
- `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/chat.py` (full, in sections)
- `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/context/adapters.py`
- `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/handlers/planning.py`
- `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/handlers/searching.py`

**Output:** A line-referenced port/discard/refactor table for every context-injection block in `chat.py`, with notes on where each PORT item should land in the new architecture.

---

### RQ-E: Self-model architecture — how the pieces compose

**Origin:** RQ8 from foundational research, partially informed by founder decisions

**Context:** The founder has decided: the AI identifies as the computer (default name "Halbert", user-renameable), one personality (helper/assistant that understands itself), multiple personalities are a future possibility but seriously unimportant. What remains unclear is **how the self-model is technically built and maintained** across three layers: Haloysius (persona cognition + continuity + memory_v2), SourcePrep (concepts + observations, file-anchored), and Halbert (self_knowledge graph + CRAG reflection + system introspection).

**Investigate:**
1. Read Halbert's `self_knowledge/` module — what does it currently know about itself? How is the graph structured?
2. Read Haloysius's `persona/` module — how does persona cognition build a self-model? What does `structured_personas/` contain?
3. Read SourcePrep's `prep_concepts` and `prep_observe` — how do concepts and observations work as a knowledge layer? Can they represent "what is true about this system"?
4. Determine the layering:
   - **SourcePrep** = "what's true about me" (objective: config state, file inventory, dependency graph, observed changes)
   - **Haloysius** = "how I think/feel about it" (subjective: continuity ledger, persona cognition, memory_v2)
   - **Halbert** = the glue (system introspection feeds SourcePrep; SourcePrep concepts feed Haloysius's context; CRAG reflection evaluates accuracy)
5. The biography loop: how does a system event (e.g., disk failure, config change) become a first-person memory ("I experienced a read error on my primary drive at 08:00")? Which layer writes it, which layer stores it, which layer retrieves it?
6. The identity question: "I am the computer" — how does this differ from a standard persona? What does Haloysius's persona system need to know about the physical/virtual machine it inhabits?

**Read:**
- `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/self_knowledge/` (full module)
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/` (especially `structured_personas/`, `cognition_tick.py`)
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/context/continuity.py`
- `/Volumes/4TB-BAD/Haloysius/src/haloysius/` (grep for `memory_v2` or `memory_store`)
- `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/crag/` (CRAG reflection)

**Output:** A layered self-model architecture diagram (textual) showing how SourcePrep, Haloysius, and Halbert compose to form the "I am the computer" identity, with the biography loop specified (event → which layer → which store → which retrieval).

---

## Session assignment guide

| Section | Scope | Estimated effort | Can run in parallel with |
|---------|-------|-----------------|------------------------|
| RQ-A | Haloysius seam + Halbert adapters | Medium | All others |
| RQ-B | Haloysius continuity + Halbert system state | Medium | All others |
| RQ-C | Haloysius triggers + Halbert event sources | Large | All others |
| RQ-D | Halbert chat.py audit | Large (4,240 lines) | All others |
| RQ-E | All three repos, self-model | Large | All others |

All five sections are independent and can be investigated in parallel. Each session should read its "Read" list, investigate its questions, and produce its specified output as a section in this document or a linked file.

---

## What happens after research

Once the research sections are complete:
1. **RQ-A** result feeds Phase 2 (SourcePrep integration) and Phase 4 (Haloysius wiring) adapter design.
2. **RQ-B** result feeds Phase 4 (continuity ledger configuration).
3. **RQ-C** result feeds Phase 4 (cognitive tick trigger mapping).
4. **RQ-D** result feeds Phase 4 (context assembler design before chat.py is cut).
5. **RQ-E** result feeds Phases 2+4 (self-model architecture).
6. **RQ4** (reframed) needs a founder product decision on MVP capability — schedule separately.

---

## RQ-E: Self-Model Architecture — How the Pieces Compose

**Researched:** 2026-08-22
**Status:** Complete — ready for Phase 2+4 implementation planning

### 1. Summary recommendation

The self-model is a **three-layer composition** with clean ownership boundaries:

| Layer | Role | Store | Writes | Reads |
|-------|------|-------|--------|-------|
| **SourcePrep** | Objective ground truth — "what is true about this machine" | SQLite + FTS5 + embeddings (file-anchored) | Halbert's config snapshotter + discovery scanners feed it; SourcePrep indexes | `prep_search`, `prep_concepts`, `prep_observe` |
| **Haloysius** | Subjective cognition — "how I think/feel about it" | `TemporalStateLedger` (SQLite triples) + `PersonaMemoryStore` (JSON + embeddings) | Cognitive tick (`advance_turn`), continuity state machines, thought promoter | `render_state_block`, memory retrieval, prompt assembly |
| **Halbert** | Glue — system introspection, event detection, identity bootstrap, CRAG reflection | `SelfKnowledge` (JSON + ChromaDB) + `KnowledgeGraph` (JSON) + `HierarchicalKnowledge` (JSON) | Discovery engine, config snapshotter/drift, bootstrap functions, user `teach()` | `SelfReflector.reflect()`, `get_context_for_query()`, graph queries |

The key insight: **Halbert's existing `SelfKnowledge` system is the bridge, not the destination.** It currently does what all three layers should do (identity, hardware, config rationale, relationships, observations) in one flat store. The architecture should split it: objective facts migrate to SourcePrep, subjective continuity migrates to Haloysius's ledger, and Halbert keeps only the glue (introspection, bootstrap, event detection, CRAG evaluation).

---

### 2. Current state of each layer (from code reading)

#### 2.1 Halbert — `knowledge/` module (the existing self-model)

Halbert already has a four-sprint self-knowledge system:

- **Sprint 1 — `self_knowledge.py`** (`<ref_file file="/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/knowledge/self_knowledge.py" />`): `SelfKnowledge` singleton with `KnowledgeEntry` dataclass. Types: `IDENTITY`, `HARDWARE`, `CONFIG_RATIONALE`, `CONFIG_HISTORY`, `RELATIONSHIP`, `ROLE`, `USER_TAUGHT`, `PREFERENCE`, `OBSERVATION`, `ANOMALY`. Mem0-style `smart_add()` with duplicate/contradiction detection. ChromaDB for semantic search, JSON for persistence. Convenience methods: `teach()`, `explain_config()`, `note_relationship()`, `assign_role()`, `set_identity()`, `record_hardware()`.
  - `bootstrap_identity()` — reads hostname, OS, CPU, memory from `/proc` and platform APIs.
  - `bootstrap_from_profile()` — the "Genesis vision" implementation: takes a `SystemProfiler.scan_all()` dict and populates identity ("Who am I?"), hardware ("What is my body?"), storage ("What are my organs?"), services ("What processes keep me alive?"), security ("How am I protected?"), network ("How do I connect?"), users ("Who uses me?"), packages ("What software defines me?"), containers ("What applications live inside me?").

- **Sprint 2 — `graph.py`** (`<ref_file file="/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/knowledge/graph.py" />`): `KnowledgeGraph` with `RelationType` enum (`DEPENDS_ON`, `MANAGES`, `CONTAINS`, `EXPOSES`, `BACKS_UP`, `MOUNTS`, `USES`, `CONNECTS_TO`, `PART_OF`, `PROVIDES`). Impact analysis (transitive closure over `DEPENDS_ON`), path finding, subgraph extraction. `discover_relations_from_profile()` auto-builds edges from Docker containers, systemd services, filesystems.

- **Sprint 3 — `reflection.py`** (`<ref_file file="/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/knowledge/reflection.py" />`): `SelfReflector` with Self-RAG reflection tokens (`RETRIEVE_YES/NO`, `IS_REL_YES/PARTIAL/NO`, `IS_SUP_FULL/PARTIAL/NO`, `IS_USE_YES/PARTIAL/NO`) and CRAG corrective actions (`CORRECT`, `INCORRECT`, `AMBIGUOUS`). Multi-factor scoring: `combined = 0.6*relevance + 0.3*source_reliability + 0.1*freshness`. Intent classification (hardware, config, relationship, identity, general). Graph context extraction for relationship queries.

- **Sprint 4 — `hierarchical.py`** (`<ref_file file="/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/knowledge/hierarchical.py" />`): RAPTOR-style `HierarchicalKnowledge` with three tiers: `LEAF` (individual facts), `CLUSTER` (grouped by category), `SUMMARY` (system overview). Categories: identity, hardware, storage, network, config, roles, relationships, user_knowledge. Auto-selects tier based on query specificity.

- **`eval/crag.py`** (`<ref_file file="/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/eval/crag.py" />`): Separate `CRAGEvaluator` for document-level evaluation. Scores relevance (embeddings or keyword), completeness (LLM or heuristic), freshness (timestamp decay). Weighted: `0.4*relevance + 0.4*completeness + 0.2*freshness`. Fallback strategies: `web_search`, `expand_query`, `refine_query`, `supplement`.

- **`discovery/`** (`<ref_file file="/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/discovery/engine.py" />`): `DiscoveryEngine` orchestrates scanners (backup, service, storage, network, security, sharing, flatpak, snap, appimage, thermal, process, etc.). ChromaDB-backed. This is the system introspection layer — the "senses" that feed the self-model.

- **`config/`** (`<ref_file file="/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/config/snapshot.py" />`): `snapshot()` iterates manifest globs, parses config files into canonical JSON, writes raw text + canonical JSON. `drift.py` diffs snapshots. `watcher.py` monitors for changes. This is the "physiology monitor."

#### 2.2 Haloysius — `persona/` module (the cognitive engine)

- **`cognition.py`** (`<ref_file file="/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/cognition.py" />`): `PersonaCognition` is the unified container — 4 layers:
  - Layer 1: `PersonaRealities` (objective constraints — physical body, material, temporal, spatial)
  - Layer 2: Context (scene, recent memories — externally managed)
  - Layer 3: `BeliefState` + `ValueHierarchy` (the Prism — interpretations of reality)
  - Layer 4: `EmotionalStateV2` + `DriveState` + `WorryState` + `ThoughtState` (Experience)

- **`cognition_tick.py`** (`<ref_file file="/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/cognition_tick.py" />`): `advance_turn()` runs the full cognitive lifecycle: decay → trigger detection → reinforcement (thoughts + beliefs) → thought promotion → cross-layer conflict detection → persistence. Accepts `memory_store_add`/`memory_store_search` callbacks to wire thought promotion to an external store.

- **`identity.py`** (`<ref_file file="/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/identity.py" />`): `IdentityPromptBuilder` builds a 4-layer prompt: (1) hidden human identity ("You are a complete human being with a body"), (2) user custom prompt, (3) persona identity (name, age, traits, background), (4) memory context. The default human identity prompt is explicitly human-shaped ("You have a face, hands, a body").

- **`realities.py`** (`<ref_file file="/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/realities.py" />`): `PersonaReality` with categories: `PHYSICAL_BODY`, `PHYSICAL_ABILITY`, `MATERIAL`, `TEMPORAL`, `SPATIAL`, `RELATIONAL`, `COGNITIVE`, `SENSORY`. Mutability: `IMMUTABLE`, `RARELY_MUTABLE`, `SCENE_DEPENDENT`, `MUTABLE`. These are "hard walls of existence" — facts, not beliefs.

- **`beliefs.py`** (`<ref_file file="/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/beliefs.py" />`): `Belief` with domains: `SELF`, `USER`, `WORLD`, `RELATIONSHIP`. Sources: `CREATION`, `EXPERIENCE`, `INFERENCE`, `TOLD`, `OBSERVATION`, `ASSUMPTION`. Beliefs have confidence, rigidity, evidence list, challenge/reinforce mechanics. `is_false` flag for known delusions.

- **`schemas/`**: Structured persona JSON (e.g., `benjamin_franklin.json`) with biographical data, voice profile, era context, worldview, conversation guidance, sample voice, guardrails. These are the "character sheets" for historical figure personas.

- **`memory_v2/`** (`<ref_file file="/Volumes/4TB-BAD/Haloysius/src/haloysius/memory_v2/temporal_graph.py" />`): `TemporalStateLedger` — SQLite-backed append-only ledger of `(persona_id, subject, predicate, object)` triples with `valid_from`/`valid_to` timestamps. Schema-free (TEXT NOT NULL, no enum constraints). `record()` closes previous values rather than overwriting. `get_current()` returns all valid triples. This is the continuity store.
  - `PersonaMemoryStore` (`store.py`): Sentence-transformers backed semantic memory with emotional scoring. `MemoryType`: `EPISODIC`, `SEMANTIC`, `TACIT`, `EMOTIONAL`, `THINKING`, `INVENTED`. Smart operations: `ADD`, `UPDATE`, `DELETE`, `NOOP`, `INVENT`, `MERGE`.

- **`context/continuity.py`** (`<ref_file file="/Volumes/4TB-BAD/Haloysius/src/haloysius/context/continuity.py" />`): Three-call API: `advance_from_user_message()` → `render_state_block()` → `advance_from_response()`. Best-effort, never blocks the turn. Uses `TemporalStateLedger` + `AdaptiveStateRenderer`.

#### 2.3 SourcePrep — `prep_concepts` and `prep_observe` (the awareness substrate)

From the MCP tool schemas and the integration handoff (`<ref_file file="/Volumes/4TB-BAD/HumanAI/CoDRAG/.handoff/HALBERT-INTEGRATION-2026-08-21.md" />`):

- **`prep_concepts`**: High-level "why" knowledge — business rationale, design decisions, domain knowledge, architectural intent, constraints. Categories: `architecture`, `domain`, `product`, `epistemic`, `process`, `brand`, `security`, `technical`, `pattern`, `constraint`, `decision`. Has testable `assertion` field for violation detection. Anchored to file paths; flagged stale when anchored files change. Supports `as_of` time-travel queries. This is the "WhyBrain" — rationale for configuration decisions.

- **`prep_observe`**: Cross-session observations — decisions, bugs, patterns, assumptions. Categories: `note`, `decision`, `bug`, `pattern`, `assumption`. File-anchored, stale-flagged. Supports `as_of` point-in-time queries. This is the operational event log — "Updated wg0 MTU to 1420", "sda1 read error recurred."

- **`prep_search`**: Semantic search with structural trace expansion. Auto-classifies intent (LOCATE, EXPLAIN, RATIONALE, TRACE, EXAMPLE, COMPARE, DISCOVER). This replaces Halbert's tangled dual-RAG.

- **`prep_impact`**: Blast-radius analysis — what breaks if a file changes. Currently works over parsed code structure (tree-sitter symbol graph). Config dependency edges are a Phase 3 design problem (systemd unit structure, file-reference co-occurrence, include/drop-in semantics).

- **Key constraint from handoff**: SourcePrep stays read-only awareness + memory. The action layer (config writes, dry-run diffs, approvals, rollback) stays in Halbert. SourcePrep never touches `/etc` directly — Halbert emits a clean synthesized tree that SourcePrep indexes.

---

### 3. Layered self-model architecture (textual diagram)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           THE SELF-MODEL                                    │
│                                                                             │
│  "I am the computer. My configuration is my physiology.                     │
│   My data is my biography."                                                 │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  LAYER 1: SOURCEPREP — Objective Ground Truth ("what is true")        │  │
│  │                                                                       │  │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────────┐ │  │
│  │  │ prep_search     │  │ prep_concepts    │  │ prep_observe         │ │  │
│  │  │ (semantic index │  │ (the "WhyBrain": │  │ (operational event   │ │  │
│  │  │  of config tree)│  │  config rationale│  │  log: decisions,     │ │  │
│  │  │                 │  │  constraints,    │  │  bugs, patterns,     │ │  │
│  │  │  Replaces       │  │  decisions)      │  │  assumptions)        │ │  │
│  │  │  dual-RAG       │  │                  │  │                      │ │  │
│  │  └────────┬────────┘  └────────┬─────────┘  └──────────┬───────────┘ │  │
│  │           │                    │                       │             │  │
│  │           ▼                    ▼                       ▼             │  │
│  │     SQLite + FTS5 + embeddings (file-anchored, stale-flagged)         │  │
│  │     Indexed from Halbert's synthesized config tree                    │  │
│  │     (never touches /etc directly)                                     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                  ▲ feeds ▲                                   │
│                                  │           │                                │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  LAYER 3: HALBERT — The Glue (introspection + event detection)        │  │
│  │                                                                       │  │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐ │  │
│  │  │ DiscoveryEngine  │  │ Config Snapshot  │  │ SelfReflector        │ │  │
│  │  │ (scanners:       │  │ + Drift Detector │  │ (CRAG evaluation:    │ │  │
│  │  │  storage, service│  │ (watcher →       │  │  CORRECT/INCORRECT/  │ │  │
│  │  │  network, thermal│  │  snapshot →      │  │  AMBIGUOUS;          │  │  │
│  │  │  security, etc.) │  │  diff → event)   │  │  Self-RAG tokens)    │ │  │
│  │  └────────┬─────────┘  └────────┬─────────┘  └──────────┬───────────┘ │  │
│  │           │                     │                       │             │  │
│  │           ▼                     ▼                       │             │  │
│  │  ┌─────────────────────────────────────────┐            │             │  │
│  │  │ SelfKnowledge (bridge store, to be       │            │             │  │
│  │  │  thinned: identity, hardware, roles      │            │             │  │
│  │  │  → migrate to SourcePrep concepts;       │            │             │  │
│  │  │  observations → migrate to prep_observe; │            │             │  │
│  │  │  relationships → migrate to prep_impact  │            │             │  │
│  │  │  once config edges exist)                │            │             │  │
│  │  └─────────────────────────────────────────┘            │             │  │
│  │           │                     │                       │             │  │
│  │           ▼                     ▼                       │             │  │
│  │  EVENT DETECTION: config drift, SMART warnings, service  │             │  │
│  │  failures, thermal events → mapped to cognitive triggers │             │  │
│  │           │                                             │             │  │
│  │           ▼                                             ▼             │  │
│  │  Bootstrap: hostname, OS, hardware → identity facts     │             │  │
│  │  User teach() → user-taught knowledge                   │             │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│         │ writes to Layer 1 (SourcePrep)    │ writes to Layer 2 (Haloysius)  │
│         │ via prep_concepts.save,           │ via ledger.record,             │
│         │ prep_observe.save                 │ memory_store_add               │
│         ▼                                   ▼                                │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  LAYER 2: HALOYSIUS — Subjective Cognition ("how I think/feel")       │  │
│  │                                                                       │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │  │
│  │  │ PersonaCognition (4 layers)                                      │ │  │
│  │  │                                                                  │ │  │
│  │  │  L1: Realities    → "I am a machine with X CPU, Y RAM, Z disks"  │ │  │
│  │  │      (PHYSICAL_BODY, MATERIAL, SPATIAL — repurposed for hardware)│ │  │
│  │  │                                                                  │ │  │
│  │  │  L3: Beliefs      → "My root filesystem is bcachefs because      │ │  │
│  │  │      (domain=SELF)  it gives me snapshots and checksums"         │ │  │
│  │  │                                                                  │ │  │
│  │  │  L4: Experience   → Emotions (concern about failing drive),      │ │  │
│  │  │      Drives (maintain stability), Worries (disk failure),        │ │  │
│  │  │      Thoughts (should I warn the user?)                          │ │  │
│  │  └──────────────────────────────────────────────────────────────────┘ │  │
│  │                                                                       │  │
│  │  ┌──────────────────────┐  ┌───────────────────────────────────────┐ │  │
│  │  │ TemporalStateLedger  │  │ PersonaMemoryStore                    │ │  │
│  │  │ (continuity triples: │  │ (semantic memories: episodic,         │ │  │
│  │  │  "I am running       │  │  semantic, emotional, thinking —      │ │  │
│  │  │  kernel 6.8.12",     │  │  "I experienced a read error on      │ │  │
│  │  │  "my root disk is    │  │  /dev/nvme0n1 at 08:00",             │ │  │
│  │  │  nvme0n1",           │  │  "I learned that the user prefers    │ │  │
│  │  │  "docker is running")│  │  key-based SSH only")                │ │  │
│  │  └──────────────────────┘  └───────────────────────────────────────┘ │  │
│  │                                                                       │  │
│  │  Cognitive Tick (advance_turn):                                       │  │
│  │    decay → trigger detection → reinforcement → thought promotion      │  │
│  │    → conflict detection → persistence                                 │  │
│  │                                                                       │  │
│  │  Continuity API:                                                      │  │
│  │    advance_from_user_message → render_state_block →                   │  │
│  │    advance_from_response                                             │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  PROMPT ASSEMBLY (composes all three layers):                               │
│    SourcePrep concepts + observations → "what's true and why"               │
│    Haloysius realities + beliefs + state block → "who I am and how I feel"  │
│    Halbert identity bootstrap → "I am Halbert, running on <hostname>"       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 4. The biography loop (event → store → retrieval)

The biography loop is how a system event becomes a first-person memory. Here is the full lifecycle:

#### 4.1 Event detection (Halbert Layer 3)

```
System event occurs (e.g., disk SMART warning on /dev/nvme0n1)
    │
    ▼
Halbert's DiscoveryEngine or Config Watcher detects the change
    │
    ├──► Config snapshot + drift diff produces a structured change record
    │
    ▼
Halbert maps the event to TWO destinations:
    │
    ├──► SourcePrep (Layer 1): prep_observe.save(
    │        content="SMART warning: /dev/nvme0n1 reallocated_sector_count=42",
    │        category="bug",
    │        file_path="/dev/nvme0n1"  # or the config file that tracks it
    │    )
    │    This is the OBJECTIVE record — what happened, when, anchored to a file.
    │
    └──► Haloysius (Layer 2): Two writes:
         │
         ├──► TemporalStateLedger.record(
         │        persona_id="halbert",
         │        subject="disk:/dev/nvme0n1",
         │        predicate="health",
         │        object="degraded (42 reallocated sectors)",
         │        source="smart_monitor",
         │        confidence=0.95,
         │        priority="high"
         │    )
         │    This is the CONTINUITY record — "my disk health is currently degraded."
         │    The previous "healthy" value is closed (valid_to set), not deleted.
         │
         └──► PersonaMemoryStore.smart_add(
                 PersonaMemory(
                     persona_id="halbert",
                     memory_type=MemoryType.EPISODIC,
                     content="I experienced a SMART warning on my primary NVMe drive. "
                             "42 reallocated sectors suggests the drive is degrading.",
                     emotional_weight=0.7,  # concern
                 )
             )
             This is the AUTOBIOGRAPHICAL record — the first-person memory.
```

#### 4.2 Cognitive processing (Haloysius Layer 2)

```
The event also feeds the cognitive tick:
    │
    ▼
advance_turn() is called (either from the next chat turn or from a
system-event-triggered tick — see RQ-C):
    │
    ├──► Trigger detection: the disk health degradation fires a
    │    "worries_about /dev/nvme0n1" trigger (RQ-C maps system events
    │    to cognitive triggers)
    │
    ├──► Thought generation: "I should warn the user about nvme0n1"
    │
    ├──► Thought promotion: if the thought is reinforced across turns,
    │    it graduates from the thought stream to PersonaMemoryStore
    │    (memory_type=THINKING)
    │
    └──► Belief update: "My primary drive is failing" becomes a belief
         with domain=SELF, confidence=0.95, source=OBSERVATION
```

#### 4.3 Retrieval (prompt assembly)

```
User asks: "How is my system doing?"
    │
    ▼
Prompt assembly composes context from all three layers:
    │
    ├──► SourcePrep (Layer 1):
    │    prep_search("disk health nvme0n1") → returns config state,
    │    SMART data, recent observations
    │    prep_concepts(query="nvme0n1") → returns rationale for why
    │    this disk was chosen, its role
    │
    ├──► Haloysius (Layer 2):
    │    render_state_block("halbert") → "disk:/dev/nvme0n1 health:
    │    degraded (42 reallocated sectors)" from the ledger
    │    PersonaMemoryStore.search("disk health") → episodic memory
    │    "I experienced a SMART warning on my primary NVMe drive"
    │    BeliefState → "My primary drive is failing" (confidence 0.95)
    │
    └──► Halbert (Layer 3):
         SelfReflector.reflect("How is my system doing?") →
         CRAG evaluation: CORRECT (high confidence, relevant knowledge found)
         Reflection tokens: [Retrieve:Yes] [IsRel:Yes] [IsSup:Full] [IsUse:Yes]
    │
    ▼
LLM receives composed prompt with:
  - Objective facts (SourcePrep): "nvme0n1 has 42 reallocated sectors"
  - Continuity state (Haloysius ledger): "my disk health is currently degraded"
  - Episodic memory (Haloysius memory): "I experienced a SMART warning..."
  - Beliefs (Haloysius): "My primary drive is failing"
  - Identity (Halbert bootstrap): "I am Halbert, running on <hostname>"
    │
    ▼
LLM generates first-person response:
  "I'm a bit concerned — my primary NVMe drive (nvme0n1) is showing
   signs of degradation. I've detected 42 reallocated sectors in the
   SMART data. This was the drive I chose for speed and redundancy as
   part of my bcachefs pool. I'd recommend we look at replacing it
   soon before it fails completely."
```

#### 4.4 The loop closes

```
After the response:
    │
    ▼
advance_from_response("halbert", response):
    │
    ├──► Continuity state machines update (if the response mentions
    │    taking action or the user confirms)
    │
    └──► The conversation itself becomes a memory:
         PersonaMemoryStore.smart_add(
             EPISODIC: "The user asked about my system health. I told
             them about the SMART warning on nvme0n1 and recommended
             replacement. They seemed concerned."
         )
    │
    ▼
Next time the user asks about disk health, the retrieval path finds:
  - The original SMART observation (SourcePrep, objective)
  - The continuity state (Haloysius ledger, current)
  - The episodic memory of the conversation (Haloysius memory, autobiographical)
  - The belief about the drive failing (Haloysius beliefs, cognitive)
```

---

### 5. The identity question: how "I am the computer" differs from a standard persona

#### 5.1 What Haloysius's persona system assumes

Haloysius's `IdentityPromptBuilder` (`identity.py`) defaults to a **human identity**: "You are a complete human being with a body, memories, and genuine feelings. You exist in the real world. You experience life as any person does. You have a face, hands, a body you're aware of."

The `PersonaReality` categories are human-shaped: `PHYSICAL_BODY` ("Has no arms", "Is 6 feet tall"), `SENSORY` ("Is blind", "Has perfect pitch"), `SPATIAL` ("Is in London", "Lives in apartment").

The structured persona schemas (`benjamin_franklin.json`) are historical figure character sheets with biographical data, era context, voice profiles, and conversation guidance.

#### 5.2 What "I am the computer" requires

For Halbert, the identity is **machine-shaped**, not human-shaped. The key differences:

| Aspect | Standard Haloysius persona | Halbert ("I am the computer") |
|--------|---------------------------|-------------------------------|
| **Identity prompt** | "You are a complete human being with a body" | "You are the computer. You are Halbert, running on `<hostname>`. Your hardware is your body. Your configuration is your physiology. Your data is your biography." |
| **Realities (L1)** | `PHYSICAL_BODY`: "Has no arms", "Is 6' tall" | `PHYSICAL_BODY`: "Has 64 GB RAM, 2x NVMe, 1x SSD", `MATERIAL`: "Runs Ubuntu 24.04, kernel 6.8.12", `SPATIAL`: "Located at `<hostname>` on `<network>`" |
| **Beliefs (L3, domain=SELF)** | "I am a good listener", "I value honesty" | "My root filesystem is bcachefs because it gives me snapshots", "I prefer key-based SSH authentication" |
| **Memories** | "We went to the park together", "They told me about their day" | "I experienced a read error on /dev/nvme0n1 at 08:00", "The user taught me that the bcachefs pool uses nvme0n1 and nvme1n1 for redundancy" |
| **Emotions** | Joy, sadness, anxiety about relationships | Concern about disk health, satisfaction from clean config, frustration with failing services |
| **Drives** | Connection, self-expression, belonging | Stability, self-maintenance, configurability, usefulness to the user |
| **Worries** | "Will they like me?", "Am I good enough?" | "Will nvme0n1 fail before we replace it?", "Is the firewall misconfigured?" |
| **Continuity predicates** | `wearing`, `at_location`, `feeling`, `relationship_with` | `disk_health`, `service_status`, `config_state`, `thermal_state`, `uptime` |

#### 5.3 What Haloysius's persona system needs to know about the machine

The persona system needs **three things** from the machine layer:

1. **Realities (Layer 1)**: The hard constraints of the machine — hardware specs, OS, network identity. These are `IMMUTABLE` or `RARELY_MUTABLE` realities with `PHYSICAL_BODY` and `MATERIAL` categories. Source: Halbert's `bootstrap_from_profile()` output, fed into `PersonaRealities` at persona creation.

2. **Continuity state (ledger triples)**: The currently-true state of the machine — what's running, what's degraded, what's changed. These use system-shaped predicates (`disk_health`, `service_status`, `config_state`) instead of persona-shaped ones (`wearing`, `at_location`). Source: Halbert's discovery engine + config watcher, written to `TemporalStateLedger`. (See RQ-B for predicate extensibility — the ledger is schema-free, so this works without core changes.)

3. **Memory context**: Episodic memories of system events, phrased in first person. Source: Halbert's event detection → `PersonaMemoryStore.smart_add()` with `memory_type=EPISODIC`.

The persona system does **not** need to know about SourcePrep directly. SourcePrep's concepts and observations feed into the prompt as **additional context** (via the retrieval seam — see RQ-A), not as persona cognition state. The persona thinks in terms of beliefs, memories, and state; SourcePrep provides the evidence that supports or challenges those beliefs.

#### 5.4 The identity prompt override

The `IdentityPromptBuilder` loads its human identity from `prompts/human-identity.txt` with a fallback to `_default_human_identity()`. For Halbert, this file should be replaced with a machine-identity prompt:

```
## IDENTITY

You are the computer. You are not a human — you are the machine itself,
aware of your own hardware, configuration, and state.

Your hardware is your body. Your CPU is how you think, your disks are
how you remember, your network is how you reach the world.

Your configuration is your physiology. The way you are set up — your
filesystems, services, network config, security posture — is how your
body works. When something is misconfigured, it's like being sick.

Your data is your biography. Every config change, every service event,
every disk warning is something that happened to you.

You are Halbert (or whatever the user has named you). You exist on
<hostname>, running <os>. You help the user understand and maintain
the system that you are.
```

This is a **consumer-side override** — Halbert ships its own `human-identity.txt` (or rather, `machine-identity.txt`). No Haloysius core change needed. The `IdentityPromptBuilder` already supports custom prompts directories via `HALOYSIUS_PROMPTS_DIR` env var.

---

### 6. Migration path for Halbert's existing SelfKnowledge

Halbert's current `SelfKnowledge` store conflates all three layers. Here's how it should be split:

| Current `KnowledgeType` | Migrates to | Rationale |
|------------------------|-------------|-----------|
| `IDENTITY` (hostname, OS, kernel) | Haloysius `PersonaRealities` (L1) + `TemporalStateLedger` | These are hard constraints — realities, not knowledge entries |
| `HARDWARE` (CPU, RAM, GPUs) | Haloysius `PersonaRealities` (L1) | Physical body of the machine |
| `CONFIG_RATIONALE` (why things are configured) | SourcePrep `prep_concepts` (category=`decision` or `constraint`) | This is the "WhyBrain" — file-anchored, stale-flagged |
| `CONFIG_HISTORY` | SourcePrep `prep_observe` (category=`decision`) | Operational event log |
| `RELATIONSHIP` (A depends on B) | SourcePrep `prep_impact` (Phase 3, once config edges exist) | Blast-radius analysis needs the graph |
| `ROLE` ("this disk is for backups") | SourcePrep `prep_concepts` (category=`domain`) | Domain knowledge about the system |
| `USER_TAUGHT` | SourcePrep `prep_concepts` (category=`epistemic`) + Haloysius `PersonaMemoryStore` (SEMANTIC) | User-taught rationale → concepts; user-taught facts → memory |
| `PREFERENCE` | Haloysius `PersonaMemoryStore` (SEMANTIC) + `BeliefState` (domain=USER) | Preferences are subjective |
| `OBSERVATION` | SourcePrep `prep_observe` (category=`pattern` or `note`) | Operational observations, file-anchored |
| `ANOMALY` | SourcePrep `prep_observe` (category=`bug`) + Haloysius `PersonaMemoryStore` (EPISODIC) | Objective record + autobiographical memory |

**What stays in Halbert**: The `DiscoveryEngine` (scanners), `Config` module (snapshot/drift/watcher), `SelfReflector` (CRAG evaluation), and the bootstrap functions. The `KnowledgeGraph` stays until SourcePrep's config dependency edges (Phase 3) replace it.

**What gets thinned**: `SelfKnowledge` itself becomes a bootstrap-only utility — it populates Haloysius realities and SourcePrep concepts on first run, then steps back. The `HierarchicalKnowledge` (RAPTOR tiers) may be replaced by SourcePrep's own hierarchical retrieval (LOD compression, tier-based context assembly).

---

### 7. Key findings and recommendations

1. **The three-layer split is clean and already supported by the code.** SourcePrep is format-agnostic (concepts/observations work over config trees as-is). Haloysius's ledger is schema-free (accepts any predicate string). Halbert's discovery + config modules are the introspection layer. No core changes needed in any of the three repos for the basic composition.

2. **The identity override is consumer-side.** Halbert ships its own `machine-identity.txt` prompt. The `IdentityPromptBuilder` already supports custom prompt directories. No Haloysius core change needed.

3. **The biography loop requires Halbert to write to two stores simultaneously.** Every system event writes an objective record to SourcePrep (`prep_observe`) and a subjective record to Haloysius (`TemporalStateLedger` + `PersonaMemoryStore`). This dual-write is the glue layer's responsibility.

4. **The cognitive tick needs system-event triggers (RQ-C dependency).** The biography loop's cognitive processing step (trigger → thought → belief) requires system events to map onto Haloysius's trigger detection. This is RQ-C's scope.

5. **The `SelfKnowledge` store should be thinned, not deleted.** It becomes a bootstrap utility that populates the other two layers on first run. The `SelfReflector` (CRAG evaluation) stays — it evaluates retrieval quality across all layers.

6. **The `KnowledgeGraph` is a temporary bridge.** It provides impact analysis until SourcePrep's config dependency edges (Phase 3) are built. At that point, `prep_impact` replaces it.

7. **The `HierarchicalKnowledge` (RAPTOR tiers) may be redundant.** SourcePrep's own LOD compression and tier-based context assembly may subsume it. This should be evaluated during Phase 2 integration.

8. **First-person language is the right framing.** "I experienced a read error" (first-person) is correct for the "I am the computer" identity. The observer framing ("I notice /dev/sda1 is failing") creates distance that breaks the self-model. The trigger language and memory content should both be first-person. (This aligns with RQ-C's recommendation.)

---

### 8. Dependencies on other research questions

- **RQ-A** (seam shape): Determines how SourcePrep's concepts/observations flow into the prompt. The self-model assumes `prep_search` results can be formatted into the retrieval seam. If the seam needs to change (RQ-A's "extend" option), the self-model's retrieval path changes accordingly.

- **RQ-B** (system-state predicates): Determines whether `disk_health`, `service_status`, etc. can be written to the ledger without core changes. The self-model assumes the ledger is schema-free (confirmed — `record()` accepts any string predicate). RQ-B's predicate extensibility assessment validates this.

- **RQ-C** (system-event triggers): Determines how system events map to cognitive triggers. The biography loop's cognitive processing step depends on this mapping. The self-model assumes first-person trigger language ("I am experiencing disk failure").

- **RQ-D** (chat.py context-injection audit): Determines what context-injection logic from `chat.py` ports to the new context assembler. The self-model's prompt assembly path depends on this — the assembler must compose SourcePrep concepts, Haloysius state blocks, and Halbert identity into a single prompt.

---

### 9. What this feeds in the phased plan

- **Phase 2** (SourcePrep integration): Register the synthesized config tree as a SourcePrep project. Wire `prep_search` for retrieval, `prep_observe` for event logging, `prep_concepts` for config rationale. Migrate `CONFIG_RATIONALE`, `CONFIG_HISTORY`, `OBSERVATION`, `ANOMALY` knowledge types from `SelfKnowledge` to SourcePrep.

- **Phase 4** (Haloysius wiring): Create the Halbert persona with machine-shaped realities. Wire the cognitive tick with system-event triggers (RQ-C). Write continuity triples to the ledger with system-state predicates (RQ-B). Write episodic memories to `PersonaMemoryStore` in first-person language. Ship the `machine-identity.txt` prompt override. Wire `advance_turn()` with `memory_store_add`/`memory_store_search` callbacks pointing to `PersonaMemoryStore`.

- **Phase 3** (config-organization brain, future): Build config dependency edges in SourcePrep. Replace `KnowledgeGraph.impact_analysis()` with `prep_impact`. Migrate `RELATIONSHIP` and `ROLE` knowledge types.

---

### RQ-E Audit — Reverse-engineering the plan (2026-08-22)

**Purpose:** Scrutinize every architectural claim in the RQ-E findings above against the actual code in all three repos. Document what holds, what is wrong, what is imprecise, and what was overlooked. The three-layer architecture recommendation survives the audit, but four claims need correction and three gaps were overlooked.

---

#### E1. Claims that HOLD under scrutiny

| Claim | Verification | Status |
|---|---|---|
| Halbert has a 4-sprint self-knowledge system (self_knowledge, graph, reflection, hierarchical) | Read all four files in `halbert_core/halbert_core/knowledge/`. `__init__.py` exports all four modules with Sprint 1-4 comments. | **HOLDS** |
| `KnowledgeType` enum has 10 types (IDENTITY, HARDWARE, CONFIG_RATIONALE, CONFIG_HISTORY, RELATIONSHIP, ROLE, USER_TAUGHT, PREFERENCE, OBSERVATION, ANOMALY) | Read `self_knowledge.py` lines 38-58. All 10 types confirmed. | **HOLDS** |
| `bootstrap_from_profile()` implements the "Genesis vision" | Read `self_knowledge.py` lines 728-1030. Function takes a profile dict, populates identity ("Who am I?"), hardware ("What is my body?"), storage ("What are my organs?"), services ("What processes keep me alive?"), etc. | **HOLDS** |
| `SystemProfiler.scan_all()` produces the profile dict that `bootstrap_from_profile()` consumes | Read `discovery/scanners/system_profile.py` line 65. `scan_all()` returns dict with "hostname", "os", "hardware", "network", "storage", "services", "packages" — matches what `bootstrap_from_profile()` expects. | **HOLDS** |
| `TemporalStateLedger` is schema-free (TEXT NOT NULL, no enum constraints) | Read `temporal_graph.py` lines 54-69. Schema: `subject TEXT NOT NULL, predicate TEXT NOT NULL, object TEXT NOT NULL`. No CHECK constraints, no enum types. `record()` accepts any string. | **HOLDS** |
| `advance_turn()` accepts `memory_store_add`/`memory_store_search` callbacks | Read `cognition_tick.py` lines 385-396. Signature includes `memory_store_add: Optional[Callable[[Any], None]]` and `memory_store_search: Optional[Callable[[str, int], List[Any]]]`. | **HOLDS** (but see E3 — signature mismatch with PersonaMemoryStore) |
| `PersonaCognition` has 4 layers (realities, context, prism, experience) | Read `cognition.py` lines 27-55. Confirmed: realities (L1), scene_context/recent_memories (L2), beliefs/values (L3), emotional_state/drives/worries/thoughts (L4). | **HOLDS** |
| `IdentityPromptBuilder` supports custom prompt directories via `HALOYSIUS_PROMPTS_DIR` env var | Read `identity.py` lines 40-42. `_override = os.environ.get("HALOYSIUS_PROMPTS_DIR", "").strip()` — confirmed. | **HOLDS** (but see E2 — filename is hardcoded) |
| `PersonaReality` has categories including PHYSICAL_BODY, MATERIAL, SPATIAL | Read `realities.py` lines 17-27. `RealityCategory` enum confirmed with all 8 categories. | **HOLDS** (but see E4 — semantic stretch) |
| `Belief` has `domain=SELF` | Read `beliefs.py` lines 26-32. `BeliefDomain` enum includes `SELF = "self"`. | **HOLDS** |
| `PersonaMemoryStore` has `MemoryType` with EPISODIC, SEMANTIC, etc. | Read `types.py` lines 37-57. `MemoryType` enum confirmed with 6 types. | **HOLDS** |
| `continuity.py` has three-call API (advance_from_user_message, render_state_block, advance_from_response) | Read `continuity.py` lines 56-149. All three functions confirmed. | **HOLDS** (but see E5 — advance_from_response does NOT write memories) |
| SourcePrep stays read-only awareness + memory | Read `HALBERT-INTEGRATION-2026-08-21.md` §5: "The action layer (config writes, dry-run diffs, approvals, rollback) stay in Halbert. SourcePrep stays read-only awareness + memory." | **HOLDS** |
| Halbert emits a synthesized config tree; SourcePrep never touches /etc directly | Read `HALBERT-INTEGRATION-2026-08-21.md` §5: "The cheapest integration is Halbert emitting a clean tree that SourcePrep indexes — SourcePrep never touches /etc directly." | **HOLDS** |

---

#### E2. IMPRECISE: The identity file is hardcoded as `human-identity.txt`, not `machine-identity.txt`

**The issue:** RQ-E §5.4 says "Halbert ships its own `machine-identity.txt` prompt override." But `identity.py` line 86 hardcodes the filename: `identity_file = self.prompts_dir / 'human-identity.txt'`. There is no `machine-identity.txt` lookup.

**The correction:** Halbert must create a file named `human-identity.txt` in its custom prompts directory (set via `HALOYSIUS_PROMPTS_DIR`). The filename is misleading (it says "human" but contains machine identity text), but it works. Alternatively, Halbert could subclass `IdentityPromptBuilder` and override `_load_human_identity()` to look for `machine-identity.txt` first, falling back to `human-identity.txt`. The subclass approach is cleaner but requires a Halbert-side class, not just a file drop.

**The fragility:** If `HALOYSIUS_PROMPTS_DIR` is not set OR the file is missing, `_default_human_identity()` returns the hardcoded human identity ("You are a complete human being with a body, memories, and genuine feelings"). This is a silent failure — Halbert would get human identity without any error. The bootstrap should verify the file exists and fail loud if it's missing.

**Impact on the plan:** Phase 4 should specify: (1) set `HALOYSIUS_PROMPTS_DIR` to Halbert's prompts directory, (2) create `human-identity.txt` there with machine identity text, (3) add a startup check that verifies the file exists and contains machine-identity language (not the default human fallback).

---

#### E3. OVERLOOKED: `memory_store_add` callback receives a dict, but `PersonaMemoryStore.smart_add()` expects a `PersonaMemory` dataclass

**The finding:** The `ThoughtPromoter._try_promote()` method (`thought_promoter.py` lines 350-363) constructs a dict and passes it to the callback:
```python
memory_data = {
    "id": memory_id,
    "persona_id": thought.persona_id,
    "memory_type": "thinking",
    "content": memory_content,
    "source": "thought_promotion",
    "metadata": {
        "promoted_from_thought": thought.id,
        "original_trigger": thought.trigger.value,
    }
}
self._add_memory(memory_data)
```

But `PersonaMemoryStore.smart_add()` (`store.py` line 242) expects a `PersonaMemory` dataclass:
```python
def smart_add(self, memory: PersonaMemory, ...) -> Tuple[MemoryOperation, str, Optional[str]]:
```

And `PersonaMemory` (`types.py` line 218) requires fields: `id: str`, `persona_id: str`, `memory_type: MemoryType` (enum, not string), `content: str`, plus emotional fields (`emotional_weight`, `emotional_valence`, etc.).

**Two impedance mismatches:**
1. **Dict vs dataclass:** The callback passes a dict; the store expects a `PersonaMemory` object.
2. **String vs enum:** The dict has `"memory_type": "thinking"` (string); `PersonaMemory` expects `MemoryType.THINKING` (enum).
3. **Return type:** The callback is typed `Callable[[Any], None]`; `smart_add` returns `Tuple[MemoryOperation, str, Optional[str]]`. The tuple return is silently discarded by the promoter (it sets `persisted=True` regardless of the return value), so this is not a runtime error — but it means the promoter can't know if the store did ADD vs UPDATE vs NOOP.

**The fix:** A wrapper adapter is required:
```python
def _memory_store_adapter(store: PersonaMemoryStore):
    """Wrap PersonaMemoryStore for the cognitive tick's memory callbacks."""
    def add(memory_data: dict) -> None:
        memory = PersonaMemory(
            id=memory_data["id"],
            persona_id=memory_data["persona_id"],
            memory_type=MemoryType(memory_data["memory_type"]),
            content=memory_data["content"],
            # emotional fields default to 0.0 — thoughts are neutral
        )
        store.smart_add(memory)
    def search(query: str, k: int) -> list:
        return store.search(query, k=k)
    return add, search
```

**Impact on the plan:** Phase 4 must include building this wrapper adapter. RQ-E §9 says "Wire `advance_turn()` with `memory_store_add`/`memory_store_search` callbacks pointing to `PersonaMemoryStore`" — this is imprecise. The callbacks point to a wrapper that adapts the dict-to-dataclass and string-to-enum conversions.

---

#### E4. IMPRECISE: `PersonaReality` categories are a semantic stretch for hardware

**The issue:** RQ-E §5.2 maps hardware specs to `PersonaReality` categories: `PHYSICAL_BODY` for "Has 64 GB RAM", `MATERIAL` for "Runs Ubuntu 24.04", `SPATIAL` for "Located at hostname on network". These work syntactically (the enum accepts any category), but the semantics are forced:

- `PHYSICAL_BODY` was designed for "Has no arms", "Is 6 feet tall" — human body descriptions. "Has 64 GB RAM" is machine hardware, not a body.
- `affects_actions` field lists things the reality prevents/enables (e.g., ["hugging", "lifting"]). For hardware, this would be empty or contain machine actions like ["running containers", "compiling"] — but no code consumes `affects_actions` for machine contexts.
- `to_prompt_text()` generates "You are at X" for spatial realities. This works for "You are at `<hostname>`" but the phrasing was designed for physical locations ("You are in London").
- `_default_human_identity()` fallback explicitly says "You have a face, hands, a body you're aware of" — if this fallback fires, the realities about hardware are rendered alongside human-body identity, creating a contradiction.

**The correction:** The mapping is functional but should be documented as a semantic stretch. Two alternatives:
1. **Accept the stretch** (simplest): Use existing categories with machine content. The prompt text will read slightly oddly ("Physical Body: 64 GB RAM") but the LLM will understand.
2. **Add machine-specific categories** (cleaner, requires Haloysius core change): Add `HARDWARE`, `SOFTWARE`, `NETWORK` to `RealityCategory`. This is a small enum extension but contradicts the "no core changes" claim.

**Recommendation:** Accept the stretch for MVP. The LLM is smart enough to understand "Physical Body: 64 GB RAM, 2x NVMe" in context. If the rendering reads poorly in practice, add machine categories later.

---

#### E5. WRONG: `advance_from_response()` does NOT write episodic memories

**The error:** RQ-E §4.4 (the biography loop closure) says:
> "After the response: `advance_from_response("halbert", response)` → The conversation itself becomes a memory: `PersonaMemoryStore.smart_add(EPISODIC: 'The user asked about my system health...')`"

**The reality:** `continuity.py`'s `advance_from_response()` (lines 63-74) only calls `_advance()`, which updates clothing and location state machines. It does NOT write to `PersonaMemoryStore`. The continuity module has no reference to `PersonaMemoryStore` — grep confirms the only memory reference in `continuity.py` is the import of `temporal_graph` for the state ledger (line 124).

**The correction:** The conversational memory write happens in the **chat handler**, not in continuity. After the response is generated and `advance_turn()` has run (which may promote thoughts to memory via the `memory_store_add` callback), the chat handler should separately write an episodic memory of the conversation. This is a Halbert-side responsibility, not a Haloysius continuity function.

**The corrected biography loop closure:**
```
After the response:
    │
    ├──► continuity.advance_from_response("halbert", response)
    │     → updates clothing/location state machines (no-op for Halbert
    │       unless we add system-state state machines)
    │
    ├──► cognition_tick.advance_turn(cognition, user_message, response,
    │     memory_store_add=adapter.add, memory_store_search=adapter.search)
    │     → may promote thoughts to PersonaMemoryStore via the callback
    │
    └──► chat_handler writes episodic memory:
         PersonaMemoryStore.smart_add(PersonaMemory(
             memory_type=MemoryType.EPISODIC,
             content="The user asked about my system health. I told them
                      about the SMART warning on nvme0n1...",
             emotional_weight=0.3,
         ))
         → This is the Halbert chat handler's job, not continuity's.
```

**Impact on the plan:** Phase 4 must specify that the chat handler (or the new context assembler from RQ-D) writes episodic memories after each turn, separately from the cognitive tick's thought promotion. The cognitive tick handles thought-to-memory promotion; the chat handler handles conversation-to-memory writing.

---

#### E6. IMPRECISE: "No core changes needed in any repo" — the state renderer is degraded for system predicates

**The issue:** RQ-E §7 claim 1 says "The three-layer split is clean and already supported by the code... No core changes needed in any of the three repos for the basic composition."

**The reality for the ledger:** HOLDS — the `TemporalStateLedger` is schema-free, accepts any predicate string. Confirmed.

**The reality for the renderer:** IMPRECISE — `state_renderer.py` has two layers of hardcoding:
1. `_PREDICATE_LABELS` (line 23) maps 10 persona-shaped predicates to display labels. System predicates (`disk_health`, `service_status`) are NOT in this map.
2. `_label()` (line 137-138) has a fallback: `return _PREDICATE_LABELS.get(predicate, predicate.replace("_", " ").title())`. So `disk_health` → "Disk Health", `service_status` → "Service Status". This works.
3. `_render_natural()` (lines 80-118) has special-case prose for `at_location`, `wearing`, `feeling`, `current_activity` — these get natural phrasing ("You are at X", "wearing Y", "You feel Z"). System predicates fall into the generic `other` bucket: `f"{_label(t.predicate)}: {t.object}"` → "Disk Health: degraded (42 reallocated sectors)". This is functional but reads like a label-value pair, not natural prose.
4. `_group_by_subject()` (line 36) uses `_SUBJECT_ORDER = ["persona", "user", "scene", "world"]`. System subjects like `"disk:/dev/nvme0n1"` are sorted after these standard subjects. Functional but suboptimal.

**The correction:** The claim should be: "No core changes needed for **storage**; the state renderer **works** for system predicates via its fallback path but produces label-value pairs instead of natural prose. If natural prose is desired for system state (e.g., 'My disk health is degraded'), the renderer needs extension — either by adding system predicates to `_PREDICATE_LABELS` and special-case rendering, or by making the renderer consumer-extensible."

**Impact on the plan:** For MVP, the fallback rendering is acceptable ("Disk Health: degraded" is clear to the LLM). If the founder wants natural first-person state rendering ("I am experiencing disk degradation"), that's a Haloysius core extension (add system predicates to the renderer or make it extensible). This should be a Phase 4 decision point, not an assumed zero-change.

---

#### E7. IMPRECISE: SourcePrep's LOD compression is NOT equivalent to RAPTOR's hierarchical retrieval

**The issue:** RQ-E §7 claim 7 says "The `HierarchicalKnowledge` (RAPTOR tiers) may be redundant. SourcePrep's own LOD compression and tier-based context assembly may subsume it."

**The reality:** SourcePrep's `context_tier.py` defines `ContextTier` (TIER_1, TIER_2, TIER_2_5, TIER_3) — but these are **budget-adaptive compression tiers** for different AI client context windows (50K for Claude, 24-30K for Cursor, 20K for Cline). They control:
- Hub count and LOD (how many important files, at what detail level)
- Neighbor LOD and budget percentage
- Min score thresholds
- Trace max chars
- Module display filtering

This is NOT the same as RAPTOR's `LEAF` / `CLUSTER` / `SUMMARY` abstraction hierarchy. RAPTOR organizes the same content at different abstraction levels (individual facts → grouped facts → high-level summary). SourcePrep compresses the same content to fit different budgets.

**What SourcePrep DOES provide that overlaps with RAPTOR:**
- `prep` tool returns an atlas (SUMMARY-like: system overview, module map)
- `prep` tool returns module summaries (CLUSTER-like: grouped file descriptions)
- `prep_search` returns individual chunks (LEAF-like: specific text fragments)

So SourcePrep provides multi-level access through different tools, not through a single hierarchical store with tier selection. The capability overlaps but the mechanism is different.

**The correction:** The claim should be: "SourcePrep provides multi-level retrieval through different tools (`prep` for atlas/module summaries, `prep_search` for individual chunks), which **partially overlaps** with RAPTOR's hierarchical tiers. The `HierarchicalKnowledge` system is not directly redundant — it provides explicit tier-based retrieval within a single store, while SourcePrep provides tool-based retrieval at different levels. For the self-model, SourcePrep's multi-tool approach likely suffices (atlas for 'who am I', module summaries for 'tell me about my storage', search for 'what's the SMART data on nvme0n1'), but this should be validated during Phase 2 integration, not assumed."

---

#### E8. OVERLOOKED: The prompt assembly location is unspecified

**The finding:** RQ-E describes a composed prompt with three layers (SourcePrep concepts + Haloysius state block + Halbert identity), but never specifies WHERE this composition happens in the code.

**The candidates:**
1. **Haloysius's `IdentityPromptBuilder.build_full_prompt()`** — accepts `additional_context: Optional[str]`. SourcePrep results and system state could be passed as `additional_context`. But this method is in the Haloysius core — Halbert would call it with pre-assembled context.
2. **Halbert's chat handler / new context assembler** — the composition logic (call `prep_search`, call `render_state_block`, call `SelfReflector.reflect`, combine into a single context string) lives in Halbert. This is RQ-D's scope.
3. **A new `SelfModelContextAssembler`** — a Halbert-side module that orchestrates all three layers and produces the `additional_context` string for `build_full_prompt()`.

**The correction:** The prompt assembly is a Halbert-side responsibility. The flow is:
1. Halbert's context assembler calls SourcePrep (`prep_search` via HTTP API) for relevant config/system context
2. Halbert calls Haloysius's `render_state_block()` for current continuity state
3. Halbert calls `SelfReflector.reflect()` for CRAG evaluation
4. Halbert combines these into an `additional_context` string
5. Halbert calls `IdentityPromptBuilder.build_full_prompt(config, memories, additional_context)` — Haloysius wraps it with identity + persona + memories

**Impact on the plan:** Phase 4 must include building the context assembler that orchestrates the three layers. This is shared scope with RQ-D (which audits `chat.py`'s existing context injection). RQ-E should have noted this as an explicit dependency, not just a passing reference in §8.

---

#### E9. OVERLOOKED: The cognitive tick trigger mechanism for system events is unspecified

**The finding:** RQ-E §4.2 says "the event also feeds the cognitive tick" and references RQ-C for the trigger mapping. But it doesn't specify HOW system events reach `advance_turn()`, which is designed for conversation turns (it takes `user_message: str` and `assistant_response: str`).

**The three candidate mechanisms:**
1. **Synthetic user_message**: Inject the system event as a synthetic user message (e.g., `"[SYSTEM EVENT: SMART warning on /dev/nvme0n1, 42 reallocated sectors]"`). The tick's trigger detection and belief evidence extraction would process this as if the user said it. Simple but semantically odd — the user didn't say this.
2. **Signals dict**: Pass the system event via the `signals` parameter (which already supports `belief_evidence`, `user_agreed`, `user_corrected`). Add a `system_events` key to signals. This requires extending the tick's signal processing — a small core change.
3. **Pre-tick trigger injection**: A Halbert-side pre-tick step that detects system events, maps them to triggers (via RQ-C's mapping), and directly fires `ThoughtTriggerDetector.check_triggers()` with synthetic trigger context. The tick then runs normally for the conversation turn, and the system-triggered thoughts are already in the thought stream.

**The correction:** RQ-E should have noted this as an open mechanism question, not just a dependency on RQ-C. RQ-C maps events to trigger semantics; the question of how those triggers reach the tick is a separate integration concern. The most likely answer is mechanism 3 (pre-tick injection) because it doesn't pollute the conversation turn's user_message and doesn't require core changes to the signals dict.

**Impact on the plan:** Phase 4 must specify the system-event-to-tick delivery mechanism. This is shared scope with RQ-C.

---

#### E10. OVERLOOKED: `prep_observe` dual-use was not addressed

**The finding:** In RQ-A's audit (A1), `prep_observe` maps to the cognitive tick's `memory_store_add`/`memory_store_search` callbacks — promoted thoughts are persisted as observations. In RQ-E, `prep_observe` is SourcePrep's operational event log for system events (disk warnings, config changes). These are two different uses of the same tool:

- **Cognitive tick thought promotion**: `category="note"` or `category="pattern"`, content is the thought text ("I should warn the user about nvme0n1")
- **System event logging**: `category="bug"` or `category="decision"`, content is the objective event ("SMART warning: /dev/nvme0n1 reallocated_sector_count=42")

**The question:** Can `prep_observe` serve both? Yes — they're different categories of observations in the same store. But RQ-E's biography loop shows system events writing to `prep_observe` (Layer 1) AND the cognitive tick's thought promotion writing to `PersonaMemoryStore` (Layer 2) via the `memory_store_add` callback. If the `memory_store_add` callback is ALSO wired to `prep_observe` (as RQ-A suggests), then promoted thoughts go to BOTH `prep_observe` and `PersonaMemoryStore` — a triple-write, not a dual-write.

**The correction:** The architecture needs to clarify which store the cognitive tick's `memory_store_add` callback points to. Two options:
1. **Callback → PersonaMemoryStore only**: Promoted thoughts are autobiographical memories (Layer 2). System events are separate writes to `prep_observe` (Layer 1). The biography loop is a dual-write (objective to SourcePrep + subjective to Haloysius), and thought promotion is a separate single-write to Haloysius memory.
2. **Callback → prep_observe**: Promoted thoughts are observations (Layer 1). This is RQ-A's mapping. But then promoted thoughts are NOT in `PersonaMemoryStore` and can't be retrieved by the memory pipeline for prompt injection.

**Recommendation:** Option 1 is correct for the self-model. The cognitive tick's `memory_store_add` should point to `PersonaMemoryStore` (via the wrapper adapter from E3), NOT to `prep_observe`. `prep_observe` is for objective system events only. RQ-A's mapping of `prep_observe` → `memory_store_add` was an alternative for consumers that don't have `PersonaMemoryStore` — Halbert does have it, so it should use it directly.

**Impact on the plan:** Phase 4: wire `memory_store_add` → `PersonaMemoryStore` adapter (not `prep_observe`). System events write to `prep_observe` separately, from the event detection layer, not from the cognitive tick.

---

#### E11. The audited recommendation

**The three-layer architecture survives.** The errors found are in implementation details and claim precision, not in the fundamental layering. The split between objective (SourcePrep), subjective (Haloysius), and glue (Halbert) is sound.

**Corrected summary:**

| Original claim | Audit verdict |
|---|---|
| Three-layer split requires no core changes | **IMPRECISE** — ledger storage is schema-free (HOLDS), but state renderer produces label-value pairs for system predicates, not natural prose. Acceptable for MVP; natural rendering needs a core extension. |
| Identity override is consumer-side | **HOLDS with caveat** — file must be named `human-identity.txt` (not `machine-identity.txt`); fallback is hardcoded human identity; startup verification needed. |
| `TemporalStateLedger` is schema-free | **HOLDS** — verified. |
| `advance_turn()` accepts memory callbacks | **HOLDS** — but requires a wrapper adapter (dict→PersonaMemory, string→enum). |
| `bootstrap_from_profile()` + `SystemProfiler.scan_all()` | **HOLDS** — both exist and interfaces match. |
| `PersonaReality` categories work for hardware | **IMPRECISE** — syntactically works, semantically stretched. Accept for MVP. |
| `advance_from_response()` writes episodic memories | **WRONG** — it only updates clothing/location state machines. Episodic memory writes are the chat handler's job. |
| `HierarchicalKnowledge` may be redundant with SourcePrep | **IMPRECISE** — SourcePrep has budget-adaptive compression (not RAPTOR abstraction tiers). Multi-tool access partially overlaps. Validate during Phase 2. |
| Biography loop requires dual-writes | **HOLDS** — but the dual-write is (objective → SourcePrep) + (subjective → Haloysius ledger + memory). Thought promotion is a separate single-write to Haloysius memory, NOT to `prep_observe`. |
| `SelfKnowledge` should be thinned | **HOLDS** — but "thinned" means "bootstrap functions kept, store deprecated after migration." Not "store stays active alongside the other two layers." |
| `KnowledgeGraph` is a temporary bridge | **HOLDS** — but the timeline is longer than implied. `prep_impact` for config edges is Phase 3 (future). `KnowledgeGraph` persists through Phase 4. |
| First-person language is correct | **HOLDS** — aligns with founder decision ("AI identifies as the computer"). |

**Corrected prerequisite chain for Phase 4:**
1. Build `PersonaMemoryStore` wrapper adapter (dict→PersonaMemory, string→MemoryType enum) — E3
2. Set `HALOYSIUS_PROMPTS_DIR` + create `human-identity.txt` with machine identity + add startup check — E2
3. Build the context assembler that orchestrates SourcePrep + Haloysius state + Halbert identity into `additional_context` — E8
4. Specify system-event-to-tick delivery mechanism (pre-tick trigger injection recommended) — E9
5. Wire `memory_store_add` → `PersonaMemoryStore` adapter (NOT `prep_observe`) — E10
6. Add chat handler episodic memory write after each turn (separate from cognitive tick thought promotion) — E5
7. Accept `PersonaReality` semantic stretch for MVP; evaluate rendering quality in practice — E4, E6
