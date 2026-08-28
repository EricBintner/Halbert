# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Home Assistant connection configuration."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("halbert.integrations.home_assistant.config")


@dataclass
class HAConfig:
    """Connection configuration for a Home Assistant instance."""

    url: str = ""
    token: str = ""
    verify_ssl: bool = True
    # Entity domains to show by default in the Home panel
    visible_domains: list[str] = field(
        default_factory=lambda: [
            "light",
            "switch",
            "climate",
            "lock",
            "cover",
            "fan",
            "media_player",
            "vacuum",
            "binary_sensor",
            "sensor",
            "person",
            "device_tracker",
            "alarm_control_panel",
        ]
    )

    def is_configured(self) -> bool:
        """Return True if both URL and token are set."""
        return bool(self.url and self.token)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Never expose the full token in API responses
        if d.get("token"):
            d["token"] = d["token"][:8] + "..." if len(d["token"]) > 8 else "***"
        return d


def _config_path() -> Path:
    """Return the path to the HA config file."""
    data_dir = os.environ.get(
        "HALBERT_DATA_DIR",
        os.path.expanduser("~/.local/share/halbert"),
    )
    return Path(data_dir) / "ha_config.json"


def load_ha_config() -> HAConfig:
    """Load HA connection config from disk, or return empty defaults."""
    path = _config_path()
    if not path.is_file():
        return HAConfig()
    try:
        data = json.loads(path.read_text())
        return HAConfig(
            url=data.get("url", ""),
            token=data.get("token", ""),
            verify_ssl=data.get("verify_ssl", True),
            visible_domains=data.get("visible_domains", HAConfig().visible_domains),
        )
    except Exception as e:
        logger.warning(f"Could not load HA config: {e}")
        return HAConfig()


def save_ha_config(config: HAConfig) -> None:
    """Save HA connection config to disk."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2))
    logger.info(f"Saved HA config to {path}")
