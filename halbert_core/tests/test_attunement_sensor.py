# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The situation sensor (A-HB-12, A-HB-19, Phase D step 1-3).

Halbert can feed thirteen of the engine's fourteen receptivity rows; this is
where they come from. The tests pin the two things the engine cannot know:
that departure is only observable at the transition, and that a label derived
from a camera must be marked as such so it is never persisted.
"""

from datetime import datetime, timedelta, timezone

import pytest

from halbert_core.agents.states import AgentState
from halbert_core.attunement.operation_state import operation_state
from halbert_core.attunement.sensor import (
    TRANSITION_WINDOW_S,
    Activity,
    SignalProvenance,
    build_signals,
)


def _ago(seconds):
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def test_no_inputs_yields_unknown_not_a_guess():
    """The engine treats 'no signals' as MODERATE. It must not receive a
    fabricated activity instead."""
    s = build_signals()
    assert s.activity is Activity.UNKNOWN
    assert s.activity_confidence == 0.0
    assert s.others_present is None


def test_a_recent_arrival_is_arriving():
    s = build_signals(last_transition=("arrival", _ago(30)))
    assert s.activity is Activity.ARRIVING
    assert s.activity_since is not None
    assert s.activity_provenance is SignalProvenance.SENSOR


def test_a_recent_departure_is_departing():
    s = build_signals(last_transition=("departure", _ago(30)))
    assert s.activity is Activity.DEPARTING


def test_a_stale_departure_is_away_not_departing():
    """A-HB-12. The occupancy model needs 300s of silence before it will call
    anyone away, so by the time it does, 'a bad moment to interrupt' is the
    wrong reading — there is nobody to interrupt."""
    s = build_signals(last_transition=("departure", _ago(TRANSITION_WINDOW_S + 60)))
    assert s.activity is Activity.AWAY


def test_a_stale_arrival_is_not_still_arriving():
    """The 96% figure is a moment, not a mood."""
    s = build_signals(last_transition=("arrival", _ago(TRANSITION_WINDOW_S + 60)))
    assert s.activity is not Activity.ARRIVING


def test_idle_beyond_the_tier_one_threshold_is_idle():
    s = build_signals(idle_seconds=45)
    assert s.activity is Activity.IDLE
    assert s.activity_provenance is SignalProvenance.DERIVED


def test_active_at_the_keyboard_is_not_idle():
    s = build_signals(idle_seconds=2)
    assert s.activity is not Activity.IDLE


def test_a_transition_outranks_idle():
    """Someone who just walked in is arriving, even if the desktop has been
    untouched for an hour."""
    s = build_signals(idle_seconds=3600, last_transition=("arrival", _ago(10)))
    assert s.activity is Activity.ARRIVING


def test_operation_state_populates_the_four_engine_fields():
    op = operation_state(agent_state=AgentState.AWAITING_CONFIRMATION,
                         safe_mode_active=True)
    s = build_signals(operation=op)
    assert s.awaiting_user_confirmation is True
    assert s.operation_in_progress is True
    assert s.incident_active is True
    assert s.destructive_turn is False


def test_others_present_from_the_occupancy_model():
    occupancy = {"persons": [{"person": "eric", "present": True},
                             {"person": "sam", "present": True}],
                 "anyone_home": True, "present_count": 2}
    assert build_signals(occupancy=occupancy).others_present is True


def test_one_person_home_is_not_others_present():
    occupancy = {"persons": [{"person": "eric", "present": True}],
                 "anyone_home": True, "present_count": 1}
    assert build_signals(occupancy=occupancy).others_present is False


def test_a_vision_derived_activity_is_marked_as_vision():
    """A-HB-19. An activity enum at a timestamp is still a fact about a
    person's home; the store drops labels whose provenance is not persistable,
    and it can only do that if we say where the label came from."""
    s = build_signals(vision_activity=(Activity.FOCUSED_WORK, 0.8))
    assert s.activity is Activity.FOCUSED_WORK
    assert s.activity_provenance is SignalProvenance.VISION


def test_a_sensor_transition_outranks_a_vision_guess():
    s = build_signals(vision_activity=(Activity.FOCUSED_WORK, 0.9),
                      last_transition=("arrival", _ago(10)))
    assert s.activity is Activity.ARRIVING
    assert s.activity_provenance is SignalProvenance.SENSOR


def test_addressed_to_persona_is_tri_state():
    """A-HB-14. No wake-word model installed means unknown, never False."""
    assert build_signals().addressed_to_persona is None
    assert build_signals(addressed_to_persona=True).addressed_to_persona is True
    assert build_signals(addressed_to_persona=False).addressed_to_persona is False


def test_verbal_channel_carries_its_confidence():
    """Our tagger cannot separate a person from a television, so the engine
    must be able to scale the delta rather than take -0.50 on faith."""
    s = build_signals(verbal_channel_busy=(True, 0.45))
    assert s.verbal_channel_busy is True
    assert s.verbal_channel_confidence == pytest.approx(0.45)


def test_area_and_observation_time_are_carried():
    s = build_signals(area_id="kitchen")
    assert s.area_id == "kitchen"
    assert s.observed_at is not None


def test_freshness_horizon_reflects_the_signal_that_set_the_activity():
    """Per-signal staleness, not a flat ten minutes: a BLE reading 90s old is
    stale, a smart-lock event 90s old is fresh."""
    ble = build_signals(last_transition=("arrival", _ago(10)),
                        transition_signal_type="bluetooth_proximity")
    lock = build_signals(last_transition=("arrival", _ago(10)),
                         transition_signal_type="smart_lock")
    assert ble.freshness_horizon_s < lock.freshness_horizon_s
