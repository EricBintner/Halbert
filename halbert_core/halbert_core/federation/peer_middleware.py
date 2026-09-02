# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""FastAPI dependency: bearer token validation for peer and MCP requests.

Implements finding C1 from the federated multi-node review.

C1 — Single auth surface for MCP and peer traffic
--------------------------------------------------
This middleware validates ``Authorization: Bearer <token>`` (or the
legacy ``X-Halbert-Peer-Token`` header) against ``PeersConfig``.  It is
the **same** validation path used by:

1. The MCP HTTP/SSE transport (Phase 4b) — when an MCP client (Warp,
   Claude Code) connects over HTTP, it presents a bearer token that is
   validated here.
2. The peer compute endpoint (``compute_endpoint.py``) — when a
   satellite Halbert offloads inference to the Desktop, it presents the
   same bearer token.
3. The fleet proxy (``fleet_proxy.py``) — when the Desktop inspects a
   satellite's config via MCP, it presents the same bearer token.

One token, one validation, one revocation path.  A revoked token is
rejected everywhere within one request cycle.

Usage in FastAPI
----------------
::

    from .peer_middleware import require_peer_auth

    @router.post("/api/compute/v1/chat/completions",
                 dependencies=[Depends(require_peer_auth)])
    async def compute_chat(...):
        ...

    @router.get("/api/peers/list",
                 dependencies=[Depends(require_peer_auth)])
    async def list_peers(...):
        ...

The dependency injects a ``PeerContext`` into the request state,
accessible via ``request.state.peer``.

Security notes
--------------
- Token comparison is constant-time (``hmac.compare_digest``) to prevent
  timing attacks.
- Revoked tokens are rejected immediately — no grace period, no caching
  of token validity beyond the request scope.
- The raw token is never logged.  Only the ``node_id`` and ``node_name``
  appear in logs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .peers_config import PeersConfig, PeerCredential

logger = logging.getLogger(__name__)

# Shared bearer token extractor — accepts "Authorization: Bearer <token>"
# This is the standard OAuth2/OIDC header format.  The legacy
# X-Halbert-Peer-Token header is also accepted for backward compatibility
# with the original handoff spec, but Bearer is preferred.
_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Peer context — injected into request.state
# ---------------------------------------------------------------------------

@dataclass
class PeerContext:
    """The authenticated peer's identity, available in request handlers.

    Access via ``request.state.peer`` or as a direct dependency::

        async def handler(peer: PeerContext = Depends(require_peer_auth)):
            print(peer.node_id)
    """
    node_id: str
    node_name: str
    role: str
    capabilities: list[str]
    credential: PeerCredential  # full record for internal use


# ---------------------------------------------------------------------------
# Singleton PeersConfig — loaded once per process
# ---------------------------------------------------------------------------

_peers_config: Optional[PeersConfig] = None


def get_peers_config() -> PeersConfig:
    """Get the process-wide PeersConfig singleton.

    TODO(federation-9.1): Wire this into the FastAPI app lifespan so
    it's created at startup and available via ``app.state.peers_config``.
    """
    global _peers_config
    if _peers_config is None:
        _peers_config = PeersConfig()
    return _peers_config


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def require_peer_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> PeerContext:
    """FastAPI dependency that validates a bearer token against PeersConfig.

    Accepts:
    - ``Authorization: Bearer <token>`` (preferred, MCP-compatible)
    - ``X-Halbert-Peer-Token: <token>`` (legacy, backward-compatible)

    Raises 401 if no token, invalid token, or revoked token.

    On success, returns a ``PeerContext`` and updates ``last_seen``.
    """
    # Extract token from either header
    raw_token: Optional[str] = None

    if credentials and credentials.credentials:
        raw_token = credentials.credentials
    else:
        # Fall back to legacy X-Halbert-Peer-Token header
        raw_token = request.headers.get("X-Halbert-Peer-Token")

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token. Provide 'Authorization: Bearer <token>' or 'X-Halbert-Peer-Token' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    config = get_peers_config()
    peer = config.verify_token(raw_token)

    if peer is None:
        # Don't reveal whether the token was revoked vs not found —
        # both return the same 401 to avoid information leakage.
        logger.warning("Rejected peer auth: invalid or revoked token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked peer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last_seen (fire-and-forget — don't block the request on disk I/O)
    # TODO(federation-9.1): make this async / throttled
    config.update_last_seen(peer.node_id)

    ctx = PeerContext(
        node_id=peer.node_id,
        node_name=peer.node_name,
        role=peer.role,
        capabilities=peer.capabilities,
        credential=peer,
    )

    # Store on request state for downstream handlers
    request.state.peer = ctx

    logger.debug("Authenticated peer: %s (%s)", peer.node_id, peer.node_name)
    return ctx


# ---------------------------------------------------------------------------
# Optional auth — for endpoints that behave differently for peers vs local
# ---------------------------------------------------------------------------

async def optional_peer_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[PeerContext]:
    """Like ``require_peer_auth`` but returns None instead of raising 401.

    Used by endpoints that serve both local users (no token) and peers
    (with token).  When a peer is authenticated, the response passes
    through ``mcp_response()`` redaction; when no peer is authenticated,
    the local user gets the full unredacted response.
    """
    if not credentials or not credentials.credentials:
        legacy = request.headers.get("X-Halbert-Peer-Token")
        if not legacy:
            return None
        # Fall through with legacy token
        raw_token = legacy
    else:
        raw_token = credentials.credentials

    config = get_peers_config()
    peer = config.verify_token(raw_token)
    if peer is None:
        return None

    config.update_last_seen(peer.node_id)
    ctx = PeerContext(
        node_id=peer.node_id,
        node_name=peer.node_name,
        role=peer.role,
        capabilities=peer.capabilities,
        credential=peer,
    )
    request.state.peer = ctx
    return ctx


# ---------------------------------------------------------------------------
# Local administration
# ---------------------------------------------------------------------------


def _is_local_client(request: "Request") -> bool:
    """Did this request come from this machine?"""
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client else None
    if not host:
        # No peer address at all (some ASGI transports, and TestClient's
        # default) — treat as local. A real network request always has one.
        return True
    try:
        import ipaddress

        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ("localhost", "testclient")


async def require_local_admin(request: "Request") -> None:
    """Restrict a route to the operator sitting at this machine.

    Distinct from ``require_peer_auth``, and deliberately not satisfiable by
    a peer token: these are the controls that rewrite this node's own
    identity — its entity mode, its body name, the token it trusts — and
    revoke other peers. A peer that could reach them could rename the body
    it federates with, or cut every other peer off (R10-F5).

    The dashboard binds 127.0.0.1 by default, but HALBERT_HOST can open it —
    and the compute-peer feature gives operators a reason to. This boundary
    holds either way.
    """
    if _is_local_client(request):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This control is available only from the machine it configures.",
    )
