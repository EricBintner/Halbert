# ChromaDB Retirement Refactor — Storage System Audit & Task List

**Created:** 2026-08-26
**Status:** Verified audit, ready for task assignment
**Reads with:**
- `.handoff/ROADMAP-2026-08-23.md` (Phase 2 — RAG Consolidation, partially done)
- `halbert_core/halbert_core/index/chroma_index.py` (self-documents the migration state)

---

## 1. The Question

> "I see 'Knowledge Base Storage — ChromaDB vector database powering semantic search and RAG' in Settings. Did we choose to keep this or retire it in favor of the SourcePrep RAG? And is ChromaDB the only interior storage system?"

**Answer:** ChromaDB is the *old* storage system, not the *only* one. The chat-path RAG retrieval was already switched to SourcePrep (Phase 2a of the roadmap is done). But ChromaDB is still wired into 4 other subsystems as a storage layer, the Settings UI still describes it as the RAG engine (stale copy), and there are 5 other interior storage systems that are NOT ChromaDB. The full retirement was planned in `ROADMAP-2026-08-23.md` Phase 2 but only the chat-path slice was executed.

---

## 2. Complete Interior Storage System Inventory

Halbert has **6 distinct storage systems**. ChromaDB is one of them — the oldest and the one slated for retirement.

| # | System | Technology | DB File / Location | Purpose | Status |
|---|--------|-----------|-------------------|---------|--------|
| 1 | **ChromaDB** | Chroma vector DB + all-MiniLM-L6-v2 embeddings | `~/.local/share/halbert/chromadb/` | Self-knowledge, discovery, telemetry (hwmon/journald/dbus), legacy RAG | **OLD — partially retired, 4 live collections remain** |
| 2 | **SourcePrep** | nomic-embed-text-v1.5 + FTS5 + trace graph | `~/.local/share/sourceprep/projects/{id}/` | RAG retrieval (docs + host config), rationale (concepts), ops memory (observations) | **NEW — live, the replacement for ChromaDB RAG** |
| 3 | **SQLite Conversations** | SQLite + FTS5 | `~/.halbert/conversations.db` | Conversation history with full-text search | **Built but NOT live** — dashboard uses raw JSON files instead |
| 4 | **JSON Conversations** | Raw `.json` files | `~/.local/share/halbert/conversations/{id}.json` | Dashboard conversation persistence (the actual live path) | **Live but primitive** — linear scan, no search index |
| 5 | **JSONL Memory** | Append-only JSONL files | `~/.local/share/halbert/memory/{core,runtime,shared,personas}/` | Episodic memory, per-persona isolation | **Live** — keyword search only, no vectors |
| 6 | **SQLite Stores (4 DBs)** | SQLite | `~/.halbert/{somatic_blocks.db, model_outcomes.db, findings.db, ...}` | Somatic blocks, model outcomes, findings, approvals | **Live** — well-structured, no retirement needed |

### Detail per system

### 2.1 ChromaDB (the one being retired)

**Collections still live in ChromaDB** (from `chroma_index.py` docstring, verified):

| Collection | Producer | Consumer | Migration target |
|-----------|----------|----------|-----------------|
| `self_hwmon` | obs loop (hwmon scanner) | `context/extra_adapters.py:TelemetryAdapter._search_chromadb()` | SourcePrep observations or SQLite |
| `self_journald` | journald reader | `context/extra_adapters.py:TelemetryAdapter._search_chromadb()` | SourcePrep observations or SQLite |
| `self_dbus` | dbus monitor | (no consumer found — may be write-only) | SourcePrep observations or delete |
| `discoveries` | `discovery/engine.py:DiscoveryEngine` | `dashboard/routes/discovery.py` + `context/extra_adapters.py` | SourcePrep observations or SQLite |
| `self_knowledge` | `knowledge/self_knowledge.py:SelfKnowledgeStore` | `context/adapters.py` + Settings UI | SourcePrep observations (rationale) + JSONL memory (facts) |
| `self_conversations` | (deprecated — migrated to HybridMemorySystem) | (backward compat only) | Already migrated, collection is dead |
| `self_knowledge_all` | (deprecated — migrated to SourcePrep observations) | (backward compat only) | Already migrated, collection is dead |

**Files that import/use ChromaDB (39 files total, categorized):**

