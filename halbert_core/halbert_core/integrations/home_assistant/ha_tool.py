# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""HA service-call tools for LLM function calling.

Registers `ha_call_service` and `ha_get_entity_state` with the
ToolExecutor so the LLM can control HA devices through chat.

All service calls pass through the AutonomyGate (REV-03 F2) — the
same gate the MCP path uses — so the autonomy_level setting is
enforced consistently across chat, MCP, and the HTTP API.
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


def _get_autonomy_gate():
    """Get the AutonomyGate from BeingConfig (same pattern as mcp/server.py)."""
    try:
        from .autonomy_gate import AutonomyGate
        from .ha_governance import HAGovernancePolicy
        from ...config.being_config import load_being_config
        cfg = load_being_config()
        return AutonomyGate(
            autonomy_level=cfg.autonomy_level,
            autonomy_overrides=cfg.autonomy_overrides,
            governance=HAGovernancePolicy(),
        )
    except Exception as e:
        logger.debug(f"Autonomy gate not available: {e}")
        return None


async def close_client() -> None:
    """Close the HA client session (call on shutdown)."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


# --- Tool schemas ---

HA_CALL_SERVICE_SCHEMA = {
    "name": "ha_call_service",
    "description": (
        "Call a Home Assistant service to control a device. "
        "Examples: turn lights on/off, set climate temperature, lock/unlock doors. "
        "Use ha_get_entity_state to check current state before calling."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "HA service domain (e.g. 'light', 'climate', 'lock', 'switch', 'cover')",
            },
            "service": {
                "type": "string",
                "description": "Service name (e.g. 'turn_on', 'turn_off', 'set_temperature', 'lock', 'unlock')",
            },
            "entity_id": {
                "type": "string",
                "description": "Entity to target (e.g. 'light.living_room', 'climate.bedroom')",
            },
            "data": {
                "type": "object",
                "description": "Additional service data (e.g. {'brightness': 128, 'temperature': 21})",
            },
        },
        "required": ["domain", "service", "entity_id"],
    },
}

HA_GET_ENTITY_STATE_SCHEMA = {
    "name": "ha_get_entity_state",
    "description": (
        "Get the current state of a Home Assistant entity. "
        "Use this before calling ha_call_service to check current state."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "entity_id": {
                "type": "string",
                "description": "Entity ID (e.g. 'light.living_room', 'sensor.temperature')",
            },
        },
        "required": ["entity_id"],
    },
}


# --- ToolExecutor-compatible handlers ---

async def _ha_call_service_handler(args: Dict[str, Any]) -> str:
    """ToolExecutor handler for ha_call_service.

    Passes through the AutonomyGate (REV-03 F2) so the autonomy_level
    setting is enforced on the chat path, matching the MCP path.
    """
    client = _get_client()
    if not client.config.is_configured():
        return "Home Assistant is not configured. Set the connection in the Home panel first."

    domain = args.get("domain", "")
    service = args.get("service", "")
    entity_id = args.get("entity_id", "")
    data = args.get("data") or {}

    # Autonomy gate check (REV-03 F2 — was governance-only, bypassing autonomy_level)
    gate = _get_autonomy_gate()
    if gate is None:
        return "Autonomy gate not available — cannot execute HA commands safely."
    decision = gate.evaluate(domain, entity_id, service)
    if not decision.allowed:
        return f"Blocked: {decision.reason}"
    if decision.requires_proposal:
        return (
            f"This action ({domain}.{service} on {entity_id}) requires a "
            f"proposal at the current autonomy level ({gate.autonomy_level}). "
            f"Use the MCP approve_proposal workflow or raise autonomy to 'act'."
        )
    if not decision.auto_execute:
        return f"Not auto-executed: {decision.reason}"

    if entity_id:
        data["entity_id"] = entity_id

    try:
        result = await client.call_service(domain, service, data)
        target = f" on {entity_id}" if entity_id else ""
        n = len(result.get("entities", []))
        suffix = ""
        if decision.cancel_window_seconds > 0:
            suffix = f" (cancel window: {decision.cancel_window_seconds}s)"
        return f"Called {domain}.{service}{target}. {n} entity/entities affected.{suffix}"
    except Exception as e:
        return f"Failed to call {domain}.{service}: {e}"


async def _ha_get_entity_state_handler(args: Dict[str, Any]) -> str:
    """ToolExecutor handler for ha_get_entity_state."""
    client = _get_client()
    if not client.config.is_configured():
        return "Home Assistant is not configured. Set the connection in the Home panel first."

    entity_id = args.get("entity_id", "")
    try:
        state = await client.get_entity_state(entity_id)
        friendly = state.get("attributes", {}).get("friendly_name", entity_id)
        return f"{friendly} ({entity_id}): state={state.get('state', 'unknown')}"
    except Exception as e:
        return f"Failed to get state for {entity_id}: {e}"


def register_ha_tools(tool_executor) -> None:
    """Register HA tools with a ToolExecutor instance.

    Call this alongside register_system_tools() and register_vision_tools().
    """
    tool_executor.register(
        "ha_call_service",
        _ha_call_service_handler,
        HA_CALL_SERVICE_SCHEMA,
    )
    tool_executor.register(
        "ha_get_entity_state",
        _ha_get_entity_state_handler,
        HA_GET_ENTITY_STATE_SCHEMA,
    )
    logger.info("Registered HA tools (ha_call_service, ha_get_entity_state)")
