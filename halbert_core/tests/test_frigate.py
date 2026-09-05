# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for Frigate integration: config, client, MQTT, event mapper, tools."""
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from halbert_core.integrations.frigate.frigate_config import (
    FrigateConfig, load_frigate_config, save_frigate_config,
)
from halbert_core.integrations.frigate.frigate_client import (
    FrigateClient, FrigateConnectionError, FrigateAuthError, FrigateNotFoundError,
)
from halbert_core.integrations.frigate.frigate_mqtt_subscriber import (
    FrigateMQTTSubscriber, TOPIC_EVENTS, TOPIC_REVIEWS,
    EVENT_TYPE_NEW, EVENT_TYPE_UPDATE, EVENT_TYPE_END,
)
from halbert_core.integrations.frigate.frigate_event_mapper import (
    FrigateEventMapper, FrigateStateTracker,
)


# ── FrigateConfig tests ────────────────────────────────────────────────────

class TestFrigateConfig:
    def test_defaults(self):
        cfg = FrigateConfig()
        assert cfg.url == ""
        assert cfg.api_key == ""
        assert cfg.mqtt_enabled is False
        assert cfg.mqtt_port == 1883
        assert cfg.enabled_cameras == []
        assert cfg.alert_labels == []
        assert cfg.alert_zones == []
        assert cfg.min_alert_score == 0.75
        assert cfg.fetch_snapshots is True
        assert not cfg.is_configured()

    def test_is_configured(self):
        cfg = FrigateConfig(url="http://frigate.local:5000")
        assert cfg.is_configured()

    def test_is_mqtt_configured(self):
        cfg = FrigateConfig(mqtt_enabled=True, mqtt_host="mqtt.local")
        assert cfg.is_mqtt_configured()
        cfg2 = FrigateConfig(mqtt_enabled=True, mqtt_host="")
        assert not cfg2.is_mqtt_configured()
        cfg3 = FrigateConfig(mqtt_enabled=False, mqtt_host="mqtt.local")
        assert not cfg3.is_mqtt_configured()

    def test_to_dict_masks_credentials(self):
        cfg = FrigateConfig(
            url="http://frigate.local",
            api_key="verylongapikey123",
            mqtt_password="secretpass",
        )
        d = cfg.to_dict()
        assert "verylongapikey123" not in d["api_key"]
        assert d["mqtt_password"] == "***"

    def test_round_trip_save_load(self, tmp_path):
        cfg = FrigateConfig(
            url="http://frigate.local:5000",
            api_key="test_key",
            mqtt_enabled=True,
            mqtt_host="mqtt.local",
            enabled_cameras=["front_door", "back_yard"],
            alert_labels=["person", "car"],
            min_alert_score=0.8,
        )
        with patch("halbert_core.integrations.frigate.frigate_config._config_path") as mock_path:
            mock_path.return_value = tmp_path / "frigate_config.json"
            save_frigate_config(cfg)
            loaded = load_frigate_config()
        assert loaded.url == "http://frigate.local:5000"
        assert loaded.api_key == "test_key"
        assert loaded.mqtt_enabled is True
        assert loaded.mqtt_host == "mqtt.local"
        assert loaded.enabled_cameras == ["front_door", "back_yard"]
        assert loaded.alert_labels == ["person", "car"]
        assert loaded.min_alert_score == 0.8

    def test_load_missing_returns_defaults(self, tmp_path):
        with patch("halbert_core.integrations.frigate.frigate_config._config_path") as mock_path:
            mock_path.return_value = tmp_path / "nonexistent.json"
            cfg = load_frigate_config()
        assert cfg.url == ""
        assert not cfg.is_configured()


# ── FrigateStateTracker tests ──────────────────────────────────────────────

