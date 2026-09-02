# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Persona management routes for dashboard.

Provides REST API for persona switching and memory management.
"""

from __future__ import annotations
from typing import Dict, Any
import logging

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from ...persona import PersonaManager, Persona, PersonaSwitchError, MemoryPurge
from ...persona.store import PersonaStore

logger = logging.getLogger('halbert.dashboard')

# Shared with settings.py to prevent races between persona switch and config save.
try:
    from .settings import _being_config_lock
except ImportError:
    import threading
    _being_config_lock = threading.Lock()


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

    class CreatePersonaRequest(BaseModel):
        """Request to create a new persona."""
        display_name: str


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
async def list_personas() -> Dict[str, Any]:
    """
    List all personas with the active one marked.
    
    Returns::
    
        {"personas": [...], "active_id": "default"}
    """
    try:
        store = PersonaStore()
        personas = [p.to_dict() for p in store.list_personas()]
        return {"personas": personas, "active_id": store.get_active_id()}
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


# ── Multi-persona CRUD endpoints ──────────────────────────────────────

@router.post("")
async def create_persona(request: CreatePersonaRequest) -> Dict[str, Any]:
    """Create a new persona."""
    try:
        store = PersonaStore()
        summary = store.create_persona(request.display_name)
        return {"status": "ok", "persona": summary.to_dict()}
    except Exception as e:
        logger.error(f"Error creating persona: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{persona_id}")
async def get_persona(persona_id: str) -> Dict[str, Any]:
    """Get a persona's full config."""
    try:
        store = PersonaStore()
        return {"status": "ok", "config": store.get_persona(persona_id)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Persona not found: {persona_id}")
    except Exception as e:
        logger.error(f"Error getting persona: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{persona_id}")
async def delete_persona(persona_id: str) -> Dict[str, Any]:
    """Delete a persona. Cannot delete the active or last persona."""
    try:
        store = PersonaStore()
        store.delete_persona(persona_id)
        return {"status": "ok"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Persona not found: {persona_id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting persona: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{persona_id}/activate")
async def activate_persona(persona_id: str) -> Dict[str, Any]:
    """Switch the active persona. Swaps the being.yml symlink and hot-reloads the agent."""
    try:
        store = PersonaStore()
        with _being_config_lock:
            store.activate(persona_id)
        # Hot-reload the running agent's personality
        try:
            from .agent import get_agent
            agent = get_agent()
            builder = getattr(agent, "prompt_builder", None) if agent else None
            if builder is not None:
                builder.reload_personality()
        except Exception as e:
            logger.warning(f"Agent hot-reload after persona switch: {e}")
        return {"status": "ok", "active_id": persona_id}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Persona not found: {persona_id}")
    except Exception as e:
        logger.error(f"Error activating persona: {e}")
        raise HTTPException(status_code=500, detail=str(e))
