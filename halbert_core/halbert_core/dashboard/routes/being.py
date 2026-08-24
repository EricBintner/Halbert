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
        loop = asyncio.get_running_loop()
        bus.attach_loop(loop)

        # Create a queue for this subscriber (lives on this loop)
        queue: asyncio.Queue = asyncio.Queue()

        # Subscribe with a callback that puts events in the queue.
        # The bus already routes foreign-thread publishes through this
        # loop via attach_loop; the running-loop check here is a safety
        # net so put_nowait never runs on a thread that doesn't own the
        # queue.
        def callback(event: ProactiveEvent) -> None:
            def _offer() -> None:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning("SSE queue full, dropping event")

            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                _offer()
            else:
                loop.call_soon_threadsafe(_offer)

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


def _resolve_finding_id(event_id: str, store: FindingStore) -> str:
    """Resolve a path id to a finding id.

    ProactiveEvents carry their own uuid and put the finding id in
    event.finding_id, so the UI passes the *event* id. Resolution order:
      (a) scan the event bus's recent buffer for an event with this id
          and use its finding_id;
      (b) treat the id as a finding id directly (store.get).

    Raises HTTPException(400) when the id resolves to an event that has
    no finding_id (non-finding events can't be snoozed/dismissed),
    and HTTPException(404) when neither resolution path finds anything
    (or the referenced finding row is gone).

    Runs synchronously against SQLite — call via asyncio.to_thread from
    async handlers.
    """
    bus = get_event_bus()
    for event in bus.get_recent(limit=200):
        if event.id == event_id:
            if not event.finding_id:
                raise HTTPException(
                    status_code=400,
                    detail="Event is not linked to a finding and cannot be snoozed/dismissed",
                )
            if store.get(event.finding_id) is None:
                raise HTTPException(status_code=404, detail="Finding not found")
            return event.finding_id
    if store.get(event_id) is not None:
        return event_id
    raise HTTPException(status_code=404, detail="Finding not found")


@router.post("/being/events/{event_id}/snooze")
async def snooze_event(event_id: str, req: SnoozeRequest = SnoozeRequest()):
    """Snooze a finding for N days.

    `event_id` may be a ProactiveEvent id (from the SSE stream) or a
    finding id directly — see _resolve_finding_id. The SQLite and
    SourcePrep work runs off the event loop via asyncio.to_thread.
    """
    def _do_snooze() -> str:
        store = FindingStore()
        finding_id = _resolve_finding_id(event_id, store)
        if not store.snooze(finding_id, req.days):
            raise HTTPException(status_code=500, detail="Failed to snooze")
        return store.get(finding_id).snoozed_until

    snoozed_until = await asyncio.to_thread(_do_snooze)
    return {"status": "ok", "snoozed_until": snoozed_until}


@router.post("/being/events/{event_id}/dismiss")
async def dismiss_event(event_id: str, req: DismissRequest = DismissRequest()):
    """Dismiss a finding with an optional reason.

    `event_id` may be a ProactiveEvent id (from the SSE stream) or a
    finding id directly — see _resolve_finding_id. The SQLite and
    SourcePrep work runs off the event loop via asyncio.to_thread.
    """
    def _do_dismiss() -> None:
        store = FindingStore()
        finding_id = _resolve_finding_id(event_id, store)
        if not store.dismiss(finding_id, req.reason):
            raise HTTPException(status_code=500, detail="Failed to dismiss")

    await asyncio.to_thread(_do_dismiss)
    return {"status": "ok", "dismissed": True}


@router.get("/being/events/recent")
async def recent_events(limit: int = Query(50, ge=1, le=200)):
    """Get recent proactive events (non-streaming)."""
    bus = get_event_bus()
    events = bus.get_recent(limit=limit)
    return {"status": "ok", "events": [e.to_dict() for e in events]}
