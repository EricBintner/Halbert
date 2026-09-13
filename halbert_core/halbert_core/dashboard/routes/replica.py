# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Replica routes — status for the status card, promote for recovery.

Two doors, deliberately different:

- ``GET /api/replica/status`` answers any principal this node can
  identify — the dashboard's tile, the trust_anchor phone checking
  whether its canonical is alive, another body.
- ``POST /api/replica/promote`` is trust_anchor-gated, not local-admin:
  the recovery story IS the phone — the operator promotes from the
  device in their pocket when they cannot sit at the machine. A body or
  compute peer still cannot promote; only the owner credential or a
  paired trust_anchor may.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from ...federation.peer_middleware import (
    require_known_principal,
    require_trust_anchor,
)

logger = logging.getLogger('halbert.dashboard.routes.replica')

router = APIRouter()


@router.get("/api/replica/status", dependencies=[Depends(require_known_principal)])
async def replica_status() -> Dict[str, Any]:
    """Replica metadata and promotion eligibility for the status card."""
    from ...replica.store import ReplicaStore
    store = ReplicaStore()
    meta = store.meta()
    return {
        "has_replica": meta is not None,
        "replica": meta.to_dict() if meta else None,
        "is_valid": store.is_valid(),
        "can_promote": store.is_valid(),
    }


@router.post("/api/replica/promote")
async def promote(
    _anchor: Any = Depends(require_trust_anchor),
) -> Dict[str, Any]:
    """Promote this satellite to the canonical host.

    The replica is installed into the live positions, divergent local
    files are quarantined beside themselves, being.yml drops its
    canonical pointers — which is also the fence that makes this node
    refuse any later stale-canonical push (409 on sync-replica).
    """
    from ...replica.promotion import promote_to_canonical
    result = promote_to_canonical()
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "promotion failed",
        )
    return {
        "status": "promoted",
        "old_canonical_url": result.old_canonical_url,
        "replica_timestamp": result.replica_timestamp,
        "memory_count": result.memory_count,
        "thread_count": result.thread_count,
        "quarantined": result.quarantined,
    }
