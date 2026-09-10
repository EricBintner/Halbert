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

Redaction here is the registry pass **and** the deterministic pattern
pass (A05-G3, FD-16). This module used to say "registry only", on the
reasoning that terminal output already meets ``streaming.redact``'s
pattern redaction before persistence. That reasoning holds for terminal
output and for nothing else at this seam: an MCP result, a tool's
structured payload and a skill's text all arrive here having met neither
pass. FD-16 supersedes that decision — A05-G3 was confirmed while
A03-G12 (which read the same seam as deliberately registry-only) was
refuted-as-deliberate, and the founder default is to add the pass.
"""
from __future__ import annotations

from typing import Any

from ..ingestion.redaction_registry import get_global_registry

#: Wire-copy bounds. Generous for a display preview, small enough that no
#: tool output — however large the result — can threaten the renderer.
MAX_DISPLAY_CHARS = 1000
MAX_DISPLAY_LINES = 16

#: The budget for one whole PAYLOAD, not one string (A05-G7). The cap
#: was per-string, so a dict of two hundred thousand-character values
#: crossed at two hundred times the display budget -- every value
#: individually "within" it.
MAX_PAYLOAD_CHARS = 16 * 1024

#: What a value becomes once the payload budget is spent.
ELIDED = "[elided: display budget spent]"

#: What the seam shows when its own redaction could not run (A05-G11).
DISPLAY_FAILED_NOTICE = "[withheld: this output could not be checked]"


def _redact_display_text(text: str) -> str:
    """The two passes a display string gets (A05-G3, FD-16).

    Registry first, then patterns -- the order the Tier-2 choke point
    uses, because a pattern pass rewrites part of what it matches and an
    exact-value registry cannot match what has already been partly
    rewritten.
    """
    from ..ingestion.redaction import redact_text

    return redact_text(get_global_registry().redact_text(text), prose=True)


def _cap_text(
    text: str,
    max_chars: int = MAX_DISPLAY_CHARS,
    max_lines: int = MAX_DISPLAY_LINES,
) -> str:
    """Bound ``text`` to the display budget, keeping the tail.

    Lines beyond ``max_lines`` are dropped from the top (the tail is
    what a person reads when a command fails). A body still over
    ``max_chars`` after that drops WHOLE further lines rather than
    slicing one (A05-G5: the cap used to cut mid-line, so a reader could
    not tell a truncated line from a short one -- and a mid-line cut in
    a path or a hash reads as a different value entirely).

    The header names BOTH cuts (A05 bug 5): "[omitted 4 lines]" on a
    body that had also been character-capped said nothing about the
    second cut.

    Untouched text comes back as the same object.
    """
    return _cap_with_facts(text, max_chars, max_lines)[0]


def _cap_with_facts(text: str, max_chars: int, max_lines: int):
    """``(capped_text, facts)`` -- the cap plus what it did (A05-G6)."""
    lines = text.split("\n")
    omitted_lines = 0
    if len(lines) > max_lines:
        omitted_lines = len(lines) - max_lines
        lines = lines[omitted_lines:]
    # Drop whole lines from the top until the body fits, rather than
    # slicing the first surviving one.
    while lines and len("\n".join(lines)) > max_chars and len(lines) > 1:
        lines.pop(0)
        omitted_lines += 1
    body = "\n".join(lines)
    char_capped = False
    if len(body) > max_chars:
        # One line, longer than the whole budget: there is nothing to
        # drop but part of it. Keep the tail and say so.
        body = body[-max_chars:]
        char_capped = True
    facts = {
        "truncated": bool(omitted_lines or char_capped),
        "omitted_lines": omitted_lines,
        "char_capped": char_capped,
        "original_chars": len(text),
        "original_lines": len(text.split("\n")),
    }
    if not facts["truncated"]:
        return text, facts
    parts = []
    if omitted_lines:
        parts.append(f"omitted {omitted_lines} lines")
    if char_capped:
        parts.append(f"cut to the last {max_chars} characters")
    header = "[" + "; ".join(parts) + "]"
    return header + "\n" + body, facts


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
    budget = [MAX_PAYLOAD_CHARS]
    return _verbose(value, max_chars, max_lines, budget)


def _verbose(value: Any, max_chars: int, max_lines: int, budget) -> Any:
    """``verbose_text`` with a shared payload budget (A05-G7).

    The cap used to be per-STRING, so a dict of two hundred
    thousand-character values crossed at two hundred times the display
    budget -- every value individually "within" it. ``budget`` is a
    one-element list threaded through the recursion: what is spent by
    one value is not available to the next, and once it runs out the
    remaining values are elided rather than rendered.
    """
    if isinstance(value, str):
        try:
            redacted = _redact_display_text(value)
        except Exception:
            # A05-G11: the seam fails CLOSED. A redaction that could not
            # run is not evidence that there was nothing to redact.
            return DISPLAY_FAILED_NOTICE
        if budget[0] <= 0:
            return ELIDED
        capped = _cap_text(redacted, max_chars, max_lines)
        budget[0] -= len(capped)
        return capped
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if budget[0] <= 0:
                out[k] = ELIDED
                continue
            out[k] = _verbose(v, max_chars, max_lines, budget)
        return out
    if isinstance(value, (list, tuple)):
        seq = []
        for v in value:
            if budget[0] <= 0:
                seq.append(ELIDED)
                continue
            seq.append(_verbose(v, max_chars, max_lines, budget))
        return seq if isinstance(value, list) else type(value)(seq)
    return value


def verbose_block(value: Any, max_chars: int = MAX_DISPLAY_CHARS,
                  max_lines: int = MAX_DISPLAY_LINES) -> dict:
    """A display block plus the structured facts about its cap (A05-G6).

    A capped block used to carry nothing a consumer could read except
    the header TEXT, so a client that wanted to offer "show the rest"
    had to parse prose. The facts ride beside the text instead.
    """
    try:
        redacted = _redact_display_text(value) if isinstance(value, str) else None
    except Exception:
        return {
            "text": DISPLAY_FAILED_NOTICE, "truncated": False,
            "omitted_lines": 0, "char_capped": False,
            "original_chars": 0, "original_lines": 0,
        }
    if redacted is None:
        return {
            "text": _verbose(value, max_chars, max_lines, [MAX_PAYLOAD_CHARS]),
            "truncated": False, "omitted_lines": 0, "char_capped": False,
            "original_chars": 0, "original_lines": 0,
        }
    text, facts = _cap_with_facts(redacted, max_chars, max_lines)
    return {"text": text, **facts}


def sanitize_chat_input(text: str) -> str:
    """Normalise one chat message before it is stored or prompted (A05-G15).

    Chat input reached the store and ``messages[0]`` as the bytes the
    client sent. Three deterministic rules, the origin's:

    * NFC normalisation, so two spellings of the same word are one
      string in the store, in a search and in a prompt;
    * a NUL byte is refused outright -- it terminates a C string, and
      several things downstream of here are C;
    * C0 controls and DEL are stripped, except tab, newline and carriage
      return, which are legitimate in a typed message.
    """
    import unicodedata

    if "\x00" in text:
        raise ValueError("a chat message may not contain a null byte")
    normalised = unicodedata.normalize("NFC", text)
    return "".join(
        ch for ch in normalised
        if ch in "\t\n\r" or (ord(ch) >= 0x20 and ord(ch) != 0x7F)
    )