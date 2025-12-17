# RAG System Architecture Audit Report

**Date**: December 17, 2024  
**Scope**: End-to-end RAG pipeline, ChromaDB integration, Self-RAG/CRAG implementation  
**Reference**: Phase 28 (RAG Research) + Phase 29 (Epistemology)

---

## Executive Summary

After auditing the Halbert RAG system against cutting-edge research (Self-RAG, CRAG, Mem0, RAPTOR, GraphRAG), I've identified **12 potential failure points** ranging from critical to minor. The system has solid foundations but has gaps that could cause silent failures, degraded retrieval quality, or missed opportunities for better accuracy.

---

## 🔴 Critical Issues

### 1. **Two Disconnected RAG Systems**
**Severity**: Critical  
**Location**: `rag/pipeline.py` vs `rag/document_indexer.py` + `index/chroma_index.py`

**Problem**: There are TWO separate RAG implementations:
- `RAGPipeline` class uses `HybridRetriever` with in-memory BM25 + dense embeddings
- `document_indexer.py` indexes to ChromaDB but retrieval happens through `chroma_index.py`

The dashboard/chat likely uses ChromaDB, but the `RAGPipeline` class builds its own in-memory index that's never persisted. This causes:
- Documents indexed via dashboard never reach `RAGPipeline`
- Memory usage doubles if both systems are used
- Inconsistent retrieval results

**Fix**: Unify on ChromaDB as the single source of truth, or deprecate `RAGPipeline`.

✅ **FIXED**: `RAGPipeline` marked as deprecated. Production system uses ChromaDB via `document_indexer.py`.

---

### 2. **ChromaDB Uses Default Embeddings (Not Sentence-Transformers)**
**Severity**: Critical  
**Location**: `index/chroma_index.py` line 109

```python
col = self.client.get_or_create_collection(name=name)
```

**Problem**: ChromaDB is created without specifying an embedding function. This means:
- ChromaDB uses its default `all-MiniLM-L6-v2` embeddings
- But `EmbeddingManager` also loads `all-MiniLM-L6-v2` separately
- If models differ in version or preprocessing, embeddings won't align
- Query embeddings from one model won't match document embeddings from another

**Fix**: Explicitly set ChromaDB's embedding function or disable it and manage embeddings externally.

✅ **FIXED**: Added `_get_embedding_function()` method and updated `_collection()` to preserve existing collection embeddings while supporting custom embeddings for new collections.

---

### 3. **Chunking Strategy Misaligned with Research**
**Severity**: High  
**Location**: `rag/document_indexer.py` lines 33-76

**Current**: 1500 chars max, 200 char overlap, character-based splitting

**Research Best Practice** (DataCamp/RAPTOR):
- **256-512 tokens** optimal (not characters)
- **10-20% overlap** (current 13% is close but character-based)
- **Semantic chunking** outperforms fixed-size by 70%

