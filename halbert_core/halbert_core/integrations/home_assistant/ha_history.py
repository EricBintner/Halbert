# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""HA History backfill — query past events on first connection.

On first connection, query GET /api/history/period/<timestamp> for the
last 7-14 days. Feed significant events (door opens, alarm state changes,
occupancy transitions) into PersonaCognition as pre-existing observations.

This makes Halbert feel like it has known the house from minute one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .ha_client import HAClient

logger = logging.getLogger("halbert.integrations.home_assistant.history")

# Domains whose history is worth backfilling
SIGNIFICANT_DOMAINS = {
    "lock",
    "alarm_control_panel",
    "person",
    "device_tracker",
    "binary_sensor",
    "climate",
    "input_boolean",
}

# How far back to query
DEFAULT_BACKFILL_DAYS = 7


async def backfill_history(
    client: HAClient,
    days: int = DEFAULT_BACKFILL_DAYS,
    on_event: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Query HA history and return significant state changes.

    Args:
        client: Connected HAClient instance.
        days: How many days back to query (default 7).
        on_event: Optional async callback called per significant event.

    Returns:
        List of significant state change dicts.
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    # HA history API expects ISO 8601 timestamps
    start_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        result = await client._request(
            "GET",
            f"/api/history/period/{start_str}",
        )
    except Exception as e:
        logger.warning(f"HA history backfill failed: {e}")
        return []

    if not isinstance(result, list):
        logger.warning("HA history returned unexpected format")
        return []

    significant: List[Dict[str, Any]] = []

    # HA history returns a list of lists, each inner list is an entity's history
    for entity_history in result:
        if not isinstance(entity_history, list):
            continue
        for state_entry in entity_history:
            entity_id = state_entry.get("entity_id", "")
            domain = entity_id.split(".")[0] if "." in entity_id else ""

            if domain not in SIGNIFICANT_DOMAINS:
                continue

            state = state_entry.get("state", "")
            if state in ("unavailable", "unknown", None):
                continue

            event = {
                "entity_id": entity_id,
                "domain": domain,
                "state": state,
                "attributes": state_entry.get("attributes", {}),
                "last_changed": state_entry.get("last_changed", ""),
            }
            significant.append(event)

            if on_event and asyncio_callable(on_event):
                import asyncio
                asyncio.get_event_loop().create_task(on_event(event))

    logger.info(f"HA history backfill: {len(significant)} significant events from {days} days")
    return significant


def asyncio_callable(fn) -> bool:
    """Check if fn is a coroutine function."""
    import inspect
    return inspect.iscoroutinefunction(fn)
