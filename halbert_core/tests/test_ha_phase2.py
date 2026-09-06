# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Unit tests for Phase 2 HA modules (event stream, history, mapper, governance)."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from halbert_core.integrations.home_assistant.ha_governance import HAGovernancePolicy
from halbert_core.integrations.home_assistant.ha_event_mapper import HAEventMapper
from halbert_core.integrations.home_assistant.ha_config import HAConfig


# --- Governance policy tests ---

class TestHAGovernancePolicy:
    def setup_method(self):
        self.policy = HAGovernancePolicy()

    def test_level0_light(self):
        result = self.policy.classify("light", "light.living_room", "turn_on")
        assert result["level"] == 0
        assert result["allowed"] is True
        assert not result["requires_confirmation"]

    def test_level0_fan(self):
        result = self.policy.classify("fan", "fan.bedroom", "turn_off")
        assert result["level"] == 0
        assert result["allowed"] is True

    def test_level1_climate(self):
        result = self.policy.classify("climate", "climate.living_room", "set_temperature")
        assert result["level"] == 1
        assert result["allowed"] is True
        assert not result["requires_confirmation"]

    def test_level2_lock(self):
        result = self.policy.classify("lock", "lock.front_door", "unlock")
        assert result["level"] == 2
        assert result["allowed"] is True
        assert result["requires_confirmation"] is True

    def test_level2_alarm(self):
        result = self.policy.classify("alarm_control_panel", "alarm_control_panel.home", "disarm")
        assert result["level"] == 2
        assert result["requires_confirmation"] is True

    def test_level3_water_valve(self):
        result = self.policy.classify("water_valve", "water_valve.main", "open")
        assert result["level"] == 3
        assert result["allowed"] is False

    def test_level3_forbidden_entity(self):
        result = self.policy.classify("switch", "switch.freezer", "turn_off")
        assert result["level"] == 3
        assert result["allowed"] is False

    def test_level3_medical_entity(self):
        result = self.policy.classify("switch", "switch.medical_device", "turn_off")
        assert result["level"] == 3
        assert result["allowed"] is False

    def test_unknown_domain_defaults_to_level1(self):
        result = self.policy.classify("unknown_domain", "unknown_domain.test", "test")
        assert result["level"] == 1
        assert result["allowed"] is True


# --- Event mapper tests ---

