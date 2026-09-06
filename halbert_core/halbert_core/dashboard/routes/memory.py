# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Memory management API routes.

The ChromaDB collection browser (self_* collections: self_hwmon, self_journald,
self_dbus, discoveries, ...) backing the Memory dashboard page. These were moved
here from routes/chat.py as part of the chat endpoint retirement (T4b.1).

The former /stats and /search endpoints sat on the file-backed MemoryRetrieval,
which was removed 2026-08-26 (audit F1) -- it could never return anything that
had been written. Machine state is now the state ledger
(continuity.state_store.StateStore, MEM-02); identity and semantic memory are
Haloysius memory_v2.

Peer memory endpoints (P2b)
---------------------------
The ``/api/memory/add``, ``/search``, ``/get/{id}``, ``/delete/{id}`` routes
expose the local ``PersonaMemoryStore`` over HTTP so that a paired peer node
(the workstation) can read/write the canonical memory store on the HA server.
All peer memory routes require peer bearer auth — no ``mcp_response()``
redaction (this is internal entity communication, not external MCP traffic).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from ...federation.peer_middleware import require_peer_auth

logger = logging.getLogger('halbert.dashboard.routes.memory')

router = APIRouter()


# -------------------------------------------------------------------------
# ChromaDB collection browser (moved from routes/chat.py — T4b.1)
#
# These back the Memory dashboard page's collection inspector. They use the
# ChromaDB index (self_* collections / discoveries), NOT the Haloysius file
# memory used by /stats and /search above.
# -------------------------------------------------------------------------


@router.get("/index/stats")
async def get_index_stats() -> Dict[str, Any]:
    """Get ChromaDB index statistics (collection counts and status)."""
    try:
        from ...index.chroma_index import get_index

        index = get_index()
        stats = index.get_stats()
        return {
            "status": "ok",
            "chromadb_available": stats.get("chromadb_available", False),
            "persist_path": stats.get("persist_path"),
            "memory_events": stats.get("memory_events", 0),
            "collections": stats.get("collections", {}),
        }
    except Exception as e:
        logger.error(f"Memory index stats error: {e}")
        return {
            "status": "error",
            "error": str(e),
            "chromadb_available": False,
        }


class MemoryQueryRequest(BaseModel):
    query: str
    k: int = 5
    collection: Optional[str] = None


