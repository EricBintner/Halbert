# RAG Corpus Optimization Plan (Phase 0)

**Created:** 2026-08-23
**Status:** Plan, pre-implementation. Ready for review.
**Reads with:**
- `.handoff/IMPLEMENTATION-PLAN-2026-08-23.md` (the master implementation plan — this document IS its Phase 0)
- `.handoff/INTAKE-PIPELINE-DESIGN-2026-08-23.md` (intake pipeline design — affects retrieval budget)
- `data/manifest.json` (current source registry)
- `halbert_core/halbert_core/rag/document_indexer.py` (current chunking + indexing)
- `halbert_core/halbert_core/rag/data_pipeline.py` (current dedup + merge)
- Reviewer feedback on file count and grouping

---

## 0. The Problem

We now have 30,749 documents across 57 JSONL files. The reviewer's feedback
identifies two structural problems and we've discovered several more during
analysis:

### 0.1 What the reviewer said

> 30K individual markdown files. That's a lot of filesystem I/O for SourcePrep's
> build pipeline. Each file gets read, hashed, chunked, embedded individually.
> The alternative — grouping by source into larger markdown files with section
> headings — reduces file count from 30K to ~57 (one per JSONL) and lets
> chunk_markdown() split on headings. Faster build, less filesystem churn.
> Recommendation: group by source, one markdown file per JSONL, each doc as a
> section with an H2 heading.

### 0.2 What we found in the data (verified 2026-08-23 by line-counting all 57 JSONL files)

| Problem | Scale | Impact |
|---------|-------|--------|
| **Empty/near-empty documents** | 1,902 docs (6.2% of total) | Pure noise. No content to retrieve. Wastes index space and build time. Concentrated in `man_pages.jsonl` (1,656 empty) and `combined_all_output.jsonl` (246 empty, 100%). |
| **Exact content duplicates** | 7,307 docs (23.8% of total) | Same content indexed multiple times. Retrieval returns redundant results. Much higher than initially estimated. |
| **Backspace formatting artifacts** | Linux man-pages (5,703 non-empty docs) | Same `\b` formatting issue we fixed in macOS man pages. Degrades embedding quality. |
| **Schema inconsistency** | 5 distinct schemas across the corpus (verified by scanning all 57 files) | Indexer has to handle all schemas. Error-prone. |
| **Merged/corpus files are stale** | `rag_corpus_merged.jsonl` (2,990 docs), `combined_all_output.jsonl` (246 docs, 100% empty), `combined_all_output_converted.jsonl` (246 docs) | These are stale merge artifacts that bloat the corpus. |
| **HF datasets** | `arch_wiki.jsonl` (2,140), `tldr_man_pages.jsonl` (481), `unix_commands.jsonl` (100) | Downloaded from HuggingFace — need verification for content quality. |
| **91 man pages duplicated across macOS + FreeBSD** | 91 commands (e.g., `cat(1)`, `chmod(1)`, `find(1)`) | Same command, different man page source. Near-duplicates with different content lengths. |
| **No cross-platform dedup** | 0 (current dedup is URL-based, per-source only) | Same command documented in Linux, macOS, and FreeBSD gets indexed 3x. |
| **Manifest inflated** | Manifest claims 59,878 docs; actual JSONL lines total 30,749 | Linux source counts are inflated (arch_wiki claims 22,794 but has ~2,206; man_pages claims 17,084 but has 7,359). macOS/BSD counts are accurate. Manifest needs correction. |

### 0.3 The real numbers (verified by scanning all 57 JSONL files)

| Metric | Count |
|--------|-------|
| Total documents in JSONL files | 30,749 |
| Empty/near-empty (<50 chars) | 1,902 (6.2%) |
| Non-empty documents | 28,847 |
| Exact duplicates (full content hash) | 7,307 (23.8%) |
| **Unique non-empty documents** | **~21,540** |
| JSONL files | 57 |
| Manifest claimed total | 59,878 (inflated) |

After cleanup, the real corpus is ~21,540 unique non-empty documents across 57 files.
The manifest needs correction to reflect actual line counts.

