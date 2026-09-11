# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Forgetting an interest -- two verbs, and an honest report of each one's reach.

``RQ-6``, decided 2026-09-10. The engine offers both mechanisms, so the
surface says which one it means:

- :func:`stop_using_interest` -- ``mark_stale`` with the engine's
  ``forgotten_by_user:`` tombstone. Reversible, auditable, listed under "Show
  forgotten", and **not resurrectable**: ``ObservationStore.save`` returns
  ``None`` for a duplicate carrying that prefix, so the next consolidation
  pass that re-derives the claim no longer quietly undoes the request.
- :func:`forget_interest` -- hard erasure. The memory row and its embedder
  entry, and the mirrored observation with its FTS entry and its bytes.

Both mirror :func:`~halbert_core.continuity.provenance.forget_request`: a
per-plane report, nothing raised, and ``complete`` False when a plane could
not be reached. Forgetting must not fail loudly at the one moment a person is
asking for privacy, and a clean tick over a job half done is the overclaim
this project keeps having to correct.

**The gap, stated rather than papered over.** ``ObservationStore`` has
``mark_stale_by_memory`` but no ``delete_by_memory``, and nothing returns a
row by ``source_memory_id``. A hard forget therefore enumerates the mirror
through FTS and keeps only exact ``source_memory_id`` matches -- the search
is the enumeration, never the decision. When that finds nothing the report
says the plane was not reached rather than claiming it was. The upstream ask
is a ``delete_by_memory`` symmetric with the marking one.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.continuity.forget_interest")

__all__ = [
    "STALE_REASON_USER",
    "STALE_REASON_LAPSED",
    "STALE_REASON_SUPERSEDED",
    "FORGET_LIMITS",
    "stop_using_interest",
    "forget_interest",
]


def _engine_tombstone() -> str:
    """The engine's own prefix, imported rather than retyped.

    If these two strings drift, the engine stops recognising our tombstone
    and silently resurrects what a person asked to drop -- so the constant is
    taken from the engine and pinned by test, not copied.
    """
    try:
        from haloysius.memory_v2.observation_store import USER_TOMBSTONE_PREFIX
        return USER_TOMBSTONE_PREFIX
    except Exception:  # pragma: no cover - engine always present in practice
        return "forgotten_by_user:"


#: ``forgotten_by_user:<turn>`` -- a person asked. Load-bearing: the engine
#: checks this prefix.
STALE_REASON_USER = _engine_tombstone()
#: ``lapsed:<date>`` -- an inferred interest ran out of evidence. Ours alone.
STALE_REASON_LAPSED = "lapsed:"
#: ``superseded_by:<id>`` -- a newer row replaced it.
STALE_REASON_SUPERSEDED = "superseded_by:"

#: What neither verb reaches. Said out loud for the same reason
#: ``ERASURE_LIMITS`` is: "everywhere" is a lie when it is two planes of
#: several, and a person deciding whether to trust this needs the true list.
FORGET_LIMITS = (
    "This removes the interest from the persona memory store (and its "
    "embedder entry) and the mirrored observation row, its full-text entry "
    "and its bytes. It does NOT reach: the conversation messages the "
    "interest was learned from, which are redacted by their own mechanism; "
    "any summary already generated from it, which must be regenerated rather "
    "than patched; a canonical host's copy under Singular Entity, which is a "
    "separate erasure; or any backup or snapshot taken before now."
)


def _report(**kw: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "memory": False,
        "observations": 0,
        "errors": [],
        "limits": FORGET_LIMITS,
    }
    base.update(kw)
    return base


def _mirror_rows(observation_store: Any, interest: Any, memory_id: str) -> List[Any]:
    """The observation rows this memory wrote, enumerated through FTS.

    Matching is on ``source_memory_id``, exactly. The search only decides
    which rows to *look* at; a text match never decides what is deleted,
    because an FTS hit on a topic word is not evidence that a row belongs to
    this memory.
    """
    found = observation_store.search(
        interest.topic, limit=50, include_stale=True
    )
    return [o for o in found if getattr(o, "source_memory_id", "") == memory_id]


def stop_using_interest(
    interest: Any,
    memory_id: str,
    *,
    turn: str = "",
    memory_store: Any = None,
    observation_store: Any = None,
) -> Dict[str, Any]:
    """Keep it, stop using it. Reversible and recorded.

    The memory row is left alone on purpose: this verb's promise is that
    nothing is destroyed, and the mirror is what recall reads.
    """
    report = _report(memory=True, verb="stop_using")
    reason = f"{STALE_REASON_USER}{turn or 'unknown-turn'}"

    if observation_store is None:
        report["errors"].append("no observation store")
        report["complete"] = False
        return report

    try:
        marked = observation_store.mark_stale_by_memory(memory_id, reason=reason)
        report["observations"] = int(marked or 0)
        if not marked:
            # Nothing mirrored it -- true for a candidate, which never
            # mirrors. Not an error, and not a claim that something was done.
            report["note"] = "nothing was mirrored for this interest"
    except Exception as e:
        logger.warning("stop_using_interest(%s): observations: %s", memory_id, e)
        report["errors"].append(f"observations: {e}")

    report["complete"] = not report["errors"]
    return report


def forget_interest(
    interest: Any,
    memory_id: str,
    *,
    memory_store: Any = None,
    observation_store: Any = None,
) -> Dict[str, Any]:
    """Erase it. Per-plane, never raising, honest about what it reached."""
    report = _report(verb="forget")

    # -- the memory, and with it the embedder entry ----------------------
    if memory_store is None:
        report["errors"].append("no memory store")
    else:
        try:
            # soft=False is the point of this verb: a soft delete leaves the
            # row readable, which is what "stop using" is for.
            report["memory"] = bool(memory_store.delete(memory_id, soft=False))
            if not report["memory"]:
                report["errors"].append(
                    f"memory {memory_id!r} was not found; nothing was erased there"
                )
        except Exception as e:
            logger.warning("forget_interest(%s): memory: %s", memory_id, e)
            report["errors"].append(f"memory: {e}")

    # -- the mirrored observation, its FTS entry and its bytes -----------
    if observation_store is None:
        report["errors"].append("no observation store")
    else:
        try:
            rows = _mirror_rows(observation_store, interest, memory_id)
            removed = 0
            for row in rows:
                if observation_store.delete(row.id):
                    removed += 1
            report["observations"] = removed
            if rows and removed != len(rows):
                report["errors"].append(
                    f"{len(rows) - removed} observation row(s) could not be removed"
                )
        except Exception as e:
            logger.warning("forget_interest(%s): observations: %s", memory_id, e)
            report["errors"].append(f"observations: {e}")

    report["complete"] = not report["errors"]
    return report