@router.post("/query")
async def query_memory_index(request: MemoryQueryRequest) -> Dict[str, Any]:
    """Query the ChromaDB memory index directly.

    Note: the legacy chat.py version of this endpoint declared bare scalar
    params on a POST, which FastAPI binds as query strings — the Memory
    page sends a JSON body, so the scalar version always 422'd. This
    version takes the JSON body the UI actually sends.
    """
    query, k, collection = request.query, request.k, request.collection
    try:
        from ...index.chroma_index import get_index

        index = get_index()
        results = index.query(query, k=k, collection=collection)
        return {
            "status": "ok",
            "query": query,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        logger.error(f"Memory query error: {e}")
        return {"status": "error", "error": str(e), "results": []}


@router.get("/collections")
async def list_memory_collections() -> Dict[str, Any]:
    """List all memory collections with counts."""
    try:
        from ...index.chroma_index import get_index

        index = get_index()
        collections = index.list_collections()
        return {"status": "ok", "collections": collections}
    except Exception as e:
        logger.error(f"List collections error: {e}")
        return {"status": "error", "error": str(e), "collections": []}


class DeleteEntriesRequest(BaseModel):
    entry_ids: List[str]


@router.get("/collections/{collection}/entries")
async def list_memory_entries(
    collection: str, limit: int = 50, offset: int = 0
) -> Dict[str, Any]:
    """List entries in a specific collection."""
    try:
        from ...index.chroma_index import get_index

        index = get_index()
        entries = index.list_entries(collection, limit=limit, offset=offset)
        return {
            "status": "ok",
            "collection": collection,
            "entries": entries,
            "count": len(entries),
        }
    except Exception as e:
        logger.error(f"List entries error: {e}")
        return {"status": "error", "error": str(e), "entries": []}


@router.post("/collections/{collection}/delete")
async def delete_memory_entries(
    collection: str, request: DeleteEntriesRequest
) -> Dict[str, Any]:
    """Delete multiple entries from a collection."""
    try:
        from ...index.chroma_index import get_index

        index = get_index()
        count = index.delete_entries(collection, request.entry_ids)
        return {"status": "ok", "deleted": count}
    except Exception as e:
        logger.error(f"Delete entries error: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/collections/{collection}/clear")
async def clear_memory_collection(collection: str) -> Dict[str, Any]:
    """Clear all entries from a collection. USE WITH CAUTION."""
    try:
        from ...index.chroma_index import get_index

        index = get_index()
        success = index.clear_collection(collection)
        return {"status": "ok" if success else "error", "cleared": success}
    except Exception as e:
        logger.error(f"Clear collection error: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/collections/{collection}/entries/{entry_id:path}")
async def get_memory_entry(collection: str, entry_id: str) -> Dict[str, Any]:
    """Get a specific entry by ID."""
    try:
        from ...index.chroma_index import get_index

        index = get_index()
        entry = index.get_entry(collection, entry_id)
        if entry:
            return {"status": "ok", "entry": entry}
        return {"status": "error", "error": "Entry not found"}
    except Exception as e:
        logger.error(f"Get entry error: {e}")
        return {"status": "error", "error": str(e)}


@router.delete("/collections/{collection}/entries/{entry_id:path}")
async def delete_memory_entry(collection: str, entry_id: str) -> Dict[str, Any]:
    """Delete a specific entry."""
    try:
        from ...index.chroma_index import get_index

        index = get_index()
        success = index.delete_entry(collection, entry_id)
        return {"status": "ok" if success else "error", "deleted": success}
    except Exception as e:
        logger.error(f"Delete entry error: {e}")
        return {"status": "error", "error": str(e)}


# -------------------------------------------------------------------------
# Peer memory endpoints (P2b)
#
# Expose the local PersonaMemoryStore over HTTP so a paired peer (the
# workstation) can read/write the canonical memory store on the HA server.
# All routes require peer bearer auth. No mcp_response() redaction — this
# is internal entity communication.
# -------------------------------------------------------------------------


_persona_stores: Dict[str, Any] = {}


def _get_persona_memory_store():
    """Get the local PersonaMemoryStore for the current persona.

    Lazy import to avoid pulling haloysius at module load time (subtractive
    contract). Returns None if haloysius is not installed. Cached per
    persona_id so we don't re-instantiate the store (and its embedder) on
    every request.
    """
    try:
        from haloysius.memory_v2.store import PersonaMemoryStore
        from ...integrations.cognition_wiring import _get_persona_id

        persona_id = _get_persona_id()
        if persona_id not in _persona_stores:
            _persona_stores[persona_id] = PersonaMemoryStore(persona_id)
        return _persona_stores[persona_id]
    except Exception as e:
        logger.error(f"Could not create PersonaMemoryStore: {e}")
        return None


def _reset_persona_memory_stores():
    """Clear cached stores (for testing)."""
    _persona_stores.clear()


class PeerMemoryAddRequest(BaseModel):
    """A PersonaMemory dict sent by a peer for smart_add."""
    memory: Dict[str, Any] = Field(..., description="PersonaMemory.to_dict() payload")


class PeerMemoryAddResponse(BaseModel):
    """Result of smart_add: operation, reason, and assigned memory_id."""
    operation: str
    reason: str
    memory_id: Optional[str] = None


@router.post(
    "/add",
    response_model=PeerMemoryAddResponse,
    dependencies=[Depends(require_peer_auth)],
)
async def peer_memory_add(request: PeerMemoryAddRequest) -> PeerMemoryAddResponse:
    """Add a memory to the local PersonaMemoryStore (peer-writable).

    Accepts a PersonaMemory dict (as produced by ``to_dict()``),
    reconstructs it via ``from_dict()``, and calls ``smart_add()``.
    Returns the operation type, reason, and assigned memory_id.

    Requires peer bearer auth. No redaction — internal entity communication.
    """
    from haloysius.memory_v2.types import PersonaMemory

    store = _get_persona_memory_store()
    if store is None:
        raise HTTPException(status_code=503, detail="PersonaMemoryStore unavailable")

    try:
        memory = PersonaMemory.from_dict(request.memory)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid memory payload: {e}")

    operation, reason, memory_id = store.smart_add(memory)
    return PeerMemoryAddResponse(
        operation=operation.value,
        reason=reason,
        memory_id=memory_id,
    )


@router.get(
    "/search",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_memory_search(
    q: str = Query(..., description="Search query"),
    k: int = Query(5, ge=1, le=50, description="Number of results"),
    memory_type: Optional[str] = Query(None, description="Filter by memory type"),
) -> Dict[str, Any]:
    """Search the local PersonaMemoryStore (peer-readable).

    Returns a list of memory dicts (as produced by ``to_dict()``).
    Requires peer bearer auth.
    """
    store = _get_persona_memory_store()
    if store is None:
        raise HTTPException(status_code=503, detail="PersonaMemoryStore unavailable")

    # Convert memory_type string to MemoryType enum if provided
    mt_enum = None
    if memory_type:
        try:
            from haloysius.memory_v2.types import MemoryType
            mt_enum = MemoryType(memory_type)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid memory_type {memory_type!r}",
            )

    results = store.search(q, k=k, memory_type=mt_enum)
    return {
        "status": "ok",
        "query": q,
        "results": [m.to_dict() for m in results],
        "count": len(results),
    }


@router.get(
    "/get/{memory_id}",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_memory_get(memory_id: str) -> Dict[str, Any]:
    """Get a single memory by ID from the local PersonaMemoryStore.

    Returns 404 if not found. Requires peer bearer auth.
    """
    store = _get_persona_memory_store()
    if store is None:
        raise HTTPException(status_code=503, detail="PersonaMemoryStore unavailable")

    memory = store.get(memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")

    return {"status": "ok", "memory": memory.to_dict()}


@router.delete(
    "/delete/{memory_id}",
    dependencies=[Depends(require_peer_auth)],
)
async def peer_memory_delete(memory_id: str) -> Dict[str, Any]:
    """Soft-delete a memory by ID from the local PersonaMemoryStore.

    Returns 404 if not found. Requires peer bearer auth.
    """
    store = _get_persona_memory_store()
    if store is None:
        raise HTTPException(status_code=503, detail="PersonaMemoryStore unavailable")

    deleted = store.delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")

    return {"status": "ok", "deleted": memory_id}
