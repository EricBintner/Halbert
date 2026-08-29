# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for BehaviorStore + PatternInferrer."""

import os
import tempfile
import time
import pytest
from datetime import datetime
from halbert_core.home.behavior import (
    BehaviorStore,
    BehaviorPattern,
    PatternInferrer,
    PATTERN_DEVICE_USAGE,
    PATTERN_TIME_OF_DAY,
    PATTERN_OCCUPANCY,
)
from halbert_core.home.timeline import TimelineStore, TimelineEvent


@pytest.fixture
def behavior_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.unlink(db_path)
    store = BehaviorStore(db_path=db_path)
    yield store
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def timeline_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.unlink(db_path)
    store = TimelineStore(db_path=db_path)
    yield store
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestBehaviorStoreRecord:
    """Test recording patterns."""

    def test_record_occurrence(self, behavior_db):
        behavior_db.record_occurrence(
            pattern_type=PATTERN_DEVICE_USAGE,
            entity_id="light.kitchen",
            action="turn_on",
            day_of_week=0,
            hour=7,
            minute=15,
        )
        patterns = behavior_db.get_patterns()
        assert len(patterns) == 1
        assert patterns[0]["entity_id"] == "light.kitchen"
        assert patterns[0]["occurrence_count"] == 1

    def test_repeated_occurrence_increments_count(self, behavior_db):
        for _ in range(5):
            behavior_db.record_occurrence(
                pattern_type=PATTERN_DEVICE_USAGE,
                entity_id="light.kitchen",
                action="turn_on",
                hour=7,
                minute=15,
            )
        patterns = behavior_db.get_patterns()
        assert len(patterns) == 1
        assert patterns[0]["occurrence_count"] == 5
        assert patterns[0]["confidence"] > 0.3  # Increased from initial

    def test_different_times_create_different_patterns(self, behavior_db):
        behavior_db.record_occurrence(
            pattern_type=PATTERN_DEVICE_USAGE,
            entity_id="light.kitchen",
            action="turn_on",
            hour=7,
            minute=15,
        )
        behavior_db.record_occurrence(
            pattern_type=PATTERN_DEVICE_USAGE,
            entity_id="light.kitchen",
            action="turn_on",
            hour=18,
            minute=30,
        )
        patterns = behavior_db.get_patterns()
        assert len(patterns) == 2


class TestBehaviorStoreConfirmDismiss:
    """Test user feedback on patterns."""

    def test_confirm_boosts_confidence(self, behavior_db):
        behavior_db.record_occurrence(
            pattern_type=PATTERN_TIME_OF_DAY,
            entity_id="climate.thermostat",
            action="heat",
            hour=6,
            minute=30,
        )
        patterns = behavior_db.get_patterns()
        initial_conf = patterns[0]["confidence"]
        behavior_db.confirm_pattern(patterns[0]["id"])
        patterns = behavior_db.get_patterns()
        assert patterns[0]["confidence"] > initial_conf
        assert patterns[0]["confirmed"] == 1

    def test_dismiss_drops_confidence(self, behavior_db):
        behavior_db.record_occurrence(
            pattern_type=PATTERN_TIME_OF_DAY,
            entity_id="light.bedroom",
            action="turn_on",
            hour=23,
            minute=0,
        )
        patterns = behavior_db.get_patterns()
        behavior_db.dismiss_pattern(patterns[0]["id"])
        patterns = behavior_db.get_patterns(active_only=False)
        assert patterns[0]["dismissed"] == 1
        assert patterns[0]["confidence"] == 0

    def test_correction_reduces_confidence(self, behavior_db):
        behavior_db.record_occurrence(
            pattern_type=PATTERN_DEVICE_USAGE,
            entity_id="light.living_room",
            action="turn_on",
            hour=20,
            minute=0,
        )
        patterns = behavior_db.get_patterns()
        initial_conf = patterns[0]["confidence"]
        behavior_db.record_correction(patterns[0]["id"])
        patterns = behavior_db.get_patterns()
        assert patterns[0]["confidence"] < initial_conf


