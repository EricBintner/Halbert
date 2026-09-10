# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The channel layer: Halbert's ingress surfaces as first-class channels.

D-4 design (``.handoff/DESIGN-CHANNEL-LAYER-2026-09-07.md`` §1) — packet C1.
A channel is an ingress/egress *fact* that feeds the turn; persona claims
and gates consume it downstream, which is why this lives beside
``threads.py`` and ``steering.py`` and not in ``persona/``. The contract
is lifted, not the surface area (design §1): no plugin SDK, no manifests,
no per-channel allowlists — the command axis already lives in
``GUEST_ALLOWED_TOOLS``/RoleGate. Six fields, each earning its place
against a seam that exists or is being built in this series:

- ``id`` — provenance, stamped into the user row's ``metadata.channel``
  (recording, never gating): "how did this turn arrive".
- ``claim_ceiling`` — the security field. ``claim_source`` used to be a
  client-supplied string, so any HTTP client could self-declare an
  ASSERTED (or VERIFIED) claim and its own RoleGate role. The ceiling is
  the most a claim arriving on this channel may carry;
  ``stamped_claim_source`` enforces it.
- ``default_role`` — the role the channel itself asserts when the turn
  names no speaker: typed is admin (the dashboard session is
  authenticated), voice is unknown (never a silent admin).
- ``busy_verbs`` — PACKET-07 Phase C's record: busy behavior is a
  capability of the channel, not a user setting (consumed by C3).