class TestFrigateStateTracker:
    def test_new_event_adds_detection(self):
        tracker = FrigateStateTracker()
        tracker.on_event(TOPIC_EVENTS, {
            "type": "new",
            "after": {
                "id": "evt1", "camera": "front_door", "label": "person",
                "current_zones": ["porch"], "score": 0.9, "top_score": 0.95,
            },
        })
        assert tracker.has_person()
        assert len(tracker.get_active_detections()) == 1
        det = tracker.get_active_detections()[0]
        assert det["camera"] == "front_door"
        assert det["label"] == "person"
        assert det["zones"] == ["porch"]

    def test_end_event_removes_detection(self):
        tracker = FrigateStateTracker()
        tracker.on_event(TOPIC_EVENTS, {
            "type": "new",
            "after": {"id": "evt1", "camera": "front_door", "label": "person"},
        })
        assert tracker.has_person()
        tracker.on_event(TOPIC_EVENTS, {
            "type": "end",
            "before": {"id": "evt1", "camera": "front_door", "label": "person"},
        })
        assert not tracker.has_person()
        assert len(tracker.get_active_detections()) == 0

    def test_update_event_replaces_state(self):
        tracker = FrigateStateTracker()
        tracker.on_event(TOPIC_EVENTS, {
            "type": "new",
            "after": {"id": "evt1", "camera": "front", "label": "person", "current_zones": []},
        })
        tracker.on_event(TOPIC_EVENTS, {
            "type": "update",
            "after": {"id": "evt1", "camera": "front", "label": "person", "current_zones": ["driveway"]},
        })
        det = tracker.get_active_detections()[0]
        assert det["zones"] == ["driveway"]

    def test_filter_by_camera(self):
        tracker = FrigateStateTracker()
        tracker.on_event(TOPIC_EVENTS, {"type": "new", "after": {"id": "1", "camera": "front", "label": "person"}})
        tracker.on_event(TOPIC_EVENTS, {"type": "new", "after": {"id": "2", "camera": "back", "label": "car"}})
        front = tracker.get_active_by_camera("front")
        assert len(front) == 1
        assert front[0]["label"] == "person"

    def test_filter_by_label(self):
        tracker = FrigateStateTracker()
        tracker.on_event(TOPIC_EVENTS, {"type": "new", "after": {"id": "1", "camera": "front", "label": "person"}})
        tracker.on_event(TOPIC_EVENTS, {"type": "new", "after": {"id": "2", "camera": "back", "label": "car"}})
        persons = tracker.get_active_by_label("person")
        assert len(persons) == 1
        assert persons[0]["camera"] == "front"

    def test_active_labels_and_cameras(self):
        tracker = FrigateStateTracker()
        tracker.on_event(TOPIC_EVENTS, {"type": "new", "after": {"id": "1", "camera": "front", "label": "person"}})
        tracker.on_event(TOPIC_EVENTS, {"type": "new", "after": {"id": "2", "camera": "back", "label": "car"}})
        assert set(tracker.get_active_labels()) == {"person", "car"}
        assert set(tracker.get_active_cameras()) == {"front", "back"}

    def test_ignores_non_events_topic(self):
        tracker = FrigateStateTracker()
        tracker.on_event(TOPIC_REVIEWS, {"severity": "alert", "camera": "front"})
        assert len(tracker.get_active_detections()) == 0


# ── FrigateMQTTSubscriber filter tests ─────────────────────────────────────

class TestFrigateMQTTFilter:
    def _make_subscriber(self, **kwargs):
        cfg = FrigateConfig(**kwargs)
        return FrigateMQTTSubscriber(cfg, on_event=lambda t, p: None)

    def test_camera_filter(self):
        sub = self._make_subscriber(enabled_cameras=["front_door"])
        event = {"type": "new", "after": {"camera": "back_yard", "label": "person", "score": 0.9}}
        assert not sub._should_process_event(event)
        event["after"]["camera"] = "front_door"
        assert sub._should_process_event(event)

    def test_label_filter(self):
        sub = self._make_subscriber(alert_labels=["person"])
        event = {"type": "new", "after": {"camera": "front", "label": "car", "score": 0.9}}
        assert not sub._should_process_event(event)
        event["after"]["label"] = "person"
        assert sub._should_process_event(event)

    def test_zone_filter(self):
        sub = self._make_subscriber(alert_zones=["driveway"])
        event = {"type": "new", "after": {"camera": "front", "label": "person", "score": 0.9, "current_zones": ["porch"]}}
        assert not sub._should_process_event(event)
        event["after"]["current_zones"] = ["driveway"]
        assert sub._should_process_event(event)

    def test_score_filter(self):
        sub = self._make_subscriber(min_alert_score=0.8)
        event = {"type": "new", "after": {"camera": "front", "label": "person", "score": 0.7}}
        assert not sub._should_process_event(event)
        event["after"]["score"] = 0.85
        assert sub._should_process_event(event)

    def test_end_event_bypasses_score_filter(self):
        sub = self._make_subscriber(min_alert_score=0.99)
        event = {"type": "end", "before": {"camera": "front", "label": "person", "score": 0.5}}
        assert sub._should_process_event(event)

    def test_no_filters_passes_all(self):
        sub = self._make_subscriber()
        event = {"type": "new", "after": {"camera": "any", "label": "anything", "score": 0.8, "current_zones": []}}
        assert sub._should_process_event(event)

    def test_review_filter_alert_only(self):
        sub = self._make_subscriber()
        assert sub._should_process_review({"camera": "front", "severity": "alert"})
        assert not sub._should_process_review({"camera": "front", "severity": "detection"})

    def test_review_camera_filter(self):
        sub = self._make_subscriber(enabled_cameras=["front"])
        assert sub._should_process_review({"camera": "front", "severity": "alert"})
        assert not sub._should_process_review({"camera": "back", "severity": "alert"})


