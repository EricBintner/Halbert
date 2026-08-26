#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Copy the vendored typefaces into each app's public/ directory.

shared-tokens/fonts/ is the one source. Vite serves and copies public/ verbatim,
and it will not reach outside a project root, so each consumer needs its own
copy at build time. Those copies are gitignored and regenerated — they are a
build artefact, not a second source of truth.

Usage::

    python3 scripts/sync_fonts.py            # copy into every consumer
    python3 scripts/sync_fonts.py --check    # fail if any copy is missing/stale
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "shared-tokens" / "fonts"

CONSUMERS = [
    REPO_ROOT / "halbert_core/halbert_core/dashboard/frontend/public/fonts",
    REPO_ROOT / "marketing/web-v7/public/fonts",
    REPO_ROOT / "packages/design-system/public/fonts",
]


def files_of(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def sync(check: bool) -> int:
    if not SOURCE.exists():
        print(f"error: {SOURCE.relative_to(REPO_ROOT)} not found — run vendor_fonts.py first", file=sys.stderr)
        return 2

    expected = [p.relative_to(SOURCE) for p in files_of(SOURCE)]
    stale: list[str] = []

    for target in CONSUMERS:
        rel_target = target.relative_to(REPO_ROOT)
        if check:
            for rel in expected:
                dest = target / rel
                if not dest.exists():
                    stale.append(f"{rel_target}/{rel}: missing")
                elif not filecmp.cmp(SOURCE / rel, dest, shallow=False):
                    stale.append(f"{rel_target}/{rel}: differs from shared-tokens/fonts")
            # A file the source no longer has must not linger in a bundle.
            for existing in files_of(target) if target.exists() else []:
                if existing.relative_to(target) not in expected:
                    stale.append(f"{rel_target}/{existing.relative_to(target)}: orphaned")
            continue

        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(SOURCE, target)
        print(f"  {rel_target}  ({len(expected)} files)")

    if check:
        if stale:
            print("OUT OF DATE — run: python3 scripts/sync_fonts.py")
            for item in stale:
                print(f"  - {item}")
            return 1
        print(f"OK: {len(expected)} font files in sync across {len(CONSUMERS)} consumers.")
        return 0

    print(f"Synced {len(expected)} files to {len(CONSUMERS)} consumers.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args()
    return sync(args.check)


if __name__ == "__main__":
    sys.exit(main())
