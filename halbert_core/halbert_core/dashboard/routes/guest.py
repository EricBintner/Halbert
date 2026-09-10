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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ...federation.peer_middleware import PeerContext, require_local_admin, require_peer_auth
from ...persona import guest, guest_homes, private_sources
from ...persona.admission import (
    ADMISSION_DISPATCH,
    Gate,
    GateEffect,
    IngressDecision,
    REASON_TEXT,
    allow,
    block,
    decide_ingress,
    deny_payload,
)
from ...persona.guest_announce import (
    EVENT_TYPE as _EVENT_TYPE,
    announce_fronting,
    ended_event as _ended_event,
    ensure_announcer as _ensure_announcer,
    fronting_event as _fronting_event,
    offered_by_for,
    own_name as _own_name,
)
from ...proactive.events import ProactiveEvent, get_event_bus

logger = logging.getLogger("halbert.dashboard.guest")

router = APIRouter()

EVENT_TYPE = _EVENT_TYPE


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
    #: Which API shape this house speaks — "default" or "h3".
    profile: str = "default"


class BecomeRequest(BaseModel):
    """"Be Marnie" — a name and, when two homes have one, which home."""
    name: str
    base_url: str = ""
    # Bounded like PullRequest's: unbounded, an out-of-range value reached
    # guest.offer's own validation and surfaced as a 500.
    ttl_seconds: float = Field(
        default=guest.DEFAULT_TTL_SECONDS, ge=1.0, le=guest.MAX_TTL_SECONDS)


# ---------------------------------------------------------------------------
# Named-gate admission (PACKET-02 C1)
# ---------------------------------------------------------------------------

# Every route's guards, as an ordered gate list. A deny is no longer an
# opaque status: each request produces an IngressDecision
# (persona/admission.py), and a refusal answers with the decisive gate and
# its reason code, so any "no" can be explained after the fact.
#
# Halley's warning, made mechanical: this seam fails CLOSED on unwritten
# policy. A route id with no entry below is refused admission outright
# (``no_gate_list_configured``) — it never silently allows — and a
# registry-completeness test keeps every route the router serves covered.
#
# Warrant-layer composition rule (packet, 2026-09-07): these gates grade
# ADMISSION — capability. The claims ladder (persona/claims.py) grades
# identity claims and the warrant layer grades legitimacy; neither is
# chained behind the other.

# R-01 Phase E (A12-G6): the reason-text registry and these three
# helpers moved to persona/admission.py, beside the decision they render,
# so the talk door answers in the same shape instead of hand-copying it.
# The names are kept as module-local aliases: they are used a few dozen
# times below, and the gate builders read better without a prefix.
_REASON_TEXT = REASON_TEXT
_allow = allow
_block = block
_deny_payload = deny_payload


# Gate builders. Each sees the raw request, the authenticated peer (the
# app's side only; None elsewhere), and the parsed body when the route has
# one. They are read-only: every state change still happens in the handler
# and in persona/guest.py, which remain the authority.

async def _local_admin_gate(request: Request, peer, body) -> Gate:
    """``require_local_admin`` as a named gate. The route used to carry the
    same check as a FastAPI dependency; the gate calls the very same
    function, so there is one boundary check, not two."""
    try:
        await require_local_admin(request)
    except HTTPException:
        return _block("local_admin", "boundary", "not_local_admin", 403)
    return _allow("local_admin", "boundary", reason="local_admin")


async def _peer_identity_gate(request: Request, peer, body) -> Gate:
    """The pairing-token boundary (``require_peer_auth``) ran as the route's
    dependency before this gate list and produced the peer; the gate
    records that outcome in the decision, and fails closed if no
    authenticated peer reached the handler."""
    if peer is None:
        return _block("peer_token", "identity", "peer_token_missing", 401)
    return _allow(
        "peer_token", "identity", reason="peer_authenticated",
        node_id=peer.node_id,
    )


async def _session_free_gate(request: Request, peer, body) -> Gate:
    """One face at a time. The peer that offered the live session may
    replace its own; nobody else may offer over it."""
    live = guest.current_guest()
    if live is None:
        return _allow("session_free", "session")
    if peer is not None and live.offered_by == peer.node_id:
        return _allow("session_free", "session", reason="replaces_own_session")
    return _block(
        "session_free", "session", "guest_already_fronting", 409,
        fronting=live.offered_by,
    )


