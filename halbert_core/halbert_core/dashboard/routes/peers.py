# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Peer pairing REST endpoints — pairing handshake, list, revoke.

Implements findings C1 and M14 from the federated multi-node review.

C1 — Single token system with MCP Phase 4b
-------------------------------------------
The pairing flow generates a token that is used for BOTH peer compute
auth and MCP HTTP/SSE auth.  One token, one PeersConfig store, one
revocation path.

M14 — Per-peer tokens, rotation, and revocation
-----------------------------------------------
Each satellite gets its own token.  Revocation is surgical
(``DELETE /api/peers/{node_id}``).  Token rotation = revoke + re-pair.

Pairing flow
------------
::

    Satellite                          Desktop (Compute Host)
    ┌──────────┐                       ┌──────────────────┐
    │ Discovers│  1. POST /api/peers/  │                  │
    │ via mDNS │     pair              │                  │
    │          │  ──────────────────►  │  Displays PIN    │
    │          │  ◄──────────────────  │  2. Returns PIN  │
    │          │                       │     + pending    │
    │          │  3. POST /api/peers/  │                  │
    │          │     verify            │                  │
    │          │  ──────────────────►  │  User confirms   │
    │          │  ◄──────────────────  │  4. Returns token│
    └──────────┘                       └──────────────────┘

Step 1: Satellite requests pairing → Desktop returns a 4-digit PIN
        (the satellite displays this to the user, or the Desktop UI
        shows it for the user to enter on the satellite).
Step 2: User confirms pairing on the Desktop UI (or enters PIN on
        satellite which sends it back).
Step 3: Satellite sends the PIN to /api/peers/verify → Desktop
        validates the PIN and returns the bearer token.
Step 4: Satellite stores the token in its own peers.json.  Both nodes
        now have each other's credential (Desktop has the token hash,
        satellite has the raw token).

