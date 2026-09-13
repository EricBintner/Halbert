# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Entity status — the one endpoint a remote device asks "how is the mind?"

The companion app's status card, a satellite's canonical-health view, and
the dashboard's own replica tile all read this. One aggregation point so
every caller sees the same shape: who the entity is, which body this is,
who is paired, and how much of it there is.

The router is self-authenticating ("entity" is in SELF_AUTHENTICATING) and
every route carries ``require_known_principal``: the local operator, the
owner credential, or any live peer token — a body peer needs canonical
status, and the trust_anchor phone is exactly this endpoint's reader.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from ...federation.peer_middleware import PeerContext, require_known_principal
from ...identity import (
    resolve_entity_name,
    resolve_entity_role,
    resolve_persona_id,
)

logger = logging.getLogger('halbert.dashboard.routes.entity')

router = APIRouter()

_ANCHOR = [Depends(require_known_principal)]


def _local_node_id() -> str:
    """This node's id, the same derivation peer discovery announces."""
    persona = os.environ.get("HALBERT_PERSONA_ID", "halbert")
    try:
        host = socket.gethostname()
    except Exception:
        host = "unknown"
    return f"{persona}-{host}"


def _memory_count(persona_id: str) -> Optional[int]:
    """Count memories.json entries without loading the embedder.

    The file is the store's own format ({version, memories: [...]}); a
    count for a status card does not justify a MemoryEmbedder load.
    """
    try:
        from haloysius.paths import state_dir
        path = state_dir("personas", persona_id) / "memories.json"
        if not path.exists():
            return 0
        data = json.loads(path.read_text())
        return len(data.get("memories") or [])
    except Exception as e:
        logger.debug(f"entity status: memory count unavailable: {e}")
        return None


def _thread_count() -> Optional[int]:
    """COUNT(*) on conversations.db, opened read-only.

    The conversation store's singleton is not asked — a status card that
    touched it could not serve during its lock anyway, and a read-only
    connection beside it costs nothing.
    """
    try:
        from ...utils.paths import data_dir
        db = Path(data_dir()) / "conversations.db"
        if not db.exists():
            return 0
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            return conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"entity status: thread count unavailable: {e}")
        return None


def _pending_approvals_count() -> Optional[int]:
    try:
        from ...approval.engine import ApprovalEngine
        return len(ApprovalEngine().get_pending_requests())
    except Exception as e:
        logger.debug(f"entity status: approval count unavailable: {e}")
        return None


def _peer_summaries() -> List[Dict[str, Any]]:
    """The non-revoked peers, summarised — no token material, no WoL
    addressing; a status reader learns who is paired and when they were
    last seen, nothing it could authenticate with."""
    try:
        from ...federation.peer_middleware import get_peers_config
        return [
            {
                "node_id": p.node_id,
                "node_name": p.node_name,
                "role": p.role,
                "last_seen": p.last_seen,
                "paired_at": p.paired_at,
            }
            for p in get_peers_config().list_peers()
        ]
    except Exception as e:
        logger.debug(f"entity status: peer list unavailable: {e}")
        return []


def _canonical_url() -> Optional[str]:
    """Where this body's canonical host lives, if it is a body."""
    try:
        from ...integrations.cognition_wiring import _get_canonical_memory_url
        return _get_canonical_memory_url() or None
    except Exception:
        return None


def _replica_status() -> Optional[Dict[str, Any]]:
    """The replica summary for the status card, or None when there is no
    replica — a canonical host or a body that never received one."""
    try:
        from ...replica.store import ReplicaStore
        from ...replica.liveness import current_probe
        store = ReplicaStore()
        meta = store.meta()
        if meta is None:
            return None
        probe = current_probe()
        return {
            **meta.to_dict(),
            "is_valid": store.is_valid(),
            "can_promote": store.is_valid(),
            "canonical_reachable": (
                probe.canonical_reachable if probe is not None else None),
        }
    except Exception as e:
        logger.debug(f"entity status: replica status unavailable: {e}")
        return None


@router.get("/api/entity/status", dependencies=_ANCHOR)
async def entity_status() -> Dict[str, Any]:
    """The aggregated status card.

    ``last_backup`` is None until the vault (Phase 2) exists — the shape
    is reserved now so the companion app's card does not change when it
    lands.
    """
    persona_id = resolve_persona_id()
    return {
        "entity_name": resolve_entity_name(),
        "persona_id": persona_id,
        "node_id": _local_node_id(),
        "role": resolve_entity_role(),
        "canonical_url": _canonical_url(),
        "peers": _peer_summaries(),
        "counts": {
            "memories": _memory_count(persona_id),
            "threads": _thread_count(),
            "pending_approvals": _pending_approvals_count(),
        },
        "replica": _replica_status(),
        "last_backup": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
