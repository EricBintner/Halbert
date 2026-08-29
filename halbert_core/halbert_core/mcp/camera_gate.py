# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MCP security design for camera and vision data.

## Threat Model

The MCP server allows external LLM clients (Claude, GPT, etc.) to query
Halbert's state. Camera footage is the most sensitive data category:

  - Faces of family members and visitors
  - License plates
  - Interior of the home
  - Timestamps that reveal occupancy patterns

## Security Principle: Metadata In, Nothing Out

The MCP server exposes **text metadata** about camera events but
**never raw image bytes**. This means:

  ALLOWED via MCP:
    - "Frigate detected a person at front_door at 14:32"
    - "3 events in the last hour, labels: person, car"
    - "Active detections: person at back_yard"
    - "Camera list: front_door, back_yard, garage"
    - "Object detection result: 2 persons, 1 car (no image)"

  NEVER via MCP:
    - Snapshot JPEGs
    - Latest frame JPEGs
    - Base64-encoded images
    - Image URLs (even local ones)
    - Face embedding vectors
    - Any binary image data

## Implementation

All MCP tools that touch camera/vision data go through a `CameraDataGate`
that strips image fields from responses before they leave the server.
This is a defense-in-depth layer on top of the existing `mcp_response()`
redaction boundary.

## Single-User Verification

The MCP server is designed for a single verified user:
  - stdio transport: same-user, same-machine (no auth needed)
  - HTTP transport: bearer token (HMAC constant-time comparison)
  - No multi-tenant isolation — one Halbert instance = one user

For camera data, the bearer token is the minimum gate. The recommendation
is to use stdio transport for any workflow that touches camera metadata,
and restrict HTTP transport to non-camera queries.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger("halbert.mcp.camera_gate")

# Fields that must never appear in an MCP response
_FORBIDDEN_IMAGE_FIELDS = frozenset({
    "image", "image_b64", "image_base64", "snapshot", "frame",
    "jpeg", "jpg", "thumbnail", "data_uri", "screenshot",
    "frame_bytes", "snapshot_bytes",
    # Additional field names that could carry image data
    "img", "picture", "photo", "video", "clip", "preview",
    "thumb", "src", "href", "url", "base64", "b64",
    "image_url", "media", "content", "encoded_image", "picture_url",
    "thumbnail_b64", "preview_b64",
})

# Regex for detecting data URIs (case-insensitive, allows whitespace prefix)
_DATA_URI_RE = re.compile(r'^\s*data:image/[^\s;]+;base64,', re.IGNORECASE)

# Fields that are safe to expose as text metadata
_SAFE_METADATA_FIELDS = frozenset({
    "id", "camera", "label", "sub_label", "zones", "current_zones",
    "entered_zones", "score", "top_score", "start_time", "end_time",
    "has_snapshot", "has_clip", "stationary", "active", "attributes",
    "false_positive", "severity", "type", "count", "detections",
    "faces", "motion_ratio", "has_motion", "bounding_boxes",
    "frame_shape", "zone_name", "timestamp", "cameras", "connected",
    "configured", "mqtt_enabled", "error", "status", "source",
    "class_id", "confidence", "bbox", "backend", "labels",
})


def _looks_like_image_data(value: Any) -> bool:
    """Check if a value looks like image data (data URI or base64 blob)."""
    if not isinstance(value, str):
        return False
    # Case-insensitive data URI check with whitespace tolerance
    if _DATA_URI_RE.match(value):
        return True
    # Long base64 strings (>1000 chars) are likely image data
    if len(value) > 1000 and re.match(r'^[A-Za-z0-9+/=\s]+$', value):
        return True
    return False


def strip_image_data(payload: Any) -> Any:
    """Recursively strip image data from a payload.

    This is the camera data gate. It removes:
    1. Any field whose name matches a known image field
    2. Any field whose value is a data:image/... URI
    3. Any string in a list that looks like image data
    4. Any suspiciously long base64 string

    Called on every MCP response that touches camera/vision data,
    before the response is sent to the client.
    """
    if isinstance(payload, dict):
        cleaned = {}
        for key, value in payload.items():
            if key.lower() in _FORBIDDEN_IMAGE_FIELDS:
                cleaned[key] = "<redacted:image>"
                continue
            if _looks_like_image_data(value):
                cleaned[key] = "<redacted:image>"
                continue
            cleaned[key] = strip_image_data(value)
        return cleaned
    elif isinstance(payload, list):
        result = []
        for item in payload:
            if _looks_like_image_data(item):
                result.append("<redacted:image>")
            else:
                result.append(strip_image_data(item))
        return result
    else:
        return payload


