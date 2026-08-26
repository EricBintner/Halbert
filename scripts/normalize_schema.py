#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Normalize all JSONL document schemas across the corpus into a single unified schema:
{
    "id": str,
    "url": str,
    "title": str,
    "content": str,
    "source": str,
    "category": str,
    "tags": list[str],
    "scraped_at": str (ISO8601),
    "metadata": dict
}

Usage:
    python scripts/normalize_schema.py [--data-dir data] [--dry-run] [--verbose]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_TIMESTAMP = "2026-08-23T00:00:00Z"


def slugify(text: str) -> str:
    """Sanitize string for identifiers, preserving symbols as words."""
    if not text:
        return "unnamed"
    text = str(text).lower()
    symbol_map = {
        "++": "_plusplus",
        "+": "_plus",
        "[": "_sym_lbracket",
        "]": "_sym_rbracket",
        "(": "_sym_lparen",
        ")": "_sym_rparen",
        "{": "_sym_lbrace",
        "}": "_sym_rbrace",
        "$": "_sym_dollar",
        "%": "_sym_percent",
        ",": "_sym_comma",
        "!": "_sym_exclamation",
        "^": "_sym_caret",
        "~": "_sym_tilde",
        "&": "_sym_amp",
        "=": "_sym_eq",
        ":": "_sym_colon",
        ";": "_sym_semicolon",
        "?": "_sym_question",
        "*": "_sym_star",
    }

    for sym, word in symbol_map.items():
        text = text.replace(sym, word)
    text = re.sub(r"[^\w\-_.]", "_", text)
    slug = re.sub(r"_+", "_", text).strip("_")
    return slug or "unnamed"



def normalize_record(doc: Dict[str, Any], file_path: Path, index: int) -> Dict[str, Any]:
    """Normalize a raw document dictionary into the unified schema."""
    metadata = doc.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {"original_metadata": metadata} if metadata else {}

    # Extract content
    content = doc.get("content") or doc.get("text") or doc.get("full_text") or ""
    if not content and "explanation" in doc:
        cmds = doc.get("commands", [])
        cmd_parts = []
        if isinstance(cmds, list):
            for c in cmds:
                if isinstance(c, dict):
                    cmd_parts.append(f"- {c.get('step', '')}: `{c.get('cmd', '')}`")
                elif isinstance(c, str):
                    cmd_parts.append(f"- `{c}`")
        content = f"{doc.get('explanation', '')}\n\n" + "\n".join(cmd_parts)
    content = str(content).strip()

    # Extract title
    title = (
        doc.get("title")
        or doc.get("name")
        or doc.get("goal")
        or metadata.get("man_page")
        or metadata.get("title")
    )
    if not title and content:
        # Check first line of content for header
        first_line = content.splitlines()[0].strip()
        first_line = re.sub(r"^#+\s*", "", first_line).strip()
        if 3 < len(first_line) < 120 and not first_line.startswith("http"):
            title = first_line

    if not title:
        title = file_path.stem.replace("_", " ").title()

    title = str(title).strip()


    # Extract source
    source = (
        doc.get("source")
        or metadata.get("source_type")
        or metadata.get("source")
        or file_path.parent.name
    )
    source = str(source).strip()

    # Extract category
    category = (
        doc.get("category")
        or metadata.get("category")
        or file_path.parent.name
    )
    category = str(category).strip()

    # Extract tags
    tags = doc.get("tags") or metadata.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    elif not isinstance(tags, list):
        tags = [str(tags)]
    tags = [str(t) for t in tags if t]
    if not tags:
        tags = [slugify(source), slugify(category)]

    # Extract url
    url = (
        doc.get("url")
        or metadata.get("url")
        or ""
    )
    if not url:
        if "man" in source or "man" in file_path.name:
            sec = str(metadata.get("section", "1"))
            url = f"x-man-page://{sec}/{slugify(title)}"
        else:
            url = ""

    # Extract scraped_at
    scraped_at = (
        doc.get("scraped_at")
        or metadata.get("scraped_at")
        or metadata.get("created_at")
        or DEFAULT_TIMESTAMP
    )

    # Extract id
    doc_id = doc.get("id") or metadata.get("id")
    if not doc_id:
        doc_id = f"{slugify(source)}_{slugify(title)}_{index}"

    return {
        "id": str(doc_id),
        "url": str(url),
        "title": str(title),
        "content": content,
        "source": str(source),
        "category": str(category),
        "tags": tags,
        "scraped_at": str(scraped_at),
        "metadata": metadata,
    }


def normalize_file(file_path: Path, dry_run: bool = False, verbose: bool = False) -> Tuple[int, int]:
    """
    Normalize a JSONL file.
    Returns (total_docs, converted_docs).
    """
    normalized_docs = []
    total = 0
    converted = 0

    canonical_keys = {"category", "content", "id", "metadata", "scraped_at", "source", "tags", "title", "url"}

    with open(file_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            doc = json.loads(line)
            is_canonical = set(doc.keys()) == canonical_keys

            norm = normalize_record(doc, file_path, idx)
            if not is_canonical:
                converted += 1
            normalized_docs.append(norm)

    if not dry_run:
        with open(file_path, "w", encoding="utf-8") as f:
            for doc in normalized_docs:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    return total, converted


def main():
    parser = argparse.ArgumentParser(description="Normalize JSONL schemas across corpus")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Path to data directory")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing files")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()
    data_dir = args.data_dir.resolve()

    print(f"Normalizing JSONL schemas in {data_dir} (dry_run={args.dry_run})...")

    total_scanned = 0
    total_converted = 0
    modified_files = 0

    jsonl_files = sorted(list(data_dir.rglob("*.jsonl")))

    for fpath in jsonl_files:
        if "staging" in fpath.parts:
            continue
        total, converted = normalize_file(fpath, dry_run=args.dry_run, verbose=args.verbose)
        total_scanned += total
        total_converted += converted
        if converted > 0:
            modified_files += 1
            print(f"  {fpath.relative_to(data_dir)}: {converted}/{total} records normalized")

    print("\n--- Summary ---")
    print(f"Total documents: {total_scanned}")
    print(f"Records normalized from legacy schemas: {total_converted}")
    print(f"Files modified: {modified_files}")


if __name__ == "__main__":
    main()