# ── FrigateEventMapper cognition tests ─────────────────────────────────────

class TestFrigateEventMapper:
    def _make_timeline_store(self, tmp_path, name="timeline.db"):
        from halbert_core.continuity.timeline import TimelineStore
        return TimelineStore(db_path=str(tmp_path / name))

    def _make_mock_cognition(self):
        cognition = MagicMock()
        cognition.worries = MagicMock()
        cognition.worries.get_active_worries.return_value = []
        cognition.emotional_state = MagicMock()
        return cognition

    def _make_mapper(self, timeline=None):
        return FrigateEventMapper(timeline=timeline)

    def test_new_person_event_records_one_timeline_row(self, tmp_path):
        store = self._make_timeline_store(tmp_path)
        mapper = self._make_mapper(timeline=store)
        mapper.handle_event(TOPIC_EVENTS, {
            "type": "new",
            "after": {"id": "1", "camera": "front_door", "label": "person", "current_zones": ["porch"], "top_score": 0.9},
        })
        rows = store.query(event_type="frigate_event")
        assert len(rows) == 1
        row = rows[0]
        assert row["source"] == "frigate"
        assert row["entity_id"] == "front_door:person"
        assert row["data"] == {
            "type": "new",
            "frigate_event_id": "1",
            "zones": ["porch"],
            "score": 0.9,
        }

    def test_new_person_at_entry_adds_worry(self):
        mapper = self._make_mapper()
        cognition = self._make_mock_cognition()
        mapper.handle_event(TOPIC_EVENTS, {
            "type": "new",
            "after": {"id": "1", "camera": "front_door", "label": "person", "current_zones": ["porch"], "top_score": 0.9},
        })
        mapper.populate_cognition(cognition)
        assert cognition.worries.add_worry.called
        worry_args = cognition.worries.add_worry.call_args
        assert "security" in str(worry_args)

    def test_end_event_resolves_worry(self):
        mapper = self._make_mapper()
        cognition = self._make_mock_cognition()
        # Simulate an existing worry
        worry = MagicMock()
        worry.source = "person_at_front_door"
        worry.id = "w1"
        cognition.worries.get_active_worries.return_value = [worry]

        mapper.handle_event(TOPIC_EVENTS, {
            "type": "end",
            "before": {"id": "1", "camera": "front_door", "label": "person", "current_zones": []},
        })
        mapper.populate_cognition(cognition)
        cognition.worries.resolve_worry.assert_called_once()

    def test_zone_change_records_update_row(self, tmp_path):
        store = self._make_timeline_store(tmp_path)
        mapper = self._make_mapper(timeline=store)
        mapper.handle_event(TOPIC_EVENTS, {
            "type": "update",
            "before": {"id": "1", "camera": "front", "label": "person", "current_zones": ["porch"]},
            "after": {"id": "1", "camera": "front", "label": "person", "current_zones": ["driveway"]},
        })
        rows = store.query(event_type="frigate_event")
        assert len(rows) == 1
        assert rows[0]["data"]["type"] == "update"
        assert rows[0]["data"]["zones"] == ["driveway"]

    def test_review_alert_adds_worry(self):
        mapper = self._make_mapper()
        cognition = self._make_mock_cognition()
        mapper.handle_event(TOPIC_REVIEWS, {
            "severity": "alert",
            "camera": "front_door",
            "id": "rev1",
        })
        mapper.populate_cognition(cognition)
        assert cognition.worries.add_worry.called

    def test_package_detection_adds_joy(self):
        pytest.importorskip("haloysius")
        mapper = self._make_mapper()
        cognition = self._make_mock_cognition()
        mapper.handle_event(TOPIC_EVENTS, {
            "type": "new",
            "after": {"id": "1", "camera": "front_door", "label": "package", "current_zones": ["porch"], "top_score": 0.9},
        })
        mapper.populate_cognition(cognition)
        # Real _add_emotion (un-mocked, DEFECT-2/§3.1): should have called
        # cognition.emotional_state.add_emotion with a real EmotionCategory.JOY.
        emotion_calls = cognition.emotional_state.add_emotion.call_args_list
        assert any("JOY" in str(c) for c in emotion_calls)

    def test_animal_detection_records_row_without_cognitive_effect(self, tmp_path):
        pytest.importorskip("haloysius")
        store = self._make_timeline_store(tmp_path)
        mapper = self._make_mapper(timeline=store)
        cognition = self._make_mock_cognition()
        mapper.handle_event(TOPIC_EVENTS, {
            "type": "new",
            "after": {"id": "1", "camera": "back", "label": "dog", "current_zones": [], "top_score": 0.9},
        })
        mapper.populate_cognition(cognition)
        # A dog is still one row in the durable ledger (A2's row contract
        # is unconditional — every message gets a row) even though it
        # produces no worry or emotion (_apply_label_emotion's animal
        # branch is a no-op).
        rows = store.query(event_type="frigate_event")
        assert len(rows) == 1
        assert rows[0]["entity_id"] == "back:dog"
        assert not cognition.worries.add_worry.called
        assert not cognition.emotional_state.add_emotion.called

    def test_person_elsewhere_against_real_cognition(self):
        """§3.1: EmotionCategory has no VIGILANCE — every one of these calls
        used to raise KeyError (swallowed by the bare except) and no emotion
        was ever recorded. Green only once VIGILANCE -> ANTICIPATION."""
        pytest.importorskip("haloysius")
        from haloysius.persona.cognition import PersonaCognition
        from haloysius.persona.emotional_state import EmotionCategory

        cognition = PersonaCognition(persona_id="test-frigate")
        mapper = self._make_mapper()
        # "patio_cam" is neither an entry point nor covered by is_night, so
        # this deterministically takes the person-elsewhere branch regardless
        # of the time the test runs.
        mapper.handle_event(TOPIC_EVENTS, {
            "type": "new",
            "after": {"id": "1", "camera": "patio_cam", "label": "person", "current_zones": [], "top_score": 0.9},
        })
        mapper.populate_cognition(cognition)

        assert cognition.emotional_state.active_emotions
        assert cognition.emotional_state.active_emotions[0].emotion == EmotionCategory.ANTICIPATION

    def test_no_vigilance_left_in_source(self):
        import inspect
        import halbert_core.integrations.frigate.frigate_event_mapper as mod
        assert '"VIGILANCE"' not in inspect.getsource(mod)