def is_camera_query(tool_name: str) -> bool:
    """Check if a tool name touches camera/vision data.

    Used to decide whether to apply the camera data gate.
    This list must match the keys in FRIGATE_MCP_TOOL_HANDLERS.
    """
    camera_tools = frozenset({
        # Frigate metadata tools (in FRIGATE_MCP_TOOL_HANDLERS)
        "frigate_get_events",
        "frigate_get_reviews",
        "frigate_list_cameras",
        "frigate_get_active_detections",
        # Vision metadata tools (in FRIGATE_MCP_TOOL_HANDLERS)
        "vision_get_detections",
        "vision_get_motion",
        # Image-returning tools from frigate_tools.py — these should
        # NEVER be exposed via MCP. If they somehow get registered,
        # the gate will strip their image responses.
        "frigate_get_snapshot",
        "frigate_get_latest_frame",
        "frigate_review_event",
        # Vision capture tools — also should never be exposed via MCP
        "capture_screenshot",
        "capture_webcam",
        "capture_window",
        "capture_active_window",
        "detect_objects",
        "detect_faces",
        "detect_motion",
    })
    return tool_name in camera_tools


# ── MCP Tool Definitions (metadata-only) ───────────────────────────────────
#
# These tool definitions are designed to be added to the MCP server's
# TOOL_HANDLERS and TOOL_SCHEMAS dicts. They expose camera/vision
# metadata without ever returning image bytes.

