"""
Persona management for Cerebric (Phase 4 M1, M4).

Handles persona switching, state management, memory isolation, and auto-context detection.
"""

from .manager import PersonaManager, Persona, PersonaSwitchError
from .memory_purge import MemoryPurge, PurgeConfirmation
from .context_detector import ContextDetector, ContextSignal, ContextPreferences

__all__ = [
    "PersonaManager",
    "Persona",
    "PersonaSwitchError",
    "MemoryPurge",
    "PurgeConfirmation",
    "ContextDetector",
    "ContextSignal",
    "ContextPreferences",
]
