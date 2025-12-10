"""
Memory management API routes.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any

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
