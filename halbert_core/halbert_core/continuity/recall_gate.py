# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Decide whether a recall hit is trustworthy enough to inject silently.

Spec §6 injects the top receipt as ``retrieved_context[0]`` with no model call
whenever a search returns a hit. The cumulative harness shows what that costs as
the store grows: the top hit is the right thread 100% of the time at 10 threads
and 63% at 500. The remaining 37% are *silent* — Halbert pastes the wrong past
conversation into its own context and nothing surfaces the mistake.

The failure is not that the search is bad. It is that "a hit exists" is being
used as evidence of confidence, and it is not. When the top two candidates score
almost the same, the index is saying *I cannot tell these apart* — and that is
exactly when the old behaviour was most confident.

So gate on the **margin**: how far ahead first place is of second.

    gap = (top - runner_up) / top        # 0.0 = tied, 1.0 = uncontested

A clear winner is injected as before. A close call becomes a *question* — the
weak-match path, where the model asks "the Samba one from July, or the NAS one
from June?". A silent wrong answer is converted into a visible choice.

Nothing here calls a model. The gate is arithmetic on scores the index already
produced, so the read path stays deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Tuple

__all__ = ["MatchStrength", "GateResult", "classify", "DEFAULT_MARGIN"]

#: Chosen by sweeping the cumulative harness, not by taste. See
#: ``tests/test_recall_gate.py::TestChosenThreshold`` for the measurement that
#: justifies this value and would fail if it stopped holding.
DEFAULT_MARGIN = 0.15


class MatchStrength(Enum):
    """What the caller should do with a recall result."""

    NONE = "none"      #: nothing matched — a normal outcome, not an error
    WEAK = "weak"      #: candidates exist but are not separable; offer, don't inject
    STRONG = "strong"  #: one clear winner; safe to inject with no model call


@dataclass(frozen=True)
class GateResult:
    strength: MatchStrength
    #: the winning thread, only when ``strength is STRONG``
    thread_id: Optional[str]
    #: candidates to offer the model when ``strength is WEAK``
    candidates: List[str]
    #: normalised gap between first and second place, for logging and telemetry
    gap: float

    @property
    def should_inject(self) -> bool:
        return self.strength is MatchStrength.STRONG


def classify(
    scored: Sequence[Tuple[str, float]],
    margin: float = DEFAULT_MARGIN,
    max_candidates: int = 3,
) -> GateResult:
    """Classify a scored result list into NONE / WEAK / STRONG.

    Args:
        scored: ``(thread_id, relevance)`` best-first, higher is better.
        margin: minimum normalised gap between first and second place for a
            STRONG match. 0.0 restores the old always-inject behaviour.
        max_candidates: how many candidates a WEAK result offers.

    A single result is STRONG: there is nothing to confuse it with. Non-positive
    top scores (the LIKE fallback, which carries no ranking information) are
    never STRONG — an unranked hit is not evidence of confidence.
    """
    if not scored:
        return GateResult(MatchStrength.NONE, None, [], 0.0)

    top_id, top_score = scored[0]

    if top_score <= 0:
        return GateResult(
            MatchStrength.WEAK, None,
            [tid for tid, _ in scored[:max_candidates]], 0.0,
        )

    if len(scored) == 1:
        return GateResult(MatchStrength.STRONG, top_id, [top_id], 1.0)

    runner_up = scored[1][1]
    gap = (top_score - runner_up) / top_score
    if gap >= margin:
        return GateResult(MatchStrength.STRONG, top_id, [top_id], gap)
    return GateResult(
        MatchStrength.WEAK, None,
        [tid for tid, _ in scored[:max_candidates]], gap,
    )
