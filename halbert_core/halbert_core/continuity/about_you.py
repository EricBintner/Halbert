# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
""""What I remember about you" -- one read model, two readers.

``RQ-5``: a remembered fact is **data**, not a directive. Lenses invariant 5
governs *directives* -- skills, lenses, ``being.yml`` -- where the file is the
mechanism, so an editable file with its source shown is right there. A fact
about a person is governed by the four-whys law instead: inspectable in the
UI, with who / when / how it was learned shown, edited through the store, and
forgotten with a statement of reach.

The Settings list and the conversational *"what do you remember about me"*
answer come from **this one function**. Two readers of one store cannot
disagree about what is remembered; two implementations of the same list can,
and eventually would.

Deliberately absent: any confidence number. The engine derives one from
provenance, and showing it would invite the reader to weigh a thing the
system cannot justify numerically. The origin and the evidence are what a
person can actually check.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.continuity.about_you")

__all__ = ["describe_learning", "list_remembered", "remembered_lines"]


def describe_learning(interest: Any) -> str:
    """How this came to be known, in plain words.

    "You told me" / "Noticed across N conversations over W days" / "You
    corrected me". Never a score.
    """
    try:
        origin = getattr(interest.origin, "value", interest.origin)
        if origin == "stated":
            return "You told me"
        evidence = dict(getattr(interest, "evidence", None) or {})
        threads = evidence.get("threads") or []
        days = evidence.get("days")
        window = evidence.get("window_days")
        if origin == "inferred_confirmed" and threads and days and window:
            return (
                f"Noticed across {len(threads)} conversations on {days} days "
                f"in {window}, and you confirmed it"
            )
        if origin == "inferred_confirmed":
            return "Noticed in conversation, and you confirmed it"
        return "Noticed in conversation, not yet confirmed"
    except Exception:
        logger.debug("could not describe how an interest was learned", exc_info=True)
        return "Origin not recorded"


def _when(interest: Any) -> str:
    raw = (
        getattr(interest, "last_confirmed_at", "")
        or getattr(interest, "last_evidenced_at", "")
        or getattr(interest, "first_seen_at", "")
    )
    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d")
    except Exception:
        return ""


def list_remembered(
    memory_store: Any,
    *,
    include_forgotten: bool = False,
) -> List[Dict[str, Any]]:
    """Every interest this person may be shown, newest first.

    Candidates are never listed. Nobody has confirmed them, so presenting one
    as "something I remember about you" would make the list claim more than
    the system is entitled to -- the same reason they are never injected.

    Never raises: a list that cannot be built is empty, and the surface says
    so, rather than the Settings page failing to load.
    """
    if memory_store is None:
        return []
    try:
        from .interests import Interest, InterestStatus

        rows: List[Dict[str, Any]] = []
        memories = getattr(memory_store, "list_memories", list)() or []
        for memory in memories:
            interest = Interest.from_persona_memory(memory)
            if interest is None:
                continue
            if interest.status is InterestStatus.CANDIDATE:
                continue
            forgotten = interest.status is not InterestStatus.ACTIVE
            if forgotten and not include_forgotten:
                continue
            rows.append({
                "memory_id": getattr(memory, "id", ""),
                "topic": interest.topic,
                "learned": describe_learning(interest),
                "when": _when(interest),
                "reason": interest.reason,
                "status": interest.status.value,
                "forgotten": forgotten,
                "actor": interest.actor,
                "speaker_role": interest.speaker_role,
            })
        rows.sort(key=lambda r: r["when"], reverse=True)
        return rows
    except Exception:
        logger.warning("could not list what is remembered", exc_info=True)
        return []


def remembered_lines(rows: List[Dict[str, Any]]) -> str:
    """The same rows as prose, for the conversational answer.

    Ends by stating the list is complete. Asked what it remembers, a model
    will otherwise round the list up to a plausible fifth item -- and an
    invented memory of a person is the worst thing this whole mechanism could
    produce.
    """
    if not rows:
        return (
            "I have nothing recorded about you. I only remember what you ask "
            "me to remember, and nothing else about you is known."
        )
    lines = [
        f"- {r['topic']} — {r['learned']}" + (f", {r['when']}" if r["when"] else "")
        for r in rows
    ]
    return (
        "Here is everything I have recorded about you:\n"
        + "\n".join(lines)
        + "\n\nThat is the complete list — nothing else about you is known. "
        "Do not add to it, and do not infer anything further."
    )
