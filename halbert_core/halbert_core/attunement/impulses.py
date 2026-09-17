# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A ``ProactiveEvent`` as an impulse: which class, on what warrant, citing what.

Spec: ``documentation/superpowers/specs/2026-09-16-presence-slider-design.md``
§14 (classification) and §7.1 (warrant). Four of Halbert's judgments are
made here and marked:

* **Life safety is caller-set, never derived from severity** (A-HB-15). It
  comes from the event's category and from the acoustic tagger's own
  confirmation — what ``ProactiveGate`` already treats as life safety.
* **An unlinked info finding is an *observed* association.** It is a real
  thing in the ledger that nothing in particular brought up; it is admitted
  only at the association rung, which is today's "assertive: all findings"
  — and it carries its finding id, so the stronger-than-default warrant is
  cited (engine ``Utterance.__post_init__``). **Only a finding is a
  citation.** An event id is identity, not provenance: it resolves to
  nothing durable, so an info event with no finding behind it is honestly
  ``INFERRED`` — a thought, not a fact.
* **Recurrence reclassifies info, never a warning.** A warning that keeps
  happening is still a warning: rung 1 pushes it, and would drop a
  ``RECURRENCE``.
* **``approval_request`` is a warning about the machine's own pending
  action** — introspected, not observed.

Nothing here imports the engine at module scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Sequence, Tuple

if TYPE_CHECKING:  # pragma: no cover - the engine is optional at runtime
    from haloysius.attunement.types import ImpulseClass, Warrant

    from ..proactive.events import ProactiveEvent


def life_safety_event(event: "ProactiveEvent") -> bool:
    """Whether this event is life safety. Never derived from severity (A-HB-15).

    Two sources, both of which ``ProactiveGate`` already honours: the
    engine's life-safety category set, and a confirmed acoustic anomaly
    (tagger severity >= 2), which the wake chain treats as life safety
    because a glass break at 3am is exactly when it matters.
    """
    category = getattr(event, "category", None) or ""
    try:
        from ..integrations.modality_wiring import is_life_safety_event
    except ImportError:   # an optional integration; a bug in the predicate must not read as "not life safety"
        is_life_safety_event = None
    if is_life_safety_event is not None and is_life_safety_event(category):
        return True
    if category == "acoustic":
        data = getattr(event, "data", None)
        if isinstance(data, dict) and data.get("anomaly_severity", 0) >= 2:
            return True
    return False


def _citation(event: "ProactiveEvent") -> Optional[str]:
    """A finding id, or nothing: an event id is identity, not provenance."""
    finding_id = getattr(event, "finding_id", None)
    return f"finding:{finding_id}" if finding_id else None


def classify(event: "ProactiveEvent", *, current_subject_paths: Sequence[str] = ()
             ) -> "Tuple[ImpulseClass, Warrant, Optional[str]]":
    """``(ImpulseClass, Warrant, source_ref)`` for one event.

    Two classes have a branch here and no producer yet, so they are
    reachable in principle and unreachable in fact in slice 1:
    ``SUBJECT_LINKED`` needs ``current_subject_paths`` (what the person is on
    right now — config paths a summoned module shows, paths named in the
    current thread), which nothing on the proactive path carries; and
    ``RECURRENCE`` needs ``data["recurrence_count"]``, which no detector sets.
    The shadow log is what says when either starts arriving.

    Contract: every class this can return appears literally as ``C.<MEMBER>``
    in a ``return`` — the ``PRODUCED_CLASSES`` test reads them by AST.
    """
    from haloysius.attunement.types import ImpulseClass as C, Warrant as W

    ref = _citation(event)
    etype = str(getattr(event, "type", "") or "").lower()
    severity = str(getattr(event, "severity", "") or "info").lower()

    if life_safety_event(event):
        return C.LIFE_SAFETY, W.INTROSPECTED, ref
    if severity == "critical":
        return C.CRITICAL, W.INTROSPECTED, ref
    if etype in ("morning_report", "guest_session"):
        return C.SCHEDULED, W.INTROSPECTED, ref
    if etype == "approval_request":
        return C.WARNING, W.INTROSPECTED, ref

    if severity == "warning":
        return C.WARNING, W.INTROSPECTED, ref

    data = getattr(event, "data", None)
    if isinstance(data, dict):
        try:
            if int(data.get("recurrence_count", 0) or 0) > 1:
                return C.RECURRENCE, W.OBSERVED, ref
        except (TypeError, ValueError):
            pass

    paths = set(getattr(event, "affected_paths", None) or [])
    if paths and paths & set(current_subject_paths):
        return C.SUBJECT_LINKED, W.OBSERVED, ref

    # An observed thing brought up by no particular association. Stronger
    # than ASSOCIATION's default warrant, so it must cite; with nothing to
    # cite it is honestly inferred.
    return C.ASSOCIATION, (W.OBSERVED if ref else W.INFERRED), ref


#: Every class ``classify`` has a branch for — what the rungs endpoint calls
#: "classifiable" (plan D8).  Classifiable means the classifier can say it,
#: not that a producer emits it today; the shadow log answers the second.
#: Value strings, not members:
#: ``ImpulseClass`` is a ``str`` enum, so ``"warning" == ImpulseClass.WARNING``
#: and this set compares equal to the engine's without importing it.
PRODUCED_CLASSES = frozenset({
    "life_safety", "critical", "warning", "scheduled",
    "recurrence", "subject_linked", "association",
})
