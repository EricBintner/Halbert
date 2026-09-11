# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""RECALL-v1 -- surfacing a remembered interest without reading as surveillance.

**The line is attribution, not volume.** The surveillance reading comes from an
unexplained claim about the person; the intuition reading comes from an
*explained use*. So a remembered fact never appears as a sentence whose subject
is the person's taste. It may colour an answer -- the example chosen, the
default offered -- and when it does, one clause whose subject is the answer
says so, with its date.

Three rules this module exists to hold:

- **Selection is arithmetic**, not judgement: overlap between the row's topic
  terms and the turn's entities and domains, at most one row, ties to the most
  recent evidence, zero overlap means nothing. The model receives a selection;
  it never makes one.
- **A recalled interest never initiates.** Not from the scheduler, not as a
  ``ProactiveEvent``, not as a line in the morning report. A person-fact beside
  a grey-van count is exactly the "it was watching me" reading, and a line
  about someone's taste has no why-care, so it cannot be a Finding (``C2-03``).
- **The dial governs initiation, not this.** Recall inside a solicited reply is
  identical at Quiet, Balanced and Assertive -- "Assertive" must never come to
  mean *talks about me more*. The one coupling is ``off``: purely reactive,
  nothing injected. Read here rather than through ``ProactiveGate``, which is
  severity-keyed and would either always pass a preference or never pass one.

Suppression currently uses the signals that exist. ``B4a``, the lens
suppression gate, was never built; when it lands this should delegate to it
rather than keep a second copy of the same list.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

logger = logging.getLogger("halbert.continuity.recall_interest")

__all__ = [
    "RECALL_COOLDOWN_SECONDS",
    "select_interest",
    "render_interest_block",
]

#: One injection per thread per rolling day. A remembered fact that resurfaces
#: every time its word is mentioned stops reading as intuition and starts
#: reading as a system with one thing to say about you.
RECALL_COOLDOWN_SECONDS = 24 * 60 * 60

#: Origins that may be injected. A bare ``inferred`` row is a candidate nobody
#: has confirmed; ``should_mirror`` keeps it out of the index and this keeps it
#: out of the prompt, because routing around one of the two is exactly how a
#: guess becomes a belief.
_ELIGIBLE_ORIGINS = ("stated", "inferred_confirmed")


def _is_eligible(row: Any) -> bool:
    try:
        return (
            getattr(row.status, "value", row.status) == "active"
            and getattr(row.origin, "value", row.origin) in _ELIGIBLE_ORIGINS
        )
    except Exception:
        return False


def _suppressed(signals: Any, dial: str) -> Optional[str]:
    """Why nothing may be injected this turn, or ``None``.

    Returns the reason rather than a bool so a caller can log which rule fired;
    a suppression nobody can name is indistinguishable from a bug.
    """
    if (dial or "").strip().lower() == "off":
        return "the proactivity dial is off"
    if getattr(signals, "is_troubleshooting", False):
        return "the turn is diagnostic"
    if (getattr(signals, "intent", "") or "") == "troubleshooting":
        return "the turn is diagnostic"
    if getattr(signals, "has_error_indicators", False):
        return "the turn carries error indicators"
    return None


def _turn_terms(signals: Any) -> set:
    entities = getattr(signals, "entities", None) or set()
    domains = getattr(signals, "detected_domains", None) or []
    return {str(t).strip().lower() for t in (set(entities) | set(domains)) if t}


def _overlap(row: Any, terms: set) -> int:
    topic_terms = {t for t in str(getattr(row, "topic", "")).lower().split() if t}
    if not topic_terms or not terms:
        return 0
    # Substring both ways: a turn entity "thinkpads" should match a topic term
    # "thinkpads", and a domain "storage" should match a topic "storage". This
    # is deliberately not fuzzy beyond that -- a looser rule starts surfacing
    # a remembered fact on turns that merely rhyme with it.
    hits = 0
    for term in terms:
        for topic_term in topic_terms:
            if term == topic_term or term in topic_term or topic_term in term:
                hits += 1
                break
    return hits


def _evidence_key(row: Any) -> str:
    return (
        getattr(row, "last_evidenced_at", "")
        or getattr(row, "last_confirmed_at", "")
        or getattr(row, "first_seen_at", "")
        or ""
    )


def select_interest(
    rows: Optional[Iterable[Any]],
    signals: Any,
    *,
    thread_id: str = "",
    dial: str = "balanced",
    last_injection_at: Optional[float] = None,
    now: Optional[float] = None,
) -> Optional[Any]:
    """The one interest this turn may carry, or ``None``.

    Never raises: a recall that fails costs the turn its colour, not its
    answer.
    """
    try:
        if signals is None or not rows:
            return None

        reason = _suppressed(signals, dial)
        if reason:
            logger.debug("interest recall suppressed: %s", reason)
            return None

        import time as _time

        stamp = now if now is not None else _time.time()
        if last_injection_at is not None and (stamp - last_injection_at) < RECALL_COOLDOWN_SECONDS:
            logger.debug("interest recall suppressed: already injected on %s today",
                         thread_id or "this thread")
            return None

        terms = _turn_terms(signals)
        if not terms:
            return None

        scored = []
        for row in rows:
            if not _is_eligible(row):
                continue
            hits = _overlap(row, terms)
            if hits:
                scored.append((hits, _evidence_key(row), row))
        if not scored:
            return None
        # Most overlap wins; ties to the most recent evidence.
        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
        return scored[0][2]
    except Exception:
        logger.warning("interest recall failed; continuing without it", exc_info=True)
        return None


def _readable_date(row: Any) -> str:
    raw = _evidence_key(row) or getattr(row, "first_seen_at", "")
    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m")


def render_interest_block(row: Any) -> str:
    """The dated block, with the instruction that keeps it an explained use.

    The four clauses are not decoration. *Only if it changes the answer* is
    what stops it being mentioned for its own sake; *say so in one clause with
    the date* is the attribution that separates intuition from surveillance;
    *never state it on its own* forbids the sentence whose subject is the
    person's taste; and *nothing else about the person is known* closes the
    door on the model filling the gap, which is the surveillance reading
    arriving by invention rather than by recall.

    Redacted and flattened, like every other line that reaches a prompt from a
    store: the topic is text a person typed.
    """
    from ..ingestion.redaction import redact_text

    topic = " ".join(str(getattr(row, "topic", "")).split())
    topic = redact_text(topic, prose=True)
    when = _readable_date(row)
    return (
        "## Something you know about the person\n"
        f"- Since {when}: they are interested in {topic}.\n"
        "Use it only if it changes the answer. If you do, say so in one clause "
        "whose subject is the answer, with the date. Never state it on its own, "
        "and never as a sentence about them. Nothing else about the person is "
        "known."
    )
