# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""HA Event Mapper — maps HA state_changed events to PersonaCognition.

Follows the same pattern as SystemEventMapper but for home automation
events. Maps door locks, occupancy changes, climate adjustments, alarm
state transitions, etc. to cognitive worries, drives, and emotions.

Called alongside SystemEventMapper.populate_cognition() before each
cognitive tick.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from ...continuity.timeline import TimelineEvent, TimelineStore
from ..observation_text import normalise_entity_id, normalise_observation_title

logger = logging.getLogger("halbert.integrations.home_assistant.event_mapper")

# Domains whose person/device_tracker home<->not_home transition is also an
# occupancy event (A2 row contract), on top of the unconditional
# ha_state_change row every event gets.
_OCCUPANCY_DOMAINS = ("person", "device_tracker")

# States that mean "we do not know where this was", not "it was away". Home
# Assistant sends old_state=None when it first adds an entity (a restart, an
# integration reload), and a Wi-Fi device tracker reports unavailable/unknown
# every time it drops off the network -- which it does constantly. Reading any
# of those as a prior location turns a phone rejoining Wi-Fi into an arrival,
# and A5's recurrence count then reports a person arriving home a dozen times
# a day.
_UNKNOWN_STATES = (None, "", "unknown", "unavailable", "none")


def describe_state_change(event: Dict[str, Any]) -> str:
    """One line of prose for a state change, for the ledger row's title.

    A row with no title renders as nothing in A4's Eyes block and in C1a's
    Noticed section, which would leave the prose the mapper computes discarded
    exactly as DEFECT-2 describes -- so the description is built here, at
    ingestion, where the row is written. ``populate_cognition`` runs at flush
    and cannot reach a row that was already appended.

    Pure and total: every branch falls through to a generic transition rather
    than returning "", because a missing title is indistinguishable from a
    lost one.
    """
    attributes = event.get("attributes") or {}
    entity_id = event.get("entity_id", "")
    friendly = attributes.get("friendly_name") or entity_id
    domain = event.get("domain", "")
    old_state = event.get("old_state", "")
    new_state = event.get("new_state", "")
    device_class = attributes.get("device_class", "")

    if domain == "lock" and new_state in ("locked", "unlocked"):
        return f"{friendly} was {new_state}"

    if domain == "alarm_control_panel":
        if new_state == "triggered":
            return f"Alarm triggered: {friendly}"
        if new_state == "disarmed":
            return f"Alarm disarmed: {friendly}"
        if new_state.startswith("armed_"):
            return f"Alarm armed ({new_state[len('armed_'):]}): {friendly}"

    if domain in _OCCUPANCY_DOMAINS:
        if new_state == "home":
            return f"{friendly} arrived home"
        if new_state == "not_home":
            return f"{friendly} left home"

    if domain == "climate":
        if old_state == "off" and new_state != "off":
            target = attributes.get("temperature", "?")
            return f"{friendly} turned on ({new_state}), target {target}C"
        if new_state == "off":
            return f"{friendly} turned off"

    if domain == "binary_sensor":
        if device_class in ("door", "opening"):
            return f"{friendly} {'opened' if new_state == 'on' else 'closed'}"
        if device_class == "motion" and new_state == "on":
            return f"Motion detected: {friendly}"
        if device_class == "moisture" and new_state == "on":
            return f"Water leak detected: {friendly}"

    if domain in ("light", "switch") and new_state in ("on", "off"):
        return f"{friendly} turned {new_state}"

    return f"{friendly}: {old_state or 'unknown'} to {new_state or 'unknown'}"


