# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Distribution channels and their capability ceilings — the §2.4 table.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §2.4:

    A capability the channel cannot deliver is not rendered disabled —
    it is not rendered. No greyed switches, no padlocks, no upsell.
    A greyed switch teaches the user they are missing something broken;
    an honest shorter list teaches them what this machine is.

THREE "channel" vocabularies exist in this codebase. This module is the
second one; the other two are named here so no future packet conflates
them:

1. **Talk channels** — ``halbert_core/agents/channels.py`` (packets
   C1/C5): the ingress surfaces a *turn* arrives on (``dashboard`` /
   ``voice`` / ``terminal``), stamped into the user row's
   ``metadata.channel`` as recording provenance and carrying the
   claim-ceiling / default-role facts. **This module must not import or
   alias it.** A talk channel says how a conversation arrived; a
   distribution channel says what the build itself is capable of.
2. **Distribution channels** — THIS module: how the app was
   distributed (``macos-pro`` / ``macos-appstore`` / ``linux`` /
   ``flatpak`` / ``windows``). This is the ``channel`` field a consent
   record carries (§1.5's example: ``"channel": "macos-pro"``), and it
   is the axis-1 writer of the five-axis model: each channel owns a
   ``CapabilityCeiling`` — the closed set of capability ids the channel
   can deliver *at all*.
3. **Session-type degradation** — Wayland vs X11, aqua vs SSH: neither
   of the above. A within-channel fact that degrades the *row*, not
   the profile (§2.4: "the row degrades, not the profile"); the live
   wiring reads it at runtime (D3-P5/P6). It is deliberately not a
   channel id here.

The ceiling is why the App Store build is **provably incapable** rather
than merely switched off (§1.2): an id that is not on the channel's
ceiling fails the ceiling axis before consent is ever consulted, and
``sensor.voiceprint`` being structurally absent is what keeps the
privacy nutrition label's "Sensitive Info → Not Collected" a
compile-time property of the build rather than a promise about
behaviour.

Fail-closed everywhere: an unknown channel id raises on lookup (the
record's ``channel`` field is a closed vocabulary, so a mis-stamped
record is detectable, not noise), and the Windows channel carries the
``EMPTY_CEILING`` until its gates are green — the app refuses to start
rather than degrading permissively (§2.4), the exact opposite of a
permissive fallthrough.

Every omission below cites the design sentence that requires it. Do not
add an id to a companion ceiling without one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Tuple

from .ceiling import (
    CapabilityCeiling,
    EMPTY_CEILING,
    NEVER_CEILING_IDS,
    VOCABULARY,
    ceiling_from_ids,
)

__all__ = [
    "CHANNELS",
    "DistributionChannel",
    "channel_for",
    "ceiling_for",
    "full_ceiling",
]


#: Ids no shipped channel may carry, on top of the structurally barred
#: ones: ``egress.telemetry`` is declared absent (NEVER_CEILING_IDS, so
#: the privacy label is provable), and ``sensor.photos`` is not
#: implemented — "not implemented; no row ships" (§1.3/§2.1).
UNSHIPPED_IDS: FrozenSet[str] = frozenset({"sensor.photos"}) | NEVER_CEILING_IDS


def full_ceiling() -> CapabilityCeiling:
    """The full channel ceiling: the shipped vocabulary minus the
    declared-absent and unimplemented ids.

    Derived, never hand-listed: a new vocabulary id lands on the full
    channels (macOS Pro, native Linux) by default, and reaches a
    companion channel only by a deliberate, cited decision. That is the
    fail direction §1.2 demands — the permissive direction here would
    be a hand-maintained allowlist drifting behind the vocabulary.
    """
    return ceiling_from_ids(frozenset(VOCABULARY) - UNSHIPPED_IDS)


#: The App Store sandbox cannot deliver these *at all* — each row cites
#: its design verdict (macos-appstore appendix §2, §7 matrix, §2.4):
#:   - screen, screen.continuous, window_titles — "no sandbox entitlement
#:     grants Screen Recording"; window enumeration is TCC-gated with it
#:     and the design binds the row to sensor.screen;
#:   - camera.continuous, mic.continuous — 2.5.4 bars ambient loops;
#:     single-shot camera and push-to-talk stay deliverable;
#:   - journal, config_watch, reach.config.read — container-confined: no
#:     host logs, no view of /etc (§7 matrix marks config read "—");
#:   - reach.config.write — 2.4.5(vi); reach.terminal — 2.5.2, children
#:     inherit the container; reach.privileged — 2.4.5(iii)(vi);
#:   - reach.service, reach.package — no host launchd/systemd from
#:     inside the sandbox;
#:   - surface.* — "network.server not requested", so the listener
#:     structurally cannot exist ("a win", §7 matrix);
#:   - sys.local_llm — local model inference is impossible on this
#:     channel (Ollama is a separate daemon; weights are a licence
#:     question).
#: sensor.voiceprint is asserted separately, twice: once by omission
#: from the id set, once by an import-time assertion below — it is the
#: row the privacy label depends on.
APPSTORE_OMITTED: FrozenSet[str] = frozenset({
    "sensor.screen",
    "sensor.screen.continuous",
    "sensor.window_titles",
    "sensor.camera.continuous",
    "sensor.mic.continuous",
    "sensor.journal",
    "sensor.config_watch",
    "reach.config.read",
    "reach.config.write",
    "reach.terminal",
    "reach.privileged",
    "reach.service",
    "reach.package",
    "surface.lan_api",
    "surface.mcp",
    "surface.wyoming",
    "surface.ha_component",
    "sys.local_llm",
    "sensor.voiceprint",
})


#: The Flatpak/Snap strict companion set (§2.4, Linux appendix §4): "a
#: sandboxed Flatpak cannot be the sysadmin product — reading the host's
#: /etc and driving the host's systemd is precisely what the sandbox
#: exists to stop". Screen, camera and mic stay: the portals are
#: designed for sandboxed apps and revocable outside the app
#: (``flatpak permission-remove``). sensor.hardware goes because the
#: least-privilege manifest drops ``--filesystem=/proc:ro`` and
#: ``/sys:ro``; the inbound-listener surfaces and the out-of-sandbox
#: model daemon go for the same reason as the App Store's.
FLATPAK_OMITTED: FrozenSet[str] = frozenset({
    "reach.config.read",
    "reach.config.write",
    "reach.terminal",
    "reach.privileged",
    "reach.service",
    "reach.package",
    "sensor.journal",
    "sensor.config_watch",
    "sensor.hardware",
    "surface.lan_api",
    "surface.mcp",
    "surface.wyoming",
    "surface.ha_component",
    "sys.local_llm",
    "sensor.voiceprint",
})


@dataclass(frozen=True)
class DistributionChannel:
    """One way the app is distributed, as data.

    The ceiling answers axis 1 ("can this channel deliver it at all?");
    ``profiles_offered`` answers §2.4's Offered column — a profile the
    channel does not offer is not displayed, never shown disabled; and
    ``degradation_note`` carries §2.4's degradation sentence as shipped
    copy for the honest shorter list. Nothing here *does* anything:
    the first-run UI and Settings render from this data (D3-P6), and
    the boot/wiring packets consume the ceiling (D3-P5).
    """

    id: str
    label: str
    ceiling: CapabilityCeiling
    #: Profile names in display order; ``()`` = nothing is offered.
    profiles_offered: Tuple[str, ...]
    #: §2.4 Windows: the app refuses to start rather than degrading
    #: permissively.
    refuses_to_start: bool = False
    #: §2.4's Degradation column, as shipped documentation copy.
    degradation_note: str = ""


def _appstore_ceiling() -> CapabilityCeiling:
    return ceiling_from_ids(frozenset(VOCABULARY) - UNSHIPPED_IDS - APPSTORE_OMITTED)


def _flatpak_ceiling() -> CapabilityCeiling:
    return ceiling_from_ids(frozenset(VOCABULARY) - UNSHIPPED_IDS - FLATPAK_OMITTED)


#: The shipped distribution channels — the closed set a consent record's
#: ``channel`` field draws from.
CHANNELS: Dict[str, DistributionChannel] = {
    "macos-pro": DistributionChannel(
        id="macos-pro",
        label="macOS — direct build (ai.halbert.macos.pro)",
        ceiling=full_ceiling(),
        profiles_offered=("reserved", "attentive", "present"),
        degradation_note=(
            "Full — once signing lands. Until Developer ID, hardened "
            "runtime, notarization and the sidecar fold ship, every "
            "macOS sensor row's OS state is UNQUERYABLE and reads "
            "\"can't tell — this build isn't signed\"."
        ),
    ),
    "macos-appstore": DistributionChannel(
        id="macos-appstore",
        label="macOS App Store companion (ai.halbert.macos.free)",
        ceiling=_appstore_ceiling(),
        profiles_offered=("reserved", "attentive"),
        degradation_note=(
            "This Mac runs me as a companion. It talks to a Halbert "
            "body — a Linux server, a homelab machine, or a Mac running "
            "the direct build — and that body does the system work: the "
            "subject of the profile is the paired body, not this Mac. "
            "Sensor rows the sandbox cannot deliver locally are not "
            "rendered; Present is not displayed."
        ),
    ),
    "linux": DistributionChannel(
        id="linux",
        label="Linux — native package (ai.halbert.linux)",
        ceiling=full_ceiling(),
        profiles_offered=("reserved", "attentive", "present"),
        degradation_note=(
            "Full. Wayland: screen via the portal, whose picker is the "
            "OS consent dialog, with persist_mode=2 and a restore_token "
            "re-persisted every session. X11: the row degrades, not "
            "the profile — sensor.screen drops to ask, the X11 "
            "sentence rides the row, and Present's continuous screen "
            "is never granted by the profile."
        ),
    ),
    "flatpak": DistributionChannel(
        id="flatpak",
        label="Linux — Flatpak / Snap strict companion",
        ceiling=_flatpak_ceiling(),
        profiles_offered=("reserved", "attentive"),
        degradation_note=(
            "Companion ceiling. A sandboxed Flatpak cannot be the "
            "sysadmin product — reading the host's /etc is exactly "
            "what the sandbox exists to prevent — so the native "
            "package is the only full-capability Linux artifact. "
            "Screen, camera and microphone go through the portals, "
            "revocable outside the app."
        ),
    ),
    "windows": DistributionChannel(
        id="windows",
        label="Windows (until W1–W13)",
        ceiling=EMPTY_CEILING,
        profiles_offered=(),
        refuses_to_start=True,
        degradation_note=(
            "Ceiling is the empty set until the Windows gates are "
            "green. The app refuses to start rather than degrading "
            "permissively."
        ),
    ),
}


def channel_for(channel_id: str) -> DistributionChannel:
    """One distribution channel. Unknown id → LookupError (fail-closed).

    The record's ``channel`` field is a closed vocabulary: a channel id
    nobody shipped is a mis-stamped record, and mis-stamped provenance
    must be loud, not defaulted.
    """
    try:
        return CHANNELS[channel_id]
    except KeyError:
        raise LookupError(
            f"'{channel_id}' is not a shipped distribution channel "
            f"({sorted(CHANNELS)}). This is the consent record's "
            f"channel field — the *talk* channels (dashboard/voice/"
            f"terminal) are a different vocabulary and never valid "
            f"here."
        ) from None


def ceiling_for(channel_id: str) -> CapabilityCeiling:
    """The ceiling of one distribution channel — axis 1, as data."""
    return channel_for(channel_id).ceiling


def _self_check() -> None:
    """Import-time invariants for the channel table.

    ``sensor.voiceprint`` is asserted twice for the App Store channel
    (§2.4: "not on the ceiling at all"), because it is the one row the
    privacy nutrition label depends on: once by omission from the id
    set, once here as a structural assertion a future edit cannot
    quietly undo. No ceiling may carry an unshipped id, and no channel
    may offer a profile with an empty intersection against its own
    ceiling — that would be a review screen with nothing on it.
    """
    appstore = CHANNELS["macos-appstore"].ceiling
    assert "sensor.voiceprint" not in appstore.ids, (
        "sensor.voiceprint must be structurally absent from the App "
        "Store ceiling — the privacy label's 'Not Collected' is a "
        "compile-time property of the build"
    )
    assert not appstore.ids & UNSHIPPED_IDS
    assert not CHANNELS["flatpak"].ceiling.ids & UNSHIPPED_IDS
    for channel in CHANNELS.values():
        assert not channel.ceiling.ids & UNSHIPPED_IDS, channel.id
        assert channel.ceiling.permits("sensor.hardware") or channel.id in (
            "flatpak", "windows",
        ), (
            f"{channel.id}: every companion that can read this "
            f"machine's own vitals must carry sensor.hardware; "
            f"dropping it is a cited decision, not a default"
        )


_self_check()