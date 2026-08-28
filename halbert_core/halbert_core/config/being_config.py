# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Being configuration — how the user lives with their computer.

Controls voice (first_person / the_computer / hybrid), proactivity dial,
quiet hours, morning report, purpose, and per-category overrides.

Default path: ~/.config/halbert/being.yml (or platform equivalent)

Phase 6 / T6a.1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..utils.platform import get_config_dir

logger = logging.getLogger(__name__)

VALID_VOICES = {"first_person", "the_computer", "hybrid"}
VALID_PROACTIVITY = {"off", "quiet", "balanced", "assertive"}
VALID_VOICE_PRESENTATIONS = {"not_defined", "male", "female"}


@dataclass
class BeingConfig:
    """Configuration for how the being behaves and communicates."""

    voice: str = "first_person"  # first_person | the_computer | hybrid
    proactivity: str = "balanced"  # off | quiet | balanced | assertive
    purpose: str = ""  # free text v1
    quiet_hours: Optional[Dict[str, str]] = None  # {"start": "22:00", "end": "07:00"}
    morning_report: Optional[Dict[str, Any]] = None  # {"enabled": True, "time": "08:00"}
    category_overrides: Dict[str, str] = field(default_factory=dict)
    timezone: str = "local"  # IANA tz name, or "local" for system timezone

    # --- Personality ---
    personality_profile: Dict[str, float] = field(default_factory=lambda: {
        "openness": 0.5, "conscientiousness": 0.5,
        "extraversion": 0.5, "agreeableness": 0.5, "neuroticism": 0.5,
    })
    archetype_id: Optional[str] = None
    tone_descriptors: List[str] = field(default_factory=list)
    speech_patterns: List[str] = field(default_factory=list)
    directives: List[str] = field(default_factory=list)
    custom_personality_prompt: str = ""  # escape hatch: replaces generated layer

    # --- Character (Phase 3 UI) ---
    name: str = ""  # display name; syncs with preferences.yml ai_name
    voice_presentation: str = "not_defined"  # not_defined | male | female
    model: Optional[str] = None  # per-persona model override (shadows chat_model when set)
    model_endpoint_id: Optional[str] = None  # saved-endpoint id for the persona model

    def validate(self) -> None:
        """Validate the config. Raises ValueError on invalid values."""
        if self.voice not in VALID_VOICES:
            raise ValueError(
                f"Invalid voice '{self.voice}'. Must be one of: {VALID_VOICES}"
            )
        if self.proactivity not in VALID_PROACTIVITY:
            raise ValueError(
                f"Invalid proactivity '{self.proactivity}'. Must be one of: {VALID_PROACTIVITY}"
            )
        if self.quiet_hours:
            if "start" not in self.quiet_hours or "end" not in self.quiet_hours:
                raise ValueError("quiet_hours must have 'start' and 'end' keys")
        if self.morning_report:
            if "enabled" not in self.morning_report:
                raise ValueError("morning_report must have 'enabled' key")
        for cat, level in self.category_overrides.items():
            if level not in VALID_PROACTIVITY:
                raise ValueError(
                    f"Invalid proactivity override '{level}' for category '{cat}'. "
                    f"Must be one of: {VALID_PROACTIVITY}"
                )
        # Personality validation
        for trait, value in self.personality_profile.items():
            if trait not in ("openness", "conscientiousness", "extraversion",
                             "agreeableness", "neuroticism"):
                raise ValueError(f"Unknown personality trait '{trait}'")
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"Personality trait '{trait}' must be 0.0-1.0, got {value}"
                )
        if self.voice_presentation not in VALID_VOICE_PRESENTATIONS:
            raise ValueError(
                f"Invalid voice_presentation '{self.voice_presentation}'. "
                f"Must be one of: {VALID_VOICE_PRESENTATIONS}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BeingConfig":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def _default_path() -> Path:
    """Get the default being.yml path."""
    return get_config_dir() / "being.yml"


def resolve_timezone(tz_name: str) -> str:
    """Resolve a timezone name to a value APScheduler accepts.

    "local" → the system's local timezone (e.g. "America/New_York").
    Any other string is returned as-is (must be a valid IANA name).
    Falls back to "UTC" if the system timezone cannot be determined.
    """
    if tz_name != "local":
        return tz_name
    # Method 1: /etc/localtime symlink (macOS) — realpath contains the IANA name
    try:
        import os
        import zoneinfo
        realpath = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in realpath:
            iana = realpath.split("zoneinfo/")[-1]
            if iana in zoneinfo.available_timezones():
                return iana
    except Exception:
        pass
    # Method 2: /etc/timezone (Linux)
    try:
        import zoneinfo
        tzpath = Path("/etc/timezone")
        if tzpath.exists():
            tz = tzpath.read_text().strip()
            if tz in zoneinfo.available_timezones():
                return tz
    except Exception:
        pass
    # Method 3: datetime tzinfo key (works when zoneinfo loads the local tz)
    try:
        import datetime
        import zoneinfo
        local_tz = datetime.datetime.now().astimezone().tzinfo
        if local_tz is not None:
            tz_key = getattr(local_tz, "key", None) or str(local_tz)
            if tz_key in zoneinfo.available_timezones():
                return tz_key
    except Exception:
        pass
    return "UTC"


def load_being_config(path: Optional[str] = None) -> BeingConfig:
    """Load being config from YAML file.

    Returns defaults if the file doesn't exist.
    Raises ValueError if the file contains invalid values.
    """
    config_path = Path(path) if path else _default_path()

    if not config_path.exists():
        logger.info(f"No being config at {config_path}, using defaults")
        return BeingConfig()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {config_path}: {e}")
    except OSError as e:
        raise ValueError(f"Cannot read {config_path}: {e}")

    config = BeingConfig.from_dict(data)
    config.validate()
    logger.info(f"Loaded being config from {config_path} (voice={config.voice})")
    return config


def save_being_config(config: BeingConfig, path: Optional[str] = None) -> None:
    """Save being config to YAML file.

    Validates before saving. Creates parent directories if needed.
    """
    config.validate()

    config_path = Path(path) if path else _default_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = config.to_dict()
    # Remove None values for cleaner YAML
    clean = {k: v for k, v in data.items() if v is not None and v != ""}

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(clean, f, default_flow_style=False, sort_keys=False)
        logger.info(f"Saved being config to {config_path}")
    except OSError as e:
        raise ValueError(f"Cannot write {config_path}: {e}")