class HAEventMapper:
    """Maps HA state_changed events to PersonaCognition cognitive updates.

    Call populate_cognition() before advance_turn() to inject home state
    into the persona's worries, drives, and emotions.

    Events are accumulated via add_event() (called by HAEventStream)
    and flushed on each cognitive tick.
    """

    # Maximum pending events before oldest are dropped. Prevents unbounded
    # memory growth if cognition ticks are slow or the agent is idle
    # (REV-03 F1). media_player attributes are large; 500 events is ~2MB.
    MAX_PENDING_EVENTS = 500

    # Minimum seconds between "queue over cap" log lines — mirrors
    # FrigateEventMapper's rate limit (A2: "do not silently drop again").
    _DROP_LOG_INTERVAL = 60.0

    # Same rationale for emotion-write failures.
    _EMOTION_LOG_INTERVAL = 60.0

    def __init__(self, trackers: Optional[Dict] = None, timeline: Optional[TimelineStore] = None):
        self._pending_events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._trackers = trackers or {}
        self._timeline = timeline
        self._dropped_since_log = 0
        self._last_drop_log_ts = 0.0
        self._last_emotion_log_ts = 0.0
        if self._timeline is None:
            logger.warning(
                "No TimelineStore configured — HA state changes will not be "
                "durably recorded (they still reach cognition this tick)"
            )

    def add_event(self, event: Dict[str, Any]) -> None:
        """Add a HA state_changed event for the next cognitive tick.

        Args:
            event: Dict with entity_id, domain, old_state, new_state,
                   attributes, timestamp.
        """
        self._record_to_timeline(event)

        with self._lock:
            self._pending_events.append(event)
            # Cap the queue: drop oldest if over limit (REV-03 F1).
            overflow = len(self._pending_events) - self.MAX_PENDING_EVENTS
            if overflow > 0:
                del self._pending_events[:overflow]
                self._dropped_since_log += overflow
                now = time.time()
                if now - self._last_drop_log_ts > self._DROP_LOG_INTERVAL:
                    logger.warning(
                        "HA pending-event queue over cap (%d); dropped %d "
                        "oldest event(s) since last log",
                        self.MAX_PENDING_EVENTS, self._dropped_since_log,
                    )
                    self._dropped_since_log = 0
                    self._last_drop_log_ts = now

    def _record_to_timeline(self, event: Dict[str, Any]) -> None:
        """A2 row contract: one ha_state_change row per event, plus an
        occupancy_change row for a person/device_tracker home transition.
        """
        if self._timeline is None:
            return
        entity_id = normalise_entity_id(event.get("entity_id", ""))
        domain = event.get("domain", "")
        old_state = event.get("old_state", "")
        new_state = event.get("new_state", "")
        attributes = event.get("attributes", {}) or {}
        timestamp = event.get("timestamp") or time.time()
        title = normalise_observation_title(describe_state_change(event))
        try:
            self._timeline.record(TimelineEvent(
                timestamp=timestamp,
                event_type="ha_state_change",
                source="ha",
                entity_id=entity_id,
                title=title,
                data={
                    "domain": domain,
                    "old_state": old_state,
                    "new_state": new_state,
                    "device_class": attributes.get("device_class", ""),
                },
            ))
            # An occupancy_change row asserts a transition, so it needs a
            # known prior state to have transitioned from. The state row above
            # is still written either way: the state was observed, only the
            # movement cannot be claimed.
            known_prior = not (
                old_state is None or str(old_state).strip().lower() in _UNKNOWN_STATES
            )
            if domain in _OCCUPANCY_DOMAINS and known_prior:
                direction = None
                if new_state == "home" and old_state != "home":
                    direction = "arrival"
                elif new_state == "not_home" and old_state != "not_home":
                    direction = "departure"
                if direction:
                    self._timeline.record(TimelineEvent(
                        timestamp=timestamp,
                        event_type="occupancy_change",
                        source="ha",
                        entity_id=entity_id,
                        title=title,
                        data={"direction": direction},
                    ))
        except Exception as e:
            logger.warning(f"Could not record HA event to timeline: {e}")

    def populate_cognition(self, cognition) -> None:
        """Flush pending events into PersonaCognition cognitive layers.

        Call this before advance_turn() so the cognitive tick operates
        on up-to-date worries/drives/emotions derived from home state.
        """
        with self._lock:
            events = list(self._pending_events)
            self._pending_events.clear()

        for event in events:
            self._apply_event_to_cognition(cognition, event)

    def _apply_event_to_cognition(self, cognition, event: Dict[str, Any]) -> None:
        """Apply a single HA event to cognitive layers."""
        domain = event.get("domain", "")
        entity_id = event.get("entity_id", "")
        old_state = event.get("old_state", "")
        new_state = event.get("new_state", "")
        attributes = event.get("attributes", {})
        friendly_name = attributes.get("friendly_name", entity_id)

        # --- Lock events ---
        if domain == "lock":
            if new_state == "locked" and old_state != "locked":
                self._add_emotion(cognition, "TRUST", 0.2, entity_id)
            elif new_state == "unlocked" and old_state != "unlocked":
                if "front" in entity_id or "back" in entity_id or "garage" in entity_id:
                    self._add_worry(
                        cognition,
                        f"{friendly_name} is unlocked",
                        entity_id,
                        "security",
                        0.4,
                    )

        # --- Alarm panel events ---
        elif domain == "alarm_control_panel":
            if new_state == "triggered":
                self._add_worry(
                    cognition,
                    f"Alarm triggered: {friendly_name}",
                    entity_id,
                    "security",
                    0.95,
                )
                self._add_emotion(cognition, "FEAR", 0.9, entity_id)
            elif new_state == "disarmed":
                self._resolve_worry(cognition, entity_id, "alarm disarmed")
            elif new_state == "armed_away":
                self._resolve_worry(cognition, entity_id, "alarm armed")

        # --- Person/device_tracker (occupancy) ---
        elif domain in ("person", "device_tracker"):
            if new_state == "home" and old_state != "home":
                self._add_emotion(cognition, "JOY", 0.3, entity_id)

        # --- Binary sensor (door/window open/close) ---
        elif domain == "binary_sensor":
            if new_state == "on" and old_state != "on":
                # Could be door open, motion detected, etc.
                device_class = attributes.get("device_class", "")
                if device_class == "moisture":
                    self._add_worry(
                        cognition,
                        f"Water leak detected: {friendly_name}",
                        entity_id,
                        "water_leak",
                        0.8,
                    )
                    self._add_emotion(cognition, "FEAR", 0.7, entity_id)

    def _add_worry(
        self, cognition, content: str, source: str, category: str, intensity: float
    ) -> None:
        # Normalised here rather than at each call site: a worry reaches the
        # prompt through check_intrusions() -> ctx.add_observation("[worry] …")
        # -> _format_observations' f"- {obs}", which strips no newlines, so a
        # friendly_name carrying one forges a markdown heading inside the
        # system prompt. One choke point, so a new call site cannot miss it.
        content = normalise_observation_title(content)
        """Add a worry to cognition."""
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
        """Resolve worries matching source."""
        try:
            for worry in cognition.worries.get_active_worries():
                if source in worry.source:
                    cognition.worries.resolve_worry(worry.id, reason)
        except Exception as e:
            logger.debug(f"Could not resolve worry: {e}")

    def _add_emotion(self, cognition, emotion_name: str, intensity: float, source: str) -> None:
        """Add an emotion to cognition."""
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
