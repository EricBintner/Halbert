# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-08 Phase E: a grant resolves to real words, and expires when they change.

- **A11-G4** -- ``is_valid_grant_record`` checks that ``text_shown_sha256``
  is non-empty. Any 64 characters satisfied that, so a grant could carry
  the digest of words nobody ever shipped -- and the whole point of
  recording the digest is that the grant resolves to SPECIFIC wording the
  owner actually saw. The digest has to be one the copy manifest knows.
- **A11-G5** -- when shipped copy WIDENS what a capability means, an old
  grant is consent to the old sentence. It has to fold to ask-again
  rather than silently carrying over to a broader promise.
- **A11-G7 (FD-7)** -- a turn-scoped grant with no live turn bound is
  QUIET: "it is whether anyone asked". The reason code existed and was
  computed by nothing.
- **A12-G2** -- ``meets_floor`` was dead and the claim axis was one
  hard-coded threshold, so an unverified speaker's claim never reached
  the evaluator at all.
"""

import pytest

from halbert_core.persona.claims import ClaimStrength, IdentifierClaim
from halbert_core.persona.permission.consent import (
    ConsentDecision,
    Principal,
    is_valid_grant_record,
)
from halbert_core.persona.permission.halt import HaltState


def _record(capability="sensor.hardware", **kw):
    from halbert_core.persona.permission.consent import ConsentRecord

    kw.setdefault("decision", ConsentDecision.GRANTED)
    return ConsentRecord(
        capability=capability,
        ts="2026-01-01T00:00:00+00:00",
        principal=Principal(kind="owner", id="local:501",
                            authn="os_reauth:touchid", at_machine=True),
        surface="desktop-app/first-run",
        **kw,
    )


# ---------------------------------------------------------------------------
# A11-G4: the digest resolves to shipped wording
# ---------------------------------------------------------------------------

def test_a_grant_whose_digest_is_not_shipped_wording_is_not_a_grant():
    record = _record(text_shown_sha256="f" * 64)
    assert is_valid_grant_record(record) is False


def test_a_grant_carrying_the_shipped_digest_is_valid():
    from halbert_core.consent.copy import digest_for

    record = _record(text_shown_sha256=digest_for("sensor.hardware"))
    assert is_valid_grant_record(record) is True


def test_a_profile_review_digest_is_accepted_too():
    """``accept_profile`` stamps the review-screen digest on every row."""
    from halbert_core.consent.copy import review_digest_for

    record = _record(
        text_shown_sha256=review_digest_for("attentive"),
        via="profile:attentive",
    )
    assert is_valid_grant_record(record) is True


def test_an_empty_digest_is_still_refused():
    assert is_valid_grant_record(_record(text_shown_sha256="")) is False


# ---------------------------------------------------------------------------
# A11-G5: widened copy folds an old grant to ask-again
# ---------------------------------------------------------------------------

def test_a_grant_for_superseded_wording_reads_as_ask_again(monkeypatch):
    """A widening means the owner agreed to a narrower sentence."""
    import halbert_core.consent.copy as copy_mod
    from halbert_core.persona.permission.consent import consent_state

    # A capability whose wording widened from v1 to the current version.
    versions = dict(copy_mod.manifest_data()["sensor.hardware"])
    v1_digest = versions["v1"]
    monkeypatch.setattr(copy_mod, "CURRENT_VERSION", "v2")
    monkeypatch.setattr(
        copy_mod, "WIDENED_VERSIONS", {"sensor.hardware": {"v2": "v1"}})
    monkeypatch.setattr(
        copy_mod, "manifest_data",
        lambda: {"sensor.hardware": {**versions, "v2": "b" * 64}})

    stale = _record(text_shown_sha256=v1_digest)
    assert consent_state([stale], "sensor.hardware") is ConsentDecision.ABSENT


def test_a_grant_for_the_current_wording_still_stands():
    from halbert_core.consent.copy import digest_for
    from halbert_core.persona.permission.consent import consent_state

    record = _record(text_shown_sha256=digest_for("sensor.hardware"))
    assert consent_state([record], "sensor.hardware") is ConsentDecision.GRANTED


def test_copy_widening_is_declared_not_inferred():
    """A copy change is a widening only when the manifest says so:
    inferring it from a diff would make every typo a re-consent."""
    from halbert_core.consent.copy import is_widening

    assert is_widening("sensor.hardware", "v1", "v1") is False


# ---------------------------------------------------------------------------
# A11-G7 (FD-7): QUIET has a producer
# ---------------------------------------------------------------------------

def test_a_turn_scoped_grant_with_no_live_turn_is_quiet():
    from halbert_core.persona.permission.affordance import AffordanceTable
    from halbert_core.persona.permission.ceiling import CapabilityCeiling
    from halbert_core.persona.permission.effective import effective_capability
    from halbert_core.persona.permission.os_grant import (
        OsGrantState, OsGrantTable,
    )

    cap = "auto.speak"
    decision = effective_capability(
        cap,
        ceiling=CapabilityCeiling(frozenset({cap})),
        affordance=AffordanceTable(present=frozenset({cap})),
        os_grants=OsGrantTable({cap: OsGrantState.GRANTED}),
        consent_records=[_record(cap, scope={"turn_scoped": True})],
        halt=HaltState(),
        turn_bound=False,
    )
    assert decision.allowed is False
    assert decision.reason_code == "QUIET"


def test_a_turn_scoped_grant_with_a_live_turn_proceeds():
    from halbert_core.persona.permission.affordance import AffordanceTable
    from halbert_core.persona.permission.ceiling import CapabilityCeiling
    from halbert_core.persona.permission.effective import effective_capability
    from halbert_core.persona.permission.os_grant import (
        OsGrantState, OsGrantTable,
    )

    cap = "auto.speak"
    decision = effective_capability(
        cap,
        ceiling=CapabilityCeiling(frozenset({cap})),
        affordance=AffordanceTable(present=frozenset({cap})),
        os_grants=OsGrantTable({cap: OsGrantState.GRANTED}),
        consent_records=[_record(cap, scope={"turn_scoped": True})],
        halt=HaltState(),
        turn_bound=True,
    )
    assert decision.allowed is True


def test_an_always_on_grant_is_not_quiet_without_a_turn():
    from halbert_core.persona.permission.affordance import AffordanceTable
    from halbert_core.persona.permission.ceiling import CapabilityCeiling
    from halbert_core.persona.permission.effective import effective_capability
    from halbert_core.persona.permission.os_grant import (
        OsGrantState, OsGrantTable,
    )

    cap = "sensor.hardware"
    decision = effective_capability(
        cap,
        ceiling=CapabilityCeiling(frozenset({cap})),
        affordance=AffordanceTable(present=frozenset({cap})),
        os_grants=OsGrantTable({cap: OsGrantState.GRANTED}),
        consent_records=[_record(cap)],
        halt=HaltState(),
        turn_bound=False,
    )
    assert decision.allowed is True


# ---------------------------------------------------------------------------
# A12-G2: the claim axis reaches the evaluator
# ---------------------------------------------------------------------------

def test_a_capability_with_a_claim_floor_denies_an_unverified_speaker():
    from halbert_core.persona.permission.affordance import AffordanceTable
    from halbert_core.persona.permission.ceiling import CapabilityCeiling
    from halbert_core.persona.permission.effective import effective_capability
    from halbert_core.persona.permission.os_grant import (
        OsGrantState, OsGrantTable,
    )

    cap = "reach.privileged"
    decision = effective_capability(
        cap,
        ceiling=CapabilityCeiling(frozenset({cap})),
        affordance=AffordanceTable(present=frozenset({cap})),
        os_grants=OsGrantTable({cap: OsGrantState.GRANTED}),
        consent_records=[_record(cap)],
        halt=HaltState(),
        claim=IdentifierClaim(kind="speaker",
                              strength=ClaimStrength.UNVERIFIED),
    )
    assert decision.allowed is False
    assert decision.decisive_axis == "claim"


def test_the_same_capability_allows_an_asserted_claim():
    from halbert_core.persona.permission.affordance import AffordanceTable
    from halbert_core.persona.permission.ceiling import CapabilityCeiling
    from halbert_core.persona.permission.effective import effective_capability
    from halbert_core.persona.permission.os_grant import (
        OsGrantState, OsGrantTable,
    )

    cap = "reach.privileged"
    decision = effective_capability(
        cap,
        ceiling=CapabilityCeiling(frozenset({cap})),
        affordance=AffordanceTable(present=frozenset({cap})),
        os_grants=OsGrantTable({cap: OsGrantState.GRANTED}),
        consent_records=[_record(cap)],
        halt=HaltState(),
        claim=IdentifierClaim(kind="speaker", strength=ClaimStrength.ASSERTED),
    )
    assert decision.allowed is True


def test_the_claim_floor_table_is_read_not_hard_coded():
    from halbert_core.persona.permission.effective import CLAIM_FLOORS

    assert CLAIM_FLOORS["reach.privileged"] >= ClaimStrength.ASSERTED
    # A capability with no floor takes any claim, including none.
    assert "sensor.hardware" not in CLAIM_FLOORS


def test_meets_floor_has_a_consumer():
    """A12-G2: it was dead vocabulary beside a hard-coded threshold."""
    import inspect

    from halbert_core.persona.permission import effective

    assert "meets_floor" in inspect.getsource(effective)
