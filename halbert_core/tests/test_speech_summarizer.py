# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Packet 04 C2: spoken summarization of long replies.

The seam (``make_speech_summarizer``) resolves the utility model through
``resolve_aux_model(task="tts_summarization", prefer_fast=True)`` and
summarizes long spoken text to 1-2 sentences through the ONE existing
client path (``call_llm_chat``). Every test mocks at those seams — no
real model calls, no network.

The load-bearing rules pinned here:

  * fail-soft everywhere — a resolution miss, request error, empty
    response, or a summary not strictly shorter than the input all
    speak the ORIGINAL text; nothing raises;
  * deterministic gating — short text (at or below the threshold) is
    never sent to a model;
  * a code-heavy reply speaks the fallback line and is NEVER
    summarized (composition after the fallback decision);
  * the display copy is byte-identical in every case.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from halbert_core.integrations.speech_summarizer import (
    SPOKEN_SUMMARY_THRESHOLD_CHARS,
    SUMMARY_TASK,
    make_speech_summarizer,
)
from halbert_core.integrations.tts_quality import DEFAULT_FALLBACK, adapt_for_speech
from halbert_core.integrations.modality_wiring import spoken_segment_lines
from halbert_core.model import client as client_mod
from halbert_core.model import utility_slot as utility_slot_mod
from halbert_core.model.llm_config import ResolvedModel


def _long_prose() -> str:
    """~10x the threshold of plain prose — a reply worth summarizing."""
    sentence = (
        "The scanner found three services that need attention, the backup "
        "job finished on schedule, and the certificate renewal is queued "
        "for tonight. "
    )
    return sentence * 10


_LONG = _long_prose()
assert len(_LONG) > SPOKEN_SUMMARY_THRESHOLD_CHARS

_RESOLVED = ResolvedModel(
    model="tiny:1b", url="http://localhost:11434", provider="ollama", api_key=""
)

_SUMMARY = "Three services need attention; backups finished and renewal is queued."


def _payload(*texts, spoken=True, display="DISPLAY TEXT"):
    """A stand-in MultiStreamPayload: one spoken segment per text plus
    display text the summarizer must never touch."""
    return SimpleNamespace(
        segments=[
            SimpleNamespace(
                text=t,
                is_spoken=spoken,
                role=SimpleNamespace(value="persona"),
                prosody=SimpleNamespace(rate=0.9, volume=0.8, whisper=False),
            )
            for t in texts
        ],
        display_text=display,
    )


def _patch(obj, name, value):
    """Patch a module attribute for the with-block — the client seam."""
    return mock.patch.object(obj, name, value)


