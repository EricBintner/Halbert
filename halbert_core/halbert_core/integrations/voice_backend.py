# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""HalbertVoiceBackend — wraps PiperTTS in the Haloysius VoiceBackend Protocol.

Implements the engine's ``VoiceBackend`` seam (spec section 3.1) on top of
Halbert's ``PiperTTS`` (sherpa-onnx OfflineTTS). The engine calls
``synthesize()`` when the modality resolver decides the response should be
spoken; this adapter maps the engine's ``ProsodyHints`` to Piper's available
parameters and returns a ``SpeechResult``.

Prosody mapping (spec section 4.3): Piper is a numeric-only engine — it
honours ``rate`` (via ``speed``) and ``volume`` (post-synthesis gain). Pitch
and energy are not directly controllable in Piper VITS; they are logged at
debug level and ignored. ``whisper=True`` reduces volume to 0.5 as a
best-effort approximation (Piper has no dedicated whisper mode). The
engine's ``expression_tokens`` and ``cadence_style`` are ignored (Piper has
no inline expressiveness or style conditioning).

Barge-in: ``cancel()`` triggers the active ``BargeInToken``, which the
``PiperTTS.synthesize()`` generator checks between chunks and aborts. The
``BargeInHandler`` owns the <120ms local-cancellation budget (spec B5).

