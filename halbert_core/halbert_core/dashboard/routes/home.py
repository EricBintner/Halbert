# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Home panel API routes for the Halbert dashboard.

Provides:
- GET  /api/home/status        — HA connection status
- GET  /api/home/entities       — List entities (filter by domain)
- GET  /api/home/entity/{id}    — Get single entity state
- POST /api/home/service        — Call HA service
- GET  /api/home/areas          — List HA areas
- GET  /api/home/archetypes     — List home archetypes
- GET  /api/home/config         — Load HA connection config
- POST /api/home/config         — Save HA connection config
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("halbert.dashboard.home")

router = APIRouter()


# --- Models ---

class HAConfigRequest(BaseModel):
    url: str
    token: str
    verify_ssl: bool = True
    visible_domains: Optional[list[str]] = None


class ServiceCallRequest(BaseModel):
    domain: str
    service: str
    entity_id: Optional[str] = None
    data: Optional[dict] = None


# --- Lazy client accessor ---

def _get_client():
    """Get the singleton HAClient from the ha_tool module."""
    from ...integrations.home_assistant.ha_tool import _get_client
    return _get_client()


# --- Routes ---

@router.get("/home/status")
async def home_status():
    """Check HA connection status."""
    from ...integrations.home_assistant.ha_config import load_ha_config
    config = load_ha_config()
    if not config.is_configured():
        return {"connected": False, "configured": False}

    client = _get_client()
    status = await client.get_status()
    return {"connected": status["connected"], "configured": True, **status}


@router.get("/home/config")
async def get_config():
    """Load HA connection config (token masked)."""
    from ...integrations.home_assistant.ha_config import load_ha_config
    config = load_ha_config()
    return config.to_dict()


@router.post("/home/config")
async def save_config(req: HAConfigRequest):
    """Save HA connection config."""
    from ...integrations.home_assistant.ha_config import HAConfig, save_ha_config
    from ...integrations.home_assistant.ha_tool import close_client

    config = HAConfig(
        url=req.url,
        token=req.token,
        verify_ssl=req.verify_ssl,
        visible_domains=req.visible_domains or HAConfig().visible_domains,
    )
    save_ha_config(config)

    # Reset the client so it picks up the new config
    await close_client()

    return {"status": "ok", "config": config.to_dict()}


@router.get("/home/entities")
async def get_entities(
    domain: Optional[str] = Query(None, description="Filter by entity domain"),
):
    """List HA entities, optionally filtered by domain.

    If no domain is specified, entities are filtered to the configured
    visible_domains list.
    """
    from ...integrations.home_assistant.ha_config import load_ha_config

    client = _get_client()
    if not client.config.is_configured():
        raise HTTPException(status_code=400, detail="Home Assistant is not configured")
    try:
        if domain:
            entities = await client.get_entities_by_domain(domain)
        else:
            # No domain filter: return all, let frontend filter by visible_domains
            entities = await client.get_entities_by_domain(None)
            config = load_ha_config()
            if config.visible_domains:
                entities = [
                    e for e in entities
                    if e["entity_id"].split(".")[0] in config.visible_domains
                ]
        return {"entities": entities, "count": len(entities)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/home/entity/{entity_id}")
async def get_entity(entity_id: str):
    """Get the state of a single HA entity."""
    client = _get_client()
    if not client.config.is_configured():
        raise HTTPException(status_code=400, detail="Home Assistant is not configured")
    try:
        state = await client.get_entity_state(entity_id)
        return state
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/home/service")
async def call_service(req: ServiceCallRequest):
    """Call a HA service."""
    client = _get_client()
    if not client.config.is_configured():
        raise HTTPException(status_code=400, detail="Home Assistant is not configured")
    try:
        service_data = req.data or {}
        if req.entity_id:
            service_data["entity_id"] = req.entity_id
        result = await client.call_service(req.domain, req.service, service_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/home/areas")
async def get_areas():
    """List HA areas."""
    client = _get_client()
    if not client.config.is_configured():
        raise HTTPException(status_code=400, detail="Home Assistant is not configured")
    try:
        areas = await client.get_areas()
        return {"areas": areas}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/home/archetypes")
async def get_archetypes():
    """List home personality archetypes."""
    from ...persona.home_archetypes import list_home_archetypes
    archetypes = list_home_archetypes()
    return {"archetypes": archetypes, "count": len(archetypes)}


# --- Phase 3: HA Config SourcePrep ---

@router.get("/home/config-search/status")
async def get_config_search_status():
    """Check if SourcePrep is running and HA config project is indexed."""
    from ...integrations.home_assistant.ha_config_bridge import check_sourceprep_status
    return check_sourceprep_status()


@router.get("/home/config-search")
async def search_ha_config_api(q: str = Query(..., description="Search query"), k: int = Query(5, ge=1, le=10)):
    """Search HA config files via SourcePrep semantic search."""
    from ...integrations.home_assistant.ha_config_bridge import search_ha_config
    results = search_ha_config(q, k=k)
    return {"results": results, "count": len(results), "query": q}