class TestBehaviorStoreDegrade:
    """Test stale pattern degradation."""

    def test_degrade_old_patterns(self, behavior_db):
        # Record a pattern with an old timestamp
        behavior_db.record_occurrence(
            pattern_type=PATTERN_TIME_OF_DAY,
            entity_id="light.garden",
            action="turn_on",
            hour=18,
            minute=0,
        )
        patterns = behavior_db.get_patterns()
        initial_conf = patterns[0]["confidence"]

        # Manually set last_occurrence to 2 weeks ago
        import sqlite3
        conn = sqlite3.connect(behavior_db.db_path)
        conn.execute(
            "UPDATE behavior_patterns SET last_occurrence = ? WHERE id = ?",
            (time.time() - 14 * 86400, patterns[0]["id"]),
        )
        conn.commit()
        conn.close()

        behavior_db.degrade_stale_patterns()
        patterns = behavior_db.get_patterns()
        assert patterns[0]["confidence"] < initial_conf


class TestPatternInferrer:
    """Test pattern inference from timeline."""

    def test_infer_from_timeline(self, timeline_db, behavior_db):
        # Record some HA state changes in the timeline
        now = time.time()
        for i in range(5):
            timeline_db.record(TimelineEvent(
                timestamp=now - i * 86400,  # 5 days
                event_type="ha_state_change",
                entity_id="light.kitchen",
                title="Kitchen light turned on",
                data={"new_state": "on"},
            ))

        inferrer = PatternInferrer(timeline_db, behavior_db)
        count = inferrer.infer_from_timeline(hours=168)
        assert count > 0

        patterns = behavior_db.get_patterns()
        assert len(patterns) > 0
        # Should have device usage and time-of-day patterns
        types = {p["pattern_type"] for p in patterns}
        assert PATTERN_DEVICE_USAGE in types or PATTERN_TIME_OF_DAY in types

    def test_predict_next(self, timeline_db, behavior_db):
        # Record a pattern that should fire 30 minutes from now
        now = datetime.now()
        future_hour = now.hour
        future_minute = ((now.minute // 15) * 15 + 30) % 60
        if future_minute < now.minute:
            future_hour = (future_hour + 1) % 24

        # Record events at the future time for the last 5 days
        from datetime import timedelta
        for i in range(5):
            event_time = now - timedelta(days=i)
            event_time = event_time.replace(hour=future_hour, minute=future_minute, second=0, microsecond=0)
            ts = event_time.timestamp()
            timeline_db.record(TimelineEvent(
                timestamp=ts,
                event_type="ha_state_change",
                entity_id="light.kitchen",
                title="Kitchen light on",
                data={"new_state": "on"},
            ))

        inferrer = PatternInferrer(timeline_db, behavior_db)
        inferrer.infer_from_timeline(hours=168)

        # Predict for the current time with a 120-minute lookahead
        predictions = inferrer.predict_next(
            current_day_of_week=now.weekday(),
            current_hour=now.hour,
            current_minute=now.minute,
            lookahead_minutes=120,
        )
        # Should have at least one prediction (the kitchen light pattern)
        assert len(predictions) > 0
        assert all("confidence" in p for p in predictions)
        assert all("minutes_until" in p for p in predictions)


class TestBehaviorStoreStats:
    """Test stats."""

    def test_stats_returns_counts(self, behavior_db):
        behavior_db.record_occurrence(
            pattern_type=PATTERN_DEVICE_USAGE,
            entity_id="light.1",
            action="on",
            hour=7,
        )
        behavior_db.record_occurrence(
            pattern_type=PATTERN_TIME_OF_DAY,
            entity_id="climate.1",
            action="heat",
            hour=6,
        )
        stats = behavior_db.stats()
        assert stats["total_patterns"] == 2
        assert stats["active_patterns"] == 2
        assert PATTERN_DEVICE_USAGE in stats["by_type"]
        assert PATTERN_TIME_OF_DAY in stats["by_type"]
