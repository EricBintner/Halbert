# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Frigate Event Mapper — maps Frigate MQTT events to PersonaCognition.

Mirrors HAEventMapper: accumulates events via handle_event(), flushes
them into cognitive layers via populate_cognition(). Maps detection
events (person, car, dog) to observations, worries, and emotions based
on label, zone, time of day, and severity.

Also maintains a FrigateStateTracker that tracks active detections
("person at front_door right now") for context assembly.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...continuity.timeline import TimelineEvent, TimelineStore
from ..observation_text import normalise_entity_id
from .frigate_mqtt_subscriber import (
    EVENT_TYPE_END,
    EVENT_TYPE_NEW,
    EVENT_TYPE_UPDATE,
    TOPIC_EVENTS,
    TOPIC_REVIEWS,
)

logger = logging.getLogger("halbert.integrations.frigate.event_mapper")


class FrigateStateTracker:
    """Tracks active Frigate detections for context assembly.

    Maintains a dict of {event_id: detection_info} for all currently
    active (in-progress) detections. Used by the cognitive layer to
    answer "what's happening on the cameras right now?"
    """

    def __init__(self):
        self._active: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def on_event(self, topic: str, payload: dict) -> None:
        """Update active detections from an MQTT event."""
        if topic != TOPIC_EVENTS:
            return

        event_type = payload.get("type", "")
        state = payload.get("after") or payload.get("before") or {}
        event_id = state.get("id", "")

        with self._lock:
            if event_type == EVENT_TYPE_END:
                self._active.pop(event_id, None)
            elif event_type in (EVENT_TYPE_NEW, EVENT_TYPE_UPDATE):
                self._active[event_id] = {
                    "id": event_id,
                    "camera": state.get("camera", ""),
                    "label": state.get("label", ""),
                    "sub_label": state.get("sub_label"),
                    "zones": state.get("current_zones", []),
                    "score": state.get("score", 0.0),
                    "top_score": state.get("top_score", 0.0),
                    "start_time": state.get("start_time", 0),
                    "stationary": state.get("stationary", False),
                    "has_snapshot": state.get("has_snapshot", False),
                    "has_clip": state.get("has_clip", False),
                    "attributes": state.get("attributes", {}),
                }

    def get_active_detections(self) -> List[dict]:
        """Return all currently active detections."""
        with self._lock:
            return list(self._active.values())

    def get_active_by_camera(self, camera: str) -> List[dict]:
        """Return active detections for a specific camera."""
        with self._lock:
            return [d for d in self._active.values() if d["camera"] == camera]

    def get_active_by_label(self, label: str) -> List[dict]:
        """Return active detections for a specific label (person, car)."""
        with self._lock:
            return [d for d in self._active.values() if d["label"] == label]

    def get_active_labels(self) -> List[str]:
        """Return unique labels currently being detected."""
        with self._lock:
            return list({d["label"] for d in self._active.values()})

    def get_active_cameras(self) -> List[str]:
        """Return cameras with active detections."""
        with self._lock:
            return list({d["camera"] for d in self._active.values()})

    def has_person(self) -> bool:
        """Quick check: is a person currently detected on any camera?"""
        with self._lock:
            return any(d["label"] == "person" for d in self._active.values())

    def clear(self) -> None:
        """Clear all active detections."""
        with self._lock:
            self._active.clear()