class TestHAEventMapper:
    def test_add_and_flush_events(self):
        mapper = HAEventMapper()
        mapper.add_event({
            "entity_id": "lock.front_door",
            "domain": "lock",
            "old_state": "unlocked",
            "new_state": "locked",
            "attributes": {"friendly_name": "Front Door"},
            "timestamp": time.time(),
        })

        # Mock cognition
        cognition = MagicMock()
        cognition.worries.add_worry = MagicMock()
        cognition.worries.get_active_worries = MagicMock(return_value=[])
        cognition.emotional_state.add_emotion = MagicMock()

        mapper.populate_cognition(cognition)

        # Should have called emotional_state.add_emotion for the lock event
        cognition.emotional_state.add_emotion.assert_called()

    def test_unlocked_front_door_creates_worry(self):
        mapper = HAEventMapper()
        mapper.add_event({
            "entity_id": "lock.front_door",
            "domain": "lock",
            "old_state": "locked",
            "new_state": "unlocked",
            "attributes": {"friendly_name": "Front Door"},
            "timestamp": time.time(),
        })

        cognition = MagicMock()
        cognition.worries.add_worry = MagicMock()
        cognition.worries.get_active_worries = MagicMock(return_value=[])
        cognition.emotional_state.add_emotion = MagicMock()

        mapper.populate_cognition(cognition)

        # Should have added a worry about front door being unlocked
        worry_calls = cognition.worries.add_worry.call_args_list
        assert any("unlocked" in str(c) for c in worry_calls)

    def test_alarm_triggered_creates_high_intensity_worry(self):
        mapper = HAEventMapper()
        mapper.add_event({
            "entity_id": "alarm_control_panel.home",
            "domain": "alarm_control_panel",
            "old_state": "armed_away",
            "new_state": "triggered",
            "attributes": {"friendly_name": "Home Alarm"},
            "timestamp": time.time(),
        })

        cognition = MagicMock()
        cognition.worries.add_worry = MagicMock()
        cognition.worries.get_active_worries = MagicMock(return_value=[])
        cognition.emotional_state.add_emotion = MagicMock()

        mapper.populate_cognition(cognition)

        worry_calls = cognition.worries.add_worry.call_args_list
        assert any("triggered" in str(c) for c in worry_calls)
        # Check intensity is high
        for call in worry_calls:
            if "triggered" in str(call):
                assert call.kwargs.get("intensity", 0) >= 0.9

    def test_person_arrives_home(self):
        mapper = HAEventMapper()
        mapper.add_event({
            "entity_id": "person.sarah",
            "domain": "person",
            "old_state": "not_home",
            "new_state": "home",
            "attributes": {"friendly_name": "Sarah"},
            "timestamp": time.time(),
        })

        cognition = MagicMock()
        cognition.worries.add_worry = MagicMock()
        cognition.worries.get_active_worries = MagicMock(return_value=[])
        cognition.emotional_state.add_emotion = MagicMock()

        mapper.populate_cognition(cognition)

        emotion_calls = cognition.emotional_state.add_emotion.call_args_list
        assert any("JOY" in str(c) for c in emotion_calls)

    def test_water_leak_creates_worry(self):
        mapper = HAEventMapper()
        mapper.add_event({
            "entity_id": "binary_sensor.kitchen_leak",
            "domain": "binary_sensor",
            "old_state": "off",
            "new_state": "on",
            "attributes": {"friendly_name": "Kitchen Leak", "device_class": "moisture"},
            "timestamp": time.time(),
        })

        cognition = MagicMock()
        cognition.worries.add_worry = MagicMock()
        cognition.worries.get_active_worries = MagicMock(return_value=[])
        cognition.emotional_state.add_emotion = MagicMock()

        mapper.populate_cognition(cognition)

        worry_calls = cognition.worries.add_worry.call_args_list
        assert any("leak" in str(c).lower() for c in worry_calls)

    def test_flushed_events_dont_persist(self):
        mapper = HAEventMapper()
        mapper.add_event({
            "entity_id": "light.test",
            "domain": "light",
            "old_state": "off",
            "new_state": "on",
            "attributes": {},
            "timestamp": time.time(),
        })

        cognition = MagicMock()
        cognition.worries.add_worry = MagicMock()
        cognition.worries.get_active_worries = MagicMock(return_value=[])
        cognition.emotional_state.add_emotion = MagicMock()

        mapper.populate_cognition(cognition)
        # Second call should have no events
        mapper.populate_cognition(cognition)

        # Second call should not add more emotions
        assert cognition.emotional_state.add_emotion.call_count == 0 or \
               cognition.emotional_state.add_emotion.call_count == 1

    def test_ignores_same_state_change(self):
        """Events where old_state == new_state should not generate cognitive updates."""
        mapper = HAEventMapper()
        # The event stream filters these, but the mapper should be robust
        mapper.add_event({
            "entity_id": "light.test",
            "domain": "light",
            "old_state": "on",
            "new_state": "on",
            "attributes": {},
            "timestamp": time.time(),
        })

        cognition = MagicMock()
        cognition.worries.add_worry = MagicMock()
        cognition.worries.get_active_worries = MagicMock(return_value=[])
        cognition.emotional_state.add_emotion = MagicMock()

        mapper.populate_cognition(cognition)
        # No worries or emotions should be added for same-state
        cognition.worries.add_worry.assert_not_called()

    def test_person_arrives_home_against_real_cognition(self):
        """One test per mapper against a real PersonaCognition (A2)."""
        pytest.importorskip("haloysius")
        from haloysius.persona.cognition import PersonaCognition
        from haloysius.persona.emotional_state import EmotionCategory

        cognition = PersonaCognition(persona_id="test-ha")
        mapper = HAEventMapper()
        mapper.add_event({
            "entity_id": "person.sarah",
            "domain": "person",
            "old_state": "not_home",
            "new_state": "home",
            "attributes": {"friendly_name": "Sarah"},
            "timestamp": time.time(),
        })
        mapper.populate_cognition(cognition)

        assert cognition.emotional_state.active_emotions
        assert cognition.emotional_state.active_emotions[0].emotion == EmotionCategory.JOY


