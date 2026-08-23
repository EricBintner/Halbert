# Handoff: Phase 0 RAG Corpus Implementation

**Created:** 2026-08-23
**For:** External AI implementation agent
**From:** The Halbert build session
**Repository root:** `/Volumes/4TB-BAD/Halbert`

---

## Starter Prompt

You are picking up Phase 0 of the Halbert implementation plan — the RAG
corpus cleanup and SourcePrep ingestion. This is a well-scoped, mostly
mechanical task with a detailed plan already written. Your job is to
execute it.

The repository is at `/Volumes/4TB-BAD/Halbert`. There is a Python venv at
`.venv/` and the SourcePrep CLI (`prep`) is installed and running. All
work happens in this repo — no external services needed beyond the
SourcePrep daemon (already running) and HuggingFace/GitHub for downloading
replacement datasets.

**Read these before starting, in this order:**

1. `.handoff/RAG-OPTIMIZATION-PLAN-2026-08-23.md` — the full plan with
   research findings, problem analysis, and the phased approach. This is
   your primary document.
2. `.handoff/IMPLEMENTATION-PLAN-2026-08-23.md` lines 17–264 — the
   task-level breakdown for Phase 0 (tasks T0a.1 through T0g.2). Each
   task has files to create, implementation notes, acceptance criteria,
   and dependencies.
3. `.handoff/ROADMAP-2026-08-23.md` sections 2 and 3 — corpus state and
   the SourcePrep chunker gap (explains why we convert to markdown and
   why large files must be split).

**The work, in order:**

1. **T0b.1** — Remove empty docs (<50 chars) from all 57 JSONL files.
   Delete stale merged files. Write `scripts/remove_empty_docs.py`.
2. **T0b.2** — Run existing `scripts/clean_man_pages.py` on Linux man
   pages to strip backspace formatting artifacts.
3. **T0b.3** — Normalize all 5 JSONL schemas to one unified schema. Write
   `scripts/normalize_schema.py`.
4. **T0c.1** — Cross-source exact dedup by content hash. Write
   `scripts/dedup_corpus.py`.
5. **T0c.2** — Man page near-duplicate resolution (91 macOS/FreeBSD
   overlaps). Write `scripts/manpage_near_dedup.py`.
6. **T0d.1** — Convert JSONL to grouped markdown files for SourcePrep.
   Write `halbert_core/halbert_core/rag/jsonl_to_markdown.py`. Output to
   `data/staging/sourceprep/`. Split large sources into multiple files
   (500 docs or 500KB per file).
7. **T0a.1** — Register "halbert-knowledge" SourcePrep project pointing
   at `data/staging/sourceprep/`. Run `prep build`.
8. **T0e.1** — Corpus quality gate. Write
   `scripts/corpus_quality_gate.py` with 20 test queries.
9. **T0e.2** — Retrieval eval script. Write `scripts/retrieval_eval.py`.
10. **T0f.1** — Move cross-platform docs (git, ssh, bash, etc.) to
    `data/common/`.
11. **T0g.1** — Download clean replacement datasets (hannah-eee/arch-wiki-docs
    from HuggingFace, tldr-pages/tldr from GitHub).
12. **T0g.2** — Update `data/manifest.json` with actual counts. Bump
    version to 2.0.0.

**Key facts about the environment:**

- Python venv: `.venv/bin/python` (use this for all Python commands)
- SourcePrep CLI: `prep` (already on PATH, daemon running)
- SourcePrep has many existing projects but none for Halbert yet — you
  create "halbert-knowledge" in T0a.1
- The existing `scripts/clean_man_pages.py` already works — it was used
  on macOS man pages. It strips `\b` (backspace) formatting artifacts.
- The existing `halbert_core/halbert_core/rag/platform_loader.py` loads
  `data/linux + data/common` on Linux and `data/macos + data/bsd +
  data/common` on macOS. If you add `data/common/` content, update this
  loader.
- The `data/common/` directory exists with a README but no JSONL files.
- No `data/staging/` directory exists yet — you create it in T0d.1.

**Verified corpus state (2026-08-23):**

| Metric | Count |
|--------|-------|
| Total documents in JSONL files | 30,749 |
| Empty/near-empty (<50 chars) | 1,902 (6.2%) |
| Non-empty documents | 28,847 |
| Exact duplicates (full content hash) | 7,307 (23.8%) |
| Unique non-empty documents | ~21,540 |
| JSONL files | 57 |
| Distinct schemas | 5 |
| Manifest claimed total | 59,878 (inflated) |