async def _session_live_gate(request: Request, peer, body) -> Gate:
    live = guest.current_guest()
    if live is None or live.id != body.session_id:
        return _block("session_live", "session", "no_such_session", 404)
    return _allow("session_live", "session", reason="session_live")


async def _session_owned_gate(request: Request, peer, body) -> Gate:
    live = guest.current_guest()
    if live is not None and live.offered_by != peer.node_id:
        return _block(
            "session_owned", "session", "session_owned_by_other_peer", 403,
            offered_by=live.offered_by,
        )
    return _allow("session_owned", "session", reason="owned_by_caller")


async def _withdraw_owned_gate(request: Request, peer, body) -> Gate:
    """Withdrawing with nothing fronting is not a deny — the route answers
    ``idle``. Only another peer's session is refused."""
    live = guest.current_guest()
    if live is None:
        return _allow("session_owned", "session", reason="no_live_session")
    if live.offered_by != peer.node_id:
        return _block(
            "session_owned", "session", "session_owned_by_other_peer", 403,
            offered_by=live.offered_by,
        )
    return _allow("session_owned", "session", reason="owned_by_caller")


async def _guest_fronting_gate(request: Request, peer, body) -> Gate:
    if guest.current_guest() is None:
        return _block("guest_fronting", "session", "no_guest_fronting", 409)
    return _allow("guest_fronting", "session", reason="guest_fronting")


async def _forget_target_gate(request: Request, peer, body) -> Gate:
    """Forgetting needs a session to forget: one named, or the one
    fronting. Neither is a refuse-the-caller deny — it is the request
    that is incomplete, so the gate stays at 409 like the check it
    replaces."""
    if not body.session_id.strip() and guest.current_guest() is None:
        return _block("forget_target", "session", "no_session_to_forget", 409)
    return _allow("forget_target", "session", reason="session_named")


async def _admit(
    route_id: str,
    request: Request,
    peer: Optional[PeerContext] = None,
    body: Any = None,
) -> IngressDecision:
    """Walk this route's ordered gate list and decide admission.

    Unwritten policy denies: a route id with no gate list configured is
    refused (403, ``no_gate_list_configured``) — never silently allowed.
    """
    builders = _ROUTE_GATES.get(route_id)
    if builders is None:
        raise HTTPException(
            status_code=403, detail=_deny_payload(
                "route_registry", "no_gate_list_configured"),
        )
    gates = []
    for build in builders:
        gates.append(await build(request, peer, body))
    decision = decide_ingress(gates)
    if decision.admission != ADMISSION_DISPATCH:
        status = 403
        for gate in decision.gate_graph:
            if gate.id == decision.decisive_gate:
                status = gate.facts.get("http_status", 403)
                break
        logger.info(
            "guest ingress %s: dropped at %s (%s)",
            route_id, decision.decisive_gate, decision.reason_code,
        )
        raise HTTPException(
            status_code=status,
            detail=_deny_payload(decision.decisive_gate, decision.reason_code),
        )
    logger.debug("guest ingress %s: dispatch at %s", route_id, decision.decisive_gate)
    return decision


# The ordered gate list per route, keyed by "METHOD path". The
# registry-completeness test in halbert_core/tests/persona/
# test_admission_wiring.py refuses a route on the router without an entry.
_ROUTE_GATES: Dict[str, Any] = {
    # The app's side — the pairing token is the boundary; the session
    # checks below it are what the token permits.
    "POST /api/guest/offer": (_peer_identity_gate, _session_free_gate),
    "POST /api/guest/heartbeat": (
        _peer_identity_gate, _session_live_gate, _session_owned_gate,
    ),
    "POST /api/guest/withdraw": (_peer_identity_gate, _withdraw_owned_gate),
    # The user's side — this machine's operator only, deliberately not
    # satisfiable by a peer token. The one-session-at-a-time conflict on
    # pull stays with guest.offer's own GuestConflict (it alone knows
    # whether the caller's home replaces its own session).
    "POST /api/guest/pull": (_local_admin_gate,),
    "POST /api/guest/end": (_local_admin_gate,),
    "GET /api/guest/homes": (_local_admin_gate,),
    "POST /api/guest/homes": (_local_admin_gate,),
    "DELETE /api/guest/homes": (_local_admin_gate,),
    "GET /api/guest/available": (_local_admin_gate,),
    "POST /api/guest/become": (_local_admin_gate,),
    "POST /api/guest/private/assign": (_local_admin_gate, _guest_fronting_gate),
    "POST /api/guest/private/release": (_local_admin_gate,),
    "GET /api/guest/private/sources": (_local_admin_gate,),
    "POST /api/guest/forget": (_local_admin_gate, _forget_target_gate),
    "GET /api/guest": (_local_admin_gate,),
}


