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
from typing import List, Optional

from . import llm_config as _store
from .hardware_detector import HardwareCapabilities

logger = logging.getLogger("halbert.model.auto_provision")

# On 16-24GB Macs the single local model rule applies: Apple Intelligence
# serves both secure_model and chat_model. On 32GB+ Macs chat_model is left
# for the user to configure (cloud or a larger local model).
_SINGLE_MODEL_MAX_GB = 24


def auto_provision_apple_intelligence(hardware: HardwareCapabilities) -> bool:
    """Register the Apple Intelligence endpoint and assign empty slots.

    Called on first boot (or wizard run) when the host is eligible for
    Apple Intelligence. Does nothing when:

    - ``hardware.apple_intelligence_available`` is False (not eligible)
    - ``hardware.apple_intelligence_bridge_running`` is False (eligible,
      but the Swift FoundationModels sidecar is not actually up — the
      endpoint would be inert, so it is not registered at all)
    - the active variant is not allowed to host a secure model
      (``CAP_SECURE_MODEL_ALLOWED`` — the preset/override signal, never
      the probe: secure_model is a sysadmin-instance slot, so home
      instances are not provisioned by default)
    - the ``apple-foundation`` endpoint is already registered (idempotent)

    Slot assignment rules:

    - ``secure_model``: assigned to Apple Intelligence when currently empty
    - ``chat_model``: assigned only on 16-24GB Macs (single-model rule),
      and only when currently empty

    Returns True when any provisioning action was taken.
    """
    if not hardware.apple_intelligence_available:
        return False

    # Gate on "this variant may host a secure model" (preset/override,
    # never probed) — not CAP_SECURE_MODEL, which means "one is already
    # configured". Gating on the probe was circular: a fresh install has
    # nothing configured yet, so the probe was always False and
    # provisioning could never run (U4-18/R05-N1/U6-BUG-02).
    _secure_allowed = False
    try:
        from ..capabilities import has_capability, CAP_SECURE_MODEL_ALLOWED
        _secure_allowed = has_capability(CAP_SECURE_MODEL_ALLOWED)
    except Exception:
        pass
    if not _secure_allowed:
        logger.debug(
            "Apple Intelligence provisioning skipped "
            "(secure_model not allowed for this variant)"
        )
        return False

    if not hardware.apple_intelligence_bridge_running:
        logger.debug(
            "Apple Intelligence provisioning skipped "
            "(eligible but the FoundationModels bridge is not running)"
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


def reconcile_apple_intelligence(hardware: HardwareCapabilities) -> List[str]:
    """Clear slots that point at the Apple Intelligence endpoint when its
    bridge is not running. Returns the slots it cleared.

    The symmetric operation to :func:`auto_provision_apple_intelligence`.
    Provisioning assigns the slot when the FoundationModels bridge answers
    the probe; nothing ever looked again, and the boot path skips
    provisioning entirely once the endpoint exists -- so a slot assigned at
    a boot where the probe passed stayed assigned after the bridge went
    away. On the founder's machine that was ``secure_model`` pointing at a
    port nothing listens on (APPLE-1), and every secure turn tried it,
    failed, and fell back to the guide -- which is how SEC-21 was reached.

    Only the *assignment* goes. The endpoint stays registered: the host is
    still eligible, the picker should still list it, and provisioning will
    re-fill an empty slot when the bridge is next seen. Only slots whose
    ``endpoint_id`` is the Apple one are touched -- a local Ollama secure
    model the user chose deliberately is not this function's business.

    Logged at WARNING per slot: clearing a configured model must be said out
    loud, in the same log a person reads when a secure turn fails closed.
    """
    if hardware.apple_intelligence_bridge_running:
        return []
    cfg = _store.load_global(use_cache=False)
    apple_ids = {
        ep.get("id") for ep in cfg.get("saved_endpoints", [])
        if ep.get("provider") == _store.APPLE_FOUNDATION_PROVIDER
    }
    if not apple_ids:
        return []
    cleared: List[str] = []
    for slot in ("secure_model", "chat_model", "specialist_model", "vision_model"):
        s = cfg.get(slot) or {}
        if s.get("model") and s.get("endpoint_id") in apple_ids:
            _store.set_slot(slot, "", s["endpoint_id"])
            cleared.append(slot)
            logger.warning(
                "%s pointed at Apple Intelligence (%s) but the FoundationModels "
                "bridge is not running — slot disabled until it is. A secure "
                "turn will fail closed rather than fall back to a cloud model.",
                slot, s.get("model"),
            )
    return cleared

