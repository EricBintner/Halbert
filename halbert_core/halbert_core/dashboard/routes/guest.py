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
from types import SimpleNamespace
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...federation.peer_middleware import PeerContext, require_local_admin, require_peer_auth
from ...persona import guest, guest_homes, private_sources
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


class PrivateSourceRequest(BaseModel):
    source_id: str


class HomeRequest(BaseModel):
    base_url: str
    label: str = ""
    token: str = ""


class BecomeRequest(BaseModel):
    """"Be Marnie" — a name and, when two homes have one, which home."""
    name: str
    base_url: str = ""
    ttl_seconds: float = guest.DEFAULT_TTL_SECONDS


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


# ---------------------------------------------------------------------------
# The homes whose personas this machine may wear
# ---------------------------------------------------------------------------

@router.get("/api/guest/homes", dependencies=[Depends(require_local_admin)])
async def list_homes() -> Dict[str, Any]:
    """The homes this machine knows. Tokens are never returned."""
    return {"homes": [h.to_dict() for h in guest_homes.list_homes()]}


@router.post("/api/guest/homes", dependencies=[Depends(require_local_admin)])
async def add_home(request: HomeRequest) -> Dict[str, Any]:
    try:
        record = guest_homes.add_home(request.base_url, request.label, request.token)
    except guest_homes.BadHome as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "home": record.to_dict()}


@router.delete("/api/guest/homes", dependencies=[Depends(require_local_admin)])
async def forget_home(base_url: str) -> Dict[str, Any]:
    try:
        removed = guest_homes.remove_home(base_url)
    except guest_homes.BadHome as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok" if removed else "unknown"}


@router.get("/api/guest/available", dependencies=[Depends(require_local_admin)])
async def available_personas() -> Dict[str, Any]:
    """Every persona this machine could wear right now, across every home.

    A home that does not answer is reported, not raised: "be Marnie" should
    still work when the other house is asleep.
    """
    return await asyncio.to_thread(guest_homes.available_personas)


@router.post("/api/guest/become", dependencies=[Depends(require_local_admin)])
async def become(request: BecomeRequest) -> Dict[str, Any]:
    """Wear the persona with this name, wherever it lives.

    The verb the user actually says. ``/api/guest/pull`` still takes a URL, a
    persona id and a token, which is a fine thing for a script and a poor
    thing for a person; this resolves a name against the known homes and
    keeps the credential on disk where it belongs.
    """
    catalogue = await asyncio.to_thread(guest_homes.available_personas)
    wanted = request.name.strip().lower()
    matches = [
        p for p in catalogue["personas"]
        if p["name"].strip().lower() == wanted
        and (not request.base_url or p["base_url"] == request.base_url.rstrip("/"))
    ]
    if not matches:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No persona called {request.name!r} in any known home"
                + (f" (unreachable: {', '.join(u['home'] for u in catalogue['unreachable'])})"
                   if catalogue["unreachable"] else "")
            ),
        )
    if len(matches) > 1:
        # Named in two houses. Answering with one of them would be a guess
        # about which face the user meant.
        raise HTTPException(
            status_code=409,
            detail=(
                f"{request.name} lives in more than one home "
                f"({', '.join(sorted({m['home_label'] for m in matches}))}); say which."
            ),
        )

    match = matches[0]
    record = guest_homes.get_home(match["base_url"])
    return await pull_persona(PullRequest(
        base_url=match["base_url"],
        persona_id=match["persona_id"],
        token=record.token if record else "",
        label=match["home_label"],
        ttl_seconds=request.ttl_seconds,
    ))


# ---------------------------------------------------------------------------
# Private sources — the user's side, and only the user's
# ---------------------------------------------------------------------------

def _private_event(source_id: str, label: str, first: bool) -> ProactiveEvent:
    """Announce a handover. The first one carries the statement.

    The private-mode review's P6 asks for that line in the interface at the
    moment the first source is handed over. The pill shows it before the
    click; this puts the same words in the bell, so the promise is on the
    record and not only in a dialog the user dismissed.
    """
    own = _own_name()
    body = (
        private_sources.statement(label, own)
        if first
        else f"{label} is the guest's for the rest of this session."
    )
    return ProactiveEvent.create(
        type=EVENT_TYPE,
        severity="info",
        title=f"{label} handed over",
        body=body,
        data={"state": "private", "source_id": source_id, "first": first},
    )