# ---------------------------------------------------------------------------
# Announcing
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The app's side
# ---------------------------------------------------------------------------

@router.post("/api/guest/offer")
async def offer_persona(
    request: OfferRequest,
    raw_request: Request,
    peer: PeerContext = Depends(require_peer_auth),
) -> Dict[str, Any]:
    """Lend this machine a persona for a session."""
    await _admit("POST /api/guest/offer", raw_request, peer=peer, body=request)
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
    raw_request: Request,
    peer: PeerContext = Depends(require_peer_auth),
) -> Dict[str, Any]:
    await _admit("POST /api/guest/heartbeat", raw_request, peer=peer, body=request)
    try:
        session = guest.heartbeat(request.session_id, offered_by=peer.node_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="No live guest session with that id")
    except guest.GuestConflict as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"status": "ok", "session": session.to_dict()}


@router.post("/api/guest/withdraw")
async def withdraw_persona(
    raw_request: Request,
    peer: PeerContext = Depends(require_peer_auth),
) -> Dict[str, Any]:
    await _admit("POST /api/guest/withdraw", raw_request, peer=peer)
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

@router.post("/api/guest/pull")
async def pull_persona(request: PullRequest, raw_request: Request) -> Dict[str, Any]:
    """Fetch a persona from a sibling's home and wear it. The session is
    kept alive by pinging the home, since nobody there is heartbeating."""
    await _admit("POST /api/guest/pull", raw_request, body=request)
    from ...persona import sibling

    payload = request.model_dump()
    # A remembered home knows which API shape it speaks; the pull request does
    # not carry it. Without this the session talks to the default mount for
    # the rest of its life and an h3 home answers nothing after the listing.
    known = guest_homes.get_home(payload.get("base_url", ""))
    if known is not None:
        payload.setdefault("profile", known.profile)
        if not payload.get("token"):
            payload["token"] = known.token
    try:
        home = guest.GuestHome.from_payload(payload)
    except guest.GuestValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _ensure_announcer()
    from urllib.parse import urlparse
    who = home.label or (urlparse(home.base_url).netloc or home.base_url)
    try:
        session, dropped = await asyncio.to_thread(
            sibling.install_from_home,
            home,
            offered_by=offered_by_for(home.base_url),
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


@router.post("/api/guest/end")
async def end_session(raw_request: Request) -> Dict[str, Any]:
    """The Presence Pill's control: the user takes the face off."""
    await _admit("POST /api/guest/end", raw_request)
    _ensure_announcer()
    ended = guest.withdraw(reason="ended_by_user", by="user")
    if ended is None:
        return {"status": "idle", "session": None}
    return {"status": "ok", "session": ended.to_dict()}


# ---------------------------------------------------------------------------
# The homes whose personas this machine may wear
# ---------------------------------------------------------------------------

@router.get("/api/guest/homes")
async def list_homes(raw_request: Request) -> Dict[str, Any]:
    """The homes this machine knows. Tokens are never returned."""
    await _admit("GET /api/guest/homes", raw_request)
    return {"homes": [h.to_dict() for h in guest_homes.list_homes()]}


@router.post("/api/guest/homes")
async def add_home(request: HomeRequest, raw_request: Request) -> Dict[str, Any]:
    await _admit("POST /api/guest/homes", raw_request, body=request)
    try:
        record = guest_homes.add_home(
            request.base_url, request.label, request.token, request.profile,
        )
    except guest_homes.BadHome as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "home": record.to_dict()}


@router.delete("/api/guest/homes")
async def forget_home(raw_request: Request, base_url: str) -> Dict[str, Any]:
    await _admit("DELETE /api/guest/homes", raw_request)
    try:
        removed = guest_homes.remove_home(base_url)
    except guest_homes.BadHome as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok" if removed else "unknown"}


