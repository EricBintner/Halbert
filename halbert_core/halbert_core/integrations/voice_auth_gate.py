# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""HalbertVoiceAuthGate — wraps CAM++ SpeakerIdentifier + RoleGate.

Implements the engine's ``VoiceAuthGate`` Protocol (spec section 5.9). The
engine's wiring layer calls ``identify_speaker()`` to populate
``ModalityContext.speaker`` (a ``SpeakerIdentity``), then the resolver uses
the speaker's role + verification state to apply graduated risk tightening
(spec 5.9: unverified/unknown/restricted speakers get the most restrictive
spoken policy).

Two layers compose here:

1. **CAM++ biometrics** (``SpeakerIdentifier``): extracts a 256-dim embedding
   from PCM audio and matches it against enrolled profiles via cosine
   similarity. The engine defines the threshold bands
   (``VoiceAuthThresholds``: 0.82 admin, 0.70 member, 0.60 guest); this gate
   applies them via ``classify_speaker_role()``.

2. **RoleGate** (``tools.role_gate.py``): enforces speaker-role-based access
   control on tool execution. ``authorize_voice_action()`` delegates to
   ``RoleGate.classify()`` to produce an ``ActionDecision``.

Decision 51 (spec 5.9): ``identify_speaker(audio_features=None)`` returns
``SpeakerIdentity(verified=False, speaker_role="unknown")`` when no audio
is available. The engine treats ``speaker=None`` (no gate registered) as
"opt out of biometric risk hobble" — but a registered gate that returns an
unverified identity applies the tightening. This gate is only registered
when the audio pipeline has a speaker-id engine; text-only deployments
register nothing, so the engine's ``speaker`` default (unverified) is NOT
applied (the gate is absent, not returning unverified).

Lazy: ``sherpa_onnx`` and ``SpeakerIdentifier`` are imported on first use.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("halbert.integrations.voice_auth_gate")


