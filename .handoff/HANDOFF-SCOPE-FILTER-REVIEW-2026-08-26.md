# Handoff: SourcePrep Scope Filtering & Retrieval Quality Review

**Date:** 2026-08-26
**Status:** REVIEWED 2026-08-26 — build is healthy, but both issues are misdiagnosed and a third, larger defect was missed (structured `/context` replaces retrieved chunks with file heads). See **Review** below before acting on the options.
**For:** External reviewer — decide fix approach for scope filtering and retrieval quality
**Prior work:** `.handoff/HANDOFF-RAG-ARCHITECTURE-REVIEW-2026-08-25.md` (reviewed), `.handoff/HANDOFF-STAGED-CODEINDEX-BUILD-2026-08-25.md` (executed)

---

## Review (2026-08-26)

Everything below was reproduced against the live daemon (Python 3.11, project `735a592e`) and the on-disk index; line refs are to CoDRAG `2691fc91`.

### Verdict

The CodeIndex build is real and healthy: 71,050 chunks, 245 files, chunk sizes p50 1,201 / p95 2,089 chars (3 outliers > 4k). But:

1. **Issue 2 is not a retrieval-quality problem.** Retrieval found the right chunks; the structured `/context` rendering threw them away.
2. **Issue 1's example is the wrong example.** The host scope is *empty in the index*, so s01/s02 ran unscoped. The boost-vs-filter defect is real, but the gate never exercised it — my cross-platform probes leak 4/4.
3. **Halbert is currently receiving one anonymous 12k-char file-head blob per query.** This is the finding that matters most and the doc did not see it.

### F1 — Structured `/context` substitutes file heads for chunks (root cause of Issue 2 and of "1 chunk per response")

- `_apply_lod_compression` (`search.py:310`) — docstring: *"Each chunk's content is replaced by its file's LOD-extracted skeleton."* Score ≥ 0.50 → LOD 0 → `abs_path.read_text()` of the **whole file** (`lod_extractor.py:553,621`). The knowledge files are up to 500 KB scraped docs, so the first file's head fills `max_chars` and every other chunk is dropped. Observed on every one of the 40 gate queries: `chunks=1`, `truncated: True`, `compression.input_chars 4815 → output_chars 12003` (a "compression" that inflates 2.5×). Raising `k` to 20 and `max_chars` to 40,000 still returns exactly 1 chunk.
- **s19:** the endpoint's own `query_coverage` reports `systemctl/service/enable` 3/3 matched in the retrieved chunks — then the emitted context is the LVM Debian-wiki navigation header of `vendor_docs_01.md`. **q16:** the retrieved chunk (`macos_support_01.md` § tar, 1,098 chars) contains "extract" and "archive"; the emitted context does not.
- Both structured branches (trace and non-trace) LOD-compress. `structured=False` does not: the same s19 query returns 8 real chunk blocks (`vendor_docs_01`, `arch_wiki_31`, `systemd_docs_01`, `tldr_04`, …).
- **Halbert impact:** structured chunks carry no `text` key (only `source_path, section, score, lod, compression_ratio, truncated`). `_parse_context_response` requires `text`, drops every chunk, and falls through to the ambient branch → a single result `{"text": <12k file head>, "source_path": "", "score": 0.0}`. That is what `ContextAssembler` gets today.
- Therefore `k`, `min_score`, BM25/hybrid and query expansion are answers to a problem that does not exist. (SourcePrep is not dense-only anyway — `_fts_boosts` / `_keyword_boosts` are applied in `CodeIndex.search`.)

### F2 — The host scope has zero indexed files

