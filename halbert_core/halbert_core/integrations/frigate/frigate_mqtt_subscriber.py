# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Async MQTT subscriber for Frigate events.

Subscribes to frigate/events and frigate/reviews, filters by the
FrigateConfig (cameras, labels, zones, min_score), and dispatches
to a callback. The callback is typically FrigateEventMapper.handle_event.

Uses aiomqtt (async-native MQTT client) as an optional dependency.
The module lazy-imports aiomqtt so it loads even without the dep —
the subscriber just won't start.

MQTT topic reference (Frigate docs):
  frigate/events  — tracked object lifecycle (new/update/end)
  frigate/reviews — review segments (alert/detection severity)
  frigate/triggers — semantic search triggers (optional)
  frigate/<camera>/<label> — per-camera per-label state (optional)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Optional

from .frigate_config import FrigateConfig

logger = logging.getLogger("halbert.integrations.frigate.mqtt")

# Topic constants
TOPIC_EVENTS = "frigate/events"
TOPIC_REVIEWS = "frigate/reviews"
TOPIC_TRIGGERS = "frigate/triggers"

# Event types from Frigate
EVENT_TYPE_NEW = "new"
EVENT_TYPE_UPDATE = "update"
EVENT_TYPE_END = "end"


class FrigateMQTTSubscriber:
    """Async MQTT subscriber for Frigate detection events.

    Runs as a background asyncio task. Reconnects automatically on
    disconnection with exponential backoff.

    The callback receives (topic, payload_dict) for each matching message.
    """

    def __init__(
        self,
        config: FrigateConfig,
        on_event: Callable[[str, dict], Any],
    ):
        self.config = config
        self.on_event = on_event
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._connected = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """Start the MQTT subscriber as a background task."""
        if self._task is not None:
            return
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("FrigateMQTTSubscriber starting")

    async def stop(self) -> None:
        """Stop the subscriber.

        Safe to call from any event loop — if called from a different
        loop than the one that started the subscriber, uses
        call_soon_threadsafe to cancel the task in the correct loop.
        """
        self._running = False
        self._connected = False
        if self._task is not None:
            current_loop = None
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            if current_loop is self._loop:
                # Same loop — cancel directly
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            elif self._loop is not None and not self._loop.is_closed():
                # Different loop — cancel thread-safely
                self._loop.call_soon_threadsafe(self._task.cancel)
            self._task = None
        logger.info("FrigateMQTTSubscriber stopped")

    async def _run_loop(self) -> None:
        """Main loop with automatic reconnection."""
        try:
            import aiomqtt
        except ImportError:
            logger.warning(
                "aiomqtt not installed — Frigate MQTT subscriber disabled. "
                "Install with: pip install aiomqtt"
            )
            return

        backoff = 1
        max_backoff = 60
        auth_failures = 0
        max_auth_failures = 5

        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=self.config.mqtt_host,
                    port=self.config.mqtt_port,
                    username=self.config.mqtt_user or None,
                    password=self.config.mqtt_password or None,
                ) as client:
                    # Subscribe BEFORE setting _connected so a subscribe
                    # failure doesn't leave a false "connected" state
                    await client.subscribe(TOPIC_EVENTS)
                    await client.subscribe(TOPIC_REVIEWS)
                    self._connected = True
                    backoff = 1  # reset backoff on successful connect
                    auth_failures = 0  # reset auth failure counter
                    logger.info(
                        f"Frigate MQTT connected to {self.config.mqtt_host}:{self.config.mqtt_port}"
                    )
                    logger.info(f"Subscribed to {TOPIC_EVENTS}, {TOPIC_REVIEWS}")

                    # Message loop
                    async for message in client.messages:
                        if not self._running:
                            break
                        await self._handle_message(message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                self._connected = False

                # Detect authentication failures and stop retrying after N attempts
                err_str = str(e).lower()
                if "auth" in err_str or "not authorized" in err_str or "bad user" in err_str:
                    auth_failures += 1
                    if auth_failures >= max_auth_failures:
                        logger.error(
                            f"Frigate MQTT: authentication failed {auth_failures} times, "
                            f"stopping. Check MQTT credentials."
                        )
                        break
                    logger.warning(
                        f"Frigate MQTT: auth failed ({auth_failures}/{max_auth_failures}), "
                        f"retrying in {backoff}s"
                    )
                else:
                    logger.warning(f"Frigate MQTT disconnected: {e}, reconnecting in {backoff}s")

                await asyncio.sleep(backoff)
                # Exponential backoff with jitter
                import random
                backoff = min(backoff * 2, max_backoff)
                jitter = random.uniform(0, backoff * 0.1)
                backoff = int(backoff + jitter)

        self._connected = False

    async def _handle_message(self, message) -> None:
        """Parse and filter an MQTT message, dispatch to callback."""
        try:
            topic = str(message.topic)
            payload_bytes = message.payload
            if isinstance(payload_bytes, (bytes, bytearray)):
                payload = json.loads(payload_bytes.decode("utf-8"))
            else:
                payload = json.loads(str(payload_bytes))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.debug(f"Frigate MQTT: failed to parse message on {topic}: {e}")
            return

        # Apply config-based filtering
        if not self._should_process(topic, payload):
            return

        try:
            result = self.on_event(topic, payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.warning(f"Frigate MQTT: callback error: {e}")

    def _should_process(self, topic: str, payload: dict) -> bool:
        """Apply config filters to decide if this event should be processed."""
        if topic == TOPIC_EVENTS:
            return self._should_process_event(payload)
        elif topic == TOPIC_REVIEWS:
            return self._should_process_review(payload)
        return True  # unknown topics pass through

    def _should_process_event(self, payload: dict) -> bool:
        """Filter frigate/events by camera, label, zone, and score."""
        # Frigate events have before/after; check the "after" state
        # (or "before" for end events where after may be null)
        state = payload.get("after") or payload.get("before") or {}

        camera = state.get("camera", "")
        label = state.get("label", "")
        zones = state.get("current_zones", []) or []
        score = state.get("score", 0.0) or state.get("top_score", 0.0)

        # Camera filter
        if self.config.enabled_cameras and camera not in self.config.enabled_cameras:
            return False

        # Label filter
        if self.config.alert_labels and label not in self.config.alert_labels:
            return False

        # Zone filter
        if self.config.alert_zones:
            if not any(z in self.config.alert_zones for z in zones):
                return False

        # Score filter (only for new/update events, not end)
        event_type = payload.get("type", "")
        if event_type != EVENT_TYPE_END and score < self.config.min_alert_score:
            return False

        return True

    def _should_process_review(self, payload: dict) -> bool:
        """Filter frigate/reviews by camera and severity."""
        camera = payload.get("camera", "")
        severity = payload.get("severity", "")

        if self.config.enabled_cameras and camera not in self.config.enabled_cameras:
            return False

        # Only surface alert-level reviews, not routine detections
        if severity != "alert":
            return False

        return True
