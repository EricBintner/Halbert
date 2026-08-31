# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Modality wiring — per-turn modality resolution, prompt injection, and delivery.

This module implements the Phase 2 per-turn flow (spec §6) connecting the
Haloysius modality-voice engine to Halbert's agent state machine:

1. **Build ModalityContext** from the turn's cognitive state, speaker
   identity, and channel capability.
2. **Resolve modality** via ``resolve_modality()`` — fills
   ``recommended_modality`` (TEXT/VOICE), ``prosody``, and
   ``voice_risk_policy``.
3. **Inject modality context** into the system prompt via
   ``ModalityAwarePromptBuilder`` (adds ``<modality_context>`` XML for
   VOICE turns, defangs user input).
4. **Demux the model response** via ``SpeechTextDemuxer.assemble_payload()``
   — splits into ``MultiStreamPayload`` with speech segments + display text.
5. **Deliver** — speak segments through the VoiceBackend, render
   display_text on screen, emit SSE events for the frontend.

All Haloysius imports are lazy so this module is importable without the
engine installed. When the engine is absent, every function degrades to
text-only (subtractive contract).

Halbert is Tier 0 (single-channel, PERSONA-only voice). Multi-occupant is
always on (smart-home context). Barge-in is ``cancel_all`` mode.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

logger = logging.getLogger("halbert.integrations.modality_wiring")

# Module-level singletons (built once, reused across turns)
_modality_prompt_builder: Any = None
_speech_demuxer: Any = None
_quiet_hours_policy: Any = None
_temporal_orchestrator: Any = None
_pronunciation_lexicon: Any = None


# ---------------------------------------------------------------------------
# Pronunciation lexicon (spec section 5.14)
# ---------------------------------------------------------------------------

# Halbert domain terms that Piper/sherpa-onnx mispronounce. These are
# technical terms, service names, and config paths common in sysadmin /
# smart-home contexts. The phonetic spelling guides the TTS engine to
# the correct pronunciation without requiring IPA support.
_HALBERT_PRONUNCIATION_MAPPINGS = {
    # Service names
    "systemd": "system-D",
    "journald": "journal-D",
    "dockerd": "docker-D",
    "NetworkManager": "Network Manager",
    "bluetoothd": "bluetooth-D",
    "wpa_supplicant": "W-P-A supplicant",
    "rsyslog": "R-syslog",
    "cron": "cron",
    "crond": "cron-D",
    # Smart-home / IoT
    "zigbee2mqtt": "zigbee to M-Q-T-T",
    "z2m": "Z-two-M",
    "homeassistant": "Home Assistant",
    "esphome": "E-S-P home",
    "wyoming": "wyoming",
    "piper": "piper",
    "sherpa": "sherpa",
    "onnx": "O-N-N-X",
    # Config / paths
    "fstab": "F-stab",
    "sshd_config": "S-S-H-D config",
    "sysctl": "sys-control",
    "iptables": "I-P tables",
    "nftables": "N-F tables",
    # Protocols
    "mqtt": "M-Q-T-T",
    "websocket": "web socket",
    "mDNS": "M-D-N-S",
    "avahi": "ah-vah-hee",
    "LLDP": "L-L-D-P",
    # Hardware
    "NVMe": "N-V-Me",
    "SATA": "S-A-T-A",
    "pcie": "P-C-I-Express",
    "Ryzen": "Rye-zen",
    "Epyc": "E-pick",
    # Halbert-specific
    "halbert": "halbert",
    "haloysius": "huh-loy-shus",
    "Tauri": "Tauri",
    "ChromaDB": "Chroma D-B",
    "ollama": "oh-lama",
    "llama": "lama",
    "mlx": "M-L-X",
}


