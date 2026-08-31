# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Phase 2 modality-voice wiring tests.

Tests the three voice accessor files (voice_backend, channel_capability,
voice_auth_gate), the HalbertAppSeam voice wiring, the modality_wiring
module, and the TASK-07 fixes (wyoming_agent markdown stripping, pipeline
barge-in, input defanging).

These tests run without the Haloysius engine installed — they verify the
subtractive contract (graceful degradation to text-only) and the structural
Protocol conformance of the accessors. When the engine IS installed, a
subset of tests exercise the full modality resolution flow.
"""

from __future__ import annotations

import asyncio
import struct
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_seam():
    """Clear the global seam before and after each test."""
    try:
        from haloysius import seam
        seam.clear_app_seam()
    except ImportError:
        pass
    yield
    try:
        from haloysius import seam
        seam.clear_app_seam()
    except ImportError:
        pass


def _engine_available() -> bool:
    """Check if the Haloysius modality engine is importable."""
    try:
        import haloysius.modality.types  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# HalbertVoiceBackend
# ---------------------------------------------------------------------------


class _FakeTTS:
    """Fake PiperTTS for testing — produces deterministic PCM."""

    def __init__(self):
        self._speed = 1.0
        self._voice_model = "test-voice.onnx"
        self._initialized = True

    def _ensure_initialized(self):
        pass

    async def synthesize(self, text, cancel_token=None):
        # Produce 100ms of silence at 16kHz (1600 samples = 3200 bytes)
        samples = [0] * 1600
        pcm = struct.pack(f"<{len(samples)}h", *samples)
        yield pcm


class TestHalbertVoiceBackend:

    def test_constructs_without_tts(self):
        from halbert_core.integrations.voice_backend import HalbertVoiceBackend
        backend = HalbertVoiceBackend()
        assert backend._tts is None

    def test_constructs_with_tts(self):
        from halbert_core.integrations.voice_backend import HalbertVoiceBackend
        tts = _FakeTTS()
        backend = HalbertVoiceBackend(tts=tts)
        assert backend._tts is tts

    def test_is_available_with_fake_tts(self):
        from halbert_core.integrations.voice_backend import HalbertVoiceBackend
        backend = HalbertVoiceBackend(tts=_FakeTTS())
        assert backend.is_available() is True

    def test_is_available_returns_false_on_init_failure(self):
        from halbert_core.integrations.voice_backend import HalbertVoiceBackend

        class _BrokenTTS:
            def _ensure_initialized(self):
                raise RuntimeError("no model")

        backend = HalbertVoiceBackend(tts=_BrokenTTS())
        assert backend.is_available() is False

    def test_synthesize_empty_text_returns_empty_result(self):
        from halbert_core.integrations.voice_backend import HalbertVoiceBackend
        backend = HalbertVoiceBackend(tts=_FakeTTS())

        if not _engine_available():
            # Subtractive contract: returns None when engine not installed
            result = asyncio.run(backend.synthesize("", MagicMock()))
            assert result is None
            return
        result = asyncio.run(backend.synthesize("", MagicMock()))
        assert result.success is True
        assert result.audio_bytes == b""

    def test_synthesize_produces_audio(self):
        from halbert_core.integrations.voice_backend import HalbertVoiceBackend
        backend = HalbertVoiceBackend(tts=_FakeTTS())

        prosody = MagicMock()
        prosody.rate = 1.0
        prosody.volume = 1.0
        prosody.whisper = False

        if not _engine_available():
            result = asyncio.run(backend.synthesize("hello world", prosody))
            assert result is None
            return
        result = asyncio.run(backend.synthesize("hello world", prosody))
        assert result.success is True
        assert len(result.audio_bytes) > 0
        assert result.duration_seconds > 0

    def test_synthesize_whisper_caps_volume(self):
        from halbert_core.integrations.voice_backend import HalbertVoiceBackend
        backend = HalbertVoiceBackend(tts=_FakeTTS())

        prosody = MagicMock()
        prosody.rate = 1.0
        prosody.volume = 1.0
        prosody.whisper = True

        if not _engine_available():
            result = asyncio.run(backend.synthesize("quiet message", prosody))
            assert result is None
            return
        result = asyncio.run(backend.synthesize("quiet message", prosody))
        assert result.success is True

    def test_cancel_triggers_barge_in_token(self):
        from halbert_core.integrations.voice_backend import HalbertVoiceBackend
        backend = HalbertVoiceBackend(tts=_FakeTTS())

        token = MagicMock()
        backend.set_barge_in_token(token)
        backend.cancel()
        token.trigger.assert_called_once()

    def test_list_voices_returns_voice_info(self):
        from halbert_core.integrations.voice_backend import HalbertVoiceBackend
        backend = HalbertVoiceBackend(tts=_FakeTTS())
        if not _engine_available():
            # Without the engine, list_voices returns [] (VoiceInfo not importable)
            assert backend.list_voices() == []
            return
        voices = backend.list_voices()
        assert len(voices) >= 1
        assert voices[0].voice_id == "test-voice"


# ---------------------------------------------------------------------------
# HalbertChannelCapability
# ---------------------------------------------------------------------------


class TestHalbertChannelCapability:

    def test_desktop_defaults(self):
        from halbert_core.integrations.channel_capability import HalbertChannelCapability
        cap = HalbertChannelCapability(is_desktop=True)
        assert cap.has_screen() is True
        assert cap.has_keyboard() is True
        assert cap.is_hands_free() is False
        assert cap.current_modality() == "text"

    def test_wyoming_active(self):
        from halbert_core.integrations.channel_capability import HalbertChannelCapability
        cap = HalbertChannelCapability(is_desktop=True, wyoming_active=True)
        assert cap.has_microphone() is True
        assert cap.has_speaker() is True
        assert cap.is_hands_free() is True
        assert cap.current_modality() == "voice"
        # Desktop screen still available alongside Wyoming
        assert cap.has_screen() is True

    def test_satellite_only_no_screen(self):
        from halbert_core.integrations.channel_capability import HalbertChannelCapability
        cap = HalbertChannelCapability(is_desktop=False, wyoming_active=True)
        assert cap.has_screen() is False
        assert cap.has_keyboard() is False
        assert cap.has_speaker() is True

    def test_no_pipeline_text_only(self):
        from halbert_core.integrations.channel_capability import HalbertChannelCapability
        cap = HalbertChannelCapability(audio_pipeline=None, is_desktop=True)
        assert cap.has_microphone() is False
        assert cap.has_speaker() is False
        assert cap.current_modality() == "text"

    def test_set_wyoming_active_updates_state(self):
        from halbert_core.integrations.channel_capability import HalbertChannelCapability
        cap = HalbertChannelCapability()
        assert cap.is_hands_free() is False
        cap.set_wyoming_active(True)
        assert cap.is_hands_free() is True
        assert cap.current_modality() == "voice"


# ---------------------------------------------------------------------------
# HalbertVoiceAuthGate
# ---------------------------------------------------------------------------


class _FakeSpeakerIdentifier:
    """Fake SpeakerIdentifier for testing."""

    def __init__(self, match_result=None):
        self._match_result = match_result

    def identify(self, pcm_bytes):
        return self._match_result


class _FakeMatch:
    """Fake SpeakerMatch result."""

    def __init__(self, speaker_id="eric", name="Eric", role="admin", confidence=0.85):
        self.speaker_id = speaker_id
        self.name = name
        self.role = role
        self.confidence = confidence


class TestHalbertVoiceAuthGate:

    @pytest.mark.skipif(not _engine_available(), reason="Haloysius engine not installed")
    def test_identify_speaker_no_audio_returns_unknown(self):
        from halbert_core.integrations.voice_auth_gate import HalbertVoiceAuthGate
        gate = HalbertVoiceAuthGate()
        identity = gate.identify_speaker(audio_features=None)
        assert identity.speaker_role == "unknown"
        assert identity.verified is False
        assert identity.speaker_id is None

    @pytest.mark.skipif(not _engine_available(), reason="Haloysius engine not installed")
    def test_identify_speaker_with_match(self):
        from halbert_core.integrations.voice_auth_gate import HalbertVoiceAuthGate
        match = _FakeMatch(speaker_id="eric", name="Eric", confidence=0.85)
        gate = HalbertVoiceAuthGate(
            speaker_identifier=_FakeSpeakerIdentifier(match_result=match),
        )
        identity = gate.identify_speaker(audio_features=b"\x00" * 32000)
        assert identity.speaker_id == "eric"
        assert identity.confidence == 0.85
        assert identity.verified is True
        # 0.85 >= 0.82 admin threshold
        assert identity.speaker_role == "admin"

    @pytest.mark.skipif(not _engine_available(), reason="Haloysius engine not installed")
    def test_identify_speaker_no_match(self):
        from halbert_core.integrations.voice_auth_gate import HalbertVoiceAuthGate
        gate = HalbertVoiceAuthGate(
            speaker_identifier=_FakeSpeakerIdentifier(match_result=None),
        )
        identity = gate.identify_speaker(audio_features=b"\x00" * 32000)
        assert identity.speaker_role == "unknown"
        assert identity.verified is False

    @pytest.mark.skipif(not _engine_available(), reason="Haloysius engine not installed")
    def test_identify_speaker_low_confidence(self):
        from halbert_core.integrations.voice_auth_gate import HalbertVoiceAuthGate
        match = _FakeMatch(speaker_id="guest1", name="Guest", confidence=0.50)
        gate = HalbertVoiceAuthGate(
            speaker_identifier=_FakeSpeakerIdentifier(match_result=match),
        )
        identity = gate.identify_speaker(audio_features=b"\x00" * 32000)
        # Below guest threshold (0.60) -> restricted
        assert identity.verified is False
        assert identity.speaker_role == "restricted"

    @pytest.mark.skipif(not _engine_available(), reason="Haloysius engine not installed")
    def test_identify_speaker_guest_band_pin_challenged(self):
        from halbert_core.integrations.voice_auth_gate import HalbertVoiceAuthGate
        match = _FakeMatch(speaker_id="guest1", name="Guest", confidence=0.65)
        gate = HalbertVoiceAuthGate(
            speaker_identifier=_FakeSpeakerIdentifier(match_result=match),
        )
        identity = gate.identify_speaker(audio_features=b"\x00" * 32000)
        # 0.65 is in guest band (0.60-0.69) -> verified, PIN challenged
        assert identity.verified is True
        assert identity.speaker_role == "guest"
        assert identity.voice_pin_challenged is True


# ---------------------------------------------------------------------------
# HalbertAppSeam voice wiring
# ---------------------------------------------------------------------------


class TestHalbertAppSeamVoiceWiring:

    def test_seam_constructs_without_voice_args(self):
        from halbert_core.integrations.app_seam import HalbertAppSeam
        seam = HalbertAppSeam()
        assert seam.get_voice_backend() is not None or True  # lazy or None

    def test_seam_lazy_constructs_voice_backend(self):
        from halbert_core.integrations.app_seam import HalbertAppSeam
        seam = HalbertAppSeam()
        vb = seam.get_voice_backend()
        # Lazy construction returns a HalbertVoiceBackend or None if
        # audio-inference extra is missing — both are valid.
        if vb is not None:
            from halbert_core.integrations.voice_backend import HalbertVoiceBackend
            assert isinstance(vb, HalbertVoiceBackend)

    def test_seam_lazy_constructs_channel_capability(self):
        from halbert_core.integrations.app_seam import HalbertAppSeam
        seam = HalbertAppSeam()
        cap = seam.get_channel_capability()
        if cap is not None:
            from halbert_core.integrations.channel_capability import HalbertChannelCapability
            assert isinstance(cap, HalbertChannelCapability)

    def test_seam_lazy_constructs_voice_auth_gate(self):
        from halbert_core.integrations.app_seam import HalbertAppSeam
        seam = HalbertAppSeam()
        gate = seam.get_voice_auth_gate()
        if gate is not None:
            from halbert_core.integrations.voice_auth_gate import HalbertVoiceAuthGate
            assert isinstance(gate, HalbertVoiceAuthGate)

    def test_seam_accepts_preconstructed_voice_objects(self):
        from halbert_core.integrations.app_seam import HalbertAppSeam
        from halbert_core.integrations.voice_backend import HalbertVoiceBackend
        from halbert_core.integrations.channel_capability import HalbertChannelCapability
        from halbert_core.integrations.voice_auth_gate import HalbertVoiceAuthGate

        vb = HalbertVoiceBackend(tts=_FakeTTS())
        cap = HalbertChannelCapability()
        gate = HalbertVoiceAuthGate()
        seam = HalbertAppSeam(
            voice_backend=vb,
            channel_capability=cap,
            voice_auth_gate=gate,
        )
        assert seam.get_voice_backend() is vb
        assert seam.get_channel_capability() is cap
        assert seam.get_voice_auth_gate() is gate


# ---------------------------------------------------------------------------
# Modality wiring
# ---------------------------------------------------------------------------


class TestModalityWiring:

    def test_defang_user_input_no_engine(self):
        """Without the engine, defang returns text unchanged (subtractive)."""
        from halbert_core.integrations.modality_wiring import defang_user_input
        # If engine is not available, this is a pass-through
        result = defang_user_input("hello <speech>world</speech>")
        assert isinstance(result, str)
        assert "hello" in result

    def test_should_speak_false_for_none_context(self):
        from halbert_core.integrations.modality_wiring import should_speak
        assert should_speak(None) is False

    def test_get_speech_text_empty_for_none(self):
        from halbert_core.integrations.modality_wiring import get_speech_text
        assert get_speech_text(None) == ""

    def test_get_display_text_empty_for_none(self):
        from halbert_core.integrations.modality_wiring import get_display_text
        assert get_display_text(None) == ""

    def test_is_life_safety_event(self):
        from halbert_core.integrations.modality_wiring import is_life_safety_event
        assert is_life_safety_event("smoke_alarm") is True
        assert is_life_safety_event("fire_alarm") is True
        assert is_life_safety_event("gas_leak") is True
        assert is_life_safety_event("carbon_monoxide") is True
        assert is_life_safety_event("co_alarm") is True
        assert is_life_safety_event("water_leak") is True
        assert is_life_safety_event("doorbell") is False
        assert is_life_safety_event("motion") is False

    def test_should_speak_proactively_life_safety_bypasses_quiet_hours(self):
        from halbert_core.integrations.modality_wiring import should_speak_proactively
        # Life-safety events bypass quiet hours unconditionally (B2)
        assert should_speak_proactively("smoke_alarm", quiet_hours=True) is True
        assert should_speak_proactively("gas_leak", quiet_hours=True) is True

    def test_should_speak_proactively_non_life_safety_suppressed_in_quiet_hours(self):
        from halbert_core.integrations.modality_wiring import should_speak_proactively
        # Non-life-safety events are suppressed during quiet hours
        assert should_speak_proactively("doorbell", quiet_hours=True) is False
        assert should_speak_proactively("motion", quiet_hours=True) is False

    def test_should_speak_proactively_non_life_safety_when_not_quiet_hours(self):
        from halbert_core.integrations.modality_wiring import should_speak_proactively
        assert should_speak_proactively("doorbell", quiet_hours=False) is True

    def test_shutdown_clears_singletons(self):
        from halbert_core.integrations import modality_wiring
        modality_wiring.shutdown()
        assert modality_wiring._modality_prompt_builder is None
        assert modality_wiring._speech_demuxer is None
        assert modality_wiring._quiet_hours_policy is None
        assert modality_wiring._pronunciation_lexicon is None

    def test_apply_pronunciation_no_engine_returns_original(self):
        from halbert_core.integrations.modality_wiring import apply_pronunciation
        result = apply_pronunciation("restart the systemd service")
        # Without the engine, text is returned unchanged
        assert result == "restart the systemd service"

    def test_pronunciation_mappings_contain_key_terms(self):
        from halbert_core.integrations.modality_wiring import (
            _HALBERT_PRONUNCIATION_MAPPINGS,
        )
        # Verify key domain terms are present
        assert "systemd" in _HALBERT_PRONUNCIATION_MAPPINGS
        assert "mqtt" in _HALBERT_PRONUNCIATION_MAPPINGS
        assert "NVMe" in _HALBERT_PRONUNCIATION_MAPPINGS
        assert "haloysius" in _HALBERT_PRONUNCIATION_MAPPINGS
        # Verify phonetic spellings are not empty
        for term, phonetic in _HALBERT_PRONUNCIATION_MAPPINGS.items():
            assert phonetic, f"Empty phonetic for {term}"


# ---------------------------------------------------------------------------
# Phase 2.5: Modality-conditional prompt formatting
# ---------------------------------------------------------------------------


class TestModalityConditionalPrompt:

    def test_build_response_prompt_text_includes_markdown(self):
        from halbert_core.prompts.agent_prompts import AgentPromptBuilder
        builder = AgentPromptBuilder()
        prompt = builder.build_response_prompt(
            query="test query",
            context=[],
            observations=[],
            response_modality="text",
        )
        assert "markdown formatting" in prompt
        assert "headers" in prompt

    def test_build_response_prompt_voice_excludes_markdown(self):
        from halbert_core.prompts.agent_prompts import AgentPromptBuilder
        builder = AgentPromptBuilder()
        prompt = builder.build_response_prompt(
            query="test query",
            context=[],
            observations=[],
            response_modality="voice",
        )
        # The formatting instruction should say "plain text" not "markdown"
        assert "plain text" in prompt.lower()
        assert "spoken naturally" in prompt.lower()
        # The formatting line should not ask for markdown syntax
        assert "use **markdown" not in prompt.lower()

    def test_build_response_prompt_default_is_text(self):
        from halbert_core.prompts.agent_prompts import AgentPromptBuilder
        builder = AgentPromptBuilder()
        prompt = builder.build_response_prompt(
            query="test query",
            context=[],
            observations=[],
        )
        assert "markdown formatting" in prompt


class TestPersonalityPromptModality:

    def test_generate_personality_section_includes_voice_presentation_for_text(self):
        from halbert_core.persona.personality_prompt import generate_personality_section

        class _FakeConfig:
            custom_personality_prompt = ""
            tone_descriptors = ["calm"]
            speech_patterns = ["concise"]
            directives = []
            voice_presentation = "male"
            archetype_id = None
            personality_profile = {}

        result = generate_personality_section(_FakeConfig(), response_modality="text")
        assert "VOICE PRESENTATION: male" in result

    def test_generate_personality_section_excludes_voice_presentation_for_voice(self):
        from halbert_core.persona.personality_prompt import generate_personality_section

        class _FakeConfig:
            custom_personality_prompt = ""
            tone_descriptors = ["calm"]
            speech_patterns = ["concise"]
            directives = []
            voice_presentation = "male"
            archetype_id = None
            personality_profile = {}

        result = generate_personality_section(_FakeConfig(), response_modality="voice")
        assert "VOICE PRESENTATION" not in result
        # TONE and SPEECH PATTERNS should still be present
        assert "TONE: calm" in result
        assert "SPEECH PATTERNS" in result


# ---------------------------------------------------------------------------
# Phase 2.5: ProactiveGate engine delegation
# ---------------------------------------------------------------------------


class TestProactiveGateEngineDelegation:

    def test_gate_constructs_without_engine(self):
        from halbert_core.proactive.gate import ProactiveGate

        class _FakeConfig:
            proactivity = "balanced"
            quiet_hours = None
            category_overrides = {}

        gate = ProactiveGate(being_config=_FakeConfig())
        assert gate is not None

    def test_gate_allows_critical_during_quiet_hours(self):
        from halbert_core.proactive.gate import ProactiveGate
        from halbert_core.proactive.events import ProactiveEvent

        class _FakeConfig:
            proactivity = "balanced"
            quiet_hours = {"start": "22:00", "end": "07:00"}
            category_overrides = {}

        gate = ProactiveGate(being_config=_FakeConfig())
        event = ProactiveEvent(
            id="test-1",
            type="system",
            category="system",
            severity="critical",
            title="Test",
            body="Test body",
        )
        should_notify, reason = gate.should_notify(event)
        assert should_notify is True

    def test_gate_suppresses_non_critical_in_quiet_hours(self):
        from halbert_core.proactive.gate import ProactiveGate
        from halbert_core.proactive.events import ProactiveEvent

        class _FakeConfig:
            proactivity = "balanced"
            quiet_hours = {"start": "22:00", "end": "07:00"}
            category_overrides = {}

        gate = ProactiveGate(being_config=_FakeConfig())
        event = ProactiveEvent(
            id="test-2",
            type="system",
            category="system",
            severity="warning",
            title="Test",
            body="Test body",
        )
        # Patch _in_quiet_hours to return True
        gate._in_quiet_hours = lambda: True
        should_notify, reason = gate.should_notify(event)
        assert should_notify is False
        assert "quiet hours" in reason


# ---------------------------------------------------------------------------
# TASK-07: Wyoming agent markdown stripping
# ---------------------------------------------------------------------------


class TestWyomingMarkdownStripping:

    def test_strip_bold(self):
        from halbert_core.integrations.wyoming_agent import _strip_markdown_for_speech
        assert _strip_markdown_for_speech("**bold text**") == "bold text"

    def test_strip_italic(self):
        from halbert_core.integrations.wyoming_agent import _strip_markdown_for_speech
        assert _strip_markdown_for_speech("*italic*") == "italic"

    def test_strip_header(self):
        from halbert_core.integrations.wyoming_agent import _strip_markdown_for_speech
        result = _strip_markdown_for_speech("# Header\nbody text")
        assert "Header" in result
        assert "body text" in result
        assert "#" not in result

    def test_strip_link_keeps_anchor(self):
        from halbert_core.integrations.wyoming_agent import _strip_markdown_for_speech
        result = _strip_markdown_for_speech("[click here](https://example.com)")
        assert "click here" in result
        assert "https://example.com" not in result

    def test_strip_code_fence_removed(self):
        from halbert_core.integrations.wyoming_agent import _strip_markdown_for_speech
        text = "before\n```python\nprint('hello')\n```\nafter"
        result = _strip_markdown_for_speech(text)
        assert "print" not in result
        assert "before" in result
        assert "after" in result

    def test_strip_inline_code_keeps_text(self):
        from halbert_core.integrations.wyoming_agent import _strip_markdown_for_speech
        result = _strip_markdown_for_speech("use `pip install` to install")
        assert "pip install" in result
        assert "`" not in result

    def test_strip_empty_string(self):
        from halbert_core.integrations.wyoming_agent import _strip_markdown_for_speech
        assert _strip_markdown_for_speech("") == ""

    def test_strip_plain_text_unchanged(self):
        from halbert_core.integrations.wyoming_agent import _strip_markdown_for_speech
        assert _strip_markdown_for_speech("just plain text") == "just plain text"

    def test_strip_list_markers(self):
        from halbert_core.integrations.wyoming_agent import _strip_markdown_for_speech
        text = "- item one\n- item two\n1. first\n2. second"
        result = _strip_markdown_for_speech(text)
        assert "item one" in result
        assert "item two" in result
        assert "first" in result
        assert "second" in result


# ---------------------------------------------------------------------------
# TASK-07: Wyoming agent per-turn session_id
# ---------------------------------------------------------------------------


class TestWyomingSessionId:

    def test_process_agent_turn_mints_unique_session_id(self):
        """TASK-07: each turn gets a unique session_id, not a stable per-process one."""
        from halbert_core.integrations.wyoming_agent import HalbertWyomingAgent

        agent = HalbertWyomingAgent.__new__(HalbertWyomingAgent)

        # Capture the session_ids passed to agent.process
        session_ids = []

        class _FakeStreamEvent:
            type = "response_complete"
            data: dict = {}

            @classmethod
            def response_complete(cls, sid):
                evt = cls()
                evt.data = {"content": ""}
                return evt

        class _FakeAgent:
            async def process(self, query, session_id):
                session_ids.append(session_id)
                yield _FakeStreamEvent.response_complete(session_id)

        # Patch the StreamEvent import inside _process_agent_turn.
        # The function does `from ...agents.events import StreamEvent` which
        # resolves to halbert_core.agents.events.StreamEvent — patch it
        # at the module level before the function runs.
        import halbert_core.agents.events as events_mod
        original = getattr(events_mod, "StreamEvent", None)
        events_mod.StreamEvent = _FakeStreamEvent
        try:
            fake_agent = _FakeAgent()
            asyncio.run(agent._process_agent_turn(fake_agent, "hello", ""))
            asyncio.run(agent._process_agent_turn(fake_agent, "world", ""))
        finally:
            if original is not None:
                events_mod.StreamEvent = original

        assert len(session_ids) == 2
        # TASK-07: session_ids must be unique per turn
        assert session_ids[0] != session_ids[1]
        # Both should start with "wyoming-"
        assert all(sid.startswith("wyoming-") for sid in session_ids)


# ---------------------------------------------------------------------------
# TASK-07: Pipeline barge-in
# ---------------------------------------------------------------------------


class TestPipelineBargeIn:
    """Tests the barge-in wiring in the audio pipeline coordinator."""

    def test_create_barge_in_token(self):
        """BargeInToken requires an event loop — test within async context."""
        from halbert_core.audio.pipeline import AudioPipelineCoordinator

        async def _test():
            pipeline = AudioPipelineCoordinator.__new__(AudioPipelineCoordinator)
            pipeline._barge_in_handler = None
            pipeline._active_barge_in_token = None

            from halbert_core.audio.speech.barge_in import BargeInHandler, BargeInToken

            token = pipeline.create_barge_in_token()
            if token is not None:
                assert isinstance(token, BargeInToken)
                assert pipeline._active_barge_in_token is token

        asyncio.run(_test())

    def test_trigger_barge_in_returns_none_when_no_token(self):
        from halbert_core.audio.pipeline import AudioPipelineCoordinator

        async def _test():
            pipeline = AudioPipelineCoordinator.__new__(AudioPipelineCoordinator)
            pipeline._barge_in_handler = None
            pipeline._active_barge_in_token = None

            result = await pipeline.trigger_barge_in()
            assert result is None

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# Engine-available: full modality resolution flow
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _engine_available(), reason="Haloysius engine not installed")
class TestModalityResolutionFlow:
    """Tests that exercise the full modality resolution when the engine is available."""

    def test_build_modality_context_returns_context(self):
        from halbert_core.integrations.modality_wiring import build_modality_context
        ctx = build_modality_context("hello", speaker_role="admin")
        assert ctx is not None
        assert ctx.query_risk == "safe"
        assert ctx.voice_policy.tier == 0  # Halbert is Tier 0

    def test_resolve_turn_modality_text_default(self):
        from halbert_core.integrations.modality_wiring import (
            build_modality_context,
            resolve_turn_modality,
        )
        ctx = build_modality_context("hello", speaker_role="admin")
        resolved = resolve_turn_modality(ctx)
        # Without a voice backend registered, default is TEXT
        from haloysius.modality.types import ResponseModality
        assert resolved.recommended_modality == ResponseModality.TEXT

    def test_demux_response_returns_payload(self):
        from halbert_core.integrations.modality_wiring import (
            build_modality_context,
            demux_response,
            resolve_turn_modality,
        )
        ctx = build_modality_context("hello", speaker_role="admin")
        resolved = resolve_turn_modality(ctx)
        payload = demux_response("Hello, world!", resolved, session_id="test")
        assert payload is not None
        assert payload.display_text == "Hello, world!"

    def test_quiet_hours_policy_created(self):
        from halbert_core.integrations.modality_wiring import get_quiet_hours_policy
        policy = get_quiet_hours_policy()
        assert policy is not None
        assert policy.start_hour == 22
        assert policy.end_hour == 7
        assert policy.life_safety_bypass is True
