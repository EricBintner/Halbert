#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Add or verify SPDX license headers on first-party source files (LEG-MIN-01).

Every first-party ``.py``, ``.rs``, ``.ts``, ``.tsx`` and ``.sh`` file tracked
by git under the roots below carries, in its first lines::

    # SPDX-License-Identifier: GPL-3.0-or-later
    # Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors

(``//`` comment style for Rust/TypeScript). A shebang line and a Python
``# -*- coding: ... -*-`` line, if present, stay above the header.

Files derived from third-party code (see ``THIRD_PARTY_HEADERS``) keep their
upstream licence identifier instead of being relabelled GPL. See
documentation/legal/THIRD-PARTY-LICENSES.md §3.5.

Usage::

    python scripts/add_spdx_headers.py            # add missing headers (idempotent)
    python scripts/add_spdx_headers.py --check    # list files missing headers; exit 1 if any
    python scripts/add_spdx_headers.py --list     # list files that WOULD be modified

Only git-tracked files are considered so that files another process is still
writing are never touched. Pass ``--include-untracked`` to widen that.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

LICENSE_ID = "GPL-3.0-or-later"
COPYRIGHT = "Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors"

# Directories (relative to the repo root) whose first-party sources are tagged.
ROOTS: Sequence[str] = (
    "Halbert",
    "halbert_core",
    "scripts",
    "tests",
    "packages",
    "config",
    "packaging",
)

EXTENSIONS: Dict[str, str] = {
    ".py": "#",
    ".sh": "#",
    ".rs": "//",
    ".ts": "//",
    ".tsx": "//",
}

# Path components that mark generated, vendored or third-party trees.
EXCLUDED_DIRS = {
    "node_modules",
    "dist",
    "build",
    "target",
    "gen",
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    "binaries",
}

# Files copied from (or closely derived from) third-party code keep the
# upstream licence so the MIT copyright/permission notice is preserved.
# Keyed by repo-relative POSIX path.
_SHADCN_HEADER = (
    "SPDX-License-Identifier: MIT",
    "SPDX-FileCopyrightText: 2023 shadcn (https://ui.shadcn.com)",
    "SPDX-FileCopyrightText: 2024-2026 Eric Bintner and Halbert Contributors (modifications)",
    "Derived from shadcn/ui, distributed under the MIT License; see THIRD-PARTY-LICENSES.md §3.5.",
)
_FE = "halbert_core/halbert_core/dashboard/frontend/src"
THIRD_PARTY_HEADERS: Dict[str, Tuple[str, ...]] = {
    f"{_FE}/components/ui/badge.tsx": _SHADCN_HEADER,
    f"{_FE}/components/ui/button.tsx": _SHADCN_HEADER,
    f"{_FE}/components/ui/card.tsx": _SHADCN_HEADER,
    f"{_FE}/components/ui/dropdown-menu.tsx": _SHADCN_HEADER,
    f"{_FE}/components/ui/input.tsx": _SHADCN_HEADER,
    f"{_FE}/components/ui/label.tsx": _SHADCN_HEADER,
    f"{_FE}/components/ui/progress.tsx": _SHADCN_HEADER,
    f"{_FE}/components/ui/sheet.tsx": _SHADCN_HEADER,
    f"{_FE}/components/ui/tabs.tsx": _SHADCN_HEADER,
    f"{_FE}/lib/utils.ts": _SHADCN_HEADER,
}

SPDX_TAG = "SPDX-License-Identifier:"
HEAD_SCAN_LINES = 6  # a header must appear within the first N lines


def _git_tracked(roots: Iterable[str]) -> List[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", *roots],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return [REPO_ROOT / p for p in out.decode("utf-8").split("\0") if p]


def _walk(roots: Iterable[str]) -> List[Path]:
    found: List[Path] = []
    for root in roots:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
            for name in filenames:
                found.append(Path(dirpath) / name)
    return found


def candidate_files(include_untracked: bool = False) -> List[Path]:
    """Return first-party source files that must carry a header."""
    paths = _walk(ROOTS) if include_untracked else _git_tracked(ROOTS)
    result: List[Path] = []
    for p in paths:
        if p.suffix not in EXTENSIONS:
            continue
        rel_parts = p.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDED_DIRS for part in rel_parts[:-1]):
            continue
        if not p.is_file():
            continue
        result.append(p)
    return sorted(set(result))


def has_header(text: str) -> bool:
    head = text.splitlines()[:HEAD_SCAN_LINES]
    return any(SPDX_TAG in line for line in head)


def header_lines_for(path: Path) -> Tuple[str, ...]:
    try:
        rel = path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = ""  # outside the repo (e.g. tests): first-party default
    if rel in THIRD_PARTY_HEADERS:
        return THIRD_PARTY_HEADERS[rel]
    return (f"{SPDX_TAG} {LICENSE_ID}", COPYRIGHT)


def _split_preamble(lines: List[str], comment: str) -> int:
    """Index at which the header is inserted (after shebang / coding lines)."""
    idx = 0
    if lines and lines[0].startswith("#!"):
        idx = 1
    if comment == "#" and len(lines) > idx and lines[idx].startswith("# -*- coding"):
        idx += 1
    return idx


def with_header(text: str, path: Path) -> str:
    comment = EXTENSIONS[path.suffix]
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline) if text else []
    idx = _split_preamble(lines, comment)
    header = [f"{comment} {line}" for line in header_lines_for(path)]
    new_lines = lines[:idx] + header + lines[idx:]
    out = newline.join(new_lines)
    if not out.endswith(newline):
        out += newline
    return out


def process(paths: Iterable[Path], *, write: bool) -> List[Path]:
    """Return the files lacking a header; add one when ``write`` is true."""
    missing: List[Path] = []
    for p in paths:
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            # Not a text source file we should touch.
            continue
        if has_header(text):
            continue
        missing.append(p)
        if write:
            p.write_bytes(with_header(text, p).encode("utf-8"))
    return missing


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report files missing a header; exit 1 if any")
    mode.add_argument("--list", action="store_true", help="list files that would be modified, without writing")
    ap.add_argument("--include-untracked", action="store_true", help="also consider files not tracked by git")
    ap.add_argument("paths", nargs="*", help="optional explicit files to process instead of the default roots")
    args = ap.parse_args(argv)

    if args.paths:
        paths = [Path(p).resolve() for p in args.paths]
        paths = [p for p in paths if p.suffix in EXTENSIONS and p.is_file()]
    else:
        paths = candidate_files(include_untracked=args.include_untracked)

    write = not (args.check or args.list)
    missing = process(paths, write=write)

    rel = [p.relative_to(REPO_ROOT).as_posix() for p in missing]
    if args.check:
        if rel:
            print(f"{len(rel)} file(s) missing an SPDX header:")
            for r in rel:
                print(f"  {r}")
            print("\nFix with: python scripts/add_spdx_headers.py")
            return 1
        print(f"OK: all {len(paths)} first-party source files carry an SPDX header.")
        return 0
    if args.list:
        for r in rel:
            print(r)
        print(f"{len(rel)} of {len(paths)} files would be modified.", file=sys.stderr)
        return 0
    print(f"Added SPDX headers to {len(rel)} file(s); {len(paths) - len(rel)} already tagged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
