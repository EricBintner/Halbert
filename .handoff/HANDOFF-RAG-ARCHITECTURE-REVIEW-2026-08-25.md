# RAG Architecture Review Handoff

**Date:** 2026-08-25
**Author:** Devin (initial analysis), for external reviewer
**Status:** REVIEWED 2026-08-25 — Strategy confirmed (Option A: embed all, route per-query). Scope-name bug fixed in code+tests (uncommitted). CodeIndex build was NEVER started (manifest shows `empty_scope` from before the config change) — staged external build handed off in `.handoff/HANDOFF-STAGED-CODEINDEX-BUILD-2026-08-25.md`. Note: with CodeIndex empty, the endpoint falls back to KnowledgeIndex and ignores scope entirely, so scope filtering is only testable after the build. Also: `format_context(max_chars=1500)` is a dead path (no callers in Halbert) — rec #3 below is misdirected.

---

## Executive Summary

We are using SourcePrep as Halbert's RAG backend. SourcePrep was designed for code intelligence, not document RAG. The architecture can work, but the current setup has a fundamental tension: SourcePrep's CodeIndex embeds raw file content (what Halbert needs), but its design assumes a human curates which files load into context. Halbert needs automatic, query-driven retrieval. This document maps the architecture, identifies the friction points, and proposes paths forward.

---

## How SourcePrep Actually Works (Verified from Source)

SourcePrep has **four distinct retrieval layers**. They are independent and serve different purposes:

### 1. CodeIndex (Raw Content Embeddings)
- **File:** `src/prep/core/index.py` (class `CodeIndex`)
- **What it does:** Chunks files by heading/section boundaries (`chunk_markdown()` in `src/prep/core/chunking.py`), embeds each chunk with `nomic-embed-text-v1.5`, stores in `documents.json` + `embeddings.npy`
- **What it serves:** Raw file content chunks. When you search, you get actual text from the file, not a summary.
- **Scope control:** Only files matching `included_paths` in the project config get embedded. Empty `included_paths` = embed nothing. This is the "Knowledge Scope" the user checks boxes in.
- **Current state for Halbert:** `included_paths` was `[]` (embed nothing) until we added `knowledge/` today. The CodeIndex is currently being built.

### 2. KnowledgeIndex (LLM Enrichment Summaries)
- **File:** `src/prep/core/knowledge.py` (class `KnowledgeIndex`)
- **What it does:** Embeds LLM-generated summaries from `trace_augmented.jsonl` (file-level summaries), `trace_epistemic.jsonl` (deeper enrichments), and `trace_modules.jsonl` (module summaries). Does NOT embed raw file content.
- **What it serves:** 1-2 sentence summaries like "LaunchAgent that runs Adobe updater at login." Useful for "what is this file?" but not for "what does the brew install command accept?"
- **Current state for Halbert:** 96 chunks, all host config summaries. Zero knowledge file content.

### 3. Trace Graph (Structural)
- **What it does:** Parses files into AST/graph nodes (sections, symbols, imports). 85,288 nodes for knowledge files. Supports structural search (find by name, kind, relationship).
- **What it serves:** Symbol/section lookup, dependency graphs, impact analysis. Not content retrieval.

### 4. Atlas (Architectural Overview)
- **File:** `src/prep/core/atlas/generator.py` (class `CodebaseAtlas`)
- **What it does:** Generates a 1-2K char summary of the entire project: what it is, platform coverage, doc-type mix, where to look.
- **What it serves:** Orientation context. Prepended to `prep()` calls so the AI knows the project layout.
- **Current Halbert atlas:** 1,440 chars describing the corpus structure. This is good and lightweight.

### How `prep()` (no args) works
- Calls `POST /projects/{id}/context` with empty query
- Returns: atlas text + module summaries + hub files
- Does NOT load raw file content into context
- Typical size: 2-5K chars (lightweight, orientation only)

### How `prep_search("query")` works
- Calls `POST /projects/{id}/context` with query
- If CodeIndex is loaded: semantic search over raw chunks, returns top-k chunks with actual file content
- If CodeIndex is NOT loaded: falls back to KnowledgeIndex (LLM summaries only)
- Scope filtering: if `scope` parameter is set, filters results to only files matching that scope's paths
- Returns: chunks with `text` (raw content), `source_path`, `score`

---

## How Halbert Interfaces with SourcePrep (Verified from Source)

### The Retrieval Backend
- **File:** `halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py`
- Halbert does NOT use the MCP tool interface. It calls the HTTP API directly via `SourcePrepClient`.
- `SourcePrepRetrievalBackend.search()` calls `POST /projects/{id}/context` with `structured=True`
- Parses the `chunks` list from the response, extracts `text`, `source_path`, `score`
- `format_context()` renders chunks as `[Source: path]\n<content>` blocks, truncated to `max_chars` (default 1500)