---

## 1. Research Findings

### 1.1 Chunking strategy (NVIDIA, Microsoft, arxiv)

**Consensus:** Structural/heading-based chunking is the best default when
document structure exists. Fixed-size token chunking is a reasonable fallback
for unstructured text. Semantic chunking (embedding-based splitting) is NOT
worth the computational cost — a 2024 arxiv paper found "the computational
costs associated with semantic chunking are not justified by consistent
performance gains."

**NVIDIA findings:** Page-level chunking achieved highest accuracy (0.648)
with lowest variance. Section-level chunking (splitting on headings) is
comparable. Optimal chunk size: 256-512 tokens for factoid queries, 1024+
for complex analytical queries. 15% overlap is the sweet spot.

**Microsoft guidance:** "The key is to implement effective chunking approaches
for your specific document types and their specific structures." Structural
chunking (markdown headings) is recommended when structure exists.

**Multigrid guidance:** "Structural: Split on the document's own markup:
Markdown headings, HTML sections. The best default when the structure exists,
because the author already decided where the topic changes." Overlap is
"often unnecessary" with structural chunking because boundaries are already
at semantic breaks.

**Recommendation for Halbert:** Use heading-based chunking (SourcePrep's
`chunk_markdown()` already does this). Group documents into markdown files
with H2 headings per document. This aligns with the reviewer's feedback AND
the research consensus.

### 1.2 Deduplication (industry practice)

**Three layers of dedup** (from Avichala GenAI):
1. **Corpus-level:** Remove exact duplicates before indexing (hash-based)
2. **Chunk-level:** Remove near-identical chunks after splitting
3. **Retrieval-time:** Filter redundant results in top-k

**Coverage-preserving dedup** (from Tian Pan): Don't just remove
near-duplicates blindly. A product spec, a support doc, and an FAQ may say
nearly the same thing but serve different query intents. Remove documents
that add "zero marginal coverage" while preserving documents that cover the
same topic with "distinct vocabulary, framing, or level of detail."

**MinHash LSH** is the standard for near-duplicate detection at scale.
Threshold ~0.85 Jaccard similarity for strict dedup. For semantic dedup
(paraphrases), use embedding comparison only within MinHash candidate pairs.

**Recommendation for Halbert:**
- Layer 1: Hash-based exact dedup (already partially done, needs to be cross-source)
- Layer 2: For man pages, keep the most comprehensive version per command
  (macOS man page has 17,788 chars for `chmod(1)`, FreeBSD has 7,653 — keep
  both if they differ significantly, or keep the longer one if they're
  near-identical)
- Layer 3: Retrieval-time dedup is already handled by ChromaDB's upsert

### 1.3 Corpus size and retrieval quality

**Optimal retrieval volume:** 5-10 documents for QA tasks (ACM 2024 study).
Performance plateaus at k=10-20 and may decline beyond that. More documents
in context = more noise = worse performance.

**Corpus size:** 30K documents is NOT too many for a local RAG system.
Production systems routinely have millions. The issue isn't corpus size —
it's corpus quality. Empty docs, exact duplicates, and formatting artifacts
are what degrade retrieval. A clean 15K-document corpus will outperform a
noisy 30K-document corpus.

**BM25 at scale:** A 2025 scaling study found that BM25 (lexical retrieval)
overtakes agentic methods around 10M corpus tokens and leads at every larger
tier. For our ~15K docs (~30M chars ≈ ~7.5M tokens), we're in the range
where hybrid retrieval (BM25 + dense) is optimal.

### 1.4 Existing open-source datasets

Several pre-cleaned datasets exist that could replace our noisier sources:

| Dataset | Source | Size | Format | License | Use case |
|---------|--------|------|--------|---------|----------|
| `hannah-eee/arch-wiki-docs` | HuggingFace | ~10K pages | JSONL (clean text + headings) | GNU FDL | Replace our empty `hf-datasets/arch_wiki.jsonl` |
| `tmskss/linux-man-pages-tldr-summarized` | HuggingFace | 481 docs | CSV | MIT | Replace our empty `tldr_man_pages.jsonl` |
| `tldr-pages/tldr` | GitHub | ~6K pages | Markdown | CC BY 4.0 | Add TLDR summaries (we have 0 non-empty) |
| Stack Exchange data dumps | archive.org | Full site dumps | XML | CC BY-SA 4.0 | Replace API-limited Ask Different scrape |
| `dougiefresh/manpages` | HuggingFace | Q&A format | JSON | Various | macOS/Linux man page Q&A |