**The 5 JSONL schemas (verified by scanning all 57 files):**

1. Man pages (Linux): `{"text": "...", "metadata": {"source_type": "man", ...}}`
2. HF datasets: `{"name": "...", "section": "...", "description": "...", "full_text": "...", "metadata": {...}}`
3. Scraped docs (macOS, some Linux): `{"id": "...", "url": "...", "title": "...", "content": "...", "source": "...", "category": "...", "tags": [...], "scraped_at": "...", "metadata": {...}}`
4. Simple scraped: `{"content": "...", "description": "...", "metadata": {...}, "name": "..."}`
5. Topic guides: `{"commands": [...], "distro": "...", "explanation": "...", "goal": "...", "metadata": {...}, "os": "...", "references": [...], "requires_sudo": bool, "risk_level": "...", "rollback": [...], "tags": [...], "verification_steps": [...]}`

**Target unified schema:**
```json
{"id": "...", "url": "...", "title": "...", "content": "...", "source": "...", "category": "...", "tags": [...], "scraped_at": "...", "metadata": {...}}
```

**SourcePrep chunker constraints (from roadmap section 3):**

- `.md`/`.markdown` files get `chunk_markdown()` — heading-based semantic
  splitting, min 350 chars per chunk. This is what we want.
- Large files (>max_file_size threshold) are truncated at 8000 chars with
  a single summary chunk. **This is why we must split large sources into
  multiple markdown files (500 docs or 500KB per file).**
- Files named `arch_wiki_01.md`, `arch_wiki_02.md`, etc. — keep every
  file under the truncation threshold.

**Commit rules:**

- Never add "Co-Authored-By" trailers to commit messages.
- Never add "Generated with Devin" or similar attribution.
- Commit messages contain only the subject line and body. Nothing else.
- Do not push unless explicitly asked.
- Do not commit if no changes exist.

**When you're done:**

- The corpus should be ~21,540 unique non-empty documents
- All JSONL files use the unified schema
- `data/staging/sourceprep/` contains ~50-100 markdown files (split for
  size)
- SourcePrep project "halbert-knowledge" is registered and built
- `scripts/corpus_quality_gate.py` passes all 20 test queries
- `data/manifest.json` reflects actual counts
- All scripts you wrote are in `scripts/` and are re-runnable

**Questions?** The plan documents are detailed. If something is ambiguous,
check the RAG-OPTIMIZATION-PLAN first, then the IMPLEMENTATION-PLAN. If
still unclear, make a reasonable decision and note it in a comment.

---

## Context for the implementation agent

### What Halbert is

Halbert is a system administration assistant that identifies as the
computer itself. It uses RAG retrieval to answer questions about the
host OS, config, and tooling. The RAG corpus is the knowledge base —
man pages, Arch Wiki, Homebrew formulas, FreeBSD Handbook, macOS support
docs, Q&A from Stack Exchange, and synthetic guides.

### Why this matters

The corpus is currently noisy: 6.2% empty docs, 23.8% exact duplicates,
5 incompatible schemas, backspace formatting artifacts in Linux man pages,
and an inflated manifest. SourcePrep (the retrieval backend) chunks on
markdown headings, so we need clean markdown files — not raw JSONL. This
phase is the foundation for all downstream retrieval work (Phases 2-8 of
the implementation plan).

### What NOT to do

- Do not modify `halbert_core/halbert_core/rag/document_indexer.py` —
  that's the old ChromaDB indexer, being retired. Your output (markdown
  files) is for SourcePrep, not ChromaDB.
- Do not modify `halbert_core/halbert_core/rag/data_pipeline.py` — same
  reason. The old pipeline is deprecated.
- Do not wire SourcePrep into the chat path — that's Phase 2, not Phase 0.
  Your job is to produce the markdown files and build the SourcePrep
  index. Wiring is someone else's task.
- Do not delete the original JSONL files — keep them as the canonical
  source. The markdown files in `data/staging/sourceprep/` are the
  build artifact.
- Do not add new scrapers or new data sources beyond what T0g.1 specifies
  (arch-wiki-docs replacement + tldr-pages). The corpus is already large
  enough.

### Existing code you should reuse

