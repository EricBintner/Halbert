# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-02: who is admitted, and on whose word.

- **A12 bug 4** (fix-first row 27) -- ``_local_admin_gate`` fronts eleven
  of fifteen guest routes, camera included, and the loopback predicate
  accepted the HOSTNAME STRINGS ``'localhost'`` and ``'testclient'``. A
  request whose Host resolves to either passes without an IP check ever
  running. Tests monkeypatch the predicate; production reads addresses.
- **A12 bug 5 + bug 6** (row 28) -- ``persona_id`` was interpolated into
  a sibling home's URL PATH, so a remote home's own listing could supply
  an id containing ``/``, ``?`` or ``#`` and the bearer-authorised
  request went somewhere else entirely; and a peer whose ``node_id`` is
  ``home:<netloc>`` could free or withdraw another home's session,
  because the ``home:`` namespace was never fenced from operator-chosen
  node ids.
- **A09 bug 4** -- ``weakest_claim([])`` raised ``ValueError`` out of the
  claim ladder. A combined identity with nothing in it is the WEAKEST
  identity there is, not an error.
- **A12-G1** -- the gate walk did not stop at the first BLOCK, so a later
  gate could overwrite the decisive one and a denial named the wrong
  reason.
- **A12-G4** -- SKIP and OBSERVE were defined in the effect vocabulary
  and dispatched nowhere.
