# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert's situation sensor — the thirteen rows we can feed.

Fuses what the product already observes into the engine's ``SituationSignals``
shape: occupancy transitions, the desktop idle report, the persona's own
operational posture, the acoustic tagger, the wake word, and (last, opt-in)
vision.

Two things here the engine cannot know:

* **Departure is only observable at the transition** (A-HB-12).
  ``OccupancyModel`` needs ``AWAY_GRACE_PERIOD_SECONDS`` of silence before it
  will call anyone away, so a departure older than that window is not "a bad
  moment to interrupt" — it is *nobody to interrupt*, which is a different
  reading with a different resume condition.
* **Where a label came from** (A-HB-19). An activity enum at a timestamp is
  still a fact about a person's home. The store drops labels whose provenance
  is not persistable, and it can only do that if the sensor says.

``build_signals`` is pure — it takes resolved values, not live objects — so it
is cheap on the always-on path and testable without a house.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from .operation_state import OperationState

#: A transition is only a transition for this long. Chosen to equal
#: ``home.occupancy.AWAY_GRACE_PERIOD_SECONDS``: past it the occupancy model
#: itself stops claiming presence, so DEPARTING would be describing a person
#: who left five minutes ago.
TRANSITION_WINDOW_S = 300

#: Matches ``system/display_power.TIER1_IDLE_SECONDS`` — the threshold the
#: frontend already reports against.
IDLE_THRESHOLD_S = 30

#: Per-signal freshness, from ``home.occupancy.SIGNAL_TTL_SECONDS``. A flat
#: ten-minute staleness rule is too coarse for sources that span 60s to an
#: hour.
SIGNAL_FRESHNESS_S: Dict[str, float] = {
    "bluetooth_proximity": 60.0,
    "wifi_presence": 120.0,
    "frigate_face": 300.0,
    "car_detection": 600.0,
    "smart_lock": 3600.0,
}
DEFAULT_FRESHNESS_S = 600.0


class Activity(str, Enum):
    """Mirror of the engine's ``Activity``. Values must stay identical."""

    UNKNOWN = "unknown"
    IDLE = "idle"
    TRANSITION = "transition"
    ARRIVING = "arriving"
    DEPARTING = "departing"
    AWAY = "away"
    CHORES = "chores"
    MEDIA = "media"
    RESTING = "resting"
    SLEEPING = "sleeping"
    FOCUSED_WORK = "focused_work"
    CONVERSATION = "conversation"
    ON_CALL = "on_call"
    DRIVING = "driving"


class SignalProvenance(str, Enum):
    """Mirror of the engine's ``SignalProvenance``."""

    SENSOR = "sensor"
    VISION = "vision"
    AUDIO = "audio"
    DERIVED = "derived"
    STATED = "stated"


@dataclass(frozen=True)
class SituationSnapshot:
    """Halbert's view of the moment, in the engine's field shape.

    Declared locally so the sensor is testable with the engine absent;
    :meth:`to_engine` builds the real type when it is importable.
    """

    activity: Activity = Activity.UNKNOWN
    activity_confidence: float = 0.0
    activity_provenance: Optional[SignalProvenance] = None
    activity_since: Optional[str] = None
    others_present: Optional[bool] = None
    verbal_channel_busy: Optional[bool] = None
    verbal_channel_confidence: float = 1.0
    addressed_to_persona: Optional[bool] = None
    calendar_busy: Optional[bool] = None
    is_hands_free: Optional[bool] = None
    operation_in_progress: Optional[bool] = None
    awaiting_user_confirmation: Optional[bool] = None
    destructive_turn: Optional[bool] = None
    incident_active: Optional[bool] = None
    area_id: Optional[str] = None
    observed_at: Optional[str] = None
    freshness_horizon_s: float = DEFAULT_FRESHNESS_S

    def to_engine(self) -> Any:
        """Build ``haloysius.attunement.types.SituationSignals``.

        Returns None when the engine is not installed, which every caller
        treats as "no sensor registered".
        """
        try:
            from haloysius.attunement.types import SituationSignals
        except ImportError:
            return None
        return SituationSignals(**{
            **{k: v for k, v in self.__dict__.items()},
        })


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _age_seconds(when: datetime, now: datetime) -> float:
    return (now - when).total_seconds()


