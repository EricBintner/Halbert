# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Piper TTS engine — neural text-to-speech via sherpa-onnx.

Uses Piper VITS models (from OHF-Voice/piper1-gpl, the maintained fork of
the archived rhasspy/piper). Runs entirely on CPU via ONNX Runtime.

Supports barge-in cancellation: the ``synthesize`` method yields PCM chunks
and checks a cancellation token between chunks, aborting generation when
the user interrupts.

Usage:
    from halbert_core.audio.speech.tts_engine import PiperTTS
    tts = PiperTTS(voice_model="/path/to/en_US-amy-medium.onnx")
    async for pcm_chunk in tts.synthesize("ZFS pool is healthy"):
        play_audio(pcm_chunk)
"""

from __future__ import annotations

import asyncio
import logging
import struct
from typing import AsyncIterator, Optional

logger = logging.getLogger("halbert.audio.speech.tts")

SAMPLE_RATE = 16_000


class PiperTTS:
    """Piper VITS text-to-speech via sherpa-onnx OfflineTTS.

    Lazy-imports ``sherpa_onnx`` on first use.
    """

    def __init__(
        self,
        voice_model: str = "",
        speaker_id: int = 0,
        num_threads: int = 2,
        speed: float = 1.0,
    ):
        self._voice_model = voice_model
        self._speaker_id = speaker_id
        self._num_threads = num_threads
        self._speed = speed
        self._tts = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy-init the sherpa-onnx offline TTS."""
        if self._initialized:
            return
        try:
            import sherpa_onnx
        except ImportError:
            raise RuntimeError(
                "sherpa-onnx is not installed. "
                "Install with: pip install halbert-core[audio-inference]"
            )

        if not self._voice_model:
            from ..config import load_config
            cfg = load_config()
            self._voice_model = cfg.tts.voice_model
            self._speaker_id = cfg.tts.speaker_id

        if not self._voice_model:
            raise RuntimeError(
                "No Piper voice model configured. "
                "Set tts.voice_model in audio_config.yml or pass voice_model=."
            )

        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=self._voice_model,
                ),
                num_threads=self._num_threads,
                provider="cpu",
                debug=False,
            ),
        )

        self._tts = sherpa_onnx.OfflineTts(config)
        self._sherpa = sherpa_onnx
        self._initialized = True
        logger.info(f"Piper TTS initialized: {self._voice_model}")

    async def synthesize(
        self,
        text: str,
        cancel_token: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[bytes]:
        """Synthesize text to speech, yielding PCM chunks.

        Args:
            text: The text to synthesize.
            cancel_token: If set, synthesis aborts when the token is set
                (barge-in). The generator stops yielding immediately.

        Yields:
            Raw 16-bit PCM bytes (sample rate depends on the voice model).
        """
        self._ensure_initialized()
        assert self._tts is not None

        # sherpa-onnx OfflineTts generates the full audio at once.
        # We chunk it for streaming playback + barge-in cancellation.
        loop = asyncio.get_event_loop()

        def _generate() -> tuple[list[float], int]:
            """Run TTS in a thread to avoid blocking the event loop."""
            audio = self._tts.generate(
                text,
                sid=self._speaker_id,
                speed=self._speed,
            )
            samples = []
            for i in range(len(audio.samples)):
                samples.append(audio.samples[i])
            return samples, audio.sample_rate

        samples, sr = await loop.run_in_executor(None, _generate)
        # Record the model's real rate (commonly 22050, not SAMPLE_RATE —
        # that constant is the mic/ASR rate). HalbertVoiceBackend and the
        # dashboard's TTS egress (O3) both read ``_sample_rate`` to label
        # the PCM they forward; a wrong rate resamples by playback error.
        self._sample_rate = sr

        # Yield in ~30ms chunks (480 samples at 16kHz, or proportional)
        chunk_size = int(sr * 0.03)
        for i in range(0, len(samples), chunk_size):
            if cancel_token is not None and cancel_token.is_set():
                logger.debug("TTS barge-in: cancellation received, aborting")
                return

            chunk = samples[i:i + chunk_size]
            # Convert float32 [-1.0, 1.0] to 16-bit PCM
            pcm_bytes = struct.pack(
                f'<{len(chunk)}h',
                *[max(-32768, min(32767, int(s * 32767))) for s in chunk],
            )
            yield pcm_bytes

    def synthesize_sync(self, text: str) -> tuple[bytes, int]:
        """Synchronous synthesis (for testing).

        Returns:
            (pcm_bytes, sample_rate)
        """
        self._ensure_initialized()
        assert self._tts is not None

        audio = self._tts.generate(
            text,
            sid=self._speaker_id,
            speed=self._speed,
        )
        samples = [audio.samples[i] for i in range(len(audio.samples))]
        pcm_bytes = struct.pack(
            f'<{len(samples)}h',
            *[max(-32768, min(32767, int(s * 32767))) for s in samples],
        )
        return pcm_bytes, audio.sample_rate

    @property
    def sample_rate(self) -> int:
        """The output sample rate of the loaded voice model."""
        self._ensure_initialized()
        # Piper voices typically output at 16000 or 22050
        # The actual rate is in the generated audio object
        return SAMPLE_RATE  # default; actual rate comes from generate()
