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

router = APIRouter()


@router.get("/api/instance/info")
async def get_instance_info() -> Dict[str, Any]:
    """Return the current instance's identity and feature flags.

    The frontend uses this to:
    - Filter sidebar navigation (hide Home tab on host, hide Dev tabs on home)
    - Display the Instance Switcher with correct label and color
    - Show the right persona name in the top bar
    """
    persona_id = os.environ.get("HALBERT_PERSONA_ID", "halbert")
    scene_context = os.environ.get("HALBERT_SCENE_CONTEXT", "")
    port = int(os.environ.get("HALBERT_PORT", "8000"))

    # Determine role from persona_id
    role = "host" if persona_id == "halbert" else "home"
    # Same resolution as backend service gating (app.py startup): a
    # being.yml-set variant must reach the frontend too, or nav gating
    # disagrees with what services actually launched.
    from ...integrations.cognition_wiring import _get_variant
    variant = _get_variant()

    # Feature flags — which tabs/pages should be visible
    features = {
        "home": role == "home" or os.environ.get("HALBERT_ENABLE_HOME_TAB", "").lower() in ("1", "true", "yes"),
        "gpu": os.environ.get("HALBERT_ENABLE_GPU_TAB", "").lower() in ("1", "true", "yes") or role == "host",
        "development": role == "host",
        "wyoming_port": int(os.environ.get("WYOMING_PORT", "10400")),
    }

    # Display info
    display_name = persona_id.capitalize()
    if role == "host":
        display_name = os.environ.get("HALBERT_DISPLAY_NAME", "Host")
    elif role == "home":
        display_name = os.environ.get("HALBERT_DISPLAY_NAME", "Home")

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
    }
