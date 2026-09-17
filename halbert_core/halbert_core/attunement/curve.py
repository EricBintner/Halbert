# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert's presence curve — the engine's shape in Halbert's voice.

Spec: ``documentation/superpowers/specs/2026-09-16-presence-slider-design.md``
§14 (curve), §15 (the ``says`` copy is the settings surface). The engine's
``DEFAULT_CURVE`` is the strictest in the family (C-5); this relaxes the top
budget and ``closes_after`` and never admits social affect (pass 3 P-2):
Halbert's affect is about its own condition, never the relationship.

Lazy on purpose: nothing in this package imports the engine at module
scope. ``halbert_curve()`` is cached; a bad table fails on first call, not
per decision.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:  # pragma: no cover - the engine is optional at runtime
    from haloysius.attunement.types import PresenceCurve


@lru_cache(maxsize=1)
def halbert_curve() -> "PresenceCurve":
    from haloysius.attunement.types import (
        ChannelClass,
        ImpulseClass,
        InvitationLevel,
        PresenceCurve,
        PresenceRung,
    )

    C = ImpulseClass
    PUSH, AMBIENT = ChannelClass.PUSH, ChannelClass.AMBIENT
    S, M, N, CH = (InvitationLevel.SILENT, InvitationLevel.MINIMAL,
                   InvitationLevel.NORMAL, InvitationLevel.CHATTY)

    l0 = {C.LIFE_SAFETY: PUSH, C.CRITICAL: PUSH}
    l1 = {**l0, C.WARNING: PUSH}
    l3 = {**l1, C.SCHEDULED: PUSH, C.RECURRENCE: PUSH}
    l4 = {**l3, C.SUBJECT_LINKED: AMBIENT}
    l6 = {**l4, C.OPEN_LOOP: PUSH, C.ABSENCE: AMBIENT}
    l8 = {**l6, C.ASSOCIATION: PUSH, C.AFFECT_STATE: PUSH}
    l10 = {**l8, C.SPONTANEOUS: PUSH}

    def rung(level: int, name: str, says: str, why: str, channel: Dict[Any, Any],
             patience: Optional[float], budget: int, target: Any, ceiling: Any,
             closes: Optional[int]) -> PresenceRung:
        return PresenceRung(
            level=level, name=name, says=says, why=why,
            admits=frozenset(channel), channel=dict(channel), patience_s=patience,
            budget_per_day=budget, invitation_target=target, invitation_ceiling=ceiling,
            presence_signal=AMBIENT, closes_after=closes,
        )

    # Where this table leaves the engine's DEFAULT_CURVE, and why.  Admission,
    # channel and patience are the engine's rung for rung (the conformance
    # vectors hold that).  Budget: engine 0,1,3,3,4,5,5 → Halbert 0,2,3,4,5,6,8,
    # a strictly increasing ramp so every step of the fine adjust moves
    # something — the engine's plateaus (3–4, 8–10) would make those steps
    # dead for budget.  closes_after: 3 → 5.  Rung 3 is named "morning"
    # because that is what the person meets there: the morning report.
    return PresenceCurve(owner="halbert", rungs=(
        # level, name, says, why, channel, patience_s, budget, target, ceiling, closes_after
        rung(0, "mute",
             "I'll only speak for what can't wait.",
             "Nothing interrupts you. Everything else waits where you can find it.",
             l0, None, 0, S, S, None),
        rung(1, "warn",
             "I'll warn you. Everything else stays where you can find it.",
             "Warnings are worth your attention. Nothing else interrupts you.",
             l1, 240.0, 2, M, M, None),   # target == ceiling: "talk to me more" must not widen a quiet level (Q7.6)
        rung(3, "morning",
             "I'll give you the morning report, and tell you what keeps happening.",
             "The default. I stay out of the way so your own judgement stays in charge.",
             l3, 240.0, 3, N, CH, None),
        rung(4, "notice",
             "If I notice something about what you're on, I'll show it — not interrupt.",
             "Attention offered, never taken: an indicator you can pull on, not a voice.",
             l4, 180.0, 4, N, CH, None),
        rung(6, "recall",
             "I'll bring things back up when they fall due.",
             "What you told me isn't lost. When I raise it, I'll come with a next step.",
             l6, 120.0, 5, N, CH, 5),
        rung(8, "associate",
             "I'll say what your work reminds me of, and how I'm running.",
             "A thought, voiced as a thought — never as a fact I don't have.",
             l8, 90.0, 6, CH, CH, 5),
        rung(10, "think",
             "I'll talk when I have a thought, not only when something happens.",
             "Company, within a daily limit, and I'll let a thread end.",
             l10, 60.0, 8, CH, CH, 5),
    ))
