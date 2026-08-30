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

import datetime
import logging
import os
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..utils.platform import get_config_dir

logger = logging.getLogger(__name__)

VALID_VOICES = {"first_person", "the_computer", "hybrid"}
VALID_PROACTIVITY = {"off", "quiet", "balanced", "assertive"}
VALID_VOICE_PRESENTATIONS = {"not_defined", "male", "female"}
VALID_VARIANTS = {"sysadmin", "home", "home-light"}
VALID_AUTONOMY_LEVELS = {"observe", "suggest", "act", "orchestrate"}
VALID_OPERATIONAL_TIERS = {"cloud_ok", "local_only", "redact"}
VALID_SECRET_TIERS = {"local_only", "cloud_ok_acknowledged"}


@dataclass
class SecurityConfig:
    """Security tier settings for config value routing.

    Controls how config values are routed when exposed via MCP tools or
    the agent context assembler.  See the tiered sensitivity plan for
    the full rationale.

    No ``secure_model`` / ``secure_endpoint`` fields — the Tier 2 path is
    deterministic (``describe_secret``), no model.  If a local model is
    ever reintroduced for open-ended questions about secrets, it must
    carry a fail-closed assertion: reject any tag ending in ``:cloud``,
    reject any provider outside ``LOCAL_GPU_PROVIDERS``, never infer
    locality from the endpoint URL.

    No ``credential_validation`` / ``compromise_check`` fields — those
    modules send the secret to external services (issuing APIs, HIBP),
    which breaks the architectural guarantee that ``describe_secret``
    never sends the secret value anywhere. They exist as standalone
    human-run tools, not as part of the Tier 2 describe path.
    """
    operational_tier: str = "cloud_ok"  # cloud_ok | local_only | redact
    secret_tier: str = "local_only"     # local_only | cloud_ok_acknowledged
    public_files: List[str] = field(default_factory=lambda: [
        "/etc/hosts", "/etc/hostname", "/etc/fstab",
    ])
    extra_secret_keys: List[str] = field(default_factory=list)
    # Per-key escape hatch: allow specific keys to be cloud_ok while the
    # global secret_tier remains local_only. Keys listed here are treated
    # as cloud_ok_acknowledged regardless of the global setting. This lets
    # a user expose database passwords (which they trust ZDR with) while
    # keeping SSH private keys and API tokens local-only.
    cloud_ok_keys: List[str] = field(default_factory=list)
    # TTL for the Tier 2 escape hatch. When secret_tier is
    # cloud_ok_acknowledged, secret_tier_expiry is an ISO 8601 timestamp
    # after which the tier auto-relocks to local_only. None means
    # permanent (no auto-relock). Checked at load time and at query time
    # via effective_secret_tier().
    secret_tier_expiry: Optional[str] = None
    # Volatile unlock: if True, the secret_tier is reset to local_only
    # on the first load_being_config call of each process (i.e. on
    # process restart). This implements the "until restart" TTL option
    # without requiring a background timer. Persisted to YAML so the next
    # process can see it and relock; cleared after relocking.
    volatile_unlock: bool = False

    def validate(self) -> None:
        if self.operational_tier not in VALID_OPERATIONAL_TIERS:
            raise ValueError(
                f"Invalid operational_tier '{self.operational_tier}'. "
                f"Must be one of: {VALID_OPERATIONAL_TIERS}"
            )
        if self.secret_tier not in VALID_SECRET_TIERS:
            raise ValueError(
                f"Invalid secret_tier '{self.secret_tier}'. "
                f"Must be one of: {VALID_SECRET_TIERS}"
            )
        # Type-check list fields to prevent downstream crashes
        for field_name in ("public_files", "extra_secret_keys", "cloud_ok_keys"):
            val = getattr(self, field_name)
            if not isinstance(val, list):
                raise ValueError(
                    f"security.{field_name} must be a list, got {type(val).__name__}"
                )
            for item in val:
                if not isinstance(item, str):
                    raise ValueError(
                        f"security.{field_name} must be a list of strings, "
                        f"got {type(item).__name__}"
                    )
        # Validate secret_tier_expiry format and consistency
        if self.secret_tier_expiry is not None:
            if self.secret_tier != "cloud_ok_acknowledged":
                raise ValueError(
                    "secret_tier_expiry can only be set when secret_tier is "
                    "'cloud_ok_acknowledged'"
                )
            try:
                datetime.datetime.fromisoformat(self.secret_tier_expiry)
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"secret_tier_expiry must be a valid ISO 8601 timestamp: {e}"
                )
        if self.volatile_unlock and self.secret_tier != "cloud_ok_acknowledged":
            raise ValueError(
                "volatile_unlock can only be True when secret_tier is "
                "'cloud_ok_acknowledged'"
            )

    def effective_secret_tier(self) -> str:
        """Return the effective secret tier, checking TTL expiry at runtime.

        If secret_tier is cloud_ok_acknowledged but the expiry has passed,
        returns 'local_only'. This is the function callers should use
        at query time — never trust secret_tier directly without this check.
        """
        if self.secret_tier != "cloud_ok_acknowledged":
            return self.secret_tier
        if self.secret_tier_expiry is None:
            return self.secret_tier
        try:
            expiry = datetime.datetime.fromisoformat(self.secret_tier_expiry)
            now = datetime.datetime.now(expiry.tzinfo) if expiry.tzinfo else datetime.datetime.now()
            if now > expiry:
                return "local_only"
        except (ValueError, TypeError):
            # Invalid expiry string — fail safe (relock)
            return "local_only"
        return self.secret_tier

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "SecurityConfig":
        if d is None:
            return cls()
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class SensesVisionConfig:
    """Persona-level vision autonomy settings.

    The system-level enable/disable gate lives in vision_config.yml
    (is_screen_capture_enabled). These fields control what the being
    is *allowed to do proactively* with vision, separate from whether
    the hardware is enabled at all.
    """
    enabled: bool = False  # persona-level consent for proactive vision
    proactive_monitoring: bool = False  # background VisualWatcher
    capture_on_intent: bool = True  # auto-capture in PLANNING when visual intent detected
    capture_on_error: bool = False  # auto-capture on tool failure (opt-in)
    interval_seconds: int = 60  # VisualWatcher cadence when proactive_monitoring=True
    error_patterns: List[str] = field(default_factory=lambda: [
        "error", "failed", "panic", "warning", "exception",
        "connection refused", "access denied", "not found",
    ])


