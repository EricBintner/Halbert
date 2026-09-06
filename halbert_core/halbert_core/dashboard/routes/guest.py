# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The channel a paired app hands a persona over — design §8, option 2.

Why HTTP in this process and not the MCP surface: ``mcp/server.py`` is a
standalone stdio/HTTP process. A guest is a process-local object
(``persona/guest.py``), and only the dashboard process owns the agent
singleton whose prompt builder and tool executor read it. Offering a
persona anywhere else would install a face nobody wears.

Two sides, two boundaries:

- The app's side — offer, heartbeat, withdraw — is authenticated with the
  pairing token (``require_peer_auth``), the same credential Linked Devices
  already issue and revoke. Only the peer that offered a session may
  heartbeat or withdraw it.
- The user's side — ``end`` — is the Presence Pill's control and is bound to
  this machine (``require_local_admin``), deliberately not satisfiable by a
  peer token.

Every beginning and ending is announced on the proactive event bus
(type ``guest_session``), so the bell and the conversation see the face
change (§7). Endings the peer did not ask for — a handback from the tool, a
missed heartbeat noticed on a read, the user ending it — reach the bus
through the session-end observer installed here.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...federation.peer_middleware import PeerContext, require_local_admin, require_peer_auth
from ...persona import guest
from ...proactive.events import ProactiveEvent, get_event_bus

logger = logging.getLogger("halbert.dashboard.guest")

router = APIRouter()

EVENT_TYPE = "guest_session"
_ANNOUNCER_KEY = "dashboard.routes.guest.announce"


class OfferRequest(BaseModel):
    persona: Dict[str, Any]
    ttl_seconds: float = Field(default=guest.DEFAULT_TTL_SECONDS, ge=1.0, le=guest.MAX_TTL_SECONDS)
    # Where the guest's words go (design §4.3). Optional: a guest without a
    # home is a face that does not remember, and the turn says so.
    home: Optional[Dict[str, Any]] = None


class PullRequest(BaseModel):
    """"Halbert, be Marnie" — the user's side fetches a persona from its home
    (design §7). The base URL and persona id name the home; the token is
    what Halbert presents to it."""
    base_url: str
    persona_id: str
    token: str = ""
    label: str = ""
    ttl_seconds: float = Field(default=guest.DEFAULT_TTL_SECONDS, ge=1.0, le=guest.MAX_TTL_SECONDS)


class HeartbeatRequest(BaseModel):
    session_id: str


# ---------------------------------------------------------------------------
# Announcing
# ---------------------------------------------------------------------------

def _own_name() -> str:
    try:
        from ...identity import resolve_entity_name
        return resolve_entity_name()
    except Exception:
        return "Halbert"


def _fronting_event(session: guest.GuestSession) -> ProactiveEvent:
    who = session.persona.name
    by = session.offered_by_name or session.offered_by
    return ProactiveEvent.create(
        type=EVENT_TYPE,
        severity="info",
        title=f"{who} is speaking for {_own_name()}",
        body=f"{by} lent {_own_name()} the persona {who} for this session. "
             f"{_own_name()} keeps its tools, memory and rules underneath.",
        data={"state": "fronting", **session.to_dict()},
    )


def _ended_event(session: guest.GuestSession) -> ProactiveEvent:
    who = session.persona.name
    own = _own_name()
    reason = session.end_reason or "ended"
    said = {
        "withdrawn": f"{session.offered_by_name or session.offered_by} took {who} back.",
        "handback": f"{who} handed the conversation back.",
        "ended_by_user": f"You ended {who}'s session.",
        "heartbeat_missed": f"{session.offered_by_name or session.offered_by} stopped answering; "
                            f"{who}'s session lapsed.",
        "replaced": f"{session.offered_by_name or session.offered_by} replaced {who}.",
    }.get(reason, f"{who}'s session ended.")
    return ProactiveEvent.create(
        type=EVENT_TYPE,
        severity="info",
        title=f"{own} is speaking as {own} again",
        body=said,
        data={"state": "ended", "reason": reason, **session.to_dict()},
    )


def _publish_from_anywhere(event: ProactiveEvent) -> None:
    """Publish from a sync observer, whichever thread notices the ending."""
    bus = get_event_bus()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        loop.create_task(bus.publish(event))
    else:
        asyncio.run(bus.publish(event))


