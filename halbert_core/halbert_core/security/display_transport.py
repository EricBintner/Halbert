# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Display-transport redact+cap for UI-bound tool text (Packet 05 addendum).

Hermes ships tool text to its UI through one seam — ``_verbose_text`` →
forced redaction → hard cap (1000 chars / 16 lines, tail-kept with an
``[omitted N lines]`` header). Full output stays in the agent context and
the store; only the redacted, capped preview crosses the wire, and the
cap is an OOM defense, not just privacy: an unbounded output blew up
their render tree and killed the TUI parent (#34095).

Halbert's dominant equivalent seam is the ``tool_start``/``tool_complete``
SSE event factories in ``agents.events`` — every live tool emission to the
Tauri frontend is built by them, so wiring the helper there covers every
producer. Other emission paths (terminal stream events, SQLite timeline
loads, job status lines) are covered by their own mechanisms or were
audited and recorded with the packet; see the factories' docstrings and
the packet status rows.

Redaction here is the *registry pass only* (Phase A's exact-value layer
over acknowledged-egress values) — not the full ``ingestion.redaction``
pattern set. Terminal output already passes through
``streaming.redact``'s pattern redaction before persistence; applying the
registry at the wire adds the learned layer without re-deciding pattern
scope for every tool display.
"""
from __future__ import annotations

from typing import Any

from ..ingestion.redaction_registry import get_global_registry

#: Wire-copy bounds. Generous for a display preview, small enough that no
#: tool output — however large the result — can threaten the renderer.
MAX_DISPLAY_CHARS = 1000
MAX_DISPLAY_LINES = 16


def _cap_text(
    text: str,
    max_chars: int = MAX_DISPLAY_CHARS,
    max_lines: int = MAX_DISPLAY_LINES,
) -> str:
    """Bound ``text`` to the display budget, keeping the tail.

    Lines beyond ``max_lines`` are dropped from the top and reported in an
    ``[omitted N lines]`` header (the tail is the part a user reads when a
    command fails); a body still over ``max_chars`` after that is cut from
    the front and reported as ``[output truncated]``. Untouched text
    comes back as the same object.
    """
    lines = text.split("\n")
    omitted_lines = 0
    if len(lines) > max_lines:
        omitted_lines = len(lines) - max_lines
        lines = lines[omitted_lines:]
    body = "\n".join(lines)
    if len(body) > max_chars:
        body = body[-max_chars:]
    if not omitted_lines and body == text:
        return text
    header = (
        f"[omitted {omitted_lines} lines]" if omitted_lines else "[output truncated]"
    )
    return header + "\n" + body


def verbose_text(
    value: Any,
    max_chars: int = MAX_DISPLAY_CHARS,
    max_lines: int = MAX_DISPLAY_LINES,
) -> Any:
    """The display copy of a tool arg/result: registry-redacted, capped.

    Strings get the registry pass (exact forms of egress-acked values
    become ``<secret>``) then the cap; dicts and lists recurse into their
    values so nested payloads keep their shape with bounded strings;
    other scalars (numbers, booleans, None) cross as-is — they are not
    credentials and not an OOM vector. Returns a new structure; the input
    is never mutated (the agent context and the store keep full fidelity).
    """
    if isinstance(value, str):
        redacted = get_global_registry().redact_text(value)
        return _cap_text(redacted, max_chars, max_lines)
    if isinstance(value, dict):
        return {
            k: verbose_text(v, max_chars, max_lines)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        seq = [verbose_text(v, max_chars, max_lines) for v in value]
        return seq if isinstance(value, list) else type(value)(seq)
    return value