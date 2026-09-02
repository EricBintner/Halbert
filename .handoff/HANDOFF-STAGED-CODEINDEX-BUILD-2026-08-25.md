# Handoff: Staged External CodeIndex Build for Halbert Knowledge Corpus

**Date:** 2026-08-25
**Status (updated 2026-09-02, RAG-10):** ~~Ready to execute. Fix landed, script written, smoke-tested (imports/embedder only — no build has run).~~ **EXECUTED AND DONE.** The build this doc plans finished 2026-08-26: 71,050 chunks, 245 files (`.handoff/HANDOFF-SCOPE-FILTER-REVIEW-2026-08-26.md`, reviewed live against the daemon). `.handoff/CODEINDEX-BUILD-LOCK.txt`, which claimed a build was still in progress under PID 66131, was stale (that process had long since exited) and has been deleted. The plan below is kept for its design rationale, not as an open TODO — the daemon's current live state is a separate question from what this doc describes (RAG-01 in the SONNET-05 results doc: the daemon's own scope-fix code is uncommitted in the CoDRAG checkout, a clean daemon restart reverts retrieval quality independent of whether this embedding build itself is intact).
**For:** The AI session that executes and babysits the staged embedding build.
**Supersedes/decides:** `.handoff/HANDOFF-RAG-ARCHITECTURE-REVIEW-2026-08-25.md` — review complete. Strategy confirmed: **Option A** (embed everything once, filter per-query by scope). Details below.

---

## TL;DR for the executing session

1. Smoke-test the embedder on one small path (~minutes).
2. Run stage 1 → 2 → 3 of `scripts/staged_knowledge_embed.py` (~24h total compute, user estimate; measure real throughput during stage 1 and report the actual ETA).
3. Restart the SourcePrep daemon.
4. Run the acceptance queries below — scoped retrieval must return raw corpus content filtered to the right platform.
5. If anything is off, restore the snapshot the script took (it prints the path).

## Why staged + external

- SourcePrep's `POST /projects/{id}/build` only builds the whole scope union in one run (no partial staging) and runs inside the daemon process.
- The corpus: 245 markdown files, 87M total — `macos` 48M / `linux` 30M / `common` 5M / `bsd` 4M, plus `host` 160K. This host is a Mac, so macos+common+host (~53M) is the highest-value first slice.
- `CodeIndex.build()` reuses unchanged files' embeddings across runs (manifest `file_hashes`), so later stages only embed the newly added platform. Nothing is recomputed.
- The script calls SourcePrep's own `CodeIndex`/`embedder_factory` in-process → artifacts are exactly what the daemon writes; no format drift.

## Already done this session (do not redo)

- **Scope-name bug fixed.** `halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py` now emits `knowledge_<platform>` (underscores, matching daemon scope IDs) instead of `knowledge-<platform>`. Tests updated (`tests/test_sourceprep_scope_routing.py`); 18/18 SourcePrep tests pass. Not committed.
- Verified live: with the CodeIndex empty, the context endpoint falls back to KnowledgeIndex (LLM summaries) and **ignores scope entirely** — so scope filtering cannot be validated until the CodeIndex exists. Do not treat "identical results for every scope" as a regression after your build; it is the current baseline.
- The LLM enrichment pipeline is already complete (all 15 stages, 11:48 UTC). Do not rerun it. Embedding is the only remaining compute.
- `sourceprep_template.yml` scope ids are **display names by design** (daemon assigns underscore IDs from them). Leave the template alone.

## Exact commands

Use the CoDRAG venv python (has `prep` + onnx deps):

```bash
SP=/Volumes/4TB-BAD/HumanAI/CoDRAG/.venv/bin/python
cd /Volumes/4TB-BAD/Halbert

# Preflight — daemon present, not building, corpus static:
curl -s localhost:8400/health
curl -s localhost:8400/projects/735a592e-a2da-499b-a614-854a5fc461f5/status \
  | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print('building:',d['building'],'| index source:',d['index']['source'],'| chunks:',d['index']['total_chunks'])"
# Expect: building: False, source: knowledge, chunks: 98 (fallback index)

# Smoke test (REQUIRED FIRST): embeds only knowledge/common (5M, 20 files).
$SP scripts/staged_knowledge_embed.py --paths knowledge/common --yes-i-know-its-not-staged
# Check the log: files/min + ETA. If embedding throughput is absurd (<1 file/min),
# stop and reassess the 24h estimate before starting stage 1.

# Stages (each overwrites the index with the cumulative union; later stages
# reuse prior chunks — they are NOT additive embeds):
$SP scripts/staged_knowledge_embed.py --stage 1   # host + macos + common (~53M)
$SP scripts/staged_knowledge_embed.py --stage 2   # + linux (+30M)
$SP scripts/staged_knowledge_embed.py --stage 3   # + bsd (+4M) = full corpus
```

