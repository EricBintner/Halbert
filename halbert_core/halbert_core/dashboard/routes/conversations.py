# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Conversation API endpoints for peer thread continuity (P3b).

Exposes the local ``SqliteConversationStore`` over HTTP so that a paired
peer node (the workstation) can read/write the shared thread history on
the HA server.  This enables cross-device conversation continuity: a
thread started on the workstation is visible on the HA server and vice
versa.

All routes require peer bearer auth.  No ``mcp_response()`` redaction —
this is internal entity communication.

The endpoints cover the core methods used by ``ThreadManager``:
- Thread CRUD: ``current_open_thread``, ``get_thread``, ``create_thread``,
  ``update_thread``, ``list_threads``
- Messages: ``append_message``, ``update_message``, ``list_messages``,
  ``recent_messages``
- Open loops: ``add_open_loop``, ``list_open_loops``
- Search: ``search``, ``search_receipts``
- Recovery: ``mark_in_progress_interrupted``, ``redact_message``
- Thread merging: ``merge_thread``
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...federation.peer_middleware import require_peer_auth, PeerContext

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Store accessor — lazy singleton
# ---------------------------------------------------------------------------

_conversation_store = None


def get_conversation_store():
    """Get the process-wide SqliteConversationStore singleton.

    Lazy import to avoid pulling sqlite at module load time.
    """
    global _conversation_store
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

class CreateThreadRequest(BaseModel):
    thread_id: str
    title: str = ""
    status: str = "open"
    persona_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UpdateThreadRequest(BaseModel):
    fields: Dict[str, Any] = Field(default_factory=dict)


class AppendMessageRequest(BaseModel):
    thread_id: str
    role: str
    content: str
    turn_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UpdateMessageRequest(BaseModel):
    fields: Dict[str, Any] = Field(default_factory=dict)


class AddOpenLoopRequest(BaseModel):
    thread_id: str
    description: str
    priority: str = "normal"


class MergeThreadRequest(BaseModel):
    new_thread_id: str
    prev_thread_id: str


# ---------------------------------------------------------------------------
# Thread endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/current-open-thread",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_current_open_thread() -> Dict[str, Any]:
    """Get the current open thread, or null."""
    store = _require_store()
    thread = store.current_open_thread()
    return {"status": "ok", "thread": thread}


@router.get(
    "/threads/{thread_id}",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_get_thread(thread_id: str) -> Dict[str, Any]:
    """Get a thread by ID."""
    store = _require_store()
    thread = store.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return {"status": "ok", "thread": thread}


@router.post(
    "/threads",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_create_thread(req: CreateThreadRequest) -> Dict[str, Any]:
    """Create a new thread."""
    store = _require_store()
    thread = store.create_thread(
        req.thread_id, title=req.title, status=req.status,
        persona_id=req.persona_id, **req.metadata,
    )
    return {"status": "ok", "thread": thread}


@router.put(
    "/threads/{thread_id}",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_update_thread(thread_id: str, req: UpdateThreadRequest) -> Dict[str, Any]:
    """Update a thread's fields."""
    store = _require_store()
    success = store.update_thread(thread_id, **req.fields)
    return {"status": "ok" if success else "error", "updated": success}


@router.get(
    "/threads",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_list_threads(
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """List threads with optional status filter."""
    store = _require_store()
    threads = store.list_threads(status=status, limit=limit, offset=offset)
    return {"status": "ok", "threads": threads, "count": len(threads)}


# ---------------------------------------------------------------------------
# Message endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/messages",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_append_message(req: AppendMessageRequest) -> Dict[str, Any]:
    """Append a message to a thread."""
    store = _require_store()
    message_id = store.append_message(
        req.thread_id, role=req.role, content=req.content,
        turn_id=req.turn_id, **req.metadata,
    )
    return {"status": "ok", "message_id": message_id}


@router.put(
    "/messages/{message_id}",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_update_message(message_id: int, req: UpdateMessageRequest) -> Dict[str, Any]:
    """Update a message's fields."""
    store = _require_store()
    success = store.update_message(message_id, **req.fields)
    return {"status": "ok" if success else "error", "updated": success}


@router.get(
    "/threads/{thread_id}/messages",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_list_messages(
    thread_id: str,
    limit: Optional[int] = Query(None, ge=1, le=500),
) -> Dict[str, Any]:
    """List messages in a thread."""
    store = _require_store()
    messages = store.list_messages(thread_id, limit=limit)
    return {"status": "ok", "messages": messages, "count": len(messages)}


@router.get(
    "/threads/{thread_id}/recent-messages",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_recent_messages(
    thread_id: str,
    limit: int = Query(12, ge=1, le=100),
) -> Dict[str, Any]:
    """Get recent messages from a thread."""
    store = _require_store()
    messages = store.recent_messages(thread_id, limit=limit)
    return {"status": "ok", "messages": messages, "count": len(messages)}


# ---------------------------------------------------------------------------
# Open loops
# ---------------------------------------------------------------------------

@router.post(
    "/open-loops",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_add_open_loop(req: AddOpenLoopRequest) -> Dict[str, Any]:
    """Add an open loop to a thread."""
    store = _require_store()
    loop_id = store.add_open_loop(
        req.thread_id, description=req.description, priority=req.priority,
    )
    return {"status": "ok", "loop_id": loop_id}


@router.get(
    "/threads/{thread_id}/open-loops",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_list_open_loops(
    thread_id: str,
    open_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """List open loops in a thread."""
    store = _require_store()
    loops = store.list_open_loops(thread_id, open_only=open_only, limit=limit)
    return {"status": "ok", "loops": loops, "count": len(loops)}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.get(
    "/search",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Search across all conversations."""
    store = _require_store()
    results = store.search(q, limit=limit)
    return {"status": "ok", "results": results, "count": len(results)}


@router.get(
    "/search-receipts",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_search_receipts(
    q: str = Query(..., description="Search query"),
    thread_id: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
) -> Dict[str, Any]:
    """Search receipts across threads."""
    store = _require_store()
    results = store.search_receipts(q, thread_id=thread_id, limit=limit)
    return {"status": "ok", "results": results, "count": len(results)}


# ---------------------------------------------------------------------------
# Recovery & maintenance
# ---------------------------------------------------------------------------

@router.post(
    "/mark-in-progress-interrupted",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_mark_in_progress_interrupted() -> Dict[str, Any]:
    """Mark all in-progress messages as interrupted (recovery)."""
    store = _require_store()
    count = store.mark_in_progress_interrupted()
    return {"status": "ok", "marked": count}


@router.post(
    "/messages/{message_id}/redact",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_redact_message(message_id: int) -> Dict[str, Any]:
    """Redact a message (propagates RedactionFailed as 500)."""
    store = _require_store()
    try:
        result = store.redact_message(message_id)
        return {"status": "ok", "result": result}
    except Exception as e:
        # RedactionFailed or other errors propagate as 500
        raise HTTPException(status_code=500, detail=f"Redaction failed: {e}")


@router.post(
    "/merge-thread",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_merge_thread(req: MergeThreadRequest) -> Dict[str, Any]:
    """Merge two threads."""
    store = _require_store()
    result = store.merge_thread(req.new_thread_id, req.prev_thread_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Merge failed — thread not found")
    return {"status": "ok", "result": result}