### Query-to-Scope Routing
- **File:** `sourceprep_retrieval_backend.py`, function `scope_for_query()`
- Routes queries to scopes based on keywords:
  - "my sshd_config" / "this host" → `host` scope
  - "linux" / "macos" / "freebsd" mentioned → `knowledge-<platform>` scope
  - No signal → `None` (search all scopes)
- **BUG:** The routing generates scope names with hyphens (`knowledge-macos`) but the actual SourcePrep scopes use underscores (`knowledge_macos`). This means scope routing is silently failing and falling back to global.

### Current Scope Configuration
| Scope ID | Paths | Pipeline Profile |
|---|---|---|
| `global` | 1 | code |
| `host` | 1 | system_config |
| `knowledge_bsd` | 1 | prose_docs |
| `knowledge_common` | 1 | prose_docs |
| `knowledge_linux` | 1 | prose_docs |
| `knowledge_macos` | 1 | prose_docs |

---

## The Core Tension

### SourcePrep's Design Assumption
SourcePrep was designed for code engineering. The typical workflow:
1. Developer imports a codebase
2. SourcePrep builds the trace graph (structural)
3. Developer checks boxes for files they want in the Knowledge Scope (CodeIndex)
4. The AI gets structural context (atlas + modules) automatically
5. The AI gets raw content only for checked-box files via `prep_search`

The "check boxes" step is the key: SourcePrep assumes a human curates which files are worth embedding. For code, this makes sense — you don't embed `node_modules/`, you embed your `src/` directory.

### Halbert's Use Case
Halbert is a system administration assistant. It needs:
1. **Lightweight orientation** — "what's on this host?" (atlas + modules = good)
2. **Targeted deep knowledge** — "what does `sshd_config`'s `PermitRootLogin` accept?" (needs raw man page content)
3. **Automatic routing** — Halbert decides which platform scope to search based on the query, no human curation

The tension: if we embed ALL 245 markdown files (90MB) into the CodeIndex, every `prep_search` query searches all of them. That's actually fine for retrieval (semantic search will find the right chunks), but:
- The user's concern: "I don't think we should be plugging in the entire Linux scope into context if we ask one linux related question"
- This concern is addressed by scope filtering — `prep_search` with `scope="knowledge_linux"` only returns results from Linux files
- But the scope routing bug means this isn't working yet

---

## What's Actually Working

1. **Atlas:** Generated, 1,440 chars, gives good orientation. Lightweight.
2. **Trace graph:** 85,288 nodes, structural search works.
3. **Scope definitions:** Six scopes created with correct paths and pipeline profiles.
4. **Retrieval backend:** Code exists, calls the right API endpoint, parses correctly.
5. **Corpus data:** 24,643 docs cleaned, deduped, converted to 245 markdown files, copied to the right location.

## What's Broken

1. **Scope name mismatch:** Retrieval backend routes to `knowledge-macos`, scopes are named `knowledge_macos`. Scope filtering silently fails.
2. **CodeIndex was empty:** `included_paths` was `[]` until we added `knowledge/`. Build is in progress now.
3. **KnowledgeIndex only has host summaries:** 96 chunks of LLM-generated host config summaries, zero knowledge content. This is by design — KnowledgeIndex embeds summaries, not raw content.

## What's Uncertain

1. **CodeIndex build status:** We added `knowledge/` to `included_paths` and triggered a build. Need to verify it completes and embeds the 245 markdown files.
2. **Context budget:** Halbert's `format_context()` defaults to 1500 chars. That's very small for man page content. May need to increase.
3. **Scope routing effectiveness:** Even with the naming bug fixed, will keyword-based scope routing actually work well? "How do I configure SSH" doesn't mention "linux" or "macos" — it would go to the default platform scope, which might be wrong.

---

## Questions for the Reviewer

### 1. Is the CodeIndex the right retrieval mechanism for Halbert?

The CodeIndex embeds raw markdown content chunks (max 1800 chars each, split by headings). When Halbert searches, it gets actual file content back. This is what Halbert needs for "what does this command accept?" type questions.

The alternative is the KnowledgeIndex (LLM summaries), but those are 1-2 sentences per file — too shallow for command reference.

**My assessment:** Yes, CodeIndex is the right mechanism. The KnowledgeIndex is supplementary (good for "what is this file?" but not for deep content).

### 2. Should we embed all knowledge files or use scope routing?

