#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Generate Halbert's own macOS command reference corpus.

LEG-CRIT-01 step 2 — replacement coverage for the quarantined SS64 slice.

`scripts/quarantine_ss64.py` pulls 87 CC BY-NC 4.0 SS64 pages out of the
shippable macOS corpus. Dropping them would leave a hole in exactly the place
Halbert is most often asked questions: "what's the flag for ...". This script
fills that hole with original, Halbert-authored references covering the same 87
commands.

Provenance matters here, so the content is a data table in this file rather
than a scraped artefact: it is written from scratch against the behaviour of
the tools as shipped on macOS 13-15 (BSD userland plus Apple's own utilities),
verifiable by running the commands, and regenerable by anyone reading this
repository. No SS64 text, structure, or ordering was copied.

Output:
    data/macos/support/macos_command_guides.jsonl

Coverage is asserted by the `macos-command-reference` contract in
`config/licensing.yml` and tested in
`halbert_core/tests/test_corpus_license_gate.py`.

Usage:
    python scripts/generate_macos_command_guides.py [--out PATH] [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "macos" / "support" / "macos_command_guides.jsonl"

SOURCE_NAME = "halbert-macos-command-guides"
LICENSE_SPDX = "LicenseRef-Halbert-Corpus-1.0"
AUTHORED_AT = "2026-08-25T00:00:00Z"

# The authored content itself lives next door in `scripts/macos_command_data.py`
# so this file stays readable. Every entry carries: command, tagline, summary,
# synopsis, options, examples, notes, see_also, tags, category.
#   options  : (flag, effect) — the flags that actually come up in support work
#   examples : (command line, what it does)
#   notes    : macOS-specific gotchas, SIP/TCC interactions, BSD-vs-GNU traps
sys.path.insert(0, str(Path(__file__).resolve().parent))
from macos_command_data import COMMANDS  # noqa: E402


def render(entry: Dict[str, Any]) -> str:
    """Render one command entry as the markdown body of a corpus record."""
    cmd = entry["command"]
    parts: List[str] = [f"# {cmd} — {entry['tagline']}", "", entry["summary"].strip(), ""]

    parts.append("## Synopsis")
    parts.append("")
    parts.append("```")
    for line in entry["synopsis"]:
        parts.append(line)
    parts.append("```")
    parts.append("")

    if entry.get("options"):
        parts.append("## Options")
        parts.append("")
        parts.append("| Option | Effect |")
        parts.append("|--------|--------|")
        for flag, effect in entry["options"]:
            parts.append(f"| `{flag}` | {effect} |")
        parts.append("")

    if entry.get("examples"):
        parts.append("## Examples")
        parts.append("")
        parts.append("```bash")
        for line, what in entry["examples"]:
            parts.append(f"# {what}")
            parts.append(line)
            parts.append("")
        while parts and parts[-1] == "":
            parts.pop()
        parts.append("```")
        parts.append("")

    if entry.get("notes"):
        parts.append("## macOS notes")
        parts.append("")
        for note in entry["notes"]:
            parts.append(f"- {note}")
        parts.append("")

    if entry.get("see_also"):
        parts.append("## See also")
        parts.append("")
        parts.append(", ".join(f"`{s}`" for s in entry["see_also"]))
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def build_record(entry: Dict[str, Any]) -> Dict[str, Any]:
    cmd = entry["command"]
    slug = cmd.replace("_", "-").replace(" ", "-")
    tags = ["macos", "command", "terminal", cmd, *entry.get("tags", [])]
    seen: set = set()
    tags = [t for t in tags if not (t in seen or seen.add(t))]

    return {
        "id": f"halbert-macos-cmd-{slug}",
        "url": f"halbert://corpus/macos/command/{slug}",
        "title": f"macOS Command: {cmd}",
        "content": render(entry),
        "source": SOURCE_NAME,
        "category": entry.get("category", "command_reference"),
        "tags": tags,
        "scraped_at": AUTHORED_AT,
        "license_spdx": LICENSE_SPDX,
        "metadata": {
            "platform": "macos",
            "command": cmd,
            "doc_type": "command_reference",
            "synthetic": True,
            "authored_by": "halbert",
            "license_spdx": LICENSE_SPDX,
            "replaces_source": "ss64-macos",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output JSONL path")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the existing output matches what would be generated (CI mode)",
    )
    args = parser.parse_args()

    commands = [e["command"] for e in COMMANDS]
    duplicates = sorted({c for c in commands if commands.count(c) > 1})
    if duplicates:
        print(f"error: duplicate command entries: {', '.join(duplicates)}", file=sys.stderr)
        return 1

    records = [build_record(entry) for entry in sorted(COMMANDS, key=lambda e: e["command"])]
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    out_path = Path(args.out)

    if args.check:
        if not out_path.exists():
            print(f"error: {out_path} does not exist — run without --check", file=sys.stderr)
            return 1
        current = out_path.read_text(encoding="utf-8")
        if current != payload:
            print(f"error: {out_path} is stale — re-run scripts/generate_macos_command_guides.py",
                  file=sys.stderr)
            return 1
        print(f"OK: {out_path} matches generator output ({len(records)} records)")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload, encoding="utf-8")
    total_bytes = len(payload.encode("utf-8"))
    print(f"Wrote {len(records)} Halbert-authored command references -> {out_path}")
    print(f"  {total_bytes:,} bytes, licence {LICENSE_SPDX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