**A. Core ChromaDB infrastructure (3 files):**
- `index/chroma_index.py` — the shared client + collection factory
- `storage/chromadb_manager.py` — health monitoring, orphan cleanup, storage metrics
- `storage/__init__.py` — exports

**B. Live producers/consumers (8 files):**
- `knowledge/self_knowledge.py` — `_init_chromadb()`, upsert, query, delete (self_knowledge collection)
- `discovery/engine.py` — `_init_chromadb()`, batch upsert, search (discoveries collection)
- `context/extra_adapters.py` — `_search_chromadb()` for journald/hwmon (telemetry collections)
- `context/adapters.py` — `RAGServiceAdapter` (deprecated, still initializes ChromaDB)
- `memory/hybrid.py` — `HybridMemorySystem` connects to ChromaDB as vector store
- `dashboard/routes/storage.py` — 9 ChromaDB management endpoints (metrics, orphans, cleanup, migration)
- `dashboard/routes/memory.py` — collection browser endpoints (list/query/delete ChromaDB collections)
- `dashboard/routes/rag.py` — `get_index_stats()` reads ChromaDB doc counts for stats display

**C. Dashboard/frontend (3 files):**
- `dashboard/frontend/src/pages/Settings.tsx` — renders `ChromaDBSettings` component + stale "powering semantic search and RAG" copy
- `dashboard/frontend/src/components/domain/ChromaDBSettings.tsx` — the ChromaDB management UI
- `dashboard/frontend/src/pages/Memory.tsx` — memory collection browser UI

**D. Migration tooling (2 files):**
- `tools/migrate_self_knowledge.py` — migrates self_knowledge_all → SourcePrep observations
- `tools/migrate_conversations.py` — migrates self_conversations → HybridMemorySystem

**E. Dead/legacy (rest):**
- `rag/retriever.py`, `rag/embeddings.py`, `rag/pipeline.py`, `rag/document_indexer.py`, `rag/raptor.py`, `rag/graphrag.py`, `rag/index_builder.py` — legacy RAG pipeline, deprecated in Phase 2
- `rag/scrapers/*` — corpus scrapers (not storage, but in the rag/ tree)
- `eval/golden.py` — eval tooling, reads ChromaDB for test fixtures

### 2.2 SourcePrep (the replacement)

- **Location:** `~/.local/share/sourceprep/projects/{project_id}/`
- **Files:** `embeddings.npy`, `documents.json`, `fts.sqlite3`, `trace_nodes.jsonl`, `trace_edges.jsonl`
- **Embeddings:** nomic-embed-text-v1.5 (768-dim, CoreML accelerated)
- **Live wiring:** `integrations/sourceprep_retrieval_backend.py` → `context/adapters.py:SourcePrepAdapter` → `dashboard/routes/agent.py` (the agent/chat path)
- **Project ID:** `735a592e-a2da-499b-a614-854a5fc461f5` (name: `halbert`)
- **Corpus:** 71,092 chunks (71,050 knowledge + 42 host config)
- **Status:** Fully operational as the chat-path RAG backend

### 2.3 SQLite Conversations (built, not live)

- **File:** `halbert_core/halbert_core/agents/conversation_sqlite.py`
- **DB:** `~/.halbert/conversations.db`
- **Features:** FTS5 full-text search, thread-safe, session_somatic_blocks table
- **Status:** Code exists and is tested, but the dashboard `routes/conversations.py` uses **raw JSON files** instead. The `get_conversation_store()` in `agents/conversation.py` returns the JSON `ConversationStore`, not the SQLite one. Only `agents/session_affinity.py` references `SqliteConversationStore`.

### 2.4 JSON Conversations (the actual live conversation store)

- **Location:** `~/.local/share/halbert/conversations/{id}.json`
- **Code:** `dashboard/routes/conversations.py` — raw `json.load()`/`json.dump()` per file
- **Also:** `agents/conversation.py:ConversationStore` — the class-based JSON store used by `agent.py`'s conversation list/get/delete endpoints
- **Limitation:** Linear scan over files for listing, no search index

### 2.5 JSONL Memory