@router.get("/api/guest/available")
async def available_personas(raw_request: Request) -> Dict[str, Any]:
    """Every persona this machine could wear right now, across every home.

    A home that does not answer is reported, not raised: "be Marnie" should
    still work when the other house is asleep.
    """
    await _admit("GET /api/guest/available", raw_request)
    return await asyncio.to_thread(guest_homes.available_personas)


@router.post("/api/guest/become")
async def become(request: BecomeRequest, raw_request: Request) -> Dict[str, Any]:
    """Wear the persona with this name, wherever it lives.

    The verb the user actually says. ``/api/guest/pull`` still takes a URL, a
    persona id and a token, which is a fine thing for a script and a poor
    thing for a person; this resolves a name against the known homes and
    keeps the credential on disk where it belongs.
    """
    await _admit("POST /api/guest/become", raw_request, body=request)
    try:
        match = await asyncio.to_thread(
            guest_homes.resolve_persona, request.name, request.base_url,
        )
    except guest_homes.Ambiguous as e:
        raise HTTPException(status_code=409, detail=str(e))
    except guest_homes.NoSuchPersona as e:
        raise HTTPException(status_code=404, detail=str(e))
    record = guest_homes.get_home(match["base_url"])
    return await pull_persona(PullRequest(
        base_url=match["base_url"],
        persona_id=match["persona_id"],
        token=record.token if record else "",
        label=match["home_label"],
        ttl_seconds=request.ttl_seconds,
    ), raw_request)


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


@router.post("/api/guest/private/assign")
async def assign_private_source(
    request: PrivateSourceRequest, raw_request: Request,
) -> Dict[str, Any]:
    """Hand one source to the fronting guest for the rest of its session.

    Local only, and deliberately not satisfiable by a peer token: the app that
    lent the persona must not be able to award itself the user's camera.
    """
    await _admit("POST /api/guest/private/assign", raw_request, body=request)
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


@router.post("/api/guest/private/release")
async def release_private_source(
    request: PrivateSourceRequest, raw_request: Request,
) -> Dict[str, Any]:
    """Take one source back. The guest keeps fronting."""
    await _admit("POST /api/guest/private/release", raw_request, body=request)
    try:
        private_sources.release(request.source_id)
    except private_sources.BadSourceId as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "private_sources": _private_sources_payload()}


@router.get("/api/guest/private/sources")
async def list_private_sources(raw_request: Request) -> Dict[str, Any]:
    """Everything the user could hand over, across the senses, with its owner."""
    await _admit("GET /api/guest/private/sources", raw_request)
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


@router.post("/api/guest/forget")
async def forget_session(request: ForgetRequest, raw_request: Request) -> Dict[str, Any]:
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
    await _admit("POST /api/guest/forget", raw_request, body=request)
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
    failed = []

    threads_blanked = 0
    try:
        from ...agents.conversation_sqlite import SqliteConversationStore
        store = SqliteConversationStore()
        # Before the delete: afterwards there is nothing left to join on.
        threads = store.threads_for_request(request_id)
        messages = store.forget_request(request_id)
        for thread_id in threads:
            if store.blank_thread_words(thread_id):
                threads_blanked += 1
    except Exception as e:
        logger.warning("Transcript not erased for %s: %s", request_id, e)
        failed.append(f"transcript: {e}")

    try:
        from ...continuity.state_store import ACTOR_USER, StateStore
        receipts = StateStore().redact_request(request_id, actor=ACTOR_USER)
    except Exception as e:
        logger.warning("Ledger not redacted for %s: %s", request_id, e)
        failed.append(f"ledger: {e}")

    if failed:
        # "ok" on a half-done erasure is the worst possible answer: the user
        # believes the words are gone and stops looking. Say which half.
        raise HTTPException(
            status_code=500,
            detail=(
                f"Partly forgotten. Removed {messages} message(s) and redacted "
                f"{receipts} ledger row(s); these failed and the words remain — "
                + "; ".join(failed)
            ),
        )

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
        "threads_blanked": threads_blanked,
    }


@router.get("/api/guest")
async def guest_status(raw_request: Request) -> Dict[str, Any]:
    await _admit("GET /api/guest", raw_request)
    live = guest.current_guest()
    return {
        "fronting": live.to_dict() if live else None,
        # Present whether or not a guest fronts, so the pill never has to
        # guess: no guest means no private sources, always.
        "private_sources": _private_sources_payload() if live else {},
    }
