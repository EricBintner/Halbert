# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The consent record — axis 4 of five: did the owner say yes, when, shown what?

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.5: one event per capability
per decision, never a bare boolean; absence of a record means *never asked*,
not allowed; and the asymmetry — narrowing needs no authority, widening
needs an owner on an authenticated first-party surface with live OS re-auth.
"""
from __future__ import annotations

import dataclasses

import pytest

from halbert_core.persona.permission.consent import (
    ABSENT_DECISION,
    ConsentDecision,
    ConsentRecord,
    FIRST_PARTY_SURFACES,
    Principal,
    consent_state,
    is_affirmative_consent,
    is_valid_grant_record,
    latest_for,
    may_record_grant,
)


def _owner(**kw) -> Principal:
    base = dict(
        kind="owner", id="local:501", name="Eric",
        authn="os_reauth:touchid", at_machine=True,
    )
    base.update(kw)
    return Principal(**base)


def _record(capability="sensor.screen", decision=ConsentDecision.GRANTED,
            principal=None, surface="desktop-app/first-run", **kw) -> ConsentRecord:
    base = dict(
        capability=capability, decision=decision, ts="2026-09-06T14:12:03Z",
        principal=principal or _owner(), surface=surface,
        text_shown_sha256="9f2c" + "0" * 60, via="profile:attentive",
    )
    base.update(kw)
    return ConsentRecord(**base)


def test_decision_enum_covers_the_designs_outcomes():
    assert {d.value for d in ConsentDecision} == {
        "granted", "denied", "revoked", "expired", "absent",
    }


def test_absence_means_never_asked_not_allowed():
    assert consent_state([], "sensor.screen") is ABSENT_DECISION
    assert is_affirmative_consent(ABSENT_DECISION) is False


def test_the_record_is_frozen():
    rec = _record()
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.decision = ConsentDecision.DENIED


def test_latest_record_for_a_capability_wins():
    records = [
        _record(decision=ConsentDecision.GRANTED, ts="2026-09-06T14:12:03Z"),
        _record(decision=ConsentDecision.DENIED, ts="2026-09-06T15:00:00Z",
                principal=_owner(authn="none")),
    ]
    assert consent_state(records, "sensor.screen") is ConsentDecision.DENIED
    assert latest_for(records, "sensor.screen").ts == "2026-09-06T15:00:00Z"


def test_records_for_other_capabilities_do_not_leak():
    records = [_record(capability="sensor.camera")]
    assert consent_state(records, "sensor.screen") is ABSENT_DECISION
    assert latest_for(records, "sensor.mic.push_to_talk") is None


def test_grant_expiry_reads_as_expired():
    records = [_record(expires_at="2027-10-11T00:00:00Z")]  # the 400-day voiceprint TTL shape
    assert consent_state(records, "sensor.screen", now="2026-09-06T14:12:03Z") is ConsentDecision.GRANTED
    assert consent_state(records, "sensor.screen", now="2027-10-12T00:00:00Z") is ConsentDecision.EXPIRED


def test_only_granted_is_affirmative():
    for decision in (
        ConsentDecision.DENIED, ConsentDecision.REVOKED,
        ConsentDecision.EXPIRED, ConsentDecision.ABSENT,
    ):
        assert is_affirmative_consent(decision) is False
    assert is_affirmative_consent(ConsentDecision.GRANTED) is True


def test_widening_needs_owner_first_party_surface_and_live_reauth():
    # the full, legitimate widening path
    assert may_record_grant(_owner(), "desktop-app/first-run") is True
    assert "desktop-app/first-run" in FIRST_PARTY_SURFACES

    # the agent is never an owner — it can only ask
    assert may_record_grant(
        Principal(kind="agent", id="", name="", authn="", at_machine=True),
        "desktop-app/first-run",
    ) is False

    # an owner on a remote surface is not a widening path
    assert may_record_grant(_owner(), "mcp") is False
    assert may_record_grant(_owner(), "ha_component") is False

    # a session credential is not a live OS re-auth
    assert may_record_grant(_owner(authn="session"), "desktop-app/first-run") is False

    # and not from another machine
    assert may_record_grant(_owner(at_machine=False), "desktop-app/first-run") is False

    # the os and the system may narrow, never widen
    assert may_record_grant(
        Principal(kind="os", id="", name="", authn="", at_machine=True),
        "desktop-app/first-run",
    ) is False


def test_narrowing_needs_no_authority():
    # a revocation the OS detected, and a system expiry, are both legal records
    os_revocation = _record(
        decision=ConsentDecision.REVOKED,
        principal=Principal(kind="os", id="", name="", authn="", at_machine=True),
        cause="os_revoked",
    )
    assert os_revocation.cause == "os_revoked"
    system_default = _record(
        decision=ConsentDecision.DENIED,
        principal=Principal(kind="system", id="", name="", authn="", at_machine=True),
        cause="new_capability_default_closed",
    )
    assert consent_state([system_default], "sensor.screen") is ConsentDecision.DENIED


def test_a_grant_record_is_not_valid_without_the_words_shown():
    # text_shown_sha256 is the field that turns a record into evidence
    assert is_valid_grant_record(_record()) is True
    assert is_valid_grant_record(_record(text_shown_sha256="")) is False
    # and not for any other decision — only grants carry the evidentiary bar
    assert is_valid_grant_record(_record(decision=ConsentDecision.DENIED)) is False


def test_prior_provenance_is_carried():
    rec = _record(prior=ConsentDecision.ABSENT)
    assert rec.prior is ConsentDecision.ABSENT
    assert rec.via == "profile:attentive"
    assert rec.policy_version == "consent-schema/1"