class TestSpeechSummarizerSeam:

    def test_long_text_returns_the_model_summary(self):
        calls = {"aux": [], "llm": []}
        with _patch(
            utility_slot_mod,
            "resolve_aux_model",
            lambda session_id=None, task="utility", prefer_fast=False: (
                calls["aux"].append(
                    {"session_id": session_id, "task": task, "prefer_fast": prefer_fast}
                ),
                _RESOLVED,
            )[1],
        ), _patch(
            client_mod,
            "call_llm_chat",
            lambda **kw: (calls["llm"].append(kw), {"content": _SUMMARY})[1],
        ):
            summarize = make_speech_summarizer("sess-1")
            out = summarize(_LONG)
        assert out == _SUMMARY
        assert len(calls["llm"]) == 1
        assert calls["llm"][0]["endpoint"] == _RESOLVED.url
        assert calls["llm"][0]["model"] == _RESOLVED.model
        assert calls["llm"][0]["provider"] == _RESOLVED.provider
        assert calls["llm"][0]["api_key"] == ""
        assert _LONG in calls["llm"][0]["messages"][1]["content"]

    def test_resolution_uses_the_utility_ladder_contract(self):
        seen = {}

        def fake_resolve(session_id=None, task="utility", prefer_fast=False):
            seen.update(session_id=session_id, task=task, prefer_fast=prefer_fast)
            return _RESOLVED

        with _patch(utility_slot_mod, "resolve_aux_model", fake_resolve), _patch(
            client_mod, "call_llm_chat", lambda **kw: {"content": _SUMMARY}
        ):
            out = make_speech_summarizer("sess-9")(_LONG)
        assert seen["task"] == SUMMARY_TASK
        assert seen["task"] == "tts_summarization"
        assert seen["prefer_fast"] is True
        assert seen["session_id"] == "sess-9"
        assert out == _SUMMARY

    def test_short_text_never_reaches_the_model(self):
        def boom(*a, **kw):
            raise AssertionError("the model must not be consulted for short text")

        short = "All quiet on the scanner."
        with _patch(utility_slot_mod, "resolve_aux_model", boom), _patch(
            client_mod, "call_llm_chat", boom
        ):
            out = make_speech_summarizer("sess-1")(short)
        assert out == short

    def test_text_at_the_threshold_is_not_summarized(self):
        def boom(*a, **kw):
            raise AssertionError("at-threshold text must not reach the model")

        at = "a" * SPOKEN_SUMMARY_THRESHOLD_CHARS
        with _patch(utility_slot_mod, "resolve_aux_model", boom), _patch(
            client_mod, "call_llm_chat", boom
        ):
            assert make_speech_summarizer("s")(at) == at

    def test_empty_text_is_returned_untouched(self):
        assert make_speech_summarizer("s")("") == ""

    def test_resolution_miss_speaks_the_original(self):
        with _patch(utility_slot_mod, "resolve_aux_model", lambda **kw: None), _patch(
            client_mod, "call_llm_chat", lambda **kw: {"content": _SUMMARY}
        ):
            out = make_speech_summarizer("s")(_LONG)
        assert out == _LONG

    def test_resolution_failure_speaks_the_original(self):
        def boom(*a, **kw):
            raise RuntimeError("models.yml unreadable")

        with _patch(utility_slot_mod, "resolve_aux_model", boom), _patch(
            client_mod, "call_llm_chat", lambda **kw: {"content": _SUMMARY}
        ):
            assert make_speech_summarizer("s")(_LONG) == _LONG

    def test_request_error_speaks_the_original(self):
        def boom(**kw):
            raise RuntimeError("endpoint down")

        with _patch(utility_slot_mod, "resolve_aux_model", lambda **kw: _RESOLVED), _patch(
            client_mod, "call_llm_chat", boom
        ):
            assert make_speech_summarizer("s")(_LONG) == _LONG

    def test_empty_response_speaks_the_original(self):
        with _patch(utility_slot_mod, "resolve_aux_model", lambda **kw: _RESOLVED), _patch(
            client_mod, "call_llm_chat", lambda **kw: {"content": "   "}
        ):
            assert make_speech_summarizer("s")(_LONG) == _LONG

    def test_summary_not_shorter_speaks_the_original(self):
        with _patch(utility_slot_mod, "resolve_aux_model", lambda **kw: _RESOLVED), _patch(
            client_mod, "call_llm_chat", lambda **kw: {"content": _LONG + " tail"}
        ):
            assert make_speech_summarizer("s")(_LONG) == _LONG

    def test_summary_equal_length_speaks_the_original(self):
        with _patch(utility_slot_mod, "resolve_aux_model", lambda **kw: _RESOLVED), _patch(
            client_mod, "call_llm_chat", lambda **kw: {"content": _LONG}
        ):
            assert make_speech_summarizer("s")(_LONG) == _LONG

    def test_summary_whitespace_is_collapsed(self):
        with _patch(utility_slot_mod, "resolve_aux_model", lambda **kw: _RESOLVED), _patch(
            client_mod,
            "call_llm_chat",
            lambda **kw: {"content": "  A   short,\n\nspoken  summary.  "},
        ):
            out = make_speech_summarizer("s")(_LONG)
        assert out == "A short, spoken summary."

    def test_client_result_none_speaks_the_original(self):
        with _patch(utility_slot_mod, "resolve_aux_model", lambda **kw: _RESOLVED), _patch(
            client_mod, "call_llm_chat", lambda **kw: None
        ):
            assert make_speech_summarizer("s")(_LONG) == _LONG


