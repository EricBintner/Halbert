# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Redact credentials from terminal output before persistence.

Runs before any write of terminal block ``output_head``/``output_tail``
or pasted content into ``messages.content``. A block with
``was_redacted=True`` sets ``terminal_blocks.redacted = 1``.

See plan-b-contracts.md section 2.
"""
from __future__ import annotations

import re
from typing import List, Tuple

_REDACTED = "[redacted]"

#: Each entry is (compiled regex, replacement). Order matters only for
#: readability; patterns are independent and non-overlapping.
PATTERNS: List[Tuple[re.Pattern, str]] = [
    # password=<value>  /  passwd=<value>  (with optional spaces and quotes)
    (
        re.compile(
            r"(?<!\w)(passw(?:or)?d)(\s*=\s*)[\"\']?[^\s\"\']+[\"\']?",
            re.IGNORECASE,
        ),
        r"\1\2[redacted]",
    ),
    # -p<token>  (preceded by start or whitespace; preserve the space.
    # Negative lookahead on lowercase avoids matching flag names like -proxy)
    (
        re.compile(r"(^|\s)(-p)(?![a-z])\S+", re.MULTILINE),
        r"\1\2[redacted]",
    ),
    # Authorization: <scheme> <token>
    (
        re.compile(
            r"(Authorization:)\s+[^\s]+(?:\s+[^\s]+)?",
            re.IGNORECASE,
        ),
        r"\1 [redacted]",
    ),
    # Bearer <token>
    (
        re.compile(r"(Bearer)\s+[^\s]+", re.IGNORECASE),
        r"\1 [redacted]",
    ),
    # AWS access key id
    (
        re.compile(r"AKIA[A-Z0-9]{16}"),
        _REDACTED,
    ),
    # Hugging Face token
    (
        re.compile(r"hf_[a-zA-Z0-9]{20,}"),
        _REDACTED,
    ),
    # GitHub personal access token
    (
        re.compile(r"ghp_[a-zA-Z0-9]{36}"),
        _REDACTED,
    ),
    # PEM private key blocks (DOTALL so . matches newlines)
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        _REDACTED,
    ),
]


def redact(text: str) -> Tuple[str, bool]:
    """Run all redaction patterns on *text*.

    Returns ``(redacted_text, was_redacted)``. ``was_redacted`` is True if
    any pattern matched. Never raises; on internal error returns
    ``(text, False)``.
    """
    try:
        if not isinstance(text, str):
            return (str(text) if text is not None else "", False)
        was_redacted = False
        result = text
        for pattern, replacement in PATTERNS:
            new = pattern.sub(replacement, result)
            if new != result:
                was_redacted = True
                result = new
        return (result, was_redacted)
    except Exception:
        return (text, False)


def redact_bytes(data: bytes) -> Tuple[bytes, bool]:
    """Decode *data* as UTF-8 (errors='replace'), redact, re-encode."""
    try:
        text = data.decode("utf-8", errors="replace")
        result, was_redacted = redact(text)
        return (result.encode("utf-8"), was_redacted)
    except Exception:
        return (data, False)
