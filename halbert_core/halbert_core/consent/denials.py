# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Typed denials — the gate never answers with a bare False.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.7:

    ``require()`` never returns a bare ``False`` and has no default
    return path. It raises ``Denied`` carrying one of seven typed
    outcomes, first-denial-wins, so both the UI and the machine's own
    voice can explain a refusal.

The seven outcomes, in the §1.7 order D3-P1 pinned for the decisive axis
(``HALTED → NO_CEILING → NO_AFFORDANCE → NOT_GRANTED → OS_DENIED /
OS_UNKNOWN → OUT_OF_SCOPE``), plus ``QUIET`` (autonomy only — reserved;
computed by the profiles packet, D3-P4). That set is **closed**: a
``Denied`` cannot carry anything else, and constructing one with an
invented reason code raises at construction — the same fail-closed
vocabulary discipline the ceiling enforces for capability ids.

``Denied.from_decision`` is the bridge from D3-P1's pure
``EffectiveDecision``: an allowed decision has no denial (that is the
"no default return path" half — an allow is a lease, D3-P3, never a
non-exception), and every denied decision raises with its decisive axis
named and its full axis evidence riding along for the audit line.

If the store cannot be read, the caller raises ``ConsentUnavailable`` and
the machine enters Stop (§4.1) — it never falls back to a value. The
exception carries the halt reason code to write into P1's ``HaltState``.
A bare ``try/except`` that swallows a ``Denied`` and continues is a lint
failure (the D3-P5 chokepoint lint).
"""
from __future__ import annotations

from typing import Optional

from ..persona.permission.effective import (
    EffectiveDecision,
    REASON_ALLOWED,
    REASON_HALTED,
    REASON_NO_AFFORDANCE,
    REASON_NO_CEILING,
    REASON_NOT_GRANTED,
    REASON_OS_DENIED,
    REASON_OS_UNKNOWN,
    REASON_OUT_OF_SCOPE,
    REASON_QUIET,
)
from ..persona.permission.halt import HaltReason

#: The closed set of §1.7 outcomes a ``Denied`` may carry. Exactly these,
#: verbatim — never a synonym, never an addition without a design decision.
CLOSED_REASONS = frozenset({
    REASON_HALTED,
    REASON_NO_CEILING,
    REASON_NO_AFFORDANCE,
    REASON_NOT_GRANTED,
    REASON_OS_DENIED,
    REASON_OS_UNKNOWN,
    REASON_OUT_OF_SCOPE,
    REASON_QUIET,
})

#: Deterministic copy for each typed outcome — the words the UI and the
#: machine's own voice use to explain a refusal (§1.7). Shipped text in
#: this table, never generated: an explanation of a refusal that is itself
#: synthesized is an unfalsifiable explanation.
DENIAL_COPY = {
    REASON_HALTED: "I'm stopped — nothing runs until the owner resumes me.",
    REASON_NO_CEILING: "This build of me can't do that at all.",
    REASON_NO_AFFORDANCE: "That needs hardware this machine doesn't have.",
    REASON_NOT_GRANTED: "You never granted this — it stays closed until you do.",
    REASON_OS_DENIED: "The operating system refused this.",
    REASON_OS_UNKNOWN: "I can't tell what the operating system says — this build isn't signed.",
    REASON_OUT_OF_SCOPE: "That's outside the scope that was granted.",
    REASON_QUIET: "I'm in quiet mode — I only speak when spoken to.",
}


def denial_copy(reason_code: str) -> str:
    """The shipped refusal wording for one typed outcome (fail-closed)."""
    try:
        return DENIAL_COPY[reason_code]
    except KeyError:
        raise ValueError(
            f"'{reason_code}' is not one of the typed denial outcomes "
            f"({sorted(CLOSED_REASONS)}). A refusal outcome cannot be "
            f"invented at a call site."
        ) from None


class Denied(Exception):
    """A typed, explainable refusal — never a bare ``False``.

    Carries the capability, the §1.7 reason code, the decisive axis, and
    (when raised from an evaluation) the full ``EffectiveDecision`` with
    every axis observation, so the audit line can always answer "denied
    on axis X, reason Y" — never "no".
    """

    def __init__(
        self,
        capability: str,
        reason_code: str,
        *,
        decisive_axis: str = "",
        detail: str = "",
        decision: Optional[EffectiveDecision] = None,
    ) -> None:
        if reason_code not in CLOSED_REASONS:
            raise ValueError(
                f"'{reason_code}' is not one of the typed denial outcomes "
                f"({sorted(CLOSED_REASONS)}). A refusal outcome cannot be "
                f"invented at a call site."
            )
        if reason_code == REASON_ALLOWED:  # pragma: no cover - defensive
            raise ValueError("ALLOWED is not a denial; it never reaches here.")
        self.capability = capability
        self.reason_code = reason_code
        self.decisive_axis = decisive_axis
        self.detail = detail or denial_copy(reason_code)
        self.decision = decision
        super().__init__(
            f"{capability}: {reason_code} ({decisive_axis or 'unattributed'}) "
            f"— {self.detail}"
        )

    @classmethod
    def from_decision(cls, decision: EffectiveDecision) -> "Denied":
        """Raise the typed denial a denied ``EffectiveDecision`` names.

        An allowed decision has no denial — the only other exit of the
        gate is the lease it mints (D3-P3). Passing an allow here is a
        programming error and raises, rather than quietly manufacturing
        a refusal out of a grant.
        """
        if decision.allowed:
            raise ValueError(
                f"an allowed decision ({decision.capability}) has no denial; "
                f"the gate mints a lease for an allow"
            )
        return cls(
            decision.capability,
            decision.reason_code,
            decisive_axis=decision.decisive_axis,
            decision=decision,
        )


class ConsentUnavailable(RuntimeError):
    """The consent ledger cannot be read or trusted — a Stop, never a
    fallback value (§1.7, §4.1).

    Carries ``halt_reason``: the ``HaltReason`` code the wiring writes into
    P1's ``HaltState`` so the machine says which trust precondition broke
    — integrity missing, ledger unreadable, or chain/projection disagreeing.
    """

    def __init__(self, message: str, *, halt_reason: str = HaltReason.CONSENT_UNREADABLE) -> None:
        super().__init__(message)
        self.halt_reason = halt_reason