The script snapshots `documents.json`/`embeddings.npy`/`manifest.json`/`fts.sqlite3`
into `<index_dir>/backups/pre_stage_<ts>/` before writing, then prints build meta
and index stats. It exits non-zero if the result doesn't load.

## Daemon reload

The daemon caches the CodeIndex in memory. After the final stage (or between stages,
if you want progressively better retrieval live):

```bash
# simplest reliable reload: restart the daemon, then re-check status
curl -s localhost:8400/projects/735a592e-a2da-499b-a614-854a5fc461f5/status \
  | python3 -c "import json,sys; i=json.load(sys.stdin)['data']['index']; print(i['source'], i['total_chunks'], i['embedding_dim'])"
# Expect: source flips off "knowledge" (or reports the CodeIndex), total_chunks in the
# thousands, embedding_dim 768.
```

## Acceptance tests (the point of all this)

```bash
PID=735a592e-a2da-499b-a614-854a5fc461f5
q() { curl -s -X POST localhost:8400/projects/$PID/context -H 'Content-Type: application/json' -d "$1" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); data=d.get('data',d); [print('-',c.get('source_path'),round(c.get('score',0),3),'|',(c.get('text','')[:90]).replace(chr(10),' ')) for c in (data.get('chunks') or [])[:4]]"; }

# 1. Unscoped: must return RAW corpus content, not "File:/Summary:" LLM blurbs
q '{"query":"sshd_config PermitRootLogin accepted values","k":4,"structured":true}'

# 2. Correct scope: ONLY knowledge/linux/ paths
q '{"query":"sshd_config PermitRootLogin","k":4,"structured":true,"scope":"knowledge_linux"}'

# 3. Mac scope: ONLY knowledge/macos/ paths
q '{"query":"brew install options","k":4,"structured":true,"scope":"knowledge_macos"}'

# 4. Hyphen scope (legacy wrong name): expect a scope_warning in the response envelope
curl -s -X POST localhost:8400/projects/$PID/context -H 'Content-Type: application/json' \
  -d '{"query":"ssh","k":2,"structured":true,"scope":"knowledge-linux"}' | python3 -m json.tool | grep -i scope
```

Pass criteria: (1) content looks like man-page/config text; (2)+(3) every chunk's
`source_path` starts with the scoped prefix; (4) carries `scope_warning`.

Also run the repo quality gate once the full corpus is embedded:
`scripts/corpus_quality_gate.py` (T-V.2, named in the template's post_build).

## Watch-outs

- **Race with the daemon:** never run a stage while the daemon's `/status` shows `building: true`, and don't modify the corpus mid-build. The build swaps artifacts atomically; worst case from a race is wasted compute, but a daemon-side rebuild *would* clobber your stage output.
- **Subset semantics:** between stages the index contains only the embedded-so-far paths. That's fine (summaries fallback is worse), but don't declare victory after stage 1.
- **Model identity must match** or reuse breaks: the script resolves the embedder through `prep.services.embedder_factory.create_embedder()` exactly like the daemon. Verified today: `NativeEmbedder`, `native:nomic-embed-text-v1.5`. If the smoke test logs a different model, stop — chunk reuse will no-op and every stage re-embeds everything.
- **`format_context(max_chars=1500)` is a dead path** — nothing in Halbert calls it (docstring-only references). If truncation shows up in responses, the lever is the API `max_chars` (`default_max_chars=12000` in the backend) or the ContextAssembler token budget, not that default.
- **Rollback:** copy the most recent snapshot from `<index_dir>/backups/pre_stage_*/` back over the four artifact files, restart daemon.

## Pointers

- Script: `/Volumes/4TB-BAD/Halbert/scripts/staged_knowledge_embed.py`
- Project index dir: `/Users/ericbintner/.local/share/sourceprep/projects/735a592e-a2da-499b-a614-854a5fc461f5/`
- Corpus / repo root: `/Users/ericbintner/.local/share/halbert/sourceprep/` (`host/`, `knowledge/{linux,macos,bsd,common}/`)
- Build driver (daemon-side reference): `/Volumes/4TB-BAD/HumanAI/CoDRAG/src/prep/services/build_manager.py:267` (`_project_build_worker`)
- Scope resolver (silent-fallback behavior): `/Volumes/4TB-BAD/HumanAI/CoDRAG/src/prep/core/scope_resolver.py`
- Original review doc: `.handoff/HANDOFF-RAG-ARCHITECTURE-REVIEW-2026-08-25.md`
