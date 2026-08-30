# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Audio perception subsystem: voice, acoustic events, and music.

The Halbert Auditory Cortex — a unified, multi-ingress, dual-track audio
perception engine that runs entirely on sherpa-onnx / ONNX Runtime (zero
PyTorch dependency).

All audio features are OFF by default and must be explicitly enabled via
Settings > Audio & Voice. The config is read on every use (not cached) so
disabling mic access takes effect immediately.

Heavy dependencies (sherpa-onnx, onnxruntime) are lazy-imported inside
functions, so this package imports cleanly with zero audio deps installed.
Install the ``audio-inference`` optional dependency group to enable:

    pip install halbert-core[audio-inference]
"""

from __future__ import annotations

from .config import (
    AudioConfig,
    LocalMicConfig,
    WyomingIngressConfig,
    RtspIngressConfig,
    AcousticEventsConfig,
    MusicRecognitionConfig,
    SpeakerIdConfig,
    TtsConfig,
    AudioPrivacyConfig,
    load_config,
    save_config,
    is_audio_enabled,
    is_local_mic_enabled,
    is_wyoming_ingress_enabled,
)
from .is_available import is_audio_available

__all__ = [
    "AudioConfig",
    "LocalMicConfig",
    "WyomingIngressConfig",
    "RtspIngressConfig",
    "AcousticEventsConfig",
    "MusicRecognitionConfig",
    "SpeakerIdConfig",
    "TtsConfig",
    "AudioPrivacyConfig",
    "load_config",
    "save_config",
    "is_audio_enabled",
    "is_local_mic_enabled",
    "is_wyoming_ingress_enabled",
    "is_audio_available",
]
