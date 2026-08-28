# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Vision configuration.

Loaded from ~/.config/halbert/vision_config.yml. All vision features
are OFF by default — the user must explicitly enable screen capture
and webcam access.

The config is read on every capture attempt (not cached), so changes
take effect immediately without a restart. This is deliberate: the
config is small, the file read is cheap, and a stale cache would mean
a user who disables webcam access might still have frames captured
before the next restart.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("halbert.vision.config")


def _config_path() -> Path:
    """Path to vision_config.yml in the user's config directory."""
    try:
        from ..utils.platform import get_config_dir
        return get_config_dir() / "vision_config.yml"
    except Exception:
        return Path.home() / ".config" / "halbert" / "vision_config.yml"


@dataclass
class ScreenCaptureConfig:
    enabled: bool = False
    quality: int = 85
    max_dimension: int = 1568
    monitor_index: int = 1  # 0=all monitors, 1=primary (default avoids multi-monitor waste)
    grayscale: bool = False  # 30% smaller JPEGs; text/UI perfectly readable


@dataclass
class WebcamConfig:
    enabled: bool = False
    camera_index: int = 0
    quality: int = 85
    max_dimension: int = 768
    grayscale: bool = False  # color matters for webcam (objects, labels)


@dataclass
class VisionConfig:
    screen_capture: ScreenCaptureConfig = field(default_factory=ScreenCaptureConfig)
    webcam: WebcamConfig = field(default_factory=WebcamConfig)


_DEFAULT_CONFIG = VisionConfig()


def load_config() -> VisionConfig:
    """Load vision config from disk, or return defaults if missing/unreadable."""
    path = _config_path()
    if not path.exists():
        return VisionConfig()
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        screen = data.get("screen_capture", {})
        webcam = data.get("webcam", {})
        return VisionConfig(
            screen_capture=ScreenCaptureConfig(
                enabled=screen.get("enabled", False),
                quality=screen.get("quality", 85),
                max_dimension=screen.get("max_dimension", 1568),
                monitor_index=screen.get("monitor_index", 1),
                grayscale=screen.get("grayscale", False),
            ),
            webcam=WebcamConfig(
                enabled=webcam.get("enabled", False),
                camera_index=webcam.get("camera_index", 0),
                quality=webcam.get("quality", 85),
                max_dimension=webcam.get("max_dimension", 768),
                grayscale=webcam.get("grayscale", False),
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to load vision config: {e}, using defaults")
        return VisionConfig()


def save_config(config: VisionConfig) -> None:
    """Save vision config to disk."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "screen_capture": {
            "enabled": config.screen_capture.enabled,
            "quality": config.screen_capture.quality,
            "max_dimension": config.screen_capture.max_dimension,
            "monitor_index": config.screen_capture.monitor_index,
            "grayscale": config.screen_capture.grayscale,
        },
        "webcam": {
            "enabled": config.webcam.enabled,
            "camera_index": config.webcam.camera_index,
            "quality": config.webcam.quality,
            "max_dimension": config.webcam.max_dimension,
            "grayscale": config.webcam.grayscale,
        },
    }
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


def is_screen_capture_enabled() -> bool:
    """Check if screen capture is enabled. Read on every call."""
    return load_config().screen_capture.enabled


def is_webcam_enabled() -> bool:
    """Check if webcam is enabled. Read on every call."""
    return load_config().webcam.enabled
