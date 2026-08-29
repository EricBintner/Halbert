# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Frigate tools for LLM function calling.

Registers frigate_get_events, frigate_get_snapshot, frigate_get_latest_frame,
frigate_review_event, frigate_list_cameras with the ToolExecutor so the
LLM can query camera detections through chat.

Mirrors ha_tool.py: module-level singleton client, register_frigate_tools().
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Optional

from .frigate_config import load_frigate_config
from .frigate_client import FrigateClient

logger = logging.getLogger("halbert.integrations.frigate.tools")

# Module-level singleton client (created on first use)
_client: Optional[FrigateClient] = None


def _get_client() -> FrigateClient:
    global _client
    if _client is None:
        _client = FrigateClient(load_frigate_config())
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


# --- Tool schemas ---

FRIGATE_GET_EVENTS_SCHEMA = {
    "name": "frigate_get_events",
    "description": (
        "Query recent detection events from Frigate cameras. "
        "Returns events with camera, label (person/car/dog), zones, "
        "score, timestamps, and snapshot/clip availability. "
        "Use this to answer 'what happened on the cameras?' or "
        "'did anything happen last night?'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "camera": {
                "type": "string",
                "description": "Camera name (e.g. 'front_door') or 'all' for all cameras",
            },
            "labels": {
                "type": "string",
                "description": "Comma-separated labels to filter (e.g. 'person,car') or 'all'",
            },
            "zones": {
                "type": "string",
                "description": "Comma-separated zones to filter or 'all'",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum events to return (default 20)",
            },
            "in_progress": {
                "type": "boolean",
                "description": "Only return in-progress detections (default false)",
            },
        },
    },
}

FRIGATE_GET_SNAPSHOT_SCHEMA = {
    "name": "frigate_get_snapshot",
    "description": (
        "Get the snapshot image for a specific Frigate event. "
        "Returns a base64-encoded JPEG with bounding box overlay. "
        "Use this when the user asks to 'show me' or 'see' a detection."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "Frigate event ID (from frigate_get_events)",
            },
            "crop": {
                "type": "boolean",
                "description": "Crop to the detected object's bounding box (default false)",
            },
        },
        "required": ["event_id"],
    },
}

FRIGATE_GET_LATEST_FRAME_SCHEMA = {
    "name": "frigate_get_latest_frame",
    "description": (
        "Get the latest live frame from a Frigate camera. "
        "Returns a base64-encoded JPEG with bounding boxes and zones. "
        "Use this when the user asks 'what's on the camera right now?'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "camera": {
                "type": "string",
                "description": "Camera name (e.g. 'front_door', 'back_yard')",
            },
        },
        "required": ["camera"],
    },
}

FRIGATE_REVIEW_EVENT_SCHEMA = {
    "name": "frigate_review_event",
    "description": (
        "Get detailed information about a specific Frigate event, "
        "including the full detection timeline, zone transitions, "
        "and attribute scores. Use after frigate_get_events to drill "
        "into a specific detection."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "Frigate event ID",
            },
        },
        "required": ["event_id"],
    },
}