Manual pairing (Tailscale / no mDNS)
-------------------------------------
The Instance Switcher's "Add Instance" form (already in InstanceSwitch.tsx)
is the manual pairing path.  The user enters the Desktop's URL directly.
This is the Tailscale path (finding H9 — mDNS doesn't cross Tailscale).
"""
from __future__ import annotations

import hmac
import logging
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...federation.peers_config import PeersConfig, PeerCredential
from ...federation.peer_middleware import (
    require_peer_auth, require_local_admin, optional_peer_auth,
    PeerContext, get_peers_config,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pending pairing requests (in-memory, cleared on restart)
# ---------------------------------------------------------------------------

# In-memory, cleared on restart: a pairing the operator did not finish is a
# pairing they can start again.
#
# Keyed by request id, NOT by PIN. The PIN is a secret the requester must
# prove it learned out of band; making it the lookup key turns every /verify
# into an oracle over a 10,000-value space.
_pending_pairings: Dict[str, "_PendingPairing"] = {}

# A PIN is read off one screen and typed into another. A minute is enough for
# that and short enough that a guessing run has no room.
PAIRING_TTL_S = 60.0
# 4 digits is 10,000 values; three tries against a 60s window is not a search.
PAIRING_MAX_ATTEMPTS = 3
# A refused request is a nuisance, not a memory leak.
PAIRING_MAX_PENDING = 16


@dataclass
class _PendingPairing:
    """A pairing waiting for the operator to approve it."""
    request_id: str
    pin: str
    fields: Dict[str, Any]
    created_at: float
    approved: bool = False
    attempts: int = 0

    def is_expired(self, now: float) -> bool:
        return (now - self.created_at) > PAIRING_TTL_S


def _sweep_pending(now: Optional[float] = None) -> None:
    """Drop expired requests. Called on every entry to the pairing routes."""
    now = now if now is not None else time.time()
    for rid in [r for r, p in _pending_pairings.items() if p.is_expired(now)]:
        _pending_pairings.pop(rid, None)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class PairRequest(BaseModel):
    """Satellite → Desktop: request to pair."""
    node_id: str = Field(..., description="Satellite's unique node ID")
    node_name: str = Field(..., description="Satellite's display name")
    role: str = Field("satellite", description="Peer role: 'satellite' or 'compute_provider'")
    capabilities: List[str] = Field(default_factory=list, description="Capabilities the satellite offers")
    endpoint: Optional[str] = Field(None, description="Satellite's endpoint URL (for Desktop→Satellite MCP proxy)")
    compute_direction: str = Field("outbound", description="Compute flow: 'outbound' (local→peer) or 'inbound' (peer→local)")
    wol_enabled: bool = Field(False, description="Enable Wake-on-LAN for this peer (LAN-only)")
    wol_mac: Optional[str] = Field(None, description="MAC address for WoL (required if wol_enabled)")
    wol_broadcast: Optional[str] = Field(None, description="Broadcast address for WoL (defaults to 255.255.255.255)")


class PairResponse(BaseModel):
    """Desktop → Satellite: pairing initiated, awaiting PIN confirmation.

    Deliberately carries no PIN. It used to: the requester was handed the
    secret it was then asked to prove, so anyone who could reach the port
    could pair itself and walk away with a bearer token — the PIN was
    theatre (SE-16 / R10-F1). The PIN is shown on THIS machine and travels
    to the other one the way a pairing code always has: through the person
    doing the pairing.
    """
    request_id: str = Field(..., description="Identifies this pairing attempt")
    status: str = "pending"
    expires_in: float = Field(PAIRING_TTL_S, description="Seconds until this attempt lapses")
    message: str = (
        "Approve this pairing on the other machine, then enter the PIN it shows."
    )


class PendingPairingInfo(BaseModel):
    """Local-admin view of a pairing waiting for approval — PIN included,
    because this is the screen the operator reads it off."""
    request_id: str
    node_id: str
    node_name: str
    role: str
    pin: str
    approved: bool
    expires_in: float


class VerifyRequest(BaseModel):
    """Satellite → Desktop: confirm pairing with PIN."""
    request_id: str = Field(..., description="The request_id from the pairing response")
    pin: str = Field(..., description="The PIN displayed on the other machine")
    node_id: str = Field(..., description="The node_id from the pairing request")


class VerifyResponse(BaseModel):
    """Desktop → Satellite: pairing confirmed, here's your token."""
    token: str = Field(..., description="Bearer token for future auth")
    status: str = "paired"
    desktop_node_id: str = Field(..., description="The Desktop's node ID")


class PeerInfo(BaseModel):
    """Public info about a paired peer (no token hash)."""
    node_id: str
    node_name: str
    role: str
    paired_at: str
    last_seen: Optional[str] = None
    revoked: bool = False
    endpoint: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    compute_direction: str = "outbound"
    wol_enabled: bool = False
    wol_mac: Optional[str] = None
    wol_broadcast: Optional[str] = None


class ComputePeerLinkRequest(BaseModel):
    """Persist a paired compute peer as this node's LLM endpoint.

    Sent by the Compute Peer card on a home variant after the
    pairing handshake (mDNS discovery or the manual Tailscale path). The
    workstation's address goes in ``endpoint``; ``token`` is the bearer
    credential the workstation issued at ``/api/peers/verify``.
    """
    endpoint: str = Field(..., description="Workstation address: host:port, peer://host:port, or http(s)://host:port")
    token: str = Field("", description="Bearer token from the workstation's /api/peers/verify")
    name: str = Field("", description="Display name for the saved endpoint")
    model: str = Field("", description="Model tag the slots request; empty = the workstation governs (handoff S3 5.2)")


class ComputePeerLinkResponse(BaseModel):
    """The persisted compute-peer link."""
    status: str = "linked"
    endpoint_id: str
    url: str
    model: str
    slots: List[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/peers/pair", response_model=PairResponse)
async def request_pairing(req: PairRequest) -> PairResponse:
    """Step 1: Satellite requests pairing with this Desktop.

    Generates a 4-digit PIN.  The Desktop UI displays the PIN for the
    user to confirm.  The satellite holds the PIN and calls
    ``/api/peers/verify`` to complete pairing.

    No token is issued yet — the PIN is the temporary credential.
    """
    # Check if already paired
    config = get_peers_config()
    existing = config.get_peer(req.node_id)
    if existing and not existing.revoked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Peer {req.node_id} is already paired. Revoke first to re-pair.",
        )

    _sweep_pending()
    if len(_pending_pairings) >= PAIRING_MAX_PENDING:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many pairing attempts are already waiting. Try again shortly.",
        )

    pending = _PendingPairing(
        request_id=uuid.uuid4().hex,
        pin=f"{secrets.randbelow(10000):04d}",
        created_at=time.time(),
        fields={
            "node_id": req.node_id,
            "node_name": req.node_name,
            "role": req.role,
            "capabilities": req.capabilities,
            "endpoint": req.endpoint,
            "compute_direction": req.compute_direction,
            "wol_enabled": req.wol_enabled,
            "wol_mac": req.wol_mac,
            "wol_broadcast": req.wol_broadcast,
        },
    )
    _pending_pairings[pending.request_id] = pending

    logger.info(
        "Pairing requested by %s (%s) — awaiting approval on this machine "
        "(request %s)", req.node_id, req.node_name, pending.request_id,
    )
    return PairResponse(request_id=pending.request_id)


