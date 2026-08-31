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

# Multi-instance: ensure Haloysius memory tree follows HALBERT_DATA_DIR
# so persona memory stores are fully isolated per instance.
_hbt_data = os.environ.get("HALBERT_DATA_DIR") or os.environ.get("Halbert_DATA_DIR")
if _hbt_data and not os.environ.get("HALOYSIUS_DATA_HOME"):
    os.environ["HALOYSIUS_DATA_HOME"] = _hbt_data


def _get_persona_id() -> str:
    """Get the persona identity.

    Priority: BeingConfig.persona_id_override > HALBERT_PERSONA_ID env > 'halbert'.
    """
    # Try BeingConfig first (supports multi-instance via HALBERT_CONFIG_DIR)
    try:
        from ..config.being_config import load_being_config
        cfg = load_being_config()
        if cfg.persona_id_override:
            return cfg.persona_id_override
    except Exception:
        pass
    return os.environ.get("HALBERT_PERSONA_ID", "halbert")


def _get_scene_context() -> str:
    """Get the scene context.

    Priority: BeingConfig.scene_context > HALBERT_SCENE_CONTEXT env > platform default.
    """
    # Try BeingConfig first
    try:
        from ..config.being_config import load_being_config
        cfg = load_being_config()
        if cfg.scene_context:
            return cfg.scene_context
    except Exception:
        pass
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


def _get_body_name() -> str:
    """Get the body name — which physical body the entity is speaking from.

    Priority: BeingConfig.body_name > variant-based default.

    In singular entity mode, the prompt builder includes this so the entity
    knows where it is ("You are currently at your desk body"). In
    independent mode, it's a device label for logging/UI.
    """
    try:
        from ..config.being_config import load_being_config
        cfg = load_being_config()
        if cfg.body_name:
            return cfg.body_name
    except Exception:
        pass
    # Variant-based default
    if _get_variant() == "home":
        return "home"
    return "workstation"


def _get_canonical_memory_url() -> str:
    """Get the canonical memory URL for singular entity mode.

    Returns the URL of the canonical memory host, or empty string if
    this node uses local memory (independent entity mode).
    """
    try:
        from ..config.being_config import load_being_config
        cfg = load_being_config()
        return cfg.canonical_memory_url or ""
    except Exception:
        return ""


def _get_canonical_thread_url() -> str:
    """Get the canonical thread URL for singular entity mode.

    Returns the URL of the canonical thread host, or empty string if
    this node uses local threads (independent entity mode).
    """
    try:
        from ..config.being_config import load_being_config
        cfg = load_being_config()
        return cfg.canonical_thread_url or ""
    except Exception:
        return ""


def _get_peer_token() -> str:
    """Get the bearer token for authenticating to the canonical host.

    Priority: being.yml peer_token > HALBERT_PEER_TOKEN env var.
    Returns empty string if not configured.
    """
    try:
        from ..config.being_config import load_being_config
        cfg = load_being_config()
        token = cfg.peer_token or ""
        if token:
            return token
    except Exception:
        pass
    return os.environ.get("HALBERT_PEER_TOKEN", "")


def is_singular_entity_mode() -> bool:
    """True when this node is in singular entity mode (proxies memory to a canonical host).

    Singular mode means: shared persona_id + shared memory + shared threads
    = one entity with multiple bodies. Independent mode (current behavior)
    means each node has its own persona_id, memory, and threads.
    """
    return bool(_get_canonical_memory_url())


def _get_variant() -> str:
    """Get the instance variant.

    Priority: variant set in being.yml > HALBERT_VARIANT env > 'sysadmin'.

    Only an explicit being.yml ``variant:`` key wins — load_being_config
    fills in the 'sysadmin' default when the file or key is absent, which
    would otherwise mask the env var (explicit_variant distinguishes them).
    """
    try:
        from ..config.being_config import explicit_variant
        variant = explicit_variant()
        if variant:
            return variant
    except Exception:
        pass
    return os.environ.get("HALBERT_VARIANT", "sysadmin")


# Home automation variant. ``secure_model`` is a sysadmin-instance slot:
# an HA variant's LLM reaches the house through tool calls that abstract
# credentials away (HA's API layer holds the tokens, never the prompt), so
# home never configures, provisions, or resolves a dedicated
# secure model (handoff HOME-AUTOMATION-SIMPLIFICATION-2026-08-30, S1).
HA_VARIANTS = ("home",)