# --- Observation-path tests (A2): none of the seven populate_cognition ---
# --- tests above assert anything reaches a durable record. ---------------

class TestHAEventMapperTimeline:
    def _make_store(self, tmp_path):
        from halbert_core.continuity.timeline import TimelineStore
        return TimelineStore(db_path=str(tmp_path / "timeline.db"))

    def test_lock_event_records_ha_state_change_row(self, tmp_path):
        store = self._make_store(tmp_path)
        mapper = HAEventMapper(timeline=store)
        mapper.add_event({
            "entity_id": "lock.front_door",
            "domain": "lock",
            "old_state": "unlocked",
            "new_state": "locked",
            "attributes": {"friendly_name": "Front Door"},
            "timestamp": 1000.0,
        })
        rows = store.query(event_type="ha_state_change")
        assert len(rows) == 1
        row = rows[0]
        assert row["source"] == "ha"
        assert row["entity_id"] == "lock.front_door"
        assert row["timestamp"] == 1000.0
        assert row["data"] == {
            "domain": "lock",
            "old_state": "unlocked",
            "new_state": "locked",
            "device_class": "",
        }
        # No occupancy_change row for a non-occupancy domain.
        assert store.query(event_type="occupancy_change") == []

    def test_person_arrival_also_records_occupancy_change(self, tmp_path):
        store = self._make_store(tmp_path)
        mapper = HAEventMapper(timeline=store)
        mapper.add_event({
            "entity_id": "person.sarah",
            "domain": "person",
            "old_state": "not_home",
            "new_state": "home",
            "attributes": {"friendly_name": "Sarah"},
            "timestamp": 2000.0,
        })
        assert len(store.query(event_type="ha_state_change")) == 1
        occupancy_rows = store.query(event_type="occupancy_change")
        assert len(occupancy_rows) == 1
        assert occupancy_rows[0]["entity_id"] == "person.sarah"
        assert occupancy_rows[0]["data"] == {"direction": "arrival"}

    def test_person_departure_records_departure_direction(self, tmp_path):
        store = self._make_store(tmp_path)
        mapper = HAEventMapper(timeline=store)
        mapper.add_event({
            "entity_id": "device_tracker.phone",
            "domain": "device_tracker",
            "old_state": "home",
            "new_state": "not_home",
            "attributes": {},
            "timestamp": 3000.0,
        })
        occupancy_rows = store.query(event_type="occupancy_change")
        assert len(occupancy_rows) == 1
        assert occupancy_rows[0]["data"] == {"direction": "departure"}

    def test_no_timeline_configured_does_not_raise(self):
        mapper = HAEventMapper()  # timeline=None
        mapper.add_event({
            "entity_id": "light.test",
            "domain": "light",
            "old_state": "off",
            "new_state": "on",
            "attributes": {},
            "timestamp": time.time(),
        })
        assert len(mapper._pending_events) == 1


# --- Event stream tests (unit-level, no real WebSocket) ---

