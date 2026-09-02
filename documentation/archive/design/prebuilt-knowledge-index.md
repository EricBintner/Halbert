> **ARCHIVED 2026-09-02 (RAG-21-adjacent, SONNET-05).** Proposes a
> distribution mechanism for a ChromaDB embedding index; the corpus is now
> staged and indexed by SourcePrep/CodeIndex instead, with a different
> distribution problem (`RAG-13`/`RAG-14` — 13 corpus JSONL files gitignored,
> no shipped index asset, both open founder decisions in
> `.handoff/DISPATCH-2026-09-01-FOUNDER-DECISIONS.md`). Kept for the framing
> of the problem (identical corpus, deterministic embedding, build-once
> distribute-many is still the right shape), not for its ChromaDB-specific
> mechanics.

# Pre-built Knowledge Index Distribution

## Problem

The Halbert knowledge corpus (man pages, Arch Wiki, FreeBSD handbook, common
CLI references) is ~28,000 documents across 252 Markdown files. Embedding
these with the configured embedding model on a local CoreML/GPU takes
1-2 hours on an M-series Mac. This is unacceptable as an onboarding step.

The knowledge corpus is **identical for every user** — it's reference
documentation, not user-specific data. The embedding model is deterministic.
Therefore the entire knowledge index can be built once and distributed.

## Solution: Embedded Mode + Pre-built Index

SourcePrep already supports `mode: embedded` projects, where the index
directory lives at `<project_root>/.sourceprep/` instead of the XDG data
directory. This means we can ship the pre-built index as files on disk and
SourcePrep will read them directly — no import/export API needed.

### What Gets Pre-built (shipped with the app / downloaded)

The `.sourceprep/` directory for the knowledge corpus:

| File | Contents | Est. Size |
|------|----------|-----------|
| `embeddings.npy` | 28K chunks x 768-dim float32 | ~86 MB |
| `documents.json` | Chunk metadata (paths, content, line ranges) | ~15 MB |
| `fts.sqlite3` | Full-text search index | ~20 MB |
| `trace_nodes.jsonl` | Structural trace graph nodes | 29 MB |
| `trace_edges.jsonl` | Structural trace graph edges | 29 MB |
| `manifest.json` | Build metadata (model, dim, file hashes) | <1 KB |
| `trace_manifest.json` | Trace graph build metadata | <30 KB |
| `atlas.json` | Generated atlas (if built) | ~1 KB |
| `repo_policy.json` | Detected repo policy | ~2 KB |
| `changeset.json` | Changeset snapshot | ~16 KB |

**Total: ~180 MB** (compresses to ~60-80 MB with zstd)

### What Gets Built at Runtime (seconds, not hours)

Only the `host` scope — the user's live config files (~40 files). This is
a trivial embedding job that takes seconds on any modern machine.

## Architecture: Two-Project Split

Instead of one unified project, we use **two SourcePrep projects**:

### Project 1: `halbert-knowledge` (embedded, pre-built)

- **Mode:** `embedded`
- **Root:** `<halbert_app_data>/sourceprep-knowledge/`
- **Index dir:** `<halbert_app_data>/sourceprep-knowledge/.sourceprep/`
- **Contents:** The 252 knowledge Markdown files + pre-built `.sourceprep/`
- **Scopes:** `knowledge-linux`, `knowledge-macos`, `knowledge-bsd`,
  `knowledge-common` (all `prose_docs` profile)
- **No host files here.** This project is read-only at runtime — the
  pre-built index is never rebuilt unless the corpus version changes.
- **Distribution:** Downloaded during onboarding (with user permission) or
  bundled with the app installer.

### Project 2: `halbert-host` (standalone, built at runtime)

- **Mode:** `standalone`
- **Root:** `~/.local/share/halbert/sourceprep/host-tree/`
- **Index dir:** XDG data dir (daemon-managed)
- **Contents:** The user's live config files (~40 files, staged by
  `register_host_project`)
- **Scopes:** `host` (`system_config` profile)
- **Build:** Fast sync only (structural + trace + embeddings). Takes seconds.
- **No knowledge files here.** This project is rebuilt whenever the user's
  config changes.

### Retrieval: Cross-Project Query

The retrieval backend (`sourceprep_retrieval_backend.py`) queries both
projects and merges results. The `scope_for_query` router already
distinguishes host vs knowledge queries — it just needs to target the
right project:

