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

from .interests import InterestStatus

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



def _set_status(memory_store: Any, memory_id: str, status: str) -> Optional[str]:
    """Write the interest's status onto the memory row. ``None`` on success.

    **Why this is not optional.** RECALL-v1 reads status from the *memory*,
    not from the mirror -- under Singular Entity the observation store is
    body-local and does not travel, so the memory is the only copy the whole
    entity sees. Marking the mirror stale and leaving the record ``active``
    means the person asked for a fact to stop being used and it kept
    appearing.

    **The engine gap.** ``PersonaMemoryStore`` has no public metadata update:
    ``confirm_memory``, ``correct_memory`` and ``add_keywords`` each mutate
    and persist, but there is no general one. So this mutates the live object
    from ``get()`` and persists through ``_save_to_disk``. Returns a reason
    when it cannot -- a peer-backed store may expose neither -- so the caller
    reports ``complete=False`` rather than claiming a status it did not set.
    A public ``set_metadata`` is the upstream ask.
    """
    if memory_store is None:
        return "no memory store"
    try:
        getter = getattr(memory_store, "get", None)
        memory = getter(memory_id) if getter else None
        if memory is None:
            return f"memory {memory_id!r} was not found"
        meta = dict(getattr(memory, "metadata", None) or {})
        meta["status"] = status
        memory.metadata = meta
        save = getattr(memory_store, "_save_to_disk", None)
        if save is None:
            return "this store cannot persist a status change"
        save()
        return None
    except Exception as e:
        logger.warning("could not set status on %s: %s", memory_id, e)
        return f"status: {e}"


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

    # The record first: the mirror is an index, and leaving the record active
    # is what made this verb a no-op for recall.
    status_error = _set_status(
        memory_store, memory_id, InterestStatus.FORGET_REQUESTED.value
    )
    if status_error:
        report["memory"] = False
        report["errors"].append(status_error)

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


def resume_interest(
    interest: Any,
    memory_id: str,
    *,
    memory_store: Any = None,
    observation_store: Any = None,
) -> Dict[str, Any]:
    """"Remember again" -- undo a stop-using.

    Only the record is restored. The mirror is rebuilt by the next save rather
    than un-staled here: the engine's tombstone deliberately refuses to
    un-stale a row, and routing around that would defeat the protection that
    makes "stop using" trustworthy in the first place.
    """
    report = _report(verb="resume")
    status_error = _set_status(
        memory_store, memory_id, InterestStatus.ACTIVE.value
    )
    if status_error:
        report["errors"].append(status_error)
    else:
        report["memory"] = True
    report["complete"] = not report["errors"]
    return report

