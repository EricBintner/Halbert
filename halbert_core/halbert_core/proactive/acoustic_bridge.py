# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Acoustic anomaly bridge — audio pipeline -> findings -> proactive SSE.

The third link of the O5 chain. The audio pipeline coordinator has emitted
``AcousticEventObservation`` via its ``on_acoustic_event`` callback since the
ambient track was built, and ``AcousticAnomalyDetector`` has accepted events
via ``add_event()`` since Phase 4 — but nothing connected them, so a tagged
anomaly (smoke alarm, glass break, ...) never became a proactive event and
never reached ``/api/being/events``.

This module owns that connection:

    coordinator.on_acoustic_event  ->  AcousticAnomalyBridge.handle
        ->  AcousticAnomalyDetector.add_event(...)      (queued)
        ->  DetectorRunner.run_acoustic()               (drain, dedup, store)
        ->  ProactiveGate -> ProactiveEventBus.publish  (type "finding",
                                                         category "acoustic",
                                                         structured data)
        ->  GET /api/being/events SSE -> useBeingEvents -> timeline/badge

The scheduled 6-hour detector sweep and the config-watcher sweep keep their
own ad-hoc ``DetectorRunner`` instances; this bridge builds a fresh runner
PER EVENT (events are rare — energy-floor gated and deduped; the sweeps
already rebuild per run, so this matches their pattern). Per-event
construction also means the gate never acts on a stale BeingConfig snapshot
from boot time, and dedup semantics survive because they live in the shared
FindingStore database, not the runner object.

Everything here is optional: the runner is only built when a sound event
actually arrives, and if the findings stack cannot be constructed the event
is dropped with a single warning (warning-once, the O3 ``_egress_log_once``
pattern) — never a raise into the audio pipeline, never a boot failure.

Voice Mode Phase 2 / O5.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, List, Optional

from ..continuity.ownership import Owner
from .events import ProactiveEvent

#: Tagger severity at which an acoustic anomaly is "confirmed" — glass break,
#: intrusion. ``ProactiveGate._is_wake_worthy_acoustic`` treats these exactly
#: like the engine's life-safety set, and so does the ownership gate below:
#: a confirmed anomaly on a private microphone still reaches Halbert (D1).
CONFIRMED_ANOMALY = 2

if TYPE_CHECKING:
    from ..audio.pipeline import AcousticEventObservation

logger = logging.getLogger(__name__)

# Signature of the per-event DetectorRunner constructor (injected in tests).
_RunnerFactory = Callable[[], "object"]


