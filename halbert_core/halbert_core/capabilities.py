# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Capability registry — probe what this body can actually do.

The variant system (``being.yml: variant: sysadmin | home``) was a hard
gate: a ``home`` node could not run ingestion, scheduler, config watcher,
terminal, SourcePrep, or secure_model — period. This is wrong for the
singular-entity vision: a Mac Studio with HA configured should do **both**
sysadmin AND home things. An N150 with an A2000 GPU should run local LLM.

This module replaces the hard variant gate with **capability probing**.
Each capability is a named, testable predicate. The variant becomes a
**preset** that sets default capabilities, but ``being.yml`` can override
any capability explicitly. Capabilities emerge from what's actually
present, not from a label.

Capabilities:
  terminal          — can start PTY sessions (shell access)
  sourceprep        — SourcePrep documentation index is available
  config_watcher    — config-registry.yml exists, watcher can start
  ingestion         — journald/hwmon ingestion service can run
  scheduler         — autonomous scheduled jobs can run
  discovery         — system discovery scanners can run
  ha_connection     — Home Assistant is configured (ha_url + ha_token)
  local_llm         — a local Ollama/LMStudio endpoint is configured
  secure_model      — a secure (local-only) model endpoint is configured

Design:
- Probes are cheap (config checks, file existence, not network probes).
- The registry is a singleton, probed once at startup.
- Backward compatible: if no ``capabilities:`` section in being.yml,
  the variant preset is used exclusively (same behavior as today).
- being.yml can override any capability:
  ``capabilities: {terminal: true, sourceprep: false}``
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Capability names
# ---------------------------------------------------------------------------

CAP_TERMINAL = "terminal"
CAP_SOURCEPREP = "sourceprep"
CAP_CONFIG_WATCHER = "config_watcher"
CAP_INGESTION = "ingestion"
CAP_SCHEDULER = "scheduler"
CAP_DISCOVERY = "discovery"
CAP_HA_CONNECTION = "ha_connection"
CAP_LOCAL_LLM = "local_llm"
CAP_SECURE_MODEL = "secure_model"

ALL_CAPABILITIES: Set[str] = {
    CAP_TERMINAL,
    CAP_SOURCEPREP,
    CAP_CONFIG_WATCHER,
    CAP_INGESTION,
    CAP_SCHEDULER,
    CAP_DISCOVERY,
    CAP_HA_CONNECTION,
    CAP_LOCAL_LLM,
    CAP_SECURE_MODEL,
}

# ---------------------------------------------------------------------------
# Variant presets — the default capability set for each variant
# ---------------------------------------------------------------------------

_PRESET_SYSADMIN: Dict[str, bool] = {
    CAP_TERMINAL: True,
    CAP_SOURCEPREP: True,
    CAP_CONFIG_WATCHER: True,
    CAP_INGESTION: True,
    CAP_SCHEDULER: True,
    CAP_DISCOVERY: True,
    CAP_HA_CONNECTION: False,  # only if ha_url is configured
    CAP_LOCAL_LLM: False,      # only if a local endpoint is configured
    CAP_SECURE_MODEL: False,   # only if a secure endpoint is configured
}

_PRESET_HOME: Dict[str, bool] = {
    CAP_TERMINAL: False,
    CAP_SOURCEPREP: False,
    CAP_CONFIG_WATCHER: False,
    CAP_INGESTION: False,
    CAP_SCHEDULER: False,
    CAP_DISCOVERY: False,
    CAP_HA_CONNECTION: True,   # home variant expects HA to be configured
    CAP_LOCAL_LLM: False,
    CAP_SECURE_MODEL: False,
}


def _variant_preset(variant: str) -> Dict[str, bool]:
    """Get the default capability preset for a variant."""
    if variant == "home":
        return dict(_PRESET_HOME)
    return dict(_PRESET_SYSADMIN)


# ---------------------------------------------------------------------------
# Probes — test for actual presence of a capability
# ---------------------------------------------------------------------------

def _probe_ha_connection() -> bool:
    """Is Home Assistant configured (ha_url + ha_token in being.yml)?"""
    try:
        from .config.being_config import load_being_config
        cfg = load_being_config()
        return bool(cfg.ha_url and cfg.ha_token)
    except Exception:
        return False


def _probe_config_watcher() -> bool:
    """Does a config-registry.yml exist (something to watch)?"""
    try:
        from .config.being_config import load_being_config
        cfg = load_being_config()
        if cfg.variant == "home":
            # Home variant doesn't have a local config tree by default,
            # but can be overridden via being.yml capabilities section.
            return False
        # Check for config-registry.yml in common locations
        from pathlib import Path
        candidates = [
            Path(os.environ.get("HALBERT_CONFIG_DIR", "")) / "config-registry.yml",
            Path.home() / ".config" / "halbert" / "config-registry.yml",
            Path("/etc/halbert/config-registry.yml"),
        ]
        return any(p.exists() for p in candidates)
    except Exception:
        return False


def _probe_sourceprep() -> bool:
    """Is SourcePrep available (index exists or module importable)?"""
    try:
        from .config.being_config import load_being_config
        cfg = load_being_config()
        if cfg.variant == "home":
            return False
        # Check if SourcePrep is importable and has an index
        import importlib
        sp = importlib.import_module("sourceprep")
        # If SourcePrep is importable, assume the index can be built/used
        return sp is not None
    except ImportError:
        return False
    except Exception:
        return False