# ── FrigateClient tests (mocked aiohttp) ───────────────────────────────────

class TestFrigateClient:
    def test_headers_with_api_key(self):
        cfg = FrigateConfig(url="http://frigate.local", api_key="test123")
        client = FrigateClient(cfg)
        headers = client._headers()
        assert headers["Authorization"] == "Bearer test123"

    def test_headers_without_api_key(self):
        cfg = FrigateConfig(url="http://frigate.local")
        client = FrigateClient(cfg)
        headers = client._headers()
        assert "Authorization" not in headers

    def test_base_url_strips_trailing_slash(self):
        cfg = FrigateConfig(url="http://frigate.local/")
        client = FrigateClient(cfg)
        assert client._base_url() == "http://frigate.local"


# ── Pending-event queue bound (U6-BUG-03) ──────────────────────────────────

class TestFrigateEventMapperQueueBound:
    """``_pending_events`` must be capped like ``HAEventMapper`` (REV-03 F1):
    with no cognition tick draining it — vision off, agent idle for days —
    an unbounded list grows with every MQTT message Frigate publishes."""

    def test_pending_events_capped_drop_oldest(self):
        mapper = FrigateEventMapper()
        mapper.MAX_PENDING_EVENTS = 3
        for i in range(5):
            mapper.handle_event(TOPIC_EVENTS, {"type": "update", "after": {"id": str(i), "label": "car"}})
        with mapper._lock:
            pending = list(mapper._pending_events)
        assert len(pending) == 3
        assert [e["payload"]["after"]["id"] for e in pending] == ["2", "3", "4"]

    def test_cap_drop_is_logged_with_count(self, caplog):
        """A2: 'do not silently drop again' — the cap previously dropped
        events with no log at all."""
        mapper = FrigateEventMapper()
        mapper.MAX_PENDING_EVENTS = 3
        with caplog.at_level("WARNING", logger="halbert.integrations.frigate.event_mapper"):
            for i in range(5):
                mapper.handle_event(TOPIC_EVENTS, {"type": "update", "after": {"id": str(i), "label": "car"}})
        # Two of the five events overflow the cap of 3 (i=3 and i=4), but the
        # rate limit means only the first overflow logs immediately; the
        # second's drop count is folded into whichever log line comes next.
        drop_records = [r for r in caplog.records if "over cap" in r.getMessage()]
        assert len(drop_records) == 1
        assert "over cap (3)" in drop_records[0].getMessage()
        assert "dropped 1" in drop_records[0].getMessage()

    def test_default_cap_matches_ha_mapper(self):
        from halbert_core.integrations.home_assistant.ha_event_mapper import HAEventMapper
        assert FrigateEventMapper.MAX_PENDING_EVENTS == HAEventMapper.MAX_PENDING_EVENTS
