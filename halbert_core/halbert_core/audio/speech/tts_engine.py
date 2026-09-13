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
        return getattr(self, "_sample_rate", None) or SAMPLE_RATE


def _pack_float_samples(samples: list[float]) -> bytes:
    """Convert float32 [-1.0, 1.0] samples to 16-bit little-endian PCM."""
    return struct.pack(
        f'<{len(samples)}h',
        *[max(-32768, min(32767, int(s * 32767))) for s in samples],
    )


def _split_text_for_kokoro(text: str, max_words: int = 15) -> list[str]:
    """Re-chunk long sentences for Kokoro's 128-phoneme / 5-second limit.

    Splits first at sentence boundaries, then at clause boundaries
    (commas, semicolons, em-dashes, colons), then at word boundaries.
    """
    import re
    if not text.strip():
        return []
    # Sentence boundaries
    sentences = re.split(r'(?<=[.!?…])\s+', text.strip())
    chunks: list[str] = []
    for sentence in sentences:
        # Clause boundaries within a sentence
        clauses = re.split(r'(?<=[,;：—])\s+', sentence)
        for clause in clauses:
            words = clause.split()
            for i in range(0, len(words), max_words):
                chunk_words = words[i:i + max_words]
                chunks.append(" ".join(chunk_words))
    return [c for c in chunks if c.strip()]


class KokoroTTS:
    """Kokoro-82M text-to-speech via sherpa-onnx OfflineTTS.

    Lazy-imports ``sherpa_onnx`` on first use. Re-chunks long sentences
    to stay within Kokoro's ~128-phoneme / 5-second synthesis limit.
    """

    def __init__(
        self,
        voice_model: str = "",
        voices: str = "",
        tokens: str = "",
        data_dir: str = "",
        speaker_id: int = 0,
        num_threads: int = 2,
        speed: float = 1.0,
        provider: str = "cpu",
    ):
        self._voice_model = voice_model
        self._voices = voices
        self._tokens = tokens
        self._data_dir = data_dir
        self._speaker_id = speaker_id
        self._num_threads = num_threads
        self._speed = speed
        self._provider = provider
        self._tts = None
        self._initialized = False

    def _resolve_paths(self) -> None:
        """Infer missing Kokoro file paths from the model directory."""
        if not self._voice_model:
            from ..config import load_config
            cfg = load_config()
            self._voice_model = cfg.tts.kokoro_model or cfg.tts.voice_model
            self._speaker_id = cfg.tts.speaker_id
            self._voices = cfg.tts.kokoro_voices
            self._tokens = cfg.tts.kokoro_tokens
            self._data_dir = cfg.tts.kokoro_data_dir

        if not self._voice_model:
            raise RuntimeError(
                "No Kokoro voice model configured. "
                "Set tts.kokoro_model in audio_config.yml or pass voice_model=."
            )

        if not self._voices or not self._tokens or not self._data_dir:
            from pathlib import Path
            model_dir = Path(self._voice_model).parent
            if not self._voices:
                self._voices = str(model_dir / "voices.bin")
            if not self._tokens:
                self._tokens = str(model_dir / "tokens.txt")
            if not self._data_dir:
                self._data_dir = str(model_dir / "espeak-ng-data")

    def _ensure_initialized(self) -> None:
        """Lazy-init the sherpa-onnx OfflineTts with Kokoro model."""
        if self._initialized:
            return
        try:
            import sherpa_onnx
        except ImportError:
            raise RuntimeError(
                "sherpa-onnx is not installed. "
                "Install with: pip install halbert-core[audio-inference]"
            )

        self._resolve_paths()

        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                    model=self._voice_model,
                    voices=self._voices,
                    tokens=self._tokens,
                    data_dir=self._data_dir,
                ),
                num_threads=self._num_threads,
                provider=self._provider,
                debug=False,
            ),
        )

        if not config.validate():
            raise RuntimeError("Kokoro TTS config failed validation")

        self._tts = sherpa_onnx.OfflineTts(config)
        self._sherpa = sherpa_onnx
        self._initialized = True
        logger.info(f"Kokoro TTS initialized: {self._voice_model}")

    async def synthesize(
        self,
        text: str,
        cancel_token: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[bytes]:
        """Synthesize text to speech, yielding PCM chunks.

        Re-chunks text for Kokoro's 128-phoneme / 5-second limit, then
        generates and yields each chunk's audio immediately — the first
        chunk's PCM reaches the caller before later chunks are synthesized.

        Args:
            text: The text to synthesize.
            cancel_token: If set, synthesis aborts when the token is set.

        Yields:
            Raw 16-bit PCM bytes (sample rate depends on the voice model).
        """
        self._ensure_initialized()
        assert self._tts is not None

        chunks = _split_text_for_kokoro(text)
        if not chunks:
            return

        loop = asyncio.get_event_loop()

        def _generate(chunk: str) -> tuple[list[float], int]:
            audio = self._tts.generate(
                chunk,
                sid=self._speaker_id,
                speed=self._speed,
            )
            samples = [audio.samples[i] for i in range(len(audio.samples))]
            return samples, audio.sample_rate

        for chunk_text in chunks:
            if cancel_token is not None and cancel_token.is_set():
                logger.debug("Kokoro TTS barge-in: cancellation received, aborting")
                return
            samples, sr = await loop.run_in_executor(None, _generate, chunk_text)
            self._sample_rate = sr

            # Yield this chunk's audio immediately in ~30ms frames.
            frame_size = int(sr * 0.03)
            for i in range(0, len(samples), frame_size):
                if cancel_token is not None and cancel_token.is_set():
                    logger.debug("Kokoro TTS barge-in: cancellation received, aborting")
                    return
                frame = samples[i:i + frame_size]
                yield _pack_float_samples(frame)

    def synthesize_sync(self, text: str) -> tuple[bytes, int]:
        """Synchronous synthesis (for testing)."""
        self._ensure_initialized()
        assert self._tts is not None

        chunks = _split_text_for_kokoro(text)
        all_samples: list[float] = []
        sample_rate = SAMPLE_RATE
        for chunk in chunks:
            audio = self._tts.generate(
                chunk,
                sid=self._speaker_id,
                speed=self._speed,
            )
            all_samples.extend(audio.samples[i] for i in range(len(audio.samples)))
            sample_rate = audio.sample_rate

        self._sample_rate = sample_rate
        pcm = _pack_float_samples(all_samples)
        return pcm, sample_rate

    @property
    def sample_rate(self) -> int:
        """The output sample rate of the loaded voice model."""
        self._ensure_initialized()
        return getattr(self, "_sample_rate", None) or SAMPLE_RATE
