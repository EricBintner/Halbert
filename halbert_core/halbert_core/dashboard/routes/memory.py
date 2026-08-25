"""
Memory management API routes.

Two backends live behind this router:
- /stats and /search — Haloysius file-based memory (MemoryRetrieval:
  core, runtime, personas/* subdirectories).
- /index/*, /collections*, /query — the ChromaDB collection browser
  (self_* collections: self_hwmon, self_journald, self_dbus, discoveries,
  ...). These were moved here from routes/chat.py as part of the chat
  endpoint retirement (T4b.1); they back the Memory dashboard page.
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

logger = logging.getLogger('halbert.dashboard.routes.memory')

router = APIRouter()


@router.get("/stats")
async def get_memory_stats() -> Dict[str, Any]:
    """Get memory storage statistics."""
    try:
        from ...memory.retrieval import MemoryRetrieval
        
        retrieval = MemoryRetrieval()
        stats = retrieval.get_stats()
        
        return stats
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_memory(
    subdir: str = Query(..., description="Memory subdirectory (core, runtime, personas/*)"),
    query: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Max results")
) -> List[Dict[str, Any]]:
    """Search memory entries."""
    try:
        from ...memory.retrieval import MemoryRetrieval

        retrieval = MemoryRetrieval()
        results = retrieval.retrieve_from(subdir, query, k=limit)

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