def build_signals(
    *,
    occupancy: Optional[Dict[str, Any]] = None,
    last_transition: Optional[Tuple[str, datetime]] = None,
    transition_signal_type: Optional[str] = None,
    idle_seconds: Optional[float] = None,
    operation: Optional[OperationState] = None,
    vision_activity: Optional[Tuple[Activity, float]] = None,
    verbal_channel_busy: Optional[Tuple[bool, float]] = None,
    addressed_to_persona: Optional[bool] = None,
    calendar_busy: Optional[bool] = None,
    is_hands_free: Optional[bool] = None,
    area_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> SituationSnapshot:
    """Fuse Halbert's observations into one snapshot.

    Precedence for ``activity``, strongest evidence first:

    1. A presence transition inside the window — a sensor saw a person move.
    2. A vision-derived class — a model's opinion about a frame.
    3. Desktop idle — cheap, reliable, but only about the keyboard.

    Everything else rides alongside as its own field.
    """
    now = now or datetime.now(timezone.utc)

    activity = Activity.UNKNOWN
    confidence = 0.0
    provenance: Optional[SignalProvenance] = None
    activity_since: Optional[str] = None
    freshness = DEFAULT_FRESHNESS_S

    # 1. Presence transitions.
    if last_transition is not None:
        direction, when = last_transition
        age = _age_seconds(when, now)
        activity_since = _iso(when)
        freshness = SIGNAL_FRESHNESS_S.get(
            (transition_signal_type or "").lower(), DEFAULT_FRESHNESS_S
        )
        if age <= TRANSITION_WINDOW_S:
            activity = (
                Activity.ARRIVING if direction == "arrival" else Activity.DEPARTING
            )
            confidence = 1.0
            provenance = SignalProvenance.SENSOR
        elif direction == "departure":
            # A-HB-12: past the window this is not a bad moment, it is nobody.
            activity = Activity.AWAY
            confidence = 1.0
            provenance = SignalProvenance.SENSOR

    # 2. Vision, when nothing stronger spoke.
    if activity is Activity.UNKNOWN and vision_activity is not None:
        activity, confidence = vision_activity
        provenance = SignalProvenance.VISION

    # 3. The desktop idle report.
    if (
        activity is Activity.UNKNOWN
        and idle_seconds is not None
        and idle_seconds >= IDLE_THRESHOLD_S
    ):
        activity = Activity.IDLE
        confidence = 1.0
        provenance = SignalProvenance.DERIVED

    others_present: Optional[bool] = None
    if occupancy is not None:
        present = occupancy.get("present_count")
        if present is None:
            present = sum(
                1 for p in occupancy.get("persons", []) if p.get("present")
            )
        others_present = bool(present > 1)

    busy: Optional[bool] = None
    busy_confidence = 1.0
    if verbal_channel_busy is not None:
        busy, busy_confidence = verbal_channel_busy

    return SituationSnapshot(
        activity=activity,
        activity_confidence=confidence,
        activity_provenance=provenance,
        activity_since=activity_since,
        others_present=others_present,
        verbal_channel_busy=busy,
        verbal_channel_confidence=busy_confidence,
        addressed_to_persona=addressed_to_persona,
        calendar_busy=calendar_busy,
        is_hands_free=is_hands_free,
        operation_in_progress=(
            operation.operation_in_progress if operation is not None else None
        ),
        awaiting_user_confirmation=(
            operation.awaiting_user_confirmation if operation is not None else None
        ),
        destructive_turn=(
            operation.destructive_turn if operation is not None else None
        ),
        incident_active=(
            operation.incident_active if operation is not None else None
        ),
        area_id=area_id,
        observed_at=_iso(now),
        freshness_horizon_s=freshness,
    )
