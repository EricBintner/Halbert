"""
Web Search API Routes

Provides endpoints for web search functionality using SearXNG.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...web.search import WebSearch, get_web_search, SearchResult

logger = logging.getLogger("halbert")
router = APIRouter(prefix="/web-search", tags=["web-search"])


class SearchRequest(BaseModel):
    """Request body for search endpoint."""
    query: str
    max_results: int = 10
    engines: Optional[List[str]] = None
    time_range: Optional[str] = None
    use_cache: bool = True


class InstanceConfig(BaseModel):
    """Configuration for adding/updating instances."""
    url: str
    is_self_hosted: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Search Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/search")
async def search(request: SearchRequest) -> Dict[str, Any]:
    """
    Perform a web search.
    
    Returns search results from SearXNG instances.
    """
    try:
        ws = get_web_search()
        results = await ws.search(
            query=request.query,
            max_results=request.max_results,
            engines=request.engines,
            time_range=request.time_range,
            use_cache=request.use_cache,
        )
        
        return {
            "status": "success",
            "query": request.query,
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_get(
    q: str,
    max_results: int = 10,
    engines: Optional[str] = None,
    time_range: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Perform a web search (GET version for easy testing).
    """
    engine_list = engines.split(",") if engines else None
    
    try:
        ws = get_web_search()
        results = await ws.search(
            query=q,
            max_results=max_results,
            engines=engine_list,
            time_range=time_range,
        )
        
        return {
            "status": "success",
            "query": q,
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search-for-rag")
async def search_for_rag(request: SearchRequest) -> Dict[str, Any]:
    """
    Search and format results for RAG context.
    
    Returns formatted text suitable for LLM context injection.
    """
    try:
        ws = get_web_search()
        context = await ws.search_for_rag(
            query=request.query,
            max_results=request.max_results,
        )
        
        return {
            "status": "success",
            "query": request.query,
            "context": context,
        }
        
    except Exception as e:
        logger.error(f"RAG search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Instance Management Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/instances")
async def get_instances() -> Dict[str, Any]:
    """
    Get status of all configured SearXNG instances.
    """
    ws = get_web_search()
    return {
        "status": "success",
        "instances": ws.get_instance_status(),
    }


@router.post("/instances/check")
async def check_instances() -> Dict[str, Any]:
    """
    Check health of all instances.
    
    Pings each instance and measures latency.
    """
    try:
        ws = get_web_search()
        health = await ws.check_all_instances()
        
        healthy_count = sum(1 for h in health.values() if h.healthy)
        
        return {
            "status": "success",
            "total": len(health),
            "healthy": healthy_count,
            "unhealthy": len(health) - healthy_count,
            "instances": [
                {
                    "url": h.url,
                    "healthy": h.healthy,
                    "latency_ms": round(h.latency_ms, 1) if h.healthy else None,
                    "error": h.error,
                }
                for h in health.values()
            ],
        }
        
    except Exception as e:
        logger.error(f"Instance check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/instances/add")
async def add_instance(config: InstanceConfig) -> Dict[str, Any]:
    """
    Add a new SearXNG instance.
    """
    ws = get_web_search()
    
    # Validate URL format
    url = config.url.rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    
    if config.is_self_hosted:
        ws.self_hosted = url
    else:
        if url not in ws.instances:
            ws.instances.insert(0, url)  # Add at front for priority
    
    return {
        "status": "success",
        "message": f"Added instance: {url}",
        "is_self_hosted": config.is_self_hosted,
    }


@router.delete("/instances")
async def remove_instance(url: str) -> Dict[str, Any]:
    """
    Remove a SearXNG instance.
    """
    ws = get_web_search()
    
    if ws.self_hosted == url:
        ws.self_hosted = None
        return {"status": "success", "message": f"Removed self-hosted instance: {url}"}
    
    if url in ws.instances:
        ws.instances.remove(url)
        return {"status": "success", "message": f"Removed instance: {url}"}
    
    raise HTTPException(status_code=404, detail=f"Instance not found: {url}")


# ─────────────────────────────────────────────────────────────────────────────
# Cache Management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/cache/stats")
async def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics.
    """
    ws = get_web_search()
    cache = ws.cache
    
    return {
        "status": "success",
        "entries": len(cache.results),
        "max_entries": cache.max_entries,
        "ttl_seconds": cache.ttl_seconds,
    }


@router.post("/cache/clear")
async def clear_cache() -> Dict[str, Any]:
    """
    Clear the search cache.
    """
    ws = get_web_search()
    count = len(ws.cache.results)
    ws.cache.results.clear()
    ws.cache.timestamps.clear()
    
    return {
        "status": "success",
        "message": f"Cleared {count} cached entries",
    }