**Key finding:** Our HuggingFace datasets (`arch_wiki.jsonl`, `tldr_man_pages.jsonl`,
`unix_commands.jsonl`) are ALL 100% empty. They were downloaded but never
properly converted. The `hannah-eee/arch-wiki-docs` dataset is a clean,
RAG-ready replacement.

### 1.5 SourcePrep's chunking

SourcePrep chunks markdown by headings (confirmed in docs):
> "Files in scope are parsed with Tree-sitter, chunked at function/class
> boundaries (or by Markdown headers for docs)."

The `chunk_markdown()` function (found in a similar project) splits on H1/H2/H3
boundaries with breadcrumb headings. This is exactly what the reviewer
recommends: group by source into markdown files with section headings, let
SourcePrep chunk on those headings.

---

## 2. The Plan

### Phase A: Cleanup (do this first, highest impact)

#### A1. Remove empty documents
- Delete all documents with <50 chars of content from all JSONL files
- This removes 1,902 empty docs (6.2% of corpus), concentrated in:
  - `man_pages.jsonl`: 1,656 empty out of 7,359
  - `combined_all_output.jsonl`: 246 empty (100%)
- Delete the stale merged files entirely:
  - `data/linux/merged/rag_corpus_merged.jsonl` (2,990 docs, stale merge artifact)
  - `data/linux/merged/combined_all_output_converted.jsonl` (246 docs, stale)
  - `data/linux/commands/combined_all_output.jsonl` (246 docs, 100% empty)
- Verify HF datasets for content quality (may not all be empty as initially thought):
  - `data/linux/hf-datasets/arch_wiki.jsonl` (2,140 docs — verify content)
  - `data/linux/hf-datasets/tldr_man_pages.jsonl` (481 docs — verify content)
  - `data/linux/hf-datasets/unix_commands.jsonl` (100 docs — verify content)

#### A2. Clean Linux man page formatting
- Run the existing `scripts/clean_man_pages.py` on `data/linux/man-pages/man_pages.jsonl`
- This removes backspace artifacts from 5,703 non-empty docs
- Also normalize the schema: convert `text`/`metadata` to `content`/`title`/`source`

#### A3. Schema normalization
- Convert all Linux docs from old schema (`text`/`metadata`) to new schema
  (`content`/`title`/`source`/`tags`/`category`/`metadata`)
- This makes the indexer simpler and the data consistent

### Phase B: Deduplication

#### B1. Cross-source exact dedup
- Hash full content across ALL sources (not per-source)
- Remove exact duplicates, keeping the first occurrence
- Expected: ~7,307 duplicates removed (23.8% of corpus — much higher than initially estimated)

#### B2. Man page near-duplicate resolution
- For the 91 commands that appear in both macOS and FreeBSD man pages:
  - If content is >85% similar (Jaccard on word sets): keep the longer version
  - If content differs significantly: keep both (different implementations,
    different flags, different examples)
- Manual spot-check of a few examples to validate the threshold

#### B3. Arch Wiki dedup
- We have Arch Wiki content in 3 places: `arch-wiki-ext/` (43 docs),
  `more-arch/` (23 docs), `hf-datasets/arch_wiki.jsonl` (empty)
- After replacing with `hannah-eee/arch-wiki-docs` dataset, dedup against
  existing Arch Wiki content

### Phase C: Replace empty datasets with clean ones

#### C1. Download `hannah-eee/arch-wiki-docs` from HuggingFace
- Clean JSONL with `content`, `title`, `headings`, `url_path` fields
- ~10K English pages (we can filter to English only)
- Replaces our 2,140 empty docs + 43 ext docs + 23 more-arch docs

