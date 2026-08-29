# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""HA Config Awareness Tools — LLM tools for querying HA config via SourcePrep.

Phase 3: These tools let the LLM search HA configuration files (automations,
scripts, dashboards, etc.) via SourcePrep semantic search.

Registered alongside ha_call_service and ha_get_entity_state.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .ha_config_bridge import search_ha_config, check_sourceprep_status

logger = logging.getLogger("halbert.integrations.home_assistant.config_tools")

# --- Tool Schemas ---

HA_SEARCH_CONFIG_SCHEMA = {
    "name": "ha_search_config",
    "description": (
        "Search Home Assistant configuration files (automations, scripts, "
        "dashboards, sensors) using semantic search. Use this to answer "
        "questions about WHY things happen in the house, find automations "
        "that touch specific entities, or understand config relationships. "
        "Requires SourcePrep to be configured and the HA config project indexed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Natural language query about HA configuration. "
                    "Examples: 'automations that control the front door lock', "
                    "'thermostat schedule changes', 'why does the living room "
                    "light turn on at sunset'"
                ),
            },
            "k": {
                "type": "integer",
                "description": "Number of results to return (default 5, max 10)",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}

HA_CONFIG_STATUS_SCHEMA = {
    "name": "ha_config_status",
    "description": (
        "Check if SourcePrep is running and the HA config project is indexed. "
        "Use this before ha_search_config to verify the config search is available."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}


# --- ToolExecutor-compatible handlers ---

async def _ha_search_config_handler(args: Dict[str, Any]) -> str:
    """ToolExecutor handler for ha_search_config."""
    query = args.get("query", "")
    k = min(args.get("k", 5), 10)

    if not query:
        return "No query provided."

    results = search_ha_config(query, k=k)

    if not results:
        return (
            "No HA config results found. This could mean:\n"
            "- SourcePrep is not running or not configured\n"
            "- The HA config project has not been indexed\n"
            "- No config files match the query\n"
            "Check ha_config_status for diagnostics."
        )

    lines = [f"Found {len(results)} config result(s) for '{query}':\n"]
    for i, chunk in enumerate(results, 1):
        file_path = chunk.get("file_path", "unknown")
        score = chunk.get("score", 0)
        content = chunk.get("content", chunk.get("text", ""))
        # Truncate long content
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"--- Result {i} (score: {score:.2f}, file: {file_path}) ---")
        lines.append(content)
        lines.append("")

    return "\n".join(lines)


async def _ha_config_status_handler(args: Dict[str, Any]) -> str:
    """ToolExecutor handler for ha_config_status."""
    status = check_sourceprep_status()

    if not status["daemon_reachable"]:
        return f"SourcePrep daemon not reachable: {status.get('error', 'unknown')}"

    if not status["indexed"]:
        return (
            f"SourcePrep is running but project '{status['project_id']}' "
            f"is not indexed. Register the HA config directory "
            f"({status['config_path']}) as a SourcePrep project."
        )

    return (
        f"SourcePrep is running and project '{status['project_id']}' is indexed. "
        f"HA config path: {status['config_path']}. "
        f"Config search is available."
    )


# --- Registration ---

HA_CONFIG_TOOLS = [HA_SEARCH_CONFIG_SCHEMA, HA_CONFIG_STATUS_SCHEMA]
HA_CONFIG_HANDLERS = {
    "ha_search_config": _ha_search_config_handler,
    "ha_config_status": _ha_config_status_handler,
}


def register_ha_config_tools(tool_executor) -> None:
    """Register HA config awareness tools with the ToolExecutor.

    Args:
        tool_executor: ToolExecutor instance to register tools with.
    """
    for schema in HA_CONFIG_TOOLS:
        handler = HA_CONFIG_HANDLERS.get(schema["name"])
        if handler:
            tool_executor.register(
                name=schema["name"],
                schema=schema,
                handler=handler,
            )
            logger.info(f"Registered HA config tool: {schema['name']}")