- **Location:** `~/.local/share/halbert/memory/{core,runtime,shared,personas}/`
- **Code:** `memory/writer.py` (append-only JSONL), `memory/retrieval.py` (keyword search)
- **Status:** Live, used by `scheduler/autonomous_tasks.py`, `scheduler/executor.py`, `dashboard/routes/persona.py`, `context/adapters.py`
- **Limitation:** Keyword search only, no vector embeddings. The `memory/retrieval.py` docstring says "Phase 3+: Can upgrade to ChromaDB vector search" — that upgrade never happened.

### 2.6 SQLite Stores (4 separate DBs, healthy)

| DB | File | Code | Purpose |
|----|------|------|---------|
| Somatic blocks | `~/.halbert/somatic_blocks.db` | `somatic/store.py` | C1a somatic block persistence |
| Model outcomes | `~/.halbert/model_outcomes.db` | `model/outcome_store.py` | A3 model call self-tuning data |
| Findings | (via `data_subdir`) | `findings/store.py` | Phase 5 config brain findings |
| Approvals | (via `data_subdir`) | `approval/engine.py` | Approval request persistence |

These are well-structured, purpose-built SQLite stores. No retirement needed.

---

## 3. What's Already Done vs. What's Left

### Already done (Phase 2a of ROADMAP-2026-08-23.md)

- [x] SourcePrep index built (71,092 chunks, 768-dim embeddings)
- [x] `SourcePrepRetrievalBackend` wired as Haloysius `RetrievalBackend` via `app_seam.py`
- [x] `SourcePrepAdapter` wired into agent path (`agent.py:110` — `rag_service = SourcePrepAdapter()`)
- [x] `RAGServiceAdapter` (ChromaDB-backed) marked deprecated in `context/adapters.py`
- [x] `chroma_index.py` docstring updated to document the migration state
- [x] Migration scripts created (`migrate_self_knowledge.py`, `migrate_conversations.py`)
- [x] `self_knowledge_all` and `self_conversations` collections migrated (kept for backward compat only)

### Not done (the remaining Phase 2b-2e + cleanup)

This is the task list.

---

## 4. Task List: ChromaDB Full Retirement

### Track A: Migrate live ChromaDB consumers off ChromaDB

**A1. Migrate `self_knowledge` collection → SourcePrep observations + JSONL memory**
- **Files:** `knowledge/self_knowledge.py`
- **Current:** Uses ChromaDB for semantic search over self-knowledge entries + JSON for full data
- **Target:** Semantic search via SourcePrep observations API (`prep_observe`); full data stays in JSON (already there); delete ChromaDB upsert/query/delete code
- **Migration:** Run `tools/migrate_self_knowledge.py --apply` (already exists)
- **Effort:** Medium (~200 lines changed)
- **Risk:** Self-knowledge search quality may differ (SourcePrep observations vs ChromaDB collection)

**A2. Migrate `discoveries` collection → SQLite**
- **Files:** `discovery/engine.py`, `dashboard/routes/discovery.py`, `context/extra_adapters.py`
- **Current:** `DiscoveryEngine` optionally stores discoveries in ChromaDB (`use_chromadb=True`), searches via ChromaDB semantic search
- **Target:** New `discovery/store.py` SQLite store (pattern: copy `findings/store.py` or `somatic/store.py`); semantic search is overkill for discoveries — FTS5 is sufficient
- **Migration:** Export ChromaDB discoveries → JSON → import to SQLite
- **Effort:** Medium (~300 lines new + ~100 lines changed)
- **Risk:** Low — discoveries are structured data, FTS5 search is adequate

**A3. Migrate `self_hwmon` + `self_journald` + `self_dbus` → SQLite or SourcePrep observations**
- **Files:** `context/extra_adapters.py`, `ingestion/service.py`, `ingestion/journald.py`, `ingestion/hwmon_runner.py`, `obs/audit.py`
- **Current:** Telemetry scanners write to ChromaDB; `TelemetryAdapter._search_chromadb()` reads from it for error/thermal queries
- **Target options:**
  - (a) SQLite telemetry store with FTS5 (simple, local, fast for time-range queries)
  - (b) SourcePrep observations (semantic, but overkill for log search)
  - **Recommendation:** (a) SQLite — telemetry is time-series log data, FTS5 + time indexing is the right tool
- **Migration:** Export ChromaDB telemetry → SQLite
- **Effort:** Medium-large (~400 lines new store + rewire 5 files)
- **Risk:** Medium — telemetry search is used in the live agent context path

