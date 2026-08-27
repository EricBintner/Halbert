#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Staged external CodeIndex builder for Halbert's SourcePrep project.

Why this exists
---------------
SourcePrep's POST /projects/{id}/build only builds the *entire* scope union
in one run (~24h of ONNX embedding compute for the 87MB knowledge corpus).
We want staged, resumable builds that make the host-relevant corpus
(macos + common + host) searchable first, then add linux and bsd.

This script drives SourcePrep's own `CodeIndex.build()` directly, in-process,
outside the daemon — so the artifacts (documents.json, embeddings.npy,
manifest.json, fts.sqlite3) are byte-for-byte what the daemon itself would
write, and `CodeIndex.build()`'s incremental reuse (manifest file_hashes)
means each stage only embeds that stage's new files.

Usage (run with the CoDRAG venv python, which has prep + onnx deps):

    /Volumes/4TB-BAD/HumanAI/CoDRAG/.venv/bin/python scripts/staged_knowledge_embed.py --stage 1
    /Volumes/4TB-BAD/HumanAI/CoDRAG/.venv/bin/python scripts/staged_knowledge_embed.py --stage 2
    /Volumes/4TB-BAD/HumanAI/CoDRAG/.venv/bin/python scripts/staged_knowledge_embed.py --stage 3

    # Smoke test (embeds ONE small file set; verify before committing ~hours):
    .../python scripts/staged_knowledge_embed.py --paths knowledge/common --yes-i-know-its-not-staged

Cumulative inclusion semantics (IMPORTANT)
------------------------------------------
`CodeIndex.build(included_paths=[...])` makes the index contain EXACTLY the
listed paths' files — files not listed are dropped from documents.json. So
each stage's list is the *cumulative union* of everything embedded so far;
reuse of prior stages' chunks is free (unchanged file_hash → no re-embed).

    stage 1: host, knowledge/macos, knowledge/common   (~53M)
    stage 2: stage 1 + knowledge/linux                  (+30M)
    stage 3: stage 2 + knowledge/bsd                    (+4M)  = full corpus

Daemon interplay
----------------
The daemon caches the CodeIndex in memory. After each stage, restart the
daemon (or wait until all stages finish and restart once). Verify with:
    curl -s localhost:8400/projects/<PID>/status | jq '.data.index'
The index `source` should flip from "knowledge" (summaries-only fallback)
to the real CodeIndex with thousands of chunks.

Do NOT run a stage while the daemon is building or the corpus is being
modified — build() swaps artifacts atomically, so the loser of a write race
is just wasted compute, but a daemon rebuild mid-stage would clobber the
stage output.