#### C2. Download TLDR pages from GitHub
- Clone `tldr-pages/tldr` and convert to JSONL
- ~6K command summaries with examples
- CC BY 4.0 license (already in our approved sources)
- Replaces our 481 empty docs

#### C3. (Optional) Download Stack Exchange data dump for Ask Different
- Full site dump from archive.org (CC BY-SA 4.0)
- Would give us thousands of Q&A instead of 269 from the API
- Format: XML, needs a converter
- Lower priority — 269 high-quality Q&A is already useful

### Phase D: Group into markdown files (reviewer's recommendation)

#### D1. Convert JSONL to grouped markdown
- One `.md` file per JSONL source (54 files total)
- Each document becomes an H2 section with metadata as a comment header
- Format:
  ```markdown
  # Source: macos-man-pages

  ## al(1)
  <!-- id: macos_al_1 | url: x-man-page://1/al | source: macos-man-pages | tags: macos,man_page,al -->

  al(1)                        General Commands Manual                       al(1)

  NAME
         al, al2 - Mono Assembly Linker
  ...

  ## brew(1)
  <!-- id: macos_brew_1 | url: ... | source: macos-man-pages | tags: ... -->

  brew(1) ...
  ```

- SourcePrep's `chunk_markdown()` splits on H2 headings → each document
  becomes a chunk with its heading as breadcrumb context
- File count drops from 30K individual docs to ~54 markdown files
- Build time drops dramatically (54 file reads vs 30K)

#### D2. Update the ingestion pipeline
- Modify `document_indexer.py` to read grouped markdown files
- Or: keep JSONL as the source of truth, generate markdown as a build step
- The markdown files are the SourcePrep input; JSONL remains the canonical format

### Phase E: Update manifest and configs

#### E1. Update `data/manifest.json`
- Remove deleted sources
- Add new sources (arch-wiki-docs from HuggingFace, tldr-pages)
- Update document counts to reflect post-dedup numbers
- Bump version to 2.0.0 (breaking change to corpus)

#### E2. Update `config/approved_sources.yml`
- Add HuggingFace as an approved source for arch-wiki-docs
- Add tldr-pages GitHub repo as approved source

---

## 3. Priority Order

| Phase | Effort | Impact | Priority |
|-------|--------|--------|----------|
| A1: Remove empty docs | Low (script) | Medium (6.2% noise reduction) | Do first |
| A2: Clean Linux man pages | Low (existing script) | Medium (embedding quality) | Do first |
| A3: Schema normalization | Medium (script) | Medium (consistency) | Do first |
| B1: Cross-source exact dedup | Low (script) | High (7.3K dups — 24% of corpus!) | Do second |
| C1: Replace Arch Wiki | Low (download) | High (2K empty → 10K clean) | Do second |
| C2: Add TLDR pages | Low (clone + convert) | Medium (6K summaries) | Do second |
| D1: Group into markdown | Medium (script) | High (build perf) | Do third |
| B2: Man page near-dedup | Medium (needs tuning) | Low (91 docs) | Do third |
| D2: Update ingestion | Medium (code change) | Medium | Do fourth |
| C3: Stack Exchange dump | High (XML parsing) | Medium | Defer |
| E1-E2: Config updates | Low | Low | Do last |
| E3: Fix manifest counts | Low (script) | Medium (accuracy) | Do last |

---

## 4. Expected Outcome

| Metric | Before | After |
|--------|--------|-------|
| Total documents | 30,749 | ~21,540 |
| Empty documents | 1,902 | 0 |
| Exact duplicates | 7,307 | 0 |
| JSONL files | 57 | ~50 (after removing stale merged files) |
| Markdown files for SourcePrep | 0 | ~50 |
| Schema consistency | Mixed (5 schemas) | Unified (1 schema) |
| Man page formatting | Mixed (some with \b artifacts) | Clean |
| Build file count | 30K individual docs | ~50 markdown files |
| Manifest accuracy | Inflated (claims 59,878) | Correct (actual line counts) |