def _announce_end(session: guest.GuestSession) -> None:
    try:
        _publish_from_anywhere(_ended_event(session))
    except Exception as e:
        logger.warning("Guest session ending not announced: %s", e)


def _ensure_announcer() -> None:
    """Idempotent: the same key re-subscribes, so a reset (tests, a reload)
    cannot leave endings silent."""
    guest.on_session_end(_announce_end, key=_ANNOUNCER_KEY)


# ---------------------------------------------------------------------------
# The app's side
# ---------------------------------------------------------------------------

@router.post("/api/guest/offer")
async def offer_persona(
    request: OfferRequest,
    peer: PeerContext = Depends(require_peer_auth),
) -> Dict[str, Any]:
    """Lend this machine a persona for a session."""
    try:
        persona, dropped = guest.GuestPersona.from_payload(request.persona)
        home = guest.GuestHome.from_payload(request.home) if request.home else None
    except guest.GuestValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _ensure_announcer()
    try:
        session = guest.offer(
            persona,
            offered_by=peer.node_id,
            offered_by_name=peer.node_name,
            ttl_seconds=request.ttl_seconds,
            home=home,
        )
    except guest.GuestConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except guest.GuestValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await get_event_bus().publish(_fronting_event(session))
    return {"status": "ok", "session": session.to_dict(), "dropped": dropped}


@router.post("/api/guest/heartbeat")
async def heartbeat(
    request: HeartbeatRequest,
    peer: PeerContext = Depends(require_peer_auth),
) -> Dict[str, Any]:
    try:
        session = guest.heartbeat(request.session_id, offered_by=peer.node_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="No live guest session with that id")
    except guest.GuestConflict as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"status": "ok", "session": session.to_dict()}


@router.post("/api/guest/withdraw")
async def withdraw_persona(
    peer: PeerContext = Depends(require_peer_auth),
) -> Dict[str, Any]:
    live = guest.current_guest()
    if live is None:
        return {"status": "idle", "session": None}
    if live.offered_by != peer.node_id:
        raise HTTPException(status_code=403, detail="That session was offered by another peer")
    _ensure_announcer()
    ended = guest.withdraw(reason="withdrawn", by=peer.node_id)
    return {"status": "ok", "session": ended.to_dict() if ended else None}


# ---------------------------------------------------------------------------
# The user's side
# ---------------------------------------------------------------------------

@router.post("/api/guest/pull", dependencies=[Depends(require_local_admin)])
async def pull_persona(request: PullRequest) -> Dict[str, Any]:
    """Fetch a persona from a sibling's home and wear it. The session is
    kept alive by pinging the home, since nobody there is heartbeating."""
    from ...persona import sibling

    try:
        home = guest.GuestHome.from_payload(request.model_dump())
    except guest.GuestValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _ensure_announcer()
    from urllib.parse import urlparse
    who = home.label or (urlparse(home.base_url).netloc or home.base_url)
    try:
        session, dropped = await asyncio.to_thread(
            sibling.install_from_home,
            home,
            offered_by=f"home:{urlparse(home.base_url).netloc}",
            offered_by_name=who,
            ttl_seconds=request.ttl_seconds,
        )
    except sibling.HomeUnreachable as e:
        raise HTTPException(status_code=502, detail=f"The persona's home did not answer: {e}")
    except guest.GuestConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except guest.GuestValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await get_event_bus().publish(_fronting_event(session))
    return {"status": "ok", "session": session.to_dict(), "dropped": dropped}


@router.post("/api/guest/end", dependencies=[Depends(require_local_admin)])
async def end_session() -> Dict[str, Any]:
    """The Presence Pill's control: the user takes the face off."""
    _ensure_announcer()
    ended = guest.withdraw(reason="ended_by_user", by="user")
    if ended is None:
        return {"status": "idle", "session": None}
    return {"status": "ok", "session": ended.to_dict()}


@router.get("/api/guest")
async def guest_status() -> Dict[str, Optional[Dict[str, Any]]]:
    live = guest.current_guest()
    return {"fronting": live.to_dict() if live else None}