def get_pronunciation_lexicon() -> Any:
    """Get or create the singleton PronunciationLexicon for Halbert.

    Populated with sysadmin / smart-home domain terms that Piper TTS
    mispronounces. Returns None if the engine is not installed.
    """
    global _pronunciation_lexicon
    if _pronunciation_lexicon is not None:
        return _pronunciation_lexicon
    if not _engine_available():
        return None
    try:
        from haloysius.modality.pronunciation import PronunciationLexicon
        lexicon = PronunciationLexicon(domain="halbert")
        lexicon.load_from_dict(_HALBERT_PRONUNCIATION_MAPPINGS)
        _pronunciation_lexicon = lexicon
        logger.info(
            f"PronunciationLexicon created for Halbert "
            f"({len(_HALBERT_PRONUNCIATION_MAPPINGS)} terms)"
        )
        return _pronunciation_lexicon
    except Exception as e:
        logger.warning(f"Could not create PronunciationLexicon: {e}")
        return None


def apply_pronunciation(text: str) -> str:
    """Apply pronunciation substitutions to text before TTS synthesis.

    Replaces domain terms with their phonetic spellings so Piper
    pronounces them correctly. Returns the original text unchanged if
    the engine is not installed.
    """
    lexicon = get_pronunciation_lexicon()
    if lexicon is None:
        return text
    try:
        return lexicon.apply(text)
    except Exception as e:
        logger.debug(f"Pronunciation substitution failed: {e}")
        return text


def _engine_available() -> bool:
    """Check if the Haloysius modality engine is importable."""
    try:
        import haloysius.modality.resolver  # noqa: F401
        return True
    except ImportError:
        return False


def get_modality_prompt_builder() -> Any:
    """Get or create the singleton ModalityAwarePromptBuilder.

    Returns None if the engine is not installed (text-only fallback).
    """
    global _modality_prompt_builder
    if _modality_prompt_builder is not None:
        return _modality_prompt_builder
    if not _engine_available():
        return None
    try:
        from haloysius.modality.prompt_builder import ModalityAwarePromptBuilder
        # Halbert's persona config — minimal, the builder adds modality context.
        persona_config = {
            "name": "Halbert",
            "tone_descriptors": ["calm", "precise", "helpful"],
        }
        _modality_prompt_builder = ModalityAwarePromptBuilder(persona_config)
        logger.info("ModalityAwarePromptBuilder created for Halbert")
        return _modality_prompt_builder
    except Exception as e:
        logger.warning(f"Could not create ModalityAwarePromptBuilder: {e}")
        return None


def get_speech_demuxer() -> Any:
    """Get or create the singleton SpeechTextDemuxer.

    Halbert uses VoicePolicy(tier=0) — single-channel, PERSONA-only.
    Returns None if the engine is not installed.
    """
    global _speech_demuxer
    if _speech_demuxer is not None:
        return _speech_demuxer
    if not _engine_available():
        return None
    try:
        from haloysius.modality.demuxer import SpeechTextDemuxer
        from haloysius.modality.types import VoicePolicy
        _speech_demuxer = SpeechTextDemuxer(voice_policy=VoicePolicy(tier=0))
        logger.info("SpeechTextDemuxer created for Halbert (Tier 0)")
        return _speech_demuxer
    except Exception as e:
        logger.warning(f"Could not create SpeechTextDemuxer: {e}")
        return None


def get_quiet_hours_policy() -> Any:
    """Get Halbert's quiet hours policy (spec section 5.10).

    Halbert: 22:00–07:00, whisper mode, life-safety bypass (advisory-only
    per B2 — the engine unconditionally bypasses for life-safety events).
    """
    global _quiet_hours_policy
    if _quiet_hours_policy is not None:
        return _quiet_hours_policy
    if not _engine_available():
        return None
    try:
        from haloysius.modality.types import QuietHoursPolicy
        _quiet_hours_policy = QuietHoursPolicy(
            enabled=True,
            start_hour=22,
            end_hour=7,
            reactive_voice_mode="whisper",
            proactive_advisory_mode="silent",
            life_safety_bypass=True,
            silence_narrator_in_whisper=True,
        )
        return _quiet_hours_policy
    except Exception as e:
        logger.warning(f"Could not create QuietHoursPolicy: {e}")
        return None


