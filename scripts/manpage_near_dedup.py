#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Man page near-duplicate analysis and resolution for macOS and FreeBSD overlapping commands.
Calculates word-level Jaccard similarity between macOS and FreeBSD man pages.

Usage:
    python scripts/manpage_near_dedup.py [--macos-file path] [--freebsd-file path] [--threshold 0.85] [--report-file path] [--dry-run]
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def normalize_cmd_title(title: str) -> str:
    """Normalize man page title to command(section) format."""
    if not title:
        return ""
    title = re.sub(r"^FreeBSD:\s*", "", title, flags=re.IGNORECASE).strip()
    return title


def jaccard_similarity(text1: str, text2: str) -> float:
    """Compute word-level Jaccard similarity between two texts."""
    words1 = set(re.findall(r"\b\w+\b", text1.lower()))
    words2 = set(re.findall(r"\b\w+\b", text2.lower()))
    if not words1 or not words2:
        return 0.0
    return len(words1 & words2) / len(words1 | words2)


def analyze_manpage_near_dedup(
    macos_file: Path,
    freebsd_file: Path,
    threshold: float = 0.85,
    dry_run: bool = False
) -> Dict[str, Any]:
    """Analyze and resolve near-duplicate man pages."""
    macos_docs: Dict[str, Dict[str, Any]] = {}
    freebsd_docs: Dict[str, Dict[str, Any]] = {}

    with open(macos_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            doc = json.loads(line)
            cmd = normalize_cmd_title(doc.get("title", ""))
            if cmd:
                macos_docs[cmd] = doc

    with open(freebsd_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            doc = json.loads(line)
            cmd = normalize_cmd_title(doc.get("title", ""))
            if cmd:
                freebsd_docs[cmd] = doc

    overlapping_cmds = sorted(list(set(macos_docs.keys()) & set(freebsd_docs.keys())))

    high_similarity = []
    different_versions = []

    for cmd in overlapping_cmds:
        m_doc = macos_docs[cmd]
        f_doc = freebsd_docs[cmd]

        m_content = m_doc.get("content", "")
        f_content = f_doc.get("content", "")

        sim = jaccard_similarity(m_content, f_content)

        info = {
            "command": cmd,
            "jaccard_similarity": round(sim, 4),
            "macos_doc_id": m_doc.get("id"),
            "macos_char_count": len(m_content),
            "freebsd_doc_id": f_doc.get("id"),
            "freebsd_char_count": len(f_content),
            "longer_version": "macos" if len(m_content) >= len(f_content) else "freebsd",
        }

        if sim >= threshold:
            high_similarity.append(info)
        else:
            different_versions.append(info)

    # Resolution policy:
    # High similarity (>threshold) are marked as near-duplicates.
    # Different versions are retained because FreeBSD and macOS man pages contain
    # platform-specific flags, sysctl names, and implementation behaviors.

    return {
        "macos_total_man_pages": len(macos_docs),
        "freebsd_total_man_pages": len(freebsd_docs),
        "overlapping_command_count": len(overlapping_cmds),
        "threshold": threshold,
        "high_similarity_count": len(high_similarity),
        "distinct_version_count": len(different_versions),
        "high_similarity_details": high_similarity,
        "distinct_version_details": different_versions,
    }


def main():
    parser = argparse.ArgumentParser(description="Man page near-duplicate analyzer")
    parser.add_argument("--macos-file", type=Path, default=Path("data/macos/man-pages/macos_man_pages.jsonl"))
    parser.add_argument("--freebsd-file", type=Path, default=Path("data/bsd/freebsd-man-pages/freebsd_man_pages.jsonl"))
    parser.add_argument("--threshold", type=float, default=0.85, help="Jaccard similarity threshold for near-duplicates")
    parser.add_argument("--report-file", type=Path, default=Path("data/manpage_near_dedup_report.json"))
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    print(f"Analyzing man page near-duplicates between {args.macos_file} and {args.freebsd_file}...")
    results = analyze_manpage_near_dedup(
        args.macos_file.resolve(),
        args.freebsd_file.resolve(),
        threshold=args.threshold,
        dry_run=args.dry_run
    )

    print("\n--- Overlap Analysis Results ---")
    print(f"macOS Man Pages:         {results['macos_total_man_pages']}")
    print(f"FreeBSD Man Pages:       {results['freebsd_total_man_pages']}")
    print(f"Overlapping Commands:    {results['overlapping_command_count']}")
    print(f"Near Duplicates (>{args.threshold*100:.0f}%): {results['high_similarity_count']}")
    print(f"Distinct Versions:       {results['distinct_version_count']}")

    if results["high_similarity_details"]:
        print("\nNear duplicate commands:")
        for item in results["high_similarity_details"]:
            print(f"  - {item['command']} (sim: {item['jaccard_similarity']:.3f}, macOS: {item['macos_char_count']} chars, FreeBSD: {item['freebsd_char_count']} chars)")

    print("\nSample distinct command pairs (retained for platform-specific flags):")
    for item in results["distinct_version_details"][:8]:
        print(f"  - {item['command']}: Jaccard={item['jaccard_similarity']:.3f} (macOS={item['macos_char_count']} chars, FreeBSD={item['freebsd_char_count']} chars)")

    if args.report_file:
        with open(args.report_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nReport saved to {args.report_file}")


if __name__ == "__main__":
    main()
