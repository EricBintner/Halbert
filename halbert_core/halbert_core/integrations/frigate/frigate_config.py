# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Frigate NVR connection configuration.

Stored at ~/.local/share/halbert/frigate_config.json.
Mirrors HAConfig: dataclass + load/save helpers + token masking.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("halbert.integrations.frigate.config")


@dataclass
class FrigateConfig:
    """Connection configuration for a Frigate NVR instance."""

    # REST API
    url: str = ""  # e.g. http://frigate.local:5000
    api_key: str = ""  # Frigate API key (optional if no auth configured)
    verify_ssl: bool = True

    # MQTT (for real-time event streaming)
    mqtt_enabled: bool = False
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_password: str = ""

    # Camera filtering — only process events from these cameras.
    # Empty list = all cameras.
    enabled_cameras: list[str] = field(default_factory=list)

    # Label filtering — only surface events with these labels to cognition.
    # Empty list = all labels. Common: person, car, dog, cat, package.
    alert_labels: list[str] = field(default_factory=list)

    # Zone filtering — only surface events in these zones.
    # Empty list = all zones.
    alert_zones: list[str] = field(default_factory=list)

    # Minimum detection score (0.0-1.0) to surface as a proactive alert.
    # Frigate's default threshold is 0.7; we default slightly higher
    # to reduce false-positive cognitive noise.
    min_alert_score: float = 0.75

    # Whether to fetch snapshot thumbnails with event data.
    # When True, the event mapper will download the snapshot JPEG
    # and store it via VisionCache for episodic memory.
    fetch_snapshots: bool = True

    def is_configured(self) -> bool:
        """Return True if the REST URL is set."""
        return bool(self.url)

    def is_mqtt_configured(self) -> bool:
        """Return True if MQTT is enabled and host is set."""
        return self.mqtt_enabled and bool(self.mqtt_host)

    def validate(self) -> list[str]:
        """Validate config values. Returns a list of error messages (empty = valid)."""
        errors = []
        if self.url:
            if not self.url.startswith(("http://", "https://")):
                errors.append("URL must start with http:// or https://")
        if self.mqtt_enabled:
            if not self.mqtt_host:
                errors.append("MQTT enabled but mqtt_host is empty")
            if not (1 <= self.mqtt_port <= 65535):
                errors.append(f"MQTT port {self.mqtt_port} is out of range (1-65535)")
        if not (0.0 <= self.min_alert_score <= 1.0):
            errors.append(f"min_alert_score {self.min_alert_score} is out of range (0.0-1.0)")
        return errors

    def to_dict(self) -> dict:
        d = asdict(self)
        # Never expose credentials in API responses
        if d.get("api_key"):
            d["api_key"] = d["api_key"][:8] + "..." if len(d["api_key"]) > 8 else "***"
        if d.get("mqtt_password"):
            d["mqtt_password"] = "***" if d["mqtt_password"] else ""
        return d


def _config_path() -> Path:
    """Return the path to the Frigate config file."""
    data_dir = os.environ.get(
        "HALBERT_DATA_DIR",
        os.path.expanduser("~/.local/share/halbert"),
    )
    return Path(data_dir) / "frigate_config.json"


def load_frigate_config() -> FrigateConfig:
    """Load Frigate config from disk, or return empty defaults."""
    path = _config_path()
    if not path.is_file():
        return FrigateConfig()
    try:
        data = json.loads(path.read_text())
        return FrigateConfig(
            url=data.get("url", ""),
            api_key=data.get("api_key", ""),
            verify_ssl=data.get("verify_ssl", True),
            mqtt_enabled=data.get("mqtt_enabled", False),
            mqtt_host=data.get("mqtt_host", ""),
            mqtt_port=data.get("mqtt_port", 1883),
            mqtt_user=data.get("mqtt_user", ""),
            mqtt_password=data.get("mqtt_password", ""),
            enabled_cameras=data.get("enabled_cameras", []),
            alert_labels=data.get("alert_labels", []),
            alert_zones=data.get("alert_zones", []),
            min_alert_score=data.get("min_alert_score", 0.75),
            fetch_snapshots=data.get("fetch_snapshots", True),
        )
    except Exception as e:
        logger.warning(f"Could not load Frigate config: {e}")
        return FrigateConfig()


def save_frigate_config(config: FrigateConfig) -> None:
    """Save Frigate config to disk with restricted permissions."""
    errors = config.validate()
    if errors:
        raise ValueError(f"Invalid Frigate config: {'; '.join(errors)}")
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write with restricted permissions (owner read/write only)
    # because the file contains API keys and MQTT passwords
    data = json.dumps(asdict(config), indent=2)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data.encode())
    finally:
        os.close(fd)
    logger.info(f"Saved Frigate config to {path}")


def _is_masked_credential(value: str) -> bool:
    """Check if a string looks like a masked credential placeholder."""
    if not value:
        return False
    return value.endswith("...") or value == "***"
