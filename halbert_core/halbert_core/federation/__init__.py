# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Federated Multi-Node Compute & Fleet Diagnostics.

This package implements the "Sovereign Self, Shared Commons" federation
architecture described in
``.handoff/HANDOFF-FEDERATED-MULTI-NODE-COMPUTE-AND-FLEET-2026-08-29.md``.

It is **not** a greenfield system.  It extends three existing foundations:

1. **MCP Phase 4b** (``halbert_core/mcp/``) — HTTP/SSE transport + bearer
   token auth.  The peer auth middleware reuses the same token mechanism
   so that MCP clients (Warp, Claude Code) and peer Halbert nodes share
   one credential surface.  See finding C1 in the handoff.

2. **Multi-Instance Phase 7** (``dashboard/routes/instance.py``,
   ``InstanceSwitch.tsx``) — env-var-isolated two-process model with a
   top-bar Instance Switcher.  The federation extends the switcher with
   mDNS-discovered peers rather than creating a parallel "Node Switcher".
   See finding C2.

3. **4-slot model architecture** (``model/llm_config.py``,
   ``model/tier_router.py``) — ``chat_model``, ``specialist_model``,
   ``vision_model``, ``secure_model``.  Peer offload is a new
   ``PeerProvider`` in ``model/providers/peer.py``, not a separate
   router.  ``secure_model`` is never peer-offloaded (finding M11).

Security boundary
-----------------
Every response that leaves a Halbert node toward a peer passes through
``mcp_response()`` (``halbert_core/mcp/response.py``), the same redaction
boundary used by the MCP server.  Peer prompts cannot invoke tools
outside the ``PEER_ALLOWED_TOOLS`` allowlist (finding C4).  Fleet
inspection is proxied through the satellite's MCP server, not a bespoke
``/api/fleet/inspect`` endpoint (finding C5).

Implementation order (Phase 9+)
-------------------------------
See §8 of the handoff for the full re-sequencing.  Files in this package
are scaffolded with ``TODO(federation-9.x)`` markers indicating which
implementation step they belong to.
"""

from __future__ import annotations

# Public API — exported for convenience but all heavy imports are lazy.
# Importing this module does NOT import zeroconf, psutil, or any provider.

__all__ = [
    # 9.1 — Peer auth (shared with MCP Phase 4b)
    # (the FastAPI dependencies require_peer_auth / optional_peer_auth and
    #  PeerContext live in peer_middleware.py — there is no middleware class)
    "PeersConfig",
    "PeerCredential",
    # 9.4 — Compute endpoint + redaction
    "PEER_ALLOWED_TOOLS",
    "is_tool_allowed_for_peer",
    # 9.6 — Hardware-profile-aware fallback
    "ComputeRouter",
    # 9.8 — Concurrency broker
    "ComputeBroker",
    # P4a — Internet connectivity detection
    "ConnectivityProbe",
]


# ---------------------------------------------------------------------------
# Lazy imports — these are resolved on first attribute access, not at module
# import time.  This keeps the subtractive contract intact (no hard deps
# beyond pyyaml + requests).
# ---------------------------------------------------------------------------

def __getattr__(name: str):  # pragma: no cover
    if name == "PeersConfig":
        from .peers_config import PeersConfig
        return PeersConfig
    if name == "PeerCredential":
        from .peers_config import PeerCredential
        return PeerCredential
    if name == "PEER_ALLOWED_TOOLS":
        from .tool_allowlist import PEER_ALLOWED_TOOLS
        return PEER_ALLOWED_TOOLS
    if name == "is_tool_allowed_for_peer":
        from .tool_allowlist import is_tool_allowed_for_peer
        return is_tool_allowed_for_peer
    if name == "ComputeRouter":
        from .compute_router import ComputeRouter
        return ComputeRouter
    if name == "ComputeBroker":
        from .compute_broker import ComputeBroker
        return ComputeBroker
    if name == "ConnectivityProbe":
        from .connectivity import ConnectivityProbe
        return ConnectivityProbe
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
