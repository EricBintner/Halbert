# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Who is the persona talking to, and how sure are we (A-HB-3).

``integrations/voice_auth_gate.py`` returns ``speaker_id=None`` for three
unrelated situations — a text turn with no audio, an uninstalled speaker
model, and a voice that failed to match. The engine's most-restrictive
inheritance rule is correct for the last and wrong for the first, so this
module un-collapses them before a subject ever reaches the engine.

The rule that falls out, and the one property to preserve if this is ever
rewritten:

    **Entity-wide silence requires entity-level identity. Anything less
    quiets a room.**
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

DEFAULT_SUBJECT_ID = "primary"

#: Roles from ``integrations/role_gate`` that may create an entity-wide
#: standing request. A guest can quiet the room they are in; a guest cannot
#: silence the house for a week (§10.4 Q14).
_ENTITY_WIDE_ROLES = frozenset({"admin", "member"})


class SubjectConfidence(str, Enum):
    """Mirror of the engine's ``SubjectConfidence``. Values must stay identical."""

    IDENTIFIED = "identified"
    """A resolved subject: an authenticated session, or a matched voice."""

    UNATTRIBUTED = "unattributed"
    """No identity, but the channel implies the trusted primary user — a typed
    turn on this host. Treated as the default subject; never inherits the
    most restrictive household request."""

    UNKNOWN = "unknown"
    """An unresolved speaker in a shared space. Inherits most-restrictive for
    un-addressed push, per the engine's §5.10."""


class Channel(str, Enum):
    """How the turn reached us. Determines what identity is even possible."""

    DASHBOARD = "dashboard"
    LOCAL_TEXT = "local_text"
    VOICE = "voice"
    SATELLITE = "satellite"


@dataclass(frozen=True)
class SubjectResolution:
    subject_id: str
    confidence: SubjectConfidence
    max_scope_entity_wide: bool
    scope_key: Optional[str] = None
    reason: str = ""


_TYPED_CHANNELS = (Channel.DASHBOARD, Channel.LOCAL_TEXT)


def resolve_subject(
    *,
    channel: Channel,
    speaker: Any = None,
    authenticated: bool = False,
    area_id: Optional[str] = None,
) -> SubjectResolution:
    """Resolve the subject for a turn.

    Args:
        channel: how the turn arrived.
        speaker: the engine's ``SpeakerIdentity`` (duck-typed on
            ``speaker_id`` / ``speaker_role`` / ``verified``), or None.
        authenticated: the session carried an identity of its own.
        area_id: the area the turn was heard in; becomes the scope key for
            anyone who may not create an entity-wide request.
    """
    if channel in _TYPED_CHANNELS:
        # Typing is the strongest evidence of engagement we ever get, and the
        # keyboard is on the host. Never unknown.
        if authenticated:
            return SubjectResolution(
                subject_id=DEFAULT_SUBJECT_ID,
                confidence=SubjectConfidence.IDENTIFIED,
                max_scope_entity_wide=True,
                reason="session_identity",
            )
        return SubjectResolution(
            subject_id=DEFAULT_SUBJECT_ID,
            confidence=SubjectConfidence.UNATTRIBUTED,
            max_scope_entity_wide=True,
            reason="host_possession",
        )

    # Spoken channels. Absent or unverified identity is genuinely unknown —
    # the microphone hears a room, not a person.
    speaker_id = getattr(speaker, "speaker_id", None)
    verified = bool(getattr(speaker, "verified", False))
    role = getattr(speaker, "speaker_role", "unknown") or "unknown"

    if speaker is None or not verified or not speaker_id:
        return SubjectResolution(
            subject_id=DEFAULT_SUBJECT_ID,
            confidence=SubjectConfidence.UNKNOWN,
            max_scope_entity_wide=False,
            scope_key=area_id,
            reason="unverified_voice",
        )

    entity_wide = role in _ENTITY_WIDE_ROLES
    return SubjectResolution(
        subject_id=speaker_id,
        confidence=SubjectConfidence.IDENTIFIED,
        max_scope_entity_wide=entity_wide,
        scope_key=None if entity_wide else area_id,
        reason=f"voice_match:{role}",
    )
