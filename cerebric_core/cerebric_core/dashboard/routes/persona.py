"""
Persona management routes for dashboard.

Provides REST API for persona switching and memory management.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
import logging

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from ...persona import PersonaManager, Persona, PersonaSwitchError, MemoryPurge

logger = logging.getLogger('cerebric.dashboard')


# Pydantic models for request/response
if FASTAPI_AVAILABLE:
    class PersonaSwitchRequest(BaseModel):
        """Request to switch persona."""
        persona: str
        user: str = "dashboard"
    
    class MemoryPurgeRequest(BaseModel):
        """Request to purge persona memory."""
        persona: str
        user: str = "dashboard"
        export_before: bool = True


# Create router
router = APIRouter(prefix="/api/persona", tags=["persona"])


@router.get("/status")
async def get_persona_status() -> Dict[str, Any]:
    """
    Get current persona status.
    
    Returns:
        {
            "active_persona": "it_admin",
            "memory_dir": "core",
            "switched_at": "2025-11-27T19:00:00Z",
            "switched_by": "system"
        }
    """
    try:
        manager = PersonaManager()
        state = manager.get_state()
        
        return {
            "active_persona": state.active_persona.value,
            "memory_dir": state.memory_dir,
            "switched_at": state.switched_at,
            "switched_by": state.switched_by
        }
    
    except Exception as e:
        logger.error(f"Error getting persona status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_personas() -> List[Dict[str, Any]]:
    """
    List available personas.
    
    Returns:
        [
            {
                "id": "it_admin",
                "name": "IT Administrator",
                "description": "Professional system management",
                "icon": "🔧",
                "enabled": true,
                "active": true,
                "memory_dir": "core"
            },
            ...
        ]
    """
    try:
        manager = PersonaManager()
        personas = manager.list_personas()
        return personas
    
    except Exception as e:
        logger.error(f"Error listing personas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/switch")
async def switch_persona(request: PersonaSwitchRequest) -> Dict[str, Any]:
    """
    Switch to a different persona.
    
    Args:
        request: PersonaSwitchRequest with persona, user
    
    Returns:
        {
            "success": true,
            "active_persona": "friend",
            "memory_dir": "personas/friend"
        }
    """
    try:
        manager = PersonaManager()
        
        # Parse persona
        try:
            target_persona = Persona(request.persona)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid persona: {request.persona}")
        
        # Execute switch
        success = manager.switch_to(
            target_persona,
            user=request.user
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Persona switch failed")
        
        # Get new state
        state = manager.get_state()
        
        return {
            "success": True,
            "active_persona": state.active_persona.value,
            "memory_dir": state.memory_dir
        }
    
    except PersonaSwitchError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error switching persona: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/stats")
async def get_memory_stats() -> Dict[str, Any]:
    """
    Get memory statistics for all personas.
    
    Returns:
        {
            "core": {"entries": 150, "size_mb": 1.2},
            "personas": {"entries": 45, "size_mb": 0.5},
            "shared": {"size_mb": 0.01}
        }
    """
    try:
        from ...memory.retrieval import MemoryRetrieval
        
        retrieval = MemoryRetrieval()
        stats = retrieval.get_stats()
        
        return stats
    
    except Exception as e:
        logger.error(f"Error getting memory stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory/purge")
async def purge_memory(request: MemoryPurgeRequest) -> Dict[str, Any]:
    """
    Purge persona memory (safe operation with export).
    
    Args:
        request: MemoryPurgeRequest with persona, user, export_before flag
    
    Returns:
        {
            "success": true,
            "persona": "friend",
            "entries_deleted": 45,
            "size_mb_deleted": 2.3,
            "exported": true,
            "export_path": "/path/to/backup.tar.gz"
        }
    """
    try:
        purge = MemoryPurge()
        
        result = purge.execute_purge(
            persona=request.persona,
            user=request.user,
            export_before=request.export_before
        )
        
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error purging memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))
