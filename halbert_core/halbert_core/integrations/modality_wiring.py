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
from typing import Any, Dict, Optional

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
    pronounces them correctly. The lexicon is local (a packaged term
    list) — it needs no engine — so substitution applies whenever a
    lexicon loads; only a missing or broken lexicon returns the text
    unchanged.
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


def get_persona_voice() -> tuple:
    """The active persona's voice identity, ``(PersonaVoiceProfile|None, voice_id)``.

    Reads ``voice_profile`` from being.yml — the ``VoiceProfileData``
    shape a cross-app persona export writes (``voice_id`` plus the five
    ``PersonaVoiceProfile`` fields). ``voice_id`` is the Kokoro voice
    pack id (e.g. ``"af_sarah"``); the other fields build the persona
    prosody base the ``ProsodyMapper`` blends against PAD.

    Returns ``(None, "")`` when no profile is configured or the engine
    is not installed — the subtractive default.
    """
    try:
        from ..config.being_config import load_being_config
        profile = getattr(load_being_config(), "voice_profile", None) or {}
    except Exception as e:
        logger.debug(f"persona voice_profile load skipped: {e}")
        return None, ""
    if not isinstance(profile, dict):
        return None, ""
    voice_id = profile.get("voice_id") or ""

    def _num(key: str, default: float) -> float:
        # ``or`` is wrong here: 0.0 is a legitimate value for every field
        # (weight=0.0 is a full-PAD blend), so falsy must not mean default.
        v = profile.get(key)
        return float(v) if v is not None else default

    try:
        from haloysius.modality.types import PersonaVoiceProfile
        pvp = PersonaVoiceProfile(
            base_rate=_num("base_rate", 1.0),
            base_pitch=_num("base_pitch", 0.0),
            base_energy=_num("base_energy", 0.5),
            cadence_style=profile.get("cadence_style"),
            weight=_num("weight", 0.5),
        )
    except Exception as e:
        logger.debug(f"PersonaVoiceProfile build skipped: {e}")
        return None, voice_id
    return pvp, voice_id