The corpus shrinks from 30,749 to ~21,540 unique non-empty documents, but the effective
information density increases dramatically. SourcePrep build goes from
30K file reads to ~50. Retrieval quality improves because there's no
empty-doc noise and no duplicates.

---

## 5. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Removing merged files loses data | They're 99.6%+ empty. The non-empty docs are duplicates of docs in source files. |
| Replacing Arch Wiki loses custom scraping | The HuggingFace dataset is derived from the same `arch-wiki-docs` package. It's a superset. |
| Markdown grouping loses granular trace nodes | SourcePrep chunks on H2 headings, so each doc is still a separate chunk. The trace graph node is the chunk, not the file. |
| Man page near-dedup removes useful variants | Use conservative threshold (85% Jaccard). Keep both if they differ significantly. Manual spot-check. |
| Schema migration breaks existing index | Rebuild index from scratch after migration. The old index is disposable. |

---

## 6. Open Questions

1. **Should we keep both macOS and FreeBSD man pages for shared commands?**
   The FreeBSD versions sometimes have more detail (e.g., `dmesg(8)`: FreeBSD
   has 1,880 chars vs macOS 457 chars). Recommendation: keep both, let
   retrieval surface the more relevant one. They're not true duplicates —
   they're different implementations of the same command.

2. **Should the markdown grouping be a build step or replace JSONL?**
   Recommendation: keep JSONL as canonical, generate markdown as a build step.
   JSONL is better for programmatic access. Markdown is better for SourcePrep.

3. **Should we download the full Stack Exchange dump?**
   269 Ask Different Q&A is useful but limited. The full dump would give us
   ~50K Q&A but requires XML parsing and significant filtering. Defer unless
   we need more Q&A coverage.

4. **Should we add `data/common/` for cross-platform docs?**
   Commands like `git`, `ssh`, `bash`, `grep` work the same on Linux and macOS.
   Currently they're in Linux sources only. A `common/` directory would avoid
   needing them in both platform-specific corpora. But this is a data
   organization decision, not a quality decision. Defer.

---

## 7. Sync with IMPLEMENTATION-PLAN-2026-08-23.md

This plan IS Phase 0 of the master implementation plan. The implementation
plan says:

> Phase 0 — SourcePrep doc ingestion — is delegated to a separate AI session
> working on the RAG corpus.

That separate session is us. The implementation plan covers Phases 1-8 and
assumes Phase 0 produces a clean, SourcePrep-ready corpus. Our plan fills
that gap.

### 7.1 Alignment — where our plan feeds the implementation plan

| Our phase | Their phase | How they connect |
|-----------|-------------|------------------|
| A (cleanup) | Phase 2 (RAG Consolidation) | Phase 2's T2a.1 wires SourcePrepRetrievalBackend into the assembler. SourcePrep indexes our markdown files. Empty docs and duplicates would waste the retrieval budget and degrade retrieval quality. Our cleanup ensures the retrieval budget (defined in T1b.1) is spent on useful content. |
| B (dedup) | Phase 2 (RAG Consolidation) | Cross-source dedup ensures SourcePrep's index doesn't have redundant chunks. The implementation plan assumes a clean index but doesn't address how to get there. |
| C (replace empty datasets) | Phase 8 (Reactive Slice) | The "how are you?" slice (T8d.1) needs high-quality retrieval for biography/self-knowledge. If the corpus has 7,845 empty docs, retrieval quality suffers. Replacing empty Arch Wiki (2,140 docs) with clean hannah-eee dataset (~10K docs) directly improves this. |
| D (group into markdown) | Phase 2's T2a.1 | SourcePrep chunks on markdown headings. Our Phase D produces the markdown files that SourcePrep indexes. Without this, SourcePrep would need to process 30K individual JSONL records — the exact problem the reviewer identified. |
| E (config updates) | Phase 2's T2a.2 | T2a.2 renames source type "rag" → "retrieval" in the assembler. Our manifest update should use the same naming convention. |

### 7.2 Dependencies — what we need from the implementation plan

