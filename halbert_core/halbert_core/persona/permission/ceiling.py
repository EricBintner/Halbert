# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The capability vocabulary and the ceiling — axis 1 of five.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.2/§1.3:

    Ceiling  — can this *channel* deliver it at all?
    Unknown  — DENY. Unknown channel = empty set.

One flat, dotted, stable namespace; every id declares a kind. The ceiling is
why the App Store build is *provably* incapable rather than merely switched
off: an id that is not on the channel's ceiling is a compile-time property,
not a promise about behaviour.

Placement note (D-3): the design names ``capabilities/ceiling.py`` as the
home, but ``halbert_core/capabilities.py`` is a module file — a package of
the same name cannot coexist with it. The five-axis modules live here, under
``persona/permission/``, beside the policy lattice they compose with.

House invariants, all fail-closed:

- A shipped id is **never renamed** — a renamed capability is a silently
  re-granted capability. ``CapabilityCeiling`` construction therefore
  *raises* on any id outside ``VOCABULARY``; it never quietly admits one.
- ``egress.telemetry`` is *declared absent*: it exists in the vocabulary so
  ``tests`` can assert no build ships analytics, and it is barred from every
  ceiling structurally (``NEVER_CEILING_IDS``), so "Data Not Collected" is
  provable rather than merely stated.
- Only ``sensor`` / ``reach`` / ``egress`` / ``auto`` take consent records
  (§1.3). ``sys.*`` is affordance-only and has no consent surface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Mapping


class CapabilityKind:
    """The closed set of kinds a vocabulary id can declare."""

    SENSOR = "sensor"    # on-demand or continuous capture of the world
    REACH = "reach"      # where the machine may read and write
    EGRESS = "egress"    # what may leave the machine
    AUTO = "auto"        # what may happen with nobody in the turn
    SURFACE = "surface"  # who may reach *in*
    SYS = "sys"          # affordance-only, never consented


# The shipped vocabulary — PERMISSION-AND-CONSENT-SYSTEM §1.3, verbatim.
# Do not rename entries; add new ids only with a design decision recorded.
VOCABULARY: Dict[str, str] = {
    # kind: sensor
    "sensor.screen": CapabilityKind.SENSOR,
    "sensor.screen.continuous": CapabilityKind.SENSOR,
    "sensor.window_titles": CapabilityKind.SENSOR,
    "sensor.camera": CapabilityKind.SENSOR,
    "sensor.camera.continuous": CapabilityKind.SENSOR,
    "sensor.camera.network": CapabilityKind.SENSOR,
    "sensor.mic.push_to_talk": CapabilityKind.SENSOR,
    "sensor.mic.continuous": CapabilityKind.SENSOR,
    "sensor.voiceprint": CapabilityKind.SENSOR,   # biometric — Art. 9 / BIPA
    "sensor.photos": CapabilityKind.SENSOR,       # not implemented, not rendered
    "sensor.journal": CapabilityKind.SENSOR,
    "sensor.hardware": CapabilityKind.SENSOR,
    "sensor.config_watch": CapabilityKind.SENSOR,
    # kind: reach
    "reach.fs.read": CapabilityKind.REACH,
    "reach.fs.write": CapabilityKind.REACH,
    "reach.config.read": CapabilityKind.REACH,
    "reach.config.write": CapabilityKind.REACH,
    "reach.terminal": CapabilityKind.REACH,
    "reach.privileged": CapabilityKind.REACH,
    "reach.service": CapabilityKind.REACH,
    "reach.package": CapabilityKind.REACH,
    "reach.network": CapabilityKind.REACH,
    "reach.home": CapabilityKind.REACH,
    "reach.display_power": CapabilityKind.REACH,
    # kind: egress
    "egress.cloud_model": CapabilityKind.EGRESS,
    "egress.web_search": CapabilityKind.EGRESS,
    "egress.web_fetch": CapabilityKind.EGRESS,
    "egress.peer": CapabilityKind.EGRESS,
    "egress.acoustid": CapabilityKind.EGRESS,
    "egress.telemetry": CapabilityKind.EGRESS,     # declared absent — never granted
    # kind: auto
    "auto.scheduler": CapabilityKind.AUTO,
    "auto.observe": CapabilityKind.AUTO,
    "auto.capture_on_intent": CapabilityKind.AUTO,
    "auto.capture_on_error": CapabilityKind.AUTO,
    "auto.speak": CapabilityKind.AUTO,
    "auto.act": CapabilityKind.AUTO,               # never granted by any profile
    # kind: surface — who may reach *in* (loopback is the floor, not a capability)
    "surface.lan_api": CapabilityKind.SURFACE,
    "surface.mcp": CapabilityKind.SURFACE,
    "surface.wyoming": CapabilityKind.SURFACE,
    "surface.ha_component": CapabilityKind.SURFACE,
    # kind: sys — affordance only, never consented
    "sys.local_llm": CapabilityKind.SYS,
    "sys.secure_model": CapabilityKind.SYS,
    "sys.sourceprep": CapabilityKind.SYS,
    "sys.discovery": CapabilityKind.SYS,
}

