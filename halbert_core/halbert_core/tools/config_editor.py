# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Config-edit block parsing and application.

Phase 4: Ported from chat.py to make config-edit functionality available
on the agent path without depending on chat.py.

Provides:
- parse_edit_blocks(response) — parse SEARCH/REPLACE blocks from LLM output
- find_best_match(search, content) — fuzzy match search text in file content
- apply_edit_blocks(content, edit_blocks) — apply parsed blocks to file content
- extract_summary(response) — extract summary from config-edit response
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def parse_edit_blocks(response: str) -> List[dict]:
    """Parse SEARCH/REPLACE edit blocks from AI response.

    Supports the standard <<<<<<< SEARCH / ======= / >>>>>>> REPLACE format
    with several fallback patterns for LLM output variations.
    """
    blocks = []

    response = response.replace("\r\n", "\n").replace("\r", "\n")

    patterns = [
        # Standard format with ======= separator
        r'<<<<<<< SEARCH\s*\n([\s\S]*?)\n=======\s*\n([\s\S]*?)\n>>>>>>> REPLACE',
        # With potential extra text on marker lines
        r'<{7}\s*SEARCH[^\n]*\n([\s\S]*?)\n={7}[^\n]*\n([\s\S]*?)\n>{7}\s*REPLACE',
        # Simpler markers (just the arrows)
        r'<<<<<<< SEARCH\n(.*?)(?:\n)?=======\n(.*?)(?:\n)?>>>>>>> REPLACE',
        # FALLBACK: Malformed blocks without ======= separator
        r'<<<<<<< SEARCH\s*\n([\s\S]*?)\n>>>>>>> REPLACE',
    ]

    for pattern_idx, pattern in enumerate(patterns):
        matches = list(re.finditer(pattern, response, re.MULTILINE | re.DOTALL))
        if matches:
            for match in matches:
                if pattern_idx < 3:
                    search_text = match.group(1).strip()
                    replace_text = match.group(2).strip()
                else:
                    content = match.group(1).strip()
                    logger.warning(
                        f"Malformed edit block (no ======= separator): "
                        f"{content[:100]}..."
                    )
                    continue

                if search_text:
                    blocks.append({"search": search_text, "replace": replace_text})
            if blocks:
                break

    if not blocks:
        logger.debug(
            f"No edit blocks found in response (len={len(response)})"
        )
        if "<<<<<<< SEARCH" in response:
            logger.warning("Response contains SEARCH marker but regex didn't match")
    else:
        logger.debug(f"Found {len(blocks)} edit blocks")

    return blocks


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for fuzzy matching."""
    lines = [re.sub(r"[ \t]+", " ", line.strip()) for line in text.split("\n")]
    return "\n".join(lines)


def find_best_match(search: str, content: str) -> Optional[Tuple[int, int]]:
    """Find the best matching location for search text in content.

    Uses fuzzy matching to handle whitespace differences.
    Returns (start, end) indices or None if no match found.
    """
    import difflib

    if search in content:
        start = content.index(search)
        return (start, start + len(search))

    search_norm = normalize_whitespace(search)
    content_norm = normalize_whitespace(content)

    if search_norm in content_norm:
        norm_start = content_norm.index(search_norm)
        search_lines = search_norm.count("\n") + 1
        content_lines = content.split("\n")

        line_start = content_norm[:norm_start].count("\n")
        line_end = line_start + search_lines

        original_start = sum(len(line) + 1 for line in content_lines[:line_start])
        original_end = sum(len(line) + 1 for line in content_lines[:line_end])

        if original_end > len(content):
            original_end = len(content)

        return (original_start, original_end)

    search_lines = search.strip().split("\n")
    content_lines = content.split("\n")

    if len(search_lines) == 0:
        return None

    matcher = difflib.SequenceMatcher(
        None,
        [normalize_whitespace(l) for l in content_lines],
        [normalize_whitespace(l) for l in search_lines],
    )

    blocks = matcher.get_matching_blocks()
    total_matched = sum(b.size for b in blocks)
    if total_matched >= len(search_lines) * 0.7:
        for block in blocks:
            if block.size >= len(search_lines) * 0.5:
                start_line = block.a
                end_line = start_line + len(search_lines)

                original_start = sum(len(line) + 1 for line in content_lines[:start_line])
                original_end = sum(len(line) + 1 for line in content_lines[:end_line])

                if original_end > len(content):
                    original_end = len(content)

                return (original_start, original_end)

    return None


def apply_edit_blocks(
    content: str, edit_blocks: List[dict]
) -> Tuple[str, bool, str]:
    """Apply edit blocks to file content with fuzzy matching.

    Args:
        content: Original file content
        edit_blocks: List of {search: str, replace: str} dicts

    Returns:
        Tuple of (new_content, success, error_message)
    """
    if not edit_blocks:
        return content, False, "No edit blocks to apply"

    new_content = content
    applied_count = 0

    for block in edit_blocks:
        search = block.get("search", "").strip()
        replace = block.get("replace", "")

        if not search:
            continue

        if search in new_content:
            new_content = new_content.replace(search, replace, 1)
            applied_count += 1
            logger.debug(
                f"Applied exact edit: {len(search)} chars -> {len(replace)} chars"
            )
        else:
            match = find_best_match(search, new_content)
            if match:
                start, end = match
                new_content = new_content[:start] + replace + new_content[end:]
                applied_count += 1
                logger.debug(
                    f"Applied fuzzy edit: {end - start} chars -> {len(replace)} chars"
                )
            else:
                logger.warning(
                    f"Could not find search text (even fuzzy): {search[:50]}..."
                )

    if applied_count == 0:
        return content, False, "No edit blocks could be matched to file content"

    return new_content, True, f"Applied {applied_count} of {len(edit_blocks)} edit blocks"


def extract_summary(response: str) -> str:
    """Extract a brief summary from a config-edit AI response.

    The summary is the text after the last edit block, or the first
    paragraph if no edit blocks are present.
    """
    blocks = parse_edit_blocks(response)
    if blocks:
        # Find text after the last >>>>>>> REPLACE
        last_marker = response.rfind(">>>>>>> REPLACE")
        if last_marker != -1:
            after = response[last_marker + len(">>>>>>> REPLACE"):].strip()
            if after:
                return after

    # Fallback: first paragraph
    paragraphs = response.strip().split("\n\n")
    return paragraphs[0] if paragraphs else response.strip()