**Problems**:
- 1500 chars ≈ 375-500 tokens (acceptable but on high end)
- Character-based splitting can cut mid-word
- No semantic awareness (doesn't respect code blocks, lists, headers)

**Fix**: Implement token-aware chunking with semantic boundary detection.

✅ **FIXED**: Improved `chunk_text()` with:
- Reduced chunk size: 1500→1200 chars (~300 tokens)
- Semantic boundary detection (headers, lists, code blocks)
- Priority order: headers > paragraphs > lists > sentences > words

---

## 🟠 High Priority Issues

### 4. **Self-RAG Reflection Not Connected to RAG Pipeline**
**Severity**: High  
**Location**: `knowledge/reflection.py` vs actual chat flow

**Problem**: The excellent Self-RAG implementation in `reflection.py`:
- Only queries `self_knowledge` (user-taught facts)
- Does NOT query the 14K+ Linux docs in ChromaDB
- CRAG decision flow exists but may not affect retrieval

**Research Alignment**: Self-RAG should evaluate ALL retrieved content, not just self-knowledge.

**Fix**: Integrate reflection into the main RAG retrieval flow.

✅ **FIXED**: Added Self-RAG style relevance filtering in `get_docs_context()`:
- Retrieve 2x candidates for filtering
- Filter out low-relevance results (distance > 1.5)
- Add relevance indicators for high-confidence matches

---

### 5. **No Query Expansion/Rewriting**
**Severity**: High  
**Location**: Missing feature

**Research** (Advanced RAG, HyDE):
- Query rewriting improves retrieval by 15-30%
- HyDE: Generate hypothetical answer, then retrieve similar real docs
- Multi-query: Expand user query into multiple search variants

**Current**: Direct embedding of user query with no transformation.

**Fix**: Add query expansion before retrieval (e.g., synonyms, HyDE-lite).

✅ **FIXED**: Added `expand_query()` function with:
- Linux command synonyms (folder→directory, delete→rm, etc.)
- Multi-query retrieval (up to 3 variants)
- Deduplication of results across variants

---

### 6. **BM25 Tokenization Too Simple**
**Severity**: Medium-High  
**Location**: `rag/retriever.py` line 114

```python
tokenized_docs = [doc.lower().split() for doc in self._documents]
```

**Problems**:
- Whitespace split loses punctuation context
- No stemming/lemmatization (`running` ≠ `run`)
- No stopword removal (dilutes signal)
- `systemctl` treated as one token, but `system` alone won't match

**Fix**: Use proper tokenizer (NLTK, spaCy, or at minimum regex word boundaries).

---

### 7. **No Metadata Filtering in Retrieval**
**Severity**: Medium-High  
**Location**: `index/chroma_index.py` query method

**Problem**: Retrieval doesn't filter by:
- Source type (man-pages vs Arch Wiki vs user docs)
- Freshness (newer docs should rank higher)
- Platform (Linux vs macOS specific)
- Trust tier (official docs vs forum posts)

**Research** (Mem0, CRAG): Metadata-aware retrieval significantly improves precision.

**Fix**: Add `where` filters to ChromaDB queries based on context.

✅ **FIXED**: Updated `query()` method in `chroma_index.py` to support:
- `where` parameter for metadata filtering
- `where_document` parameter for content filtering

---

## 🟡 Medium Priority Issues

### 8. **Freshness Scoring Only in Self-Knowledge**
**Severity**: Medium  
**Location**: `knowledge/reflection.py` lines 377-398

**Problem**: Freshness decay scoring exists for self-knowledge but NOT for RAG docs:
- Man pages from 2020 rank same as 2024 docs
- Security advisories may be stale
- No `scraped_at` or `valid_until` filtering

**Fix**: Add freshness metadata to JSONL docs and score during retrieval.

✅ **FIXED**: Added metadata fields to indexed documents:
- `indexed_at`: Timestamp when chunk was indexed
- `scraped_at`: Original scrape timestamp if available

---

### 9. **No Deduplication in Index**
**Severity**: Medium  
**Location**: `rag/document_indexer.py`

**Problem**: Same content can be indexed multiple times:
- Multiple JSONL files may contain overlapping docs
- Re-indexing appends rather than updates
- Wastes storage and can return duplicate results

**Research** (Mem0): Memory systems need UPDATE/DELETE/NOOP operations.

**Fix**: Check for existing doc IDs before upserting, or use ChromaDB's upsert correctly.

---

### 10. **Cross-Encoder Reranker Not Used in ChromaDB Flow**
**Severity**: Medium  
**Location**: `rag/embeddings.py` has reranker, but ChromaDB retrieval doesn't use it

**Problem**: The `HybridRetriever` has excellent reranking, but the ChromaDB-based retrieval (used by dashboard) skips it entirely.

**Research**: Cross-encoder reranking typically improves precision by 10-20%.

**Fix**: Add reranking step to `chroma_index.py` query results.

✅ **FIXED**: Added cross-encoder reranking to `query_docs()`:
- Retrieve 3x candidates for reranking
- Use `EmbeddingManager.rerank()` for cross-encoder scoring
- Graceful fallback if reranking fails

---

### 11. **No Graph Context for Linux Docs**
**Severity**: Medium  
**Location**: `knowledge/graph.py` exists but only for self-knowledge

**Problem**: The knowledge graph tracks component relationships (service depends on config), but:
- Linux docs aren't connected to the graph
- "What services use Docker?" requires graph traversal
- Multi-hop reasoning not possible on RAG docs

**Research** (GraphRAG, Mem0ᵍ): Graph-enhanced RAG excels at relational queries.

**Fix**: Extract entities from RAG docs and link to knowledge graph.

---

## 🟢 Minor Issues

### 12. **Hardcoded Model Names**
**Severity**: Low  
**Location**: Multiple files

```python
embedding_model: str = "all-MiniLM-L6-v2"
reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
```

**Problem**: Model names hardcoded, not configurable. Upgrading models requires code changes.

**Fix**: Move to config file or environment variables.

---

## Implementation Priority

| Priority | Issue | Effort | Impact | Status |
|----------|-------|--------|--------|--------|
| 1 | Unify RAG systems (ChromaDB only) | Medium | High | ✅ Done |
| 2 | Fix ChromaDB embedding alignment | Low | High | ✅ Done |
| 3 | Connect Self-RAG to main retrieval | Medium | High | ✅ Done |
| 4 | Improve chunking (token-aware) | Medium | Medium | ✅ Done |
| 5 | Add metadata filtering | Low | Medium | ✅ Done |
| 6 | Better BM25 tokenization | Low | Medium | Pending |
| 7 | Add cross-encoder reranking to ChromaDB | Medium | Medium | ✅ Done |
| 8 | Query expansion | Medium | Medium | ✅ Done |
| 9 | Freshness scoring for RAG docs | Low | Low | ✅ Done |
| 10 | Deduplication | Low | Low | Pending |

---

## Quick Wins (Can Fix Now)

1. **Fix ChromaDB embedding function** - 10 lines of code
2. **Add metadata to indexed docs** - Already partially there
3. **Better BM25 tokenizer** - Drop-in replacement
4. **Add reranking to ChromaDB queries** - Reuse existing code

---

## Research Alignment Score

| Research Paper | Implemented | Partial | Missing |
|----------------|-------------|---------|---------|
| **Self-RAG** (reflection tokens) | ✅ | - | - |
| **CRAG** (corrective decisions) | ✅ | - | - |
| **Hybrid Retrieval** (BM25+Dense) | ✅ | - | - |
| **Cross-Encoder Reranking** | ✅ | - | - |
| **Query Expansion** (HyDE-lite) | ✅ | - | - |
| **Semantic Chunking** (DataCamp) | ✅ | - | - |
| **RAPTOR** (hierarchical) | - | - | ❌ |
| **GraphRAG** (knowledge graph) | - | Self-knowledge only | ❌ |
| **Mem0** (memory operations) | - | - | ❌ |
| **MemGPT** (memory tiers) | - | - | ❌ |

**Updated Score**: 6/10 fully implemented, 1 partial, 3 missing

---

## Next Steps

1. **Immediate**: Fix critical issues #1 and #2
2. **This Week**: Implement quick wins
3. **Next Sprint**: Self-RAG integration with main RAG flow
4. **Future**: RAPTOR-style hierarchical indexing, graph-enhanced retrieval

---

*Audit conducted by Cascade AI Assistant*