**A4. Migrate `HybridMemorySystem` off ChromaDB**
- **Files:** `memory/hybrid.py`
- **Current:** `HybridMemorySystem.__init__` connects to ChromaDB via `get_index()` as `self.vectors`
- **Target:** Either remove `HybridMemorySystem` entirely (if unused) or rewire to SourcePrep observations
- **Check first:** Is `HybridMemorySystem` actually instantiated anywhere? Grep shows references in `memory/__init__.py` and `memory/hybrid.py` itself, but need to verify live callers.
- **Effort:** Small if removed, medium if rewired
- **Risk:** Low — likely dead code or test-only

### Track B: Remove dead ChromaDB code

**B1. Delete legacy RAG pipeline modules**
- **Files:** `rag/retriever.py`, `rag/embeddings.py`, `rag/pipeline.py`, `rag/document_indexer.py`, `rag/raptor.py`, `rag/graphrag.py`, `rag/index_builder.py`
- **Condition:** After A1-A4 complete and no live code imports them
- **Keep:** `rag/jsonl_to_markdown.py` (used for SourcePrep ingestion), `rag/scrapers/*` (corpus builders), `rag/freshness.py`, `rag/evaluation.py` (if still used)
- **Effort:** Small (delete files + fix imports)
- **Risk:** Low — verify no live imports first

**B2. Delete `index/chroma_index.py` and `storage/chromadb_manager.py`**
- **Condition:** After A1-A4 complete (no live collections remain)
- **Files:** `index/chroma_index.py`, `storage/chromadb_manager.py`, `storage/__init__.py`
- **Effort:** Small (delete + fix imports)
- **Risk:** Low — verify no imports remain

**B3. Delete `context/adapters.py:RAGServiceAdapter`**
- **Condition:** After A1-A4 (already deprecated, just remove)
- **Effort:** Trivial
- **Risk:** Low

**B4. Delete ChromaDB dashboard routes**
- **Files:** `dashboard/routes/storage.py` (9 ChromaDB endpoints), `dashboard/routes/memory.py` (collection browser — partially ChromaDB)
- **Condition:** After A1-A4 (no ChromaDB to manage)
- **Note:** `memory.py` has non-ChromaDB endpoints too (stats, search) — only remove the ChromaDB collection browser endpoints
- **Effort:** Small-medium
- **Risk:** Low — frontend components need updating too

### Track C: Update dashboard frontend

**C1. Fix stale Settings UI copy**
- **File:** `dashboard/frontend/src/pages/Settings.tsx` (line 1272-1278)
- **Current:** "Knowledge Tab - ChromaDB + Self-Knowledge + RAG" + `ChromaDBSettings` component as centerpiece
- **Target:** Rename to "Knowledge & Memory" tab; replace `ChromaDBSettings` with a SourcePrep status card + memory stats card
- **Effort:** Small
- **Risk:** Low

**C2. Replace or remove `ChromaDBSettings.tsx` component**
- **File:** `dashboard/frontend/src/components/domain/ChromaDBSettings.tsx`
- **Target:** Either delete (if no ChromaDB to show) or replace with `SourcePrepStatusCard` showing index health, chunk count, scope info
- **Effort:** Medium (~200 lines new component)
- **Risk:** Low