class TestHAEventStream:
    def test_ws_url_http(self):
        from halbert_core.integrations.home_assistant.ha_event_stream import HAEventStream
        config = HAConfig(url="http://ha.local:8123", token="test")
        stream = HAEventStream(config)
        assert stream._ws_url() == "ws://ha.local:8123/api/websocket"

    def test_ws_url_https(self):
        from halbert_core.integrations.home_assistant.ha_event_stream import HAEventStream
        config = HAConfig(url="https://ha.local:8123", token="test")
        stream = HAEventStream(config)
        assert stream._ws_url() == "wss://ha.local:8123/api/websocket"

    def test_process_state_changed_filters_unfiltered_domain(self):
        from halbert_core.integrations.home_assistant.ha_event_stream import HAEventStream
        config = HAConfig(url="http://ha.local:8123", token="test")
        callback_called = []
        stream = HAEventStream(config, on_event=lambda e: callback_called.append(e))

        stream._process_state_changed({
            "data": {
                "entity_id": "automation.test",
                "new_state": {"state": "on"},
                "old_state": {"state": "off"},
            }
        })
        assert len(callback_called) == 0  # automation not in FILTERED_DOMAINS

    def test_process_state_changed_forwards_light(self):
        from halbert_core.integrations.home_assistant.ha_event_stream import HAEventStream
        config = HAConfig(url="http://ha.local:8123", token="test")
        callback_called = []
        stream = HAEventStream(config, on_event=lambda e: callback_called.append(e))

        stream._process_state_changed({
            "data": {
                "entity_id": "light.living_room",
                "new_state": {"state": "on", "attributes": {"friendly_name": "Living Room"}},
                "old_state": {"state": "off"},
            }
        })
        assert len(callback_called) == 1
        assert callback_called[0]["entity_id"] == "light.living_room"
        assert callback_called[0]["new_state"] == "on"

    def test_process_state_changed_skips_same_state(self):
        from halbert_core.integrations.home_assistant.ha_event_stream import HAEventStream
        config = HAConfig(url="http://ha.local:8123", token="test")
        callback_called = []
        stream = HAEventStream(config, on_event=lambda e: callback_called.append(e))

        stream._process_state_changed({
            "data": {
                "entity_id": "light.living_room",
                "new_state": {"state": "on"},
                "old_state": {"state": "on"},
            }
        })
        assert len(callback_called) == 0

    def test_debounce_sensor(self):
        from halbert_core.integrations.home_assistant.ha_event_stream import HAEventStream
        config = HAConfig(url="http://ha.local:8123", token="test")
        callback_called = []
        stream = HAEventStream(config, on_event=lambda e: callback_called.append(e))

        # First sensor event should pass
        stream._process_state_changed({
            "data": {
                "entity_id": "sensor.temperature",
                "new_state": {"state": "21.5"},
                "old_state": {"state": "21.0"},
            }
        })
        assert len(callback_called) == 1

        # Second sensor event within debounce window should be skipped
        stream._process_state_changed({
            "data": {
                "entity_id": "sensor.temperature",
                "new_state": {"state": "21.6"},
                "old_state": {"state": "21.5"},
            }
        })
        assert len(callback_called) == 1  # Still only 1


# --- History backfill tests ---

class TestHAHistoryBackfill:
    @pytest.mark.asyncio
    async def test_backfill_returns_significant_events(self):
        from halbert_core.integrations.home_assistant.ha_history import backfill_history

        # Mock HAClient
        client = MagicMock()
        client._request = AsyncMock(return_value=[
            [
                {"entity_id": "lock.front_door", "state": "locked", "attributes": {"friendly_name": "Front Door"}, "last_changed": "2026-08-20T10:00:00Z"},
                {"entity_id": "lock.front_door", "state": "unlocked", "attributes": {"friendly_name": "Front Door"}, "last_changed": "2026-08-20T11:00:00Z"},
            ],
            [
                {"entity_id": "sensor.temperature", "state": "21.5", "attributes": {}, "last_changed": "2026-08-20T10:00:00Z"},
            ],
        ])

        events = await backfill_history(client, days=7)
        # Only lock events should be significant (sensor not in SIGNIFICANT_DOMAINS)
        assert len(events) == 2
        assert all(e["entity_id"].startswith("lock.") for e in events)

    @pytest.mark.asyncio
    async def test_backfill_handles_error(self):
        from halbert_core.integrations.home_assistant.ha_history import backfill_history

        client = MagicMock()
        client._request = AsyncMock(side_effect=Exception("Connection failed"))

        events = await backfill_history(client, days=7)
        assert events == []

    @pytest.mark.asyncio
    async def test_backfill_skips_unavailable_states(self):
        from halbert_core.integrations.home_assistant.ha_history import backfill_history

        client = MagicMock()
        client._request = AsyncMock(return_value=[
            [
                {"entity_id": "lock.front_door", "state": "unavailable", "attributes": {}, "last_changed": ""},
                {"entity_id": "lock.front_door", "state": "locked", "attributes": {}, "last_changed": "2026-08-20T10:00:00Z"},
            ],
        ])

        events = await backfill_history(client, days=7)
        assert len(events) == 1
        assert events[0]["state"] == "locked"
