# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The voice relay's receipts — the server-side knowledge a voice turn's
claim is stamped from (D-4 design, packet C2).

C1 made the claim *server-stamped* but the voice channel's stamp still
leaned on the wire's word: over the voice channel a declared
``voice_speaker_verification`` sits exactly AT the channel's ceiling
(ASSERTED), so the clamp could not tell the honest browser relay from a
raw POST saying the same words — ``modality="voice"`` +
``claim_source="voice_speaker_verification"`` + ``speaker_role="admin"``
minted an ASSERTED speaker claim with the owner's role. C2 closes it: the
relay (``app.py``'s ``_relay_voice_turn``) is where the server's own
knowledge of a spoken utterance lives — the speech track already ran STT
and speaker identification ONCE (transcribe-once), and the
``VoiceTurnObservation`` IS that single result. So the relay:

  1. records the observation under a server-minted single-use receipt
     token (``VoiceRelayReceipts.record``), and
  2. broadcasts the token with the transcript.

The browser threads the token back with the turn, and the talk door
(``routes/agent.py``) consumes it: the turn's claim, speaker name and
role are stamped from the OBSERVATION (:func:`stamped_voice_fields`),
never from the wire's fields — which are ignored entirely on voice
turns. Three fail-closed properties, all pinned by tests:

  * **single-use** — a receipt redeems once; a replayed token is spent;
  * **transcript-bound** — a receipt only stamps a claim onto the exact
    words it recorded (``transcribe_before_command``: the transcript IS
    the command text), so a stolen token cannot carry the observed
    speaker's identity onto different words;
  * **TTL-bounded** — a receipt the browser never redeemed ages out, so
    a turn arriving later cannot borrow an old utterance's identity.

A voice turn with no receipt (or a spent/expended/mismatched one) is an
*unidentified* voice turn: no claim, no name, the channel's own "unknown"
role — never refused (an unknown speaker may talk; the RoleGate clamps),
never a silent admin. This is not the delivery-obligation ledger the
design declined (§3): nothing here tracks whether anything was
*delivered*; it is ingress provenance for the claim stamp, and it holds a
handful of pending receipts, never a transcript log.
"""
from __future__ import annotations

import logging
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("halbert.dashboard.voice_relay")


@dataclass(frozen=True)
class RelayReceipt:
    """One relayed utterance, as the server observed it.

    The fields are the observation's own — the STT/speaker-id pipeline's
    actual result — never anything the wire said. ``verified`` is True
    when the pipeline matched an enrolled profile (a speaker_id), which
    is the only thing that can stamp a ``voice_speaker_verification``
    claim.
    """

    text: str
    speaker_name: str
    speaker_role: str
    verified: bool
    recorded_at: float


def _verified_from_observation(observation: Any) -> bool:
    """The pipeline's actual verification result.

    Verified when the identification matched an enrolled profile AND
    that profile resolved: a speaker id with no profile behind it names
    nobody (A09 bug 5). The pipeline clears the id in that case, and
    this is the belt on those braces -- the NAME is what a profile
    lookup produces, so an id without one is a match the store could not
    stand behind.
    """
    if not (getattr(observation, "speaker_id", "") or ""):
        return False
    return bool(getattr(observation, "speaker_name", "") or "")


#: How long two identical utterances are one utterance (A09 bug 6). The
#: origin's window: a relay that re-sends, a satellite that hears the
#: same phrase twice, or a double-submit used to become two TURNS -- two
#: answers, and for a command, two executions.
UTTERANCE_DEDUPE_SECONDS = 12.0


class VoiceRelayReceipts:
    """Pending relay receipts: token -> observation-derived facts.

    Bounded and TTL'd by construction (a ring of at most
    ``MAX_ENTRIES`` receipts, each expiring after ``TTL_S``), so the
    store is a handful of pending utterances — never a log of what was
    said. Single event loop: no lock needed, same as the TTS egress hub.
    """

    #: A relayed utterance is submitted within seconds; five minutes
    #: covers a slow turn boundary without letting an old utterance
    #: vouch for a later turn.
    TTL_S = 300.0
    #: Small on purpose: the browser redeems the newest receipt; a burst
    #: larger than this is a stuck client, not a queue to serve.
    MAX_ENTRIES = 32

    def __init__(self) -> None:
        self._pending: "OrderedDict[str, RelayReceipt]" = OrderedDict()
        self._now = time.time  # seam for the expiry test
        #: A09 bug 6: the last utterance and when, for the dedupe window.
        self._last_utterance = None

    def reset(self) -> None:
        """Test seam: drop every pending receipt."""
        self._pending.clear()
        self._last_utterance = None

    def size(self) -> int:
        return len(self._pending)

    def is_duplicate(self, text: str, *, window: float = UTTERANCE_DEDUPE_SECONDS) -> bool:
        """Whether this utterance is the one just recorded (A09 bug 6).

        One utterance is one turn. A relay that re-sends, a satellite
        that hears the same phrase twice, or a double-submit produced two
        turns -- two answers, and for a command two executions. Compared
        on NORMALISED text, because the same words re-transcribed differ
        in whitespace and case alone.
        """
        normalised = " ".join(str(text or "").lower().split())
        if not normalised:
            return False
        now = self._now()
        last = getattr(self, "_last_utterance", None)
        self._last_utterance = (normalised, now)
        if last is None:
            return False
        previous, at = last
        return previous == normalised and (now - at) <= window

    def record(self, observation: Any) -> str:
        """Record one relayed observation; return its receipt token.

        Prunes expired entries and the oldest beyond ``MAX_ENTRIES`` on
        every record, so the store never grows with the conversation.
        """
        now = self._now()
        expired = [
            t for t, r in self._pending.items()
            if now - r.recorded_at > self.TTL_S
        ]
        for token in expired:
            self._pending.pop(token, None)
        token = secrets.token_urlsafe(24)
        self._pending[token] = RelayReceipt(
            text=str(getattr(observation, "text", "") or ""),
            speaker_name=str(getattr(observation, "speaker_name", "") or ""),
            speaker_role=str(getattr(observation, "speaker_role", "") or "unknown"),
            verified=_verified_from_observation(observation),
            recorded_at=now,
        )
        while len(self._pending) > self.MAX_ENTRIES:
            self._pending.popitem(last=False)
        return token

    def consume(self, token: Optional[str]) -> Optional[RelayReceipt]:
        """Redeem one receipt token, single-use.

        Returns the recorded receipt, or None when the token is unknown,
        already spent, or expired — the caller treats None as "this
        voice turn is unidentified" and stamps no claim.
        """
        if not token:
            return None
        receipt = self._pending.pop(token, None)
        if receipt is None:
            return None
        if self._now() - receipt.recorded_at > self.TTL_S:
            return None
        return receipt


#: Module singleton, the get_event_bus pattern: the publisher (the relay
#: in app.py) and the consumer (the talk door in routes/agent.py) meet
#: here without either holding the FastAPI app.
_RECEIPTS: Optional[VoiceRelayReceipts] = None


def get_voice_relay_receipts() -> VoiceRelayReceipts:
    global _RECEIPTS
    if _RECEIPTS is None:
        _RECEIPTS = VoiceRelayReceipts()
    return _RECEIPTS


def stamped_voice_fields(
    receipt: Optional[RelayReceipt],
    submitted_text: str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """The voice turn's stamped claim fields, from the receipt only.

    Returns ``(claim_source, speaker_name, speaker_role)`` for
    ``process()``. The wire's voice fields never reach this function —
    the server ignores them in favour of this stamp (the design's C2
    row). The rules, all fail-closed:

    * **No receipt** (unknown/spent/expired token, or none sent): no
      claim, no name, no role — the channel's own "unknown" default
      applies and the ladder reads the turn as UNVERIFIED.
    * **Transcript mismatch**: the receipt is bound to the utterance it
      recorded (``transcribe_before_command``: the transcript IS the
      command text); redeeming it against different words stamps
      nothing — an observed speaker's identity cannot be carried onto
      words they never said.
    * **Verified** (the pipeline matched an enrolled profile): the
      speaker-verification claim, the observation's own name and role.
    * **Name without a match**: a free-text claim — MUTABLE, gates
      nothing — and never a role (a spoken self-identification is not
      a role grant).
    """
    if receipt is None:
        return None, None, None
    if (submitted_text or "").strip() != receipt.text.strip():
        logger.info(
            "relay receipt transcript mismatch: stamped no claim "
            "(receipt_chars=%d submitted_chars=%d)",
            len(receipt.text), len(submitted_text or ""),
        )
        return None, None, None
    if receipt.verified:
        return (
            "voice_speaker_verification",
            receipt.speaker_name or None,
            receipt.speaker_role or None,
        )
    if receipt.speaker_name:
        return ("free_text_name", receipt.speaker_name, None)
    return None, None, None