Config parity (must match the daemon's build for model/reuse compatibility):
- include/exclude globs, max_file_bytes copied from the project config
  (sourceprep_template.yml / GET /projects/<PID>)
- use_gitignore=False (project config)
- embedder resolved via prep's own embedder_factory so the manifest `model`
  string matches the daemon's manifest `model` value — required for the
  incremental-reuse path (prev_model == cur_model) to ever trigger.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# SourcePrep source tree (CoDRAG repo). Its .venv provides the deps.
PREP_SRC = Path("/Volumes/4TB-BAD/HumanAI/CoDRAG/src")
if str(PREP_SRC) not in sys.path:
    sys.path.insert(0, str(PREP_SRC))

REPO_ROOT = Path("/Users/ericbintner/.local/share/halbert/sourceprep")
INDEX_DIR = Path(
    "/Users/ericbintner/.local/share/sourceprep/projects/"
    "735a592e-a2da-499b-a614-854a5fc461f5"
)

# From the project config (sourceprep_template.yml). Keep in sync.
INCLUDE_GLOBS = ["host/**/*", "knowledge/**/*.md"]
EXCLUDE_GLOBS = [
    "**/ssl/**", "**/letsencrypt/**", "**/shadow", "**/gshadow",
    "**/*.key", "**/*.pem",
]
MAX_FILE_BYTES = 500_000
HARD_LIMIT_BYTES = 100_000_000

# Cumulative stage definitions.
STAGES = {
    1: ["host", "knowledge/macos", "knowledge/common"],
    2: ["host", "knowledge/macos", "knowledge/common", "knowledge/linux"],
    3: ["host", "knowledge/macos", "knowledge/common", "knowledge/linux",
        "knowledge/bsd"],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("staged_embed")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stage", type=int, choices=sorted(STAGES),
                    help="Cumulative stage to build (1=macos+common+host, "
                         "2=+linux, 3=+bsd)")
    ap.add_argument("--paths", nargs="+",
                    help="Explicit included_paths override (smoke test).")
    ap.add_argument("--yes-i-know-its-not-staged", action="store_true",
                    help="Required with --paths so a partial index is never "
                         "written by accident.")
    ap.add_argument("--index-dir", default=str(INDEX_DIR))
    ap.add_argument("--repo-root", default=str(REPO_ROOT))
    args = ap.parse_args()

    if args.paths and not args.yes_i_know_its_not_staged:
        ap.error("--paths requires --yes-i-know-its-not-staged")
    if not args.paths and not args.stage:
        ap.error("pass --stage N (or --paths for a smoke test)")

    included_paths = args.paths or STAGES[args.stage]
    index_dir = Path(args.index_dir)
    repo_root = Path(args.repo_root)

    logger.info("included_paths (%d): %s", len(included_paths), included_paths)
    logger.info("index_dir: %s", index_dir)
    logger.info("repo_root: %s", repo_root)

    # Snapshot the current artifacts before we touch them (cheap; the
    # existing ones are an empty index, but never write blind).
    backup_dir = index_dir / "backups" / time.strftime("pre_stage_%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in ("documents.json", "embeddings.npy", "manifest.json",
                 "fts.sqlite3"):
        src = index_dir / name
        if src.exists():
            dst = backup_dir / name
            dst.write_bytes(src.read_bytes())
    logger.info("snapshot: %s", backup_dir)

    from prep.core.index import CodeIndex
    from prep.services.embedder_factory import create_embedder

    embedder = create_embedder()  # same resolution chain as the daemon
    logger.info("embedder model: %s", getattr(embedder, "model", "unknown"))

    idx = CodeIndex(index_dir=index_dir, embedder=embedder)

    t0 = time.monotonic()
    n_files = [0]

    def _progress(file_path: str, current: int, total: int) -> None:
        elapsed = time.monotonic() - t0
        rate = current / elapsed if elapsed > 0 else 0
        eta_s = (total - current) / rate if rate > 0 else float("inf")
        # Log every 10 files (and the first) — throughput + ETA for whoever
        # is babysitting the run.
        if current == 1 or current % 10 == 0 or current == total:
            logger.info(
                "progress: %d/%d files (%.1f files/min, ETA %.1f min) — %s",
                current, total, rate * 60, eta_s / 60, file_path,
            )
        n_files[0] = current

    meta = idx.build(
        repo_root=repo_root,
        include_globs=INCLUDE_GLOBS,
        exclude_globs=EXCLUDE_GLOBS,
        max_file_bytes=MAX_FILE_BYTES,
        hard_limit_bytes=HARD_LIMIT_BYTES,
        use_gitignore=False,
        included_paths=included_paths,
        progress_callback=_progress,
    )

    elapsed = time.monotonic() - t0
    logger.info("build finished in %.1f min", elapsed / 60)
    logger.info("build meta: %s", json.dumps(meta, indent=2, default=str))

    # Post-build sanity: index must be loadable and non-empty.
    stats = idx.stats()
    logger.info("index stats: %s", json.dumps(stats, indent=2, default=str))
    if not stats.get("loaded"):
        logger.error("index did not load after build — do NOT restart the "
                     "daemon; restore the snapshot in %s", backup_dir)
        return 1
    if (stats.get("build") or {}).get("chunks_embedded", 0) == 0 \
            and (stats.get("build") or {}).get("chunks_reused", 0) == 0:
        logger.error("no chunks embedded or reused — check included_paths")
        return 1

    logger.info("OK. Restart the SourcePrep daemon for it to pick this up, "
                "then run the acceptance queries from the handoff doc.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
