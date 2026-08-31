# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Proactive event bus — in-memory pub/sub for proactive events.

The being publishes events (findings, morning reports, approval requests,
system anomalies) to this bus. SSE subscribers receive them in real-time.

Phase 7 / T7a.1.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Callable, Deque, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProactiveEvent:
    """A proactive event from the being."""

    id: str
    type: str  # finding | morning_report | approval_request | system_anomaly
    severity: str  # info | warning | critical
    title: str
    body: str
    finding_id: Optional[str] = None
    proposal_id: Optional[str] = None
    created_at: str = ""
    # Category used by ProactiveGate's per-category overrides
    # (general | config | storage | security | ...)
    category: str = "general"
    # Structured payload for type-specific frontend rendering (O5). None for
    # plain finding/report events; the acoustic anomaly detector fills it with
    # the frontend module contract (sound_class, confidence, area_id,
    # decibel_level, anomaly_severity, source, timestamp ISO-8601).
    data: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def create(
        cls,
        type: str,
        severity: str,
        title: str,
        body: str,
        **kwargs,
    ) -> "ProactiveEvent":
        """Create a new event with auto-generated ID and timestamp."""
        return cls(
            id=str(uuid.uuid4()),
            type=type,
            severity=severity,
            title=title,
            body=body,
            created_at=datetime.now(timezone.utc).isoformat(),
            **kwargs,
        )


# Type alias for subscriber callbacks
Subscriber = Callable[[ProactiveEvent], None]


class ProactiveEventBus:
    """In-memory event bus for proactive events.

    Thread-safe via a threading lock on the recent buffer. Supports async
    subscribers. Maintains a ring buffer of recent events for late
    subscribers.

    Publishers may live on a different thread/loop than subscribers (the
    config-watcher worker thread publishes while SSE subscriber queues live
    on the uvicorn loop). Call attach_loop() from the subscriber side so
    publish() can hand dispatch to that loop via call_soon_threadsafe.
    """

    def __init__(self, buffer_size: int = 50):
        self._subscribers: dict[str, Subscriber] = {}
        self._recent: Deque[ProactiveEvent] = deque(maxlen=buffer_size)
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread_id: Optional[int] = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Attach the asyncio loop that owns subscriber callbacks.

        Called from the subscribing side (e.g. the SSE handler) with the
        running loop. When publish() runs on a different thread/loop,
        subscriber dispatch is routed here via call_soon_threadsafe instead
        of touching asyncio objects from a foreign thread.
        """
        self._loop = loop
        self._loop_thread_id = threading.get_ident()

    def _invoke(self, sub_id: str, callback: Subscriber, event: ProactiveEvent) -> None:
        """Invoke one subscriber callback, scheduling coroutine results."""
        try:
            result = callback(event)
            # If the callback is a coroutine, schedule it
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)
        except Exception as e:
            logger.warning(f"Subscriber {sub_id} error: {e}")

    async def publish(self, event: ProactiveEvent) -> None:
        """Publish an event to all subscribers.

        Safe to await from any thread/loop. If an attached loop exists and
        this call runs on a different thread, subscriber dispatch is handed
        to that loop via call_soon_threadsafe; otherwise callbacks are
        invoked directly (current async behavior).
        """
        with self._lock:
            self._recent.append(event)
            # Snapshot under the lock — subscribe/unsubscribe also mutate
            # this dict from other threads.
            subscribers = list(self._subscribers.items())

        use_attached_loop = (
            self._loop is not None
            and threading.get_ident() != self._loop_thread_id
        )

        # Call subscribers outside the lock to prevent blocking
        for sub_id, callback in subscribers:
            if use_attached_loop:
                try:
                    self._loop.call_soon_threadsafe(
                        self._invoke, sub_id, callback, event
                    )
                except RuntimeError:
                    # Attached loop is closed (e.g. uvicorn hot-reload before
                    # an SSE client reconnected). Deliberate fallback: deliver
                    # inline rather than lose the event.
                    logger.info(
                        "Attached event loop closed; delivering inline"
                    )
                    self._invoke(sub_id, callback, event)
            else:
                self._invoke(sub_id, callback, event)

        logger.info(f"Proactive event published: [{event.severity}] {event.title}")

    def subscribe(self, callback: Subscriber) -> str:
        """Subscribe to events. Returns a subscription ID for unsubscribing."""
        sub_id = str(uuid.uuid4())
        with self._lock:
            self._subscribers[sub_id] = callback
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        """Unsubscribe by subscription ID."""
        with self._lock:
            self._subscribers.pop(sub_id, None)

    def get_recent(self, limit: int = 50) -> List[ProactiveEvent]:
        """Get recent events from the ring buffer."""
        return list(self._recent)[-limit:]

    def clear(self) -> None:
        """Clear the recent events buffer."""
        self._recent.clear()


# Global singleton instance
_bus: Optional[ProactiveEventBus] = None


def get_event_bus() -> ProactiveEventBus:
    """Get the global ProactiveEventBus singleton."""
    global _bus
    if _bus is None:
        _bus = ProactiveEventBus()
    return _bus
