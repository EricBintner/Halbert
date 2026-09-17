# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""What the machine would have said at another level — from the shadow log.

Spec: ``documentation/superpowers/specs/2026-09-16-presence-slider-design.md``
§15. The preview is admission and channel re-run over stored rows at a
hypothetical level (plan D7). It is *not* a re-decide: a stored row has no
live receptivity and no standing requests, so the inequality cannot be
re-run honestly. What can be re-run exactly is whether the class would be
admitted and at what channel — and that is what the person is choosing.

Nor is the budget re-run: exhaustion is a deferral to the next turn, per
day at the consumer's midnight, and neither the deadline nor the timezone
is in a stored row — so the counts are "what would have been admitted",
and ``budget_per_day`` rides beside them for the surface to say "up to N a
day".

"Held" here is the person's word (spec §15, the rung-0 copy): not brought
up, and waiting where they can find it. It is not the engine's
``EngagementOutcome.HOLD``, which is an *admitted* impulse deferred with a
resume condition and a deadline. A shadow row with ``outcome: "hold"`` and
a preview verdict "held" are two different statements.

Rows written before slice 1 carry no ``impulse_class``; they are counted
as ``unclassified`` and never guessed at. A row whose timestamp cannot be
read is counted as ``undated`` so the totals reconcile with the store.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: The verdict a delivery channel reads as, in the person's words: pushed is
#: "said", ambient is "shown", pull is "held" (findable, never pushed — the
#: engine never suppresses a pull utterance; no slice-1 row carries pull,
#: every shadow row is decided at PUSH). A label table; the *ranking* is
#: the engine's ``channel_rank``.
_VERDICT_BY_CHANNEL = {"push": "said", "ambient": "shown", "pull": "held"}


def _parse(ts: Any) -> Optional[datetime]:
    """The store writes tz-aware UTC; a naive value reads as UTC, and a
    trailing ``Z`` is accepted (``fromisoformat`` rejects it before 3.11).

    When the caller pre-filters with the store's own ``since`` (as the
    preview route does), a row whose ``ts`` cannot be parsed here has
    already been included or excluded lexically by SQL, before this
    function ever sees it — so ``undated`` below counts only what
    survived that filter, not every unparsable row the store holds.
    """
    text = str(ts)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def preview_for_level(rows: Iterable[Dict[str, Any]], level: int, *, being_config: Any,
                      days: int = 7, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Counts and per-row verdicts for ``level`` over the last ``days``.

    The config's own level is irrelevant here — the person is asking about
    ``level`` — only its overrides ride along, through the one drop rule in
    ``context.resolve_vector``.
    """
    from .context import resolve_vector

    vector = resolve_vector(level, dict(getattr(being_config, "presence_overrides", None) or {}))
    if vector is None:
        return {"level": level, "days": days, "said": 0, "shown": 0, "held": 0,
                "unclassified": 0, "undated": 0, "budget_per_day": None, "items": [], "engine": False}
    from haloysius.attunement.types import ImpulseClass, channel_rank

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    counts = {"said": 0, "shown": 0, "held": 0}
    unclassified = undated = 0
    dated: List[Tuple[datetime, Dict[str, Any]]] = []

    for r in rows:
        ts = _parse(r.get("ts"))
        if ts is None:
            undated += 1
            continue
        if ts < cutoff:
            continue
        raw = r.get("impulse_class")
        if not raw:
            unclassified += 1
            continue
        try:
            cls = ImpulseClass(raw)
        except ValueError:
            unclassified += 1
            continue
        # Every shadow row is decided at PUSH (context.SHADOW_CHANNEL_CLASS) and
        # the recorder writes the field with the row; the default is the loudest
        # reading for a row that somehow lacks it.
        own = str(r.get("channel_class") or "push")
        if cls not in vector.admits:
            verdict, channel = "held", None
        else:
            ceiling = vector.channel[cls].value
            try:
                capped = channel_rank(own) > channel_rank(ceiling)
            except ValueError:            # a channel the engine does not know: resolve at the ceiling
                capped = True
            channel = ceiling if capped else own
            verdict = _VERDICT_BY_CHANNEL[channel]
        counts[verdict] += 1
        dated.append((ts, {
            "attempt_id": r.get("attempt_id"), "ts": r.get("ts"),
            "source": r.get("source"), "severity": r.get("severity"),
            "context_key": r.get("context_key"),
            "impulse_class": cls.value, "verdict": verdict, "channel": channel,
            "live_outcome": r.get("gate_outcome"),
        }))

    dated.sort(key=lambda pair: pair[0], reverse=True)   # chronological, not lexical
    return {"level": vector.level, "days": days, **counts,
            "unclassified": unclassified, "undated": undated,
            "budget_per_day": vector.budget_per_day,
            "items": [item for _, item in dated], "engine": True}
