#!/usr/bin/env python3
"""
Remove empty and near-empty documents (< 50 characters) from JSONL corpus files.
Also deletes stale merged/temporary JSONL artifacts.

Usage:
    python scripts/remove_empty_docs.py [--data-dir data] [--min-chars 50] [--dry-run] [--verbose]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple


STALE_FILES = [
    Path("data/linux/merged/rag_corpus_merged.jsonl"),
    Path("data/linux/merged/combined_all_output_converted.jsonl"),
    Path("data/linux/commands/combined_all_output.jsonl"),
]


def extract_content(doc: dict) -> str:
    """Extract primary text content from any known schema."""
    text = doc.get("content") or doc.get("text") or doc.get("full_text") or ""
    if not text and "explanation" in doc:
        # Schema 5 (topic guide)
        cmds = doc.get("commands", [])
        cmd_str = ""
        if isinstance(cmds, list):
            for c in cmds:
                if isinstance(c, dict):
                    cmd_str += f" {c.get('step', '')} {c.get('cmd', '')}"
                elif isinstance(c, str):
                    cmd_str += f" {c}"
        text = f"{doc.get('explanation', '')} {cmd_str}".strip()
    return text.strip() if isinstance(text, str) else ""


def clean_file(file_path: Path, min_chars: int = 50, dry_run: bool = False, verbose: bool = False) -> Tuple[int, int]:
    """
    Clean empty docs from a single JSONL file.
    Returns (total_docs, removed_docs).
    """
    if not file_path.exists():
        return 0, 0

    kept_docs = []
    total = 0
    removed = 0

    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                doc = json.loads(line)
            except Exception as e:
                if verbose:
                    print(f"[{file_path}:{line_num}] JSON parse error: {e}", file=sys.stderr)
                removed += 1
                continue

            content = extract_content(doc)
            if len(content) < min_chars:
                removed += 1
                if verbose:
                    title = doc.get("title") or doc.get("name") or doc.get("goal") or f"doc_{line_num}"
                    print(f"[{file_path.name}] Removing short doc ({len(content)} chars): '{title}'", file=sys.stderr)
            else:
                kept_docs.append(doc)

    if removed > 0 and not dry_run:
        with open(file_path, "w", encoding="utf-8") as f:
            for doc in kept_docs:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    return total, removed


def remove_stale_files(base_dir: Path, dry_run: bool = False, verbose: bool = False) -> int:
    """Delete known stale merged files and their empty parent directories."""
    deleted = 0
    for rel_path in STALE_FILES:
        target = base_dir.parent / rel_path if base_dir.name == "data" else base_dir / rel_path
        if not target.is_absolute():
            target = Path(os.path.abspath(target))

        if target.exists():
            print(f"{'[DRY RUN] Would delete' if dry_run else 'Deleting'} stale file: {target}")
            if not dry_run:
                target.unlink()
                parent = target.parent
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                    if verbose:
                        print(f"Removed empty directory: {parent}")
            deleted += 1
    return deleted


def main():
    parser = argparse.ArgumentParser(description="Remove empty docs (<50 chars) from JSONL files")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Path to data directory")
    parser.add_argument("--min-chars", type=int, default=50, help="Minimum characters for non-empty doc")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without modifying files")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()
    data_dir = args.data_dir.resolve()

    if not data_dir.exists():
        print(f"Error: data directory {data_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning JSONL files in {data_dir} (min_chars={args.min_chars}, dry_run={args.dry_run})...")

    # Step 1: Remove stale files
    stale_deleted = remove_stale_files(data_dir, dry_run=args.dry_run, verbose=args.verbose)

    # Step 2: Clean remaining JSONL files
    total_scanned = 0
    total_removed = 0
    modified_files = 0

    jsonl_files = sorted(list(data_dir.rglob("*.jsonl")))

    for fpath in jsonl_files:
        # Skip if in staging
        if "staging" in fpath.parts:
            continue
        total, removed = clean_file(fpath, min_chars=args.min_chars, dry_run=args.dry_run, verbose=args.verbose)
        total_scanned += total
        total_removed += removed
        if removed > 0:
            modified_files += 1
            print(f"  {fpath.relative_to(data_dir)}: {total - removed}/{total} retained ({removed} removed)")

    print("\n--- Summary ---")
    print(f"Stale files {'detected' if args.dry_run else 'deleted'}: {stale_deleted}")
    print(f"Total documents scanned: {total_scanned}")
    print(f"Total empty/short documents removed: {total_removed}")
    print(f"Documents retained: {total_scanned - total_removed}")
    print(f"Files modified: {modified_files}")


if __name__ == "__main__":
    main()
