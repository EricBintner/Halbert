# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Persona management for Halbert (Phase 4 M1, M4).

Handles persona switching, state management, memory isolation, and auto-context detection.
"""

from .manager import PersonaManager, Persona, PersonaSwitchError
from .memory_purge import MemoryPurge, PurgeConfirmation
from .context_detector import ContextDetector, ContextSignal, ContextPreferences
from .store import PersonaStore, PersonaSummary

__all__ = [
    "PersonaManager",
    "Persona",
    "PersonaSwitchError",
    "MemoryPurge",
    "PurgeConfirmation",
    "ContextDetector",
    "ContextSignal",
    "ContextPreferences",
    "PersonaStore",
    "PersonaSummary",
]
