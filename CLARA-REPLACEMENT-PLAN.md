# CLARA Replacement Plan

**Date:** 2026-08-23
**Status:** Approved — Ready for Implementation
**Goal:** Replace Apple CLaRa-7B context compression with a 3-tier compression system ported from LinuxBrain Phase 72, plus conversation summarization and a source-aware budget cascade.

---

## 1. Why CLARA Is Being Removed

### What CLARA does
CLaRa (`model/clara_provider.py`, 498 lines) is Halbert's context compression layer. It takes a list of memory/context strings + a user query, runs them through Apple's CLaRa-7B-Instruct model (14GB FP16), and returns a generated "answer" that summarizes the memories relative to the query. It's wired into `ContextAssembler._compress_with_clara()` (assembler.py lines 570-630), triggered when assembled context exceeds 4000 tokens.

### Why it's inappropriate
| Problem | Detail |
|---------|--------|
| 14GB VRAM / FP16 only | No 4-bit quantization available. Massive footprint for a compression utility. |
| Generates an "answer", not compressed source text | Loses citations/provenance. Phase 69 research explicitly flagged this: "citations become fuzzier." |
| Apple-specific model | `apple/CLaRa-7B-Instruct` — not portable, not actively maintained. |
| Disabled by default | `enabled: bool = False` — requires 14GB VRAM or remote server. Most users never benefit. |
| LinuxBrain already decided | Phase 72 research (RESEARCH_AND_PLAN.md line 621): "CLaRa compression → Remove entirely → Replaced by LLMLingua-2 local" |

### CLARA's full footprint in Halbert (11 files)
| File | Matches | Role |
|------|---------|------|
| `halbert_core/model/clara_provider.py` | 53 | 498-line provider (local model + remote server) |
| `halbert_core/context/assembler.py` | 18 | `_compress_with_clara()` method + constructor arg |
| `halbert_core/dashboard/routes/clara.py` | 40 | 186-line API router |
| `halbert_core/dashboard/routes/settings.py` | 29 | CLARA config endpoints |
| `halbert_core/dashboard/frontend/src/components/ClaraSettings.tsx` | 35 | 415-line React settings panel |
| `halbert_core/dashboard/frontend/src/pages/Settings.tsx` | 7 | CLARA UI section |
| `halbert_core/dashboard/app.py` | 2 | Router registration |
| `halbert_core/tests/test_clara_integration.py` | 26 | Test suite |
| `config/models.yml` | 7 | `clara:` config block + tier comments |
| `.handoff/RQ-D-SCRUTINY-2026-08-22.md` | 2 | Handoff doc references |
| `.handoff/RQ-D-CHAT-AUDIT-2026-08-22.md` | 3 | Architecture audit references |

---

## 2. What We're Replacing It With

### 3-tier compression system (ported from LinuxBrain Phase 72)

LinuxBrain already went through this exact transition. They built a `compression/` package with three complementary compressors behind a factory:

**Tier 1: LinguaCompressor (neural, lazy-loaded)**
- Uses `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank` (178MB — vs CLaRa's 14GB)
- Token-pruning (not generation): removes redundant tokens while preserving original text. Citations/provenance preserved.
- CPU-only, lazy-loaded on first `compress()` call, never blocks startup
- 3 levels: light (60% keep), standard (40% keep), aggressive (25% keep)
- Falls back to noop on any error

**Tier 2: SemanticCompressor (rule-based, zero deps, always available)**
- Regex-based: filler word removal, verbose-to-concise phrase replacement, adjective trimming, clause pruning, abbreviations
- 3 levels: light, standard, aggressive
- Zero external dependencies — works everywhere
- Also provides `extract_keywords()` and `infer_category()` utilities

**Tier 3: MemoryLOD (structural, 6-level budget-aware)**
- Adapted from SourcePrep/CoDRAG's `lod_extractor.py` for prose memories
- 6 LOD levels (0-5): full content → filler removed → key facts → one-liner → keywords → ID tag
- `assign_memory_lod(relevance, epistemic)` — dynamically assigns compression level per-memory
- `compress_batch()` — budget-aware: packs more memories by compressing less-relevant ones more aggressively
- **Epistemic floor fix** (new, from gist failure pattern research): if epistemic >= 0.8, never return LOD > 2

**Factory: `create_compressor()`**
- Priority: LinguaCompressor (if `llmlingua` installed) → SemanticCompressor (always) → NoopCompressor (always)

### Conversation summarization (ported from LinuxBrain)
5-level hierarchical conversation compression:
- Level 0 (Raw): Last 10 messages — full detail
- Level 1 (Detailed): Messages 11-50 — detailed summary
- Level 2 (Compressed): Messages 51-200 — compressed summary
- Level 3 (Key Facts): Messages 201-1000 — key facts only
- Level 4 (Core): Messages 1000+ — relationship essence

### Source-aware budget cascade (new design, inspired by LinuxBrain's budget_v2.py)
The assembler's `_compress_with_cascade()` method applies different strategies per source type:
- **memories** → LOD batch compression (`compress_batch`)
- **persona/scene** → Lingua/Semantic compressor (level auto-selected by ratio)
- **conversation** → hierarchical summarization (for older messages) + raw (for recent)
- **rag/SourcePrep** → light or no compression (already compressed by SourcePrep's LOD)
- **observations** → Semantic compressor (standard level)
- **history** → truncate oldest turns

### Relationship to SourcePrep
SourcePrep handles **code/config context compression** (structural LOD for source files, AST-aware). It's already wired via `SourcePrepRetrievalBackend`. The new compression package handles **prose memory/conversation compression**. These are complementary, not overlapping. The cascade is source-aware: it skips or lightly compresses RAG results that SourcePrep already compressed.

---

## 3. Adaptations for Halbert (sysadmin context, not persona chat)

### LinguaCompressor FORCE_TOKENS
LinuxBrain preserves prose/dialogue tokens (`"`, `'`, `—`, `...`). Halbert needs sysadmin tokens:
- Add: `/`, `=`, `|`, `>`, `<`, `$`, backtick, `#` (paths, config keys, shell operators, comments)

### MemoryLOD fact indicators
LinuxBrain matches persona facts (`lives`, `born`, `from`, `named`). Halbert needs sysadmin facts:
- Add: `configured`, `enabled`, `disabled`, `installed`, `running`, `failed`, `error`, `version`, `path`

### Category inference
LinuxBrain infers persona categories (`background`, `personality`, `relationship`, `interest`, `secret`, `quirk`). Halbert needs sysadmin categories:
- `service`, `network`, `storage`, `security`, `package`, `kernel`, `hardware`, `config`

### Epistemic floor (new, from research)
In `assign_memory_lod()`: if `epistemic >= 0.8`, never return LOD > 2. This prevents the "lost along the way" failure mode identified in the ACL 2025 gist token study.

---

## 4. Implementation Strategy

### Design principles
1. **Additive-first, subtractive-last**: Build new system alongside CLARA, wire it in, test it, THEN remove CLARA
2. **4 phases, 4 commits**: Each phase is independently revertable
3. **Graceful degradation**: Lingua (if installed) → Semantic (always) → Noop (always)
4. **Same return shape**: New methods return `{'content', 'tokens', 'original_tokens', 'ratio'}` for drop-in replacement
5. **Source-aware cascade**: Different compression strategies per source type
6. **Use assembler's token counter**: All token estimates use `self.tokens.count()` for consistency

### Risk mitigations
| Risk | Mitigation |
|------|------------|
| LLMLingua model download fails (no internet) | SemanticCompressor is always available as fallback |
| Compression changes output format | New method returns same dict shape as `_compress_with_clara` |
| Async vs sync mismatch | New compressors are sync, wrapped in async method (same as CLARA) |
| Double-compression with SourcePrep | Cascade skips or lightly compresses RAG sources (already compressed) |
| Tests import CLARA | Delete `test_clara_integration.py` in Phase 4, replace with `test_compression.py` in Phase 1 |

---

## 5. Phase Details

### Phase 1: Additive — Create compression package + tests
**Risk:** Zero (nothing imports from compression/ yet)
**New files:**
| File | ~Lines | Source |
|------|--------|--------|
| `halbert_core/halbert_core/compression/compressor.py` | 90 | Port from LinuxBrain |
| `halbert_core/halbert_core/compression/semantic_compressor.py` | 203 | Port + adapt categories |
| `halbert_core/halbert_core/compression/lingua_compressor.py` | 178 | Port + adapt FORCE_TOKENS |
| `halbert_core/halbert_core/compression/memory_lod.py` | 270 | Port + adapt facts + add epistemic floor |
| `halbert_core/halbert_core/compression/factory.py` | 63 | Direct port |
| `halbert_core/halbert_core/compression/__init__.py` | 41 | Direct port |
| `halbert_core/tests/test_compression.py` | ~200 | New (LinuxBrain has none) |

**Updated files:**
| File | Change |
|------|--------|
| `halbert_core/pyproject.toml` | Add `compression = ["llmlingua>=0.2", "huggingface-hub>=0.20"]` to optional-dependencies |

**Adaptations:**
- All imports: `halley_core.compression.*` → `halbert_core.compression.*`
- FORCE_TOKENS: add sysadmin tokens (`/`, `=`, `|`, `>`, `<`, `$`, backtick, `#`)
- `_FACT_INDICATORS`: add sysadmin facts (`configured`, `enabled`, `disabled`, `installed`, `running`, `failed`, `error`, `version`, `path`)
- `infer_category()`: sysadmin categories (`service`, `network`, `storage`, `security`, `package`, `kernel`, `hardware`, `config`)
- `assign_memory_lod()`: epistemic floor — if `epistemic >= 0.8`, cap at LOD 2

**Tests to write:**
- `test_compressor`: CompressResult fields, NoopCompressor pass-through
- `test_semantic_compressor`: all 3 levels, keyword extraction, category inference (sysadmin)
- `test_lingua_compressor`: `is_available` check, compress with mock model, fallback on error
- `test_memory_lod`: all 6 LOD levels, `assign_memory_lod` thresholds, `compress_batch` budget fitting, epistemic floor
- `test_factory`: auto-detection, explicit backend selection, fallback chain

**Verification:**
- `pytest tests/test_compression.py -v` passes
- No existing tests broken (nothing imports compression/ yet)

**Commit:** `Add compression package (ported from LinuxBrain Phase 72)`

---

### Phase 2: Wiring — Add cascade to assembler + API routes + summarization module
**Risk:** Low (CLARA still works, new code is parallel)

**New files:**
| File | ~Lines | Source |
|------|--------|--------|
| `halbert_core/halbert_core/conversation/summarization.py` | ~463 | Port from LinuxBrain + adapt |
| `halbert_core/halbert_core/conversation/__init__.py` | ~10 | New |
| `halbert_core/halbert_core/dashboard/routes/compression.py` | ~120 | New (mirrors clara.py structure) |

**Updated files:**
| File | Change |
|------|--------|
| `halbert_core/halbert_core/context/assembler.py` | Add `_compress_with_cascade()` method (source-aware, uses compression package). Keep `_compress_with_clara()` as fallback. |
| `config/models.yml` | Add `compression:` block (keep `clara:` block) |
| `halbert_core/halbert_core/dashboard/app.py` | Register compression router (keep clara router) |

**`_compress_with_cascade()` design:**
```python
async def _compress_with_cascade(
    self, content: str, query: str, sources: List[Dict]
) -> Optional[Dict[str, Any]]:
    """Source-aware compression cascade.

    Applies different strategies per source type:
    - memories → LOD batch compression
    - rag/SourcePrep → light or skip (already compressed)
    - conversation → semantic compression (standard level)
    - observations → semantic compression (standard level)
    - other → semantic compression (standard level)
    """
```

**Compression config block (models.yml):**
```yaml
compression:
  enabled: true
  backend: auto  # auto | lingua | semantic | noop
  threshold: 4000
  level: standard  # light | standard | aggressive
  lod_epistemic_floor: 0.8
```

**Compression API routes:**
- `GET /api/compression/status` — active backend, model loaded, etc.
- `GET /api/compression/config` — current config
- `POST /api/compression/config` — update config
- `POST /api/compression/compress` — manual compress endpoint
- `POST /api/compression/test` — run test compression, show stats

**Verification:**
- `pytest` passes (all tests including new compression tests)
- Dashboard starts, compression API endpoints respond
- CLARA routes still work (untouched)

**Commit:** `Wire compression cascade into assembler + add compression API routes`

---

### Phase 3: Switchover — Prefer cascade over CLARA in all paths
**Risk:** Medium (one commit, revertable)

**Updated files:**
| File | Change |
|------|--------|
| `halbert_core/halbert_core/context/assembler.py` | Prefer `_compress_with_cascade` over `_compress_with_clara` in `assemble()`. Keep CLARA as fallback. |
| `halbert_core/halbert_core/dashboard/routes/settings.py` | Replace CLARA config endpoints with compression config endpoints (29 refs) |
| `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx` | Replace CLARA section with compression section (7 refs) |
| `halbert_core/halbert_core/dashboard/frontend/src/lib/tauri.ts` | Add compression API calls |

**New files:**
| File | ~Lines | Source |
|------|--------|--------|
| `halbert_core/halbert_core/dashboard/frontend/src/components/CompressionSettings.tsx` | ~200 | New (replaces ClaraSettings.tsx) |

**CompressionSettings.tsx shows:**
- Active backend (Lingua/Semantic/Noop) with status indicator
- Compression level selector (light/standard/aggressive)
- Threshold input
- Test button (calls `/api/compression/test`, shows before/after stats)
- Model download status (for Lingua)

**Verification:**
- `pytest` passes
- Dashboard Settings page loads with compression panel
- Compression status endpoint returns data
- Test compression works via API
- Chat path works (assembler uses cascade, falls back to CLARA if needed)

**Commit:** `Switchover: prefer compression cascade over CLARA in UI and settings`

---

### Phase 4: Subtractive — Remove CLARA, wire summarization, cleanup
**Risk:** Low (cascade is verified from Phase 3)

**Deleted files:**
| File | Lines |
|------|-------|
| `halbert_core/halbert_core/model/clara_provider.py` | 498 |
| `halbert_core/halbert_core/dashboard/routes/clara.py` | 186 |
| `halbert_core/halbert_core/dashboard/frontend/src/components/ClaraSettings.tsx` | 415 |
| `halbert_core/tests/test_clara_integration.py` | ~190 |

**Updated files:**
| File | Change |
|------|--------|
| `halbert_core/halbert_core/context/assembler.py` | Remove `_compress_with_clara()`, remove `clara_provider` imports, remove `_clara` constructor arg, replace `_clara_threshold` with `_compressor_threshold`. Wire `conversation/summarization.py` into `_format_conversation()`. |
| `halbert_core/halbert_core/dashboard/app.py` | Remove clara router import + registration |
| `halbert_core/halbert_core/dashboard/routes/settings.py` | Remove all CLARA references |
| `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx` | Remove CLARA references |
| `config/models.yml` | Remove `clara:` block, update tier comments |
| `.handoff/RQ-D-SCRUTINY-2026-08-22.md` | Update 2 references |
| `.handoff/RQ-D-CHAT-AUDIT-2026-08-22.md` | Update 3 references |

**Conversation summarization wiring:**
In `assembler.py` `_format_conversation()`:
- If `len(conversation) > MESSAGE_THRESHOLD` (10): use hierarchical summarization for older messages
- Keep last `KEEP_RECENT` (6) messages as raw text
- This replaces the current end-truncation approach (lines 290-326)

**Verification:**
- `grep -ri 'clara' halbert_core/` returns 0 results (except historical handoff notes)
- `pytest` passes (all tests, no CLARA imports)
- Dashboard starts, Settings page works
- Chat path works with compression cascade + conversation summarization

**Commit:** `Remove CLARA, wire conversation summarization, cleanup references`

---

## 6. Cutting-Edge Research Findings (2025-2026)

### Directly relevant, production-ready now

**LLMLingua-2** (Microsoft, ACL 2024) — Still the practical SOTA for task-agnostic prompt compression.
- Token classification (not generation) → preserves provenance
- 178MB model, CPU-only, 3-6x faster than alternatives
- 2x-5x compression with minimal quality loss
- No training needed, model-agnostic, black-box API compatible
- Repo: https://github.com/microsoft/llmlingua

**SimpleMem** (2026, PyPI `pip install simplemem`, open source) — Complete memory system.
- 3-stage pipeline: Semantic Structured Compression → Recursive Memory Consolidation → Adaptive Query-Aware Retrieval
- 30x token reduction, 26.4% F1 improvement over baselines
- MCP support (works with Claude Desktop, Cursor, etc.)
- Future candidate to replace our hand-rolled system entirely

### Architecturally relevant (not directly deployable)

**Mem0 v3** (April 2026) — Managed platform, architectural patterns worth learning:
- ADD-only extraction (memories accumulate, consolidation handles duplicates)
- Entity linking (extract, embed, link across memories)
- Multi-signal retrieval (semantic + BM25 + entity matching, parallel fusion)
- **"Dream"** background consolidation: merge, supersede, synthesize
- 92.5 on LoCoMo, 91% lower p95 latency, 90% token cost savings

**R3Mem** (ACL 2025) — Reversible compression via virtual memory tokens. SOTA for conversational agents. Requires fine-tuning.

**CoLoR** (ACL 2025) — Compression model trained for retrieval via preference optimization. 1.91x compression, 6% retrieval improvement. Requires training.

**UniGist** (NeurIPS 2025) — Sequence-level compression with gist tokens. Solves cross-chunk information loss. Requires training.

### Research insights applied in this plan

**Gist token study** (ACL 2025) — Three failure patterns:
- "Lost by the boundary" — information at chunk boundaries gets lost
- "Lost if surprise" — unexpected information gets compressed away
- "Lost along the way" — detail degrades through multiple compression levels
- **Applied:** Epistemic floor in `assign_memory_lod()` — high-confidence memories never go below LOD 2

**Prompt Compression in the Wild** (2026) — 30,000+ experiment study:
- On Apple M1 Pro: compression overhead can exceed savings for short prompts
- **Applied:** Keep the 4000-token threshold (matches CLARA's current threshold, confirmed by research)

**Contextual Compression in RAG survey** (2024) — Comprehensive taxonomy confirming LLMLingua-2 as practical leader.

---

## 7. Future Evolution (tracked, not in this plan)

| Item | When | What |
|------|------|------|
| SimpleMem integration | After compression package is stable | Could replace hand-rolled LOD + retrieval with its 3-stage pipeline. Has MCP support. |
| Mem0 "Dream" pattern | After consolidation is needed | Background consolidation: merge (newer contains older + more), supersede (newer replaces older), synthesize (groups → summary). LinuxBrain's `consolidation.py` and `rolling_summary.py` are precursors. |
| Multi-signal retrieval | After hybrid search is enhanced | Parallel semantic + BM25 + entity matching, fused. Halbert already has `memory/hybrid.py` as a starting point. |
| R3Mem / UniGist | If fine-tuning becomes feasible | Reversible compression + cross-chunk information preservation. Requires training infrastructure. |

---

## 8. Comparison: CLARA vs New System

| Criterion | CLARA | LLMLingua-2 + Semantic + LOD |
|-----------|-------|------------------------------|
| Model size | 14GB FP16 | 178MB (or 0 for rule-based) |
| Hardware | CUDA/MPS, 14GB VRAM | CPU-only, any machine |
| Output | Generated "answer" (loses citations) | Pruned original text (preserves citations) |
| Provenance | Lost | Preserved |
| Fallback | None (fails closed) | 3-tier graceful degradation |
| Query-conditioned | Yes (generates answer from query) | LOD uses relevance + epistemic scores |
| Maintained | Apple-specific, stale | Microsoft LLMLingua-2, active |
| Already proven | No | Yes — LinuxBrain Phase 72, in production |
| Code overlap with SourcePrep | None | LOD concept shared with SourcePrep's `lod_extractor.py` |
| Default state | Disabled (requires 14GB) | Enabled (SemanticCompressor always works) |
