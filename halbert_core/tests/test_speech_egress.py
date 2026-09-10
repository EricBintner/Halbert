# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-10: one spoken pipeline, and it says what it did.

- **A10-G5** (fix-first row 9) -- the Wyoming/HA satellite path collected
  ``response_chunk`` events and read the concatenation aloud. Those are
  raw model output: they bypass ``_parse_module_invocations``, the echo
  guard, the engine's word cap and ``tts_quality`` entirely. An
  unbounded, un-redacted read-aloud on the one screenless surface, where
  nobody can see what was said.
- **A10-G1** -- reasoning and tool-call tokens (``<think>`` blocks, tool
  markers) were spoken as words.
- **A10-G3 + bug 1** -- the fence scanner did not match the origin's
  (container unwrap, matching closer, an unclosed fence counting), so
  ``modality_resolved.speech_text`` and what was actually spoken could
  disagree.
- **A10-G12** -- the shaping facts (code-heavy fallback, word-cap
  truncation) were not recorded, so nothing downstream could tell a
  reply that spoke its content from one that spoke the fallback line.
"""

import pytest

from halbert_core.integrations.tts_quality import (
    DEFAULT_FALLBACK,
    adapt_for_speech,
    code_fence_ratio,
    shape_for_speech,
    strip_reasoning_tokens,
)


# ---------------------------------------------------------------------------
# A10-G1: reasoning and tool tokens are not words
# ---------------------------------------------------------------------------

def test_a_think_block_is_not_spoken():
    out = strip_reasoning_tokens(
        "<think>the user wants the disk usage</think>Your disk is 80% full.")
    assert "think" not in out
    assert "Your disk is 80% full." in out


def test_an_unclosed_think_block_is_dropped_to_the_end():
    out = strip_reasoning_tokens("Answer. <think>still reasoning")
    assert "still reasoning" not in out
    assert out.startswith("Answer.")


def test_tool_call_markers_are_not_spoken():
    out = strip_reasoning_tokens(
        '<tool_call>{"name": "run_command"}</tool_call>Done.')
    assert "tool_call" not in out
    assert "run_command" not in out
    assert "Done." in out


def test_control_tokens_are_not_spoken():
    out = strip_reasoning_tokens("<|im_start|>assistant<|im_end|>Hello.")
    assert "im_start" not in out
    assert "Hello." in out


def test_ordinary_prose_is_untouched():
    assert strip_reasoning_tokens("Your disk is 80% full.") == (
        "Your disk is 80% full.")


# ---------------------------------------------------------------------------
# A10-G3 + bug 1: the fence scanner matches the origin
# ---------------------------------------------------------------------------

def test_an_unclosed_fence_counts_to_the_end():
    """The origin counts an unclosed fence as running to the end of the
    text; a scanner that requires a closer under-counts exactly the
    reply most in need of the fallback."""
    assert code_fence_ratio("intro\n```\nline\nline\nline\nline") > 0.5


def test_a_longer_container_fence_is_matched_by_its_own_closer():
    """A four-backtick container holding three-backtick blocks closes on
    four, not on the first three it meets."""
    text = "````\n```\ninner\n```\n````\n"
    assert code_fence_ratio(text) > 0.9


def test_prose_has_no_fence_ratio():
    assert code_fence_ratio("just some prose about disks") == 0.0


# ---------------------------------------------------------------------------
# A10-G12: the shaping facts are recorded
# ---------------------------------------------------------------------------

def test_a_code_heavy_reply_records_the_fallback():
    text = "```\n" + "\n".join("code line" for _ in range(40)) + "\n```"
    shaped = shape_for_speech(text)
    assert shaped.text == DEFAULT_FALLBACK
    assert shaped.code_heavy is True
    assert shaped.word_cap_truncated is False


def test_a_prose_reply_records_no_shaping():
    shaped = shape_for_speech("Your disk is 80 percent full.")
    assert shaped.code_heavy is False
    assert shaped.word_cap_truncated is False
    assert shaped.text == "Your disk is 80 percent full."


def test_a_word_capped_reply_says_it_was_cut():
    shaped = shape_for_speech(" ".join(f"word{i}" for i in range(200)),
                              max_words=20)
    assert shaped.word_cap_truncated is True
    assert len(shaped.text.split()) <= 21


def test_the_shaping_record_is_serialisable():
    shaped = shape_for_speech("hello")
    assert isinstance(shaped.as_dict(), dict)
    assert shaped.as_dict()["code_heavy"] is False


# ---------------------------------------------------------------------------
# A10-G5: one pipeline, and the Wyoming path is on it
# ---------------------------------------------------------------------------

def test_adapt_for_speech_strips_reasoning_tokens_too():
    """The one pipeline: everything a satellite reads aloud passes here."""
    out = adapt_for_speech("<think>hmm</think>Your disk is fine.")
    assert "think" not in out
    assert "Your disk is fine." in out


def test_adapt_for_speech_scrubs_a_registered_secret():
    from halbert_core.ingestion.redaction_registry import get_global_registry

    get_global_registry().register("spoken-secret-value-5")
    out = adapt_for_speech("the key is spoken-secret-value-5")
    assert "spoken-secret-value-5" not in out


@pytest.mark.asyncio
async def test_the_wyoming_path_speaks_the_committed_text():
    """It collected response_chunk -- raw model output that never met the
    guard, the parser or the word cap."""
    import halbert_core.integrations.wyoming_agent as wyoming

    import inspect

    source = inspect.getsource(wyoming)
    assert "speech_segment" in source, (
        "the satellite path must take the committed spoken text, not the "
        "raw chunks"
    )
    assert "adapt_for_speech" in source


def test_the_proactive_path_is_on_the_same_pipeline():
    import inspect

    import halbert_core.integrations.wyoming_agent as wyoming

    # ``proactive_speak`` is a module-level function, not a method.
    source = inspect.getsource(wyoming.proactive_speak)
    assert "adapt_for_speech" in source


# ---------------------------------------------------------------------------
# A10-G7: the model is told the spoken budget
# ---------------------------------------------------------------------------

def test_the_budget_hint_names_the_word_count():
    from halbert_core.integrations.modality_wiring import spoken_budget_hint

    hint = spoken_budget_hint(35)
    assert "35" in hint
    assert "words" in hint.lower()


def test_no_budget_means_no_hint():
    from halbert_core.integrations.modality_wiring import spoken_budget_hint

    assert spoken_budget_hint(None) == ""
    assert spoken_budget_hint(0) == ""


def test_the_hint_is_deterministic():
    from halbert_core.integrations.modality_wiring import spoken_budget_hint

    assert spoken_budget_hint(20) == spoken_budget_hint(20)


def test_the_response_prompt_carries_the_hint_on_a_voice_turn():
    from halbert_core.prompts.agent_prompts import AgentPromptBuilder

    prompt = AgentPromptBuilder().build_response_prompt(
        query="how is the disk",
        context="",
        observations=[],
        response_modality="voice",
        spoken_max_words=25,
    )
    assert "25" in prompt


def test_a_text_turn_gets_no_spoken_budget_hint():
    from halbert_core.prompts.agent_prompts import AgentPromptBuilder

    prompt = AgentPromptBuilder().build_response_prompt(
        query="how is the disk",
        context="",
        observations=[],
        response_modality="text",
        spoken_max_words=25,
    )
    assert "spoken" not in prompt.lower() or "25" not in prompt


# ---------------------------------------------------------------------------
# A10-G6: a barge-in is fed back as a deterministic note
# ---------------------------------------------------------------------------

def test_a_barge_in_leaves_a_note_for_the_next_turn():
    from halbert_core.integrations.modality_wiring import (
        barge_in_note,
        record_barge_in,
        take_barge_in_note,
    )

    record_barge_in("s1", spoken_words=12, total_words=40)
    note = take_barge_in_note("s1")
    assert note
    assert "interrupt" in note.lower() or "stopped" in note.lower()
    # Once: the note is for the NEXT turn, not for every later turn.
    assert take_barge_in_note("s1") is None


def test_no_barge_in_leaves_no_note():
    from halbert_core.integrations.modality_wiring import take_barge_in_note

    assert take_barge_in_note("never-spoke") is None


def test_the_note_is_deterministic_text():
    from halbert_core.integrations.modality_wiring import barge_in_note

    assert barge_in_note(5, 30) == barge_in_note(5, 30)
    assert "5" in barge_in_note(5, 30)


# ---------------------------------------------------------------------------
# R-10 Phase E (FD-4): the summarizer is dormant but correct
# ---------------------------------------------------------------------------

def test_a_secure_turn_never_reaches_a_cloud_summarizer(monkeypatch):
    """A14-G4 (summarizer half): the spoken copy of a secure turn must
    not leave the machine to be shortened."""
    from halbert_core.integrations import speech_summarizer

    seen = {}

    def _resolve(**kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr(
        speech_summarizer, "_resolve_aux", _resolve)
    summarize = speech_summarizer.make_speech_summarizer("s1", secure=True)
    long_text = "word " * 400
    assert summarize(long_text) == long_text
    assert seen.get("require_local") is True


def test_an_ordinary_turn_does_not_demand_a_local_model(monkeypatch):
    from halbert_core.integrations import speech_summarizer

    seen = {}
    monkeypatch.setattr(
        speech_summarizer, "_resolve_aux",
        lambda **kw: seen.update(kw) or None)
    speech_summarizer.make_speech_summarizer("s1")("word " * 400)
    assert seen.get("require_local") is False


def test_a_failed_pick_is_retried_once_excluding_it(monkeypatch):
    """A14-G7 (summarizer half): a model that errors is excluded and the
    ladder is asked again, once."""
    from halbert_core.integrations import speech_summarizer

    calls = []

    class _Resolved:
        url = "http://localhost:1"
        model = "m1"
        provider = "ollama"
        api_key = ""

    class _Resolved2(_Resolved):
        model = "m2"

    def _resolve(**kwargs):
        calls.append(kwargs.get("exclude"))
        return _Resolved() if len(calls) == 1 else _Resolved2()

    def _call(**kwargs):
        if kwargs.get("model") == "m1":
            raise RuntimeError("model unavailable")
        return {"content": "short"}

    monkeypatch.setattr(speech_summarizer, "_resolve_aux", _resolve)
    monkeypatch.setattr(speech_summarizer, "_call_llm", _call)

    out = speech_summarizer.make_speech_summarizer("s1")("word " * 400)
    assert out == "short"
    assert len(calls) == 2
    assert "m1" in (calls[1] or ())


def test_the_retry_happens_at_most_once(monkeypatch):
    from halbert_core.integrations import speech_summarizer

    calls = []

    class _Resolved:
        url = "http://localhost:1"
        model = "m"
        provider = "ollama"
        api_key = ""

    monkeypatch.setattr(
        speech_summarizer, "_resolve_aux",
        lambda **kw: calls.append(1) or _Resolved())
    monkeypatch.setattr(
        speech_summarizer, "_call_llm",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("always down")))

    original = "word " * 400
    assert speech_summarizer.make_speech_summarizer("s1")(original) == original
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_the_summarizer_runs_off_the_event_loop(monkeypatch):
    """A14 bug 3: the sync summarizer and the catalog probe ran INLINE on
    the loop, so a slow or hung utility model froze every other session's
    turn as well as its own."""
    import inspect

    from halbert_core.integrations import speech_summarizer

    source = inspect.getsource(speech_summarizer.make_async_speech_summarizer)
    assert "to_thread" in source


def test_the_docstring_no_longer_claims_the_summarizer_is_reachable():
    """A10 bug 3 + the FD-4 finding: the C2 summarizer sits behind the
    engine's 12-35-word cap, so its 600-character gate can never fire on
    a real voice turn. The module says so."""
    from halbert_core.integrations import speech_summarizer

    text = (speech_summarizer.__doc__ or "").lower()
    assert "unreachable" in text or "dormant" in text


def test_the_summary_gate_sits_behind_the_engines_word_cap():
    """FD-4's finding, as arithmetic rather than prose.

    The C2 summarizer's deterministic gate is 600 characters. The
    engine's VoiceRiskPolicy cap is 12-35 words, and English averages
    well under 8 characters a word including the space -- so the longest
    text that can reach this seam on a real voice turn is a few hundred
    characters, and the gate can never fire. Keeping the cap and wiring
    the budget hint instead (A10-G7) is FD-4's ruling; this pins the
    reason, so a later change to either number is a change someone has
    to look at.
    """
    from halbert_core.integrations.speech_summarizer import (
        SPOKEN_SUMMARY_THRESHOLD_CHARS,
    )

    engine_cap_words = 35
    generous_chars_per_word = 8
    assert engine_cap_words * generous_chars_per_word < SPOKEN_SUMMARY_THRESHOLD_CHARS
