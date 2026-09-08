# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Packet 04 C1: TTS quality rules (OpenClaw speech-text.ts patterns).

What a voice reply may speak is not what the screen shows. A code-heavy
reply read aloud is garbage — fences, indentation and identifiers
synthesized as noise — so the spoken copy is adapted before it reaches
the segment path:

  * fenced-block ratio >= 50% of characters -> a deterministic fallback
    line, verbatim. The detail is on screen; the voice says so, the
    same way every time.
  * otherwise fenced blocks are dropped and inline code / markdown
    noise is stripped from the SPOKEN copy only. The on-screen text is
    never touched — this module has no write path to it.

Pure text in, pure text out: no engine, no imports beyond re. The one
model-owned step — spoken summarization of long replies (C2) — arrives
through the ``summarizer`` callable the caller supplies (the C2 seam,
:func:`.speech_summarizer.make_speech_summarizer`); this module never
resolves or calls a model itself. Composition order is fixed: the
code-heavy fallback decision is made FIRST and wins — a code-heavy
reply speaks the fallback line and is never summarized — and the
summarizer, when it fires, summarizes the already-stripped spoken
copy, keeping only a strictly-shorter result.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

#: The line spoken for a code-heavy reply. Deterministic on purpose: the
#: same situation speaks the same words every time, so the voice builds
#: a habit the user can trust instead of a fresh sentence to parse.
DEFAULT_FALLBACK = "I've put the detailed response on screen."

#: At or above this share of characters inside fenced code blocks, the
#: reply is "code-heavy" and the fallback line wins.
_CODE_HEAVY_RATIO = 0.5

# Fenced blocks: ```lang ... ``` (or ~~~ ... ~~~), across lines.
_FENCED_RE = re.compile(r"^(?:```|~~~).*?(?:```|~~~)", re.DOTALL | re.MULTILINE)

# Inline code spans: `...` (not fences — those are already gone by then).
_INLINE_CODE_RE = re.compile(r"`([^`\n]*)`")

# Markdown noise that reads badly aloud.
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.DOTALL)
_ITALIC_RE = re.compile(r"(?<!\*)\*(?=\S)([^*\n]+?)(?<=\S)\*(?!\*)")
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\([^)\n]*\)")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)


def code_fence_ratio(text: str) -> float:
    """Share of the reply's characters that sit inside fenced code blocks.

    0.0 for prose, ~1.0 for a wall of code. The markers count as code:
    they are part of what would be spoken.
    """
    if not text:
        return 0.0
    code_chars = sum(len(m.group(0)) for m in _FENCED_RE.finditer(text))
    return code_chars / len(text)


def is_code_heavy(text: str) -> bool:
    """True when the reply should speak the fallback line instead of
    its own content."""
    return code_fence_ratio(text) >= _CODE_HEAVY_RATIO


def strip_code_noise(text: str) -> str:
    """Remove code and markdown noise from the spoken copy.

    Fenced blocks vanish entirely (their content is screen-only); inline
    code keeps its inner text — `systemctl restart` is speakable, the
    backticks are not. Collapse the whitespace the removals leave behind.

    This is the PROSE path only: it never substitutes the fallback line,
    so a segment that was all code strips to nothing and is dropped
    rather than replaced — the fallback decision belongs to the whole
    reply (``is_code_heavy``), not to one segment.
    """
    text = _FENCED_RE.sub(" ", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    text = _HEADING_RE.sub("", text)
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _BULLET_RE.sub("", text)
    # Blank-line paragraphs stay, runs of blanks collapse to one.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def adapt_for_speech(
    text: str,
    fallback: str = DEFAULT_FALLBACK,
    summarizer: Optional[Callable[[str], str]] = None,
) -> str:
    """The spoken copy of a reply.

    Args:
        text: The reply as it will appear on screen.
        fallback: The deterministic line spoken for a code-heavy reply,
            returned verbatim (no wrapper — a wrapper reads as a
            meta-instruction).
        summarizer: Optional C2 seam (packet 04, :func:
            ``.speech_summarizer.make_speech_summarizer``). When given,
            the STRIPPED spoken copy of a long reply is offered to it
            and a strictly-shorter summary is spoken instead. The
            callable owns the length gate and every failure mode (it
            returns its input unchanged whenever it does not fire), and
            this module defends the composition anyway: a summarizer
            that raises or returns anything longer or empty is ignored.

    Returns:
        The text to synthesize. The on-screen text is untouched.
    """
    if not text:
        return text
    if is_code_heavy(text):
        # The fallback decision is first and final: a code-heavy reply
        # speaks the fallback line and is NEVER summarized (packet 04
        # C2 composition rule).
        return fallback
    spoken = strip_code_noise(text)
    if summarizer is None or not spoken:
        return spoken
    try:
        summary = summarizer(spoken)
    except Exception:
        # Belt and braces: the C2 seam is fail-soft by contract; a
        # foreign callable that is not must not break speech either.
        return spoken
    if not summary or len(summary) >= len(spoken):
        return spoken
    return summary