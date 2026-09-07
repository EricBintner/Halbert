# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The verb, said in the conversation: "be Marnie".

`.handoff/HANDOFF-OPUS-GUEST-PERSONA-NEXT-STEPS-2026-09-06.md` N5. The route
existed first (``POST /api/guest/become``); this is the same act reachable
from a sentence instead of a click, because "be Marnie" is a thing people say
and not a thing they go to Settings for.

**Denied to a guest, and that is the whole safety story.** A guest that could
call this could swap itself for another persona — walk out of its own session
into someone else's face without the user asking, and without the user
learning it had happened from anything but the pill. So the name is on
``GUEST_DENIED_TOOLS``, and ``guest_tools`` refuses it at ``execute()`` as
well as hiding it from the schemas, because a guest inherits a conversation
whose history holds Halbert's own calls and a model imitates calls it was not
offered.

It resolves through ``guest_homes.resolve_persona`` — the same function the
route uses. Two callers resolving a name two ways is how "be Marnie" starts
meaning different faces depending on where you said it.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("halbert.persona.become")

BECOME_TOOL_NAME = "become_persona"

BECOME_TOOL_SCHEMA: Dict[str, Any] = {
    "name": BECOME_TOOL_NAME,
    "description": (
        "Wear a persona from one of this machine's known homes — what the user "
        "means by \"be Marnie\". The machine keeps its own tools, memory and "
        "rules underneath; only the name, manner and voice change. Call this "
        "when the user asks for someone by name. With no name, it lists who is "
        "available."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Who to be. Omit to list who is available.",
            },
            "home": {
                "type": "string",
                "description": (
                    "Which home, when the same name lives in more than one. "
                    "The base URL as the listing gives it."
                ),
            },
        },
        "required": [],
    },
}


async def become_persona(args: Dict[str, Any]) -> str:
    """Wear the named persona, or say who is available.

    Returns prose rather than a payload: the model is about to speak to the
    user about it, and the failure cases — nobody by that name, that name in
    two houses, no homes known — are things the user has to be told rather
    than a status code to interpret.
    """
    import asyncio

    from . import guest, guest_homes, sibling

    name = " ".join(str((args or {}).get("name") or "").split())
    home_url = str((args or {}).get("home") or "").strip()

    if not name:
        catalogue = await asyncio.to_thread(guest_homes.available_personas)
        return _describe(catalogue)

    try:
        match = await asyncio.to_thread(guest_homes.resolve_persona, name, home_url)
    except guest_homes.Ambiguous as e:
        return str(e)
    except guest_homes.NoSuchPersona as e:
        return str(e)

    from .guest_announce import announce_fronting_async, offered_by_for

    record = guest_homes.get_home(match["base_url"])
    home = guest.GuestHome(
        base_url=match["base_url"],
        persona_id=match["persona_id"],
        token=record.token if record else "",
        label=match["home_label"],
        # Carried, not dropped: without it every call after the listing —
        # the pull, every memory write, every recall — goes to the default
        # mount and an h3 home answers none of them.
        profile=record.profile if record else match.get("profile", "default"),
    )
    try:
        session, dropped = await asyncio.to_thread(
            sibling.install_from_home,
            home,
            # The same spelling the route uses. ``guest.offer`` refuses a
            # second session from a *different* peer, so two spellings meant
            # switching faces between the pill and the chat was refused as
            # another peer's session.
            offered_by=offered_by_for(match["base_url"]),
            offered_by_name=match["home_label"],
        )
    except sibling.HomeUnreachable as e:
        return f"{match['name']}'s home did not answer: {e}"
    except Exception as e:
        return f"Could not wear {match['name']}: {e}"

    # The route announces; before this the chat verb did not — so a face put
    # on by saying so changed who was speaking with nothing on the bell, and
    # (because the end-of-session observer is installed by the same call) that
    # session's *ending* went unannounced too, however it ended.
    await announce_fronting_async(session)
    logger.info("Now fronting as %s from %s", session.persona.name, match["home_label"])
    note = f" (ignored: {', '.join(dropped)})" if dropped else ""
    return (
        f"{session.persona.name} is now speaking, from {match['home_label']}. "
        f"The tools, memory and rules are still this machine's.{note}"
    )


def _describe(catalogue: Dict[str, Any]) -> str:
    personas = catalogue.get("personas") or []
    unreachable = [u["home"] for u in (catalogue.get("unreachable") or [])]
    if not personas:
        if unreachable:
            return (
                "No personas available right now; "
                f"{', '.join(unreachable)} did not answer."
            )
        return (
            "No homes are known yet, so there is nobody to be. Homes are added "
            "in Settings."
        )
    lines = [f"- {p['name']} (at {p['home_label']})" for p in personas]
    tail = f"\n{', '.join(unreachable)} did not answer." if unreachable else ""
    return "Available to be:\n" + "\n".join(lines) + tail
