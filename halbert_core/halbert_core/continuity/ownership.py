# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Ownership is by actor, in every mode.

One function every conversation writer, the cognitive tick and the sensor
outputs consult before they write. The reasoning lives here and nowhere
else, so it can be reviewed in one place and pinned by one test file.

``.handoff/DESIGN-PERSONA-LAYERS-2026-09-06.md`` §4–§5, with the founder's
answers of 2026-09-06:

- **R1** The world — what the machine and the house are doing — is
  Halbert's in every mode. No guest, no privacy setting, routes it away.
- **R2** While a guest persona fronts (``persona/guest.py``), what was said
  to the guest belongs to the guest, at the guest's home. The cognitive
  tick is the guest's from the first turn, in every mode: Halbert's own
  psyche never learns a guest's evenings. The transcript is Halbert's in
  normal mode — tagged with the session so one ``redact_request`` erases
  it (D2) — and the guest's in private mode.
- **R3** Private mode is a set of sources handed to the guest
  (``persona/private_sources.py``). An observation from such a source is
  the guest's. Life safety is the exception (D1): the house is not private
  from its own smoke alarm.
- **P3** While a guest fronts, a writer nobody classified fails closed. A
  store added next year cannot leak; it announces itself by not working.

Without a guest, every answer is ``HALBERT`` and nothing here changes what
the writers did before it existed.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, FrozenSet, Optional

logger = logging.getLogger("halbert.continuity.ownership")


class Owner(str, Enum):
    HALBERT = "halbert"
    GUEST = "guest"
    DROP = "drop"


# Writers that record what the machine and the house are doing.
WORLD_KINDS: FrozenSet[str] = frozenset({
    "world",       # state_trackers, ha state, discoveries
    "finding",     # findings/store
    "timeline",    # continuity/timeline via the event mappers
    "config",      # config/watcher
    "outcome",     # model/outcome_store (telemetry, no content)
    "behavior",    # home/behavior
})

# Writers that record what was said, and to whom.
CONVERSATION_KINDS: FrozenSet[str] = frozenset({
    "conversation.message",   # conversation_sqlite.append_message
    "conversation.receipt",   # threads.py close receipts → ledger
    "cognition.tick",         # state_machine._run_cognition_tick
})

OBSERVATION_KIND = "observation"


def _fronting():
    try:
        from ..persona.guest import current_guest
        return current_guest()
    except Exception:
        return None


def _private_mode() -> bool:
    try:
        from ..persona.private_sources import active
        return active()
    except Exception:
        return False


def route_write(kind: str, *, actor: str = "", source: str = "") -> Owner:
    """Where a write of ``kind`` goes right now.

    ``actor`` and ``source`` are accepted for the callers that have them and
    for the log line; the decision keys on the kind, the guest session and
    the private-source map.
    """
    if kind == OBSERVATION_KIND:
        return route_observation(source)
    guest = _fronting()
    if guest is None:
        return Owner.HALBERT
    if kind in WORLD_KINDS:
        return Owner.HALBERT
    if kind == "cognition.tick":
        return Owner.GUEST
    private = _private_mode()
    if kind == "conversation.message":
        return Owner.GUEST if private else Owner.HALBERT
    if kind == "conversation.receipt":
        return Owner.DROP if private else Owner.HALBERT
    logger.warning(
        "Unclassified writer %r while %s fronts: failing closed (dropped)",
        kind, guest.persona.name,
    )
    return Owner.DROP


def route_observation(source_id: str, *, life_safety: bool = False) -> Owner:
    """Where an observation from ``source_id`` goes right now.

    A writer that cannot say where it looked (empty id) cannot have been
    handed over, so it stays Halbert's. Life safety is always Halbert's.
    """
    if life_safety or not source_id:
        return Owner.HALBERT
    if _fronting() is None:
        return Owner.HALBERT
    try:
        from ..persona.private_sources import owner_of
        return owner_of(source_id)
    except Exception:
        return Owner.HALBERT


def guest_request_id(session) -> str:
    """The session-scoped request id every guest-session write into
    Halbert's own stores carries, so ``redact_request`` can undo a session."""
    return f"guest-session-{session.id}"


def guest_tag() -> Dict[str, str]:
    """``actor`` and ``request_id`` for a write made while a guest fronts;
    ``{}`` otherwise. Writers merge this into their own provenance."""
    guest = _fronting()
    if guest is None:
        return {}
    return {"actor": f"guest:{guest.id}", "request_id": guest_request_id(guest)}