def is_home_variant() -> bool:
    """True when the active variant is a home automation variant.

    Resolution follows :func:`_get_variant` (being.yml > HALBERT_VARIANT
    env > 'sysadmin'), so gating here agrees with the per-variant service
    skips in dashboard/app.py rather than reading the env var directly.
    """
    return _get_variant() in HA_VARIANTS


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
    """Create a HaloysiusMemoryAdapter backed by a PersonaMemoryStore.

    This connects advance_turn's thought promotion to persistent memory.

    In singular entity mode (canonical_memory_url set in being.yml, P2c)
    the adapter is backed by a ``PeerMemoryBackend`` that proxies
    smart_add/search to the canonical HA server over the peer HTTP link,
    so both cognitions share one autobiography. Otherwise, a local
    ``PersonaMemoryStore`` as before.
    """
    try:
        from .haloysius_memory_adapter import HaloysiusMemoryAdapter

        store = _create_memory_store()
        adapter = HaloysiusMemoryAdapter(store)
        logger.info(
            "Created HaloysiusMemoryAdapter for %s (%s)",
            _get_persona_id(),
            "peer-backed" if _get_canonical_memory_url() else "local",
        )
        return adapter
    except Exception as e:
        logger.warning(f"Could not create memory adapter: {e}")
        return None


def _create_memory_store():
    """Create the memory store based on singular entity config (P2c).

    When ``canonical_memory_url`` is set in being.yml, returns a
    ``PeerMemoryBackend`` that proxies to the canonical host. Otherwise,
    a local ``PersonaMemoryStore``. Falls back to the local store when
    the peer token is missing or the backend cannot be imported — a
    cognition tick with local memory beats no cognition at all.
    """
    canonical_memory_url = _get_canonical_memory_url()
    if canonical_memory_url:
        try:
            from haloysius.memory_v2.peer_backend import PeerMemoryBackend

            token = _get_peer_token()
            if not token:
                logger.warning(
                    "canonical_memory_url is set but no peer_token configured "
                    "— falling back to local PersonaMemoryStore"
                )
            else:
                logger.info(
                    "Memory adapter: using PeerMemoryBackend at %s",
                    canonical_memory_url,
                )
                return PeerMemoryBackend(
                    peer_url=canonical_memory_url,
                    bearer_token=token,
                )
        except ImportError as e:
            logger.warning(
                f"Failed to import PeerMemoryBackend (falling back to local): {e}"
            )

    from haloysius.memory_v2.store import PersonaMemoryStore

    return PersonaMemoryStore(_get_persona_id())


def _ensure_app_seam_wired() -> None:
    """Register the Halbert AppSeam if nothing is registered yet (guarded).

    routes/agent.py calls get_cognition_tick() before get_event_mapper(),
    so the seam must be wired here for the thought generator to find it.

    Capability-based: skip SourcePrep retrieval if the sourceprep
    capability is not available. The variant preset sets defaults
    (home = no sourceprep), but being.yml can override.
    """
    try:
        from haloysius.seam import get_app_seam

        if get_app_seam() is None:
            from . import app_seam

            # Use capability registry instead of hard variant gate
            try:
                from ..capabilities import has_capability, CAP_SOURCEPREP
                skip_retrieval = not has_capability(CAP_SOURCEPREP)
            except Exception:
                # Fallback to variant gate if capabilities module unavailable
                skip_retrieval = is_home_variant()

            app_seam.wire_halbert_seam(skip_retrieval=skip_retrieval)
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

        # Wrap in composite with HA and Frigate event mappers if available.
        # Both are optional (HA/Frigate may not be configured); the composite
        # filters None entries. Without this wiring the HA event stream feeds
        # the mapper but populate_cognition() is never called on it, so the
        # persona never learns from the house and the pending-event queue
        # grows without bound (REV-03 F1).
        secondary_mappers = []
        ha_mapper = get_ha_event_mapper()
        if ha_mapper is not None:
            secondary_mappers.append(ha_mapper)
            logger.info("HA event mapper added to composite")
        frigate_mapper = get_frigate_event_mapper()
        if frigate_mapper is not None:
            secondary_mappers.append(frigate_mapper)
            logger.info("Frigate event mapper added to composite")
        if secondary_mappers:
            _event_mapper = CompositeEventMapper(
                primary=_event_mapper,
                secondary_mappers=secondary_mappers,
            )
            logger.info(
                f"Event mapper wrapped with composite "
                f"({len(secondary_mappers)} secondary)"
            )

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
