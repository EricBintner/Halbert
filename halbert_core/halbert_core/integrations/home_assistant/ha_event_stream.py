# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""HA WebSocket event stream — filtered state_changed subscriptions.

Connects to HA's WebSocket API, subscribes to state_changed events,
filters by domain, debounces telemetry sensors, and forwards meaningful
events to a callback (typically HAEventMapper).

Also handles initial state hydration via REST /api/states on connect.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, Optional, Set

import aiohttp

from .ha_config import HAConfig

logger = logging.getLogger("halbert.integrations.home_assistant.event_stream")

# Domains worth forwarding to cognition
FILTERED_DOMAINS: Set[str] = {
    "climate",
    "lock",
    "alarm_control_panel",
    "binary_sensor",
    "person",
    "device_tracker",
    "input_boolean",
    "light",
    "switch",
    "cover",
    "fan",
    "media_player",
    "vacuum",
}

# Telemetry domains debounced N seconds — only last value per window
DEBOUNCE_DOMAINS: Dict[str, float] = {
    "sensor": 30.0,
}


class HAEventStream:
    """Filtered WebSocket subscription to HA state_changed events.

    Usage:
        stream = HAEventStream(config, on_event=my_callback)
        await stream.start()  # runs in background task
        ...
        await stream.stop()
    """

    def __init__(
        self,
        config: HAConfig,
        on_event: Optional[Callable] = None,
    ) -> None:
        self.config = config
        self._on_event = on_event
        self._task: Optional[asyncio.Task] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._debounce: Dict[str, Dict[str, float]] = {}  # domain -> {entity_id: last_ts}
        self._msg_id = 0

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _ws_url(self) -> str:
        url = self.config.url.rstrip("/")
        if url.startswith("https://"):
            return url.replace("https://", "wss://") + "/api/websocket"
        elif url.startswith("http://"):
            return url.replace("http://", "ws://") + "/api/websocket"
        return url + "/api/websocket"

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.config.token}"}

    async def start(self) -> None:
        """Start the WebSocket listener as a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("HA event stream started")

    async def stop(self) -> None:
        """Stop the WebSocket listener."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("HA event stream stopped")

    async def _run_loop(self) -> None:
        """Main loop: connect, authenticate, subscribe, receive."""
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"HA event stream error: {e}")
            if self._running:
                logger.info("HA event stream reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _connect_and_listen(self) -> None:
        """Connect to HA WebSocket, authenticate, and listen for events."""
        self._session = aiohttp.ClientSession()
        try:
            self._ws = await self._session.ws_connect(
                self._ws_url(),
                headers=self._headers(),
                ssl=self.config.verify_ssl,
            )

            # 1. Wait for auth_required message
            msg = await self._ws.receive(timeout=10)
            data = json.loads(msg.data)
            if data.get("type") != "auth_required":
                raise HAEventStreamError(f"Expected auth_required, got {data.get('type')}")

            # 2. Send auth
            await self._ws.send_json({"type": "auth", "access_token": self.config.token})

            # 3. Wait for auth_ok
            msg = await self._ws.receive(timeout=10)
            data = json.loads(msg.data)
            if data.get("type") != "auth_ok":
                raise HAEventStreamError(f"Auth failed: {data.get('message', 'unknown')}")

            logger.info("HA WebSocket authenticated")

            # 4. Subscribe to state_changed events
            sub_id = self._next_id()
            await self._ws.send_json({
                "id": sub_id,
                "type": "subscribe_events",
                "event_type": "state_changed",
            })

            # 5. Listen for messages
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    self._handle_message(data)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    logger.warning("HA WebSocket closed/error")
                    break
        finally:
            if self._ws and not self._ws.closed:
                await self._ws.close()
            if self._session and not self._session.closed:
                await self._session.close()

    def _handle_message(self, data: Dict[str, Any]) -> None:
        """Handle a WebSocket message."""
        msg_type = data.get("type")
        if msg_type == "event":
            event = data.get("event", {})
            self._process_state_changed(event)
        elif msg_type == "result":
            if not data.get("success"):
                logger.warning(f"HA WebSocket command failed: {data.get('error')}")

    def _process_state_changed(self, event: Dict[str, Any]) -> None:
        """Filter and forward a state_changed event."""
        data = event.get("data", {})
        entity_id = data.get("entity_id", "")
        if not entity_id:
            return

        domain = entity_id.split(".")[0] if "." in entity_id else ""

        # Filter by domain
        if domain not in FILTERED_DOMAINS:
            return

        new_state = data.get("new_state", {})
        old_state = data.get("old_state", {})

        # Skip if no actual state change
        new_val = new_state.get("state") if new_state else None
        old_val = old_state.get("state") if old_state else None
        if new_val == old_val:
            return

        # Debounce telemetry sensors
        if domain in DEBOUNCE_DOMAINS:
            now = time.time()
            interval = DEBOUNCE_DOMAINS[domain]
            last = self._debounce.get(domain, {}).get(entity_id, 0)
            if now - last < interval:
                return
            self._debounce.setdefault(domain, {})[entity_id] = now

        # Forward to callback
        if self._on_event:
            try:
                self._on_event({
                    "entity_id": entity_id,
                    "domain": domain,
                    "old_state": old_val,
                    "new_state": new_val,
                    "attributes": new_state.get("attributes", {}) if new_state else {},
                    "timestamp": time.time(),
                })
            except Exception as e:
                logger.error(f"Event callback error: {e}")


class HAEventStreamError(Exception):
    """Raised when the HA WebSocket stream encounters an error."""