FRIGATE_LIST_CAMERAS_SCHEMA = {
    "name": "frigate_list_cameras",
    "description": (
        "List all configured Frigate cameras with their zones and "
        "detection settings. Use this to discover available cameras."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

FRIGATE_GET_REVIEWS_SCHEMA = {
    "name": "frigate_get_reviews",
    "description": (
        "Query review segments from Frigate. Reviews are higher-level "
        "groupings of events with severity (alert/detection). "
        "Use this to see what needs attention."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "camera": {
                "type": "string",
                "description": "Camera name or 'all'",
            },
            "severity": {
                "type": "string",
                "description": "Filter by severity: 'alert', 'detection', or 'all'",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum reviews to return (default 20)",
            },
        },
    },
}


# --- ToolExecutor-compatible handlers ---

async def _frigate_get_events_handler(args: Dict[str, Any]) -> str:
    client = _get_client()
    if not client.config.is_configured():
        return "Frigate is not configured. Set the connection in the Home panel first."

    try:
        events = await client.get_events(
            camera=args.get("camera", "all"),
            labels=args.get("labels", "all"),
            zones=args.get("zones", "all"),
            limit=args.get("limit", 20),
            in_progress=args.get("in_progress", False),
        )
        if not events:
            return "No events found matching the criteria."

        lines = [f"Found {len(events)} event(s):"]
        for e in events[:20]:
            label = e.get("label", "?")
            camera = e.get("camera", "?")
            zones = ", ".join(e.get("zones", [])) or "no zone"
            score = e.get("top_score", 0)
            start = e.get("start_time", 0)
            has_snap = e.get("has_snapshot", False)
            has_clip = e.get("has_clip", False)
            eid = e.get("id", "")[:12]
            from datetime import datetime
            ts = datetime.fromtimestamp(start).strftime("%H:%M:%S") if start else "?"
            snap = " [snapshot]" if has_snap else ""
            clip = " [clip]" if has_clip else ""
            lines.append(f"  {ts} {camera}: {label} in {zones} (score={score:.2f}){snap}{clip} id={eid}")
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to query Frigate events: {e}"


async def _frigate_get_snapshot_handler(args: Dict[str, Any]) -> str:
    client = _get_client()
    if not client.config.is_configured():
        return "Frigate is not configured."

    event_id = args.get("event_id", "")
    if not event_id:
        return "event_id is required."

    try:
        jpeg_bytes = await client.get_event_snapshot(
            event_id,
            crop=args.get("crop", False),
        )
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        return f"Failed to get snapshot: {e}"


async def _frigate_get_latest_frame_handler(args: Dict[str, Any]) -> str:
    client = _get_client()
    if not client.config.is_configured():
        return "Frigate is not configured."

    camera = args.get("camera", "")
    if not camera:
        return "camera is required."

    try:
        jpeg_bytes = await client.get_latest_frame(camera)
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        return f"Failed to get latest frame from {camera}: {e}"


async def _frigate_review_event_handler(args: Dict[str, Any]) -> str:
    client = _get_client()
    if not client.config.is_configured():
        return "Frigate is not configured."

    event_id = args.get("event_id", "")
    if not event_id:
        return "event_id is required."

    try:
        event = await client.get_event(event_id)
        label = event.get("label", "?")
        camera = event.get("camera", "?")
        zones = event.get("zones", [])
        score = event.get("top_score", 0)
        start = event.get("start_time", 0)
        end = event.get("end_time")
        sub_label = event.get("sub_label")
        attributes = event.get("attributes", {})
        data = event.get("data", {})

        from datetime import datetime
        start_ts = datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M:%S") if start else "?"
        end_ts = datetime.fromtimestamp(end).strftime("%H:%M:%S") if end else "in progress"

        lines = [
            f"Event {event_id}",
            f"  Camera: {camera}",
            f"  Label: {label}" + (f" ({sub_label})" if sub_label else ""),
            f"  Zones: {', '.join(zones) or 'none'}",
            f"  Score: {score:.2f}",
            f"  Start: {start_ts}",
            f"  End: {end_ts}",
        ]
        if attributes:
            lines.append(f"  Attributes: {attributes}")
        if data:
            lines.append(f"  Data: {data}")
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to review event: {e}"


async def _frigate_list_cameras_handler(args: Dict[str, Any]) -> str:
    client = _get_client()
    if not client.config.is_configured():
        return "Frigate is not configured."

    try:
        cameras = await client.get_cameras()
        if not cameras:
            return "No cameras configured in Frigate."

        lines = [f"Frigate has {len(cameras)} camera(s):"]
        for cam in cameras:
            zones = ", ".join(cam.get("zones", [])) or "no zones"
            objects = cam.get("objects", {})
            detect = "enabled" if cam.get("detect", True) else "disabled"
            lines.append(f"  {cam['name']}: zones=[{zones}], detection={detect}")
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to list cameras: {e}"


async def _frigate_get_reviews_handler(args: Dict[str, Any]) -> str:
    client = _get_client()
    if not client.config.is_configured():
        return "Frigate is not configured."

    try:
        reviews = await client.get_reviews(
            camera=args.get("camera", "all"),
            severity=args.get("severity", "all"),
            limit=args.get("limit", 20),
        )
        if not reviews:
            return "No reviews found."

        lines = [f"Found {len(reviews)} review(s):"]
        for r in reviews[:20]:
            severity = r.get("severity", "?")
            camera = r.get("camera", "?")
            start = r.get("start_time", 0)
            from datetime import datetime
            ts = datetime.fromtimestamp(start).strftime("%H:%M:%S") if start else "?"
            lines.append(f"  {ts} {camera}: {severity}")
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to query reviews: {e}"


# --- Registration ---

def register_frigate_tools(tool_executor) -> None:
    """Register Frigate tools with a ToolExecutor instance.

    Call this alongside register_ha_tools() in get_agent().
    Only registers if Frigate is configured.
    """
    config = load_frigate_config()
    if not config.is_configured():
        logger.info("Frigate not configured; tools not registered")
        return

    tool_executor.register("frigate_get_events", _frigate_get_events_handler, FRIGATE_GET_EVENTS_SCHEMA)
    tool_executor.register("frigate_get_snapshot", _frigate_get_snapshot_handler, FRIGATE_GET_SNAPSHOT_SCHEMA)
    tool_executor.register("frigate_get_latest_frame", _frigate_get_latest_frame_handler, FRIGATE_GET_LATEST_FRAME_SCHEMA)
    tool_executor.register("frigate_review_event", _frigate_review_event_handler, FRIGATE_REVIEW_EVENT_SCHEMA)
    tool_executor.register("frigate_list_cameras", _frigate_list_cameras_handler, FRIGATE_LIST_CAMERAS_SCHEMA)
    tool_executor.register("frigate_get_reviews", _frigate_get_reviews_handler, FRIGATE_GET_REVIEWS_SCHEMA)
    logger.info("Registered Frigate tools (6 tools)")
