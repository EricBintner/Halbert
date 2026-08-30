# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Silero VAD v5 ONNX wrapper — voice activity detection.

Silero VAD v5 is a lightweight (2.2MB) ONNX model that classifies whether
an audio frame contains speech. It operates on 512-sample (32ms) windows
at 16kHz and runs in <1ms per chunk on CPU.

sherpa-onnx provides a built-in VAD wrapper (``sherpa_onnx.VoiceActivityDetector``)
that handles the ONNX session, windowing, and hysteresis thresholds. This
module wraps it with a clean Python API and lazy imports.

Usage:
    from halbert_core.audio.speech.vad import VoiceActivityDetector
    vad = VoiceActivityDetector(model_path="/path/to/silero_vad.onnx")
    segments = vad.detect_speech(pcm_bytes)
    for seg in segments:
        print(f"Speech: {seg.start_ms:.0f}ms - {seg.end_ms:.0f}ms")
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("halbert.audio.speech.vad")

# Silero VAD v5 uses 512-sample windows at 16kHz (32ms)
SILERO_WINDOW_SAMPLES = 512
SAMPLE_RATE = 16_000

# Default hysteresis thresholds (Silero recommended)
DEFAULT_START_THRESHOLD = 0.5   # P(speech) > this to start speech segment
DEFAULT_NEG_THRESHOLD = 0.35    # P(speech) < this to end speech segment
# Minimum silence duration to split segments (ms)
DEFAULT_MIN_SILENCE_MS = 500


@dataclass
class SpeechSegment:
    """A detected speech segment with onset/offset timestamps."""
    start_ms: float
    end_ms: float
    duration_ms: float
    confidence: float = 0.0


class VoiceActivityDetector:
    """Silero VAD v5 wrapper via sherpa-onnx.

    Lazy-imports ``sherpa_onnx`` on first use. The module imports cleanly
    without it installed.
    """

    def __init__(
        self,
        model_path: str = "",
        start_threshold: float = DEFAULT_START_THRESHOLD,
        neg_threshold: float = DEFAULT_NEG_THRESHOLD,
        min_silence_ms: int = DEFAULT_MIN_SILENCE_MS,
    ):
        self._model_path = model_path
        self._start_threshold = start_threshold
        self._neg_threshold = neg_threshold
        self._min_silence_ms = min_silence_ms
        self._detector = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy-init the sherpa-onnx VAD detector."""
        if self._initialized:
            return
        try:
            import sherpa_onnx
        except ImportError:
            raise RuntimeError(
                "sherpa-onnx is not installed. "
                "Install with: pip install halbert-core[audio-inference]"
            )

        if not self._model_path:
            # Try to find default model in data dir
            from ..config import load_config
            from ...utils.paths import data_subdir
            default_path = data_subdir("audio", "models", "silero_vad.onnx")
            if default_path:
                self._model_path = str(default_path)

        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = self._model_path
        config.silero_vad.threshold = self._start_threshold
        config.silero_vad.min_silence_duration_ms = self._min_silence_ms
        config.silero_vad.min_speech_duration_ms = 100
        config.sample_rate = SAMPLE_RATE
        config.provider = "cpu"
        config.num_threads = 1

        self._detector = sherpa_onnx.VoiceActivityDetector(
            config,
            buffer_size_in_seconds=10,
        )
        self._initialized = True
        logger.info(f"Silero VAD initialized: {self._model_path}")

    def detect_speech(self, pcm_bytes: bytes) -> List[SpeechSegment]:
        """Detect speech segments in a PCM audio buffer.

        Args:
            pcm_bytes: Raw 16-bit, 16kHz, mono PCM audio.

        Returns:
            List of SpeechSegment with start/end timestamps.
        """
        self._ensure_initialized()
        assert self._detector is not None

        # Convert bytes to float32 samples [-1.0, 1.0]
        n = len(pcm_bytes) // 2
        samples = struct.unpack(f'<{n}h', pcm_bytes)
        float_samples = [s / 32768.0 for s in samples]

        # Feed into VAD in 512-sample windows
        segments: List[SpeechSegment] = []
        offset = 0

        while offset < len(float_samples):
            chunk = float_samples[offset:offset + SILERO_WINDOW_SAMPLES]
            if len(chunk) < SILERO_WINDOW_SAMPLES:
                # Pad last chunk with silence
                chunk = chunk + [0.0] * (SILERO_WINDOW_SAMPLES - len(chunk))

            self._detector.accept_waveform(chunk)
            while self._detector.empty() is False:
                seg = self._detector.front
                self._detector.pop()

                start_ms = seg.start / SAMPLE_RATE * 1000
                end_ms = (seg.start + seg.length) / SAMPLE_RATE * 1000
                segments.append(SpeechSegment(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    duration_ms=end_ms - start_ms,
                ))

            offset += SILERO_WINDOW_SAMPLES

        # Reset detector for next call
        self._detector.flush()

        return segments

    def is_speech(self, pcm_chunk: bytes) -> bool:
        """Quick check: does this chunk contain speech?

        Uses a single window evaluation. Faster than detect_speech for
        real-time gating.
        """
        self._ensure_initialized()
        assert self._detector is not None

        n = len(pcm_chunk) // 2
        if n < SILERO_WINDOW_SAMPLES:
            return False

        samples = struct.unpack(f'<{n}h', pcm_chunk)
        float_samples = [s / 32768.0 for s in samples]

        self._detector.accept_waveform(float_samples[:SILERO_WINDOW_SAMPLES])
        has_speech = self._detector.empty() is False
        if has_speech:
            self._detector.pop()
        self._detector.flush()
        return has_speech

    def reset(self) -> None:
        """Reset the VAD state (clear buffered segments)."""
        if self._detector:
            self._detector.flush()