class AcousticAnomalyBridge:
    """Feeds coordinator acoustic observations into the findings chain.

    Builds a DetectorRunner per acoustic event (see module docstring); a
    dashboard without a working findings stack must boot (and stream audio)
    normally.
    """

    def __init__(self, runner_factory: Optional[_RunnerFactory] = None):
        self._runner_factory: _RunnerFactory = runner_factory or self._default_runner
        self._warned: set = set()

    @staticmethod
    def _default_runner():
        from .detector_runner import DetectorRunner

        return DetectorRunner()

    def _build_runner(self):
        """Build a fresh DetectorRunner for this event, or None on failure.

        Construction failure is warning-once (the site, not the event, is
        the wiring problem worth an operator's attention); the next event
        simply tries again, so a transient failure (locked SQLite, partial
        config) recovers by itself.
        """
        try:
            return self._runner_factory()
        except Exception as e:
            self._log_once(
                "runner_init",
                f"DetectorRunner unavailable — acoustic events dropped: {e}",
            )
            return None

    def _log_once(self, site: str, message: str) -> None:
        """Warn once per failure site, then drop to debug (O3 pattern)."""
        if site in self._warned:
            logger.debug(message)
            return
        self._warned.add(site)
        logger.warning(message)

    async def handle(
        self, observation: "AcousticEventObservation"
    ) -> List[ProactiveEvent]:
        """Coordinator ``on_acoustic_event`` callback (O5 wiring point).

        Maps the observation onto ``AcousticAnomalyDetector.add_event``'s
        field names verbatim, then drains just the acoustic detector. Returns
        the events that passed the gate (empty when the findings stack is
        unavailable — the no-op path). Never raises: ``run_acoustic`` cannot
        throw (``DetectorRunner._run_detector`` swallows every detector
        failure into a warning-once log line).
        """
        # Ownership (design §5.3): a microphone the user handed to a guest
        # for a private session is the guest's. Its acoustic events go to the
        # guest's home and touch none of Halbert's stores — not the detector,
        # not findings, not the event bus. Life safety is the exception (D1):
        # the house is not private from its own smoke alarm, and a confirmed
        # anomaly is what this gate already treats as life safety everywhere
        # else (``ProactiveGate._is_wake_worthy_acoustic``).
        owner, source_id = self._route(observation)
        if owner is not Owner.HALBERT:
            if owner is Owner.GUEST:
                self._forward_to_guest(observation, source_id)
            return []

        runner = self._build_runner()
        detector = getattr(runner, "acoustic_detector", None)
        if runner is None or detector is None:
            self._log_once(
                "no_detector",
                "AcousticAnomalyDetector absent — acoustic events dropped",
            )
            return []

        try:
            detector.add_event(
                sound_class=observation.sound_class,
                confidence=observation.confidence,
                area_id=observation.area_id or "",
                source=observation.source or "",
                decibel_level=observation.decibel_level,
                anomaly_severity=observation.anomaly_severity,
                timestamp=observation.timestamp,
            )
        except Exception as e:
            self._log_once("add_event", f"Acoustic add_event failed: {e}")
            return []

        return await runner.run_acoustic()


    @staticmethod
    def _route(observation) -> "tuple[Owner, str]":
        """Who this event belongs to, and the id to label a forward with.

        The window was classified from the shared ring buffer, so it names
        every live ear rather than one (``AudioPipelineCoordinator.
        live_source_ids``). ``route_mixed_observation`` drops a window whose
        ears disagree about their owner instead of guessing.
        """
        ids = list(getattr(observation, "source_ids", None) or [])
        life_safety = int(getattr(observation, "anomaly_severity", 0) or 0) >= CONFIRMED_ANOMALY
        try:
            from ..continuity.ownership import route_mixed_observation
            owner = route_mixed_observation(ids, life_safety=life_safety)
        except Exception:
            owner = Owner.HALBERT
        return owner, (ids[0] if len(ids) == 1 else "mic")

    def _forward_to_guest(self, observation, source_id: str) -> None:
        try:
            from ..persona import sibling
            from ..persona.guest import current_guest
            session = current_guest()
            if session is None:
                return
            sound = getattr(observation, "sound_class", "") or "a sound"
            area = getattr(observation, "area_id", "") or ""
            where = f" in {area}" if area else ""
            sibling.forward_observation(
                session, f"[{source_id}] heard {sound}{where}", source_id,
            )
        except Exception as e:
            self._log_once("forward", f"Private-microphone event not forwarded: {e}")


# ---------------------------------------------------------------------------
# Module-level singleton (the get_event_bus / get_tts_egress_hub pattern)
# ---------------------------------------------------------------------------

_bridge: Optional[AcousticAnomalyBridge] = None


def get_acoustic_bridge() -> AcousticAnomalyBridge:
    """Get the global bridge singleton."""
    global _bridge
    if _bridge is None:
        _bridge = AcousticAnomalyBridge()
    return _bridge


def reset_acoustic_bridge() -> None:
    """Drop the singleton (test isolation)."""
    global _bridge
    _bridge = None


def attach_acoustic_bridge(
    coordinator,
    bridge: Optional[AcousticAnomalyBridge] = None,
) -> AcousticAnomalyBridge:
    """Set ``coordinator.on_acoustic_event`` to the bridge handler.

    Called from the dashboard bootstrap (O2's startup) once the coordinator
    has started. Never builds the DetectorRunner — that waits for the first
    real acoustic event. Idempotent: attaching twice just re-points the
    callback at the (same) singleton.
    """
    b = bridge or get_acoustic_bridge()
    coordinator.on_acoustic_event = b.handle
    logger.info("Acoustic anomaly bridge attached to the audio pipeline")
    return b