- `scripts/clean_man_pages.py` — works, already tested on macOS man pages
- `halbert_core/halbert_core/rag/platform_loader.py` — loads platform-
  specific data dirs; update if you add `data/common/` content
- `halbert_core/halbert_core/rag/scrapers/` — 28 existing scrapers, all
  produce JSONL in the scraped doc schema (schema 3 above)
- `halbert_core/halbert_core/integrations/sourceprep_client.py` —
  SourcePrep HTTP client, already wired
- `halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py`
  — SourcePrep retrieval backend, already wired into the app seam

### SourcePrep CLI usage

```bash
# Register a new project
prep add --name halbert-knowledge --path /Volumes/4TB-BAD/Halbert/data/staging/sourceprep

# Build the index
prep build --project-id <id-from-prep-list>

# Search the index
prep search "how to configure sshd" --project-id <id>

# List projects
prep list

# Check status
prep status --project-id <id>
```

The `prep add` command may need `--include-globs` or similar flags —
check `prep add --help` for the exact interface. The project should
include `**/*.md` files only.

### File layout after completion

```
data/
  linux/              # original JSONL (canonical, cleaned in place)
    man-pages/man_pages.jsonl
    arch-wiki-ext/arch_wiki_ext.jsonl
    ... (50 files)
  macos/              # original JSONL (canonical, already clean)
    man-pages/macos_man_pages.jsonl
    homebrew/homebrew.jsonl
    ... (5 files)
  bsd/                # original JSONL (canonical, already clean)
    freebsd-handbook/freebsd_handbook.jsonl
    freebsd-man/freebsd_man.jsonl
  common/             # cross-platform docs (new, from T0f.1)
    git/git.jsonl
    ssh/ssh.jsonl
    ...
  staging/
    sourceprep/       # markdown build artifact (new, from T0d.1)
      linux-man-pages/man_pages_01.md, man_pages_02.md, ...
      linux-arch-wiki/arch_wiki_01.md, arch_wiki_02.md, ...
      macos-man-pages/macos_man_pages_01.md, ...
      common-git/git.md
      ...
  manifest.json       # updated with actual counts (T0g.2)

scripts/
  remove_empty_docs.py     # T0b.1
  clean_man_pages.py       # already exists (T0b.2)
  normalize_schema.py      # T0b.3
  dedup_corpus.py          # T0c.1
  manpage_near_dedup.py    # T0c.2
  corpus_quality_gate.py   # T0e.1
  retrieval_eval.py        # T0e.2

halbert_core/halbert_core/rag/
  jsonl_to_markdown.py     # T0d.1 (the converter)
```

### Estimated effort

The plan estimates this as small-to-medium effort. The scripts are mostly
mechanical (scan JSONL, hash content, write filtered output). The
converter (`jsonl_to_markdown.py`) is the most substantial piece (~250
lines). The SourcePrep build will take 10-20 minutes for ~21K docs on
M-series. Total: a few hours of focused work.

---

## Reading list (full paths)

| Document | Path |
|----------|------|
| RAG optimization plan (primary) | `/Volumes/4TB-BAD/Halbert/.handoff/RAG-OPTIMIZATION-PLAN-2026-08-23.md` |
| Implementation plan (Phase 0 tasks) | `/Volumes/4TB-BAD/Halbert/.handoff/IMPLEMENTATION-PLAN-2026-08-23.md` |
| Roadmap (corpus + chunker context) | `/Volumes/4TB-BAD/Halbert/.handoff/ROADMAP-2026-08-23.md` |
| Manifest (current, needs correction) | `/Volumes/4TB-BAD/Halbert/data/manifest.json` |
| Approved sources config | `/Volumes/4TB-BAD/Halbert/config/approved_sources.yml` |
| Existing clean script | `/Volumes/4TB-BAD/Halbert/scripts/clean_man_pages.py` |
| Platform loader | `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/rag/platform_loader.py` |
| SourcePrep client | `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/sourceprep_client.py` |
| SourcePrep retrieval backend | `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py` |
| Data README (Linux) | `/Volumes/4TB-BAD/Halbert/data/linux/README.md` (if exists) |
| Data README (macOS) | `/Volumes/4TB-BAD/Halbert/data/macos/README.md` |
| Data README (BSD) | `/Volumes/4TB-BAD/Halbert/data/bsd/README.md` |
| Data README (common) | `/Volumes/4TB-BAD/Halbert/data/common/README.md` |
