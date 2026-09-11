# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Promoting a candidate to a confirmed interest -- one place, two doors.

The conversational aside and the Settings list both end in a person saying
yes, and they must end in the *same* write. Two promotions would drift, and
the drift would be a candidate confirmed one way behaving differently from
one confirmed the other -- which is the kind of difference nobody would
think to look for.

``MEM-06`` accepts two kinds of reason: a human utterance, or a self-naming
rule. The tool passes the person's sentence; the Settings route passes the
name of the button they pressed. Both are honest about where the yes came
from, and neither is a sentence a model composed.

**Why this mutates rather than re-adds.** The candidate and the confirmation
share an id *and* their content, so ``smart_add`` treats the second as a
duplicate and merges it -- returning success while leaving the status
``candidate``. A caller would report "Recorded" and nothing would have
changed. That failure has now appeared four times in this workstream, always
with a green-looking write at the centre of it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .interests import Interest, InterestStatus, Origin

logger = logging.getLogger("halbert.continuity.confirm")

__all__ = ["confirm_candidate"]


def confirm_candidate(
    interest: Any,
    memory_id: str,
    *,
    reason: str,
    actor: str = "user",
    speaker_role: str = "",
    memory_store: Any = None,
    observation_store: Any = None,
) -> Dict[str, Any]:
    """Candidate to confirmed. Never raises; reports per plane.

    Returns the same report shape the forget verbs use, so a surface can
    render one thing.
    """
    report: Dict[str, Any] = {
        "verb": "confirm", "memory": False, "observations": 0, "errors": [],
    }

    if memory_store is None:
        report["errors"].append("no memory store")
        report["complete"] = False
        return report
    if not (reason or "").strip():
        # MEM-06 is not optional, and a confirmation with no reason is the
        # model-chosen write wearing a different hat.
        report["errors"].append("a confirmation needs a reason")
        report["complete"] = False
        return report

    try:
        if getattr(interest, "status", None) is not InterestStatus.CANDIDATE:
            report["errors"].append(
                f"{getattr(interest, 'topic', '')!r} is not an outstanding question"
            )
            report["complete"] = False
            return report

        memory = memory_store.get(memory_id)
        if memory is None:
            report["errors"].append(f"memory {memory_id!r} was not found")
            report["complete"] = False
            return report

        stamp = datetime.now(timezone.utc).isoformat()
        evidence = dict(getattr(interest, "evidence", None) or {})
        # Kept, not overwritten: it is why the machine asked, and "how did
        # you know to ask?" is a question the person is entitled to answer to.
        evidence["proposed_reason"] = getattr(interest, "reason", "")

        confirmed = Interest(
            topic=interest.topic,
            origin=Origin.INFERRED_CONFIRMED,
            status=InterestStatus.ACTIVE,
            reason=reason,
            actor=actor,
            speaker_role=speaker_role,
            body_id=getattr(interest, "body_id", ""),
            evidence=evidence,
            first_seen_at=getattr(interest, "first_seen_at", "") or stamp,
            last_evidenced_at=getattr(interest, "last_evidenced_at", "") or stamp,
            last_confirmed_at=stamp,
        )

        meta = dict(getattr(memory, "metadata", None) or {})
        meta.update(confirmed._metadata())
        memory.metadata = meta

        tags = list(getattr(memory, "tags", None) or [])
        if Origin.INFERRED.value in tags:
            tags[tags.index(Origin.INFERRED.value)] = Origin.INFERRED_CONFIRMED.value
            memory.tags = tags

        save = getattr(memory_store, "_save_to_disk", None)
        if save is None:
            report["errors"].append("this store cannot record a confirmation")
            report["complete"] = False
            return report
        save()
        report["memory"] = True

        # The engine's own confirmation path, which is what a person saying
        # yes actually is: it raises validation_count and the confidence
        # derived from it, rather than this module inventing a number.
        confirm = getattr(memory_store, "confirm_memory", None)
        if confirm is not None:
            try:
                confirm(memory_id)
            except Exception as e:
                report["errors"].append(f"confirmation count: {e}")

        report["observations"] = _mirror(confirmed, memory_id, observation_store)
        report["content"] = confirmed.content
    except Exception as e:
        logger.warning("could not confirm %s: %s", memory_id, e, exc_info=True)
        report["errors"].append(str(e))

    report["complete"] = not report["errors"] and report["memory"]
    return report


def _mirror(interest: Interest, memory_id: str, observation_store: Any) -> int:
    """The observation row a confirmed interest is entitled to.

    A candidate has none -- ``should_mirror`` is False for it -- so this is
    the moment the index gains the row, and it is the moment a person said
    yes. Absent rather than fatal: losing the index costs search quality,
    not the fact.
    """
    if not interest.should_mirror or not memory_id or observation_store is None:
        return 0
    try:
        saved = observation_store.save(
            category=interest.observation_category,
            content=interest.content,
            source_memory_id=memory_id,
        )
        return 1 if saved else 0
    except Exception:
        logger.warning("could not mirror the confirmed interest", exc_info=True)
        return 0