**C3. Update `Memory.tsx` collection browser**
- **File:** `dashboard/frontend/src/pages/Memory.tsx`
- **Current:** Browses ChromaDB collections
- **Target:** Browse JSONL memory files + SourcePrep observations (or just remove the collection browser if it's not useful post-migration)
- **Effort:** Medium
- **Risk:** Low

**C4. Remove ChromaDB from `domain/index.ts` exports**
- **File:** `dashboard/frontend/src/components/domain/index.ts`
- **Effort:** Trivial

### Track D: Clean up dependencies

**D1. Remove `chromadb` from `pyproject.toml` and `requirements-rag.txt`**
- **Condition:** After all tracks complete
- **Effort:** Trivial
- **Risk:** Low — but verify no other package depends on it transitively

**D2. Remove `chromadb` from health checks**
- **File:** `utils/health.py` (13 ChromaDB references in health check logic)
- **Target:** Replace ChromaDB health check with SourcePrep health check (already has `/health` endpoint)
- **Effort:** Small
- **Risk:** Low

**D3. Update `dashboard/routes/settings.py` ChromaDB references**
- **File:** `dashboard/routes/settings.py` (7 ChromaDB references at lines 1207, 1221, 1234, 1251, 1355, 2206, 2210)
- **Target:** Remove ChromaDB status endpoints, add SourcePrep status endpoints
- **Effort:** Small
- **Risk:** Low

### Track E: Consolidate conversation storage (opportunistic)

**E1. Switch dashboard conversations from JSON files to SQLite store**
- **Files:** `dashboard/routes/conversations.py` (currently raw JSON), `agents/conversation.py` (ConversationStore class)
- **Target:** Use `SqliteConversationStore` (already built, has FTS5 search)
- **Why now:** While we're cleaning up storage systems, switch the conversation store from primitive JSON files to the already-built SQLite store
- **Effort:** Medium (~150 lines changed in conversations.py)
- **Risk:** Low-medium — need migration script for existing JSON conversations (already exists: `migrate_json_conversations_to_sqlite`)

**E2. Unify the two conversation code paths**
- **Current:** `dashboard/routes/conversations.py` uses raw JSON; `dashboard/routes/agent.py` uses `get_conversation_store()` (also JSON `ConversationStore`)
- **Target:** Both use `SqliteConversationStore` via `get_conversation_store()`
- **Effort:** Small (after E1)
- **Risk:** Low

---

## 5. Dependency Graph

```
Track A (migrate consumers)          Track B (delete dead code)
  A1 (self_knowledge)                  ↓ depends on A1-A4
  A2 (discoveries)                   B1 (delete rag/ modules)
  A3 (telemetry)                     B2 (delete chroma_index + manager)
  A4 (hybrid memory)                 B3 (delete RAGServiceAdapter)
    ↓ all complete                    B4 (delete ChromaDB routes)
    ↓                                    ↓ depends on B1-B4
Track C (frontend)                  Track D (dependencies)
  C1 (fix Settings copy)             D1 (remove chromadb dep)
  C2 (replace ChromaDBSettings)      D2 (health checks)
  C3 (update Memory.tsx)             D3 (settings routes)
  C4 (domain exports)
                                      ↓ all complete
Track E (conversations)            Final: ChromaDB fully removed
  E1 (JSON → SQLite) — can run in parallel
  E2 (unify paths)
```

**Parallelizable:** A1, A2, A3, A4 can run in parallel (different collections, different files). E1-E2 can run anytime. C1 can run immediately (just text fix).

**Critical path:** A1-A4 → B1-B4 → D1 → ChromaDB removed.

---

## 6. What NOT to Touch

- **SourcePrep** — the new RAG backend, fully operational
- **SQLite stores** (somatic, outcomes, findings, approvals) — well-structured, no changes needed
- **JSONL memory** — live and working; the keyword search limitation is acceptable for now (vector upgrade is a separate future task)
- **`rag/scrapers/*`** — corpus builders, not storage
- **`rag/jsonl_to_markdown.py`** — used for SourcePrep ingestion
- **`rag/freshness.py`** — data freshness tracking, not ChromaDB-dependent

---

## 7. Estimated Scope

| Track | Tasks | Effort | Risk |
|-------|-------|--------|------|
| A: Migrate consumers | 4 | ~1200 lines | Medium (telemetry is live path) |
| B: Delete dead code | 4 | ~800 lines deleted | Low |
| C: Frontend updates | 4 | ~400 lines | Low |
| D: Dependency cleanup | 3 | ~100 lines | Low |
| E: Conversation consolidation | 2 | ~200 lines | Low-medium |
| **Total** | **17 tasks** | **~1700 lines new + ~800 deleted** | |

---

## 8. Verification

After all tracks complete:

1. `grep -r "chromadb\|ChromaDB\|chroma_index\|chroma_collection" halbert_core/` returns 0 results (excluding migration scripts kept for historical reference)
2. `pip show chromadb` — package not installed
3. `~/.local/share/halbert/chromadb/` directory does not exist (or is empty)
4. Agent path still retrieves context correctly (SourcePrep still works)
5. Self-knowledge search still works (via SourcePrep observations)
6. Discovery search still works (via SQLite FTS5)
7. Telemetry search still works (via SQLite FTS5)
8. All tests pass
9. Settings UI shows SourcePrep status, not ChromaDB
10. No `import chromadb` statements in the codebase
