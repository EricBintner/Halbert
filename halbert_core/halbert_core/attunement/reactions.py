# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Labelling the attempts — the other arm of the outcome ledger (A-HB-26).

``update_reaction`` has existed since the store landed and nothing called
it, so every proactive attempt Halbert has ever recorded is unlabelled and
the learning loop ``the-being.md`` §4 promised — *"which interrupts did you
act on"* — has no evidence at all.

The engine's warning about which arm is which is the reason this module is
careful rather than convenient:

    A loop that sees its speaking decisions punished and its silences never
    evaluated ratchets toward silence, and a quiet assistant looks
    well-behaved while getting worse.

So two rules hold here, and both are about not manufacturing evidence:

* **A reaction is a person's, not a process's.** These are called from the
  surfaces where a human did something — the dismiss and snooze routes, the
  "propose fix" route — and never from ``FindingStore``, where an automatic
  cleanup dismissing a stale finding would enter the ledger looking exactly
  like a person saying no.
* **Silence is not a reaction.** :meth:`ReactionRecorder.sweep_ignored`
  never touches an attempt the gate suppressed. Nobody saw it, so nobody
  ignored it, and a negative label minted from the product's own silence
  would corrupt the one arm Phase C most needs to trust.

Nothing here raises into its caller: a finding must still dismiss when the
ledger is unavailable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .context import DEFAULT_PERSONA_ID
from .subject import DEFAULT_SUBJECT_ID

logger = logging.getLogger("halbert.attunement.reactions")

#: How long an attempt stays open before silence counts as being ignored.
#: Four hours rather than a day: past that the person has plausibly not
#: been at the machine at all, and "away" is not "ignored".
DEFAULT_IGNORED_AFTER_S = 4 * 3600


class ReactionRecorder:
    """Attaches a person's reaction to the attempt that prompted it."""

    def __init__(self, store: Any, *, persona_id: str = DEFAULT_PERSONA_ID,
                 subject_id: str = DEFAULT_SUBJECT_ID):
        self.store = store
        self.persona_id = persona_id
        self.subject_id = subject_id

    # -- the three event-shaped arms ------------------------------------

    def on_dismissed(self, finding_id: Optional[str]) -> bool:
        """The person said no to this finding."""
        return self._label(finding_id, "dismissed")

    def on_snoozed(self, finding_id: Optional[str]) -> bool:
        """The person said not now.

        Deliberately not ``DISMISSED``: a postponement and a refusal are
        different evidence, and a loop that merges them learns that being
        asked to wait means it should not have spoken.
        """
        return self._label(finding_id, "not_now")

    def on_engaged(self, finding_id: Optional[str]) -> bool:
        """The person acted on this finding, or answered it.

        The positive arm — the one a silence can never produce, which is
        what makes it the valuable one. Founder ruling (2026-09-10): acting
        on it or replying to it counts; merely opening it does not, and
        records nothing either way.
        """
        return self._label(finding_id, "engaged")

    # -- the sweep -------------------------------------------------------

    def sweep_ignored(self, *, after_s: int = DEFAULT_IGNORED_AFTER_S,
                      now: Optional[datetime] = None, limit: int = 500) -> int:
        """Label attempts nobody answered. Returns how many were labelled.

        Only attempts the gate actually let through: an attempt that was
        suppressed reached no one, and calling that "ignored" would mint a
        negative label out of the product's own silence.
        """
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(seconds=after_s)).isoformat()
        labelled = 0
        try:
            rows = self.store.unanswered_attempts(
                self.persona_id, before_ts=cutoff,
                subject_id=self.subject_id, limit=limit,
            )
        except Exception as exc:
            logger.warning("attunement: could not sweep for ignored attempts: %s", exc)
            return 0

        for row in rows:
            # Belt and braces: the query already restricts to spoken,
            # unanswered rows, and this is the assertion that a store which
            # stopped doing so cannot quietly start minting negatives.
            if row.get("gate_outcome", row.get("outcome")) != "speak":
                continue
            if row.get("reaction"):
                continue
            attempt_id = row.get("attempt_id")
            if not attempt_id:
                continue
            try:
                if self._attach(attempt_id, "ignored"):
                    labelled += 1
            except Exception as exc:
                logger.warning("attunement: could not label %s: %s", attempt_id, exc)
        return labelled

    # -- internals -------------------------------------------------------

    def _label(self, context_key: Optional[str], reaction: str) -> bool:
        """Find the attempt this reaction is about, and label it.

        False when there is no attempt the person actually received. A
        finding whose push the gate suppressed is still written and still
        listed, so it can be met on the Findings page and dismissed there
        having never interrupted anyone — that is a reaction to a *finding*,
        not to an attempt, and the store's ``spoken_only`` default is what
        keeps the two apart.
        """
        if not context_key:
            return False
        try:
            attempt_id = self.store.latest_attempt_for_context(
                context_key, persona_id=self.persona_id,
                subject_id=self.subject_id,
            )
            if not attempt_id:
                return False
            return self._attach(attempt_id, reaction)
        except Exception as exc:
            logger.warning(
                "attunement: could not record reaction %s for %s: %s",
                reaction, context_key, exc,
            )
            return False

    def _attach(self, attempt_id: str, reaction: str) -> bool:
        """Write the reaction through the engine's writer where we can.

        ``record_reaction`` is not a wrapper around ``update_reaction``: it
        also calls ``note_accepted`` on ENGAGED, and that counter is read by
        the policy. While ``accepted_interactions`` is below the engine's
        quiet-period threshold every decision carries a fixed extra cost, so
        a wiring that writes the reaction but never advances the counter
        pins that cost on forever and depresses every margin it records —
        and ``margin`` is the one quantity Phase C's exploration arm is
        defined over.

        Falls back to the store when the engine is absent, which loses the
        counter and nothing else.
        """
        try:
            from haloysius.attunement.ledger import (
                StandingRequestLedger,
                record_reaction,
            )

            from .context import halbert_config

            ledger = StandingRequestLedger(
                self.store, self.persona_id, halbert_config()
            )
            return bool(record_reaction(
                ledger, attempt_id, reaction, self.subject_id
            ))
        except ImportError:
            return bool(self.store.update_reaction(attempt_id, reaction))


def default_reactions() -> Optional[ReactionRecorder]:
    """The recorder the findings surfaces use, or None.

    None rather than a raise: a dismissal must still dismiss when the
    ledger cannot be opened.
    """
    try:
        from .store import AttunementStore

        return ReactionRecorder(AttunementStore())
    except Exception as exc:
        logger.warning("attunement: could not open the outcome ledger: %s", exc)
        return None


def note(reaction: str, finding_id: Optional[str]) -> bool:
    """Label ``finding_id``'s most recent attempt. Never raises.

    The one call the findings surfaces make, so that a route needs to know
    the name of the reaction and nothing else about the ledger.
    """
    recorder = default_reactions()
    if recorder is None:
        return False
    method = {
        "dismissed": recorder.on_dismissed,
        "not_now": recorder.on_snoozed,
        "engaged": recorder.on_engaged,
    }.get(reaction)
    if method is None:  # pragma: no cover - a typo in a caller
        logger.warning("attunement: unknown reaction %r", reaction)
        return False
    return method(finding_id)
