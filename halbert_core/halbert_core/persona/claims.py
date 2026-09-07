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


def meets_floor(actual: ClaimStrength, required: ClaimStrength) -> bool:
    return actual >= required


def weakest_claim(claims) -> IdentifierClaim:
    """Combined identity is only as strong as its weakest claim."""
    return min(claims, key=lambda c: c.strength)