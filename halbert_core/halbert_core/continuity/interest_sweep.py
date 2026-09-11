# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""``MEM-04``: what goes quiet on its own, and what never does.

Two clocks, and the difference between them is the whole module.

**An inferred interest lapses at 90 days without new evidence.** It was
always a guess the machine made and a person agreed to; when the evidence
stops, the guess stops. Letting it run forever would mean a fortnight of
work in March still colouring answers the following winter.

**A stated interest does not decay by time.** A person said it in their own
words. Nothing about the passage of time makes that less true, and a machine
that quietly forgot what it was told would be worse than one that never
listened. A stated interest ends one way only: the person retracts it, or
contradicts it. Never on a timer.

**An unanswered candidate expires at 30 days.** It was proposed, the aside
was offered or the list ignored, and nobody said yes. Keeping it forever
would leave a queue of unanswered questions about someone growing quietly.

Nothing here erases. A lapse is a status and a tombstone on the mirror, so
"Show forgotten" still holds it and "Remember again" still works -- the
machine losing interest must never be less reversible than the person
asking it to.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .interests import Interest, InterestStatus, Origin

logger = logging.getLogger("halbert.continuity.interest_sweep")

__all__ = [
    "INFERRED_LAPSE_DAYS",
    "CANDIDATE_EXPIRY_DAYS",
    "sweep_interests",
]

#: An inferred interest with no new evidence for this long goes quiet.
INFERRED_LAPSE_DAYS = 90

#: A candidate nobody answered stops waiting after this long.
CANDIDATE_EXPIRY_DAYS = 30

_DAY = 24 * 3600


def _epoch(stamp: str) -> Optional[float]:
    """An ISO timestamp as epoch seconds, or ``None`` when unreadable.

    Unreadable is deliberately not "very old": a row whose date cannot be
    parsed must not be swept on the strength of a parse failure.
    """
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(stamp)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except Exception:
        return None


def _last_evidence(interest: Interest) -> Optional[float]:
    """The newest thing that kept this interest alive."""
    stamps = [
        _epoch(interest.last_evidenced_at),
        _epoch(interest.last_confirmed_at),
        _epoch(interest.first_seen_at),
    ]
    known = [s for s in stamps if s is not None]
    return max(known) if known else None


def _due(interest: Interest, now: float) -> Optional[str]:
    """Why this row is due to go quiet, or ``None``.

    Returns the ``stale_reason`` to write, which is also the audit trail:
    ``lapsed:<date>`` says a machine did this on a date, and is a different
    claim from ``forgotten_by_user:<turn>``.
    """
    # A person's own words are not on a clock. Checked first and by origin,
    # not by status, so no later branch can reach a stated row by accident.
    if interest.origin is Origin.STATED:
        return None

    last = _last_evidence(interest)
    if last is None:
        return None
    age_days = (now - last) / _DAY

    if interest.status is InterestStatus.CANDIDATE:
        if age_days >= CANDIDATE_EXPIRY_DAYS:
            return f"expired:{datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat()}"
        return None

    if interest.status is InterestStatus.ACTIVE:
        if age_days >= INFERRED_LAPSE_DAYS:
            return f"lapsed:{datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat()}"
    return None


def sweep_interests(
    memory_store: Any = None,
    observation_store: Any = None,
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Retire what has run out of evidence. Never raises.

    Returns a per-outcome count plus the topics touched, so a caller can log
    what happened rather than that something did.
    """
    import time as _time

    ts = _time.time() if now is None else now
    report: Dict[str, Any] = {"lapsed": 0, "expired": 0, "errors": [], "topics": []}

    if memory_store is None:
        try:
            from ..integrations.cognition_wiring import get_persona_memory_store
            memory_store = get_persona_memory_store()
        except Exception:
            memory_store = None
    if memory_store is None:
        report["errors"].append("no memory store")
        return report

    if observation_store is None:
        try:
            from ..integrations.cognition_wiring import get_observation_store
            observation_store = get_observation_store()
        except Exception:
            observation_store = None

    try:
        memories = list(getattr(memory_store, "list_memories", list)() or [])
    except Exception as e:
        report["errors"].append(f"could not list memories: {e}")
        return report

    for memory in memories:
        interest = Interest.from_persona_memory(memory)
        if interest is None:
            continue
        reason = _due(interest, ts)
        if reason is None:
            continue
        memory_id = getattr(memory, "id", "")
        if _retire(memory_store, observation_store, memory_id, reason, report):
            report["topics"].append(interest.topic)
            key = "expired" if reason.startswith("expired:") else "lapsed"
            report[key] += 1

    if report["lapsed"] or report["expired"]:
        logger.info(
            "interest sweep: %s lapsed, %s expired (%s)",
            report["lapsed"], report["expired"], ", ".join(report["topics"]),
        )
    return report


def _retire(
    memory_store: Any,
    observation_store: Any,
    memory_id: str,
    reason: str,
    report: Dict[str, Any],
) -> bool:
    """Status on the record, tombstone on the mirror. The record decides.

    Same order and same reasoning as ``stop_using_interest``: recall reads
    status from the memory, because under Singular Entity the observation
    store is body-local and does not travel. A mirror marked stale beside a
    record still ``active`` is an interest that kept being used.
    """
    from .forget_interest import _set_status

    error = _set_status(memory_store, memory_id, InterestStatus.LAPSED.value)
    if error:
        report["errors"].append(error)
        return False

    # The mirror is an index. Failing to retire it costs search quality, not
    # correctness, so it is reported and not fatal.
    if observation_store is not None:
        try:
            observation_store.mark_stale_by_memory(memory_id, reason=reason)
        except Exception as e:
            report["errors"].append(f"observations: {e}")
    return True
