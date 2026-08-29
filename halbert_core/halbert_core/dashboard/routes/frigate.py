# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Frigate panel API routes for the Halbert dashboard.

Provides:
- GET  /api/frigate/status        — Frigate connection status
- GET  /api/frigate/config        — Load Frigate config (credentials masked)
- POST /api/frigate/config        — Save Frigate config
- GET  /api/frigate/cameras       — List Frigate cameras
- GET  /api/frigate/events        — Query recent events
- GET  /api/frigate/reviews       — Query review segments
- GET  /api/frigate/snapshot/{id} — Get event snapshot (JPEG)
- GET  /api/frigate/latest/{cam}  — Get latest camera frame (JPEG)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger("halbert.dashboard.frigate")

router = APIRouter()


# --- Models ---

class FrigateConfigRequest(BaseModel):
    url: str = ""
    api_key: str = ""
    verify_ssl: bool = True
    mqtt_enabled: bool = False
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_password: str = ""
    enabled_cameras: list[str] = []
    alert_labels: list[str] = []
    alert_zones: list[str] = []
    min_alert_score: float = 0.75
    fetch_snapshots: bool = True


# --- Routes ---

@router.get("/frigate/status")
async def frigate_status():
    """Check if Frigate is reachable and return camera count."""
    from ...integrations.frigate.frigate_config import load_frigate_config
    from ...integrations.frigate.frigate_client import FrigateClient

    config = load_frigate_config()
    if not config.is_configured():
        return {"configured": False, "connected": False}

    client = FrigateClient(config)
    try:
        result = await client.get_status()
        return {
            "configured": True,
            "connected": result.get("connected", False),
            "cameras": result.get("cameras", []),
            "mqtt_enabled": config.mqtt_enabled,
            "error": result.get("error"),
        }
    finally:
        await client.close()


@router.get("/frigate/config")
async def get_frigate_config():
    """Load Frigate config (credentials masked)."""
    from ...integrations.frigate.frigate_config import load_frigate_config

    config = load_frigate_config()
    return config.to_dict()


@router.post("/frigate/config")
async def save_frigate_config_route(req: FrigateConfigRequest):
    """Save Frigate connection config."""
    from ...integrations.frigate.frigate_config import FrigateConfig, load_frigate_config, save_frigate_config

    # Preserve existing credentials if not provided in the request
    existing = load_frigate_config()
    api_key = req.api_key if req.api_key else existing.api_key
    mqtt_password = req.mqtt_password if req.mqtt_password else existing.mqtt_password

    config = FrigateConfig(
        url=req.url,
        api_key=api_key,
        verify_ssl=req.verify_ssl,
        mqtt_enabled=req.mqtt_enabled,
        mqtt_host=req.mqtt_host,
        mqtt_port=req.mqtt_port,
        mqtt_user=req.mqtt_user,
        mqtt_password=mqtt_password,
        enabled_cameras=req.enabled_cameras,
        alert_labels=req.alert_labels,
        alert_zones=req.alert_zones,
        min_alert_score=req.min_alert_score,
        fetch_snapshots=req.fetch_snapshots,
    )
    save_frigate_config(config)
    return {"status": "ok"}


@router.get("/frigate/cameras")
async def list_cameras():
    """List all configured Frigate cameras."""
    from ...integrations.frigate.frigate_config import load_frigate_config
    from ...integrations.frigate.frigate_client import FrigateClient

    config = load_frigate_config()
    if not config.is_configured():
        raise HTTPException(400, "Frigate not configured")

    client = FrigateClient(config)
    try:
        cameras = await client.get_cameras()
        return {"cameras": cameras}
    except Exception as e:
        raise HTTPException(502, f"Frigate error: {e}")
    finally:
        await client.close()


@router.get("/frigate/events")
async def get_events(
    camera: str = Query("all"),
    labels: str = Query("all"),
    zones: str = Query("all"),
    limit: int = Query(20, le=100),
    in_progress: bool = Query(False),
):
    """Query recent detection events."""
    from ...integrations.frigate.frigate_config import load_frigate_config
    from ...integrations.frigate.frigate_client import FrigateClient

    config = load_frigate_config()
    if not config.is_configured():
        raise HTTPException(400, "Frigate not configured")

    client = FrigateClient(config)
    try:
        events = await client.get_events(
            camera=camera, labels=labels, zones=zones,
            limit=limit, in_progress=in_progress,
        )
        return {"events": events}
    except Exception as e:
        raise HTTPException(502, f"Frigate error: {e}")
    finally:
        await client.close()


@router.get("/frigate/reviews")
async def get_reviews(
    camera: str = Query("all"),
    severity: str = Query("all"),
    limit: int = Query(20, le=100),
):
    """Query review segments."""
    from ...integrations.frigate.frigate_config import load_frigate_config
    from ...integrations.frigate.frigate_client import FrigateClient

    config = load_frigate_config()
    if not config.is_configured():
        raise HTTPException(400, "Frigate not configured")

    client = FrigateClient(config)
    try:
        reviews = await client.get_reviews(
            camera=camera, severity=severity, limit=limit,
        )
        return {"reviews": reviews}
    except Exception as e:
        raise HTTPException(502, f"Frigate error: {e}")
    finally:
        await client.close()


@router.get("/frigate/snapshot/{event_id}")
async def get_snapshot(event_id: str):
    """Get event snapshot as JPEG."""
    from ...integrations.frigate.frigate_config import load_frigate_config
    from ...integrations.frigate.frigate_client import FrigateClient

    config = load_frigate_config()
    if not config.is_configured():
        raise HTTPException(400, "Frigate not configured")

    client = FrigateClient(config)
    try:
        jpeg_bytes = await client.get_event_snapshot(event_id)
        return Response(content=jpeg_bytes, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(502, f"Frigate error: {e}")
    finally:
        await client.close()


@router.get("/frigate/latest/{camera}")
async def get_latest_frame(camera: str):
    """Get latest camera frame as JPEG."""
    from ...integrations.frigate.frigate_config import load_frigate_config
    from ...integrations.frigate.frigate_client import FrigateClient

    config = load_frigate_config()
    if not config.is_configured():
        raise HTTPException(400, "Frigate not configured")

    client = FrigateClient(config)
    try:
        jpeg_bytes = await client.get_latest_frame(camera)
        return Response(content=jpeg_bytes, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(502, f"Frigate error: {e}")
    finally:
        await client.close()
