# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Vision capture subsystem: screen and webcam frames for the agent.

Local-only. Frames are captured on demand (user button or agent tool call),
encoded to JPEG, and sent to the configured vision model. Nothing is stored
to disk unless the user explicitly saves a conversation with images.

All capture is gated by vision_config.yml — features are OFF by default
and must be explicitly enabled via Settings > Vision.
"""

from .config import (
    VisionConfig,
    ScreenCaptureConfig,
    WebcamConfig,
    load_config,
    save_config,
    is_screen_capture_enabled,
    is_webcam_enabled,
)
from .ocr import recognize, is_available as ocr_available

__all__ = [
    "VisionConfig",
    "ScreenCaptureConfig",
    "WebcamConfig",
    "load_config",
    "save_config",
    "is_screen_capture_enabled",
    "is_webcam_enabled",
    "recognize",
    "ocr_available",
]
