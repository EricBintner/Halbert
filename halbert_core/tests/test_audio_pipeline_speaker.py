# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Task O4: the last identified speaker surfaces on ``get_status()``.

The speech track already builds a ``VoiceTurnObservation`` with
``speaker_name`` / ``speaker_role`` / ``speaker_confidence`` per turn, but
the coordinator never remembered it, so ``/api/audio/status`` (which returns
``coordinator.get_status()`` verbatim since O1) had no way to tell the
frontend who was talking. These tests pin:

  1. ``speaker`` is ``null`` before any speech-track turn has run.
  2. After a recognized turn, ``speaker`` carries the observation's name,
     role, and confidence — and never the transcript text (the payload is a
     status frame, not a log of what was said).
  3. A match whose profile is absent stays truthful: empty name, role
     ``"unknown"``, real confidence — no invented "Unknown" string.
  4. A turn with no match at all updates the badge to an unidentified
     observation rather than leaving a stale identification behind.
  5. Wyoming satellite transcripts (which perform no speaker ID) never
     clobber a real identification.
"""
from __future__ import annotations

import pytest

from halbert_core.audio.config import AudioConfig
from halbert_core.audio.pipeline import AudioPipelineCoordinator
from halbert_core.audio.speech.speaker_id import SpeakerMatch


# 1s of 16kHz 16-bit mono (values are irrelevant — every engine is stubbed).
SAMPLE_PCM = b"\x00\x01" * 16_000


class _StubASR:
    """ASR stand-in that always hears the same sentence."""

    def __init__(self, text: str):
        self._text = text

    def transcribe_chunk(self, pcm: bytes) -> str:
        return self._text


class _StubSpeakerID:
    """SpeakerIdentifier stand-in that always answers with one match."""

    def __init__(self, match):
        self._match = match
        self.calls = 0

    def identify(self, pcm: bytes):
        self.calls += 1
        return self._match


class _StubProfile:
    """SpeakerProfile stand-in (only name/role are read)."""

    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role


class _StubStore:
    """SpeakerProfileStore stand-in for a single enrolled profile."""

    def __init__(self, profile):
        self._profile = profile

    def get(self, speaker_id: str):
        return self._profile


@pytest.fixture
def coordinator(monkeypatch, request):
    """Hermetic coordinator: stub ASR + speaker ID + profile store.

    Parameterize via ``request.param`` = (match, profile_or_None). Uses the
    O2/O3 hermetic pattern — the real ``AudioPipelineCoordinator`` is built
    but no engine ever touches sherpa-onnx, disk, or the network.
    """
    match, profile = request.param
    monkeypatch.setattr(
        "halbert_core.audio.storage.speaker_store.SpeakerProfileStore",
        lambda: _StubStore(profile),
    )
    coord = AudioPipelineCoordinator(config=AudioConfig(enabled=True))
    coord._asr = _StubASR("turn on the desk lamp")
    coord._speaker_id = _StubSpeakerID(match)
    return coord


async def _run_speech_turn(coord: AudioPipelineCoordinator, area_id: str = "office"):
    """Drive the real speech-segment code path once."""
    await coord._ring_buffer.write(SAMPLE_PCM)
    await coord._process_speech_segment("browser", area_id)


class TestSpeakerStatusNullBeforeSpeech:
    @pytest.mark.parametrize(
        "coordinator",
        [(
            SpeakerMatch(speaker_id="spk-1", name="Eric", role="admin", confidence=0.93),
            _StubProfile("Eric", "admin"),
        )],
        indirect=True,
    )
    async def test_speaker_is_null_before_any_speech(self, coordinator):
        assert coordinator.get_status()["speaker"] is None


class TestSpeakerStatusCarriesIdentification:
    @pytest.mark.parametrize(
        "coordinator",
        [(
            SpeakerMatch(speaker_id="spk-1", name="Eric", role="admin", confidence=0.93),
            _StubProfile("Eric", "admin"),
        )],
        indirect=True,
    )
    async def test_identified_speaker_reaches_status(self, coordinator):
        await _run_speech_turn(coordinator)

        speaker = coordinator.get_status()["speaker"]
        assert speaker == {"name": "Eric", "role": "admin", "confidence": 0.93}

    @pytest.mark.parametrize(
        "coordinator",
        [(
            SpeakerMatch(speaker_id="spk-1", name="Eric", role="admin", confidence=0.93),
            _StubProfile("Eric", "admin"),
        )],
        indirect=True,
    )
    async def test_status_carries_confidence_not_transcript(self, coordinator):
        """The status frame may name WHO spoke, never WHAT was said."""
        await _run_speech_turn(coordinator)

        raw = str(coordinator.get_status())
        assert "desk lamp" not in raw
        assert "turn on" not in raw

    @pytest.mark.parametrize(
        "coordinator",
        [(
            SpeakerMatch(speaker_id="spk-1", name="Eric", role="admin", confidence=0.93),
            _StubProfile("Eric", "admin"),
        )],
        indirect=True,
    )
    async def test_real_code_path_ran_speaker_id(self, coordinator):
        """Guard against a stub short-circuit: identify() must be reached."""
        await _run_speech_turn(coordinator)
        assert coordinator._speaker_id.calls == 1


class TestUnknownSpeakerIsTruthful:
    @pytest.mark.parametrize(
        "coordinator",
        [(
            SpeakerMatch(speaker_id="spk-unenrolled", name="", role="", confidence=0.81),
            None,
        )],
        indirect=True,
    )
    async def test_match_without_profile_stays_truthful(self, coordinator):
        """No enrolled profile: empty name, role 'unknown', real confidence."""
        await _run_speech_turn(coordinator)

        speaker = coordinator.get_status()["speaker"]
        assert speaker == {"name": "", "role": "unknown", "confidence": 0.81}

    @pytest.mark.parametrize(
        "coordinator",
        [(
            SpeakerMatch(speaker_id="spk-1", name="Eric", role="admin", confidence=0.93),
            _StubProfile("Eric", "admin"),
        )],
        indirect=True,
    )
    async def test_unmatched_turn_updates_status_to_unidentified(self, coordinator):
        """A turn no one recognizes must not leave a stale identification.

        The first turn is identified; the second returns no match. The
        status then truthfully reports the last turn was from an
        unidentified speaker (empty name, 'unknown' role, confidence 0).
        """
        await _run_speech_turn(coordinator)
        assert coordinator.get_status()["speaker"]["name"] == "Eric"

        coordinator._speaker_id = _StubSpeakerID(None)
        await _run_speech_turn(coordinator)

        speaker = coordinator.get_status()["speaker"]
        assert speaker == {"name": "", "role": "unknown", "confidence": 0.0}


class TestWyomingTranscriptsNeverClobberIdentification:
    @pytest.mark.parametrize(
        "coordinator",
        [(
            SpeakerMatch(speaker_id="spk-1", name="Eric", role="admin", confidence=0.93),
            _StubProfile("Eric", "admin"),
        )],
        indirect=True,
    )
    async def test_satellite_transcript_preserves_badge(self, coordinator):
        """Wyoming satellites do no speaker ID — a transcript (speaker_role
        'unknown', no identification) must not erase a real match."""
        await _run_speech_turn(coordinator)
        assert coordinator.get_status()["speaker"]["name"] == "Eric"

        await coordinator._handle_wyoming_transcript(
            "turn on the lights", conversation_id="ha-42", area_id="kitchen",
        )

        speaker = coordinator.get_status()["speaker"]
        assert speaker == {"name": "Eric", "role": "admin", "confidence": 0.93}
