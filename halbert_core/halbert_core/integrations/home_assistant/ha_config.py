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
    from ...utils.platform import get_data_dir
    return get_data_dir() / "ha_config.json"


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
    """Save HA connection config to disk with restricted permissions.

    The file contains the HA long-lived access token which grants full
    house control (locks, alarm, garage) — write 0600 like Frigate
    (REV-03 F5). Also chmod existing files on load.
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(asdict(config), indent=2)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data.encode())
    finally:
        os.close(fd)
    logger.info(f"Saved HA config to {path}")


def seed_ha_config_from_being(url: str, token: str) -> None:
    """Seed HA config from being.yml without clobbering operator edits.

    Only writes if ha_config.json does not exist, or fills in missing
    url/token fields without touching verify_ssl/visible_domains that
    the operator may have set in the dashboard (REV-03 F6).
    """
    path = _config_path()
    if path.is_file():
        existing = load_ha_config()
        if existing.url and existing.token:
            return  # already configured — don't clobber
        # Fill in missing url/token only
        existing.url = url
        existing.token = token
        save_ha_config(existing)
        logger.info("HA config url/token filled from being.yml (existing file preserved)")
    else:
        save_ha_config(HAConfig(url=url, token=token))
        logger.info("HA config seeded from being.yml (new file)")