class HalbertVoiceAuthGate:
    """VoiceAuthGate Protocol implementation wrapping CAM++ + RoleGate.

    The engine's ``VoiceAuthGate`` Protocol (runtime_checkable, structural):
    ``identify_speaker()``, ``authorize_voice_action()``.
    """

    def __init__(
        self,
        speaker_identifier: Any = None,
        role_gate: Any = None,
        thresholds: Any = None,
    ):
        # ``speaker_identifier`` is a SpeakerIdentifier instance (or mock).
        # ``role_gate`` is a RoleGate instance (or mock).
        # Both are lazy-constructed if None.
        self._speaker_id = speaker_identifier
        self._role_gate = role_gate
        self._thresholds = thresholds

    # ------------------------------------------------------------------
    # VoiceAuthGate Protocol
    # ------------------------------------------------------------------

    def identify_speaker(
        self,
        audio_features: Optional[Any] = None,
    ) -> Any:  # SpeakerIdentity (engine type)
        """Resolve speaker identity from audio features or session state.

        Args:
            audio_features: PCM bytes (16-bit, 16kHz, mono) from the current
                voice turn, or None when no audio is available (text mode).

        Returns:
            A ``SpeakerIdentity`` with:
            - ``speaker_id``: the matched profile ID, or None.
            - ``speaker_role``: 'admin', 'member', 'guest', 'restricted',
              or 'unknown' (classified via the engine's threshold bands).
            - ``confidence``: CAM++ cosine similarity score.
            - ``verified``: True if confidence >= the guest threshold (0.60).
            - ``voice_pin_challenged``: True when role is 'guest' (PIN or
              screen gate required per spec 5.9).

        When ``audio_features`` is None (no audio), returns an unverified
        'unknown' identity — the engine applies the most restrictive policy.
        When the speaker-id model is not installed, returns unverified
        'unknown' (graceful degradation, spec 5.9).
        """
        from haloysius.modality.types import SpeakerIdentity
        from haloysius.seam import (
            DEFAULT_VOICE_AUTH_THRESHOLDS,
            classify_speaker_role,
        )

        thresholds = self._thresholds or DEFAULT_VOICE_AUTH_THRESHOLDS

        if audio_features is None:
            return SpeakerIdentity(
                speaker_id=None,
                speaker_role="unknown",
                confidence=0.0,
                verified=False,
                voice_pin_challenged=False,
            )

        try:
            identifier = self._get_speaker_id()
        except Exception as e:
            logger.warning(f"SpeakerIdentifier unavailable: {e}")
            return SpeakerIdentity(
                speaker_id=None,
                speaker_role="unknown",
                confidence=0.0,
                verified=False,
            )

        try:
            match = identifier.identify(audio_features)
        except Exception as e:
            logger.warning(f"Speaker identification failed: {e}")
            return SpeakerIdentity(
                speaker_id=None,
                speaker_role="unknown",
                confidence=0.0,
                verified=False,
            )

        if match is None:
            # No enrolled speaker matched above threshold.
            return SpeakerIdentity(
                speaker_id=None,
                speaker_role="unknown",
                confidence=0.0,
                verified=False,
            )

        # Classify the role from the confidence score using the engine's bands.
        role = classify_speaker_role(match.confidence, thresholds)
        verified = match.confidence >= thresholds.guest
        pin_challenged = role == "guest"  # spec 5.9: guest band needs PIN/screen gate

        # Look up the human-readable name from the speaker store.
        speaker_name = match.name
        if not speaker_name and match.speaker_id:
            try:
                from ..audio.storage.speaker_store import SpeakerProfileStore
                store = SpeakerProfileStore()
                profile = store.get(match.speaker_id)
                if profile:
                    speaker_name = profile.name
                    # The store's role may be more specific than the band classification.
                    role = profile.role or role
            except Exception:
                pass

        return SpeakerIdentity(
            speaker_id=match.speaker_id,
            speaker_role=role,
            confidence=match.confidence,
            verified=verified,
            voice_pin_challenged=pin_challenged,
        )

    def authorize_voice_action(
        self,
        action: str,
        speaker: Any,  # SpeakerIdentity (engine type)
    ) -> Any:  # ActionDecision (engine type)
        """Authorize an action for this speaker via the voice channel.

        Delegates to ``RoleGate.classify()`` which wraps
        ``ToolSafetyFramework.classify()`` and enforces the role-based risk
        cap (admin=full, member=HIGH, guest=MEDIUM, restricted=LOW,
        unknown=MEDIUM+confirmation for HIGH).

        Returns an ``ActionDecision``:
        - ``allow()`` when the role's cap permits the action's risk level.
        - ``require_approval()`` when an unknown speaker attempts a HIGH-risk
          action (PIN prompt).
        - ``deny()`` when the action's risk exceeds the role's cap.
        """
        from haloysius.seam import ActionDecision

        gate = self._get_role_gate()
        if gate is None:
            # No RoleGate — allow (the ToolSafetyFramework's own classification
            # is the backstop; the gate is an additional tightening layer).
            return ActionDecision.allow("no role gate registered")

        try:
            result = gate.classify(action, {}, speaker_role=speaker.speaker_role)
        except Exception as e:
            logger.warning(f"RoleGate classify failed: {e}")
            return ActionDecision.deny(f"authorization check failed: {e}")

        if result.allowed and not result.requires_confirmation:
            return ActionDecision.allow(result.reason)
        if result.requires_confirmation:
            return ActionDecision.require_approval(result.reason)
        return ActionDecision.deny(result.reason)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_speaker_id(self) -> Any:
        """Return the SpeakerIdentifier, lazy-constructing if needed."""
        if self._speaker_id is None:
            from ..audio.speech.speaker_id import SpeakerIdentifier
            self._speaker_id = SpeakerIdentifier()
        return self._speaker_id

    def _get_role_gate(self) -> Any:
        """Return the RoleGate, lazy-constructing if needed."""
        if self._role_gate is None:
            try:
                from ..tools.safety import ToolSafetyFramework
                from ..tools.role_gate import RoleGate
                self._role_gate = RoleGate(ToolSafetyFramework())
            except Exception as e:
                logger.warning(f"Could not construct RoleGate: {e}")
                return None
        return self._role_gate
