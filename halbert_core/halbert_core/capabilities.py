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
  secure_model      — a secure (local-only) model endpoint is CONFIGURED
                       right now (probed). This is the runtime "is it
                       configured" signal a turn gate reads before
                       resolving the secure_model slot.
  secure_model_allowed — this variant is ALLOWED to host a secure model
                       at all (preset/override only, no probe). Fresh
                       installs have no secure_model configured yet, so
                       gating provisioning on `secure_model` itself is
                       circular — it never fires. Provisioning code (and
                       the wizard's secure-slot write) gates on this one
                       instead; `secure_model` stays the "already
                       configured" signal for the turn gate.
  audio             — the voice pipeline can run (config enabled + sherpa-onnx)

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
CAP_SECURE_MODEL_ALLOWED = "secure_model_allowed"
CAP_AUDIO = "audio"

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
    CAP_SECURE_MODEL_ALLOWED,
    CAP_AUDIO,
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
    CAP_SECURE_MODEL_ALLOWED: True,   # sysadmin may host a secure model
    CAP_AUDIO: True,           # any node can be the voice terminal (probe gates)
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
    # secure_model is a sysadmin-instance slot: an HA variant's LLM reaches
    # the house through tool calls that abstract credentials away, so home
    # never provisions or writes one (HOME-AUTOMATION-SIMPLIFICATION S1).
    CAP_SECURE_MODEL_ALLOWED: False,
    CAP_AUDIO: True,           # any node can be the voice terminal (probe gates)
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
    """Does a config-registry.yml exist (something to watch)?

    Presence only — the variant preset already defaults this off for
    home, and a home-variant node that *does* carry a config tree (the
    Mac Studio with both sysadmin and home duties, the exact case F5
    exists for) gets the capability from the file, not the label.
    """
    try:
        from pathlib import Path

        from .utils.platform import get_config_dir
        candidates = [
            get_config_dir() / "config-registry.yml",
            Path("/etc/halbert/config-registry.yml"),
        ]
        return any(p.exists() for p in candidates)
    except Exception:
        return False


def _probe_sourceprep() -> bool:
    """Is the SourcePrep module importable (an index can be built/used)?

    Presence only — no variant early-return (see _probe_config_watcher).
    Importability is a deliberately coarse proxy for "index available":
    it answers "this body can run SourcePrep", which is what the
    sourceprep-gated adapters need before they try. Import side effects
    are SourcePrep's own lazy-import discipline to keep cheap.
    """
    try:
        import importlib

        sp = importlib.import_module("sourceprep")
        return sp is not None
    except ImportError:
        return False
    except Exception:
        return False


def _probe_local_llm() -> bool:
    """Is a loopback LLM endpoint configured (this node's own model)?

    Checks the chat_model, specialist_model, and secure_model slots for
    a URL on a loopback/unspecified address, via ``llm_config._is_local_url``
    — the same properly-parsed check that enforces secure_model's
    local-only rule, so the two probes can never disagree about what
    "local" means (and ``http://[::1]:11434`` counts while
    ``https://api.localhost.gg`` — a public tunnel whose hostname merely
    contains "localhost" — does not).

    Deliberately NOT LAN-inclusive: a model on another machine's Ollama
    is the peer tier of the compute chain, not this node's local tier,
    and a ``peer://`` endpoint is the workstation's governed surface.
    """
    try:
        from .model.llm_config import _is_local_url, resolve
        for slot in ("chat_model", "specialist_model", "secure_model"):
            model = resolve(slot)
            if model and model.url and _is_local_url(str(model.url)):
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


def _probe_audio() -> bool:
    """Can the voice pipeline run (audio_config enabled + sherpa-onnx)?

    Presence only — never a variant check. A ``home`` appliance and a
    sysadmin workstation can both be the voice terminal; what matters is
    that the operator enabled audio (``audio_config.yml enabled: true``)
    and the inference runtime is importable. ``being.yml
    capabilities: {audio: false}`` remains the operator override that
    wins over this probe.
    """
    try:
        from .audio.config import load_config
        from .audio.is_available import is_audio_available
        return bool(load_config().enabled and is_audio_available())
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
    CAP_AUDIO: _probe_audio,
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

    @staticmethod
    def _resolve_variant() -> str:
        """Resolve the variant the same way the rest of the backend does.

        being.yml > HALBERT_VARIANT env > 'sysadmin' — delegates to
        ``cognition_wiring._get_variant()`` rather than reading
        ``load_being_config().variant`` directly, which defaults to
        'sysadmin' and never consults the env var (U6-BUG-01). A home
        node deployed env-only (``deploy/halbert-home.service``, no
        being.yml) was getting the sysadmin preset — scheduler,
        ingestion, discovery and terminal all True — because this
        method never looked past the (absent) file.

        The import is lazy: capabilities.py has no module-level
        dependency on integrations, and any failure there simply falls
        back to 'sysadmin' rather than breaking capability resolution.
        """
        try:
            from .integrations.cognition_wiring import _get_variant
            return _get_variant()
        except Exception:
            return "sysadmin"

    def _load_config(self) -> tuple:
        """Load variant and explicit capability overrides from being.yml.

        Returns (variant, overrides_dict).
        """
        variant = self._resolve_variant()
        overrides: Dict[str, bool] = {}
        try:
            # The capabilities section is not a typed field on BeingConfig
            # (yet) — read it from the raw YAML to avoid a migration.
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
        except Exception as e:
            logger.debug("Capability override load failed, using defaults: %s", e)
            return variant, {}
        return variant, overrides

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
