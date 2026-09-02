# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Device & entity-mode endpoints — the Settings → Devices page (P7a).

The singular-entity product language is devices and bodies, not nodes and
peers: a user "adds this Mac as part of Halbert" and never sees the word
"peer".  This router is the device-shaped API surface for that page.

Operation map (P7a's five operations; no logic is duplicated — the
pairing handshake and peer-store mutations live in ``routes/peers.py``
and ``federation/peers_config.py``):

- **Pair** — the existing handshake: ``POST /api/peers/pair`` then
  ``POST /api/peers/verify`` (routes/peers.py).  The Devices page's
  "Add a device" modal (P7c) drives those endpoints directly.
- **List devices** — ``GET /api/devices`` here: the paired devices plus
  *this node's* entity identity (mode, body name, canonical URLs).
- **Toggle entity mode** — ``PUT /api/devices/entity-mode`` here:
  singular (this node proxies memory/threads to a canonical host) vs
  independent (this node keeps its own).  Writes ``being.yml`` through
  the locked load-modify-save composite.
- **Toggle WoL** — ``PUT /api/devices/{node_id}/wol`` here, a thin
  alias of ``PUT /api/peers/{node_id}/wol`` so the Devices page has one
  coherent surface.
- **Remove device** — ``DELETE /api/devices/{node_id}`` here, a thin
  alias of ``DELETE /api/peers/{node_id}`` (surgical revocation; the
  record is retained for audit).