| Their phase | What we need | Why |
|-------------|-------------|-----|
| Phase 2 (T2a.1) | SourcePrep project config | We need to know the SourcePrep project name and scope for our RAG corpus. T5a.1 creates a "halbert-host" project for config. We should create a "halbert-knowledge" project for the RAG corpus. These are two separate SourcePrep projects serving different purposes. |
| Phase 1 (T1b.1) | ContextBudget.retrieval allocation | The budget table defines how many tokens retrieval gets per model tier. Our corpus quality determines how much useful content fits in that budget. A clean 15K-doc corpus in a 300-token retrieval budget (medium tier) will surface better results than a noisy 30K-doc corpus in the same budget. |

### 7.3 No conflicts

Our plan touches only:
- `data/` directory (JSONL files, manifest, READMEs)
- `scripts/` (cleanup utilities)
- `halbert_core/halbert_core/rag/scrapers/` (new scrapers)

The implementation plan touches:
- `halbert_core/halbert_core/intake/` (new module)
- `halbert_core/halbert_core/context/` (assembler changes)
- `halbert_core/halbert_core/agents/` (state machine)
- `halbert_core/halbert_core/dashboard/` (routes, frontend)
- `halbert_core/halbert_core/findings/` (new module)

Zero file overlap. No conflicts.

### 7.4 Suggestions for the implementation plan

These are improvements we discovered during RAG analysis that would benefit
the larger scope:

#### S1: Define two SourcePrep projects explicitly

The implementation plan's T5a.1 creates a "halbert-host" SourcePrep project
for the host config tree. But there's no mention of the RAG knowledge base
as a SourcePrep project. We should define:

- **"halbert-knowledge"**: The RAG corpus (our markdown files from Phase D).
  Contains man pages, Arch Wiki, Homebrew, FreeBSD Handbook, Q&A, synthetic
  guides. Indexed by SourcePrep for retrieval during chat.
- **"halbert-host"**: The host config tree (T5a.1). Contains /etc config
  files, launchd plists. Indexed by SourcePrep for config brain findings.

These are separate projects with different scopes, different freshness
requirements, and different retrieval patterns. The implementation plan
should mention both in Phase 2 or Phase 0.

**Recommendation:** Add a T0a.1 task to the implementation plan: "Register
halbert-knowledge as a SourcePrep project" with the markdown files from our
Phase D as the project scope.

#### S2: Add a corpus quality gate (analogous to Phase 4.5 boot-test gate)

The implementation plan has a boot-test gate (Phase 4.5) that verifies the
full stack works end-to-end. We need an analogous gate for the RAG corpus:

- A set of ~20 test queries with expected source matches
- Run before and after cleanup to verify improvement
- Verify SourcePrep can build the index from our markdown files
- Verify retrieval returns relevant results (not empty docs)

**Recommendation:** Add a T0e.1 task: "Corpus quality gate — verify
retrieval returns useful results for 20 test queries after cleanup."

#### S3: The intake budget table should account for corpus quality

The budget table in T1b.1 allocates tokens for retrieval:
- tiny: 50 tokens, small: 100, medium: 300, large: 600, xlarge: 1200, massive: 2400

These budgets assume a clean corpus. With 7,845 empty docs in the current
corpus, a 300-token retrieval budget might return 3 chunks of nothing. After
our cleanup, the same 300-token budget returns 3 chunks of useful content.

**Recommendation:** Note in the implementation plan that the budget table
assumes Phase 0 cleanup is complete. The budgets may need tuning after
measuring actual retrieval quality post-cleanup.

#### S4: Schema normalization affects Phase 2 migration scripts

Phase 2's T2c.1 migrates `self_knowledge_all` from ChromaDB to SourcePrep
observations. T2c.2 migrates `self_conversations` to memory_v2. These
migrations read from ChromaDB collections that use the old schema
(`text`/`metadata`).

Our Phase A3 (schema normalization) unifies all JSONL to the new schema
(`content`/`title`/`source`). The migration scripts in T2c.1/T2c.2 should
use the same normalized schema when writing to SourcePrep/memory_v2.

**Recommendation:** T2c.1 and T2c.2 should reference our normalized schema
as the target format for migrated records.