Lazy: ``sherpa_onnx`` and ``PiperTTS`` are imported on first use so this
module is importable without the audio-inference extra.
"""

from __future__ import annotations

import asyncio
import logging
import struct
from typing import Any, List, Optional

logger = logging.getLogger("halbert.integrations.voice_backend")


class HalbertVoiceBackend:
    """VoiceBackend Protocol implementation wrapping PiperTTS.

    The engine's ``VoiceBackend`` Protocol (runtime_checkable, structural):
    ``is_available()``, ``synthesize()``, ``cancel()``, ``list_voices()``.
    """

    def __init__(self, tts: Any = None):
        # ``tts`` is a PiperTTS instance (or a mock in tests). Lazy-init:
        # if None, one is constructed on first ``synthesize`` call.
        self._tts = tts
        self._barge_in_token: Any = None  # BargeInToken, set per turn.
        self._playback_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # VoiceBackend Protocol
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """True if PiperTTS can be initialized (model configured + sherpa-onnx)."""
        try:
            tts = self._get_tts()
            # PiperTTS._ensure_initialized() raises if no model / no sherpa-onnx.
            tts._ensure_initialized()
            return True
        except Exception:
            return False

    async def synthesize(
        self,
        text: str,
        prosody: Any,  # ProsodyHints (engine type, annotation-only here)
    ) -> Any:  # SpeechResult (engine type)
        """Synthesize ``text`` with prosody guidance, return SpeechResult.

        ``text`` is markdown-stripped plain text ready to speak (the engine's
        demuxer has already cleaned it). ``prosody`` carries rate, pitch,
        volume, energy, voice_id, and whisper hints.

        Maps prosody to Piper's parameters:
        - ``rate`` -> Piper ``speed`` (direct pass-through; Piper default 1.0)
        - ``volume`` -> post-synthesis linear gain on PCM samples
        - ``whisper`` -> volume capped at 0.5 (best-effort whisper approximation)
        - ``pitch_offset``, ``energy``, ``expression_tokens``, ``cadence_style``
          -> logged at debug, ignored (Piper has no controls for these)

        Barge-in: if a ``BargeInToken`` is set (via ``cancel()`` or
        ``set_barge_in_token()``), synthesis aborts when the token fires.
        """
        try:
            from haloysius.modality.types import SpeechResult
        except ImportError:
            return None  # type: ignore  — engine not installed

        if not text.strip():
            return SpeechResult(success=True, audio_bytes=b"", duration_seconds=0.0)

        try:
            tts = self._get_tts()
        except Exception as e:
            logger.warning(f"PiperTTS unavailable: {e}")
            return SpeechResult(success=False, error=str(e))

        # Apply prosody to Piper's speed parameter.
        rate = getattr(prosody, "rate", 1.0) or 1.0
        volume = getattr(prosody, "volume", 1.0) or 1.0
        whisper = getattr(prosody, "whisper", False)

        if whisper:
            volume = min(volume, 0.5)

        # PiperTTS stores speed as _speed; override for this call.
        original_speed = tts._speed
        tts._speed = rate
        try:
            tts._ensure_initialized()
        except Exception as e:
            logger.warning(f"PiperTTS init failed: {e}")
            return SpeechResult(success=False, error=str(e))

        cancel_token = self._barge_in_token

        try:
            # Collect all PCM chunks (PiperTTS.synthesize is an async generator).
            pcm_chunks: List[bytes] = []
            sample_rate = 16000
            async for chunk in tts.synthesize(text, cancel_token=cancel_token):
                pcm_chunks.append(chunk)

            if cancel_token is not None and cancel_token.is_set():
                logger.debug("Voice synthesis cancelled by barge-in")
                return SpeechResult(
                    success=False,
                    cancelled=True,
                    error="barge_in",
                )

            pcm = b"".join(pcm_chunks)
            if not pcm:
                return SpeechResult(success=False, error="no audio produced")

            # Apply volume gain (post-synthesis, linear scale on 16-bit PCM).
            if volume != 1.0:
                pcm = _apply_volume_gain(pcm, volume)

            # Estimate duration from PCM length (16-bit mono at sample_rate).
            num_samples = len(pcm) // 2
            sample_rate = getattr(tts, "_sample_rate", None) or 16000
            duration = num_samples / sample_rate if sample_rate > 0 else 0.0

            return SpeechResult(
                success=True,
                audio_bytes=pcm,
                format="wav",
                sample_rate=sample_rate,
                duration_seconds=duration,
            )
        except Exception as e:
            logger.error(f"Voice synthesis failed: {e}")
            return SpeechResult(success=False, error=str(e))
        finally:
            tts._speed = original_speed

    def cancel(self) -> None:
        """Cancel any in-flight synthesis (barge-in)."""
        if self._barge_in_token is not None:
            self._barge_in_token.trigger()
            logger.debug("Voice backend: barge-in token triggered")
        if self._playback_task is not None and not self._playback_task.done():
            self._playback_task.cancel()

    def list_voices(self) -> List[Any]:
        """List available Piper voices.

        Returns a list of VoiceInfo-shaped objects. Piper typically has one
        configured voice (the model file); we report it as a single entry.
        Returns [] when the engine is not installed.
        """
        try:
            from haloysius.seam import VoiceInfo
        except ImportError:
            return []

        try:
            tts = self._get_tts()
            tts._ensure_initialized()
            voice_model = getattr(tts, "_voice_model", "default")
            # Derive a voice id from the model filename.
            voice_id = voice_model.split("/")[-1].replace(".onnx", "") if voice_model else "default"
            return [VoiceInfo(voice_id=voice_id, name=voice_id, language="en")]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Halbert-specific barge-in wiring
    # ------------------------------------------------------------------

    def set_barge_in_token(self, token: Any) -> None:
        """Set the BargeInToken for the current turn's synthesis.

        Called by the wiring layer before ``synthesize()`` so ``cancel()``
        can trigger it. The token is an ``asyncio.Event`` wrapper
        (``BargeInToken`` from ``audio.speech.barge_in``).
        """
        self._barge_in_token = token

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_tts(self) -> Any:
        """Return the PiperTTS instance, lazy-constructing if needed."""
        if self._tts is None:
            from ..audio.speech.tts_engine import PiperTTS
            self._tts = PiperTTS()
        return self._tts


def _apply_volume_gain(pcm: bytes, gain: float) -> bytes:
    """Apply a linear volume gain to 16-bit PCM audio.

    Clips to [-32768, 32767] to prevent overflow. ``gain`` of 1.0 = no change.
    """
    n = len(pcm) // 2
    if n == 0:
        return pcm
    samples = struct.unpack(f"<{n}h", pcm)
    scaled = [max(-32768, min(32767, int(s * gain))) for s in samples]
    return struct.pack(f"<{n}h", *scaled)
