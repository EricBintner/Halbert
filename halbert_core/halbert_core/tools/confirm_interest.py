# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The "yes" half of the confirmation aside.

The aside asks; this records the answer. Built in the same shape as
``remember`` and for the same reason: the failure to prevent is a model
deciding on its own that someone agreed.

Three gates, all deterministic:

1. **A candidate must actually be outstanding.** Not any topic the model
   names -- a row already written by the arithmetic rule, still a candidate,
   and already asked about.
2. **The person's own words must carry an affirmative**, read from the turn's
   ContextVar rather than from the model's arguments. A value the model
   supplied cannot verify a value the model supplied.
3. **The role floor**, as everywhere else a fact about a person is written.

The promotion sets ``origin`` to ``inferred_confirmed`` and ``status`` to
``active``, and the ``MEM-06`` reason becomes the person's sentence -- their
words, not the arithmetic's. The arithmetic's reason is kept beside it as
the evidence that prompted the question.

There is no "no" tool. A person who declines has said nothing that needs
storing, and the candidate expires on its own thirty-day clock. A tool that
recorded refusals would be a second list of things someone said no to,
which is a record nobody asked for.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("halbert.tools.confirm_interest")

__all__ = ["CONFIRM_INTEREST_SCHEMA", "confirm_interest"]

#: What counts as yes, in the person's own words. Short and literal on
#: purpose: every entry is unambiguous agreement in reply to a question, and
#: none of them is a word that merely appears near one. "sure", "go on" and
#: "why not" are deliberately absent -- they are agreement in some tones and
#: sarcasm in others, and the cost of guessing wrong is a fact about someone
#: recorded because they were being dry.
_AFFIRMATIVES = (
    "yes",
    "yeah",
    "yep",
    "sure thing",
    "please do",
    "do that",
    "go ahead",
    "remember it",
    "remember that",
    "worth remembering",
    "that's right",
    "thats right",
    "correct",
)

#: Same floor as ``remember`` (``RQ-8``).
_MAY_WRITE = frozenset({"admin", "member"})

_WS = re.compile(r"\s+")

CONFIRM_INTEREST_SCHEMA = {
    "name": "confirm_interest",
    "description": (
        "Record that the user said yes to a question you asked about "
        "remembering something they work on. "
        "Only call this when you asked in the previous turn AND they "
        "agreed in their own words in this one. Never call it on your own "
        "reading of enthusiasm, and never to record a topic they did not "
        "agree to — a confirmation you inferred is refused."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The topic they agreed to, exactly as you asked about it.",
            },
        },
        "required": ["topic"],
    },
}


def _normalise(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def _refusal(why: str) -> str:
    return f"Not recorded: {why}"


async def confirm_interest(args: Dict[str, Any]) -> str:
    """Promote a candidate the person agreed to, or refuse and say why."""
    from ..continuity.interests import Interest, InterestStatus, Origin, topic_slug
    from ..continuity.provenance import current_user_message
    from .executor import current_speaker_role

    topic = (args.get("topic") or "").strip()
    if not topic:
        return _refusal("no topic was given.")

    role = (current_speaker_role.get(None) or "").strip().lower()
    if role not in _MAY_WRITE:
        return _refusal(
            f"a {role or 'unidentified'} speaker may not record a fact about "
            "the household."
        )

    said = current_user_message.get(None)
    if not said:
        return _refusal("there is no user message in scope to verify it against.")
    said_n = _normalise(said)
    if not any(a in said_n for a in _AFFIRMATIVES):
        return _refusal(
            "the user did not agree in this turn. A confirmation you inferred "
            "is not a confirmation."
        )

    store = _store()
    if store is None:
        return _refusal("there is no memory store to record it in.")

    slug = topic_slug(topic)
    for memory in (getattr(store, "list_memories", list)() or []):
        candidate = Interest.from_persona_memory(memory)
        if candidate is None or candidate.slug != slug:
            continue
        if candidate.status is not InterestStatus.CANDIDATE:
            return _refusal(
                f"{candidate.topic!r} is not an outstanding question."
            )
        return _promote(store, memory, candidate, said)
    return _refusal(f"nothing was asked about {topic!r}.")


def _store():
    try:
        from ..integrations.cognition_wiring import get_persona_memory_store
        return get_persona_memory_store()
    except Exception:
        logger.warning("no persona memory store for a confirmation", exc_info=True)
        return None


def _promote(store: Any, memory: Any, candidate: Any, said: str) -> str:
    """Candidate to confirmed, with the person's sentence as the reason."""
    from datetime import datetime, timezone

    from ..continuity.interests import Interest, InterestStatus, Origin
    from ..ingestion.redaction import redact_text

    stamp = datetime.now(timezone.utc).isoformat()
    evidence = dict(candidate.evidence or {})
    # The arithmetic that prompted the question is kept, not overwritten: it
    # is why the machine asked, and "how did you know to ask?" is a question
    # the person is entitled to an answer to.
    evidence["proposed_reason"] = candidate.reason
    confirmed = Interest(
        topic=candidate.topic,
        origin=Origin.INFERRED_CONFIRMED,
        status=InterestStatus.ACTIVE,
        reason=redact_text(" ".join(said.split()), prose=True),
        actor="user",
        speaker_role=(_role() or ""),
        body_id=candidate.body_id,
        evidence=evidence,
        first_seen_at=candidate.first_seen_at,
        last_evidenced_at=candidate.last_evidenced_at or stamp,
        last_confirmed_at=stamp,
    )
    memory_id = getattr(memory, "id", "")
    try:
        # Mutate the row in place rather than smart_add-ing a replacement.
        # The candidate and the confirmation have the same id AND the same
        # content, so `smart_add` treats the second as a duplicate and
        # MERGES it -- returning success while leaving the status
        # `candidate`. The tool said "Recorded" and nothing changed, which
        # is the exact failure this workstream keeps having to catch.
        meta = dict(getattr(memory, "metadata", None) or {})
        meta.update(confirmed._metadata())
        memory.metadata = meta
        tags = list(getattr(memory, "tags", None) or [])
        if Origin.INFERRED.value in tags:
            tags[tags.index(Origin.INFERRED.value)] = Origin.INFERRED_CONFIRMED.value
            memory.tags = tags
        save = getattr(store, "_save_to_disk", None)
        if save is None:
            return _refusal("this store cannot record a confirmation.")
        save()
        # The engine's own confirmation path, which is what a person saying
        # yes actually is: it raises validation_count and the derived
        # confidence with it, rather than this module inventing a number.
        confirm = getattr(store, "confirm_memory", None)
        if confirm is not None:
            confirm(memory_id)
        _mirror(confirmed, memory_id)
    except Exception:
        logger.warning("could not promote the candidate", exc_info=True)
        return _refusal("the memory store could not be written.")
    return f'Recorded: "{confirmed.content}"'


def _role() -> Optional[str]:
    from .executor import current_speaker_role

    return current_speaker_role.get(None)


def _mirror(interest: Any, memory_id: str) -> None:
    """The observation row a confirmed interest is entitled to.

    A candidate has none -- ``should_mirror`` is False for it -- so this is
    the moment the index gains the row, and it is the moment a person said
    yes. Absent rather than fatal: losing the index costs search quality,
    not the fact.
    """
    if not interest.should_mirror or not memory_id:
        return
    try:
        from ..integrations.cognition_wiring import get_observation_store

        store = get_observation_store()
        if store is None:
            return
        store.save(
            category=interest.observation_category,
            content=interest.content,
            source_memory_id=memory_id,
        )
    except Exception:
        logger.warning("could not mirror the confirmed interest", exc_info=True)
