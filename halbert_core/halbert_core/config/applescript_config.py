# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""AppleScript execution configuration.

Loaded from ``get_config_dir()/applescript_config.yml`` (platform
dependent: ``~/Library/Application Support/Halbert/`` on macOS,
``~/.config/halbert/`` on Linux). AppleScript/JXA execution is OFF by
default — the user must explicitly enable it.

The config is read on every tool call (not cached), so changes take
effect immediately without a restart. This mirrors vision/config.py and
is deliberate for the same reason: a user who disables AppleScript
execution must not have scripts still running against a stale cache.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger("halbert.config.applescript")


def _config_path() -> Path:
    """Path to applescript_config.yml in the user's config directory."""
    try:
        from ..utils.platform import get_config_dir
        return get_config_dir() / "applescript_config.yml"
    except Exception:
        return Path.home() / ".config" / "halbert" / "applescript_config.yml"


@dataclass
class AppleScriptConfig:
    enabled: bool = False
    timeout_seconds: int = 10


def load_config() -> AppleScriptConfig:
    """Load applescript config from disk, or defaults if missing/unreadable."""
    path = _config_path()
    if not path.exists():
        return AppleScriptConfig()
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        # Strictly True: a quoted "false"/"yes" string or a number must not
        # read as enabled — anything but a real YAML boolean is disabled.
        return AppleScriptConfig(
            enabled=data.get("enabled", False) is True,
            timeout_seconds=int(data.get("timeout_seconds", 10)),
        )
    except Exception as e:
        logger.warning(f"Failed to load applescript config: {e}, using defaults")
        return AppleScriptConfig()


def is_applescript_enabled() -> bool:
    """Check if AppleScript execution is enabled. Read on every call."""
    return load_config().enabled
