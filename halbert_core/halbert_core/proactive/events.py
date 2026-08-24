"""
Proactive event bus — in-memory pub/sub for proactive events.

The being publishes events (findings, morning reports, approval requests,
system anomalies) to this bus. SSE subscribers receive them in real-time.

Phase 7 / T7a.1.
"""

from __future__ import annotations

import asyncio
import logging
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

    Thread-safe via asyncio locks. Supports async subscribers.
    Maintains a ring buffer of recent events for late subscribers.
    """

    def __init__(self, buffer_size: int = 50):
        self._subscribers: dict[str, Subscriber] = {}
        self._recent: Deque[ProactiveEvent] = deque(maxlen=buffer_size)
        self._lock = asyncio.Lock()

    async def publish(self, event: ProactiveEvent) -> None:
        """Publish an event to all subscribers."""
        async with self._lock:
            self._recent.append(event)

        # Call subscribers outside the lock to prevent blocking
        for sub_id, callback in list(self._subscribers.items()):
            try:
                result = callback(event)
                # If the callback is a coroutine, schedule it
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as e:
                logger.warning(f"Subscriber {sub_id} error: {e}")

        logger.info(f"Proactive event published: [{event.severity}] {event.title}")

    def subscribe(self, callback: Subscriber) -> str:
        """Subscribe to events. Returns a subscription ID for unsubscribing."""
        sub_id = str(uuid.uuid4())
        self._subscribers[sub_id] = callback
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        """Unsubscribe by subscription ID."""
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
