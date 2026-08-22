"""
Cognition Wiring — connects Haloysius cognitive core to Halbert's agent.

This module provides factory functions that:
1. Create a PersonaCognition instance for Halbert
2. Wire advance_turn as the cognition_tick callable
3. Wire the SystemEventMapper for populating cognition from system events
4. Register state trackers with Haloysius continuity

All imports are lazy so the agent still works if Haloysius is not installed.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("halbert.integrations.cognition_wiring")

# Module-level singletons
_cognition = None
_event_mapper = None
_trackers = None


def _create_cognition():
    """Create a PersonaCognition instance configured for Halbert."""
    from haloysius.persona.cognition import PersonaCognition

    cognition = PersonaCognition(persona_id="halbert")

    # Set scene context to the system identity
    cognition.scene_context = "Linux system administration"

    logger.info("Created PersonaCognition for halbert")
    return cognition


def get_cognition():
    """Get or create the singleton PersonaCognition instance."""
    global _cognition
    if _cognition is None:
        _cognition = _create_cognition()
    return _cognition


def _create_memory_adapter():
    """Create a HaloysiusMemoryAdapter backed by PersonaMemoryStore.

    This connects advance_turn's thought promotion to persistent memory.
    """
    try:
        from haloysius.memory_v2.store import PersonaMemoryStore
        from .haloysius_memory_adapter import HaloysiusMemoryAdapter

        store = PersonaMemoryStore("halbert")
        adapter = HaloysiusMemoryAdapter(store)
        logger.info("Created HaloysiusMemoryAdapter for halbert")
        return adapter
    except Exception as e:
        logger.warning(f"Could not create memory adapter: {e}")
        return None


def get_cognition_tick() -> Callable:
    """Return a callable wrapping advance_turn for the state machine.

    The returned callable has the signature:
        tick(cognition, user_message, assistant_response) -> TurnResult

    Memory callbacks (memory_store_add, memory_store_search) are wired
    from HaloysiusMemoryAdapter so thought promotion persists to the
    PersonaMemoryStore.
    """
    from haloysius.persona.cognition_tick import advance_turn

    # Ensure cognition exists
    get_cognition()

    # Wire memory adapter for thought promotion persistence
    memory_adapter = _create_memory_adapter()
    mem_add = memory_adapter.add_callback() if memory_adapter else None
    mem_search = memory_adapter.search_callback() if memory_adapter else None

    def tick(cognition, user_message, assistant_response):
        return advance_turn(
            cognition=cognition,
            user_message=user_message,
            assistant_response=assistant_response,
            memory_store_add=mem_add,
            memory_store_search=mem_search,
        )

    return tick


def get_event_mapper():
    """Get or create the singleton SystemEventMapper instance.

    Also wires the Halbert AppSeam (SourcePrep retrieval backend, model
    backend, governance policy) with Haloysius on first call.
    """
    global _event_mapper, _trackers
    if _event_mapper is None:
        # Wire app seam (SourcePrep retrieval, model backend, governance)
        try:
            from .app_seam import wire_halbert_seam
            wire_halbert_seam()
            logger.info("Halbert AppSeam wired")
        except Exception as e:
            logger.warning(f"Could not wire app seam (non-fatal): {e}")

        from .system_event_mapper import SystemEventMapper

        # Try to register state trackers with Haloysius
        try:
            from .state_trackers import register_halbert_state_trackers
            _trackers = register_halbert_state_trackers()
        except Exception as e:
            logger.warning(f"Could not register state trackers: {e}")
            _trackers = {}

        # Try to get discovery engine (telemetry is handled by TelemetryAdapter via psutil)
        discovery = None
        try:
            from ..discovery.engine import get_engine
            discovery = get_engine()
        except Exception:
            pass

        _event_mapper = SystemEventMapper(
            discovery_engine=discovery,
            telemetry_store=None,
            trackers=_trackers,
        )

        # Start background scan
        _event_mapper.start_background_scan()

    return _event_mapper


def get_trackers():
    """Get the registered state tracker instances."""
    global _trackers
    if _trackers is None:
        try:
            from .state_trackers import register_halbert_state_trackers
            _trackers = register_halbert_state_trackers()
        except Exception as e:
            logger.warning(f"Could not register state trackers: {e}")
            _trackers = {}
    return _trackers


def shutdown():
    """Clean shutdown of background threads and trackers."""
    global _event_mapper, _cognition, _trackers
    if _event_mapper is not None:
        _event_mapper.stop_background_scan()
        _event_mapper = None
    _cognition = None
    _trackers = None
    logger.info("Cognition wiring shut down")
