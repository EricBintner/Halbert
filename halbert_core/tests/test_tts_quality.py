# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Packet 04 C1: TTS quality rules (OpenClaw speech-text.ts patterns).

A code-heavy reply read aloud is garbage: fences, indentation and
identifiers synthesized as noise. The rule lifted from OpenClaw:

  * fenced-block ratio >= 50% of characters -> speak a deterministic
    fallback line verbatim (the detail is on screen);
  * otherwise strip fences/inline code/markdown noise from the SPOKEN
    copy only — the on-screen text is untouched.

``summarizer`` is the C2 hook (spoken summarization of long replies),
wired to the utility-model seam in packet 04 C2 — see
test_speech_summarizer.py for the seam's own contract.
"""
from __future__ import annotations

from types import SimpleNamespace

from halbert_core.integrations.tts_quality import (
    DEFAULT_FALLBACK,
    adapt_for_speech,
    code_fence_ratio,
    is_code_heavy,
)
from halbert_core.integrations.modality_wiring import spoken_segment_lines


def _payload(*texts, spoken=True):
    """A stand-in MultiStreamPayload with one segment per text."""
    return SimpleNamespace(segments=[
        SimpleNamespace(
            text=t,
            is_spoken=spoken,
            role=SimpleNamespace(value="persona"),
            prosody=SimpleNamespace(rate=0.9, volume=0.8, whisper=False),
        )
        for t in texts
    ])


class TestSpokenSegmentLines:

    def test_code_heavy_reply_speaks_one_fallback_line(self):
        reply = "```python\n" + "x = 1\n" * 30 + "```"
        lines = spoken_segment_lines(reply, _payload("x = 1"))
        assert [l["text"] for l in lines] == [DEFAULT_FALLBACK]
        assert lines[0]["role"] == "persona"

    def test_prose_segments_keep_their_text_and_prosody(self):
        lines = spoken_segment_lines(
            "All good.", _payload("The scanner is back online.")
        )
        assert len(lines) == 1
        assert lines[0]["text"] == "The scanner is back online."
        assert lines[0]["rate"] == 0.9
        assert lines[0]["volume"] == 0.8
        assert lines[0]["whisper"] is False

    def test_a_code_segment_is_not_spoken(self):
        lines = spoken_segment_lines(
            "Prose reply.", _payload("```python\nx = 1\n```")
        )
        assert lines == []

    def test_unspoken_segments_are_skipped(self):
        lines = spoken_segment_lines(
            "Prose reply.", _payload("not for the voice", spoken=False)
        )
        assert lines == []

    def test_no_payload_no_lines(self):
        assert spoken_segment_lines("Prose reply.", None) == []


class TestAdaptForSpeech:

    def test_plain_text_passes_through(self):
        assert adapt_for_speech("The scanner is back online.") == "The scanner is back online."

    def test_code_heavy_reply_gets_fallback_line(self):
        reply = "Here is the fix:\n```python\n" + "x = 1\n" * 30 + "```\nthats the whole change"
        spoken = adapt_for_speech(reply, fallback="I've put the detailed response on screen.")
        assert spoken == "I've put the detailed response on screen."

    def test_code_heavy_default_fallback(self):
        reply = "```\n" + "config: yes\n" * 40 + "```"
        assert adapt_for_speech(reply) == DEFAULT_FALLBACK

    def test_mixed_reply_strips_fences_and_speaks_prose(self):
        reply = "Two things.\n```\nsome code\n```\nThat's it."
        spoken = adapt_for_speech(reply)
        assert "```" not in spoken and "Two things." in spoken and "That's it." in spoken

    def test_fallback_is_verbatim_not_wrapped(self):
        """No wrapper phrase around the fallback — the spoken line IS the
        line the caller wrote (a wrapper reads as a meta-instruction)."""
        line = "I've put the detailed response on screen."
        spoken = adapt_for_speech("```python\nx = 1\n```", fallback=line)
        assert spoken == line

    def test_inline_code_and_markdown_noise_are_stripped(self):
        reply = "## Status\nRun `systemctl restart` with **care**."
        spoken = adapt_for_speech(reply)
        assert "`" not in spoken and "**" not in spoken and "#" not in spoken
        assert "systemctl restart" in spoken and "care" in spoken

    def test_summarizer_hook_composes_for_long_text_only(self):
        """C2: the hook is live. A summarizer that does not fire for
        short text (the seam's own gate) changes nothing."""
        reply = "All quiet on the scanner."
        assert adapt_for_speech(reply, summarizer=lambda t: t) == reply


class TestCodeFenceRatio:

    def test_prose_is_not_code_heavy(self):
        assert code_fence_ratio("Just a sentence about the scanner.") < 0.5
        assert is_code_heavy("Just a sentence about the scanner.") is False

    def test_a_wall_of_code_is_code_heavy(self):
        reply = "Here is the fix:\n```python\n" + "x = 1\n" * 30 + "```\nthats the whole change"
        assert is_code_heavy(reply) is True

    def test_a_small_snippet_is_not_code_heavy(self):
        reply = "Two things.\n```\nsome code\n```\nThat's it."
        assert is_code_heavy(reply) is False

    def test_empty_text_is_not_code_heavy(self):
        assert is_code_heavy("") is False