Device capability discovery (P5c's write path): ``POST
/api/devices/{node_id}/discover`` asks the device's MCP server what it
can do (``PeerToolProxy.list_tools``, P5a) and updates the stored
capabilities.  mDNS-announced capabilities (``gpu_llm``) flow in through
the pairing handshake; the live probe is for the tool surface.

No ``mcp_response()`` redaction here: every response is local-dashboard
configuration data (peer records carry no raw tokens — hashes never
leave ``peers.json``).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...federation.peer_middleware import get_peers_config, require_local_admin
from ...federation.peers_config import KNOWN_PEER_CAPABILITIES

logger = logging.getLogger(__name__)

router = APIRouter()

# These routes rewrite this node's own identity — its entity mode, its body
# name, the peer token it trusts — and revoke other peers. They had no auth
# dependency at all, so any caller that could reach the dashboard could do
# all of it (R10-F5). Local-admin, not peer auth: a peer must not be able to
# rename the body it federates with or cut the others off.

#: Serializes being.yml load-modify-save cycles inside this process (the
#: cross-process advisory lock is held by ``update_being_config`` itself;
#: this one keeps two concurrent dashboard requests from interleaving).
_being_config_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# MCP tool name -> capability (discovery heuristics)
# ---------------------------------------------------------------------------

#: Substrings of an MCP tool name that imply a capability.  Deliberately
#: coarse: discovery feeds *routing hints* (P5b picks a peer by
#: capability), and a wrong hint costs one failed routing attempt, not a
#: security decision.  A successful ``tools/list`` always adds ``mcp`` —
#: the peer demonstrably runs an MCP server, which is that capability's
#: whole definition.
_TOOL_CAPABILITY_HINTS = (
    ("sourceprep", "sourceprep"),
    ("search_knowledge", "sourceprep"),
    ("terminal", "terminal"),
    ("shell", "terminal"),
    ("home", "home_tools"),
    ("scene", "home_tools"),
    ("light", "home_tools"),
    ("climate", "home_tools"),
    ("config", "sysadmin_tools"),
    ("editor", "sysadmin_tools"),
    ("apply", "sysadmin_tools"),
    ("service", "sysadmin_tools"),
    ("camera", "vision"),
    ("frigate", "vision"),
    ("vision", "vision"),
)


def _capabilities_from_tools(tool_names: List[str]) -> List[str]:
    """Map discovered MCP tool names onto the capability vocabulary."""
    found = {"mcp"}  # tools/list answered — the peer runs an MCP server
    for name in tool_names:
        low = name.lower()
        for hint, capability in _TOOL_CAPABILITY_HINTS:
            if hint in low:
                found.add(capability)
    return sorted(found & KNOWN_PEER_CAPABILITIES)


def _peer_token_for(endpoint: Optional[str]) -> Optional[str]:
    """The bearer token this node holds for a peer's compute/MCP API.

    Looked up in the saved ``peer://`` LLM endpoints (where the
    compute-peer link stores the workstation-issued token).  The single
    token system (finding C1) means one credential serves compute, MCP,
    and discovery alike.
    """
    if not endpoint:
        return None
    host = endpoint.replace("peer://", "http://", 1).split("//", 1)[-1].split("/", 1)[0]
    if not host:
        return None
    try:
        from ...model import llm_config as llm_store
        for ep in llm_store.load_global().get("saved_endpoints", []):
            if ep.get("provider") != "peer":
                continue
            url = ep.get("url") or ""
            if url.rstrip("/").endswith(host):
                return ep.get("api_key") or None
    except Exception as e:
        logger.warning("device token lookup failed: %s", e)
    return None


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class DeviceInfo(BaseModel):
    """A paired device as the Devices page shows it (no token material)."""
    node_id: str
    node_name: str
    role: str
    endpoint: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    compute_direction: str = "outbound"
    wol_enabled: bool = False
    wol_mac: Optional[str] = None
    wol_broadcast: Optional[str] = None
    paired_at: str = ""
    last_seen: Optional[str] = None
    revoked: bool = False


class EntityModeRequest(BaseModel):
    """Switch this node between singular and independent entity mode."""
    mode: str = Field(..., description='"singular" or "independent"')
    base_url: Optional[str] = Field(
        None, description="The canonical host (e.g. http://n150.lan:8001). "
        "canonical URLs are derived as {base}/api/memory and {base}/api/conversations.")
    memory_url: Optional[str] = Field(
        None, description="Explicit canonical memory URL (overrides base_url derivation)")
    thread_url: Optional[str] = Field(
        None, description="Explicit canonical thread URL (overrides base_url derivation)")


class BodyNameRequest(BaseModel):
    """Label which physical body this node is ("desk", "home")."""
    body_name: str = Field(..., min_length=1, max_length=64)


class CapabilitiesRequest(BaseModel):
    """Set a device's advertised capabilities (P5c vocabulary)."""
    capabilities: List[str] = Field(default_factory=list)


class DiscoverRequest(BaseModel):
    """Live capability discovery against the device's MCP server."""
    token: Optional[str] = Field(
        None, description="Bearer token for the device; omitted = look up "
        "the stored compute-peer token")
    timeout: float = Field(10.0, gt=0, le=60, description="Probe timeout (seconds)")


class WolToggleRequest(BaseModel):
    enabled: bool
    mac: Optional[str] = None
    broadcast: Optional[str] = None


# ---------------------------------------------------------------------------
# Entity identity (this node)
# ---------------------------------------------------------------------------

def _entity_state() -> Dict[str, Any]:
    """This node's entity identity from being.yml (P1 fields)."""
    from ...integrations.cognition_wiring import (
        _get_body_name,
        _get_canonical_memory_url,
        _get_canonical_thread_url,
    )
    memory_url = _get_canonical_memory_url()
    return {
        "entity_mode": "singular" if memory_url else "independent",
        "body_name": _get_body_name(),
        "canonical_memory_url": memory_url,
        "canonical_thread_url": _get_canonical_thread_url(),
    }


@router.get("/devices")
async def list_devices() -> Dict[str, Any]:
    """The Devices page read model: paired devices + this node's entity identity."""
    config = get_peers_config()
    devices = [
        DeviceInfo(
            node_id=p.node_id, node_name=p.node_name, role=p.role,
            endpoint=p.endpoint, capabilities=p.capabilities,
            compute_direction=p.compute_direction,
            wol_enabled=p.wol_enabled, wol_mac=p.wol_mac,
            wol_broadcast=p.wol_broadcast, paired_at=p.paired_at,
            last_seen=p.last_seen, revoked=p.revoked,
        ).model_dump()
        for p in config.list_peers(include_revoked=True)
    ]
    return {"status": "ok", **_entity_state(), "devices": devices}


@router.put("/devices/entity-mode", dependencies=[Depends(require_local_admin)])
async def set_entity_mode(req: EntityModeRequest) -> Dict[str, Any]:
    """Toggle this node's entity mode (singular vs independent).

    Singular: this body joins the canonical host's one autobiography —
    ``canonical_memory_url``/``canonical_thread_url`` are pointed at the
    canonical host (P2c/P3c wiring reads them).  Independent: both are
    cleared and this node keeps its own memory and threads.

    The common singular shape takes just ``base_url`` (the canonical
    host); explicit ``memory_url``/``thread_url`` override the derived
    ``{base}/api/memory`` / ``{base}/api/conversations`` paths.
    """
    if req.mode not in ("singular", "independent"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"mode must be 'singular' or 'independent', got {req.mode!r}",
        )
    if req.mode == "singular":
        if req.memory_url and req.thread_url:
            memory_url, thread_url = req.memory_url, req.thread_url
        elif req.base_url:
            base = req.base_url.rstrip("/")
            memory_url = req.memory_url or f"{base}/api/memory"
            thread_url = req.thread_url or f"{base}/api/conversations"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="singular mode needs base_url (or both memory_url and thread_url)",
            )
    else:
        memory_url = thread_url = ""

    from ...config.being_config import update_being_config

    def mutate(cfg) -> None:
        cfg.canonical_memory_url = memory_url
        cfg.canonical_thread_url = thread_url

    try:
        async with _being_config_lock:
            update_being_config(mutate)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.info("Entity mode set to %s (memory=%s threads=%s)",
                req.mode, memory_url or "local", thread_url or "local")
    return {"status": "ok", **_entity_state()}


