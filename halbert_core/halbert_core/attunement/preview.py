# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""What the machine would have said at another level — from the shadow log.

Spec: ``documentation/superpowers/specs/2026-09-16-presence-slider-design.md``
§15. The preview is admission and channel re-run over stored rows at a
hypothetical level (plan D7). It is *not* a re-decide: a stored row has no
live receptivity and no standing requests, so the inequality cannot be
re-run honestly. What can be re-run exactly is whether the class would be
admitted and at what channel — and that is what the person is choosing.

Rows written before slice 1 carry no ``impulse_class``; they are counted
as ``unclassified`` and never guessed at.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

#: The channel a row would be delivered at, read as the person will: pushed
#: is "said", ambient is "shown", pull is "held". Ranking is the engine's
#: ``channel_rank`` — one choke point, not a second table.
_VERDICT_BY_CHANNEL = {"push": "said", "ambient": "shown", "pull": "held"}


def _parse(ts: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def preview_for_level(rows: Iterable[Dict[str, Any]], level: int, *, being_config: Any,
                      days: int = 7, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Counts and per-row verdicts for ``level`` over the last ``days``.

    The config's own level is irrelevant here — the person is asking about
    ``level`` — only its overrides ride along. Refused overrides are dropped,
    never invented (the same rule as ``context.presence_for``).
    """
    try:
        from haloysius.attunement.presence import resolve_presence
        from haloysius.attunement.types import ImpulseClass, channel_rank
    except ImportError:
        resolve_presence = None
    from .context import halbert_config
    config = halbert_config() if resolve_presence is not None else None
    if config is None:
        return {"level": level, "days": days, "said": 0, "shown": 0, "held": 0,
                "unclassified": 0, "items": [], "engine": False}
    from .curve import halbert_curve
    # Raw to the resolver: it coerces keys and levels and refuses a bool; the
    # config was validated before it got here (Task 14).
    overrides = dict(getattr(being_config, "presence_overrides", None) or {})
    try:
        vector = resolve_presence(level, halbert_curve(), config.attachment, overrides)
    except (TypeError, ValueError):
        vector = resolve_presence(level, halbert_curve(), config.attachment, {})

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    counts = {"said": 0, "shown": 0, "held": 0}
    unclassified = 0
    items: List[Dict[str, Any]] = []

    for r in rows:
        ts = _parse(r.get("ts"))
        if ts is None or ts < cutoff:
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
        own = str(r.get("channel_class") or "push")
        if cls not in vector.admits:
            verdict, channel = "held", None
        else:
            ceiling = vector.channel[cls].value
            try:
                capped = channel_rank(own) > channel_rank(ceiling)
            except ValueError:            # a row with a channel the engine does not know: treat as pushed
                capped = True
            channel = ceiling if capped else own
            verdict = _VERDICT_BY_CHANNEL[channel]
        counts[verdict] += 1
        items.append({
            "attempt_id": r.get("attempt_id"), "ts": r.get("ts"),
            "source": r.get("source"), "severity": r.get("severity"),
            "impulse_class": cls.value, "verdict": verdict, "channel": channel,
            "live_outcome": r.get("gate_outcome"),
        })

    items.sort(key=lambda i: str(i.get("ts")), reverse=True)
    return {"level": vector.level, "days": days, **counts,
            "unclassified": unclassified, "items": items, "engine": True}
