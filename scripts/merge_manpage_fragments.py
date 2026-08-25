#!/usr/bin/env python3
"""
Merge fragmented Linux man pages.

The Linux man page extractor split each man page into many tiny fragments
by section (NAME, SYNOPSIS, DESCRIPTION, etc.). This script merges them
back into one document per man page, ordered by the fragment number in
the ID.

Before: 4,368 fragments of 142 unique man pages
After:  142 whole man pages

Usage:
    .venv/bin/python scripts/merge_manpage_fragments.py
    .venv/bin/python scripts/merge_manpage_fragments.py --dry-run
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def fragment_num(doc_id: str) -> int:
    """Extract the numeric fragment suffix from an ID like 'man_brew_1_42'."""
    m = re.search(r"_(\d+)$", doc_id)
    return int(m.group(1)) if m else 0


def merge_fragments(input_path: Path, output_path: Path, dry_run: bool = False) -> dict:
    """
    Merge fragmented man pages in a JSONL file.

    Groups documents by title, sorts fragments by their numeric suffix,
    concatenates content, and keeps the first fragment's metadata.
    """
    with open(input_path) as f:
        docs = [json.loads(line) for line in f]

    # Group by title
    groups: dict[str, list] = defaultdict(list)
    for doc in docs:
        groups[doc["title"]].append(doc)

    merged_docs = []
    stats = {
        "input_path": str(input_path),
        "fragments_in": len(docs),
        "unique_titles": len(groups),
        "merged_out": 0,
    }

    for title, fragments in groups.items():
        # Sort fragments by their numeric suffix to reconstruct original order
        fragments_sorted = sorted(fragments, key=lambda d: fragment_num(d["id"]))

        # Concatenate content with double newlines between fragments
        content_parts = []
        for frag in fragments_sorted:
            c = frag["content"].strip()
            if c:
                content_parts.append(c)
        merged_content = "\n\n".join(content_parts)

        # Use the first fragment as the base, update content and ID
        base = fragments_sorted[0].copy()
        # Clean up the ID: remove the fragment suffix
        base["id"] = re.sub(r"_\d+$", "", base["id"])
        base["content"] = merged_content
        base["metadata"] = base.get("metadata", {})
        base["metadata"]["merged_fragments"] = len(fragments)

        merged_docs.append(base)

    # Sort merged docs by title for deterministic output
    merged_docs.sort(key=lambda d: d["title"])

    stats["merged_out"] = len(merged_docs)

    if dry_run:
        print(f"[DRY RUN] {input_path}")
        print(f"  Fragments in:  {stats['fragments_in']}")
        print(f"  Unique titles: {stats['unique_titles']}")
        print(f"  Merged out:    {stats['merged_out']}")
        # Show size distribution
        sizes = sorted([len(d["content"]) for d in merged_docs])
        print(f"  Content sizes: min={sizes[0]}, median={sizes[len(sizes)//2]}, max={sizes[-1]}")
        return stats

    # Write merged output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for doc in merged_docs:
            f.write(json.dumps(doc) + "\n")

    print(f"[OK] {input_path} -> {output_path}")
    print(f"  Fragments in:  {stats['fragments_in']}")
    print(f"  Merged out:    {stats['merged_out']}")
    return stats


def main():
    dry_run = "--dry-run" in sys.argv

    base = Path("data")

    # Only Linux man pages have the fragmentation issue
    # macOS man pages were verified clean (5,280 docs, 0 duplicate titles)
    targets = [
        (base / "linux/man-pages/man_pages.jsonl"),
    ]

    all_stats = []
    for input_path in targets:
        if not input_path.exists():
            print(f"[SKIP] {input_path} does not exist")
            continue
        stats = merge_fragments(input_path, input_path, dry_run=dry_run)
        all_stats.append(stats)

    print()
    total_in = sum(s["fragments_in"] for s in all_stats)
    total_out = sum(s["merged_out"] for s in all_stats)
    print(f"Total: {total_in} fragments -> {total_out} merged man pages")

    if dry_run:
        print("\n[DRY RUN] No files were modified. Run without --dry-run to apply.")


if __name__ == "__main__":
    main()