@router.get(
    "/api/peers/pending",
    response_model=List[PendingPairingInfo],
    dependencies=[Depends(require_local_admin)],
)
async def list_pending_pairings() -> List[PendingPairingInfo]:
    """Pairings waiting on this machine, with their PINs.

    This is the screen the operator reads the PIN off. Local-admin only: the
    PIN is the whole secret, so serving it to anyone who asks would put the
    hole straight back.
    """
    _sweep_pending()
    now = time.time()
    return [
        PendingPairingInfo(
            request_id=p.request_id,
            node_id=p.fields["node_id"],
            node_name=p.fields["node_name"],
            role=p.fields["role"],
            pin=p.pin,
            approved=p.approved,
            expires_in=max(0.0, PAIRING_TTL_S - (now - p.created_at)),
        )
        for p in _pending_pairings.values()
    ]


@router.post(
    "/api/peers/pending/{request_id}/approve",
    dependencies=[Depends(require_local_admin)],
)
async def approve_pairing(request_id: str) -> Dict[str, Any]:
    """The confirmation step: a person at this machine says yes.

    Nothing issues a token without this. It is the whole difference between
    a handshake and self-service — /verify used to mint a bearer on a PIN
    match alone, and the PIN was in the pairing response.
    """
    _sweep_pending()
    pending = _pending_pairings.get(request_id)
    if pending is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No such pairing request, or it has expired")
    pending.approved = True
    logger.info("Pairing %s approved for %s", request_id, pending.fields["node_id"])
    return {"status": "approved", "request_id": request_id}


@router.delete(
    "/api/peers/pending/{request_id}",
    dependencies=[Depends(require_local_admin)],
)
async def reject_pairing(request_id: str) -> Dict[str, Any]:
    """Refuse a pairing outright rather than letting it lapse."""
    _sweep_pending()
    if _pending_pairings.pop(request_id, None) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No such pairing request, or it has expired")
    return {"status": "rejected", "request_id": request_id}