- `scope=host` → query `halbert-host` project
- `scope=knowledge-*` → query `halbert-knowledge` project
- `scope=None` (unscoped) → query both, merge by score

This is a small change to the retrieval backend: instead of one
`project_id`, it holds two and dispatches based on the resolved scope.

## Distribution Flow

### Option A: Download During Onboarding (primary)

1. User installs Halbert.
2. On first launch, onboarding wizard offers to download the knowledge
   corpus (~80 MB compressed).
3. User accepts → Halbert downloads `halbert-knowledge-index-v1.tar.zst`
   from a GitHub release / CDN.
4. Extract to `<halbert_app_data>/sourceprep-knowledge/`.
5. `sourceprep_setup.py` creates the `halbert-knowledge` project in
   embedded mode (no build needed — index is already there).
6. `sourceprep_setup.py` creates the `halbert-host` project and builds
   the host scope (seconds).

### Option B: Bundled with App (fallback / offline)

1. The pre-built index ships inside the app bundle at
   `Halbert.app/Contents/Resources/sourceprep-knowledge/`.
2. On first launch, Halbert copies it to the user's data directory.
3. Same setup as Option A steps 5-6.

### Versioning

The knowledge index is versioned by corpus version + embedding model:
`halbert-knowledge-index-v{corpus}-{embedding-model}.tar.zst`

When the corpus is updated (new man pages, new wiki dumps), a new version
is published. Halbert checks for updates periodically and offers to
download the new version (with user permission).

## Build Pipeline (one-time, for maintainers)

```
# 1. Generate knowledge corpus from JSONL sources
python scripts/jsonl_to_markdown.py --output ~/.local/share/halbert/sourceprep/knowledge/

# 2. Create the knowledge project in embedded mode
# (sourceprep_setup.py with a knowledge-only template)

# 3. Run the full build (embeddings + trace + atlas)
# This is the 1-2 hour step that only happens once per corpus version.
sourceprep_setup apply --template knowledge-only --build

# 4. Package the .sourceprep/ directory
tar --zstd -cf halbert-knowledge-index-v1.tar.zst \
    -C ~/.local/share/halbert/sourceprep-knowledge/ .sourceprep/ knowledge/

# 5. Publish as a GitHub release asset
```

## Changes Required

### sourceprep_setup.py

- Add a `knowledge_template.yml` (knowledge-only, embedded mode) alongside
  the unified `sourceprep_template.yml`.
- Add an `apply_knowledge_prebuilt()` method that:
  - Creates the `halbert-knowledge` project in embedded mode
  - Verifies the `.sourceprep/` index files exist (no build needed)
  - Reconciles scopes (read-only — no paths to add/remove)
- Modify `apply()` to support the two-project split:
  - If pre-built knowledge index exists → use it (no knowledge build)
  - If not → fall back to building knowledge in the unified project
    (current behavior, for development)

### sourceprep_retrieval_backend.py

- Hold two project IDs: `host_project_id` and `knowledge_project_id`.
- In `get_context()`, dispatch based on resolved scope:
  - `host` → query host project
  - `knowledge-*` → query knowledge project
  - `None` → query both, merge results by score

### Onboarding (dashboard)

- Add a step that offers to download the pre-built knowledge index.
- Show download progress and estimated size.
- On completion, trigger `sourceprep_setup.apply()` which sets up both
  projects.

### Corpus versioning

- Add a `knowledge_corpus_version` field to the knowledge template.
- Halbert checks the latest version on GitHub releases.
- If a newer version exists, offer to download it (with user permission).

## Why Not One Unified Project?

The current unified project (`halbert`, standalone mode) mixes host and
knowledge files in one index. This works for development but not for
distribution:

1. **Can't ship a pre-built index for a mixed project** — the host files
   are user-specific, so the index would be wrong for every other user.

2. **Embedded mode puts the index in the project root** — if the project
   root contains both knowledge/ and host/, the `.sourceprep/` directory
   would be inside the user's data directory, not shippable.

3. **Two projects is cleaner** — the knowledge project is read-only and
   versioned; the host project is rebuilt on config changes. They have
   different lifecycles, different scopes, different profiles. Keeping
   them separate respects that.

The retrieval backend already routes by scope; the two-project split just
makes the routing explicit at the project level instead of the scope level.