@dataclass
class SensesConfig:
    """Sensory autonomy settings for the being."""
    vision: SensesVisionConfig = field(default_factory=SensesVisionConfig)


@dataclass
class BeingConfig:
    """Configuration for how the being behaves and communicates."""

    # --- Persona metadata (multi-persona system) ---
    persona_id: str = "default"  # slug id matching the persona filename
    display_name: str = "Default"  # human-readable persona name
    created_at: str = ""  # ISO timestamp of persona creation

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

    # --- Senses (vision autonomy) ---
    senses: SensesConfig = field(default_factory=SensesConfig)

    # --- Home identity & multi-instance ---
    # Variant gates which startup services launch (sysadmin vs home).
    # scene_context overrides platform-derived cognition framing.
    # persona_id_override replaces hardcoded "halbert" in cognition_wiring.
    variant: str = "sysadmin"  # sysadmin | home | home-light
    scene_context: str = ""  # e.g. "smart home automation"
    persona_id_override: str = ""  # e.g. "home"

    # --- Home Assistant connection (light variant stores HA creds here
    # instead of a separate ha_config.yml, so being.yml is the single
    # file a home-light user needs to deploy) ---
    ha_url: Optional[str] = None
    ha_token: Optional[str] = None

    # --- Home autonomy ---
    # Controls whether Halbert can take physical action or only observe.
    # observe: perceive and report only. No device commands.
    # suggest: create proposals but wait for approval.
    # act: execute Level 0/1 governance actions (lights, blinds, thermostat).
    # orchestrate: coordinate multi-device sequences, Level 2 with cancel window.
    autonomy_level: str = "observe"
    # Per-domain overrides keyed by HA domain (e.g. {"lock": "suggest", "climate": "act"})
    autonomy_overrides: Dict[str, str] = field(default_factory=dict)

    # --- Security (MCP trust boundary) ---
    security: SecurityConfig = field(default_factory=SecurityConfig)

    def __post_init__(self) -> None:
        """Coerce nested dict senses into SensesConfig if needed."""
        if isinstance(self.senses, dict):
            vision_data = self.senses.get("vision", {})
            if isinstance(vision_data, dict):
                self.senses = SensesConfig(
                    vision=SensesVisionConfig(**{
                        k: v for k, v in vision_data.items()
                        if k in SensesVisionConfig.__dataclass_fields__
                    })
                )
            else:
                self.senses = SensesConfig()

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
        # Senses validation
        vision = self.senses.vision
        if vision.interval_seconds < 10:
            raise ValueError(
                f"senses.vision.interval_seconds must be >= 10, got {vision.interval_seconds}"
            )
        # Home identity validation
        if self.variant not in VALID_VARIANTS:
            raise ValueError(
                f"Invalid variant '{self.variant}'. Must be one of: {VALID_VARIANTS}"
            )
        if self.autonomy_level not in VALID_AUTONOMY_LEVELS:
            raise ValueError(
                f"Invalid autonomy_level '{self.autonomy_level}'. "
                f"Must be one of: {VALID_AUTONOMY_LEVELS}"
            )
        for domain, level in self.autonomy_overrides.items():
            if level not in VALID_AUTONOMY_LEVELS:
                raise ValueError(
                    f"Invalid autonomy override '{level}' for domain '{domain}'. "
                    f"Must be one of: {VALID_AUTONOMY_LEVELS}"
                )
        # Security validation
        self.security.validate()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BeingConfig":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        # Unpack nested SensesConfig — from_dict only filters top-level keys,
        # so nested dataclasses need explicit construction.
        if "senses" in known and isinstance(known["senses"], dict):
            senses_data = known["senses"]
            vision_data = senses_data.get("vision", {})
            if isinstance(vision_data, dict):
                known["senses"] = SensesConfig(
                    vision=SensesVisionConfig(**{
                        k: v for k, v in vision_data.items()
                        if k in SensesVisionConfig.__dataclass_fields__
                    })
                )
            else:
                known["senses"] = SensesConfig()
        # Handle nested security config — guard against null / missing
        if "security" in known:
            if isinstance(known["security"], dict):
                known["security"] = SecurityConfig.from_dict(known["security"])
            elif known["security"] is None:
                # security: null in YAML — use defaults instead of crashing
                known["security"] = SecurityConfig()
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


