# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Conversation API — the P3b server half of the P3a wire contract.

Exposes the local ``SqliteConversationStore`` over HTTP so that a paired
peer node (the workstation) can read/write the shared thread history on
the HA server.  This enables cross-device conversation continuity: a
thread started on the workstation is visible on the HA server and vice
versa.

Wire contract (authoritative version in
``agents/peer_conversation_store.py`` module docstring):

- ``POST /api/conversations/invoke`` with JSON body
  ``{"method": <name>, "args": [...], "kwargs": {...}}`` and bearer auth.
  The server allowlists ``method`` against ``PEER_CONVERSATION_METHODS``,
  calls the same-named method on its local ``SqliteConversationStore``,
  and answers ``200 {"value": <return value>}`` — including
  ``null``/``false``/``[]``, which are ordinary answers here, not errors.
- ``GET /api/conversations/health`` →
  ``{"healthy": bool, "connected": bool}``.
- ``Conversation``-carrying methods — ``get``/``create``/``get_or_create``
  return, and ``save`` accepts, ``Conversation.to_dict()`` at the wire;
  the server rebuilds the dataclass with ``from_dict()`` before calling.
- A failed redaction answers
  ``500 {"error": {"type": "RedactionFailed", "message": ...}}`` and the
  proxy re-raises ``RedactionFailed`` so the privacy promise survives the
  network hop.
- 401 (bad bearer token) and any other non-200 raise
  ``PeerConversationUnavailable`` locally.

No ``mcp_response()`` redaction — this is internal communication between
two bodies of one entity.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...agents.peer_conversation_store import PEER_CONVERSATION_METHODS
from ...federation.peer_middleware import require_peer_auth

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Store accessor — thread-safe lazy singleton
# ---------------------------------------------------------------------------

_conversation_store = None
_store_lock = threading.Lock()


def get_conversation_store():
    """Get the process-wide SqliteConversationStore singleton.

    Thread-safe double-checked locking.  Lazy import to avoid pulling
    sqlite at module load time.
    """
    global _conversation_store
    if _conversation_store is None:
        with _store_lock:
            if _conversation_store is None:
                try:
                    from ...agents.conversation_sqlite import SqliteConversationStore
                    _conversation_store = SqliteConversationStore()
                except Exception as e:
                    logger.error("Could not create SqliteConversationStore: %s", e)
    return _conversation_store


def reset_conversation_store():
    """Reset the singleton (for testing)."""
    global _conversation_store
    with _store_lock:
        _conversation_store = None


def _require_store():
    """Get the store or raise 503."""
    store = get_conversation_store()
    if store is None:
        raise HTTPException(status_code=503, detail="ConversationStore unavailable")
    return store


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class InvokeRequest(BaseModel):
    """The P3a wire envelope for method dispatch."""
    method: str = Field(..., description="SqliteConversationStore method name")
    args: List[Any] = Field(default_factory=list, description="Positional arguments")
    kwargs: Dict[str, Any] = Field(default_factory=dict, description="Keyword arguments")


class InvokeResponse(BaseModel):
    """The P3a wire response — wraps the method's return value."""
    value: Any = None


class ErrorResponse(BaseModel):
    """Error response for failed operations (e.g. RedactionFailed)."""
    error: Dict[str, str] = Field(..., description="Error type and message")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_conversation_health() -> Dict[str, Any]:
    """Get the store's health status (healthy + connected)."""
    store = _require_store()
    return {
        "healthy": store.healthy,
        "connected": store.connected,
    }


@router.post(
    "/invoke",
    response_model=InvokeResponse,
    dependencies=[Depends(require_peer_auth)],
)
async def peer_conversation_invoke(req: InvokeRequest) -> InvokeResponse:
    """Dispatch a method call to the local SqliteConversationStore.

    This is the single dispatch endpoint that ``PeerConversationStore``
    (P3a) calls.  The method name is allowlisted against
    ``PEER_CONVERSATION_METHODS`` to prevent arbitrary method invocation.

    ``Conversation``-carrying methods: ``save`` receives a
    ``Conversation.to_dict()`` as its first positional arg; the server
    rebuilds it with ``Conversation.from_dict()`` before calling.

    A failed redaction (``RedactionFailed``) is the one deliberate raise
    in the store — it answers ``500`` with an error envelope so the proxy
    can re-raise it and the privacy promise survives the network hop.
    """
    store = _require_store()

    # Allowlist check — prevent arbitrary method invocation
    if req.method not in PEER_CONVERSATION_METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"method not allowed: {req.method!r}",
        )

    # Conversation-carrying arg: rebuild the dataclass server-side
    args = list(req.args)
    if req.method == "save" and args:
        from ...agents.conversation import Conversation
        try:
            args[0] = Conversation.from_dict(args[0])
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid Conversation payload: {e}",
            )

    # Dispatch
    try:
        result = getattr(store, req.method)(*args, **req.kwargs)
    except Exception as e:
        # Check if it's a RedactionFailed — the one deliberate raise
        # that must propagate as a 500 error envelope
        error_type = type(e).__name__
        if error_type == "RedactionFailed":
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "type": "RedactionFailed",
                        "message": str(e),
                    }
                },
            )
        # Any other unexpected exception — log and return 500
        logger.error("Invoke %s failed: %s", req.method, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error calling {req.method}: {e}",
        )

    # Conversation-carrying return: serialize to dict at the wire
    if hasattr(result, "to_dict") and callable(getattr(result, "to_dict")):
        result = result.to_dict()

    return InvokeResponse(value=result)