class TestAdaptForSpeechComposition:

    def test_long_reply_is_replaced_by_the_summary(self):
        spoken = adapt_for_speech(_LONG, summarizer=lambda t: _SUMMARY)
        assert spoken == _SUMMARY

    def test_summarizer_receives_the_stripped_copy(self):
        reply = "## Status\n" + _LONG + "\nRun `systemctl restart`."
        seen = {}

        def spy(text):
            seen["text"] = text
            return _SUMMARY

        adapt_for_speech(reply, summarizer=spy)
        assert seen["text"] == adapt_for_speech(reply)

    def test_code_heavy_reply_is_never_summarized(self):
        reply = "```python\n" + "x = 1\n" * 400 + "```"

        def boom(text):
            raise AssertionError("a code-heavy reply must never be summarized")

        spoken = adapt_for_speech(reply, fallback=DEFAULT_FALLBACK, summarizer=boom)
        assert spoken == DEFAULT_FALLBACK

    def test_summarizer_failure_speaks_the_original(self):
        def boom(text):
            raise RuntimeError("seam violated its contract")

        spoken = adapt_for_speech(_LONG, summarizer=boom)
        assert spoken == adapt_for_speech(_LONG)

    def test_longer_summary_is_ignored(self):
        spoken = adapt_for_speech(_LONG, summarizer=lambda t: t + " even longer")
        assert spoken == adapt_for_speech(_LONG)

    def test_empty_summary_is_ignored(self):
        original = adapt_for_speech(_LONG)
        assert adapt_for_speech(_LONG, summarizer=lambda t: "") == original

    def test_short_reply_is_untouched_by_a_honest_seam(self):
        reply = "All quiet on the scanner."
        assert adapt_for_speech(reply, summarizer=lambda t: t) == reply


class TestSpokenSegmentLinesSummarizer:

    def test_long_reply_speaks_the_summary(self):
        payload = _payload(_LONG, _LONG)
        lines = spoken_segment_lines(_LONG, payload, summarizer=lambda t: _SUMMARY)
        assert [l["text"] for l in lines] == [_SUMMARY]
        assert lines[0]["role"] == "persona"
        assert lines[0]["rate"] == 0.9  # the first line's prosody is kept

    def test_display_text_is_byte_identical(self):
        payload = _payload(_LONG, display="byte-identical display")
        before = payload.display_text
        spoken_segment_lines(_LONG, payload, summarizer=lambda t: _SUMMARY)
        assert payload.display_text == before
        assert payload.display_text == "byte-identical display"

    def test_summarizer_failure_speaks_the_original_lines(self):
        payload = _payload("The scanner is back online.")

        def boom(text):
            raise RuntimeError("never escapes")

        lines = spoken_segment_lines("The scanner is back online.", payload, summarizer=boom)
        assert [l["text"] for l in lines] == ["The scanner is back online."]

    def test_summarizer_no_op_keeps_the_c1_lines(self):
        payload = _payload(_LONG)
        c1_lines = spoken_segment_lines(_LONG, payload)
        c2_lines = spoken_segment_lines(_LONG, payload, summarizer=lambda t: t)
        assert c2_lines == c1_lines

    def test_summary_longer_than_input_is_ignored(self):
        payload = _payload(_LONG)
        c1_lines = spoken_segment_lines(_LONG, payload)
        c2_lines = spoken_segment_lines(
            _LONG, payload, summarizer=lambda t: t + " padding"
        )
        assert c2_lines == c1_lines

    def test_code_heavy_reply_never_calls_the_summarizer(self):
        reply = "```python\n" + "x = 1\n" * 400 + "```"

        def boom(text):
            raise AssertionError("code-heavy replies are never summarized")

        lines = spoken_segment_lines(reply, _payload("x = 1"), summarizer=boom)
        assert [l["text"] for l in lines] == [DEFAULT_FALLBACK]

    def test_display_text_untouched_even_when_the_summarizer_fires(self):
        payload = _payload(_LONG, display="keep me")
        spoken_segment_lines(_LONG, payload, summarizer=lambda t: _SUMMARY)
        assert payload.display_text == "keep me"

    def test_short_reply_never_invokes_the_summarizer(self):
        def boom(text):
            raise AssertionError("short replies are never summarized")

        lines = spoken_segment_lines(
            "All good.", _payload("The scanner is back online."), summarizer=boom
        )
        assert [l["text"] for l in lines] == ["The scanner is back online."]

    def test_end_to_end_seam_over_the_threshold(self):
        """The real seam, mocked only at the client seam: a long reply's
        spoken copy is the model's summary; the display copy is the
        original reply, byte for byte."""
        with _patch(utility_slot_mod, "resolve_aux_model", lambda **kw: _RESOLVED), _patch(
            client_mod, "call_llm_chat", lambda **kw: {"content": _SUMMARY}
        ):
            summarize = make_speech_summarizer("sess-e2e")
            payload = _payload(_LONG, display=_LONG)
            lines = spoken_segment_lines(_LONG, payload, summarizer=summarize)
        assert [l["text"] for l in lines] == [_SUMMARY]
        assert payload.display_text == _LONG