# Config paths whose volatile-unlock relock has already run in THIS process.
#
# The volatile ("until restart") escape hatch is persisted to YAML so a fresh
# process can see it and relock — but load_being_config is called per request
# (dashboard routes) and per tool call (MCP server), not once at startup.
# Without this guard the very next load after unlocking relocks immediately:
# "until restart" actually meant "until the next config read", and the
# relock's save_being_config call wrote being.yml on every load. Keyed by
# path so multi-instance setups (one being.yml per instance) and tests with
# per-test tmp paths each get their own once-per-process check.
_volatile_relock_done: set = set()
_volatile_relock_lock = threading.Lock()


def load_being_config(path: Optional[str] = None) -> BeingConfig:
    """Load being config from YAML file.

    Returns defaults if the file doesn't exist.
    Raises ValueError if the file contains invalid values.
    """
    config_path = Path(path) if path else _default_path()

    # Consume this process's first-load check for this path BEFORE the
    # exists() early-return: on a fresh install being.yml is created by the
    # unlock POST itself, and the guard must already be spent by then or
    # the next load relocks the unlock it just wrote.
    config_key = str(config_path)
    with _volatile_relock_lock:
        first_load_this_process = config_key not in _volatile_relock_done
        _volatile_relock_done.add(config_key)

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

    # Volatile unlock: reset to local_only on the FIRST load in each
    # process (i.e. on process restart). The volatile_unlock flag is
    # persisted so the next process can see it and relock; later loads in
    # the same process must not relock — see _volatile_relock_done above.
    relocked = False
    if config.security.volatile_unlock and first_load_this_process:
        logger.info("Volatile unlock detected on load — relocking secrets to local_only")
        config.security.secret_tier = "local_only"
        config.security.volatile_unlock = False
        config.security.secret_tier_expiry = None
        relocked = True

    # Expiry check: if the escape hatch has expired, relock.
    if (config.security.secret_tier == "cloud_ok_acknowledged"
            and config.security.secret_tier_expiry):
        effective = config.security.effective_secret_tier()
        if effective == "local_only":
            logger.info("Secret tier expiry passed — relocking to local_only")
            config.security.secret_tier = "local_only"
            config.security.secret_tier_expiry = None
            relocked = True

    config.validate()

    # Persist the relocked state so the YAML doesn't keep stale TTL fields
    if relocked:
        try:
            save_being_config(config, path)
        except Exception as e:
            logger.warning(f"Failed to persist relocked config: {e}")

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
    # Strip None-valued fields from the nested security block for cleaner YAML.
    # volatile_unlock IS persisted — it is the marker that tells the next
    # load_being_config call to relock (implementing "until restart" TTL).
    if "security" in clean and isinstance(clean["security"], dict):
        clean["security"] = {
            k: v for k, v in clean["security"].items() if v is not None
        }

    try:
        # Atomic write: write to temp file then rename, so a concurrent
        # reader never sees a partially-written file. Restricted to 0o600
        # because being.yml can contain security config references.
        #
        # Resolve symlinks: being.yml may be a symlink to personas/<id>.yml
        # in multi-persona mode. We must write to the target file, not
        # replace the symlink itself.
        write_path = config_path.resolve() if config_path.is_symlink() else config_path
        import tempfile
        fd, tmp_path = tempfile.mkstemp(
            dir=str(write_path.parent), suffix=".yml.tmp", prefix=".being_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.dump(clean, f, default_flow_style=False, sort_keys=False)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, str(write_path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        logger.info(f"Saved being config to {config_path}")
    except OSError as e:
        raise ValueError(f"Cannot write {config_path}: {e}")
