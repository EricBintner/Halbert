# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Assist API Tools — LLM tools for HA's native conversation/intent API.

Phase 6: These tools let the LLM use HA's built-in Assist API to run
intents (TurnOn, TurnOff, GetState, etc.) via the /api/conversation/process
endpoint. This is complementary to the direct ha_call_service tool —
the Assist API handles intent matching and natural language entity
resolution natively, while ha_call_service gives precise control.

Use case: When a user says "turn on the living room lights" through
the Wyoming agent, Halbert can either:
  1. Use ha_call_service with exact entity_ids (requires knowing them)
  2. Use ha_assist_process to let HA's intent matcher resolve the request

Option 2 is simpler for natural language and leverages HA's built-in
entity matching, area awareness, and exposure settings.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger("halbert.integrations.home_assistant.assist_tools")

# --- Tool Schemas ---

HA_ASSIST_PROCESS_SCHEMA = {
    "name": "ha_assist_process",
    "description": (
        "Send a natural language command to Home Assistant's Assist API. "
        "HA's intent matcher resolves entity names, areas, and exposure settings. "
        "Use this when the user gives a vague command like 'turn on the lights' "
        "and you want HA to figure out which entities to control. "
        "This is often simpler than ha_call_service for natural language requests."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": (
                    "The natural language command to process. "
                    "Examples: 'turn on the living room lights', "
                    "'what's the temperature in the bedroom', "
                    "'lock the front door'"
                ),
            },
            "conversation_id": {
                "type": "string",
                "description": "Optional conversation ID for multi-turn context",
                "default": "",
            },
            "language": {
                "type": "string",
                "description": "Language of the command (default: en)",
                "default": "en",
            },
        },
        "required": ["text"],
    },
}


# --- ToolExecutor-compatible handlers ---

async def _ha_assist_process_handler(args: Dict[str, Any]) -> str:
    """ToolExecutor handler for ha_assist_process."""
    text = args.get("text", "")
    conversation_id = args.get("conversation_id", "")
    language = args.get("language", "en")

    if not text:
        return "No command provided."

    try:
        from .ha_config import load_ha_config
        config = load_ha_config()
        if not config.is_configured():
            return "Home Assistant is not configured."

        result = await _call_assist_api(
            url=config.url,
            token=config.token,
            text=text,
            conversation_id=conversation_id,
            language=language,
            verify_ssl=config.verify_ssl,
        )

        response = result.get("response", {})
        speech = response.get("speech", {})
        speech_text = speech.get("plain", {}).get("speech", "")

        if not speech_text:
            speech_text = response.get("response_type", "unknown")

        conversation_id = result.get("conversation_id", conversation_id)

        return f"Assist response: {speech_text}"

    except Exception as e:
        logger.error(f"Assist API call failed: {e}")
        return f"Failed to process command via Assist API: {e}"


async def _call_assist_api(
    url: str,
    token: str,
    text: str,
    conversation_id: str = "",
    language: str = "en",
    verify_ssl: bool = True,
) -> Dict[str, Any]:
    """Call HA's /api/conversation/process endpoint."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body: Dict[str, Any] = {"text": text, "language": language}
    if conversation_id:
        body["conversation_id"] = conversation_id

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{url.rstrip('/')}/api/conversation/process",
            json=body,
            headers=headers,
            ssl=verify_ssl,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()


# --- Registration ---

ASSIST_TOOLS = [HA_ASSIST_PROCESS_SCHEMA]
ASSIST_HANDLERS = {
    "ha_assist_process": _ha_assist_process_handler,
}


def register_assist_tools(tool_executor) -> None:
    """Register Assist API tools with the ToolExecutor.

    Args:
        tool_executor: ToolExecutor instance to register tools with.
    """
    for schema in ASSIST_TOOLS:
        handler = ASSIST_HANDLERS.get(schema["name"])
        if handler:
            tool_executor.register(
                name=schema["name"],
                schema=schema,
                handler=handler,
            )
            logger.info(f"Registered Assist API tool: {schema['name']}")
