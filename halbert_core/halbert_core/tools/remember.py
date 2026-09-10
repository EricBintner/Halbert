# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""``remember`` -- the explicit write path for a fact about the person.

``RQ-3``: two write paths, both with deterministic selection; **no
model-chosen write, ever**. This is the explicit one; the inferred one is a
candidate the Consolidator proposes and a person confirms.

The design is a set of refusals, because the failure it exists to prevent is
one the field commits routinely -- Haloysius's own ``update_user_knowledge``
auto-applies a model-picked value with the reason "Learned from conversation"
and a confidence the model invented. ``MEM-06`` is the rule this enforces: a
stored fact about a person needs a reason that is a **human utterance**, never
model text.

Two gates carry that:

1. The turn's user message must contain one of :data:`_REQUEST_PHRASES`.
2. The recorded ``reason`` must be a substring of that message.

The second is the load-bearing one. Without it a model calling ``remember``
on a paraphrase -- *"you seem to like…"* -- collapses the explicit path back
into a model-chosen write, and the tool becomes the thing it replaced. Both
read the person's words from a ContextVar
(:data:`~halbert_core.continuity.provenance.current_user_message`) rather than
from the args, because a value the model supplied cannot verify a value the
model supplied.

Nothing here calls a model, ranks, or searches.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("halbert.tools.remember")

__all__ = ["REMEMBER_SCHEMA", "remember"]

#: The deterministic phrase list. Short on purpose: every entry is a phrase a
#: person uses to ask for something to be kept, and none is a phrase that
#: merely *mentions* a topic. Widening this widens what counts as consent.
_REQUEST_PHRASES = (
    "remember that",
    "remember i",
    "remember, ",
    "note that",
    "keep in mind",
    "don't forget that",
    "dont forget that",
)

#: Roles permitted to record a fact about the household (``RQ-8``). Below
#: member a speaker may use the machine but may not tell it what is true about
#: the people in the house.
_MAY_WRITE = frozenset({"admin", "member"})

_WS = re.compile(r"\s+")

REMEMBER_SCHEMA = {
    "name": "remember",
    "description": (
        "Record something the user has explicitly asked you to remember about "
        "them — an interest, a preference, a topic they work on. "
        "Only call this when the user asked, in their own words, in this turn "
        "('remember that…', 'note that…', 'keep in mind…'). "
        "The `reason` MUST be copied verbatim from the user's message — a "
        "substring of what they actually typed. Do not paraphrase, do not "
        "summarise, and never call this on your own inference that they seem "
        "to like something: a reason you composed is refused, and the refusal "
        "is not a reason to retry with different wording."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The thing they are interested in, e.g. 'vintage thinkpads'",
            },
            "reason": {
                "type": "string",
                "description": "Verbatim from the user's message this turn.",
            },
        },
        "required": ["topic", "reason"],
    },
}


def _normalise(text: str) -> str:
    """Case- and whitespace-insensitive form, for substring checking only.

    Deliberately not a fuzzy match. The rule is "these are the person's own
    words"; tolerating case and spacing keeps a copy-paste from failing on a
    double space, while anything looser would start admitting paraphrase,
    which is the whole thing being refused.
    """
    return _WS.sub(" ", (text or "").strip().lower())


def _refusal(why: str) -> str:
    return (
        f"Not recorded: {why} "
        "Nothing was stored. A fact about a person is only recorded from their "
        "own words, asked for in this turn."
    )


def _write_interest(interest: Any) -> Optional[str]:
    """Persist the interest. Seam, so the tests do not need a real store."""
    from ..continuity.interests import Interest  # noqa: F401  (documents the type)
    from ..integrations.cognition_wiring import get_persona_memory_store

    store = get_persona_memory_store()
    if store is None:
        return None
    _op, _reason, memory_id = store.smart_add(
        interest.to_persona_memory(getattr(store, "persona_id", "halbert"))
    )
    return memory_id


async def remember(args: Dict[str, Any]) -> str:
    """Record an explicitly-requested fact, or refuse and say why."""
    from ..continuity.interests import Interest, InterestStatus, Origin
    from ..continuity.provenance import current_turn, current_user_message
    from .executor import current_speaker_role

    topic = (args.get("topic") or "").strip()
    reason = (args.get("reason") or "").strip()

    if not topic:
        return _refusal("no topic was given.")
    if not reason:
        return _refusal("no reason was given, and a reason must be the user's own words.")

    # -- the speaker ----------------------------------------------------
    role = (current_speaker_role.get(None) or "").strip().lower()
    if role not in _MAY_WRITE:
        return _refusal(
            f"a {role or 'unidentified'} speaker may not record a fact about "
            "the household."
        )

    # -- the person's own words -----------------------------------------
    said = current_user_message.get(None)
    if not said:
        # No turn in scope, so the reason cannot be verified against
        # anything. Writing anyway would be the model-chosen write by
        # another route.
        return _refusal("there is no user message in scope to verify it against.")

    said_n = _normalise(said)
    if not any(p in said_n for p in _REQUEST_PHRASES):
        return _refusal(
            "the user did not ask for anything to be remembered in this turn."
        )
    if _normalise(reason) not in said_n:
        return _refusal(
            "the reason is not what the user said. Record their words, not a "
            "paraphrase of them."
        )

    # -- secrets --------------------------------------------------------
    # Scrubbed before anything is stored or echoed. A Tier-2 credential is
    # answered by a deterministic template and never becomes a memory: the
    # standing rule is that Tier 2 is answered without a model, and a stored
    # credential would outlive the turn that carried it.
    from ..ingestion.redaction import redact_text

    safe_topic = redact_text(topic, prose=True)
    safe_reason = redact_text(reason, prose=True)
    if safe_topic != topic or safe_reason != reason:
        if _looks_like_credential(topic, reason, safe_topic, safe_reason):
            return (
                "Not recorded: that looks like a credential. "
                "Secrets are never stored as memories — keep it in the "
                "credential store, and I will read it from there when needed."
            )
        topic, reason = safe_topic, safe_reason

    # -- write ----------------------------------------------------------
    try:
        interest = Interest(
            topic=topic,
            origin=Origin.STATED,
            reason=reason,
            status=InterestStatus.ACTIVE,
            actor="user",
            speaker_role=role,
            evidence={"turn": current_turn.get(None) or ""},
        )
    except ValueError as e:
        return _refusal(str(e))

    try:
        _write_interest(interest)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("remember: the write failed", exc_info=True)
        return f"Not recorded: the memory store could not be written ({type(e).__name__})."

    # The echo is the confirmation, and the person's first chance to correct
    # it. Verbatim: a paraphrased echo cannot be checked against what was
    # stored, which is the point of showing it at all.
    return f'Recorded: "{interest.content}"'


def _looks_like_credential(topic: str, reason: str, safe_topic: str, safe_reason: str) -> bool:
    """Whether redaction removed a *secret*, rather than an address.

    Redaction rewrites several things that are not credentials -- a public IP,
    an email. Those are worth scrubbing from a stored sentence but are not
    grounds to refuse the whole request, so the refusal is narrowed to the
    placeholders that mean "a secret was here".
    """
    removed = (safe_topic + " " + safe_reason)
    return any(
        marker in removed
        for marker in ("<secret>", "<token>", "<jwt>", "<pem_block>", "<password>")
    )
