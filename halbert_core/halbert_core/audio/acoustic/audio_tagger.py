# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Audio tagger — CED-tiny / Zipformer-small acoustic event classification.

Uses sherpa-onnx for ONNX-based audio event tagging. NOT YAMNet (which
sherpa-onnx does not support — finding C4). Uses CED-tiny or
Zipformer-small-audio-tagging-int8 models instead.

The class ontology differs from YAMNet's 521 AudioSet classes. CED-tiny
uses a different label set. Use ``label_map.py`` to map raw model output
to human-readable labels.

Lazy-imports ``sherpa_onnx`` on first use.
"""

from __future__ import annotations

import logging
import struct
from typing import List, Dict

logger = logging.getLogger("halbert.audio.acoustic.audio_tagger")

SAMPLE_RATE = 16_000


class AudioTagger:
    """Acoustic event classifier via sherpa-onnx.

    Supports CED-tiny or Zipformer-small-audio-tagging-int8 models.
    Lazy-imports sherpa_onnx on first use.
    """

    def __init__(
        self,
        model_path: str = "",
        labels_path: str = "",
        num_threads: int = 2,
    ):
        self._model_path = model_path
        self._labels_path = labels_path
        self._num_threads = num_threads
        self._classifier = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy-init the sherpa-onnx audio tagger."""
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
            from ..config import load_config
            cfg = load_config()
            self._model_path = cfg.acoustic_events.model

        if not self._model_path:
            from ...utils.paths import data_subdir
            self._model_path = str(
                data_subdir("audio", "models", "ced-tiny.onnx")
            )

        if not self._labels_path:
            from ...utils.paths import data_subdir
            self._labels_path = str(
                data_subdir("audio", "models", "ced-tiny-labels.txt")
            )

        # CED: ced is a plain string path (not a config object).
        # Zipformer: uses OfflineZipformerAudioTaggingModelConfig.
        # num_threads/provider go inside AudioTaggingModelConfig.
        # AudioTaggingConfig requires labels (path to label file) and top_k.
        try:
            config = sherpa_onnx.AudioTaggingConfig(
                model=sherpa_onnx.AudioTaggingModelConfig(
                    ced=self._model_path,
                    num_threads=self._num_threads,
                    provider="cpu",
                ),
                labels=self._labels_path,
                top_k=5,
            )
            self._classifier = sherpa_onnx.AudioTagging(config)
        except Exception:
            # Fall back to Zipformer audio tagging
            config = sherpa_onnx.AudioTaggingConfig(
                model=sherpa_onnx.AudioTaggingModelConfig(
                    zipformer=sherpa_onnx.OfflineZipformerAudioTaggingModelConfig(
                        model=self._model_path,
                    ),
                    num_threads=self._num_threads,
                    provider="cpu",
                ),
                labels=self._labels_path,
                top_k=5,
            )
            self._classifier = sherpa_onnx.AudioTagging(config)

        self._sherpa = sherpa_onnx
        self._initialized = True
        logger.info(f"Audio tagger initialized: {self._model_path}")

    def classify(self, pcm_bytes: bytes, top_k: int = 5) -> List[Dict]:
        """Classify a 1-second PCM window into acoustic event classes.

        Args:
            pcm_bytes: Raw 16-bit, 16kHz, mono PCM (1 second = 32000 bytes).
            top_k: Number of top results to return.

        Returns:
            List of dicts with keys: class, confidence, is_anomaly, severity, decibel.
        """
        self._ensure_initialized()
        assert self._classifier is not None

        n = len(pcm_bytes) // 2
        samples = struct.unpack(f'<{n}h', pcm_bytes)
        float_samples = [s / 32768.0 for s in samples]

        stream = self._classifier.create_stream()
        stream.accept_waveform(SAMPLE_RATE, float_samples)
        stream.input_finished()

        # compute() returns a list of AudioEvent objects (not get_result)
        events = self._classifier.compute(stream, top_k=top_k)
        results = []
        for event in events:
            if event.prob > 0.1:
                results.append({
                    "class": event.name,
                    "confidence": event.prob,
                    "is_anomaly": _is_anomaly_class(event.name),
                    "severity": _anomaly_severity(event.name),
                    "decibel": _estimate_db(pcm_bytes),
                })

        return results

    @property
    def is_available(self) -> bool:
        """Check if the tagger is initialized."""
        return self._initialized and self._classifier is not None


# ── Anomaly classification helpers ───────────────────────────────────────

# Classes that indicate a safety-critical anomaly
_ANOMALY_CLASSES = {
    "smoke_alarm", "smoke_detector", "fire_alarm",
    "glass_breaking", "glass_break",
    "burglar_alarm", "car_alarm", "alarm",
    "siren", "emergency_vehicle",
    "water", "water_leak", "water_running",
}

# Severity mapping for anomaly classes
_SEVERITY_MAP = {
    "smoke_alarm": 3, "smoke_detector": 3, "fire_alarm": 3,
    "glass_breaking": 3, "glass_break": 3,
    "burglar_alarm": 3, "car_alarm": 2, "alarm": 2,
    "siren": 2, "emergency_vehicle": 2,
    "water": 1, "water_leak": 2, "water_running": 1,
}


def _is_anomaly_class(class_name: str) -> bool:
    """Check if a class name indicates an anomaly."""
    name_lower = class_name.lower().replace(" ", "_")
    return any(a in name_lower for a in _ANOMALY_CLASSES)


def _anomaly_severity(class_name: str) -> int:
    """Get anomaly severity (0-3) for a class name."""
    name_lower = class_name.lower().replace(" ", "_")
    for key, severity in _SEVERITY_MAP.items():
        if key in name_lower:
            return severity
    return 0


def _estimate_db(pcm_bytes: bytes) -> float:
    """Estimate dB level of a PCM buffer."""
    import math
    n = len(pcm_bytes) // 2
    if n == 0:
        return -999.0
    samples = struct.unpack(f'<{n}h', pcm_bytes)
    rms = (sum(s * s for s in samples) / n) ** 0.5
    if rms == 0:
        return -999.0
    return 20 * math.log10(rms / 32768.0)
