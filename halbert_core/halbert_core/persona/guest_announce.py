# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Announcing a face going on and coming off, from wherever it was put on.

The route announced; the chat verb did not. So "be Marnie" typed into the
conversation changed who was speaking with nothing on the bell, nothing in the
conversation, and — worse — without the end-of-session observer installed, so
that session's *ending* went unannounced too, whichever way it ended.

The announcement is not decoration. It is how the user learns the face
changed, and I4 says they must always be able to tell what is holding the
tools. A way of putting a face on that skips it is a way of putting a face on
quietly.

Lives here rather than in the route so both callers reach the same code
without a tool importing a web handler.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("halbert.persona.guest_announce")

EVENT_TYPE = "guest_session"
_ANNOUNCER_KEY = "persona.guest_announce"


def own_name() -> str:
    try:
        from ..identity import resolve_entity_name
        return resolve_entity_name()
    except Exception:
        return "Halbert"


def fronting_event(session: Any):
    from ..proactive.events import ProactiveEvent

    who = session.persona.name
    by = session.offered_by_name or session.offered_by
    own = own_name()
    return ProactiveEvent.create(
        type=EVENT_TYPE,
        severity="info",
        title=f"{who} is speaking for {own}",
        body=f"{by} lent {own} the persona {who} for this session. "
             f"{own} keeps its tools, memory and rules underneath.",
        data={"state": "fronting", **session.to_dict()},
    )


def ended_event(session: Any):
    from ..proactive.events import ProactiveEvent

    who = session.persona.name
    own = own_name()
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


def publish_from_anywhere(event) -> None:
    """Publish from a sync caller, whichever thread it is on."""
    from ..proactive.events import get_event_bus

    bus = get_event_bus()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        loop.create_task(bus.publish(event))
    else:
        asyncio.run(bus.publish(event))


def _announce_end(session: Any) -> None:
    try:
        publish_from_anywhere(ended_event(session))
    except Exception as e:
        logger.warning("Guest session ending not announced: %s", e)


def ensure_announcer() -> None:
    """Idempotent: the same key re-subscribes, so a reset (tests, a reload)
    cannot leave endings silent."""
    from .guest import on_session_end

    on_session_end(_announce_end, key=_ANNOUNCER_KEY)


def announce_fronting(session: Any) -> None:
    """Install the ending observer and announce the beginning, in that order.

    The observer first: a session that ends before its start was announced is
    strange, but a session whose ending is never announced is a face the user
    is not told came off.
    """
    ensure_announcer()
    try:
        publish_from_anywhere(fronting_event(session))
    except Exception as e:
        logger.warning("Guest session not announced: %s", e)


async def announce_fronting_async(session: Any) -> None:
    """The same, awaited, for a caller that is already in the loop.

    ``publish_from_anywhere`` schedules a task when a loop is running, so a
    caller that returns immediately afterwards can finish before the event is
    delivered — which is how the chat verb ended up announcing nothing that
    anyone saw. An async caller awaits instead.
    """
    ensure_announcer()
    try:
        from ..proactive.events import get_event_bus
        await get_event_bus().publish(fronting_event(session))
    except Exception as e:
        logger.warning("Guest session not announced: %s", e)


def offered_by_for(base_url: str) -> str:
    """The peer id a home-pulled session is stamped with.

    One spelling, because ``guest.offer`` refuses a second session from a
    *different* peer: the pill stamping ``home:h2.lan:8002`` and the chat verb
    stamping ``home:http://h2.lan:8002`` meant switching faces across the two
    was refused as another peer's session, and the only way out was ending the
    first by hand.
    """
    from urllib.parse import urlparse

    return f"home:{urlparse(str(base_url or '')).netloc or base_url}"
