#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Cross-source exact deduplication for Halbert RAG corpus.
Computes SHA-256 content hashes across all JSONL files, removes duplicates,
and produces a detailed deduplication report.

Usage:
    python scripts/dedup_corpus.py [--data-dir data] [--report-file dedup_report.json] [--dry-run] [--verbose]
"""

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def normalize_content_for_hash(content: str) -> str:
    """Normalize whitespace and lowercase for content hashing."""
    if not content:
        return ""
    # Standardize newlines and trailing whitespace per line
    lines = [line.strip() for line in content.strip().splitlines() if line.strip()]
    return "\n".join(lines)


def hash_content(content: str) -> str:
    """Compute SHA-256 hex digest of normalized content."""
    normalized = normalize_content_for_hash(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def dedup_corpus(
    data_dir: Path,
    dry_run: bool = False,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Run cross-source exact deduplication across all JSONL files in data_dir.
    Returns summary statistics dict.
    """
    seen_hashes: Dict[str, Tuple[str, str, str]] = {}  # hash -> (filepath, doc_id, title)
    duplicates_by_file: Dict[str, int] = defaultdict(int)
    retained_by_file: Dict[str, int] = defaultdict(int)
    duplicate_records: List[Dict[str, Any]] = []

    jsonl_files = sorted(list(data_dir.rglob("*.jsonl")))
    # Exclude staging if present
    jsonl_files = [f for f in jsonl_files if "staging" not in f.parts]

    total_docs = 0
    total_retained = 0
    total_duplicates = 0

    # First pass: identify duplicates and collect clean documents per file
    file_docs_map: Dict[Path, List[Dict[str, Any]]] = {}

    for fpath in jsonl_files:
        clean_docs = []
        rel_path = str(fpath.relative_to(data_dir))

        with open(fpath, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                total_docs += 1
                try:
                    doc = json.loads(line)
                except Exception as e:
                    if verbose:
                        print(f"Error parsing {fpath}:{line_idx}: {e}", file=sys.stderr)
                    continue

                content = doc.get("content", "")
                if not content:
                    continue

                h = hash_content(content)
                doc_id = doc.get("id", f"{fpath.stem}_{line_idx}")
                doc_title = doc.get("title", "Untitled")

                if h in seen_hashes:
                    orig_file, orig_id, orig_title = seen_hashes[h]
                    total_duplicates += 1
                    duplicates_by_file[rel_path] += 1
                    duplicate_records.append({
                        "duplicate_file": rel_path,
                        "duplicate_id": doc_id,
                        "duplicate_title": doc_title,
                        "original_file": orig_file,
                        "original_id": orig_id,
                        "original_title": orig_title,
                    })
                    if verbose:
                        print(f"  [DUP] {rel_path} '{doc_title}' -> matches {orig_file} '{orig_title}'")
                else:
                    seen_hashes[h] = (rel_path, doc_id, doc_title)
                    clean_docs.append(doc)
                    retained_by_file[rel_path] += 1
                    total_retained += 1

        file_docs_map[fpath] = clean_docs

    # Second pass: write back files if not dry run
    files_modified = 0
    if not dry_run:
        for fpath, docs in file_docs_map.items():
            rel_path = str(fpath.relative_to(data_dir))
            if duplicates_by_file.get(rel_path, 0) > 0:
                files_modified += 1
                with open(fpath, "w", encoding="utf-8") as f:
                    for doc in docs:
                        f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    return {
        "total_documents_scanned": total_docs,
        "unique_documents_retained": total_retained,
        "exact_duplicates_removed": total_duplicates,
        "files_scanned": len(jsonl_files),
        "files_modified": files_modified if not dry_run else len([f for f, cnt in duplicates_by_file.items() if cnt > 0]),
        "duplicates_by_file": dict(duplicates_by_file),
        "retained_by_file": dict(retained_by_file),
        "sample_duplicates": duplicate_records[:50],
    }


def main():
    parser = argparse.ArgumentParser(description="Cross-source exact deduplication for RAG corpus")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Path to data directory")
    parser.add_argument("--report-file", type=Path, default=None, help="Save JSON report to file")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without modifying files")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()
    data_dir = args.data_dir.resolve()

    print(f"Running cross-source deduplication in {data_dir} (dry_run={args.dry_run})...")
    stats = dedup_corpus(data_dir, dry_run=args.dry_run, verbose=args.verbose)

    print("\n--- Deduplication Results ---")
    print(f"Total documents scanned:    {stats['total_documents_scanned']}")
    print(f"Unique documents retained:   {stats['unique_documents_retained']}")
    print(f"Exact duplicates removed:    {stats['exact_duplicates_removed']} ({stats['exact_duplicates_removed']/stats['total_documents_scanned']*100:.1f}%)")
    print(f"Files modified:              {stats['files_modified']}")

    print("\nTop sources with duplicates removed:")
    sorted_dups = sorted(stats["duplicates_by_file"].items(), key=lambda x: x[1], reverse=True)
    for src, count in sorted_dups[:10]:
        print(f"  {src}: {count} duplicates removed")

    if args.report_file:
        with open(args.report_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
        print(f"\nSaved report to {args.report_file}")


if __name__ == "__main__":
    main()
