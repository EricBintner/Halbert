# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Availability check for the audio inference runtime.

sherpa-onnx and onnxruntime are lazy optional extras. This module provides
a single function that checks whether the heavy audio deps are importable
without actually importing them at module level.
"""

from __future__ import annotations

import importlib.util

_AVAILABLE: bool | None = None


def is_audio_available() -> bool:
    """Check if sherpa-onnx is importable.

    Returns True if ``sherpa_onnx`` can be imported. Cached after first call.
    The audio subsystem is a no-op (no VAD, no ASR, no speaker ID) when this
    returns False, but the package itself imports cleanly.
    """
    global _AVAILABLE
    if _AVAILABLE is not None:
        return _AVAILABLE
    _AVAILABLE = importlib.util.find_spec("sherpa_onnx") is not None
    return _AVAILABLE