FRIGATE_MCP_TOOLS = {
    "frigate_get_events": {
        "description": (
            "Query recent Frigate camera detection events. Returns text "
            "metadata only: camera, label (person/car/dog), zones, score, "
            "timestamps. No images or snapshots are exposed via MCP."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "camera": {"type": "string", "description": "Camera name or 'all'"},
                "labels": {"type": "string", "description": "Comma-separated labels or 'all'"},
                "limit": {"type": "integer", "description": "Max events (default 20)"},
            },
        },
    },
    "frigate_get_reviews": {
        "description": (
            "Query Frigate review segments (alert/detection severity). "
            "Returns text metadata only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "description": "'alert', 'detection', or 'all'"},
                "limit": {"type": "integer", "description": "Max reviews (default 20)"},
            },
        },
    },
    "frigate_list_cameras": {
        "description": (
            "List configured Frigate cameras with zones and detection status. "
            "Returns text metadata only."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    "frigate_get_active_detections": {
        "description": (
            "Get currently active (in-progress) Frigate detections. "
            "Returns text metadata: camera, label, zones, score. No images."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    "vision_get_detections": {
        "description": (
            "Get the latest local object detection result (from YOLOv8). "
            "Returns text metadata: labels, confidence, bounding boxes. "
            "No image data is exposed via MCP."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "'webcam' or 'screen'"},
            },
        },
    },
    "vision_get_motion": {
        "description": (
            "Get the latest motion detection result. Returns text metadata: "
            "has_motion, motion_ratio, bounding_boxes. No image data."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
}


def _tool_frigate_get_events(args: dict) -> dict:
    """MCP handler for frigate_get_events — metadata only."""
    import asyncio
    from ..integrations.frigate.frigate_config import load_frigate_config
    from ..integrations.frigate.frigate_client import FrigateClient

    config = load_frigate_config()
    if not config.is_configured():
        return {"error": "Frigate not configured"}

    client = FrigateClient(config)
    try:
        loop = asyncio.new_event_loop()
        try:
            events = loop.run_until_complete(client.get_events(
                camera=args.get("camera", "all"),
                labels=args.get("labels", "all"),
                limit=args.get("limit", 20),
            ))
        finally:
            loop.close()

        # Return only safe metadata fields
        safe_events = []
        for e in events:
            safe_events.append({
                "id": e.get("id", "")[:12],
                "camera": e.get("camera", ""),
                "label": e.get("label", ""),
                "sub_label": e.get("sub_label"),
                "zones": e.get("zones", []),
                "score": e.get("top_score", 0),
                "start_time": e.get("start_time", 0),
                "end_time": e.get("end_time"),
                "has_snapshot": e.get("has_snapshot", False),
                "has_clip": e.get("has_clip", False),
            })
        return {"events": safe_events, "count": len(safe_events)}
    except Exception as e:
        return {"error": str(e)}
    finally:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(client.close())
        loop.close()


def _tool_frigate_get_reviews(args: dict) -> dict:
    """MCP handler for frigate_get_reviews — metadata only."""
    import asyncio
    from ..integrations.frigate.frigate_config import load_frigate_config
    from ..integrations.frigate.frigate_client import FrigateClient

    config = load_frigate_config()
    if not config.is_configured():
        return {"error": "Frigate not configured"}

    client = FrigateClient(config)
    try:
        loop = asyncio.new_event_loop()
        try:
            reviews = loop.run_until_complete(client.get_reviews(
                severity=args.get("severity", "all"),
                limit=args.get("limit", 20),
            ))
        finally:
            loop.close()

        safe_reviews = []
        for r in reviews:
            safe_reviews.append({
                "id": r.get("id", "")[:12],
                "camera": r.get("camera", ""),
                "severity": r.get("severity", ""),
                "start_time": r.get("start_time", 0),
                "end_time": r.get("end_time"),
            })
        return {"reviews": safe_reviews, "count": len(safe_reviews)}
    except Exception as e:
        return {"error": str(e)}
    finally:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(client.close())
        loop.close()


def _tool_frigate_list_cameras(args: dict) -> dict:
    """MCP handler for frigate_list_cameras — metadata only."""
    import asyncio
    from ..integrations.frigate.frigate_config import load_frigate_config
    from ..integrations.frigate.frigate_client import FrigateClient

    config = load_frigate_config()
    if not config.is_configured():
        return {"error": "Frigate not configured"}

    client = FrigateClient(config)
    try:
        loop = asyncio.new_event_loop()
        try:
            cameras = loop.run_until_complete(client.get_cameras())
        finally:
            loop.close()
        return {"cameras": cameras}
    except Exception as e:
        return {"error": str(e)}
    finally:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(client.close())
        loop.close()


def _tool_frigate_get_active_detections(args: dict) -> dict:
    """MCP handler for frigate_get_active_detections — metadata only."""
    from ..integrations.frigate.frigate_event_mapper import FrigateStateTracker

    # The global state tracker is maintained by the MQTT subscriber
    # We create a fresh one here if the global isn't available
    try:
        from ..dashboard.app import _frigate_event_mapper
        if _frigate_event_mapper and _frigate_event_mapper.state_tracker:
            detections = _frigate_event_mapper.state_tracker.get_active_detections()
        else:
            detections = []
    except Exception:
        detections = []

    safe = []
    for d in detections:
        safe.append({
            "camera": d.get("camera", ""),
            "label": d.get("label", ""),
            "zones": d.get("zones", []),
            "score": d.get("score", 0),
            "start_time": d.get("start_time", 0),
        })
    return {"active_detections": safe, "count": len(safe)}


def _tool_vision_get_detections(args: dict) -> dict:
    """MCP handler for vision_get_detections — metadata only.

    Returns the last object detection result without any image data.
    The actual detection is run locally and only the text metadata
    (labels, confidence, bounding boxes) is exposed.
    """
    from ..vision.inference.detector import is_available
    if not is_available():
        return {"error": "Object detection not available on this host"}

    # This is a read-only query — it doesn't trigger a new capture.
    # In a full implementation, this would return the last cached
    # detection result. For now, we return availability info.
    return {
        "available": True,
        "backend": "yolov8",
        "note": "Use the Halbert dashboard or chat to run live detection. "
                "MCP exposes detection results, not live capture.",
    }


def _tool_vision_get_motion(args: dict) -> dict:
    """MCP handler for vision_get_motion — metadata only."""
    return {
        "available": True,
        "note": "Motion detection results are available via the Halbert "
                "dashboard or chat. MCP exposes motion metadata, not frames.",
    }


# Tool handler registry for MCP server integration
FRIGATE_MCP_TOOL_HANDLERS = {
    "frigate_get_events": _tool_frigate_get_events,
    "frigate_get_reviews": _tool_frigate_get_reviews,
    "frigate_list_cameras": _tool_frigate_list_cameras,
    "frigate_get_active_detections": _tool_frigate_get_active_detections,
    "vision_get_detections": _tool_vision_get_detections,
    "vision_get_motion": _tool_vision_get_motion,
}


def gate_response(tool_name: str, response: Any) -> Any:
    """Apply the camera data gate to an MCP tool response.

    Call this on every tool response before sending it to the client.
    If the tool is a camera query, strip_image_data() is applied.
    Otherwise, the response passes through unchanged.

    This is the main entry point for the MCP server to use.
    """
    if is_camera_query(tool_name):
        return strip_image_data(response)
    return response


def verify_bearer_token(provided: str, expected: str) -> bool:
    """Constant-time bearer token comparison.

    Uses hmac.compare_digest to prevent timing attacks. Both arguments
    must be strings; if either is empty, returns False.

    The MCP server should call this for every HTTP-transport request
    before dispatching to a tool handler.
    """
    import hmac
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())