"""

import pytest

from halbert_core.persona.admission import (
    ADMISSION_DISPATCH,
    ADMISSION_DROP,
    ADMISSION_OBSERVE,
    ADMISSION_SKIP,
    Gate,
    GateEffect,
    decide_ingress,
)
from halbert_core.persona.claims import ClaimStrength, IdentifierClaim, weakest_claim


def _gate(gid, effect, reason="ok"):
    return Gate(
        id=gid, phase="test", effect=effect,
        allowed=effect in (GateEffect.ALLOW, GateEffect.OBSERVE),
        reason_code=reason,
    )


# ---------------------------------------------------------------------------
# A12-G1: the first BLOCK wins and the walk stops
# ---------------------------------------------------------------------------

def test_the_first_block_is_the_decisive_gate():
    decision = decide_ingress([
        _gate("a", GateEffect.ALLOW),
        _gate("b", GateEffect.BLOCK, "first_reason"),
        _gate("c", GateEffect.BLOCK, "second_reason"),
    ])
    assert decision.admission == ADMISSION_DROP
    assert decision.decisive_gate == "b"
    assert decision.reason_code == "first_reason"


def test_an_all_allow_walk_dispatches():
    decision = decide_ingress([_gate("a", GateEffect.ALLOW)])
    assert decision.admission == ADMISSION_DISPATCH


def test_an_empty_gate_list_drops():
    assert decide_ingress([]).admission == ADMISSION_DROP


# ---------------------------------------------------------------------------
# A12-G4: SKIP and OBSERVE dispatch as advertised
# ---------------------------------------------------------------------------

def test_a_skip_gate_produces_a_skip_admission():
    decision = decide_ingress([
        _gate("a", GateEffect.ALLOW),
        _gate("b", GateEffect.SKIP, "quiet_hours"),
    ])
    assert decision.admission == ADMISSION_SKIP
    assert decision.decisive_gate == "b"


def test_an_observe_gate_produces_an_observe_admission():
    decision = decide_ingress([
        _gate("a", GateEffect.ALLOW),
        _gate("b", GateEffect.OBSERVE, "shadow_mode"),
    ])
    assert decision.admission == ADMISSION_OBSERVE


def test_a_block_still_beats_a_skip():
    """A refusal is louder than a pass-over, whatever the order."""
    decision = decide_ingress([
        _gate("a", GateEffect.SKIP, "quiet_hours"),
        _gate("b", GateEffect.BLOCK, "not_local_admin"),
    ])
    assert decision.admission == ADMISSION_DROP
    assert decision.decisive_gate == "b"


# ---------------------------------------------------------------------------
# A09 bug 4: weakest_claim is total
# ---------------------------------------------------------------------------

def test_an_empty_claim_set_is_the_weakest_claim():
    claim = weakest_claim([])
    assert claim.strength is ClaimStrength.MUTABLE


def test_the_weakest_of_several_wins():
    claim = weakest_claim([
        IdentifierClaim(kind="speaker", strength=ClaimStrength.VERIFIED),
        IdentifierClaim(kind="speaker", strength=ClaimStrength.UNVERIFIED),
    ])
    assert claim.strength is ClaimStrength.UNVERIFIED


# ---------------------------------------------------------------------------
# A12 bug 4: loopback by IP, never by hostname string
# ---------------------------------------------------------------------------

def test_a_testclient_host_is_not_local():
    from halbert_core.federation.peer_middleware import _is_loopback_host

    assert _is_loopback_host("testclient") is False


def test_a_localhost_string_is_not_local():
    """It is not an address, and a name resolves to whatever DNS says."""
    from halbert_core.federation.peer_middleware import _is_loopback_host

    assert _is_loopback_host("localhost") is False


def test_a_loopback_address_is_local():
    from halbert_core.federation.peer_middleware import _is_loopback_host

    assert _is_loopback_host("127.0.0.1") is True
    assert _is_loopback_host("::1") is True


def test_a_routable_address_is_not_local():
    from halbert_core.federation.peer_middleware import _is_loopback_host

    assert _is_loopback_host("10.0.0.5") is False


# ---------------------------------------------------------------------------
# A12 bug 5: a persona id cannot steer the request
# ---------------------------------------------------------------------------

def test_a_persona_id_with_separators_is_refused_at_intake():
    from halbert_core.persona.sibling import validate_persona_id

    for bad in ("a/../b", "x?y", "p#frag", "with space", ""):
        with pytest.raises(ValueError):
            validate_persona_id(bad)


def test_an_ordinary_persona_id_passes():
    from halbert_core.persona.sibling import validate_persona_id

    assert validate_persona_id("guest-42") == "guest-42"


def test_the_url_path_quotes_the_id():
    from halbert_core.persona.sibling import quote_persona_id

    assert "/" not in quote_persona_id("a/b")
    assert quote_persona_id("a b") == "a%20b"


# ---------------------------------------------------------------------------
# A12 bug 6: the home: namespace is reserved
# ---------------------------------------------------------------------------

def test_a_peer_cannot_take_a_home_node_id():
    from halbert_core.federation.peers_config import validate_node_id

    with pytest.raises(ValueError):
        validate_node_id("home:example.test")


def test_an_ordinary_node_id_is_accepted():
    from halbert_core.federation.peers_config import validate_node_id

    assert validate_node_id("studio-mac") == "studio-mac"


def test_the_reserved_prefix_is_case_insensitive():
    from halbert_core.federation.peers_config import validate_node_id

    with pytest.raises(ValueError):
        validate_node_id("HOME:example.test")


# ---------------------------------------------------------------------------
# A09 bugs 5 and 6: voice provenance
# ---------------------------------------------------------------------------

def test_a_speaker_id_with_no_profile_is_not_verified():
    """Fix-first row 29: a matcher hit whose profile lookup fails used to
    be stamped ``claim_source='voice_speaker_verification'`` -- a verified
    claim with no subject."""
    from types import SimpleNamespace

    from halbert_core.dashboard.voice_relay import _verified_from_observation

    matched_no_profile = SimpleNamespace(
        speaker_id="spk-1", speaker_name="", speaker_role="unknown")
    assert _verified_from_observation(matched_no_profile) is False


def test_a_matched_speaker_with_a_profile_is_verified():
    from types import SimpleNamespace

    from halbert_core.dashboard.voice_relay import _verified_from_observation

    assert _verified_from_observation(SimpleNamespace(
        speaker_id="spk-1", speaker_name="Sam", speaker_role="admin")) is True


def test_the_same_utterance_twice_is_one_turn():
    from halbert_core.dashboard.voice_relay import VoiceRelayReceipts

    receipts = VoiceRelayReceipts()
    assert receipts.is_duplicate("turn on the kitchen light") is False
    assert receipts.is_duplicate("turn on the kitchen light") is True


def test_whitespace_and_case_do_not_defeat_the_dedupe():
    from halbert_core.dashboard.voice_relay import VoiceRelayReceipts

    receipts = VoiceRelayReceipts()
    receipts.is_duplicate("Turn on the light")
    assert receipts.is_duplicate("turn  on   the light") is True


def test_a_different_utterance_is_not_a_duplicate():
    from halbert_core.dashboard.voice_relay import VoiceRelayReceipts

    receipts = VoiceRelayReceipts()
    receipts.is_duplicate("turn on the light")
    assert receipts.is_duplicate("turn off the light") is False


def test_the_same_utterance_after_the_window_is_a_new_turn():
    from halbert_core.dashboard.voice_relay import VoiceRelayReceipts

    receipts = VoiceRelayReceipts()
    clock = {"t": 1000.0}
    receipts._now = lambda: clock["t"]
    receipts.is_duplicate("what time is it")
    clock["t"] += 60
    assert receipts.is_duplicate("what time is it") is False