def is_quiet_hours() -> bool:
    """Check if the current time is within quiet hours (22:00–07:00)."""
    policy = get_quiet_hours_policy()
    if policy is None or not policy.enabled:
        return False
    import datetime
    now = datetime.datetime.now()
    hour = now.hour
    # Handle overnight range (22:00 → 07:00)
    if policy.start_hour > policy.end_hour:
        return hour >= policy.start_hour or hour < policy.end_hour
    return policy.start_hour <= hour < policy.end_hour


def build_modality_context(
    user_query: str,
    speaker_role: str = "unknown",
    audio_features: Optional[bytes] = None,
    query_risk: str = "safe",
    emotional_state: Optional[tuple] = None,
) -> Any:
    """Build a ModalityContext for the current turn.

    Assembles the per-turn context from:
    - Channel capability (from the seam — Tauri desktop / Wyoming state)
    - Speaker identity (from the VoiceAuthGate — CAM++ biometrics)
    - Cognitive state (PAD emotional state, query risk)
    - Quiet hours policy
    - Voice policy (Tier 0 for Halbert)

    The context is then passed to ``resolve_modality()`` which fills the
    channel fields from the seam and runs the pure resolver.

    Args:
        user_query: The user's message text.
        speaker_role: The verified speaker role ('admin', 'member', 'guest',
            'restricted', 'unknown'). For text turns, this is 'admin' (text
            chat is authenticated via the dashboard session).
        audio_features: PCM bytes for speaker identification (voice turns),
            or None for text turns.
        query_risk: The query risk level ('safe', 'low', 'medium', 'high',
            'critical'). Defaults to 'safe'.
        emotional_state: Optional (valence, arousal, dominance) tuple from
            the cognitive state. Defaults to (0.0, 0.0, 0.0).

    Returns:
        A ModalityContext, or None if the engine is not installed.
    """
    if not _engine_available():
        return None
    try:
        from haloysius.modality.types import (
            AreaContext,
            ModalityContext,
            SpeakerIdentity,
            VoicePolicy,
        )
    except ImportError:
        return None

    # Resolve speaker identity from the VoiceAuthGate (if audio available)
    speaker = SpeakerIdentity()  # default: unverified, unknown
    if audio_features is not None:
        try:
            from haloysius.seam import resolve_voice_auth_gate
            gate = resolve_voice_auth_gate()
            if gate is not None:
                speaker = gate.identify_speaker(audio_features)
        except Exception as e:
            logger.debug(f"Speaker identification skipped: {e}")
    else:
        # Text turn: set the role from the authenticated session.
        # speaker=None opts out of biometric risk hobble (decision 51).
        speaker = None  # type: ignore

    # Emotional state (PAD from PersonaCognition)
    valence, arousal, dominance = emotional_state or (0.0, 0.0, 0.0)

    # Quiet hours
    quiet_active = is_quiet_hours()
    quiet_policy = get_quiet_hours_policy()

    ctx = ModalityContext(
        query_risk=query_risk,
        speaker=speaker,
        emotional_valence=valence,
        emotional_arousal=arousal,
        emotional_dominance=dominance,
        quiet_hours_active=quiet_active,
        quiet_hours_policy=quiet_policy,
        voice_policy=VoicePolicy(tier=0),  # Halbert: Tier 0
        area=AreaContext(multi_occupant=True),  # always on for smart-home
    )
    return ctx


def resolve_turn_modality(ctx: Any) -> Any:
    """Resolve the modality for the current turn.

    Calls ``resolve_modality()`` which fills channel fields from the seam
    (VoiceBackend, ChannelCapability) and runs the pure ModalityResolver.
    The context is mutated in-place with ``recommended_modality``,
    ``prosody``, and ``voice_risk_policy``.

    Returns the resolved context, or None if the engine is not installed.
    """
    if ctx is None:
        return None
    try:
        from haloysius.modality.resolver import resolve_modality
        return resolve_modality(ctx)
    except Exception as e:
        logger.warning(f"Modality resolution failed: {e}")
        return ctx


