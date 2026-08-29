# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
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
_ha_event_mapper = None
_ha_event_stream = None
_frigate_event_mapper = None
_trackers = None


def _get_persona_id() -> str:
    """Get the persona identity from env, defaulting to 'halbert'."""
    return os.environ.get("HALBERT_PERSONA_ID", "halbert")


def _get_scene_context() -> str:
    """Get the scene context from env, falling back to platform-derived default."""
    env_ctx = os.environ.get("HALBERT_SCENE_CONTEXT", "").strip()
    if env_ctx:
        return env_ctx

    from ..utils.platform import is_linux, is_macos

    if is_macos():
        return "macOS system administration"
    elif is_linux():
        return "Linux system administration"
    else:
        return "system administration"


def _create_cognition():
    """Create a PersonaCognition instance configured for Halbert."""
    from haloysius.persona.cognition import PersonaCognition

    persona_id = _get_persona_id()
    cognition = PersonaCognition(persona_id=persona_id)
    cognition.scene_context = _get_scene_context()

    logger.info(f"Created PersonaCognition for {persona_id}")
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

        store = PersonaMemoryStore(_get_persona_id())
        adapter = HaloysiusMemoryAdapter(store)
        logger.info(f"Created HaloysiusMemoryAdapter for {_get_persona_id()}")
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
        persona_id = _get_persona_id()
        return ThoughtGenerator(persona_id, persona_id.capitalize(), llm_generate=backend.generate_text)
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

        # Wrap in composite with Frigate event mapper if available
        frigate_mapper = get_frigate_event_mapper()
        if frigate_mapper is not None:
            _event_mapper = CompositeEventMapper(
                primary=_event_mapper,
                secondary_mappers=[frigate_mapper],
            )
            logger.info("Event mapper wrapped with Frigate composite")

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


def get_ha_event_mapper():
    """Get or create the singleton HAEventMapper instance.

    Returns None if HA is not configured.
    """
    global _ha_event_mapper
    if _ha_event_mapper is None:
        try:
            from .home_assistant.ha_event_mapper import HAEventMapper
            _ha_event_mapper = HAEventMapper(trackers=_trackers)
        except Exception as e:
            logger.warning(f"Could not create HA event mapper: {e}")
    return _ha_event_mapper


def get_frigate_event_mapper():
    """Get or create the singleton FrigateEventMapper instance.

    Returns None if Frigate is not configured. The mapper is also
    used by the MQTT subscriber (via dashboard/app.py) — if that
    has already created one, we reuse it.
    """
    global _frigate_event_mapper
    if _frigate_event_mapper is None:
        try:
            from .frigate.frigate_config import load_frigate_config
            from .frigate.frigate_event_mapper import FrigateEventMapper

            config = load_frigate_config()
            if not config.is_configured():
                return None

            _frigate_event_mapper = FrigateEventMapper()
            logger.info("Frigate event mapper created")
        except Exception as e:
            logger.warning(f"Could not create Frigate event mapper: {e}")
    return _frigate_event_mapper


class CompositeEventMapper:
    """Calls populate_cognition() on multiple event mappers.

    Wraps the primary SystemEventMapper and any secondary mappers
    (HA, Frigate) so the AgentStateMachine only needs one
    event_mapper reference.
    """

    def __init__(self, primary, secondary_mappers=None):
        self._primary = primary
        self._secondary = [m for m in (secondary_mappers or []) if m is not None]

    def populate_cognition(self, cognition):
        if self._primary is not None:
            self._primary.populate_cognition(cognition)
        for mapper in self._secondary:
            try:
                mapper.populate_cognition(cognition)
            except Exception as e:
                logger.debug(f"Secondary event mapper failed: {e}")

    def start_background_scan(self):
        if self._primary is not None:
            self._primary.start_background_scan()

    def stop_background_scan(self):
        if self._primary is not None:
            self._primary.stop_background_scan()


def start_ha_event_stream() -> None:
    """Start the HA WebSocket event stream if configured.

    Called from dashboard startup. If HA is not configured, this is a no-op.
    """
    global _ha_event_stream
    if _ha_event_stream is not None:
        return
    try:
        from .home_assistant.ha_config import load_ha_config
        from .home_assistant.ha_event_stream import HAEventStream

        config = load_ha_config()
        if not config.is_configured():
            return

        mapper = get_ha_event_mapper()
        if mapper is None:
            return

        _ha_event_stream = HAEventStream(
            config=config,
            on_event=mapper.add_event,
        )
        logger.info("HA event stream created (start deferred to async context)")
    except Exception as e:
        logger.warning(f"Could not create HA event stream: {e}")


def shutdown():
    """Clean shutdown of background threads and trackers."""
    global _event_mapper, _cognition, _trackers, _ha_event_mapper, _ha_event_stream, _frigate_event_mapper
    if _event_mapper is not None:
        _event_mapper.stop_background_scan()
        _event_mapper = None
    _ha_event_mapper = None
    _ha_event_stream = None
    _frigate_event_mapper = None
    _cognition = None
    _trackers = None
    logger.info("Cognition wiring shut down")
