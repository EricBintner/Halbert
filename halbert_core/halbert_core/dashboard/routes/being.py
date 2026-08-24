"""
Being SSE routes — Server-Sent Events for proactive notifications.

Provides:
- GET /api/being/events — SSE stream of proactive events
- POST /api/being/events/{event_id}/snooze — snooze a finding
- POST /api/being/events/{event_id}/dismiss — dismiss a finding

Phase 7 / T7b.1.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...proactive.events import get_event_bus, ProactiveEvent
from ...findings.store import FindingStore

logger = logging.getLogger("halbert.dashboard.being")

router = APIRouter()


@router.get("/being/events")
async def being_events(request: Request):
    """SSE stream of proactive events.

    Subscribes to the ProactiveEventBus and yields events as SSE.
    Sends a heartbeat every 15 seconds to keep the connection alive.
    """
    bus = get_event_bus()

    # Send recent events first, then live events
    async def event_stream():
        # Create a queue for this subscriber
        queue: asyncio.Queue = asyncio.Queue()

        # Subscribe with a callback that puts events in the queue
        def callback(event: ProactiveEvent) -> None:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("SSE queue full, dropping event")

        sub_id = bus.subscribe(callback)

        try:
            # Send recent events first
            for event in bus.get_recent(limit=20):
                yield f"data: {json.dumps(event.to_dict())}\n\n"

            # Then live events with heartbeat
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event.to_dict())}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(sub_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


class SnoozeRequest(BaseModel):
    days: int = 7


class DismissRequest(BaseModel):
    reason: str = ""


@router.post("/being/events/{event_id}/snooze")
async def snooze_event(event_id: str, req: SnoozeRequest = SnoozeRequest()):
    """Snooze a finding for N days."""
    store = FindingStore()
    if not store.get(event_id):
        raise HTTPException(status_code=404, detail="Finding not found")
    success = store.snooze(event_id, req.days)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to snooze")
    return {"status": "ok", "snoozed_until": store.get(event_id).snoozed_until}


@router.post("/being/events/{event_id}/dismiss")
async def dismiss_event(event_id: str, req: DismissRequest = DismissRequest()):
    """Dismiss a finding with an optional reason."""
    store = FindingStore()
    if not store.get(event_id):
        raise HTTPException(status_code=404, detail="Finding not found")
    success = store.dismiss(event_id, req.reason)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to dismiss")
    return {"status": "ok", "dismissed": True}


@router.get("/being/events/recent")
async def recent_events(limit: int = Query(50, ge=1, le=200)):
    """Get recent proactive events (non-streaming)."""
    bus = get_event_bus()
    events = bus.get_recent(limit=limit)
    return {"status": "ok", "events": [e.to_dict() for e in events]}
