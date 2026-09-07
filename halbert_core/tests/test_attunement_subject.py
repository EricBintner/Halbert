# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Subject resolution (A-HB-3).

``HalbertVoiceAuthGate.identify_speaker`` collapses three different situations
onto ``speaker_id=None``: a text turn with no audio, a missing speaker model,
and a voice that failed to match. The engine's "unknown speaker inherits the
most restrictive active request" rule is right for the third and catastrophic
for the first — it would apply the household's strictest quiet request to a
person typing at the keyboard, which is the strongest evidence of engagement
we ever get.

These tests pin the un-collapsing.
"""

from dataclasses import dataclass
from typing import Optional

import pytest

from halbert_core.attunement.subject import (
    Channel,
    SubjectConfidence,
    resolve_subject,
)


@dataclass(frozen=True)
class FakeSpeaker:
    """Duck-type of the engine's SpeakerIdentity, so this suite runs with the
    engine absent."""

    speaker_id: Optional[str] = None
    speaker_role: str = "unknown"
    confidence: float = 0.0
    verified: bool = False


def test_authenticated_dashboard_turn_is_identified():
    r = resolve_subject(channel=Channel.DASHBOARD, authenticated=True)
    assert r.confidence is SubjectConfidence.IDENTIFIED
    assert r.subject_id == "primary"
    assert r.max_scope_entity_wide is True


def test_local_typed_turn_is_unattributed_not_unknown():
    """Possession of the host is evidence. An unattributed turn is the default
    subject and must not inherit the most restrictive household request."""
    r = resolve_subject(channel=Channel.LOCAL_TEXT, authenticated=False)
    assert r.confidence is SubjectConfidence.UNATTRIBUTED
    assert r.subject_id == "primary"
    assert r.max_scope_entity_wide is True


def test_verified_voice_is_identified_by_speaker_id():
    r = resolve_subject(
        channel=Channel.VOICE,
        speaker=FakeSpeaker(speaker_id="eric", speaker_role="admin",
                            confidence=0.91, verified=True),
    )
    assert r.confidence is SubjectConfidence.IDENTIFIED
    assert r.subject_id == "eric"
    assert r.max_scope_entity_wide is True


def test_guest_voice_may_quiet_a_room_but_not_the_house():
    r = resolve_subject(
        channel=Channel.VOICE,
        speaker=FakeSpeaker(speaker_id="guest-3", speaker_role="guest",
                            confidence=0.64, verified=True),
        area_id="kitchen",
    )
    assert r.confidence is SubjectConfidence.IDENTIFIED
    assert r.max_scope_entity_wide is False
    assert r.scope_key == "kitchen"


def test_unverified_voice_is_unknown():
    r = resolve_subject(
        channel=Channel.VOICE,
        speaker=FakeSpeaker(speaker_id=None, speaker_role="unknown", verified=False),
        area_id="kitchen",
    )
    assert r.confidence is SubjectConfidence.UNKNOWN
    assert r.max_scope_entity_wide is False


def test_satellite_without_a_speaker_model_is_unknown_and_area_scoped():
    """The common install: openwakeword and CAM++ are optional extras."""
    r = resolve_subject(channel=Channel.SATELLITE, speaker=None, area_id="study")
    assert r.confidence is SubjectConfidence.UNKNOWN
    assert r.max_scope_entity_wide is False
    assert r.scope_key == "study"


def test_a_voice_turn_with_no_speaker_object_is_never_unattributed():
    """Regression guard for the collapse this module exists to undo: audio
    with no identity is not the same as typing at the keyboard."""
    r = resolve_subject(channel=Channel.VOICE, speaker=None)
    assert r.confidence is SubjectConfidence.UNKNOWN


@pytest.mark.parametrize("channel", [Channel.DASHBOARD, Channel.LOCAL_TEXT])
def test_typed_channels_never_resolve_to_unknown(channel):
    """The property the whole module protects."""
    r = resolve_subject(channel=channel, authenticated=False)
    assert r.confidence is not SubjectConfidence.UNKNOWN


def test_confidence_values_match_the_engine_contract():
    assert SubjectConfidence.IDENTIFIED.value == "identified"
    assert SubjectConfidence.UNATTRIBUTED.value == "unattributed"
    assert SubjectConfidence.UNKNOWN.value == "unknown"
