# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Minimal HA service-call tool for Phase 1 chat integration.

This wraps HA's call_service endpoint so the LLM can control devices
through chat. Phase 1 has no governance restrictions — the user is in
the loop and sees every call in the conversation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .ha_client import HAClient
from .ha_config import load_ha_config

logger = logging.getLogger("halbert.integrations.home_assistant.tool")

# Module-level singleton client (created on first use)
_client: Optional[HAClient] = None


def _get_client() -> HAClient:
    global _client
    if _client is None:
        _client = HAClient(load_ha_config())
    return _client


async def ha_call_service(
    domain: str,
    service: str,
    entity_id: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> str:
    """Call a Home Assistant service.

    Args:
        domain: HA service domain (e.g. 'light', 'climate', 'lock').
        service: Service name (e.g. 'turn_on', 'turn_off', 'set_temperature').
        entity_id: Optional entity to target (e.g. 'light.living_room').
        data: Optional service data dict (e.g. {'brightness': 128}).

    Returns:
        Human-readable result string for the chat.
    """
    client = _get_client()
    if not client.config.is_configured():
        return "Home Assistant is not configured. Set the connection in the Home panel first."

    service_data = data or {}
    if entity_id:
        service_data["entity_id"] = entity_id

    try:
        result = await client.call_service(domain, service, service_data)
        target = f" on {entity_id}" if entity_id else ""
        return f"Called {domain}.{service}{target}. {len(result.get('entities', []))} entity/entities affected."
    except Exception as e:
        return f"Failed to call {domain}.{service}: {e}"


async def close_client() -> None:
    """Close the HA client session (call on shutdown)."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
