# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Apple Intelligence auto-provisioning.

Lives outside :mod:`model.llm_config` (the single owner of the ``llm_config``
section) because provisioning needs :class:`HardwareCapabilities` from
:mod:`model.hardware_detector`, and importing hardware detection into the
config store would violate the separation the store was built to enforce.

The provisioning is **idempotent**: it checks whether the
``apple-foundation`` endpoint already exists (not whether any endpoints
exist), and only assigns slots that are currently empty. A user who clears
a slot afterwards keeps it cleared — this never overwrites a deliberate
choice.
"""

from __future__ import annotations

import logging
from typing import Optional

from . import llm_config as _store
from .hardware_detector import HardwareCapabilities

logger = logging.getLogger("halbert.model.auto_provision")

# On 16-24GB Macs the single local model rule applies: Apple Intelligence
# serves both secure_model and chat_model. On 32GB+ Macs chat_model is left
# for the user to configure (cloud or a larger local model).
_SINGLE_MODEL_MAX_GB = 24


def _is_home_variant() -> bool:
    """True when the active instance runs a home automation variant.

    secure_model is a sysadmin-instance slot (see the module docstring in
    ``integrations/cognition_wiring.py``): an HA variant's LLM reaches the
    house through tool calls that abstract credentials away, so it never
    provisions a dedicated secure model. The import is lazy so the model
    layer carries no module-level dependency on the integrations package.
    """
    try:
        from ..integrations.cognition_wiring import is_home_variant
        return is_home_variant()
    except Exception:
        return False


def auto_provision_apple_intelligence(hardware: HardwareCapabilities) -> bool:
    """Register the Apple Intelligence endpoint and assign empty slots.

    Called on first boot (or wizard run) when the host is eligible for
    Apple Intelligence. Does nothing when:

    - ``hardware.apple_intelligence_available`` is False
    - the active variant is home (secure_model is a
      sysadmin-instance slot, so Apple Intelligence is not provisioned
      for home automation variants at all)
    - the ``apple-foundation`` endpoint is already registered (idempotent)

    Slot assignment rules:

    - ``secure_model``: assigned to Apple Intelligence when currently empty
    - ``chat_model``: assigned only on 16-24GB Macs (single-model rule),
      and only when currently empty

    Returns True when any provisioning action was taken.
    """
    if not hardware.apple_intelligence_available:
        return False

    if _is_home_variant():
        logger.debug(
            "Home automation variant — Apple Intelligence provisioning skipped "
            "(secure_model is a sysadmin-instance slot)"
        )
        return False

    cfg = _store.load_global(use_cache=False)
    existing = [
        ep for ep in cfg.get("saved_endpoints", [])
        if ep.get("provider") == _store.APPLE_FOUNDATION_PROVIDER
    ]
    if existing:
        logger.debug("Apple Intelligence endpoint already registered — skipping")
        return False

    ep_id = _store.ensure_apple_foundation_endpoint()
    model = _store.APPLE_FOUNDATION_MODEL
    changed = False

    # secure_model: always assign when empty (mandatory local slot)
    secure = cfg.get("secure_model") or {}
    if not secure.get("model"):
        _store.set_slot("secure_model", model, ep_id)
        changed = True
        logger.info("Apple Intelligence assigned to secure_model")

    # chat_model: only on 16-24GB Macs (single-model rule), when empty
    mem = hardware.unified_memory_gb or 0
    if mem and mem <= _SINGLE_MODEL_MAX_GB:
        chat = cfg.get("chat_model") or {}
        if not chat.get("model"):
            _store.set_slot("chat_model", model, ep_id)
            changed = True
            logger.info(
                "Apple Intelligence assigned to chat_model "
                "(%dGB — single local model rule)", mem,
            )

    if not changed:
        logger.debug("Apple Intelligence endpoint registered but no empty slots to fill")
    return changed