@router.put("/devices/body-name", dependencies=[Depends(require_local_admin)])
async def set_body_name(req: BodyNameRequest) -> Dict[str, Any]:
    """Label which physical body this node is — the name the entity and
    the UI use for it ("desk", "home", "kitchen")."""
    from ...config.being_config import update_being_config

    def mutate(cfg) -> None:
        cfg.body_name = req.body_name.strip()

    try:
        async with _being_config_lock:
            update_being_config(mutate)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"status": "ok", **_entity_state()}


# ---------------------------------------------------------------------------
# Per-device operations
# ---------------------------------------------------------------------------

def _device_or_404(node_id: str):
    config = get_peers_config()
    peer = config.get_peer(node_id)
    if peer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Device {node_id} not found"
        )
    return config, peer


@router.put("/devices/{node_id}/capabilities", dependencies=[Depends(require_local_admin)])
async def set_device_capabilities(
    node_id: str, req: CapabilitiesRequest
) -> Dict[str, Any]:
    """Set a device's advertised capabilities (P5c).

    Unknown capability names are kept with a warning, not rejected — a
    device on a newer Halbert may advertise one this node hasn't learned
    yet (see KNOWN_PEER_CAPABILITIES).  The response reports them so the
    UI can flag them.
    """
    config, _ = _device_or_404(node_id)
    unknown = [c for c in req.capabilities if c not in KNOWN_PEER_CAPABILITIES]
    config.set_capabilities(node_id, list(req.capabilities))
    return {
        "status": "ok",
        "node_id": node_id,
        "capabilities": config.get_peer(node_id).capabilities,
        "unknown": unknown,
    }


