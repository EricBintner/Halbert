# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The affordance — axis 2 of five.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.2:

    Affordance — is the hardware/software present?
    Unknown → DENY, rendered "unavailable on this machine", never "off".

Two presence sources, in a strict precedence:

1. **The explicit table** (``AffordanceTable``) — deliberate assertions the
   wiring layers (D3-P5) make about hardware and software the probe registry
   cannot see: cameras, displays, microphones. An explicit entry beats the
   registry in both directions.
2. **The probe registry** — but only for the ``sys.*`` ids, and only by
   delegation: this module maps ``sys.local_llm`` → the ``CAP_LOCAL_LLM``
   constant owned by ``halbert_core.capabilities`` and asks the registry's
   ``has()``. **The probe logic is not duplicated and is never edited here**
   (single source of truth stays ``capabilities.py``).

A probe is presence, never a grant (§1.1). Nothing in this module is ever
consulted by the consent, ceiling, or OS-grant axes.

Fail-closed rules, pinned by test:

- an id outside the shipped vocabulary is never available;
- an in-vocabulary id with no presence evidence anywhere is not available;
- an out-of-vocabulary id on an explicit table raises at construction —
  presence may not be asserted for a capability that does not exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional

from ...capabilities import (
    CAP_DISCOVERY,
    CAP_LOCAL_LLM,
    CAP_SECURE_MODEL,
    CAP_SOURCEPREP,
)
from .ceiling import VOCABULARY

#: The only ids whose presence is delegated to the capabilities.py probe
#: registry. The names are the registry's own constants — imported, never
#: restated — so this table cannot drift from the probes it defers to.
REGISTRY_BACKED_CAPABILITIES = {
    "sys.local_llm": CAP_LOCAL_LLM,
    "sys.secure_model": CAP_SECURE_MODEL,
    "sys.sourceprep": CAP_SOURCEPREP,
    "sys.discovery": CAP_DISCOVERY,
}


@dataclass(frozen=True)
class AffordanceTable:
    """Explicit presence assertions for ids the probe registry cannot see.

    ``present``  — asserted available on this machine.
    ``absent``   — asserted unavailable; the UI vocabulary is "unavailable
                   on this machine", never "off".

    Construction fails loudly on ids outside the vocabulary and on an id
    asserted both ways — presence is a fact about a shipped capability, and
    a table that could invent or contradict itself must never exist.
    """

    present: FrozenSet[str] = frozenset()
    absent: FrozenSet[str] = frozenset()

    def __post_init__(self) -> None:
        for entry in (*self.present, *self.absent):
            if entry not in VOCABULARY:
                raise ValueError(
                    f"Affordance table asserts '{entry}', which is outside the "
                    f"shipped vocabulary. Presence may not be asserted for a "
                    f"capability that does not exist."
                )
        overlap = self.present & self.absent
        if overlap:
            raise ValueError(
                f"Affordance table asserts both present and absent: {sorted(overlap)}."
            )


#: The empty table: no explicit assertions. Only registry-backed ids can
#: be available through it — everything else denies (missing affordance).
EMPTY_AFFORDANCE = AffordanceTable()


def affords(
    capability_id: str,
    table: AffordanceTable = EMPTY_AFFORDANCE,
    *,
    registry: Optional[object] = None,
) -> bool:
    """Is the hardware/software for this capability present on this machine?

    Unknown → not available. Explicit table entries win over the registry;
    the registry is consulted only for ``sys.*`` ids the table does not
    cover; every other id needs an explicit table entry or it denies.

    ``registry`` is injectable for tests. The default resolves to the real
    ``capabilities.get_capability_registry()`` singleton lazily, so importing
    this module never probes the host.
    """
    if capability_id not in VOCABULARY:
        return False
    if capability_id in table.absent:
        return False
    if capability_id in table.present:
        return True
    registry_name = REGISTRY_BACKED_CAPABILITIES.get(capability_id)
    if registry_name is None:
        # No probe exists for this id and nobody asserted presence: missing
        # affordance denies.
        return False
    if registry is None:
        from ...capabilities import get_capability_registry

        registry = get_capability_registry()
    return bool(registry.has(registry_name))