def defang_user_input(user_text: str) -> str:
    """Strip modality control tags from untrusted user input (spec 5.11).

    Delegates to ``SpeechTextDemuxer.defang_input()`` when available;
    otherwise returns the text unchanged (text-only fallback).

    This prevents prompt injection where a user message carrying
    ``<speech>``/``<text>``/``<modality_context>`` tags could trick the
    model into speaking arbitrary content.
    """
    demuxer = get_speech_demuxer()
    if demuxer is None:
        return user_text
    try:
        return demuxer.defang_input(user_text)
    except Exception as e:
        logger.debug(f"Input defanging failed: {e}")
        return user_text


def demux_response(
    response: str,
    ctx: Any,
    session_id: str = "",
    thread_id: str = "",
) -> Any:
    """Demux the model response into a MultiStreamPayload.

    Splits the response into speech segments + display text using
    ``SpeechTextDemuxer.assemble_payload()``. Halbert is Tier 0
    (single PERSONA segment), multi_occupant=True (always on for
    smart-home), with the turn's resolved prosody and risk policy.

    Returns a MultiStreamPayload, or None if the engine is not installed.
    """
    if ctx is None:
        return None
    demuxer = get_speech_demuxer()
    if demuxer is None:
        return None
    try:
        from haloysius.modality.types import ResponseModality

        prosody = getattr(ctx, "prosody", None)
        risk_policy = getattr(ctx, "voice_risk_policy", None)
        modality = getattr(ctx, "recommended_modality", ResponseModality.TEXT)
        whisper = getattr(prosody, "whisper", False) if prosody else False

        payload = demuxer.assemble_payload(
            response,
            multi_occupant=True,  # always on for Halbert (smart-home)
            whisper_active=whisper,
            prosody=prosody,
            modality=modality,
            risk_policy=risk_policy,
            thread_id=thread_id,
            session_id=session_id or str(uuid.uuid4()),
        )
        return payload
    except Exception as e:
        logger.warning(f"Response demuxing failed: {e}")
        return None


def should_speak(ctx: Any) -> bool:
    """Check if the resolved modality indicates voice output."""
    if ctx is None:
        return False
    try:
        from haloysius.modality.types import ResponseModality
        modality = getattr(ctx, "recommended_modality", ResponseModality.TEXT)
        return modality in (ResponseModality.VOICE, ResponseModality.MIXED)
    except ImportError:
        return False


def get_speech_text(payload: Any) -> str:
    """Extract the spoken text from a MultiStreamPayload."""
    if payload is None:
        return ""
    return getattr(payload, "speech_text", "") or ""


def get_display_text(payload: Any) -> str:
    """Extract the display text from a MultiStreamPayload."""
    if payload is None:
        return ""
    return getattr(payload, "display_text", "") or ""


def get_prosody(ctx: Any) -> Any:
    """Extract the prosody hints from a resolved ModalityContext."""
    if ctx is None:
        return None
    return getattr(ctx, "prosody", None)


# ---------------------------------------------------------------------------
# Life-safety bypass (spec B2)
# ---------------------------------------------------------------------------

LIFE_SAFETY_EVENT_TYPES = frozenset({
    "smoke_alarm", "fire_alarm", "gas_leak",
    "carbon_monoxide", "co_alarm", "water_leak",
})


def is_life_safety_event(event_type: str) -> bool:
    """Check if an event type is a life-safety event that bypasses quiet hours."""
    return event_type.lower() in LIFE_SAFETY_EVENT_TYPES


def should_speak_proactively(event_type: str, quiet_hours: bool = False) -> bool:
    """Check if a proactive event should be spoken aloud.

    Life-safety events (smoke alarm, gas leak, etc.) bypass quiet hours
    unconditionally (B2: the engine logs a WARNING and still speaks even
    when ``life_safety_bypass=False`` is configured for testing).

    Non-life-safety events are suppressed during quiet hours.
    """
    if is_life_safety_event(event_type):
        return True  # unconditional bypass (B2)
    if quiet_hours:
        return False
    return True


def shutdown() -> None:
    """Clear module-level singletons."""
    global _modality_prompt_builder, _speech_demuxer, _quiet_hours_policy, _temporal_orchestrator, _pronunciation_lexicon
    _modality_prompt_builder = None
    _speech_demuxer = None
    _quiet_hours_policy = None
    _temporal_orchestrator = None
    _pronunciation_lexicon = None