@router.post("/devices/{node_id}/discover", dependencies=[Depends(require_local_admin)])
async def discover_device_capabilities(
    node_id: str, req: DiscoverRequest
) -> Dict[str, Any]:
    """Live capability discovery: ask the device's MCP server (P5a's
    ``PeerToolProxy.list_tools``) and update its stored capabilities.

    Discovery outcomes are results, not errors: an unreachable device or
    a missing token leaves the stored capabilities untouched and reports
    why, so the Devices page can render the state instead of an error.
    """
    config, peer = _device_or_404(node_id)
    if not peer.endpoint:
        return {"status": "no-endpoint", "node_id": node_id,
                "capabilities": peer.capabilities}
    token = req.token or _peer_token_for(peer.endpoint)
    if not token:
        return {"status": "no-token", "node_id": node_id,
                "capabilities": peer.capabilities}

    from ...agents.peer_tool_proxy import PeerToolProxy, PeerToolUnavailable

    proxy = PeerToolProxy(peer_url=peer.endpoint, bearer_token=token,
                          timeout=req.timeout)
    try:
        tools = await asyncio.get_running_loop().run_in_executor(
            None, proxy.list_tools)
    except PeerToolUnavailable as e:
        logger.info("Capability discovery for %s unreachable: %s", node_id, e)
        return {"status": "unreachable", "node_id": node_id,
                "capabilities": peer.capabilities}

    discovered = _capabilities_from_tools(tools)
    config.set_capabilities(node_id, discovered)
    logger.info("Capability discovery for %s: %d tools -> %s",
                node_id, len(tools), discovered)
    return {"status": "discovered", "node_id": node_id,
            "tools": len(tools), "capabilities": discovered}


@router.put("/devices/{node_id}/wol", dependencies=[Depends(require_local_admin)])
async def toggle_device_wol(node_id: str, req: WolToggleRequest) -> Dict[str, Any]:
    """Toggle Wake-on-LAN for a device — thin alias of
    ``PUT /api/peers/{node_id}/wol`` so the Devices page has one surface."""
    config, _ = _device_or_404(node_id)
    if not config.set_wol(node_id, req.enabled, req.mac, req.broadcast):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Device {node_id} not found"
        )
    return {"status": "ok", "node_id": node_id, "wol_enabled": req.enabled}

class PeerTokenRequest(BaseModel):
    """The bearer token this node presents to its canonical host (Q4).

    Written to ``being.yml: peer_token`` — the credential
    PeerMemoryBackend (P2a) and PeerConversationStore (P3a) authenticate
    with. Normally captured automatically after a pairing handshake with
    the canonical host; this endpoint is the manual path (rotation,
    out-of-band headless setup) behind the Devices page's Advanced
    disclosure. An empty token clears it.
    """
    token: str = Field("", max_length=512)


@router.put("/devices/peer-token", dependencies=[Depends(require_local_admin)])
async def set_peer_token(req: PeerTokenRequest) -> Dict[str, Any]:
    """Persist (or clear) the peer token for the canonical host.

    Validation: a token without a canonical host is a configuration
    mistake waiting to happen (singular mode needs both) — rejected with
    400 unless the node is independent (clearing is always allowed).
    """
    from ...config.being_config import update_being_config
    from ...integrations.cognition_wiring import _get_canonical_memory_url

    token = req.token.strip()
    if token and not _get_canonical_memory_url():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No canonical host configured — set singular entity mode "
                   "(with a base URL) before storing a peer token.",
        )

    def mutate(cfg) -> None:
        cfg.peer_token = token

    try:
        async with _being_config_lock:
            update_being_config(mutate)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.info("Peer token %s", "stored" if token else "cleared")
    return {"status": "ok", "peer_token_set": bool(token)}


@router.delete("/devices/{node_id}", dependencies=[Depends(require_local_admin)])
async def remove_device(node_id: str, forget: bool = False) -> Dict[str, Any]:
    """Remove a device — thin alias of ``DELETE /api/peers/{node_id}``:
    surgical token revocation, record retained for audit.

    ``forget=true`` (G12 review Q5: "Permanently Forget") erases the
    record entirely instead — a fresh pairing of the same machine starts
    clean, with no ghost record left to collide with.
    """
    config, _ = _device_or_404(node_id)
    if forget:
        if not config.delete_peer(node_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device {node_id} not found",
            )
        return {"status": "forgotten", "node_id": node_id}
    if not config.revoke_peer(node_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Device {node_id} not found"
        )
    return {"status": "removed", "node_id": node_id}
