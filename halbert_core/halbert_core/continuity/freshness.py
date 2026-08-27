# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Look before you speak: where an answer is allowed to come from.

Founder direction 2026-08-26: *"yes probe go look first too."*

Halbert stores a note — *"Jul 14: set up the media share at /srv/media"* — and
six weeks later is asked whether the share is working. Answering from the note
is fast and may be wrong, with nothing to show it was wrong. Answering from a
live check is correct. This module decides which is allowed, deterministically.

The rule it encodes (design strategies §4.2, the re-observability rule): memory
holds what cannot be re-derived — intent, rationale, what was tried and ruled
out, preferences, commitments. The **machine** holds current state. So a claim
about current state is never answered from memory.

The cheap part, and the reason this is affordable at all: **the ledger is
usually the probe.** A state tracker that recorded ``service:nginx`` thirty
seconds ago has already looked; reading that costs one indexed query and no
subprocess. Only when the ledger has nothing, or holds a reading old enough to
be a memory rather than an observation, does a real command have to run — and
its result is written back, so the next question is free again.

Nothing here runs commands or calls a model. It returns a decision; the caller
acts on it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

__all__ = [
    "AnswerSource",
    "Decision",
    "decide",
    "is_re_observable",
    "DEFAULT_FRESH_SECONDS",
    "RE_OBSERVABLE_PREDICATES",
    "DURABLE_RECEIPT_FIELDS",
    "RE_OBSERVABLE_RECEIPT_FIELDS",
]

#: How recent a ledger reading must be to count as *looking* rather than
#: *remembering*. A minute-old reading of a service is, for a sysadmin question,
#: now. Raise it to probe less often at the cost of freshness; lower it to probe
#: more. This is the single dial on how chatty "checking now" makes Halbert.
DEFAULT_FRESH_SECONDS = 60.0

#: Predicates describing machine state, which the host can always re-derive.
#: The first four are what Halbert's own state trackers record.
RE_OBSERVABLE_PREDICATES = frozenset({
    "disk_health", "service_status", "cpu_load", "memory_usage",
    "load_average", "admin_presence",
    "mounted", "running", "enabled", "listening", "installed_version",
    "free_space", "permissions", "owner", "port", "pid", "uptime",
})

#: Receipt lines that stay true because they record what happened, not what is.
DURABLE_RECEIPT_FIELDS = frozenset({
    "Title", "When", "Domains", "Entities", "Started with",
    "Commands", "Files written", "Open loop",
})

#: Receipt lines that can hold a present-tense claim about mutable state. This
#: is the one field in Plan A's nine that fails the re-observability test.
RE_OBSERVABLE_RECEIPT_FIELDS = frozenset({"Last said"})


class AnswerSource(Enum):
    """Where the caller is permitted to get the answer."""

    #: The ledger holds a fresh reading. Authoritative, one query, no subprocess.
    LEDGER = "ledger"
    #: Nothing fresh enough exists. Run the check, answer from it, record it.
    PROBE = "probe"
    #: A durable claim — intent, rationale, a commitment. Memory is correct here.
    MEMORY = "memory"


@dataclass(frozen=True)
class Decision:
    source: AnswerSource
    reason: str
    #: age in seconds of the ledger reading consulted, when there was one
    age_seconds: Optional[float] = None
    #: the current value, only when ``source is LEDGER``
    value: Optional[str] = None
    #: when the fact was last established, for the "we set that on ..." phrasing
    observed_at: Optional[float] = None

    @property
    def must_look(self) -> bool:
        return self.source is AnswerSource.PROBE

    def preamble(self) -> str:
        """The sentence Halbert says before answering, or '' when none is needed.

        This is the visible half of the behaviour: the admin should be able to
        see that a stale claim was re-checked rather than repeated.
        """
        if self.source is not AnswerSource.PROBE or self.observed_at is None:
            return ""
        day = datetime.fromtimestamp(self.observed_at, timezone.utc).strftime("%Y-%m-%d")
        return f"We last saw that on {day} — checking now."


def is_re_observable(predicate: str) -> bool:
    """True when the host can re-derive this fact, so memory must not answer it."""
    return (predicate or "").strip().lower() in RE_OBSERVABLE_PREDICATES


def decide(
    subject: str,
    predicate: str,
    store=None,
    fresh_seconds: float = DEFAULT_FRESH_SECONDS,
    now: Optional[float] = None,
) -> Decision:
    """Decide where an answer about ``subject``/``predicate`` may come from.

    Args:
        subject: e.g. ``"service:nginx"``.
        predicate: e.g. ``"service_status"``.
        store: a :class:`~halbert_core.continuity.state_store.StateStore`, or
            None when no ledger is available.
        fresh_seconds: how recent a reading must be to count as looking.
        now: injected clock for tests.

    A durable predicate returns MEMORY. A re-observable one returns LEDGER when
    a reading is fresh enough, and PROBE otherwise — including when the ledger
    has never seen it, which is the common case on a new install.
    """
    ts = time.time() if now is None else now

    if not is_re_observable(predicate):
        return Decision(
            AnswerSource.MEMORY,
            f"{predicate!r} is not re-observable; memory is the right source",
        )

    if store is None:
        return Decision(
            AnswerSource.PROBE,
            "no ledger available; the host must be checked",
        )

    current = store.current_state(subject=subject, predicate=predicate)
    if not current:
        return Decision(
            AnswerSource.PROBE,
            f"ledger has never observed {subject}/{predicate}",
        )

    triple = current[0]
    age = ts - triple.valid_from
    if age <= fresh_seconds:
        return Decision(
            AnswerSource.LEDGER,
            f"ledger reading is {age:.0f}s old, within {fresh_seconds:.0f}s",
            age_seconds=age,
            value=triple.object,
            observed_at=triple.valid_from,
        )
    return Decision(
        AnswerSource.PROBE,
        f"ledger reading is {age:.0f}s old, older than {fresh_seconds:.0f}s — "
        f"that is a memory, not an observation",
        age_seconds=age,
        observed_at=triple.valid_from,
    )