def _probe_local_llm() -> bool:
    """Is a local LLM endpoint configured (Ollama/LMStudio URL)?

    Checks the chat_model, specialist_model, and secure_model slots for
    a URL pointing at localhost or a LAN address.
    """
    try:
        from .model.llm_config import resolve
        for slot in ("chat_model", "specialist_model", "secure_model"):
            model = resolve(slot)
            if model and model.url:
                url = str(model.url)
                if "localhost" in url or "127.0.0.1" in url or "0.0.0.0" in url:
                    return True
        return False
    except Exception:
        return False


def _probe_secure_model() -> bool:
    """Is a secure (local-only) model endpoint configured?

    Checks the secure_model slot for an enabled, local URL.
    """
    try:
        from .model.llm_config import resolve, _is_local_url
        model = resolve("secure_model")
        if model and model.url and _is_local_url(model.url):
            return True
        return False
    except Exception:
        return False


# Capabilities that have active probes (test for actual presence).
# Others use the variant preset default (which can be overridden in being.yml).
_PROBES = {
    CAP_HA_CONNECTION: _probe_ha_connection,
    CAP_CONFIG_WATCHER: _probe_config_watcher,
    CAP_SOURCEPREP: _probe_sourceprep,
    CAP_LOCAL_LLM: _probe_local_llm,
    CAP_SECURE_MODEL: _probe_secure_model,
}


# ---------------------------------------------------------------------------
# CapabilityRegistry
# ---------------------------------------------------------------------------

class CapabilityRegistry:
    """Probe and cache what this body can actually do.

    Resolution order for each capability:
    1. Explicit override in being.yml ``capabilities:`` section
    2. Active probe (if one exists for this capability)
    3. Variant preset default

    This means a Mac Studio with ``variant: sysadmin`` gets all sysadmin
    capabilities by default, but if the user adds
    ``capabilities: {ha_connection: true}`` and configures ha_url/ha_token,
    it also gets HA capabilities — without changing variant.
    """

    def __init__(self):
        self._capabilities: Dict[str, bool] = {}
        self._probed = False

    def _load_config(self) -> tuple:
        """Load variant and explicit capability overrides from being.yml.

        Returns (variant, overrides_dict).
        """
        try:
            from .config.being_config import load_being_config
            cfg = load_being_config()
            variant = cfg.variant
            # The capabilities section is not a typed field on BeingConfig
            # (yet) — read it from the raw YAML to avoid a migration.
            overrides: Dict[str, bool] = {}
            import yaml
            from .config.being_config import _default_path
            path = _default_path()
            if path and path.exists():
                with open(path, "r") as f:
                    raw = yaml.safe_load(f) or {}
                caps = raw.get("capabilities", {})
                if isinstance(caps, dict):
                    for k, v in caps.items():
                        if k in ALL_CAPABILITIES and isinstance(v, bool):
                            overrides[k] = v
            return variant, overrides
        except Exception as e:
            logger.debug("Capability config load failed, using defaults: %s", e)
            return "sysadmin", {}

    def probe(self) -> None:
        """Probe all capabilities. Called once at startup."""
        variant, overrides = self._load_config()
        preset = _variant_preset(variant)

        for cap in ALL_CAPABILITIES:
            # 1. Explicit override wins
            if cap in overrides:
                self._capabilities[cap] = overrides[cap]
                continue

            # 2. Active probe (if one exists)
            if cap in _PROBES:
                try:
                    self._capabilities[cap] = _PROBES[cap]()
                    continue
                except Exception as e:
                    logger.debug("Probe for %s failed: %s", cap, e)

            # 3. Variant preset default
            self._capabilities[cap] = preset.get(cap, False)

        self._probed = True
        enabled = sorted(k for k, v in self._capabilities.items() if v)
        disabled = sorted(k for k, v in self._capabilities.items() if not v)
        logger.info(
            "Capabilities probed (variant=%s): enabled=%s disabled=%s",
            variant, enabled, disabled,
        )

    def has(self, capability: str) -> bool:
        """Check if a capability is available. Probes if not yet probed."""
        if not self._probed:
            self.probe()
        return self._capabilities.get(capability, False)

    def has_all(self, *capabilities: str) -> bool:
        """Check if all given capabilities are available."""
        return all(self.has(c) for c in capabilities)

    def has_any(self, *capabilities: str) -> bool:
        """Check if any of the given capabilities are available."""
        return any(self.has(c) for c in capabilities)

    def enabled(self) -> Set[str]:
        """Return the set of enabled capabilities."""
        if not self._probed:
            self.probe()
        return {k for k, v in self._capabilities.items() if v}

    def describe(self) -> Dict[str, bool]:
        """Return a dict of all capabilities and their state."""
        if not self._probed:
            self.probe()
        return dict(self._capabilities)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry: Optional[CapabilityRegistry] = None


def get_capability_registry() -> CapabilityRegistry:
    """Get the singleton CapabilityRegistry."""
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry


def has_capability(capability: str) -> bool:
    """Convenience: check if a capability is available."""
    return get_capability_registry().has(capability)


def reset_registry() -> None:
    """Reset the singleton (for testing)."""
    global _registry
    _registry = None
