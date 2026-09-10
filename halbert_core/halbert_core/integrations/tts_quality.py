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
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

#: The line spoken for a code-heavy reply. Deterministic on purpose: the
#: same situation speaks the same words every time, so the voice builds
#: a habit the user can trust instead of a fresh sentence to parse.
DEFAULT_FALLBACK = "I've put the detailed response on screen."

#: At or above this share of characters inside fenced code blocks, the
#: reply is "code-heavy" and the fallback line wins.
_CODE_HEAVY_RATIO = 0.5

#: Reasoning and control tokens a model emits that are not words
#: (A10-G1). A satellite read "<think>" and the reasoning inside it
#: aloud, and a tool-call marker with its JSON. Deterministic and closed:
#: a shape, never a judgement about content.
_REASONING_BLOCKS = (
    ("<think>", "</think>"),
    ("<thinking>", "</thinking>"),
    ("<reasoning>", "</reasoning>"),
    ("<scratchpad>", "</scratchpad>"),
    ("<tool_call>", "</tool_call>"),
    ("<tool_response>", "</tool_response>"),
    ("<function_call>", "</function_call>"),
)

#: Chat-template control tokens, which are markup rather than blocks.
_CONTROL_TOKEN_RE = re.compile(r"<\|[^|>]{0,64}\|>")


def strip_reasoning_tokens(text: str) -> str:
    """Remove reasoning blocks and control tokens from spoken text.

    A10-G1. A model that emits its reasoning inline had it read aloud
    word for word on the one surface where nobody can see what is being
    said. An UNCLOSED block runs to the end of the text: an
    interrupted reasoning block is still reasoning, and speaking its
    remainder is the exact failure this removes.
    """
    if not text:
        return text
    out = text
    for opener, closer in _REASONING_BLOCKS:
        while True:
            start = out.lower().find(opener)
            if start < 0:
                break
            end = out.lower().find(closer, start + len(opener))
            if end < 0:
                out = out[:start]
                break
            out = out[:start] + out[end + len(closer):]
    out = _CONTROL_TOKEN_RE.sub("", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def _fence_spans(text: str) -> List[Tuple[int, int]]:
    """Character spans of fenced code blocks (A10-G3 + bug 1).

    The old regex was ``^(?:```|~~~).*?(?:```|~~~)`` — non-greedy, and it
    matched ANY closer. Two consequences, both under-counting exactly the
    reply that most needs the spoken fallback:

    * an UNCLOSED fence matched nothing at all, so a reply that opened a
      block and ran out of tokens read as pure prose;
    * a container fence (````` ```` `````) holding inner ``` blocks closed
      on the first inner marker instead of on its own, so most of the
      block fell outside the span.

    The origin scans line by line: a fence opens with three or more
    backticks or tildes, and closes only on a run of the SAME character
    at least as long. An unclosed fence runs to the end.
    """
    spans: List[Tuple[int, int]] = []
    offset = 0
    open_at: Optional[int] = None
    open_marker = ""
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        match = re.match(r"^(`{3,}|~{3,})", stripped)
        if match:
            marker = match.group(1)
            if open_at is None:
                open_at = offset
                open_marker = marker
            elif marker[0] == open_marker[0] and len(marker) >= len(open_marker):
                spans.append((open_at, offset + len(line)))
                open_at = None
                open_marker = ""
        offset += len(line)
    if open_at is not None:
        spans.append((open_at, len(text)))
    return spans


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
    code_chars = sum(end - start for start, end in _fence_spans(text))
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
    # Same scanner the ratio uses, so what is measured is what is
    # removed (A10 bug 1: they could disagree).
    for start, end in reversed(_fence_spans(text)):
        text = text[:start] + " " + text[end:]
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


@dataclass(frozen=True)
class SpokenShape:
    """The spoken copy of a reply, and what shaping it took (A10-G12).

    The shaping facts were not recorded anywhere, so nothing downstream
    could tell a reply that spoke its own content from one that spoke
    the fallback line, or a reply that was cut at the word cap from one
    that simply ended. Both are things a person would notice and ask
    about, and both were invisible in the event and the receipt.
    """

    text: str
    code_heavy: bool = False
    word_cap_truncated: bool = False
    summarized: bool = False
    original_words: int = 0
    spoken_words: int = 0

    def as_dict(self) -> Dict[str, object]:
        return {
            "code_heavy": self.code_heavy,
            "word_cap_truncated": self.word_cap_truncated,
            "summarized": self.summarized,
            "original_words": self.original_words,
            "spoken_words": self.spoken_words,
        }


def shape_for_speech(
    text: str,
    fallback: str = DEFAULT_FALLBACK,
    summarizer: Optional[Callable[[str], str]] = None,
    max_words: Optional[int] = None,
) -> SpokenShape:
    """``adapt_for_speech`` plus the record of what it did (A10-G12).

    ``max_words`` is the engine's own spoken budget, passed in rather
    than reached for: this module never raises or bypasses the engine's
    VoiceRiskPolicy cap (FD-4), it only records when the text met it.
    """
    original_words = len((text or "").split())
    spoken = adapt_for_speech(text, fallback=fallback, summarizer=summarizer)
    code_heavy = bool(text) and spoken == fallback and fallback != text
    truncated = False
    if max_words and spoken and not code_heavy:
        words = spoken.split()
        if len(words) > max_words:
            spoken = " ".join(words[:max_words]) + "…"
            truncated = True
    return SpokenShape(
        text=spoken,
        code_heavy=code_heavy,
        word_cap_truncated=truncated,
        summarized=bool(summarizer) and not code_heavy,
        original_words=original_words,
        spoken_words=len(spoken.split()),
    )


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
    # A10-G5 + G1: THIS is the one pipeline every spoken egress passes
    # through -- the dashboard's, the Wyoming satellite's, and
    # proactive_speak's. Two things happen before any shaping decision:
    # reasoning and control tokens stop being words, and the text meets
    # the same egress scrub every other user-visible string meets. The
    # satellite path used to read raw response_chunk text aloud, which
    # met none of this.
    text = strip_reasoning_tokens(text)
    try:
        from ..security.scrub import scrub_for_egress
        text = scrub_for_egress(text, surface="spoken")
    except Exception:  # pragma: no cover - defensive
        pass
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