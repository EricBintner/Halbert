# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Occupancy Model — multi-signal presence correlation for the sentient home.

Correlates multiple signals into a unified occupancy model:
- Frigate face recognition (who is visible)
- Smart lock events (who entered with which PIN/key)
- Phone presence on WiFi (MAC addresses)
- Apple Watch proximity (Bluetooth)
- Car in driveway (Frigate object detection)

The model maintains a real-time view of who is present, with confidence
scores and evidence trails. Confidence increases when multiple signals
agree, decreases when they disagree.

Handles transitions gracefully:
- Person leaves → phone gone but watch still detected → probably in the
  garage → wait 5 min before marking away
- Person arrives → smart lock PIN + Frigate face → confirmed present

The cognitive loop reads this model to decide:
- Should the house enter away mode?
- Should it prepare for arrival?
- Should it suppress alerts because someone is home?
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.home.occupancy")

# Signal types
SIGNAL_FRIGATE_FACE = "frigate_face"
SIGNAL_SMART_LOCK = "smart_lock"
SIGNAL_WIFI_PRESENCE = "wifi_presence"
SIGNAL_BLUETOOTH_PROXIMITY = "bluetooth_proximity"
SIGNAL_CAR_DETECTION = "car_detection"

# Signal weights (how much each signal contributes to confidence)
SIGNAL_WEIGHTS: Dict[str, float] = {
    SIGNAL_FRIGATE_FACE: 0.35,
    SIGNAL_SMART_LOCK: 0.30,
    SIGNAL_WIFI_PRESENCE: 0.20,
    SIGNAL_BLUETOOTH_PROXIMITY: 0.10,
    SIGNAL_CAR_DETECTION: 0.05,
}

# How long before a signal is considered stale
SIGNAL_TTL_SECONDS: Dict[str, float] = {
    SIGNAL_FRIGATE_FACE: 300,      # 5 minutes
    SIGNAL_SMART_LOCK: 3600,       # 1 hour (lock event implies presence)
    SIGNAL_WIFI_PRESENCE: 120,     # 2 minutes (phone disconnects quickly)
    SIGNAL_BLUETOOTH_PROXIMITY: 60,  # 1 minute (BLE is real-time)
    SIGNAL_CAR_DETECTION: 600,     # 10 minutes
}

# Grace period before marking someone as away after all signals disappear
AWAY_GRACE_PERIOD_SECONDS = 300  # 5 minutes


@dataclass
class PresenceSignal:
    """A single signal contributing to the occupancy model."""
    signal_type: str
    person: str
    present: bool
    timestamp: float
    location: str = ""  # room, area, or zone
    confidence: float = 1.0
    detail: str = ""


@dataclass
class PersonPresence:
    """The occupancy model's view of a single person."""
    person: str
    present: bool
    confidence: float  # 0.0 to 1.0
    last_seen: float
    last_location: str = ""
    evidence: List[PresenceSignal] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "person": self.person,
            "present": self.present,
            "confidence": round(self.confidence, 2),
            "last_seen": self.last_seen,
            "last_seen_ago_seconds": time.time() - self.last_seen,
            "last_location": self.last_location,
            "evidence": [
                {
                    "signal_type": s.signal_type,
                    "present": s.present,
                    "timestamp": s.timestamp,
                    "location": s.location,
                    "confidence": s.confidence,
                    "detail": s.detail,
                }
                for s in self.evidence
            ],
        }


class OccupancyModel:
    """Multi-signal occupancy correlation.

    Thread-safe. Call update_signal() when a new signal arrives, and
    get_occupancy() to get the current model.

    Args:
        known_persons: List of known person names to track.
    """

    def __init__(self, known_persons: Optional[List[str]] = None) -> None:
        self.known_persons = known_persons or []
        self._signals: Dict[str, List[PresenceSignal]] = {}  # person -> signals
        self._lock = threading.Lock()
        self._away_timers: Dict[str, float] = {}  # person -> timestamp when away grace started

    def update_signal(self, signal: PresenceSignal) -> None:
        """Update the model with a new signal.

        Args:
            signal: The presence signal to incorporate.
        """
        with self._lock:
            person = signal.person
            if person not in self._signals:
                self._signals[person] = []

            # Remove stale signals of the same type for this person
            self._signals[person] = [
                s for s in self._signals[person]
                if s.signal_type != signal.signal_type
                or (time.time() - s.timestamp) < SIGNAL_TTL_SECONDS.get(s.signal_type, 300)
            ]

            # Add the new signal
            self._signals[person].append(signal)

            # If person is detected as present, clear the away timer
            if signal.present:
                self._away_timers.pop(person, None)

            logger.debug(
                f"Occupancy signal: {person} {signal.signal_type} "
                f"present={signal.present} confidence={signal.confidence}"
            )

    def get_occupancy(self) -> Dict[str, Any]:
        """Get the current occupancy model.

        Returns:
            Dict with:
                persons: List of PersonPresence dicts
                anyone_home: bool
                present_count: int
                confidence: float (overall confidence in the model)
        """
        with self._lock:
            now = time.time()
            persons: List[PersonPresence] = []

            for person, signals in self._signals.items():
                # Filter to non-stale signals
                active_signals = [
                    s for s in signals
                    if (now - s.timestamp) < SIGNAL_TTL_SECONDS.get(s.signal_type, 300)
                ]

                if not active_signals:
                    # All signals stale — check away grace period
                    away_start = self._away_timers.get(person)
                    if away_start is None:
                        # Just started the away grace period
                        self._away_timers[person] = now
                        present = True  # Still considered present during grace
                        confidence = 0.1
                    elif (now - away_start) < AWAY_GRACE_PERIOD_SECONDS:
                        present = True  # Still in grace period
                        confidence = 0.1
                    else:
                        present = False
                        confidence = 0.0
                else:
                    # Calculate weighted confidence
                    present_weight = 0.0
                    absent_weight = 0.0
                    last_seen = 0.0
                    last_location = ""

                    for s in active_signals:
                        weight = SIGNAL_WEIGHTS.get(s.signal_type, 0.1) * s.confidence
                        if s.present:
                            present_weight += weight
                            if s.timestamp > last_seen:
                                last_seen = s.timestamp
                                last_location = s.location
                        else:
                            absent_weight += weight

                    total_weight = present_weight + absent_weight
                    if total_weight > 0:
                        confidence = present_weight / total_weight
                    else:
                        confidence = 0.0

                    present = confidence > 0.5
                    self._away_timers.pop(person, None)

                persons.append(PersonPresence(
                    person=person,
                    present=present,
                    confidence=confidence,
                    last_seen=max((s.timestamp for s in active_signals), default=now),
                    last_location=last_location if active_signals else "",
                    evidence=active_signals,
                ))

            # Sort: present first, then by confidence
            persons.sort(key=lambda p: (not p.present, -p.confidence))

            present_count = sum(1 for p in persons if p.present)
            anyone_home = present_count > 0
            overall_confidence = (
                sum(p.confidence for p in persons) / len(persons)
                if persons else 0.0
            )

            return {
                "persons": [p.to_dict() for p in persons],
                "anyone_home": anyone_home,
                "present_count": present_count,
                "confidence": round(overall_confidence, 2),
                "timestamp": now,
            }

    def is_anyone_home(self) -> bool:
        """Quick check if anyone is home."""
        return self.get_occupancy()["anyone_home"]

    def is_person_home(self, person: str) -> bool:
        """Check if a specific person is home."""
        occupancy = self.get_occupancy()
        for p in occupancy["persons"]:
            if p["person"] == person:
                return p["present"]
        return False