# Ids that exist in the vocabulary so tests can prove their absence, but that
# no ceiling may ever carry. egress.telemetry is here so "Data Not Collected"
# is a structural property of every build.
NEVER_CEILING_IDS: FrozenSet[str] = frozenset({"egress.telemetry"})

# Only these kinds take consent records (§1.3). sys.* is affordance-only.
CONSENTING_KINDS: FrozenSet[str] = frozenset({
    CapabilityKind.SENSOR,
    CapabilityKind.REACH,
    CapabilityKind.EGRESS,
    CapabilityKind.AUTO,
})


def takes_consent_records(capability_id: str) -> bool:
    """True only for vocabulary ids of a consenting kind (sensor/reach/egress/auto).

    Unknown ids never take consent records — they are not capabilities at all.
    """
    return VOCABULARY.get(capability_id) in CONSENTING_KINDS


@dataclass(frozen=True)
class CapabilityCeiling:
    """A closed set of capability ids one channel can deliver at all.

    Fail-closed by construction:

    - ids outside ``VOCABULARY`` raise at construction — a ceiling never
      quietly invents or renames a capability (§1.3: "a shipped id is never
      renamed; a renamed capability is a silently re-granted capability").
    - ids in ``NEVER_CEILING_IDS`` raise at construction.
    - ``permits`` on anything not in the set — including ids the vocabulary
      has never heard of — is False. The Windows ceiling is the empty set
      until its gates are green; the app refuses rather than degrading.
    """

    ids: FrozenSet[str]

    def __post_init__(self) -> None:
        unknown = self.ids - VOCABULARY.keys()
        if unknown:
            raise ValueError(
                f"Ceiling contains ids outside the shipped vocabulary: "
                f"{sorted(unknown)}. A renamed capability is a silently "
                f"re-granted capability — add it to VOCABULARY deliberately "
                f"or fix the id."
            )
        barred = self.ids & NEVER_CEILING_IDS
        if barred:
            raise ValueError(
                f"Ceiling contains declared-absent ids: {sorted(barred)}. "
                f"egress.telemetry is permanently absent so the privacy "
                f"label is provable by test."
            )

    def permits(self, capability_id: str) -> bool:
        """Can this channel deliver this capability at all? Unknown → False."""
        return capability_id in self.ids

    def __contains__(self, capability_id: object) -> bool:
        return capability_id in self.ids

    def __len__(self) -> int:
        return len(self.ids)


#: The empty ceiling: unknown channel, or a channel that has shipped no
#: gates yet (Windows until W1–W13). Denies everything.
EMPTY_CEILING = CapabilityCeiling(frozenset())


def ceiling_from_ids(ids) -> CapabilityCeiling:
    """Build a ceiling from any iterable of shipped vocabulary ids."""
    return CapabilityCeiling(frozenset(ids))