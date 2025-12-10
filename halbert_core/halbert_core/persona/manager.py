"""
Persona Manager.

Manages persona switching, state persistence, and integration with
memory/prompts/audit systems.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum
import json
import logging

from ..obs.logging import get_logger
from ..obs.audit import write_audit

logger = get_logger("halbert")


class Persona(str, Enum):
    """Available personas."""
    IT_ADMIN = "it_admin"
    FRIEND = "friend"
    CUSTOM = "custom"  # Phase 5


class PersonaSwitchError(Exception):
    """Raised when persona switch fails."""
    pass


@dataclass
class PersonaState:
    """Current persona state."""
    active_persona: Persona
    memory_dir: str
    switched_at: str
    switched_by: str


class PersonaManager:
    """
    Manages persona state and switching.
    
    Usage:
        manager = PersonaManager()
        
        # Switch persona
        manager.switch_to(Persona.FRIEND, user="admin")
        
        # Get current state
        state = manager.get_state()
        print(f"Active: {state.active_persona}")
        
        # List available personas
        personas = manager.list_personas()
    """
    
    def __init__(self, state_file: Optional[Path] = None):
        """
        Initialize persona manager.
        
        Args:
            state_file: Path to persona state file.
                       If None, uses default location.
        """
        if state_file is None:
            state_file = Path.home() / '.local/share/halbert/persona_state.json'
        
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load or create initial state
        if self.state_file.exists():
            self.state = self._load_state()
        else:
            self.state = self._create_default_state()
            self._save_state()
        
        logger.info("PersonaManager initialized", extra={
            "active_persona": self.state.active_persona.value,
            "state_file": str(self.state_file)
        })
    
    def _create_default_state(self) -> PersonaState:
        """Create default persona state (IT Admin)."""
        return PersonaState(
            active_persona=Persona.IT_ADMIN,
            memory_dir="core",
            switched_at=datetime.now(timezone.utc).isoformat(),
            switched_by="system"
        )
    
    def _load_state(self) -> PersonaState:
        """Load persona state from file."""
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            
            return PersonaState(
                active_persona=Persona(data["active_persona"]),
                memory_dir=data["memory_dir"],
                switched_at=data["switched_at"],
                switched_by=data["switched_by"]
            )
        except Exception as e:
            logger.error(f"Failed to load persona state: {e}. Using default.")
            return self._create_default_state()
    
    def _save_state(self):
        """Save persona state to file."""
        try:
            data = {
                "active_persona": self.state.active_persona.value,
                "memory_dir": self.state.memory_dir,
                "switched_at": self.state.switched_at,
                "switched_by": self.state.switched_by
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug("Persona state saved")
        
        except Exception as e:
            logger.error(f"Failed to save persona state: {e}")
    
    def switch_to(
        self,
        persona: Persona,
        user: str = "system"
    ) -> bool:
        """
        Switch to a different persona.
        
        Args:
            persona: Target persona
            user: User who authorized the switch
        
        Returns:
            True if switch successful
        
        Raises:
            PersonaSwitchError: If switch fails
        """
        if persona == self.state.active_persona:
            logger.info(f"Already in {persona.value} persona")
            return True
        
        # Validate persona
        if persona == Persona.CUSTOM:
            raise PersonaSwitchError(
                "Custom persona is not available (coming in Phase 5)"
            )
        
        previous_persona = self.state.active_persona.value
        
        try:
            # Determine memory directory
            if persona == Persona.IT_ADMIN:
                memory_dir = "core"
            elif persona == Persona.FRIEND:
                memory_dir = "personas/friend"
            else:
                memory_dir = f"personas/{persona.value}"
            
            # Update state
            self.state = PersonaState(
                active_persona=persona,
                memory_dir=memory_dir,
                switched_at=datetime.now(timezone.utc).isoformat(),
                switched_by=user
            )
            
            # Persist state
            self._save_state()
            
            # Audit log
            write_audit(
                tool="persona",
                mode="switch",
                request_id="",
                ok=True,
                summary=f"Switched from {previous_persona} to {persona.value}",
                user=user
            )
            
            logger.info(f"Persona switched: {previous_persona} → {persona.value}", extra={
                "from": previous_persona,
                "to": persona.value,
                "user": user
            })
            
            return True
        
        except Exception as e:
            logger.error(f"Persona switch failed: {e}")
            raise PersonaSwitchError(f"Failed to switch persona: {e}")
    
    def get_state(self) -> PersonaState:
        """Get current persona state."""
        return self.state
    
    def get_active_persona(self) -> Persona:
        """Get active persona."""
        return self.state.active_persona
    
    def get_memory_dir(self) -> str:
        """Get memory directory for active persona."""
        return self.state.memory_dir
    
    def list_personas(self) -> List[Dict[str, Any]]:
        """
        List available personas.
        
        Returns:
            List of persona info dicts
        """
        personas = [
            {
                "id": Persona.IT_ADMIN.value,
                "name": "IT Administrator",
                "description": "Professional system management",
                "icon": "🔧",
                "enabled": True,
                "memory_dir": "core",
                "default": True
            },
            {
                "id": Persona.FRIEND.value,
                "name": "Casual Companion",
                "description": "Warm conversational style",
                "icon": "😊",
                "enabled": True,
                "memory_dir": "personas/friend",
                "default": False
            },
            {
                "id": Persona.CUSTOM.value,
                "name": "Custom Persona",
                "description": "User-defined (Phase 5)",
                "icon": "⚙️",
                "enabled": False,
                "memory_dir": "personas/custom",
                "default": False,
                "note": "Coming in Phase 5"
            }
        ]
        
        # Mark active persona
        for p in personas:
            p["active"] = (p["id"] == self.state.active_persona.value)
        
        return personas
    
    def get_persona_info(self, persona: Persona) -> Dict[str, Any]:
        """Get detailed info for a specific persona."""
        personas = self.list_personas()
        for p in personas:
            if p["id"] == persona.value:
                return p
        return {}
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get persona switch history.
        
        Args:
            limit: Number of recent switches to return
        
        Returns:
            List of switch records
        """
        # TODO: Implement full history tracking
        # For now, return current state only
        return [{
            "persona": self.state.active_persona.value,
            "switched_at": self.state.switched_at,
            "switched_by": self.state.switched_by
        }]
    
    def export_state(self) -> Dict[str, Any]:
        """
        Export persona state for backup/transfer.
        
        Returns:
            State dict suitable for JSON serialization
        """
        return {
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "state": {
                "active_persona": self.state.active_persona.value,
                "memory_dir": self.state.memory_dir,
                "switched_at": self.state.switched_at,
                "switched_by": self.state.switched_by
            }
        }
