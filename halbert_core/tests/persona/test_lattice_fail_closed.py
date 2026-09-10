# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-08 Phase A: the lattice fails closed, on one clock, with typed refusals.

Four defects, each a way the permission evaluator answered something
other than "denied" when it could not answer at all:

- **A11-G2 + bug 1** -- ``Scope.from_mapping`` raises on any key it does
  not know, and 24 of the 47 shipped profile rows carry keys it does not
  know (``roots``, ``verbs``, ``re_auth``, ``diff``, ``jobs``, ...). So
  the first ``require()`` after first-run acceptance raised a bare
  ``ValueError`` out of the permission system and crashed the turn,
  rather than producing the typed ``Denied`` the design promises. The
  vocabulary splits: BINDING facts (what ``admits`` actually checks) go
  through ``Scope``; the rest are provenance recorded beside it; a key in
  neither set still raises, because a scope that silently drops a field
  would widen what the check believes it covered.
- **A11 bug 3** -- two clocks. ``require()`` resolved the granted scope
  through an injected ``now`` while ``effective_capability`` folded the
  consent state on wall time, so an injected ``now`` past ``expires_at``
  produced ALLOWED with ``granted_scope=None``: no scope check, and no
  redaction check either.
- **A11 bug 6** -- ``halt=None`` read as "not halted", so a wiring site
  that forgot the argument never observed Stop.
- **A11 bug 7** -- a shard edited to a string principal raised
  ``TypeError`` out of the ledger reader instead of the ``ConsentUnavailable``
  the halt path is written for.