- ``delivery`` — what the channel can honestly receive (consumed by C4's
  tee: a channel not in a turn's delivery set was never owed a delivery).
- ``transcribe_before_command`` — the Hermes voice rule: a command
  arrives as transcript, so the browser-relay seam cannot regress it.

The terminal channel IS declared (C5, founder ruling 2026-09-07: "the
terminal becomes a third talk channel, ASSERTED via dashboard token" —
design §8 Q1's recommendation accepted, Q3 answered yes-with-caution).
It is the talk channel of a terminal-originated *client* — a turn that
arrives at the one talk door having been typed at the machine's
terminal surface. The existing terminal subsystem (pty spawn/exec/stage,
``routes/terminal.py``, the Plan B watched shells and their
``terminal_blocks``) is a tool surface and stays one: it runs commands,
it does not talk.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Dict, Optional

from ..persona.claims import CLAIM_SOURCE_STRENGTHS, ClaimStrength

logger = logging.getLogger("halbert.agents.channels")


@dataclass(frozen=True)
class ChannelDeclaration:
    """One ingress surface, as data. Frozen: the registry is policy other
    code reads to gate with, so a mutated declaration would be policy
    written by assignment."""

    id: str
    #: The strongest claim strength a turn arriving here may carry.
    claim_ceiling: ClaimStrength
    #: The speaker role the channel itself asserts when the turn names no
    #: speaker. Typed turns are admin (dashboard sessions are
    #: authenticated); voice turns are unknown — never a silent admin.
    default_role: str
    #: Mid-turn verbs this channel may use (subset of stop/steer/queue).
    busy_verbs: frozenset
    #: Egress surfaces this channel can honestly receive (sse/tts/...).
    delivery: frozenset
    #: Voice rule: commands arrive as transcript, never a placeholder.
    transcribe_before_command: bool


#: The dashboard door: the authenticated HTTP surface. Ceiling ASSERTED
#: (the session token the server validates), default role admin — the
#: convention process() has always applied to typed turns. Busy verbs
#: (PACKET-07 Phase C record): text steers, /stop claims the generation.
DASHBOARD_CHANNEL = ChannelDeclaration(
    id="dashboard",
    claim_ceiling=ClaimStrength.ASSERTED,
    default_role="admin",
    busy_verbs=frozenset({"stop", "steer"}),
    delivery=frozenset({"sse"}),
    transcribe_before_command=False,
)

#: The voice surface: browser-relayed STT today (the Wyoming path
#: server-side). Speaker verification is its strongest honest source
#: (ceiling ASSERTED); an unidentified speaker is "unknown", never admin.
#: A spoken follow-up steers; playback interruption is barge-in's job,
#: below the state machine.
VOICE_CHANNEL = ChannelDeclaration(
    id="voice",
    claim_ceiling=ClaimStrength.ASSERTED,
    default_role="unknown",
    busy_verbs=frozenset({"steer"}),
    delivery=frozenset({"sse", "tts"}),
    transcribe_before_command=True,
)

#: The terminal talk channel (C5, founder ruling 2026-09-07): a turn
#: typed at the machine's terminal surface and submitted to the one talk
#: door. Ceiling ASSERTED via the dashboard token (the ruling accepted
#: design §8 Q1's recommendation — the same credential the server
#: validates for any local client); default role admin, the terminal's
#: own convention: the owner's shell on the owner's machine. Busy verbs
#: (design §4 table, the C5 row): a CLI user accepts whole-turn queuing
#: as the first-class mode; steer rides the same slot when a turn is
#: live — /stop stays unclaimed here, which C3's busy unification
#: consumes. Delivery is the door's own SSE stream; C4's event tee (the
#: design names the terminal a tee consumer) extends this set when that
#: dispatch lands, not before — a channel declares only what it can
#: honestly receive today. Commands are typed, never transcribed.
TERMINAL_CHANNEL = ChannelDeclaration(
    id="terminal",
    claim_ceiling=ClaimStrength.ASSERTED,
    default_role="admin",
    busy_verbs=frozenset({"queue", "steer"}),
    delivery=frozenset({"sse"}),
    transcribe_before_command=False,
)

#: Every admitted ingress. Unknown channel fails closed (below) — an
#: ingress that resolves to nothing here is refused, never silently
#: treated as typed.
CHANNEL_REGISTRY: Dict[str, ChannelDeclaration] = {
    DASHBOARD_CHANNEL.id: DASHBOARD_CHANNEL,
    VOICE_CHANNEL.id: VOICE_CHANNEL,
    TERMINAL_CHANNEL.id: TERMINAL_CHANNEL,
}

#: The source the SERVER stamps for each channel — the design §5 table:
#: what each channel actually is. Used when the wire declares a source
#: the channel cannot carry: the claim clamps to this, never to anything
#: the wire named. The terminal's stamp is the SAME dashboard token the
#: server validated on the request (the founder ruling: ASSERTED via the
#: existing dashboard token — an OS uid is not a cryptographic device
#: credential, so no ``local_console`` VERIFIED source exists, per the
#: ruling's decline of design §8 Q1's alternative).
CHANNEL_CLAIM_STAMP: Dict[str, str] = {
    "dashboard": "dashboard_token",
    "voice": "voice_speaker_verification",
    "terminal": "dashboard_token",
}


class ChannelRefused(Exception):
    """Fail-closed refusal: an ingress that resolves to no registered
    channel. Mirrors guest.py's ``no_gate_list_configured`` posture —
    unwritten policy denies, it never silently allows."""

    decisive_gate = "channel_registry"
    reason_code = "no_channel_configured"

    def __init__(self, modality: Optional[str]):
        self.modality = modality
        super().__init__(f"no registered channel for modality {modality!r}")

    def payload(self) -> Dict[str, str]:
        """The admission-shape deny payload.

        R-01 Phase E (A12-G6): this used to hand-copy the shape with a
        comment saying it mirrored ``guest.py``'s ``_deny_payload``. A
        comment is not a shared function -- and the modality was
        interpolated into the message, so the one door every turn arrives
        at echoed the client's own string back at it. It renders through
        the shared payload now; the refused modality goes in the log,
        where a diagnostic belongs.
        """
        from ..persona.admission import deny_payload
        return deny_payload(self.decisive_gate, self.reason_code)

    def gate(self):
        """This refusal as a named gate, for the door's decision record."""
        from ..persona.admission import block
        return block(self.decisive_gate, "ingress", self.reason_code, 400)


def resolve_channel(modality: Optional[str]) -> ChannelDeclaration:
    """Resolve the ingress channel from the turn's modality.

    The typed values map to the dashboard door (a typed turn IS a
    dashboard turn: the same authenticated HTTP surface, which is why
    ``"text"`` resolves like an absent modality); ``"voice"`` maps to the
    voice channel; ``"terminal"`` maps to the terminal talk channel (C5:
    a turn typed at the machine's terminal surface). Normalization
    matches process()'s own, so the route and the state machine can
    never disagree about which channel a turn arrived on. Anything else
    raises :class:`ChannelRefused` — fail closed, in the admission
    module's shape.
    """
    normalized = str(modality or "").strip().lower()
    if normalized in ("", "text"):
        return CHANNEL_REGISTRY["dashboard"]
    if normalized == "voice":
        return CHANNEL_REGISTRY["voice"]
    if normalized == "terminal":
        return CHANNEL_REGISTRY["terminal"]
    raise ChannelRefused(modality)


def stamped_claim_source(
    channel: ChannelDeclaration,
    declared: Optional[str],
) -> Optional[str]:
    """The claim source a turn may carry — derived from the resolved
    channel, never from the wire's word alone. Before
    ``claims.claim_from_source`` ever sees a source, this decides which
    source the turn actually carries:

    - Nothing declared stamps nothing: absent fields keep today's
      behavior exactly (04-A1's byte-identical pin) — a typed turn
      records no claim and an unidentified voice turn fails closed to
      UNVERIFIED in the ladder. (The terminal channel's own identity is
      stamped downstream of this function — see ``CHANNEL_CLAIM_STAMP``
      and the state machine's C5 branch — so an absent field can no more
      weaken a terminal turn than a declared one can raise it.)
    - The dashboard door accepts no client-named sources at all: every
      declared claim clamps to the channel's own stamp
      (``dashboard_token``), the one credential the server actually
      validated. A forged ``voice_speaker_verification`` can never mint
      a speaker claim here. The terminal channel holds the same rule
      (C5): its identity IS the dashboard token, so a declared source
      over it can only ever clamp to that stamp.
    - The voice channel passes a declared source at or below its ceiling
      through unchanged and a declared source ABOVE the ceiling clamps
      down to the channel's stamp: the wire can raise nothing. Since C2
      (voice honesty) the hint the voice door hands this function is not
      the wire's word at all — it is the relay receipt's stamp
      (``dashboard/voice_relay.py``), so this clamp is the voice
      channel's LAST line of defence, not its first; the wire's fields
      are ignored upstream of it.
    """
    if not declared:
        return None
    strength = CLAIM_SOURCE_STRENGTHS.get(declared, ClaimStrength.UNVERIFIED)
    stamp = CHANNEL_CLAIM_STAMP[channel.id]
    if channel.id in ("dashboard", "terminal") or strength > channel.claim_ceiling:
        if declared != stamp:
            logger.info(
                "claim_clamped: channel=%s declared_source=%s stamped_source=%s "
                "ceiling=%s",
                channel.id, declared, stamp, channel.claim_ceiling.name,
            )
        return stamp
    return declared


#: The resolved channel of the turn that is currently running — bound by
#: ``process()`` under the turn lock (the same copy-down-the-task pattern
#: as ``current_turn_digest``), read by the ThreadManager when it writes
#: the user row. Recording only: nothing gates on this. The binding dies
#: with the turn in process()'s finally, so no channel bleeds into a
#: later turn.
current_turn_channel: ContextVar[Optional[ChannelDeclaration]] = ContextVar(
    "halbert_current_turn_channel", default=None
)