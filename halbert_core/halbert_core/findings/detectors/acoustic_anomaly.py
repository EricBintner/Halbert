# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Acoustic anomaly detector — creates findings from detected sound events.

This detector is called by the DetectorRunner when acoustic events are
detected by the audio pipeline. Unlike the config-brain detectors
(dropin_conflicts, fstab_phantom) which scan the filesystem, this detector
receives acoustic events from the audio pipeline coordinator and converts
them into Finding objects with the Four Whys framework.

The detector is registered in DetectorRunner.__init__ alongside the
existing detectors. Acoustic events are pushed to it by the pipeline
coordinator via ``add_event()``.

Phase 4 / T4.2.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import List, Optional

from ..store import Finding

logger = logging.getLogger(__name__)


# Severity mapping: audio tagger anomaly_severity (0-3) -> Finding severity
_SEVERITY_MAP = {
    0: "info",
    1: "warning",
    2: "warning",   # confirmed anomaly but not life-safety
    3: "critical",  # life-safety (smoke alarm, glass break, intrusion)
}

# Human-readable labels for common sound classes
_CLASS_LABELS = {
    "smoke_alarm": "Smoke detector alarm",
    "smoke_detector": "Smoke detector alarm",
    "fire_alarm": "Fire alarm",
    "glass_breaking": "Glass break",
    "glass_break": "Glass break",
    "burglar_alarm": "Burglar alarm",
    "car_alarm": "Car alarm",
    "alarm": "Alarm",
    "siren": "Siren / emergency vehicle",
    "water": "Water leak / running water",
    "water_leak": "Water leak",
    "water_running": "Running water",
    "mechanical_fan": "Mechanical fan noise",
    "bearing_friction": "Mechanical bearing friction / coil whine",
}


class AcousticAnomalyDetector:
    """Convert acoustic events from the audio pipeline into Findings.

    Unlike filesystem-scanning detectors, this detector receives events
    pushed from the audio pipeline coordinator. The ``add_event()`` method
    queues events; ``detect()`` drains the queue and creates Findings.

    Registered in DetectorRunner.__init__ alongside existing detectors.
    """

    def __init__(self):
        self._pending_events: List[dict] = []

    def add_event(
        self,
        sound_class: str,
        confidence: float,
        area_id: str = "",
        source: str = "",
        decibel_level: float = 0.0,
        anomaly_severity: int = 0,
        timestamp: float = 0.0,
    ) -> None:
        """Queue an acoustic event for the next detect() cycle.

        Called by the audio pipeline coordinator when an anomaly is detected.
        Thread-safe via the GIL (list.append is atomic).
        """
        self._pending_events.append({
            "sound_class": sound_class,
            "confidence": confidence,
            "area_id": area_id,
            "source": source,
            "decibel_level": decibel_level,
            "anomaly_severity": anomaly_severity,
            "timestamp": timestamp or time.time(),
        })

    def detect(self) -> List[Finding]:
        """Drain pending events and create Findings.

        Returns findings for all queued acoustic events. Each event becomes
        one Finding with the Four Whys framework.
        """
        events = self._pending_events[:]
        self._pending_events.clear()

        findings: List[Finding] = []
        for event in events:
            finding = self._event_to_finding(event)
            if finding:
                findings.append(finding)

        return findings

    def _event_to_finding(self, event: dict) -> Optional[Finding]:
        """Convert an acoustic event dict to a Finding."""
        sound_class = event["sound_class"]
        confidence = event["confidence"]
        area_id = event.get("area_id", "")
        source = event.get("source", "")
        db = event.get("decibel_level", 0.0)
        severity_num = event.get("anomaly_severity", 0)
        ts = event.get("timestamp", time.time())

        # Skip non-anomalies
        if severity_num == 0 and confidence < 0.5:
            return None

        severity = _SEVERITY_MAP.get(severity_num, "info")
        label = _CLASS_LABELS.get(sound_class, sound_class.replace("_", " ").title())
        location = f" in {area_id}" if area_id else ""
        source_str = f" via {source}" if source else ""

        # Generate a unique ID prefix for this event
        finding_id = ""

        # Four Whys
        why_now = (
            f"Acoustic anomaly detected at {time.strftime('%H:%M:%S', time.localtime(ts))}"
            f"{location}{source_str}: {label} at {confidence:.0%} confidence"
        )

        if severity_num >= 3:
            why_care = (
                f"This sound class ({label}) indicates a potential life-safety "
                f"emergency. Immediate attention required."
            )
        elif severity_num >= 2:
            why_care = (
                f"This sound class ({label}) may indicate a security or safety "
                f"issue. Investigation recommended."
            )
        else:
            why_care = (
                f"Unusual acoustic event ({label}) detected. May indicate "
                f"equipment malfunction or environmental change."
            )

        why_so = (
            f"The audio tagger classified a 1-second window with {confidence:.1%} "
            f"confidence as '{sound_class}'"
        )
        if db > 0:
            why_so += f" at {db:.0f}dB"
        why_so += f". Anomaly severity: {severity_num}/3."

        why_trust = [
            f"audio_tagger:{sound_class}:{confidence:.3f}",
            f"source:{source or 'unknown'}",
            f"area:{area_id or 'unknown'}",
            f"timestamp:{ts:.3f}",
        ]

        # Structured payload for the frontend AcousticAnomalyModule (O5).
        # Key names are that module's AcousticAnomalyData contract, verbatim;
        # timestamp is ISO-8601 because the module feeds it to ``new Date()``.
        # The DetectorRunner copies this onto the published ProactiveEvent.
        payload = {
            "sound_class": sound_class,
            "confidence": confidence,
            "area_id": area_id,
            "decibel_level": db,
            "anomaly_severity": severity_num,
            "source": source,
            "timestamp": datetime.fromtimestamp(ts).isoformat(),
        }

        return Finding(
            id=finding_id,
            detector="acoustic_anomaly",
            severity=severity,
            title=f"Acoustic anomaly: {label}{location}",
            description=(
                f"Detected {label} at {confidence:.0%} confidence{location}{source_str}."
            ),
            why_now=why_now,
            why_care=why_care,
            why_so=why_so,
            why_trust=why_trust,
            affected_paths=[],
            affected_services=[],
            data=payload,
        )
