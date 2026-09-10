# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Identifier-claim authentication strength.

Lifted from OpenClaw src/channels/message-access/identifier-authentication.ts:
identity CLAIMS carry a strength (verified > asserted > unverified > mutable);
authorization floors are expressed in required strength. Display names never
change strength — resolve_entity_name() is untouched by design (no name tiers).

The ladder gates *directed* actions ("may this person adjust config mid-debate").
It must NOT be chained into the warrant layer's *mandated*-action question
("may the moderator act on this signal") — chaining ladder_strength into
warrant.authorize() would wrongly silence a mandated act whenever the trigger's
identity is weak.
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from enum import IntEnum


class ClaimStrength(IntEnum):
    MUTABLE = 0      # free-text name, anything the requester chose themselves
    UNVERIFIED = 1   # claimed but uncorroborated
    ASSERTED = 2     # issued credential the server validates (dashboard session token)
    VERIFIED = 3     # cryptographic device proof (device cert, mTLS)


@dataclass(frozen=True)
class IdentifierClaim:
    kind: str
    strength: ClaimStrength
    value_sha256: str = ""   # never store raw identifiers in the ladder


CLAIM_SOURCE_STRENGTHS: dict[str, ClaimStrength] = {
    "free_text_name": ClaimStrength.MUTABLE,
    "voice_speaker_verification": ClaimStrength.ASSERTED,
    "dashboard_token": ClaimStrength.ASSERTED,
    "device_cert": ClaimStrength.VERIFIED,
}


def claim_from_source(claim_source: str | None, *, value: str | None = None) -> IdentifierClaim:
    """Derive a speaker's IdentifierClaim from the turn's declared source.

    Packet 04 A2: a voice turn carries ``claim_source`` (typed ingress,
    A1); this maps it through CLAIM_SOURCE_STRENGTHS. A source the ladder
    does not know — or an absent one — fails closed to UNVERIFIED, never
    to a stronger reading. ``value`` is the raw identifier (the speaker
    name): it is hashed and never stored on the claim. Recording only —
    nothing here gates an action; RoleGate consumption is the D-6
    permission-system pass.
    """
    strength = CLAIM_SOURCE_STRENGTHS.get(claim_source or "", ClaimStrength.UNVERIFIED)
    value_sha256 = hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""
    return IdentifierClaim(kind="speaker", strength=strength, value_sha256=value_sha256)


def meets_floor(actual: ClaimStrength, required: ClaimStrength) -> bool:
    return actual >= required


def weakest_claim(claims) -> IdentifierClaim:
    """Combined identity is only as strong as its weakest claim.

    A09 bug 4: total. ``min([])`` raised ``ValueError`` out of the claim
    ladder, and a combined identity with NOTHING in it is the weakest
    identity there is -- MUTABLE, the floor -- not an error for a caller
    to handle. Raising there meant an empty claim set became an
    exception on an authorization path, which fails in whichever
    direction the caller's except clause happens to point.
    """
    claims = list(claims or ())
    if not claims:
        return IdentifierClaim(kind="speaker", strength=ClaimStrength.MUTABLE)
    return min(claims, key=lambda c: c.strength)