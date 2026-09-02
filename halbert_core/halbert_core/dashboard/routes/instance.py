# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Instance info endpoint for multi-instance awareness.

Returns the current Halbert instance's identity, role, and available
features so the frontend can adapt its navigation and display.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter

from ...identity import (
    resolve_body_name,
    resolve_entity_name,
    resolve_entity_role,
    resolve_persona_id,
)

router = APIRouter()


@router.get("/api/instance/info")
async def get_instance_info() -> Dict[str, Any]:
    """Return the current instance's identity and feature flags.

    The frontend uses this to:
    - Filter sidebar navigation (hide Home tab on host, hide Dev tabs on home)
    - Display the Instance Switcher with correct label and color
    - Show the right persona name in the top bar

    ``display_name`` comes from the same resolver as ``/api/identity``
    (``halbert_core.identity``), so the Presence Pill and the greeting
    never disagree about what this machine is called. ``persona_id``
    honours being.yml ``persona_id_override`` the way the memory wiring
    does. ``entity_role`` is the tri-state (canonical | body |
    independent); ``singular`` is its two-state view for the pill.
    """
    persona_id = resolve_persona_id()
    scene_context = os.environ.get("HALBERT_SCENE_CONTEXT", "")
    port = int(os.environ.get("HALBERT_PORT", "8000"))

    # Determine role from the variant, not persona_id (REV-03 F8).
    # A home node with variant:home but no persona_id override gets
    # persona_id == "halbert" → was role "host" → Home tab hidden in
    # its own UI. Variant is the authoritative signal for what services
    # actually launched (app.py keys on it), so the frontend must too.
    from ...integrations.cognition_wiring import _get_variant
    variant = _get_variant()
    role = "home" if variant == "home" else "host"

    # Feature flags — which tabs/pages should be visible
    features = {
        "home": role == "home" or os.environ.get("HALBERT_ENABLE_HOME_TAB", "").lower() in ("1", "true", "yes"),
        "gpu": os.environ.get("HALBERT_ENABLE_GPU_TAB", "").lower() in ("1", "true", "yes") or role == "host",
        "development": role == "host",
        "wyoming_port": int(os.environ.get("WYOMING_PORT", "10400")),
    }

    # The entity's name: HALBERT_DISPLAY_NAME launch override > onboarding
    # ai_name > being.yml name > short hostname > "Halbert". Never a
    # role literal — "Host"/"Home" are what the machine does, not its name.
    display_name = resolve_entity_name()

    # body_name labels which physical body the entity is speaking from
    # (e.g. "desk", "home"). entity_role is "body" when this node proxies
    # memory/threads to a canonical host, "canonical" when it IS the host
    # for at least one paired body, else "independent". singular is true
    # on both sides of a pair — one entity, many bodies.
    body_name = resolve_body_name()
    entity_role = resolve_entity_role()
    singular = entity_role != "independent"

    return {
        "persona_id": persona_id,
        "scene_context": scene_context,
        "role": role,
        "variant": variant,
        "display_name": display_name,
        "port": port,
        "features": features,
        "data_dir": os.environ.get("HALBERT_DATA_DIR") or os.environ.get("Halbert_DATA_DIR", ""),
        "config_dir": os.environ.get("HALBERT_CONFIG_DIR") or os.environ.get("Halbert_CONFIG_DIR", ""),
        "body_name": body_name,
        "entity_role": entity_role,
        "singular": singular,
    }