@router.post("/api/peers/verify", response_model=VerifyResponse)
async def verify_pairing(req: VerifyRequest) -> VerifyResponse:
    """Step 2: Satellite confirms pairing with the PIN.

    Validates the PIN, generates a bearer token, stores the peer
    credential (with token hash) in PeersConfig, and returns the raw
    token to the satellite.

    The satellite stores this token in its own peers.json and uses it
    for all future compute and MCP requests.
    """
    _sweep_pending()
    pending = _pending_pairings.get(req.request_id)
    if pending is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired pairing request",
        )

    if pending.fields["node_id"] != req.node_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This pairing request belongs to a different node",
        )

    if not pending.approved:
        # The load-bearing line. A PIN match alone used to be enough, and the
        # PIN was handed to the requester — so this endpoint issued bearer
        # tokens to anyone who asked twice.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This pairing has not been approved on the other machine yet",
        )

    pending.attempts += 1
    if not hmac.compare_digest(str(req.pin), pending.pin):
        if pending.attempts >= PAIRING_MAX_ATTEMPTS:
            _pending_pairings.pop(req.request_id, None)
            logger.warning(
                "Pairing %s abandoned after %d wrong PINs",
                req.request_id, pending.attempts,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many incorrect PINs; start pairing again",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect PIN",
        )

    # Only now is the request consumed.
    _pending_pairings.pop(req.request_id, None)
    fields = pending.fields

    # Generate token and store credential
    config = get_peers_config()
    raw_token = config.generate_token()

    try:
        config.add_peer(
            node_id=fields["node_id"],
            node_name=fields["node_name"],
            role=fields["role"],
            raw_token=raw_token,
            endpoint=fields.get("endpoint"),
            capabilities=fields.get("capabilities", []),
            compute_direction=fields.get("compute_direction", "outbound"),
            wol_enabled=fields.get("wol_enabled", False),
            wol_mac=fields.get("wol_mac"),
            wol_broadcast=fields.get("wol_broadcast"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    # Get this node's ID for the response
    import os
    import socket
    desktop_node_id = os.environ.get("HALBERT_PERSONA_ID", "halbert") + "-" + socket.gethostname()

    logger.info("Pairing confirmed: %s (%s)", fields["node_id"], fields["node_name"])

    return VerifyResponse(token=raw_token, desktop_node_id=desktop_node_id)


@router.get("/api/peers/list", response_model=List[PeerInfo])
async def list_peers(
    peer: PeerContext = Depends(require_peer_auth),
) -> List[PeerInfo]:
    """List all paired peers (requires auth — only paired peers can see the list).

    TODO(federation-9.1): Consider whether this should be a local-only
    endpoint (no peer auth) or peer-authenticated.  For now, requires
    peer auth so that only authenticated peers can enumerate the fleet.
    """
    config = get_peers_config()
    return [
        PeerInfo(
            node_id=p.node_id,
            node_name=p.node_name,
            role=p.role,
            paired_at=p.paired_at,
            last_seen=p.last_seen,
            revoked=p.revoked,
            endpoint=p.endpoint,
            capabilities=p.capabilities,
            compute_direction=p.compute_direction,
            wol_enabled=p.wol_enabled,
            wol_mac=p.wol_mac,
            wol_broadcast=p.wol_broadcast,
        )
        for p in config.list_peers(include_revoked=True)
    ]


@router.delete("/api/peers/{node_id}")
async def revoke_peer(
    request: Request,
    node_id: str,
    peer: Optional[PeerContext] = Depends(optional_peer_auth),
) -> Dict[str, Any]:
    """Revoke a peer's token (M14 — surgical revocation).

    The revoked peer's token is immediately invalid. All future requests
    from this peer will get 401.

    Two callers are allowed, and only two: the operator at this machine, and
    a peer revoking itself (leaving the fleet). Any authenticated peer could
    revoke any other — the file's own TODO called it a privilege-escalation
    risk, and it was: one compromised satellite could cut every other node
    off from the host (R10-F5).
    """
    from ...federation.peer_middleware import _is_local_client

    if not _is_local_client(request) and (peer is None or peer.node_id != node_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A peer may revoke only itself; revoking another peer is "
                   "done from the machine they are paired with.",
        )

    config = get_peers_config()
    if not config.revoke_peer(node_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Peer {node_id} not found",
        )
    return {"status": "revoked", "node_id": node_id}


class WolUpdateRequest(BaseModel):
    """Update WoL settings on a peer."""
    enabled: bool = Field(..., description="Enable or disable WoL for this peer")
    mac: Optional[str] = Field(None, description="MAC address (required when enabling if not already set)")
    broadcast: Optional[str] = Field(None, description="Broadcast address (optional, defaults to 255.255.255.255)")


@router.put("/api/peers/{node_id}/wol")
async def update_wol(
    node_id: str,
    req: WolUpdateRequest,
    peer: PeerContext = Depends(require_peer_auth),
) -> Dict[str, Any]:
    """Toggle Wake-on-LAN for a paired peer (P6c).

    WoL is LAN-only and off by default.  When enabled, the ComputeRouter
    (P6b) will attempt to wake this peer before falling through to
    template degraded mode.
    """
    config = get_peers_config()
    if not config.set_wol(node_id, req.enabled, req.mac, req.broadcast):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Peer {node_id} not found",
        )
    return {"status": "updated", "node_id": node_id, "wol_enabled": req.enabled}


# ---------------------------------------------------------------------------
# Compute-peer wiring (home automation simplification, S3 / W16)
# ---------------------------------------------------------------------------

def _peer_url(address: str) -> str:
    """Normalise a user-supplied workstation address to ``peer://host:port``.

    Accepts the three shapes a user pastes: a bare ``host:port`` (the
    Compute Peer card's field), a saved ``peer://`` URL, or an ``http(s)://``
    URL copied from the workstation's own address bar. Raises ValueError
    on anything without a host.
    """
    import urllib.parse

    u = (address or "").strip().rstrip("/")
    if not u:
        raise ValueError("empty peer address")
    if u.startswith("peer://"):
        pass
    elif u.startswith(("http://", "https://")):
        u = "peer://" + u.split("://", 1)[1]
    else:
        u = "peer://" + u
    parsed = urllib.parse.urlparse(u)
    if not parsed.netloc:
        raise ValueError(f"no host in peer address {address!r}")
    return u


@router.post("/api/peers/compute-peer", response_model=ComputePeerLinkResponse)
async def link_compute_peer(req: ComputePeerLinkRequest) -> ComputePeerLinkResponse:
    """Persist a paired workstation as this node's compute endpoint.

    Home automation simplification S3 (handoff
    HOME-AUTOMATION-SIMPLIFICATION-2026-08-30, 5.2/W16): an HA node has
    no model picker. Pairing with the workstation saves one ``peer://``
    endpoint and points BOTH ``chat_model`` and ``specialist_model`` at
    it — the same endpoint, the same model list — and the workstation's
    own model configuration governs which model serves the requests.
    ``secure_model`` is never touched: home never configure
    it (S1), and a peer URL is not local, so even a hand-edited file is
    disabled by llm_config's local-only enforcement.

    Only home variants may set the link: a sysadmin instance
    keeps the full model picker, where each slot is chosen per endpoint.
    """
    from ...integrations.cognition_wiring import is_home_variant

    if not is_home_variant():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compute-peer linking is a home feature; "
                   "the sysadmin variant assigns models per slot in Settings.",
        )

    try:
        url = _peer_url(req.endpoint)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    from ...model import llm_config as llm_store
    from ...model.providers.peer import PEER_GOVERNED_MODEL

    endpoint_id = llm_store.ensure_endpoint(
        url, provider="peer", name=req.name or "Compute Peer", api_key=req.token,
    )
    model = req.model.strip() or PEER_GOVERNED_MODEL
    for slot in ("chat_model", "specialist_model"):
        llm_store.set_slot(slot, model, endpoint_id)

    logger.info("Compute peer linked: %s (slots chat_model + specialist_model)", url)
    return ComputePeerLinkResponse(
        endpoint_id=endpoint_id, url=url, model=model,
        slots=["chat_model", "specialist_model"],
    )


@router.get("/api/peers/discovered")
async def list_discovered_peers() -> List[Dict[str, Any]]:
    """List peers discovered via mDNS (unauthenticated — no tokens involved).

    Returns the current mDNS discovery cache.  These are unauthenticated
    discoveries — the user must pair via /api/peers/pair before any
    compute or fleet interaction.

    TODO(federation-9.7): Wire to PeerListener.get_discovered().
    If zeroconf is not installed, returns an empty list with a 200
    (graceful degradation per finding H10).
    """
    # TODO(federation-9.7): Get the PeerListener singleton and return
    # its discovered peers.  For now, return empty.
    return []