def build_modality_context(
    user_query: str,
    speaker_role: str = "unknown",
    audio_features: Optional[bytes] = None,
    query_risk: str = "safe",
    emotional_state: Optional[tuple] = None,
    ingress_modality: str = "text",
    speaker_name: Optional[str] = None,
) -> Any:
    """Build a ModalityContext for the current turn.

    Assembles the per-turn context from:
    - Channel capability (from the seam — Tauri desktop / Wyoming state)
    - Speaker identity (from the VoiceAuthGate — CAM++ biometrics — or the
      turn's carried claim for a voice turn identified out-of-band)
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
        ingress_modality: 'voice' when the turn arrived spoken. The audio
            pipeline already ran CAM++ speaker identification before the
            turn existed (the transcript reaches the HTTP door with the
            identified name/role attached), so a voice turn carries that
            result as an *unverified claim* here — never a role grant.
        speaker_name: The identified speaker's name for a voice turn (the
            CAM++ profile name). Recorded on the claim, not used for
            authorization.

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
    elif ingress_modality == "voice" and speaker_role and speaker_role != "unknown":
        # Packet 04 A1: a voice turn whose speaker the audio pipeline
        # identified out-of-band. There are no PCM bytes to re-verify
        # here (transcribe-once: the pipeline's single identification
        # rides the turn), so the result is carried as an UNVERIFIED
        # claim — the engine treats unverified speakers as role
        # "unknown" and applies the most restrictive policy. A verified
        # claim needs the claim-strength ladder (PACKET-02 Phase B /
        # 04-A2), which is the permission-system deep pass, not this
        # wiring.
        speaker = SpeakerIdentity(
            speaker_id=speaker_name or None,
            speaker_role=speaker_role,
            confidence=0.0,
            verified=False,
        )
    else:
        # Text turn: set the role from the authenticated session.
        # speaker=None opts out of biometric risk hobble (decision 51).
        speaker = None  # type: ignore

    # Emotional state (PAD from PersonaCognition)
    valence, arousal, dominance = emotional_state or (0.0, 0.0, 0.0)

    # Quiet hours
    quiet_active = is_quiet_hours()
    quiet_policy = get_quiet_hours_policy()

    # Persona prosody base (spec 4.3): the persona's VoiceProfileData from
    # being.yml — base_rate/pitch/energy/cadence_style/weight blended
    # against the PAD delta by ProsodyMapper. The pack id itself
    # (``voice_id``) is not on PersonaVoiceProfile; demux_response and
    # stream_spoken_segments read it separately for persona_voice_id.
    persona_voice_profile, _ = get_persona_voice()

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
        persona_voice_profile=persona_voice_profile,
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
    persona_voice_id: str = "",
) -> Any:
    """Demux the model response into a MultiStreamPayload.

    Splits the response into speech segments + display text using
    ``SpeechTextDemuxer.assemble_payload()``. Halbert is Tier 0
    (single PERSONA segment), multi_occupant=True (always on for
    smart-home), with the turn's resolved prosody and risk policy.

    ``persona_voice_id`` is stamped on persona segments' ``voice_id``
    (the Kokoro voice pack id); when empty it falls back to the active
    persona's ``voice_profile.voice_id`` from being.yml.

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
        if not persona_voice_id:
            _, persona_voice_id = get_persona_voice()

        payload = demuxer.assemble_payload(
            response,
            multi_occupant=True,  # always on for Halbert (smart-home)
            whisper_active=whisper,
            prosody=prosody,
            modality=modality,
            risk_policy=risk_policy,
            thread_id=thread_id,
            session_id=session_id or str(uuid.uuid4()),
            persona_voice_id=persona_voice_id,
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


def spoken_segment_lines(response: str, payload: Any, summarizer: Any = None) -> list:
    """Select the lines a voice turn will actually speak (packet 04 C1).

    The spoken copy is adapted before synthesis — a code-heavy reply
    (fenced-block ratio >= 50% of characters) speaks one deterministic
    fallback line instead of its own content, and every other spoken
    segment has fences/inline code/markdown noise stripped. The
    on-screen text is untouched: this reads the payload the demuxer
    already assembled and never writes back to it.

    Packet 04 C2: ``summarizer`` (from
    ``.speech_summarizer.make_speech_summarizer``) summarizes the
    whole spoken copy of a long prose reply to one or two sentences.
    The gate is the whole reply, not one segment — a threshold gate
    applied per segment would miss a long reply split into short
    ones — so the stripped lines are joined, offered to the
    summarizer once, and only a strictly-shorter summary replaces
    them (as a single persona line carrying the first line's
    prosody). A code-heavy reply is never summarized: the fallback
    branch runs before any summarizer use. The summarizer is
    fail-soft by contract and returns its input whenever it does not
    fire, so the spoken path degrades to the C1 behavior.

    Args:
        response: The full reply text (the code-heaviness decision is
            made on the whole reply, not per segment).
        payload: The MultiStreamPayload from ``demux_response`` (its
            ``segments`` carry the per-segment prosody/role).
        summarizer: Optional C2 seam callable (see above). The
            display copy is never passed to it — only the spoken copy.

    Returns:
        A list of dicts ``{text, role, rate, volume, whisper, voice_id,
        cadence_style}`` — the spoken lines in order; empty when there
        is nothing to speak.
    """
    from .tts_quality import adapt_for_speech, is_code_heavy, strip_code_noise

    if is_code_heavy(response):
        # The whole reply is code: one fallback line, spoken the same
        # way every time. The detail is on screen. Never summarized —
        # the fallback decision precedes summarization (C2).
        return [{
            "text": adapt_for_speech(response),
            "role": "persona",
            "rate": 1.0,
            "volume": 1.0,
            "whisper": False,
            "voice_id": None,
            "cadence_style": None,
        }]

    lines = []
    for seg in getattr(payload, "segments", None) or []:
        if not getattr(seg, "is_spoken", False):
            continue
        # Strip path only, never the per-segment fallback: the reply as
        # a whole was prose, so a segment that was all code strips to
        # nothing and is dropped (screen-only), not replaced.
        spoken = strip_code_noise(getattr(seg, "text", "") or "")
        if not spoken:
            continue
        prosody = getattr(seg, "prosody", None)
        lines.append({
            "text": spoken,
            "role": getattr(getattr(seg, "role", None), "value", "persona"),
            "rate": float(getattr(prosody, "rate", 1.0) or 1.0),
            "volume": float(getattr(prosody, "volume", 1.0) or 1.0),
            "whisper": bool(getattr(prosody, "whisper", False)),
            # The demuxer already stamped the persona pack id (or a cameo
            # override) on the segment; pass it through to synthesis.
            "voice_id": getattr(seg, "voice_id", None),
            "cadence_style": getattr(prosody, "cadence_style", None),
        })

    # C2: one summary for the whole spoken copy. The summarizer owns
    # the deterministic length gate; a no-op (short text, no model,
    # failed request, summary not strictly shorter) returns the join
    # unchanged and the segment set stays as C1 produced it.
    if summarizer is not None and lines:
        joined = "\n\n".join(line["text"] for line in lines)
        try:
            summary = summarizer(joined)
        except Exception as e:
            logger.debug(f"Speech summarization skipped (non-fatal): {e}")
            summary = joined
        if summary and summary != joined and len(summary) < len(joined):
            first = lines[0]
            lines = [{
                "text": summary,
                "role": first["role"],
                "rate": first["rate"],
                "volume": first["volume"],
                "whisper": first["whisper"],
                "voice_id": first["voice_id"],
                "cadence_style": first["cadence_style"],
            }]
    return lines


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
# Streaming sentence delivery (spec section 2 — split_stream consumer)
# ---------------------------------------------------------------------------

async def stream_spoken_segments(
    token_stream: Any,  # AsyncIterator[str] — LLM token deltas
    ctx: Any,
    session_id: str = "",
    thread_id: str = "",
    persona_voice_id: str = "",
) -> Any:  # AsyncIterator[dict]
    """Yield spoken segments as sentences complete in the token stream.

    Wraps the engine's ``SpeechTextDemuxer.split_stream()`` — which
    flushes at sentence boundaries (``[.!?…]+``) — and applies
    Halbert's pronunciation lexicon + code-noise stripping to each
    segment before yielding. The consumer's ``VoiceBackend`` then
    re-chunks each sentence for Kokoro's 128-phoneme limit (that
    re-chunking lives in ``KokoroTTS``, not here).

    Yields dicts ``{text, role, rate, volume, whisper, voice_id}`` —
    the same shape as ``spoken_segment_lines`` but produced
    incrementally as the LLM streams, so the first sentence reaches
    the synthesizer before the full response is generated.

    ``persona_voice_id`` is the default Kokoro voice pack id from the
    persona's ``VoiceProfileData.voice_id``; a segment's own
    ``voice_id`` (cameo override) takes precedence when set.

    Degrades to nothing when the engine is not installed (the caller
    falls back to the batch ``demux_response`` + ``spoken_segment_lines``
    path).

    Args:
        token_stream: An async iterator of LLM token deltas (strings).
        ctx: A resolved ``ModalityContext`` (from ``resolve_turn_modality``).
        session_id: The turn's session id (for tracing).
        thread_id: The turn's thread id (for the demuxer's payload).
        persona_voice_id: Default voice pack id from the persona profile.

    Returns:
        An async iterator of spoken-segment dicts, or ``None`` if the
        engine is not installed.
    """
    if ctx is None:
        return None
    demuxer = get_speech_demuxer()
    if demuxer is None:
        return None
    try:
        from haloysius.modality.types import ResponseModality
    except ImportError:
        return None

    prosody = getattr(ctx, "prosody", None)
    risk_policy = getattr(ctx, "voice_risk_policy", None)
    modality = getattr(ctx, "recommended_modality", ResponseModality.TEXT)
    whisper = getattr(prosody, "whisper", False) if prosody else False
    if not persona_voice_id:
        _, persona_voice_id = get_persona_voice()

    from .tts_quality import strip_code_noise

    async def _stream():
        async for seg in demuxer.split_stream(
            token_stream,
            persona_voice_id=persona_voice_id,
            whisper_active=whisper,
            prosody=prosody,
            risk_policy=risk_policy,
        ):
            if not getattr(seg, "is_spoken", False):
                continue
            text = strip_code_noise(getattr(seg, "text", "") or "")
            if not text:
                continue
            seg_prosody = getattr(seg, "prosody", None)
            # Segment voice_id (cameo override) wins; persona default is
            # the fallback so every persona line speaks in its own voice.
            seg_voice_id = getattr(seg, "voice_id", None) or persona_voice_id or None
            yield {
                "text": apply_pronunciation(text),
                "role": getattr(getattr(seg, "role", None), "value", "persona"),
                "rate": float(getattr(seg_prosody, "rate", 1.0) or 1.0),
                "volume": float(getattr(seg_prosody, "volume", 1.0) or 1.0),
                "whisper": bool(getattr(seg_prosody, "whisper", False)),
                "voice_id": seg_voice_id,
                "cadence_style": getattr(seg_prosody, "cadence_style", None),
            }

    return _stream()


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


# ---------------------------------------------------------------------------
# A10-G7: the model is told the spoken budget
# ---------------------------------------------------------------------------

def spoken_budget_hint(max_words: Optional[int]) -> str:
    """One deterministic line telling the model its spoken budget.

    A10-G7. The engine's own prompt block reads
    ``voice_risk_policy.max_spoken_words`` and was never reached --
    ``get_modality_prompt_builder`` appears exactly once in the tree, at
    its own ``def``. So every voice reply was written at essay length and
    then hard-truncated mid-sentence at 12-35 words, with no audible
    signal. The measured result was "Your disk is filling up. Your disk
    is filling up. Your disk".

    The cap itself is the engine's and stays exactly where it is (FD-4:
    keep the cap, wire the hint). This does not raise it, bypass it or
    re-implement it -- it tells the model what it is, so the reply fits
    instead of being cut.
    """
    if not max_words or max_words <= 0:
        return ""
    return (
        f"You are speaking aloud. Answer in at most {max_words} words: "
        f"say the one thing that matters and stop. Anything longer is cut "
        f"off mid-sentence, which the listener hears as a fault."
    )


def spoken_max_words(ctx: Any) -> Optional[int]:
    """The engine's spoken word cap for this turn, or None.

    Read from the resolved modality context's own policy, never
    computed here: the cap is the engine's deterministic decision and
    this module's job is to report it, not to have an opinion about it.
    """
    policy = getattr(ctx, "voice_risk_policy", None)
    value = getattr(policy, "max_spoken_words", None)
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# A10-G6: a barge-in is a fact the next turn should know
# ---------------------------------------------------------------------------

#: Sessions whose last spoken reply was interrupted, and by how much.
#: Bounded: a handful of live sessions, cleared as each note is taken.
_BARGE_IN: Dict[str, tuple] = {}
_BARGE_IN_MAX = 32


def barge_in_note(spoken_words: int, total_words: int) -> str:
    """The deterministic note describing an interrupted reply.

    A10-G6. Barge-in stopped the audio and told the model nothing, so
    the next turn answered as if the whole reply had been heard -- and
    the commonest reason a person interrupts is that the answer had
    already gone wrong. Deterministic text, not a generated
    apology: the same situation reads the same way every time.
    """
    return (
        f"The listener interrupted your last spoken reply after about "
        f"{spoken_words} of {total_words} words. Assume they did not hear "
        f"the rest, and do not repeat it unless they ask."
    )


def record_barge_in(session_id: str, *, spoken_words: int, total_words: int) -> None:
    """Record that this session's spoken reply was cut short."""
    if not session_id:
        return
    _BARGE_IN[session_id] = (int(spoken_words or 0), int(total_words or 0))
    while len(_BARGE_IN) > _BARGE_IN_MAX:
        _BARGE_IN.pop(next(iter(_BARGE_IN)), None)


def take_barge_in_note(session_id: str) -> Optional[str]:
    """The note for this session's NEXT turn, consumed once.

    Once, because it describes one interruption: carrying it forward
    would have every later turn apologising for something that happened
    minutes ago.
    """
    facts = _BARGE_IN.pop(session_id or "", None)
    if not facts:
        return None
    return barge_in_note(*facts)


# ---------------------------------------------------------------------------
# Screen privacy — present is not the same as private
# ---------------------------------------------------------------------------


def screen_is_private() -> bool:
    """Whether this body's screen is one only the operator can read.

    Fails CLOSED. No engine, no seam, no capability, or a capability too
    old to answer all mean "assume a bystander can read it" — the cost of
    being wrong in that direction is a redaction nobody needed, and in the
    other direction it is a secret on a wall.
    """
    if not _engine_available():
        return False
    try:
        from haloysius.seam import resolve_channel_capability
        cap = resolve_channel_capability()
    except Exception as e:
        logger.debug(f"channel capability unavailable: {e}")
        return False
    if cap is None:
        return False
    getter = getattr(cap, "has_private_screen", None)
    if getter is None:
        return False
    try:
        return bool(getter())
    except Exception as e:
        logger.debug(f"has_private_screen raised: {e}")
        return False
