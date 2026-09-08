# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The OS grant — axis 3 of five.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.2:

    OS grant — has the operating system agreed?
    Four-state: GRANTED / DENIED / UNDETERMINED / UNQUERYABLE.

**The four states exist because three would force a lie.** ``UNQUERYABLE``
is the honest state for macOS Full Disk Access (no API exists — you probe
by ``EPERM`` on the TCC database) and for every macOS sensor row while the
signing chain has not landed: with ``signingIdentity: null`` the designated
requirement is a cdhash that rotates on every build, so no TCC grant
persists and no row may read "on". The correct answer is "can't tell —
this build isn't signed", and this module can say it.

Fail-closed rules, pinned by test:

- only ``GRANTED`` is affirmative. ``DENIED``, ``UNDETERMINED`` and
  ``UNQUERYABLE`` all deny — the two "can't tell" states are never read
  as yes. "Never infer a grant from the absence of an error."
- an id outside the shipped vocabulary cannot carry an OS-grant entry at
  all (construction raises).
- **the default table is empty.** The audit found zero hits for any
  authorization-status API anywhere in the tree; absence of a query is
  never a grant, so nothing reads GRANTED until a preflight is wired
  (D3-P5, per channel). Until then every id reads UNDETERMINED — the
  fail-closed reading, and the honest one.

A probe is not a grant (§1.1): this module never consults the
``capabilities.py`` probe registry. Presence is the affordance axis's
question; this axis is the operating system's answer.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Mapping, Optional

from .ceiling import VOCABULARY


class OsGrantState(Enum):
    """The operating system's answer. Only GRANTED is affirmative."""

    GRANTED = "granted"            # a live preflight said yes
    DENIED = "denied"               # the OS said no (a revocation we detected)
    UNDETERMINED = "undetermined"  # a preflight exists but could not decide
    UNQUERYABLE = "unqueryable"    # no query exists at all (FDA, unsigned builds)


#: The states a table entry may legally hold (every state — the table is
#: how the wiring records what it learned).
_VALID_STATES: FrozenSet[OsGrantState] = frozenset(OsGrantState)


@dataclass(frozen=True)
class OsGrantTable:
    """The per-channel record of what the OS has been observed to say.

    This is app-owned policy config (reconciliation §2: the engine does not
    own policy). Ids outside the shipped vocabulary and values outside the
    four states raise at construction — a table that could invent a
    capability or fabricate a state must never exist.
    """

    entries: Mapping[str, OsGrantState]

    def __post_init__(self) -> None:
        for cap_id, state in self.entries.items():
            if cap_id not in VOCABULARY:
                raise ValueError(
                    f"OS-grant table names '{cap_id}', which is outside the "
                    f"shipped vocabulary. The OS cannot be recorded as saying "
                    f"anything about a capability that does not exist."
                )
            if not isinstance(state, OsGrantState):
                raise ValueError(
                    f"OS-grant table state for '{cap_id}' is {state!r}, not an "
                    f"OsGrantState. An unknown state is a lie — use one of "
                    f"the four, or leave the id out (UNDETERMINED)."
                )

    def state_for(self, capability_id: str) -> OsGrantState:
        """The OS's answer for this capability. Absent → UNDETERMINED.

        UNDETERMINED, not UNQUERYABLE: an id missing from the table means
        no preflight has been wired for it (a decision pending), which is
        a different fact from "no query can exist".
        """
        return self.entries.get(capability_id, OsGrantState.UNDETERMINED)


#: The default table: empty. No preflight is wired anywhere in the tree
#: today, so nothing is OS-GRANTED by default and the whole axis denies —
#: the deny-all posture until D3-P5 wires real per-channel preflights.
DEFAULT_OS_GRANTS = OsGrantTable({})


def is_os_grant_affirmative(state: Optional[OsGrantState]) -> bool:
    """Only a live GRANTED is yes. Every "can't tell" is no."""
    return state is OsGrantState.GRANTED