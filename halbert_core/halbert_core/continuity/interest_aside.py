# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The one confirmation aside -- the single exception, and its fence.

``RQ-3``'s inferred half ends with a person saying yes. This is the only
place the machine asks, and it is the **single exception** to RECALL-v1's
rule that a fact about the person is never volunteered. Everything here is
the fence around that exception.

**It is phrased about the work, never about the person.** *"samba has come
up on four days this month -- worth remembering as something you work on?"*
and never *"you seem to be into samba"*. The first is an observation about a
month of conversations, which is checkable. The second is a claim about who
someone is, which is the surveillance reading arriving in a friendly voice.

**Once.** One aside per candidate, ever. A second ask is the machine
disagreeing with a person's silence, and silence is an answer. After that
the candidate waits in the Settings list until it expires.

**Inside a solicited reply.** Never from the scheduler, never as a
``ProactiveEvent``, never in the morning report. It rides a turn the person
started, or it does not happen.

**Dial-gated, because it initiates in miniature.** Off never, Quiet
list-only, Balanced and Assertive once. This is the one place the dial
touches interests -- recall itself is identical at Quiet, Balanced and
Assertive, because "Assertive" must never come to mean *talks about me
more*.

**Behind B4a**, like anything else optional, plus one per thread per 24h.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger("halbert.continuity.interest_aside")

__all__ = [
    "ASIDE_COOLDOWN_SECONDS",
    "DIALS_THAT_ASK",
    "select_candidate",
    "render_aside",
    "was_offered",
]

#: One aside per thread per rolling day, on top of one per candidate ever.
ASIDE_COOLDOWN_SECONDS = 24 * 60 * 60

#: Dials at which the machine may ask. Quiet is list-only by design: a
#: person who turned the dial down asked for fewer interruptions, and an
#: aside is an interruption however short.
DIALS_THAT_ASK = ("balanced", "assertive")

#: Written into the candidate's evidence once it has been asked about, so
#: "once, ever" survives a restart. A timeline event would not: the ledger
#: is body-local, and the candidate travels.
OFFERED_KEY = "aside_offered_at"


def was_offered(interest: Any) -> bool:
    """Whether this candidate has already been asked about."""
    try:
        return bool((interest.evidence or {}).get(OFFERED_KEY))
    except Exception:
        # Unreadable evidence means we cannot prove we have not asked. Not
        # asking is the recoverable error; asking twice is not.
        return True


def select_candidate(
    rows: Optional[Iterable[Any]],
    signals: Any,
    *,
    dial: str = "balanced",
    thread_id: str = "",
    last_aside_at: Optional[float] = None,
    now: Optional[float] = None,
    required_confirmation: bool = False,
    finding_store: Any = None,
) -> Optional[Any]:
    """The one candidate this turn may ask about, or ``None``. Never raises.

    Unlike :func:`~halbert_core.continuity.recall_interest.select_interest`,
    relevance to the turn is **not** required. The question is about a month
    of conversations, not about this sentence, and waiting for the subject to
    come up again would mean asking at the exact moment the person is busy
    with it.
    """
    try:
        if not rows:
            return None
        if (dial or "").strip().lower() not in DIALS_THAT_ASK:
            logger.debug("no aside: the dial is %s", dial)
            return None

        from ..skills.suppression import suppress_lens

        reason = suppress_lens(
            signals,
            required_confirmation=required_confirmation,
            proactivity=dial,
            finding_store=finding_store,
        )
        if reason:
            logger.debug("no aside: %s", reason)
            return None

        import time as _time

        stamp = now if now is not None else _time.time()
        if last_aside_at is not None and (stamp - last_aside_at) < ASIDE_COOLDOWN_SECONDS:
            logger.debug("no aside: already asked on %s today", thread_id or "this thread")
            return None

        from .interests import InterestStatus, Origin

        pending = [
            r for r in rows
            if getattr(r, "status", None) is InterestStatus.CANDIDATE
            and getattr(r, "origin", None) is Origin.INFERRED
            and not was_offered(r)
        ]
        if not pending:
            return None
        # The strongest evidence first: most days, then most threads, then
        # by topic so a run is reproducible.
        pending.sort(key=lambda r: (
            -int((r.evidence or {}).get("days") or 0),
            -len((r.evidence or {}).get("threads") or []),
            str(getattr(r, "topic", "")),
        ))
        return pending[0]
    except Exception:
        logger.warning("selecting a confirmation aside failed", exc_info=True)
        return None


def render_aside(interest: Any) -> str:
    """The block that carries the question, and the rules it must obey.

    The instruction is explicit about phrasing because this is the one
    sentence in the whole mechanism where the model composes something about
    the person. *About the work* is the fence: a question about what someone
    works on can be wrong and corrected; a statement about what they are like
    cannot.

    Redacted and flattened like every other stored string that reaches a
    prompt -- the topic is a noun someone typed.
    """
    from ..ingestion.redaction import redact_text

    topic = " ".join(str(getattr(interest, "topic", "")).split())
    topic = redact_text(topic, prose=True)
    evidence = getattr(interest, "evidence", None) or {}
    days = int(evidence.get("days") or 0)
    threads = len(evidence.get("threads") or [])
    count = (
        f"on {days} separate days across {threads} conversations this month"
        if days and threads else "several times this month"
    )
    return (
        "## One thing you may ask about, at the end of your answer\n"
        f"- {topic} has come up {count}.\n"
        "Answer the person's actual question first and in full. Then, in a "
        "single short sentence at the end, ask whether they want that "
        "remembered as something they work on. Ask about the work, never "
        "about them: not what they seem to like, not what kind of person "
        "they are. If the answer you are giving is bad news, or the question "
        "was urgent, leave it out entirely -- it will be asked another time. "
        "Ask once, never twice, and never rephrase it if they do not reply."
    )
