#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Track Tailwind palette classes that bypass the Halbert theme.

A class like ``bg-slate-800`` is a literal colour from Tailwind's stock palette.
It ignores ``shared-tokens/tokens.css`` entirely, so it does not follow the
Olivetti identity, does not swap with the theme, and is not covered by the
contrast gate. On the bone canvas a stray dark neutral reads as a hole in the
page.

There are too many of these to fix in one pass without real regression risk, so
this script is a **ratchet** rather than a wall: it records a per-file baseline
and fails only when a file gains new violations. Existing debt is allowed to
sit; it is not allowed to grow.

Usage::

    python3 scripts/check_literal_colors.py            # report
    python3 scripts/check_literal_colors.py --check    # fail if any file grew
    python3 scripts/check_literal_colors.py --baseline # re-record after fixes
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / ".literal-colors-baseline.json"

SCAN_ROOTS = ["halbert_core/halbert_core/dashboard/frontend/src"]

FAMILIES = (
    "slate|zinc|gray|neutral|stone|red|orange|amber|yellow|lime|green|emerald|"
    "teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose"
)
PROPS = "bg|text|border|from|to|via|ring|divide|fill|stroke|outline|shadow|accent|caret|decoration"

PATTERN = re.compile(rf"\b(?:{PROPS})-(?:{FAMILIES})-\d{{2,3}}\b")

# Dark neutral backgrounds are called out separately: they are the ones that
# read as a hole punched in the bone canvas rather than merely off-brand.
CLASHING = re.compile(rf"\bbg-(?:slate|zinc|gray|neutral|stone)-(?:[789]\d\d)\b")


def scan() -> tuple[dict[str, int], dict[str, int], Counter]:
    counts: dict[str, int] = {}
    clashes: dict[str, int] = {}
    by_class: Counter = Counter()

    files = subprocess.run(
        ["git", "ls-files", "--", *[f"{root}/**/*.tsx" for root in SCAN_ROOTS],
         *[f"{root}/**/*.ts" for root in SCAN_ROOTS]],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()

    for rel in files:
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        hits = PATTERN.findall(text)
        if hits:
            counts[rel] = len(hits)
            by_class.update(hits)
        clash = CLASHING.findall(text)
        if clash:
            clashes[rel] = len(clash)

    return counts, clashes, by_class


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if any file gained violations")
    parser.add_argument("--baseline", action="store_true", help="re-record the baseline")
    args = parser.parse_args()

    counts, clashes, by_class = scan()
    total = sum(counts.values())
    clash_total = sum(clashes.values())

    if args.baseline:
        BASELINE.write_text(json.dumps({"files": counts, "total": total}, indent=2, sort_keys=True) + "\n")
        print(f"Recorded baseline: {total} literal classes across {len(counts)} files.")
        return 0

    if args.check:
        if not BASELINE.exists():
            print("No baseline recorded. Run with --baseline first.", file=sys.stderr)
            return 2
        recorded = json.loads(BASELINE.read_text())["files"]
        grew = [
            (rel, recorded.get(rel, 0), n)
            for rel, n in sorted(counts.items())
            if n > recorded.get(rel, 0)
        ]
        if grew:
            print("FAILED — files gained literal palette classes:")
            for rel, was, now in grew:
                print(f"  {rel}: {was} -> {now}")
            print("\nUse the theme instead: bg-background, text-foreground, text-muted-foreground,")
            print("border-border, and the semantic text-success / -warning / -error / -info.")
            return 1
        improved = sum(recorded.get(r, 0) - n for r, n in counts.items() if n < recorded.get(r, 0))
        print(f"OK: {total} literal classes, none gained." + (f" ({improved} fixed since baseline.)" if improved else ""))
        return 0

    print(f"Literal Tailwind palette classes: {total} across {len(counts)} files")
    print(f"Of those, {clash_total} are dark neutral backgrounds that clash on the bone canvas.\n")
    if clashes:
        print("Clashing dark backgrounds, worst first:")
        for rel, n in sorted(clashes.items(), key=lambda kv: -kv[1])[:12]:
            print(f"  {n:4d}  {rel}")
    print("\nHeaviest files overall:")
    for rel, n in sorted(counts.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {n:4d}  {rel}")
    print("\nMost common classes:")
    for cls, n in by_class.most_common(10):
        print(f"  {n:4d}  {cls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