- `documents.json`: `knowledge/macos` 38,359 · `knowledge/linux` 25,046 · `knowledge/common` 4,150 · `knowledge/bsd` 3,495 = 71,050. **`host/`: 0.** `files_total: 245` = the `.md` count; the 40 host files (37 `.plist`, `hosts`, `sshd_config`, 1 `.conf`) never entered the build.
- Cause: `include_globs: ["host/**", ...]`. On Python 3.11 (the daemon's interpreter) `pathlib` `**` matches **directories only** — verified with that interpreter: `host/**` → 7 dirs, 0 files; `host/**/*` → 40 files. (Python 3.13 changed this, which is why the glob looked right.) Set in `halbert_core/halbert_core/integrations/sourceprep_template.yml:22` and `scripts/staged_knowledge_embed.py:83`.
- Knock-on SourcePrep bug: with `_expanded_mask` empty the endpoint skips scope application (`if _expanded_mask:`) yet still returns top-level `applied_scope: "host"` (the `atlas` block lacks `applied_scope`/`agent_scope_files`, which is the tell). An empty scope should produce a `scope_warning`, not a silent global search. `/search` with `scope=host` returns `[]` for the same reason.

### F3 — Boost-not-filter is real, leaks 100%, and the gate cannot see it

- The 15 platform "isolation" passes and s19/s20 use in-platform queries whose *unscoped* top-10 is already single-platform (verified for "systemctl service enable": all 10 are `knowledge/linux`). They pass regardless of scope handling.
- Cross-platform probes on `/context` (k=10): `"homebrew brew install cask"` scope=`knowledge_linux` → `homebrew_18.md`; `"diskutil apfs resize container"` scope=`knowledge_linux` → `macos_support_01.md`; `"pacman install package arch"` scope=`knowledge_macos` → `arch_wiki_13.md`; `"systemctl service enable"` scope=`knowledge_macos` → `vendor_docs_01.md`. 4/4 leak, structured and non-structured alike. `/search` (hard filter) correctly returns `[]`.
- Out-of-scope winners carry scores > 1.0 (1.104, 1.024): atlas-routing, knowledge-routing, path/keyword/FTS boosts outweigh the 0.25 scope boost. Tuning the boost cannot deliver isolation.

### F4 — Corrections to the doc

- `sourceprep_retrieval_backend.py` scope fix is **committed** (`e479c61`). Only `scripts/corpus_quality_gate.py` is dirty.
- The gate matches terms against `context + source_paths`, so path strings satisfy terms (`systemd-docs` → "systemd", `homebrew_18` → "brew", `freebsd-handbook`, `macports-guide`, `git-docs`, `docker-docs`, `nvidia-docs`, `tldr`). Several "passes" are path matches. With 1-chunk file-head responses, 95% / 85% overstate quality substantially.
- Unscoped gate omits `trace_expand`; scoped gate sends `trace_expand: True`. Inconsistent (moot while both hit LOD, but fix it).
- `atlas.segments` ids are hyphenated (`knowledge-linux`) while scopes are underscored (`knowledge_linux`). Cosmetic, but the same trap that produced `e479c61` — don't "align" the scope ids.

### Answers

1. **Scope filtering → Option B, and it is smaller than described.** `CodeIndex.search` already sets `sims[i] = -inf` for `exclude_paths` *before* any boosting or ranking (`index.py:1199`) — a true pre-filter, so there is no over-fetch waste. Implement: in the context endpoint, when `scope_mode="hard"`, compute `_indexed_paths_for_scope - _expanded_mask` and forward it as `exclude_paths` to `get_context` / `get_context_structured` / `get_context_with_trace_expansion` (none of which receive `exclude_paths` today, even though `ContextRequest` declares the field). Empty scope in hard mode → zero chunks + `scope_warning`, never global fallback. Halbert sends `hard` for every `host`/`knowledge_*` scope. Option A is not possible today (Halbert doesn't know the scope's paths and `exclude_paths` isn't forwarded). Option C's "loses LOD compression" con is inverted — LOD is what's hurting us — but its 200-char `preview` rules it out anyway. **Ordering:** F1 first; a hard-filtered result that is then replaced by a file head is still garbage.
2. **Retrieval quality → not a tuning problem.** Fix F1, re-run; expect q16 and s19 to pass. Revisit hybrid only once the gate measures real chunk text.
3. **Commit strategy → commit `corpus_quality_gate.py` now**, after the hardening in step 4 below. It is independent of the SourcePrep changes; don't bundle.
4. **Context budget → unanswerable until F1.** Today 12,000 chars = one file head. After F1, 12k chars ≈ 8–10 chunks at p50; the binding constraint becomes Halbert's backend default `k=3`, not `max_chars`. Decide with real numbers then.

### Recommended order

1. **SourcePrep (F1):** in `_apply_lod_compression`, keep the chunk's own text for doc-role / non-code files instead of `extractor.extract`, and emit `text` on every entry in `new_chunks` (Halbert needs it regardless of LOD). ~30 lines + a test that a `.md` chunk survives structured mode verbatim.
2. **Halbert (F2):** `host/**` → `host/**/*` in `sourceprep_template.yml` and `staged_knowledge_embed.py`; PUT the project config; rerun stage 1 (incremental: 40 files embed, 71,050 chunks reuse). Verify `host/` > 0 in `documents.json`. The plists are XML — confirm the chunker handles them (`files_code: 0`, they will classify as `other`).
3. **SourcePrep (F3):** `scope_mode: "hard"` pre-filter via `exclude_paths` + `scope_warning` on empty scope. **Halbert:** backend sends `scope_mode="hard"`.
4. **Gate hardening:** match terms against chunk `text` only; require ≥ 2 chunks; add the four cross-platform negative probes above (pass = empty or all in-scope); make `trace_expand` consistent; build `top_sources` from chunks. Then commit.
5. Re-run both gates; answer Q4 with the real distribution.

---

## What was accomplished this session

The full CodeIndex build is complete and verified:

| Metric | Value |
|---|---|
| Files embedded | 245 |
| Total chunks | 71,050 |
| Embedding dim | 768 (nomic-embed-text-v1.5, CoreML) |
| Lines indexed | 2,749,970 |
| Index source | `code_index` (was `knowledge` fallback) |
| Build method | Staged external (`scripts/staged_knowledge_embed.py`) |
| Total build time | ~20 hours across 3 stages + smoke test |

**Acceptance tests: 4/4 PASSED**
- Unscoped query returns raw corpus content (not LLM summaries)
- `scope="knowledge_linux"` returns only `knowledge/linux/` paths
- `scope="knowledge_macos"` returns only `knowledge/macos/` paths
- Legacy hyphenated scope (`knowledge-linux`) correctly rejected with `scope_warning`

**Unscoped quality gate: 19/20 (95%) PASSED**
- 19 queries matched expected terms in returned content
- 1 failure: `q16_tar_extract` matched only 1/4 expected terms (retrieval quality, not structural)

**Scoped quality gate: 17/20 (85%) FAILED**
- 15 platform-scope queries passed (linux, macos, bsd, common all isolate correctly)
- 2 host-scope queries FAILED (knowledge/macos paths leaked into host scope results)
- 1 linux isolation query FAILED (retrieval quality — no terms matched)

---

## Issue 1: Context endpoint applies scope as boost, not hard filter

### What happens

When Halbert calls `POST /projects/{id}/context` with `scope="host"`, the endpoint:
1. Resolves the scope to a set of file paths via `scope_resolver.resolve_mask()`
2. Uses those paths as a **score boost** (`_sr6_segment_boost = 0.25`) for matching files
3. Does NOT exclude files outside the scope from results

So a query for "sshd_config Port directive" with `scope="host"` returns:
- `applied_scope: host` (scope was found and applied)
- But the top result is `knowledge/macos/macports-guide/macports_guide_01.md` (score 0.828)
- Because that file has higher semantic similarity to "sshd_config Port directive" than any host config file, even after the 0.25 boost

### Why it's designed this way

SourcePrep was built for code engineering. When a developer says "search in the auth module," they want auth files boosted but don't want to hard-exclude a utility file that happens to be highly relevant. The boost approach is correct for that use case.

### Why it's wrong for Halbert

Halbert needs platform isolation. If a user asks "how do I configure sshd on macOS," returning Linux arch-wiki content is actively harmful — the instructions may not apply. Halbert needs hard filtering: if `scope="knowledge_macos"`, zero chunks from `knowledge/linux/` should appear.

### Where in the code

The context endpoint (`src/prep/api/routers/projects/search.py`, line 1256-1288) applies scope as boost:

```python
# Line 1277-1278: scope mask becomes a boost set, not a filter
_segment_file_paths = _expanded_mask
_sr6_segment_boost = max(_sr6_segment_boost, 0.25)
```

Then `idx.get_context()` (line 1295-1304) uses `_segment_file_paths` as a boost, not an `exclude_paths` filter.

In contrast, the `/search` endpoint (line 52-77) does hard filtering:

```python
# Line 62: hard skip — files outside scope are excluded
if _agent_mask is not None and source_path and not path_matches_any_scope(source_path, _agent_mask):
    continue
```

### Fix options

**Option A: Post-filter in Halbert's retrieval backend**
- File: `halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py`
- In `_parse_context_response()`, after parsing chunks, drop any chunk whose `source_path` doesn't match the scope's paths
- Pro: No SourcePrep changes, Halbert controls its own filtering
- Con: Wastes retrieval budget — if k=5 and 3 are out-of-scope, only 2 useful results come back. Would need to over-fetch (k=10) then filter down.
- Con: Halbert needs to know the scope's paths to filter (currently it just passes the scope name to SourcePrep)

**Option B: Add hard-filter mode to the context endpoint**
- File: `src/prep/api/routers/projects/search.py`, context endpoint
- Add a `scope_filter_mode` parameter: `"boost"` (default, current behavior) or `"hard"` (exclude non-matching)
- When `"hard"`, pass `_expanded_mask` as `exclude_paths` (inverted) to `idx.get_context()`
- Pro: Clean API, both use cases served, no wasted retrieval budget
- Con: SourcePrep code change, needs testing

**Option C: Use `/search` endpoint for scoped queries**
- Halbert's retrieval backend already has `SourcePrepClient.search()` which calls `/search` (hard filter)
- Route scoped queries to `.search()` and unscoped queries to `.get_context()`
- Pro: No code changes needed — the `/search` endpoint already hard-filters
- Con: `/search` returns `preview` (200 chars) not full `text` — Halbert would need to fetch full content separately, or the `/search` endpoint needs to return full content
- Con: Loses trace expansion, LOD compression, atlas prepend, concept injection — all the context assembly features that `/context` provides

**Our assessment:** Option B is the cleanest. Option A is the fastest to implement. Option C loses too much context assembly value.

---

## Issue 2: Retrieval quality gaps (2 queries)

### q16_tar_extract: "tar extract tar.gz archive to directory"
- Expected terms: `tar`, `extract`, `archive`, `gzip`
- Matched: only `tar` (1/4 = 25%, below 50% threshold)
- The query is about a common Unix command, and `knowledge/common/tldr/` should have tar examples
- Possible cause: the tar content may be in a chunk that doesn't contain all four terms, or the semantic search returned a different file's chunk

### s19_isolation_linux: "systemctl service enable" with scope=knowledge_linux
- Expected terms: `systemctl`, `service`
- Matched: 0/2 (0%)
- The query returned 1 chunk but the context text didn't contain "systemctl" or "service"
- Possible cause: the boost-only scope filtering (Issue 1) returned a chunk from a different platform that doesn't use systemd, or the semantic match was to a generic Linux file that mentions neither term

### Are these structural or tuning issues?

Both failures look like retrieval quality issues, not structural problems. The index has the content (tar is in common/tldr, systemctl is in linux arch-wiki/systemd-docs). The semantic search just didn't surface the right chunks for these specific queries.

Possible mitigations:
- Increase `k` (fetch more candidates, better chance of hitting the right chunk)
- Lower `min_score` (currently 0.15 — may be filtering out valid results)
- Add BM25/hybrid retrieval (SourcePrep's CodeIndex is dense-only; the Halbert project has its own `retriever.py` with BM25+dense hybrid that isn't being used)
- Query expansion (rewrite "tar extract" to "tar extract extract files gzip archive tarball")

---

## What's NOT broken (verified this session)

- The CodeIndex build is correct: 71,050 chunks, 768-dim, all 245 files
- The daemon loads the CodeIndex: `index source: code_index`, `total_chunks: 71050`
- Unscoped retrieval returns raw content (not LLM summaries)
- Platform scopes (linux, macos, bsd, common) isolate correctly in the `/search` endpoint
- The scope-name bug is fixed: `knowledge_<platform>` (underscores) in both the retrieval backend and quality gate
- The quality gate script is fixed: reads `source_path` and `context` fields correctly

---

## Files modified this session (uncommitted)

| File | Change |
|---|---|
| `scripts/corpus_quality_gate.py` | Fixed field name mismatch (`content`/`file_path` → `source_path`/`context`), fixed scope names (`knowledge-linux` → `knowledge_linux`) |
| `halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py` | Scope name fix (`knowledge-<plat>` → `knowledge_<plat>`) — done in prior session, still uncommitted |

## Questions for the reviewer

1. **Scope filtering approach:** Which fix option (A, B, or C) is the right one for Halbert? Is there a fourth option we're missing?
2. **Retrieval quality:** Are the 2 query failures worth fixing now, or are they acceptable for a v1? Should we consider hybrid (BM25+dense) retrieval?
3. **Commit strategy:** Should we commit the scope-name fix and quality gate fixes now, or bundle them with the scope-filtering fix?
4. **Context budget:** The `/context` endpoint returns up to 12,000 chars by default. Is that the right budget for Halbert's prompt, or should it be tuned per query type?

---

## Pointers

- Build script: `/Volumes/4TB-BAD/Halbert/scripts/staged_knowledge_embed.py`
- Quality gate: `/Volumes/4TB-BAD/Halbert/scripts/corpus_quality_gate.py`
- Retrieval backend: `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py`
- SourcePrep context endpoint: `/Volumes/4TB-BAD/HumanAI/CoDRAG/src/prep/api/routers/projects/search.py` (line 932, scope boost at line 1256)
- SourcePrep search endpoint (hard filter): same file, line 31 (scope filter at line 52)
- SourcePrep scope resolver: `/Volumes/4TB-BAD/HumanAI/CoDRAG/src/prep/core/scope_resolver.py`
- Quality gate reports: `/Volumes/4TB-BAD/Halbert/data/quality_gate_report.json`, `data/quality_gate_report_scoped.json`
- Project index: `/Users/ericbintner/.local/share/sourceprep/projects/735a592e-a2da-499b-a614-854a5fc461f5/`
- Corpus root: `/Users/ericbintner/.local/share/halbert/sourceprep/` (`host/`, `knowledge/{linux,macos,bsd,common}/`)
