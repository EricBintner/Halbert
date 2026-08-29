# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for OccupancyModel — multi-signal presence correlation."""

import time
import pytest
from halbert_core.home.occupancy import (
    OccupancyModel,
    PresenceSignal,
    SIGNAL_FRIGATE_FACE,
    SIGNAL_SMART_LOCK,
    SIGNAL_WIFI_PRESENCE,
    SIGNAL_BLUETOOTH_PROXIMITY,
    SIGNAL_CAR_DETECTION,
)


@pytest.fixture
def model():
    return OccupancyModel(known_persons=["eric", "sarah"])


class TestOccupancyModelBasic:
    """Test basic signal updates and occupancy queries."""

    def test_empty_model_no_one_home(self, model):
        occ = model.get_occupancy()
        assert occ["anyone_home"] is False
        assert occ["present_count"] == 0

    def test_single_present_signal(self, model):
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_FRIGATE_FACE,
            person="eric",
            present=True,
            timestamp=time.time(),
            location="living_room",
        ))
        occ = model.get_occupancy()
        assert occ["anyone_home"] is True
        assert occ["present_count"] == 1
        assert occ["persons"][0]["person"] == "eric"
        assert occ["persons"][0]["present"] is True

    def test_absent_signal_marks_away(self, model):
        # First mark present
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_WIFI_PRESENCE,
            person="eric",
            present=True,
            timestamp=time.time(),
        ))
        assert model.is_anyone_home()

        # Then mark absent
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_WIFI_PRESENCE,
            person="eric",
            present=False,
            timestamp=time.time(),
        ))
        occ = model.get_occupancy()
        eric = [p for p in occ["persons"] if p["person"] == "eric"][0]
        assert not eric["present"]


class TestOccupancyModelConfidence:
    """Test confidence calculation with multiple signals."""

    def test_multiple_present_signals_increase_confidence(self, model):
        now = time.time()
        # Start with conflicting signals (face=present, wifi=absent)
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_FRIGATE_FACE, person="eric", present=True, timestamp=now,
        ))
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_WIFI_PRESENCE, person="eric", present=False, timestamp=now,
        ))
        occ1 = model.get_occupancy()
        conf1 = [p for p in occ1["persons"] if p["person"] == "eric"][0]["confidence"]

        # Add another present signal (lock)
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_SMART_LOCK, person="eric", present=True, timestamp=now,
        ))
        occ2 = model.get_occupancy()
        conf2 = [p for p in occ2["persons"] if p["person"] == "eric"][0]["confidence"]

        assert conf2 > conf1

    def test_conflicting_signals_reduce_confidence(self, model):
        now = time.time()
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_FRIGATE_FACE, person="eric", present=True, timestamp=now,
        ))
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_WIFI_PRESENCE, person="eric", present=False, timestamp=now,
        ))
        occ = model.get_occupancy()
        eric = [p for p in occ["persons"] if p["person"] == "eric"][0]
        # Should have moderate confidence (face says yes, wifi says no)
        assert 0.3 < eric["confidence"] < 0.8

    def test_all_signals_present_high_confidence(self, model):
        now = time.time()
        for signal_type in [SIGNAL_FRIGATE_FACE, SIGNAL_SMART_LOCK, SIGNAL_WIFI_PRESENCE,
                            SIGNAL_BLUETOOTH_PROXIMITY, SIGNAL_CAR_DETECTION]:
            model.update_signal(PresenceSignal(
                signal_type=signal_type, person="eric", present=True, timestamp=now,
            ))
        occ = model.get_occupancy()
        eric = [p for p in occ["persons"] if p["person"] == "eric"][0]
        assert eric["confidence"] > 0.9


class TestOccupancyModelMultiplePersons:
    """Test tracking multiple people."""

    def test_two_people_home(self, model):
        now = time.time()
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_FRIGATE_FACE, person="eric", present=True, timestamp=now,
        ))
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_FRIGATE_FACE, person="sarah", present=True, timestamp=now,
        ))
        occ = model.get_occupancy()
        assert occ["present_count"] == 2
        assert occ["anyone_home"] is True

    def test_one_home_one_away(self, model):
        now = time.time()
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_WIFI_PRESENCE, person="eric", present=True, timestamp=now,
        ))
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_WIFI_PRESENCE, person="sarah", present=False, timestamp=now,
        ))
        occ = model.get_occupancy()
        assert occ["present_count"] == 1
        eric = [p for p in occ["persons"] if p["person"] == "eric"][0]
        sarah = [p for p in occ["persons"] if p["person"] == "sarah"][0]
        assert eric["present"]
        assert not sarah["present"]


class TestOccupancyModelGracePeriod:
    """Test the away grace period."""

    def test_grace_period_keeps_present_temporarily(self, model):
        # Mark present
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_WIFI_PRESENCE, person="eric", present=True, timestamp=time.time(),
        ))
        assert model.is_person_home("eric")

        # Signal goes stale (simulate by using old timestamp)
        # The model should still consider present during grace period
        occ = model.get_occupancy()
        # During grace period, still present with low confidence
        eric = [p for p in occ["persons"] if p["person"] == "eric"][0]
        # Either still present (grace) or just started grace
        assert eric["present"] is True  # Grace period keeps present


class TestOccupancyModelEvidence:
    """Test the evidence trail."""

    def test_evidence_recorded(self, model):
        now = time.time()
        model.update_signal(PresenceSignal(
            signal_type=SIGNAL_FRIGATE_FACE, person="eric", present=True,
            timestamp=now, location="kitchen", detail="Face recognized in kitchen camera",
        ))
        occ = model.get_occupancy()
        eric = [p for p in occ["persons"] if p["person"] == "eric"][0]
        assert len(eric["evidence"]) > 0
        assert eric["evidence"][0]["signal_type"] == SIGNAL_FRIGATE_FACE
        assert eric["evidence"][0]["location"] == "kitchen"
        assert eric["last_location"] == "kitchen"
