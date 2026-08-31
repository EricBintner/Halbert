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

logger = logging.getLogger("halbert.integrations.home_assistant.event_mapper")


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

    def __init__(self, trackers: Optional[Dict] = None):
        self._pending_events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._trackers = trackers or {}

    def add_event(self, event: Dict[str, Any]) -> None:
        """Add a HA state_changed event for the next cognitive tick.

        Args:
            event: Dict with entity_id, domain, old_state, new_state,
                   attributes, timestamp.
        """
        with self._lock:
            self._pending_events.append(event)
            # Cap the queue: drop oldest if over limit (REV-03 F1).
            if len(self._pending_events) > self.MAX_PENDING_EVENTS:
                del self._pending_events[: len(self._pending_events) - self.MAX_PENDING_EVENTS]

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
                self._add_observation(cognition, f"{friendly_name} was locked")
                self._add_emotion(cognition, "TRUST", 0.2, entity_id)
            elif new_state == "unlocked" and old_state != "unlocked":
                self._add_observation(cognition, f"{friendly_name} was unlocked")
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
                self._add_observation(cognition, f"Alarm disarmed: {friendly_name}")
                self._resolve_worry(cognition, entity_id, "alarm disarmed")
            elif new_state == "armed_away":
                self._add_observation(cognition, f"Alarm armed (away): {friendly_name}")
                self._resolve_worry(cognition, entity_id, "alarm armed")

        # --- Person/device_tracker (occupancy) ---
        elif domain in ("person", "device_tracker"):
            if new_state == "home" and old_state != "home":
                self._add_observation(cognition, f"{friendly_name} arrived home")
                self._add_emotion(cognition, "JOY", 0.3, entity_id)
            elif new_state == "not_home" and old_state != "not_home":
                self._add_observation(cognition, f"{friendly_name} left home")

        # --- Climate events ---
        elif domain == "climate":
            if old_state == "off" and new_state != "off":
                target = attributes.get("temperature", "?")
                self._add_observation(
                    cognition,
                    f"{friendly_name} turned on ({new_state}), target {target}C",
                )
            elif new_state == "off" and old_state != "off":
                self._add_observation(cognition, f"{friendly_name} turned off")

        # --- Binary sensor (door/window open/close) ---
        elif domain == "binary_sensor":
            if new_state == "on" and old_state != "on":
                # Could be door open, motion detected, etc.
                device_class = attributes.get("device_class", "")
                if device_class in ("door", "opening"):
                    self._add_observation(cognition, f"{friendly_name} opened")
                elif device_class == "motion":
                    self._add_observation(cognition, f"Motion detected: {friendly_name}")
                elif device_class == "moisture":
                    self._add_worry(
                        cognition,
                        f"Water leak detected: {friendly_name}",
                        entity_id,
                        "water_leak",
                        0.8,
                    )
                    self._add_emotion(cognition, "FEAR", 0.7, entity_id)
            elif new_state == "off" and old_state != "off":
                device_class = attributes.get("device_class", "")
                if device_class in ("door", "opening"):
                    self._add_observation(cognition, f"{friendly_name} closed")

        # --- Light/switch (lifestyle awareness) ---
        elif domain in ("light", "switch"):
            if new_state == "on" and old_state != "on":
                self._add_observation(cognition, f"{friendly_name} turned on")
            elif new_state == "off" and old_state != "off":
                self._add_observation(cognition, f"{friendly_name} turned off")

    def _add_observation(self, cognition, text: str) -> None:
        """Add an observation to cognition's internal state."""
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
            logger.debug(f"Could not add emotion: {e}")
