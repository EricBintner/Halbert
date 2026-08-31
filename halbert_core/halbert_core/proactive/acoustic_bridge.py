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
own ad-hoc ``DetectorRunner`` instances; this bridge holds ONE long-lived
runner so pushed events are drained immediately (an urgent anomaly must wake
the screen now, not at the next sweep) while sharing the FindingStore (and
therefore the dedup + snooze semantics) with those sweeps.

Everything here is optional: the runner is built lazily on the first acoustic
event, and if the findings stack cannot be constructed the event is dropped
with a single warning (warning-once, the O3 ``_egress_log_once`` pattern) —
never a raise into the audio pipeline, never a boot failure.

Voice Mode Phase 2 / O5.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, List, Optional

from .events import ProactiveEvent

if TYPE_CHECKING:
    from ..audio.pipeline import AcousticEventObservation

logger = logging.getLogger(__name__)

# Signature of the lazy DetectorRunner constructor (injected in tests).
_RunnerFactory = Callable[[], "object"]


class AcousticAnomalyBridge:
    """Feeds coordinator acoustic observations into the findings chain.

    Holds one lazily-built DetectorRunner for the life of the process. The
    runner is ONLY built when a sound event actually arrives — a dashboard
    without a working findings stack must boot (and stream audio) normally.
    """

    def __init__(self, runner_factory: Optional[_RunnerFactory] = None):
        self._runner = None
        self._runner_factory: _RunnerFactory = runner_factory or self._default_runner
        self._warned: set = set()

    @staticmethod
    def _default_runner():
        from .detector_runner import DetectorRunner

        return DetectorRunner()

    def _get_runner(self):
        """Return the cached runner, building it on first use.

        Construction failure is warning-once (the site, not the event, is the
        wiring problem worth an operator's attention); the failed attempt is
        NOT cached, so a transient failure (locked SQLite, partial config)
        recovers on the next event.
        """
        if self._runner is None:
            try:
                self._runner = self._runner_factory()
            except Exception as e:
                self._log_once(
                    "runner_init",
                    f"DetectorRunner unavailable — acoustic events dropped: {e}",
                )
                return None
        return self._runner

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
        unavailable — the no-op path). Never raises.
        """
        runner = self._get_runner()
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

        try:
            return await runner.run_acoustic()
        except Exception as e:
            self._log_once("run_acoustic", f"Acoustic detector sweep failed: {e}")
            return []


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
