# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Wake word spotting — "Hey Halbert" via openWakeWord.

openWakeWord ships pre-trained models for phrases like "alexa", "hey mycroft",
"hey jarvis". "Hey Halbert" is NOT pre-trained — it must be trained using
openWakeWord's synthetic data pipeline:

1. Define target phrase in a YAML config
2. Generate synthetic TTS positive/adversarial samples + background noise
3. Pre-compute openWakeWord features
4. Run train.py (~1hr on Colab or local GPU)
5. Export trained .tflite / .onnx model

The trained model should be placed at:
    ~/.local/share/halbert/audio/models/hey_halbert.ww.tflite

Training is deferred to a Fable/Colab session — this module loads whatever
trained model is available and falls back gracefully if none exists.

Usage:
    from halbert_core.audio.speech.wake_word import WakeWordSpotter
    spotter = WakeWordSpotter()
    if spotter.is_available():
        detected = spotter.detect(pcm_chunk)
        if detected:
            print("Wake word detected!")
"""

from __future__ import annotations

import logging
import struct
from typing import Optional

logger = logging.getLogger("halbert.audio.speech.wake_word")

SAMPLE_RATE = 16_000
# openWakeWord uses 128-sample frames at 16kHz (8ms)
OWW_FRAME_SAMPLES = 128
DEFAULT_THRESHOLD = 0.5


class WakeWordSpotter:
    """openWakeWord wrapper for custom "Hey Halbert" detection.

    Lazy-imports ``openwakeword`` on first use. If no trained model is
    found, ``is_available()`` returns False and the pipeline skips
    wake-word detection (falling back to hotkey-only activation).
    """

    def __init__(
        self,
        model_path: str = "",
        threshold: float = DEFAULT_THRESHOLD,
    ):
        self._model_path = model_path
        self._threshold = threshold
        self._model = None
        self._initialized = False
        self._available = False

    def _ensure_initialized(self) -> None:
        """Lazy-init the openWakeWord model."""
        if self._initialized:
            return

        try:
            import openwakeword
            from openwakeword.model import Model
        except ImportError:
            logger.debug("openwakeword not installed — wake word spotting disabled")
            self._available = False
            self._initialized = True
            return

        if not self._model_path:
            from ...utils.paths import data_subdir
            default_path = data_subdir("audio", "models", "hey_halbert.ww.tflite")
            self._model_path = str(default_path)

        try:
            self._model = Model(
                wakeword_model_paths=[self._model_path],
                inference_framework="onnx",
            )
            self._available = True
            logger.info(f"Wake word model loaded: {self._model_path}")
        except Exception as e:
            logger.debug(f"Wake word model not available: {e}")
            self._available = False

        self._initialized = True

    def is_available(self) -> bool:
        """Check if a trained wake word model is loaded."""
        self._ensure_initialized()
        return self._available

    def detect(self, pcm_bytes: bytes) -> bool:
        """Check if the wake word is detected in this audio chunk.

        Args:
            pcm_bytes: Raw 16-bit, 16kHz, mono PCM.

        Returns:
            True if wake word confidence exceeds threshold.
        """
        self._ensure_initialized()
        if not self._available or self._model is None:
            return False

        n = len(pcm_bytes) // 2
        samples = struct.unpack(f'<{n}h', pcm_bytes)
        float_samples = [s / 32768.0 for s in samples]

        # openWakeWord expects numpy float32 array
        import numpy as np
        audio_np = np.array(float_samples, dtype=np.float32)

        predictions = self._model.predict(audio_np)
        for model_name, score in predictions.items():
            if score >= self._threshold:
                logger.debug(f"Wake word '{model_name}' detected: {score:.2f}")
                return True
        return False

    def get_scores(self, pcm_bytes: bytes) -> dict:
        """Get raw confidence scores for all loaded models.

        Returns:
            Dict of model_name -> confidence score (0.0-1.0).
        """
        self._ensure_initialized()
        if not self._available or self._model is None:
            return {}

        n = len(pcm_bytes) // 2
        samples = struct.unpack(f'<{n}h', pcm_bytes)
        float_samples = [s / 32768.0 for s in samples]

        import numpy as np
        audio_np = np.array(float_samples, dtype=np.float32)

        return dict(self._model.predict(audio_np))