#### S5: Cross-platform docs (data/common/)

The implementation plan doesn't mention cross-platform documentation. Commands
like `git`, `ssh`, `bash`, `grep`, `sed`, `awk` work the same on Linux and
macOS. Currently they're only in Linux sources. On macOS, retrieval for "how
do I use git rebase?" would search macOS-specific sources (man pages,
Homebrew) but miss the Linux vendor docs that cover git comprehensively.

A `data/common/` directory for cross-platform tools would:
- Avoid duplicating these docs in both platform-specific corpora
- Ensure macOS users get comprehensive coverage of cross-platform tools
- Reduce total corpus size (no need for git docs in both linux/ and macos/)

**Recommendation:** Add a T0f.1 task: "Create data/common/ for cross-platform
docs (git, ssh, bash, grep, sed, awk, curl, wget, vim, emacs). Move
cross-platform content from linux/ to common/. Update platform_loader.py to
load common/ for all platforms."

#### S6: Retrieval quality measurement

The implementation plan doesn't define how to measure retrieval quality
before and after the Phase 0/2 changes. Without measurement, we can't verify
that the corpus cleanup actually improved things.

A simple eval framework:
- 20-50 test queries spanning domains (storage, network, security, macOS, Linux)
- For each query, the expected source(s) that should be retrieved
- Run retrieval, measure: precision (did the right source appear in top-k?),
  coverage (did any source from the expected domain appear?)
- Run before cleanup, after cleanup, after SourcePrep wiring

**Recommendation:** Add a T0e.2 task: "Create a retrieval eval script with
20-50 test queries and expected source matches. Run before and after corpus
cleanup to quantify improvement." This also benefits Phase 2's T2a.1
acceptance criteria — "SourcePrep results are relevant" is subjective without
measurement.

#### S7: The implementation plan's Phase 2 assumes ChromaDB has useful data

T2c.1 migrates `self_knowledge_all` from ChromaDB to SourcePrep. But
ChromaDB's `linux_docs` collection was indexed from our JSONL files — which
have 7,845 empty docs and 2,034 duplicates. The ChromaDB index is noisy.

After our Phase 0 cleanup, the ChromaDB index should be rebuilt from the
cleaned JSONL before migration. Otherwise we're migrating noise.

**Recommendation:** Add a note to T2c.1: "Rebuild ChromaDB index from cleaned
JSONL (post-Phase 0) before migration. The current index contains 7,845 empty
docs and 2,034 duplicates that should not be migrated."

### 7.5 Updated task list for Phase 0

Based on the sync analysis, here's the complete Phase 0 task list for the
implementation plan:

| Task | Description | Dependencies |
|------|-------------|--------------|
| T0a.1 | Register "halbert-knowledge" as a SourcePrep project (scope: markdown files from T0d.1) | T0d.1 |
| T0a.2 | Run `prep build` on halbert-knowledge project | T0a.1 |
| T0b.1 | Remove empty documents from all JSONL files (7,845 docs) | — |
| T0b.2 | Clean Linux man page formatting (backspace artifacts) | — |
| T0b.3 | Normalize schema across all JSONL (unify to content/title/source) | T0b.1 |
| T0c.1 | Cross-source exact dedup (2,034 duplicates) | T0b.3 |
| T0c.2 | Man page near-duplicate resolution (91 macOS/FreeBSD overlaps) | T0c.1 |
| T0d.1 | Convert JSONL to grouped markdown files (~50 files, H2 per doc) | T0c.1 |
| T0e.1 | Corpus quality gate — verify retrieval for 20 test queries | T0a.2 |
| T0e.2 | Create retrieval eval script with expected source matches | T0a.2 |
| T0f.1 | Create data/common/ for cross-platform docs | T0b.3 |
| T0g.1 | Replace empty HF datasets with clean ones (arch-wiki-docs, tldr-pages) | T0b.1 |
| T0g.2 | Update manifest.json and approved_sources.yml | All above |

This is the complete Phase 0. Phases 1-8 in the implementation plan can
proceed once T0a.2 and T0e.1 are complete (SourcePrep built, quality verified).