**Option A: Embed all, route at query time.**
- Embed all 245 files into the CodeIndex
- Use scope filtering at query time to limit results to the right platform
- Pro: Simple, all content available
- Con: Every query searches the full index (but semantic search is fast — this is what vector DBs are designed for)
- Con: Scope routing needs to be accurate or results are noisy

**Option B: Embed per-scope, switch projects.**
- Create separate SourcePrep projects per platform
- Halbert routes to the right project based on query
- Pro: Strong isolation
- Con: More complex, can't search across platforms, more daemon overhead

**Option C: Embed all, no scope filtering.**
- Embed all 245 files, always search everything
- Pro: Simplest, no routing bugs
- Con: "How do I configure SSH on macOS" might return Linux SSH docs

**My assessment:** Option A is best. Scope filtering at query time is the right pattern. The scope routing bug needs fixing, and the routing heuristic needs improvement, but the architecture is sound.

### 3. Is the atlas + modules approach sufficient for lightweight context?

When Halbert gets a query, it should:
1. Get lightweight orientation (atlas + modules) — this is automatic via `prep()`
2. Search for specific content (CodeIndex) — this is via `prep_search()`
3. Format results into the prompt — this is `format_context()`

The atlas is 1,440 chars. Module summaries add maybe 2-3K more. That's ~5K chars of orientation context. Then `prep_search` returns targeted content chunks. This seems right.

**My assessment:** Yes, this is sufficient. The atlas is lightweight and gives good orientation. The deep content comes from targeted search, not from loading everything.

### 4. Should Halbert use the MCP tool interface or the HTTP API?

Currently Halbert uses the HTTP API directly (`SourcePrepClient`). The MCP tool interface (`prep_search`) drops the `chunks` list and returns formatted markdown. The HTTP API gives structured chunks that Halbert can format itself.

**My assessment:** HTTP API is correct for Halbert. Halbert needs control over formatting and context budget, which the MCP tool doesn't provide.

### 5. What about the LLM enrichment pipeline?

SourcePrep's pipeline runs LLM enrichment on all files, generating summaries that go into the KnowledgeIndex. For 245 markdown files, this requires 245 LLM calls (cloud API). The enrichment is useful for the atlas and for "what is this file?" queries, but it's not the primary retrieval mechanism for Halbert.

**My assessment:** Enrichment is nice-to-have but not critical. The CodeIndex (raw content) is the primary retrieval mechanism. If enrichment fails or is slow, Halbert still works via CodeIndex. We should not block on enrichment completion.

---

## Recommended Path Forward

1. **Fix the scope name mismatch** — change `knowledge-macos` to `knowledge_macos` in `sourceprep_retrieval_backend.py` (or rename the scopes to use hyphens)
2. **Verify the CodeIndex build completes** — check that `documents.json` and `embeddings.npy` are populated
3. **Increase `format_context` max_chars** — 1500 is too small for man page content. Suggest 4000-6000.
4. **Improve scope routing** — the keyword heuristic is fragile. Consider using the intake signals more robustly, or just default to the host's platform scope.
5. **Run a quality gate** — test retrieval with real queries ("how to configure sshd", "brew install options", "freebsd jail setup") and verify the right content comes back.
6. **Consider whether enrichment is worth the cost** — 245 LLM calls for summaries that aren't the primary retrieval mechanism. May want to skip enrichment and rely on CodeIndex + atlas.

---

## File References

- SourcePrep CodeIndex: `/Volumes/4TB-BAD/HumanAI/CoDRAG/src/prep/core/index.py`
- SourcePrep KnowledgeIndex: `/Volumes/4TB-BAD/HumanAI/CoDRAG/src/prep/core/knowledge.py`
- SourcePrep chunking: `/Volumes/4TB-BAD/HumanAI/CoDRAG/src/prep/core/chunking.py` (line 209: `chunk_markdown`)
- SourcePrep atlas: `/Volumes/4TB-BAD/HumanAI/CoDRAG/src/prep/core/atlas/generator.py`
- SourcePrep scope resolver: `/Volumes/4TB-BAD/HumanAI/CoDRAG/src/prep/core/scope_resolver.py`
- SourcePrep context endpoint: `/Volumes/4TB-BAD/HumanAI/CoDRAG/src/prep/api/routers/projects/search.py` (line 932)
- Halbert retrieval backend: `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py`
- Halbert SourcePrep client: `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/sourceprep_client.py`
- Halbert host project registration: `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/tools/register_host_project.py`
- SourcePrep project data: `/Users/ericbintner/.local/share/sourceprep/projects/735a592e-a2da-499b-a614-854a5fc461f5/`
- Halbert knowledge corpus: `/Users/ericbintner/.local/share/halbert/sourceprep/knowledge/`