@router.post("/api/guest/private/assign", dependencies=[Depends(require_local_admin)])
async def assign_private_source(request: PrivateSourceRequest) -> Dict[str, Any]:
    """Hand one source to the fronting guest for the rest of its session.

    Local only, and deliberately not satisfiable by a peer token: the app that
    lent the persona must not be able to award itself the user's camera.
    """
    label = _label_for(request.source_id)
    first = not private_sources.active()
    try:
        private_sources.assign(request.source_id)
    except private_sources.NoGuestFronting as e:
        raise HTTPException(status_code=409, detail=str(e))
    except private_sources.BadSourceId as e:
        raise HTTPException(status_code=400, detail=str(e))
    await get_event_bus().publish(_private_event(request.source_id, label, first))
    return {"status": "ok", "private_sources": _private_sources_payload()}


@router.post("/api/guest/private/release", dependencies=[Depends(require_local_admin)])
async def release_private_source(request: PrivateSourceRequest) -> Dict[str, Any]:
    """Take one source back. The guest keeps fronting."""
    try:
        private_sources.release(request.source_id)
    except private_sources.BadSourceId as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "private_sources": _private_sources_payload()}


@router.get("/api/guest/private/sources", dependencies=[Depends(require_local_admin)])
async def list_private_sources() -> Dict[str, Any]:
    """Everything the user could hand over, across the senses, with its owner."""
    return {"sources": private_sources.catalogue()}


def _label_for(source_id: str) -> str:
    for entry in private_sources.catalogue():
        if entry["id"] == source_id:
            return entry["label"]
    return source_id


def _private_sources_payload() -> Dict[str, str]:
    return {sid: owner.value for sid, owner in private_sources.assigned().items()}


class ForgetRequest(BaseModel):
    """Which session to forget. Omitted means the one fronting now."""
    session_id: str = ""


@router.post("/api/guest/forget", dependencies=[Depends(require_local_admin)])
async def forget_session(request: ForgetRequest) -> Dict[str, Any]:
    """Erase what a guest session left in Halbert's own stores.

    D2's promise made good. In normal mode the transcript is Halbert's, kept
    and tagged with ``guest-session-<id>`` so that one call can take it back
    out again — that tag is worth nothing unless something calls this.

    Two halves, and missing either leaves the words on disk: the transcript
    (``forget_request`` deletes the messages) and the ledger
    (``redact_request`` replaces the stated reasons with UNRECORDED, leaving
    the facts and their timeline intact — what was true and when is not the
    thing being forgotten, and deleting those rows would make the history
    lie).

    Local only, and it does not require a guest to be fronting: the session
    most worth forgetting is usually one that has ended.
    """
    session_id = request.session_id.strip()
    if not session_id:
        live = guest.current_guest()
        if live is None:
            raise HTTPException(
                status_code=409,
                detail="No guest is fronting; say which session to forget.",
            )
        session_id = live.id

    from ...continuity.ownership import guest_request_id

    request_id = guest_request_id(SimpleNamespace(id=session_id))
    messages = 0
    receipts = 0

    try:
        from ...agents.conversation_sqlite import SqliteConversationStore
        messages = SqliteConversationStore().forget_request(request_id)
    except Exception as e:
        logger.warning("Transcript not erased for %s: %s", request_id, e)

    try:
        from ...continuity.state_store import ACTOR_USER, StateStore
        receipts = StateStore().redact_request(request_id, actor=ACTOR_USER)
    except Exception as e:
        logger.warning("Ledger not redacted for %s: %s", request_id, e)

    logger.info(
        "Forgot guest session %s: %d message(s), %d ledger row(s)",
        session_id, messages, receipts,
    )
    return {
        "status": "ok",
        "session_id": session_id,
        "request_id": request_id,
        "messages_removed": messages,
        "ledger_rows_redacted": receipts,
    }


@router.get("/api/guest")
async def guest_status() -> Dict[str, Any]:
    live = guest.current_guest()
    return {
        "fronting": live.to_dict() if live else None,
        # Present whether or not a guest fronts, so the pill never has to
        # guess: no guest means no private sources, always.
        "private_sources": _private_sources_payload() if live else {},
    }
