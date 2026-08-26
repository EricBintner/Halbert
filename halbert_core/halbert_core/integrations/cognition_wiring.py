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
import os
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

    # Set scene context to the system identity (platform-derived)
    from ..utils.platform import is_linux, is_macos

    if is_macos():
        cognition.scene_context = "macOS system administration"
    elif is_linux():
        cognition.scene_context = "Linux system administration"
    else:
        cognition.scene_context = "system administration"

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


def _ensure_app_seam_wired() -> None:
    """Register the Halbert AppSeam if nothing is registered yet (guarded).

    routes/agent.py calls get_cognition_tick() before get_event_mapper(),
    so the seam must be wired here for the thought generator to find it.
    """
    try:
        from haloysius.seam import get_app_seam

        if get_app_seam() is None:
            from . import app_seam

            app_seam.wire_halbert_seam()
    except Exception as e:
        logger.warning(f"Could not wire app seam (non-fatal): {e}")


def _llm_thoughts_enabled() -> bool:
    return os.environ.get("HALBERT_LLM_THOUGHTS", "").strip().lower() in ("1", "true", "yes")


def _create_thought_generator():
    """ThoughtGenerator whose llm_generate is the registered seam ModelBackend.

    This is the seam ModelBackend's one real consumer. Returns None (template
    thoughts) if no seam/model backend is wired.
    """
    try:
        from haloysius.seam import get_app_seam
        from haloysius.persona.thought_generator import ThoughtGenerator

        seam = get_app_seam()
        backend = seam.get_model_backend() if seam is not None else None
        if backend is None or not hasattr(backend, "generate_text"):
            return None
        return ThoughtGenerator("halbert", "Halbert", llm_generate=backend.generate_text)
    except Exception as e:
        logger.warning(f"Could not create LLM thought generator: {e}")
        return None


def get_cognition_tick() -> Callable:
    """Return a callable wrapping advance_turn for the state machine.

    The returned callable has the signature:
        tick(cognition, user_message, assistant_response) -> TurnResult

    Memory callbacks (memory_store_add, memory_store_search) are wired
    from HaloysiusMemoryAdapter so thought promotion persists to the
    PersonaMemoryStore.

    Thought generation: when HALBERT_LLM_THOUGHTS is truthy (1/true/yes) a
    ThoughtGenerator backed by the seam ModelBackend is passed to
    advance_turn; this adds a blocking guide-model LLM call per triggered
    turn, so it is OFF by default (template thoughts).
    """
    from haloysius.persona import cognition_tick as _ct

    # Ensure cognition exists
    get_cognition()

    # Seam must be registered before we can read its model backend
    _ensure_app_seam_wired()

    # Wire memory adapter for thought promotion persistence
    memory_adapter = _create_memory_adapter()
    mem_add = memory_adapter.add_callback() if memory_adapter else None
    mem_search = memory_adapter.search_callback() if memory_adapter else None

    thought_generator = None
    if _llm_thoughts_enabled():
        thought_generator = _create_thought_generator()
        if thought_generator is not None:
            logger.info("Cognition tick: LLM thought generation ON (seam model backend)")
        else:
            logger.info(
                "Cognition tick: HALBERT_LLM_THOUGHTS set but no seam model backend — "
                "using template thoughts"
            )
    else:
        logger.info("Cognition tick: template thoughts (set HALBERT_LLM_THOUGHTS=1 for LLM)")

    def tick(cognition, user_message, assistant_response):
        return _ct.advance_turn(
            cognition=cognition,
            user_message=user_message,
            assistant_response=assistant_response,
            thought_generator=thought_generator,
            memory_store_add=mem_add,
            memory_store_search=mem_search,
        )

    return tick


def get_event_mapper():
    """Get or create the singleton SystemEventMapper instance.

    Also ensures the Halbert AppSeam (SourcePrep retrieval backend, model
    backend, governance policy) is registered on first call; it is usually
    already registered by get_cognition_tick(), which runs first.
    """
    global _event_mapper, _trackers
    if _event_mapper is None:
        _ensure_app_seam_wired()

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
