# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for TimelineStore — the persistent event ledger."""

import os
import tempfile
import time
import pytest
from halbert_core.home.timeline import TimelineStore, TimelineEvent


def test_home_timeline_is_a_shim_for_continuity_timeline():
    """A1: TimelineStore moved to continuity/timeline.py (the event ledger
    belongs with state_store/provenance, not under home/); home/timeline.py
    is kept as a one-line shim so this module path stays importable."""
    from halbert_core.continuity.timeline import TimelineStore as CanonicalStore
    from halbert_core.continuity.timeline import TimelineEvent as CanonicalEvent

    assert TimelineStore is CanonicalStore
    assert TimelineEvent is CanonicalEvent


@pytest.fixture
def store():
    """Create a TimelineStore with a temp database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.unlink(db_path)  # Let TimelineStore create it fresh
    s = TimelineStore(db_path=db_path)
    yield s
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestTimelineStoreRecord:
    """Test recording events."""

    def test_record_returns_row_id(self, store):
        event = TimelineEvent(
            timestamp=time.time(),
            event_type="ha_state_change",
            source="ha",
            entity_id="light.living_room",
            title="Living room light turned on",
        )
        row_id = store.record(event)
        assert row_id > 0

    def test_record_simple(self, store):
        row_id = store.record_simple(
            event_type="frigate_event",
            source="frigate",
            entity_id="front_porch",
            severity="info",
            title="Person detected",
            description="Person at front door",
            data={"label": "person", "zones": ["porch"]},
        )
        assert row_id > 0

    def test_record_with_data(self, store):
        store.record_simple(
            event_type="cognitive_tick",
            source="cognitive_loop",
            data={"actions_executed": 2, "actions_blocked": 1},
        )
        results = store.query(event_type="cognitive_tick")
        assert len(results) == 1
        assert results[0]["data"]["actions_executed"] == 2


class TestTimelineStoreQuery:
    """Test querying events."""

    def test_query_by_event_type(self, store):
        store.record_simple(event_type="ha_state_change", entity_id="light.1")
        store.record_simple(event_type="frigate_event", entity_id="cam.front")
        store.record_simple(event_type="ha_state_change", entity_id="light.2")

        results = store.query(event_type="ha_state_change")
        assert len(results) == 2
        assert all(r["event_type"] == "ha_state_change" for r in results)

    def test_query_by_entity_id(self, store):
        store.record_simple(event_type="ha_state_change", entity_id="light.living_room")
        store.record_simple(event_type="ha_state_change", entity_id="light.bedroom")

        results = store.query(entity_id="light.living_room")
        assert len(results) == 1
        assert results[0]["entity_id"] == "light.living_room"

    def test_query_by_severity(self, store):
        store.record_simple(event_type="alert", severity="critical")
        store.record_simple(event_type="alert", severity="info")

        results = store.query(severity="critical")
        assert len(results) == 1
        assert results[0]["severity"] == "critical"

    def test_query_by_time_range(self, store):
        now = time.time()
        store.record_simple(event_type="test", title="old")
        # Manually insert an old event
        event = TimelineEvent(timestamp=now - 7200, event_type="test", title="very_old")
        store.record(event)

        results = store.query(since=now - 3600)
        assert all(r["timestamp"] >= now - 3600 for r in results)
        assert all(r["title"] != "very_old" for r in results)

    def test_query_limit(self, store):
        for i in range(10):
            store.record_simple(event_type="test", title=f"event_{i}")
        results = store.query(limit=5)
        assert len(results) == 5

    def test_query_returns_newest_first(self, store):
        store.record_simple(event_type="test", title="first")
        time.sleep(0.01)
        store.record_simple(event_type="test", title="second")
        results = store.query()
        assert results[0]["title"] == "second"
        assert results[1]["title"] == "first"


class TestTimelineStoreRecent:
    """Test get_recent."""

    def test_get_recent_24h(self, store):
        now = time.time()
        store.record(TimelineEvent(timestamp=now, event_type="test", title="recent"))
        store.record(TimelineEvent(timestamp=now - 86400 * 2, event_type="test", title="old"))

        results = store.get_recent(hours=24)
        assert len(results) == 1
        assert results[0]["title"] == "recent"


class TestTimelineStoreCorrelations:
    """Test get_correlations."""

    def test_correlations_finds_nearby_events(self, store):
        base_time = time.time()
        # Target event
        store.record(TimelineEvent(
            timestamp=base_time,
            event_type="ha_state_change",
            entity_id="lock.front_door",
            title="Front door unlocked",
        ))
        # Nearby events
        store.record(TimelineEvent(
            timestamp=base_time - 60,
            event_type="frigate_event",
            entity_id="front_porch",
            title="Person detected at front door",
        ))
        store.record(TimelineEvent(
            timestamp=base_time + 120,
            event_type="ha_state_change",
            entity_id="light.entry",
            title="Entry light turned on",
        ))
        # Distant event (should not be in correlations)
        store.record(TimelineEvent(
            timestamp=base_time - 7200,
            event_type="ha_state_change",
            entity_id="light.bedroom",
            title="Bedroom light (unrelated)",
        ))

        results = store.get_correlations("lock.front_door", window_seconds=1800)
        assert len(results) >= 2
        titles = [r["title"] for r in results]
        assert "Person detected at front door" in titles
        assert "Entry light turned on" in titles
        assert "Bedroom light (unrelated)" not in titles


class TestTimelineStoreStats:
    """Test stats."""

    def test_stats_returns_counts(self, store):
        store.record_simple(event_type="ha_state_change")
        store.record_simple(event_type="ha_state_change")
        store.record_simple(event_type="frigate_event")

        stats = store.stats()
        assert stats["total_events"] == 3
        assert stats["by_type"]["ha_state_change"] == 2
        assert stats["by_type"]["frigate_event"] == 1
        assert stats["oldest_timestamp"] is not None
        assert stats["newest_timestamp"] is not None


class TestTimelineStoreCleanup:
    """Test cleanup of old events."""

    def test_cleanup_removes_old_events(self, store):
        now = time.time()
        store.record(TimelineEvent(timestamp=now, event_type="test", title="recent"))
        store.record(TimelineEvent(timestamp=now - 86400 * 100, event_type="test", title="very_old"))

        deleted = store.cleanup(max_age_days=90)
        assert deleted == 1

        results = store.query()
        assert len(results) == 1
        assert results[0]["title"] == "recent"
