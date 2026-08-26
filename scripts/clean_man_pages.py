# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Clean up macOS man page formatting artifacts.

The `man` command outputs backspace-overwrite sequences for bold and underline:
- Bold:   N\bNA\bAM\bME\bE  →  each char doubled with backspace (char + \b + char)
- Underline: _\bc  →  underscore + backspace + char

This script strips those artifacts to produce clean plain text.
"""

import json
import re
import sys
from pathlib import Path


def strip_man_formatting(text: str) -> str:
    """
    Remove man page bold/underline backspace formatting.

    Bold pattern:   char + \b + same_char  →  just the char
    Underline pattern: _ + \b + char       →  just the char
    Any remaining:  char + \b + other_char →  keep other_char (last write wins)
    """
    # Single-pass: replace all c\b sequences at once
    # Pattern: any char + backspace → remove both, the following char wins
    # But we need to handle chains: a\bb\bc → c
    # Use a loop with a global regex that handles all at once
    prev = None
    while prev != text:
        prev = text
        # Remove bold: c\bc → c  (char followed by backspace followed by same char)
        text = re.sub(r'(.)\x08\1', r'\1', text)
        # Remove underline: _\bc → c
        text = re.sub(r'_\x08(.)', r'\1', text)
        # Remove any remaining backspace pair: c\bd → d (last write wins)
        text = re.sub(r'.\x08', '', text)

    # Strip any remaining orphan backspaces
    text = re.sub(r'[\x08\b]+', '', text)
    return text



def clean_jsonl(input_path: Path, output_path: Path = None):
    """Clean a JSONL file of man page documents."""
    if output_path is None:
        output_path = input_path

    total = 0
    cleaned = 0
    docs = []

    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            doc = json.loads(line)
            total += 1
            doc_cleaned = False

            for field in ['content', 'text', 'full_text', 'description']:
                val = doc.get(field)
                if isinstance(val, str) and '\b' in val:
                    doc[field] = strip_man_formatting(val)
                    doc_cleaned = True

            if doc_cleaned:
                cleaned += 1

            docs.append(doc)

    with open(output_path, 'w', encoding='utf-8') as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')

    print(f"Processed {total} documents, cleaned {cleaned} in {input_path}", file=sys.stderr)
    return total, cleaned


if __name__ == '__main__':
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('data/linux/man-pages/man_pages.jsonl')
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else target

    if target.is_dir():
        for p in sorted(target.rglob('*.jsonl')):
            total, cleaned = clean_jsonl(p)
            print(f"Done {p.name}: {cleaned}/{total} documents cleaned")
    else:
        total, cleaned = clean_jsonl(target, output)
        print(f"Done: {cleaned}/{total} documents cleaned")

