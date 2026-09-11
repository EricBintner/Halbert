# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""B4a -- the one list of turns where nothing extra may be injected.

``CD-9``, answered: the gate runs at the **assemble call**, over signals that
exist today, on both the trigger path and the explicit one.

**Why one gate rather than a check per consumer.** A lens and a remembered
interest are different content with the same failure: arriving on a turn where
the person needed the machine to be plain. Two copies of "is this a bad moment"
drift, and the drift is invisible -- the copy that stops being updated keeps
injecting on exactly the turns the other one learned to avoid. RECALL-v1
shipped with its own copy, said so in its docstring, and this is that copy
being retired.

**It returns a reason, not a bool.** A suppression nobody can name is
indistinguishable from a bug, and the explicit path has to *say* why it
refused: a person who typed ``/understated`` and got nothing is owed the
signal that stopped it, not silence.

**What it does not decide.** Not whether a lens matched, and not whether a
remembered interest is relevant -- both are the caller's arithmetic. This
answers one question: may anything optional be added to this turn at all.

``B4b`` adds `is_destructive` and `is_incident` on `MessageSignals`, plus the
entity-to-finding join, before ``C2``. Those signals do not exist yet; the
structure here is what they attach to.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("halbert.skills.suppression")

__all__ = ["suppress_lens", "SUPPRESSION_REASONS"]

#: Every reason this gate can give, for tests and for the refusal text. Named
#: rather than inlined so a new signal cannot be added without appearing in
#: the list a person may be shown.
SUPPRESSION_REASONS = (
    "the turn is diagnostic",
    "the turn carries error indicators",
    "a confirmation is pending on this turn",
    "the proactivity dial is off",
    "lens intensity is off",
    "a critical finding is open",
)


def _dial_off(value: Any) -> bool:
    return str(value or "").strip().lower() == "off"


def suppress_lens(
    signals: Any = None,
    *,
    required_confirmation: bool = False,
    proactivity: str = "balanced",
    lens_intensity: str = "",
    finding_store: Any = None,
) -> Optional[str]:
    """Why nothing optional may be added this turn, or ``None``.

    Never raises. A gate that throws takes down the turn it was meant to keep
    plain, which is a worse outcome than either answer it could have given.
    Failure is treated as *not suppressed*: the alternative is a machine that
    goes silent whenever a store is unreachable, and silence is indeed the
    safer content but it is not the safer failure -- it is unexplainable, and
    the caller has already decided this content was worth adding.
    """
    try:
        # -- the turn itself ---------------------------------------------
        # Diagnostic work is the clearest case: a person mid-fault wants the
        # machine plain, and a remark about their taste in laptops lands as
        # the machine not reading the room.
        if signals is not None:
            if (getattr(signals, "intent", "") or "") == "troubleshooting":
                return "the turn is diagnostic"
            if getattr(signals, "is_troubleshooting", False):
                return "the turn is diagnostic"
            if getattr(signals, "has_error_indicators", False):
                return "the turn carries error indicators"

        # A confirmation is a question with a yes/no shape. Anything added
        # beside it competes with the only answer the turn is asking for.
        if required_confirmation:
            return "a confirmation is pending on this turn"

        # -- what the person configured ----------------------------------
        if _dial_off(proactivity):
            return "the proactivity dial is off"
        if _dial_off(lens_intensity):
            return "lens intensity is off"

        # -- what the machine knows is wrong -----------------------------
        # An open critical finding means something is actually broken. Read
        # last because it is the only branch that touches a store.
        if finding_store is not None:
            try:
                if finding_store.list_by_severity("critical"):
                    return "a critical finding is open"
            except Exception:
                logger.debug("could not read open findings for the gate",
                             exc_info=True)
        return None
    except Exception:
        logger.warning("the suppression gate failed; not suppressing",
                       exc_info=True)
        return None
