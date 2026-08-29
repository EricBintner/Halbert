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

import logging
import secrets
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...federation.peers_config import PeersConfig, PeerCredential
from ...federation.peer_middleware import require_peer_auth, PeerContext, get_peers_config

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pending pairing requests (in-memory, cleared on restart)
# ---------------------------------------------------------------------------

# TODO(federation-9.1): Move to a more durable store if the Desktop
# restarts mid-pairing.  For MVP, in-memory is fine — the user just
# re-initiates pairing.
_pending_pairings: Dict[str, Dict[str, Any]] = {}  # pin -> {node_id, node_name, role, created_at}


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


class PairResponse(BaseModel):
    """Desktop → Satellite: pairing initiated, awaiting PIN confirmation."""
    pin: str = Field(..., description="4-digit PIN to confirm pairing")
    status: str = "pending"
    message: str = "Confirm this PIN on the Desktop UI to complete pairing"


class VerifyRequest(BaseModel):
    """Satellite → Desktop: confirm pairing with PIN."""
    pin: str = Field(..., description="The PIN from the pairing response")
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

    # Generate 4-digit PIN
    pin = f"{secrets.randbelow(10000):04d}"

    _pending_pairings[pin] = {
        "node_id": req.node_id,
        "node_name": req.node_name,
        "role": req.role,
        "capabilities": req.capabilities,
        "endpoint": req.endpoint,
    }

    logger.info("Pairing requested by %s (%s) — PIN generated", req.node_id, req.node_name)

    # TODO(federation-9.1): Emit a WebSocket event so the Desktop UI
    # shows a pairing confirmation dialog with the PIN.
    return PairResponse(pin=pin)


@router.post("/api/peers/verify", response_model=VerifyResponse)
async def verify_pairing(req: VerifyRequest) -> VerifyResponse:
    """Step 2: Satellite confirms pairing with the PIN.

    Validates the PIN, generates a bearer token, stores the peer
    credential (with token hash) in PeersConfig, and returns the raw
    token to the satellite.

    The satellite stores this token in its own peers.json and uses it
    for all future compute and MCP requests.
    """
    pending = _pending_pairings.pop(req.pin, None)
    if pending is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired PIN",
        )

    if pending["node_id"] != req.node_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PIN does not match this node_id",
        )

    # Generate token and store credential
    config = get_peers_config()
    raw_token = config.generate_token()

    try:
        config.add_peer(
            node_id=pending["node_id"],
            node_name=pending["node_name"],
            role=pending["role"],
            raw_token=raw_token,
            endpoint=pending.get("endpoint"),
            capabilities=pending.get("capabilities", []),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    # Get this node's ID for the response
    import os
    import socket
    desktop_node_id = os.environ.get("HALBERT_PERSONA_ID", "halbert") + "-" + socket.gethostname()

    logger.info("Pairing confirmed: %s (%s)", pending["node_id"], pending["node_name"])

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
        )
        for p in config.list_peers(include_revoked=True)
    ]


@router.delete("/api/peers/{node_id}")
async def revoke_peer(
    node_id: str,
    peer: PeerContext = Depends(require_peer_auth),
) -> Dict[str, Any]:
    """Revoke a peer's token (M14 — surgical revocation).

    The revoked peer's token is immediately invalid.  All future
    requests from this peer will get 401.

    TODO(federation-9.1): Should this require local admin auth rather
    than peer auth?  A peer revoking another peer is a privilege
    escalation risk.  For now, any authenticated peer can revoke —
    but this should be restricted to local admin or the peer revoking
    itself.
    """
    config = get_peers_config()
    if not config.revoke_peer(node_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Peer {node_id} not found",
        )
    return {"status": "revoked", "node_id": node_id}


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