class FrigateEventMapper:
    """Maps Frigate MQTT events to PersonaCognition cognitive updates.

    Call populate_cognition() before advance_turn() to inject camera
    detection state into the persona's worries, drives, and emotions.

    Events are accumulated via handle_event() (called by the MQTT
    subscriber) and flushed on each cognitive tick.
    """

    # Maximum pending events before the oldest are dropped. Mirrors
    # HAEventMapper.MAX_PENDING_EVENTS (REV-03 F1): with no cognition tick
    # draining the queue (vision off, agent idle) a Frigate camera publishes
    # a steady stream of update events and the list grew without bound
    # (U6-BUG-03).
    MAX_PENDING_EVENTS = 500

    # Minimum seconds between "queue over cap" log lines (A2: "do not
    # silently drop again", but a busy camera would otherwise log every
    # single insert once the queue is saturated).
    _DROP_LOG_INTERVAL = 60.0

    # Same rationale for emotion-write failures: a bad emotion name (e.g.
    # the VIGILANCE/EmotionCategory mismatch this branch fixes) would
    # otherwise fire a WARNING on every single detection.
    _EMOTION_LOG_INTERVAL = 60.0

    def __init__(
        self,
        state_tracker: Optional[FrigateStateTracker] = None,
        timeline: Optional[TimelineStore] = None,
    ):
        self._pending_events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self.state_tracker = state_tracker or FrigateStateTracker()
        self._timeline = timeline
        self._dropped_since_log = 0
        self._last_drop_log_ts = 0.0
        self._last_emotion_log_ts = 0.0
        if self._timeline is None:
            logger.warning(
                "No TimelineStore configured — Frigate detections will not "
                "be durably recorded (they still reach cognition this tick)"
            )

    def handle_event(self, topic: str, payload: dict) -> None:
        """Handle an MQTT message from Frigate.

        Called by FrigateMQTTSubscriber. Updates the state tracker,
        records a durable ledger row for a detection event, and queues
        the event for cognitive processing.
        """
        # Update state tracker first (synchronous, no cognition needed)
        self.state_tracker.on_event(topic, payload)

        now = time.time()
        if topic == TOPIC_EVENTS:
            self._record_to_timeline(payload, now)

        # Queue for cognitive processing
        with self._lock:
            self._pending_events.append({
                "topic": topic,
                "payload": payload,
                "timestamp": now,
            })
            # Cap the queue: drop oldest if over limit (U6-BUG-03).
            overflow = len(self._pending_events) - self.MAX_PENDING_EVENTS
            if overflow > 0:
                del self._pending_events[:overflow]
                self._dropped_since_log += overflow
                if now - self._last_drop_log_ts > self._DROP_LOG_INTERVAL:
                    logger.warning(
                        "Frigate pending-event queue over cap (%d); dropped "
                        "%d oldest event(s) since last log",
                        self.MAX_PENDING_EVENTS, self._dropped_since_log,
                    )
                    self._dropped_since_log = 0
                    self._last_drop_log_ts = now

    def _record_to_timeline(self, payload: dict, timestamp: float) -> None:
        """A2 row contract: one row per Frigate message, never a second row
        for the affect strings in ``_apply_label_emotion``.
        """
        if self._timeline is None:
            return
        event_type = payload.get("type", "")
        state = payload.get("after") or payload.get("before") or {}
        camera = state.get("camera", "unknown")
        label = state.get("label", "unknown")
        sub_label = state.get("sub_label")
        try:
            self._timeline.record(TimelineEvent(
                timestamp=timestamp,
                event_type="frigate_event",
                source="frigate",
                entity_id=normalise_entity_id(f"{camera}:{sub_label or label}"),
                data={
                    "type": event_type,
                    "frigate_event_id": state.get("id", ""),
                    "zones": state.get("current_zones", []) or [],
                    "score": state.get("top_score", 0.0) or state.get("score", 0.0),
                },
            ))
        except Exception as e:
            logger.warning(f"Could not record Frigate event to timeline: {e}")

    def populate_cognition(self, cognition) -> None:
        """Flush pending events into PersonaCognition cognitive layers."""
        with self._lock:
            events = list(self._pending_events)
            self._pending_events.clear()

        for event in events:
            self._apply_event_to_cognition(cognition, event)

    def _apply_event_to_cognition(self, cognition, event: dict) -> None:
        """Apply a single Frigate event to cognitive layers."""
        topic = event.get("topic", "")
        payload = event.get("payload", {})

        if topic == TOPIC_EVENTS:
            self._apply_detection_event(cognition, payload)
        elif topic == TOPIC_REVIEWS:
            self._apply_review_event(cognition, payload)

    def _apply_detection_event(self, cognition, payload: dict) -> None:
        """Map a frigate/events message to cognitive effects."""
        event_type = payload.get("type", "")
        state = payload.get("after") or payload.get("before") or {}

        camera = state.get("camera", "unknown")
        label = state.get("label", "unknown")
        sub_label = state.get("sub_label")
        zones = state.get("current_zones", []) or []
        score = state.get("top_score", 0.0) or state.get("score", 0.0)
        event_id = state.get("id", "")

        # Build a human-readable description
        zone_str = f" in {', '.join(zones)}" if zones else ""
        sub_str = f" ({sub_label})" if sub_label else ""

        if event_type == EVENT_TYPE_NEW:
            desc = f"Detected {label}{sub_str} at {camera}{zone_str}"
            self._add_observation(cognition, desc)
            self._apply_label_emotion(cognition, label, camera, zones, event_id)

        elif event_type == EVENT_TYPE_UPDATE:
            # Zone changes are significant — entering a new zone
            before = payload.get("before") or {}
            before_zones = set(before.get("current_zones", []) or [])
            after_zones = set(zones)
            new_zones = after_zones - before_zones
            if new_zones:
                desc = f"{label}{sub_str} entered {', '.join(new_zones)} at {camera}"
                self._add_observation(cognition, desc)
                self._apply_label_emotion(cognition, label, camera, list(new_zones), event_id)

        elif event_type == EVENT_TYPE_END:
            desc = f"{label}{sub_str} left {camera}{zone_str}"
            self._add_observation(cognition, desc)
            # Resolve the worry when a person leaves
            if label == "person":
                self._resolve_worry(cognition, f"person_at_{camera}", "person left")

    def _apply_review_event(self, cognition, payload: dict) -> None:
        """Map a frigate/reviews message to cognitive effects."""
        severity = payload.get("severity", "")
        camera = payload.get("camera", "unknown")
        review_id = payload.get("id", "")

        if severity == "alert":
            self._add_worry(
                cognition,
                f"Camera alert at {camera} — review needed",
                f"frigate_review_{review_id}",
                "security",
                0.6,
            )
            self._add_emotion(cognition, "ANTICIPATION", 0.5, f"frigate:{camera}")

    def _apply_label_emotion(
        self, cognition, label: str, camera: str, zones: list, source: str
    ) -> None:
        """Apply label-specific cognitive effects.

        Person detections at night or at entry points are more concerning
        than a cat in the backyard.
        """
        hour = datetime.now().hour
        is_night = hour < 6 or hour > 22
        is_entry = any(k in camera.lower() for k in ("front", "back", "door", "entry", "garage"))
        source_id = f"person_at_{camera}" if label == "person" else f"{label}_at_{camera}"

        if label == "person":
            if is_night and is_entry:
                # Person at front door at 2am — high concern
                self._add_worry(
                    cognition,
                    f"Person detected at {camera} at night",
                    source_id,
                    "security",
                    0.7,
                )
                self._add_emotion(cognition, "ANTICIPATION", 0.6, source)
            elif is_entry:
                # Person at entry point during the day — moderate
                self._add_worry(
                    cognition,
                    f"Person at {camera}",
                    source_id,
                    "security",
                    0.3,
                )
                self._add_emotion(cognition, "ANTICIPATION", 0.3, source)
            else:
                # Person elsewhere — mild awareness
                self._add_observation(cognition, f"Person seen at {camera}")
                self._add_emotion(cognition, "ANTICIPATION", 0.15, source)

        elif label in ("car", "vehicle"):
            if is_night and is_entry:
                self._add_observation(cognition, f"Vehicle at {camera} at night")
                self._add_emotion(cognition, "ANTICIPATION", 0.2, source)
            else:
                self._add_observation(cognition, f"Vehicle at {camera}")

        elif label in ("dog", "cat", "bird", "squirrel"):
            # Animals are routine — no cognitive effect unless unusual
            pass

        elif label == "package":
            self._add_observation(cognition, f"Package detected at {camera}")
            self._add_emotion(cognition, "JOY", 0.2, source)

    def _add_observation(self, cognition, text: str) -> None:
        try:
            if hasattr(cognition, "internal_state"):
                cognition.internal_state.add_observation(text)
            elif hasattr(cognition, "observations"):
                cognition.observations.append(text)
        except Exception as e:
            logger.debug(f"Could not add observation: {e}")

    def _add_worry(
        self, cognition, content: str, source: str, category: str, intensity: float
    ) -> None:
        try:
            cognition.worries.add_worry(
                content=content,
                source=source,
                category=category,
                intensity=intensity,
                intrusion_rate=0.3,
            )
        except Exception as e:
            logger.debug(f"Could not add worry: {e}")

    def _resolve_worry(self, cognition, source: str, reason: str) -> None:
        try:
            for worry in cognition.worries.get_active_worries():
                if source in worry.source:
                    cognition.worries.resolve_worry(worry.id, reason)
        except Exception as e:
            logger.debug(f"Could not resolve worry: {e}")

    def _add_emotion(self, cognition, emotion_name: str, intensity: float, source: str) -> None:
        try:
            from haloysius.persona.emotional_state import EmotionCategory
            cognition.emotional_state.add_emotion(
                emotion=EmotionCategory[emotion_name],
                intensity=intensity,
                source=source,
            )
        except Exception as e:
            now = time.time()
            if now - self._last_emotion_log_ts > self._EMOTION_LOG_INTERVAL:
                logger.warning(f"Could not add emotion {emotion_name!r}: {e}")
                self._last_emotion_log_ts = now
