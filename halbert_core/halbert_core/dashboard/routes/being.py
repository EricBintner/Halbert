# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
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

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import require_owner_stream
from ...proactive.events import get_event_bus, is_user_facing, ProactiveEvent
from ...attunement.reactions import note
from ...findings.store import FindingStore

logger = logging.getLogger("halbert.dashboard.being")

router = APIRouter()


def _should_stream(event: ProactiveEvent) -> bool:
    """Only attention events reach the human-facing channel (C2-16).

    somatic_block / subagent_event are published straight to the bus by the
    state machine and the subagent manager (ungated, and already on the
    agent SSE stream); rendered here they were generic rows whose
    snooze/dismiss 400'd.
    """
    return is_user_facing(event)


# EventSource cannot set a header, and in the Tauri webview it cannot use a
# cookie either, so this one route also accepts ?token=. Router-level
# require_owner still applies to every other route in this module.
@router.get("/being/events", dependencies=[Depends(require_owner_stream)])
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
            if not _should_stream(event):
                return

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
                if _should_stream(event):
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


def _note_safely(reaction: str, finding_id: str) -> None:
    """Record the reaction; never let the ledger cost the user their action."""
    try:
        note(reaction, finding_id)
    except Exception as exc:  # pragma: no cover - `note` already swallows
        logger.warning("Could not record the %s reaction: %s", reaction, exc)


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
        # A-HB-26: label the attempt this is a reaction to. "Not now" and
        # "no" are different evidence and the ledger keeps them apart.
        # Guarded here as well as inside `note`: the reaction is the
        # secondary effect, and losing it is a gap in the evidence where
        # losing the snooze is a bug the person sees.
        _note_safely("not_now", finding_id)
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
        _note_safely("dismissed", finding_id)

    await asyncio.to_thread(_do_dismiss)
    return {"status": "ok", "dismissed": True}


@router.get("/being/events/recent")
async def recent_events(limit: int = Query(50, ge=1, le=200)):
    """Get recent user-facing proactive events (non-streaming).

    ``limit`` counts rows the caller will see, so lifecycle events are
    filtered before it applies (the ring buffer holds at most 50 anyway).
    """
    bus = get_event_bus()
    events = [e for e in bus.get_recent(limit=200) if _should_stream(e)]
    return {"status": "ok", "events": [e.to_dict() for e in events[-limit:]]}


# ─────────────────────────────────────────────────────────────────────────────
# Presence (spec 2026-09-16 v2 §15). Read-only; the level itself is written
# through /api/settings/being.
# ─────────────────────────────────────────────────────────────────────────────

def _attunement_store():
    """The shadow log. A function so tests can point it at a temp DB."""
    from ...attunement.store import AttunementStore
    return AttunementStore()


@router.get("/being/presence/rungs")
def presence_rungs() -> dict:
    """The curve's rungs with their first-person copy — the settings surface
    never hardcodes it (plan D8) — and whether each rung is *classifiable*
    yet: every class it newly admits has a classification branch
    (``PRODUCED_CLASSES``). Whether a producer emits the class today is the
    shadow log's question, not this endpoint's. Plain ``def``: Starlette
    runs it off the event loop, like ``findings.py``'s handlers."""
    try:
        from ...attunement.curve import halbert_curve
        from ...attunement.impulses import PRODUCED_CLASSES
        curve = halbert_curve()
    except ImportError:
        raise HTTPException(status_code=503, detail="attunement engine not installed")
    rungs, previous = [], set()
    for r in curve.rungs:
        newly = set(r.admits) - previous
        rungs.append({
            "level": r.level, "name": r.name, "says": r.says, "why": r.why,
            "admits": sorted(c.value for c in r.admits),
            "channel": {c.value: ch.value for c, ch in r.channel.items()},
            "budget_per_day": r.budget_per_day, "patience_s": r.patience_s,
            "closes_after": r.closes_after,
            "classifiable": newly <= PRODUCED_CLASSES,   # str-enum members compare equal to their value strings
        })
        previous = set(r.admits)
    return {"status": "ok", "rungs": rungs}   # the curve's owner id is internal, not a surface string


#: A safety cap on rows read for one preview; the window itself is a ``since``
#: filter in SQL, so this binds only a store far busier than a month of
#: proactive events. When it binds, ``truncated`` says so on the wire.
_PREVIEW_ROWS = 20000


@router.get("/being/presence/preview")
def presence_preview(
    level: int = Query(..., ge=0, le=10),
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """What I would have said, shown and held over the last ``days`` at
    ``level`` — admission and channel re-run over the shadow log. The counts
    see every row in the window (a ``since`` filter in SQL; ``truncated``
    only if the safety cap bound); ``items`` is cut to ``limit`` for the
    wire. 503 without the engine, like the rungs; 400 on a config the
    loader refuses, like the settings GET. Plain ``def``: three synchronous
    reads (a SQLite open, the window, the YAML) stay off the event loop."""
    try:
        import haloysius.attunement.presence  # noqa: F401
    except ImportError:
        raise HTTPException(status_code=503, detail="attunement engine not installed")

    from datetime import datetime, timedelta, timezone

    from ...attunement.context import DEFAULT_PERSONA_ID
    from ...attunement.preview import preview_for_level
    from ...config.being_config import load_being_config

    try:
        config = load_being_config()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()
    rows = _attunement_store().list_outcomes_raw(DEFAULT_PERSONA_ID, limit=_PREVIEW_ROWS, since=since)
    preview = preview_for_level(rows, level, being_config=config, days=days, now=now)
    if not preview["engine"]:
        raise HTTPException(
            status_code=503,
            detail="the attunement engine is installed but did not resolve a presence vector",
        )
    preview.pop("engine", None)   # the frontend's Preview interface never declared it
    preview["items"] = preview["items"][:limit]
    preview["truncated"] = len(rows) >= _PREVIEW_ROWS
    # the envelope last, so no preview key can shadow it; preview_for_level
    # returns a fresh dict on every call, so setting a key here cannot
    # corrupt a shared object
    preview["status"] = "ok"
    return preview
