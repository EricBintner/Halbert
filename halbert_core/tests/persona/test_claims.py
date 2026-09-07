# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
from halbert_core.persona.claims import (
    ClaimStrength, meets_floor, weakest_claim, IdentifierClaim,
)

def test_strength_order():
    assert ClaimStrength.MUTABLE < ClaimStrength.UNVERIFIED < ClaimStrength.ASSERTED < ClaimStrength.VERIFIED

def test_floor_gating():
    assert meets_floor(ClaimStrength.VERIFIED, ClaimStrength.ASSERTED)
    assert meets_floor(ClaimStrength.ASSERTED, ClaimStrength.ASSERTED)
    assert not meets_floor(ClaimStrength.MUTABLE, ClaimStrength.ASSERTED)

def test_weakest_claim_combines_downward():
    # a session claiming both a dashboard token and a free-text name is as weak as the free text
    combined = weakest_claim([
        IdentifierClaim(kind="token", strength=ClaimStrength.ASSERTED),
        IdentifierClaim(kind="display_name", strength=ClaimStrength.MUTABLE),
    ])
    assert combined.strength is ClaimStrength.MUTABLE

def test_documented_strength_map_is_complete():
    # executor note: extend this table when a new auth surface is added; the test
    # forces every new ClaimStrength source to be classified deliberately
    from halbert_core.persona.claims import CLAIM_SOURCE_STRENGTHS
    for source in ("dashboard_token", "voice_speaker_verification", "free_text_name", "device_cert"):
        assert source in CLAIM_SOURCE_STRENGTHS