"""

import pytest

from halbert_core.persona.permission.consent import ConsentDecision, Principal
from halbert_core.persona.permission.halt import HaltState
from halbert_core.persona.permission.lease import (
    Denied,
    Scope,
    require,
)


def _granted(capability, **kw):
    """A shipped-shape GRANTED record."""
    from halbert_core.persona.permission.consent import ConsentRecord

    return ConsentRecord(
        capability=capability,
        decision=ConsentDecision.GRANTED,
        ts="2026-01-01T00:00:00+00:00",
        principal=Principal(kind="owner", id="local:501", authn="session",
                            at_machine=True),
        surface="test",
        **kw,
    )


# ---------------------------------------------------------------------------
# A11-G2 + bug 1: the scope vocabulary splits
# ---------------------------------------------------------------------------

def test_every_shipped_profile_row_has_a_readable_scope():
    """The reproduction: 24 of 47 rows used to raise here."""
    import halbert_core.persona.permission.profiles as profiles

    unreadable = []
    for profile in (profiles._RESERVED, profiles._ATTENTIVE, profiles._PRESENT):
        for row in profile.grants:
            try:
                Scope.from_mapping(row.scope)
            except Exception as e:
                unreadable.append((profile.name, row.capability, str(e)))
    assert unreadable == [], unreadable


def test_binding_facts_still_bind():
    scope = Scope.from_mapping({"reach_roots": ["/tmp"], "redaction": "required"})
    assert scope.reach_roots == ("/tmp",)
    assert scope.redaction_required is True


def test_provenance_is_recorded_not_interpreted():
    scope = Scope.from_mapping({"diff": "literal", "reason": True, "backup": True})
    assert scope.provenance["diff"] == "literal"
    # It binds nothing: a descriptive fact is not a grant.
    assert scope.reach_roots == ()
    assert scope.admits(Scope.from_mapping({"reach_roots": ["/etc"]})) is False


def test_a_key_in_neither_vocabulary_still_raises():
    """The parser.py lesson holds: a scope the code cannot read is not a grant."""
    with pytest.raises(ValueError):
        Scope.from_mapping({"totally_new_control": "yes"})


def test_an_unreadable_scope_denies_it_does_not_raise_out_of_require():
    """Whatever fails inside require(), the caller gets a typed Denied."""
    record = _granted("sensor.hardware", scope={"totally_new_control": "yes"})
    with pytest.raises(Denied) as excinfo:
        require(
            "sensor.hardware",
            consent_records=[record],
            halt=HaltState(),
        )
    assert excinfo.value.reason_code == "SCOPE_UNREADABLE"


# ---------------------------------------------------------------------------
# A11 bug 6: halt is required
# ---------------------------------------------------------------------------

def test_a_wiring_site_that_forgets_halt_denies():
    with pytest.raises(Denied) as excinfo:
        require("sensor.hardware")
    assert excinfo.value.decisive_axis == "halt"


def test_effective_capability_without_halt_evidence_denies():
    from halbert_core.persona.permission.effective import effective_capability

    decision = effective_capability("sensor.hardware")
    assert decision.allowed is False
    assert decision.decisive_axis == "halt"


def test_a_live_halt_state_that_is_not_halted_is_accepted():
    """Passing the real state is the wired path and must not deny on this axis."""
    from halbert_core.persona.permission.effective import effective_capability

    decision = effective_capability("sensor.hardware", halt=HaltState())
    assert decision.decisive_axis != "halt"


# ---------------------------------------------------------------------------
# A11 bug 3: one clock
# ---------------------------------------------------------------------------

def test_an_expired_grant_denies_under_the_injected_clock():
    """Reproduced: injected ``now`` past expiry, wall clock before it.

    The scope resolution saw "expired" and left granted_scope None while
    the evaluator folded the consent state on wall time and said GRANTED
    -- so the call was ALLOWED with no scope and no redaction check.
    """
    from halbert_core.persona.permission.ceiling import CapabilityCeiling
    from halbert_core.persona.permission.effective import effective_capability

    record = _granted(
        "sensor.hardware", expires_at="2020-01-01T00:00:00+00:00")
    ceiling = CapabilityCeiling(frozenset({"sensor.hardware"}))

    # Wall time is 2026 in this record's world; the injected clock is
    # 2030, past the 2020 expiry. The evaluator must read the injected
    # one -- the same one require() resolves the granted scope through.
    decision = effective_capability(
        "sensor.hardware",
        ceiling=ceiling,
        consent_records=[record],
        halt=HaltState(),
        now="2030-01-01T00:00:00+00:00",
    )
    assert decision.allowed is False
    # The consent axis is what this test is about; the affordance axis
    # denies first on a bare table, so read the observation rather than
    # the decisive axis.
    consent_axis = next(
        o for o in decision.observations if o.axis == "consent")
    assert consent_axis.affirmative is False
    assert consent_axis.detail == "expired"


def test_a_live_grant_reads_granted_under_the_same_clock():
    """The other direction, so the test above is not passing for free."""
    from halbert_core.persona.permission.ceiling import CapabilityCeiling
    from halbert_core.persona.permission.effective import effective_capability

    record = _granted(
        "sensor.hardware", expires_at="2040-01-01T00:00:00+00:00")
    decision = effective_capability(
        "sensor.hardware",
        ceiling=CapabilityCeiling(frozenset({"sensor.hardware"})),
        consent_records=[record],
        halt=HaltState(),
        now="2030-01-01T00:00:00+00:00",
    )
    consent_axis = next(
        o for o in decision.observations if o.axis == "consent")
    assert consent_axis.affirmative is True


def test_require_and_the_evaluator_read_the_same_clock():
    """The bug was the disagreement, not either reading on its own."""
    from halbert_core.persona.permission.ceiling import CapabilityCeiling

    record = _granted(
        "sensor.hardware", expires_at="2020-01-01T00:00:00+00:00")
    with pytest.raises(Denied) as excinfo:
        require(
            "sensor.hardware",
            ceiling=CapabilityCeiling(frozenset({"sensor.hardware"})),
            consent_records=[record],
            halt=HaltState(),
            now="2030-01-01T00:00:00+00:00",
        )
    # Never ALLOWED-with-no-scope, which is what the split clock produced.
    assert excinfo.value.reason_code != "ALLOWED"


# ---------------------------------------------------------------------------
# A11 bug 7: a malformed shard halts, it does not crash
# ---------------------------------------------------------------------------

def test_a_malformed_consent_row_raises_consent_unavailable():
    from halbert_core.consent.denials import ConsentUnavailable
    from halbert_core.consent.store import record_from_payload

    with pytest.raises(ConsentUnavailable):
        record_from_payload({
            "capability": "sensor.hardware",
            "decision": "granted",
            "ts": "2026-01-01T00:00:00+00:00",
            # A principal edited to a string: the wrong TYPE, not the
            # wrong value, which is the case TypeError covers.
            "principal": "owner",
            "surface": "test",
        })
