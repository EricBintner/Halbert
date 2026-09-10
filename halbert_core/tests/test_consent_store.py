# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The consent ledger — D3-P2's store, its one writer, and its Stop.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.5:

    <data_dir>/consent/consent.log — an append-only
    haloysius.integrity.EventLog ... chain continuous ... persisted head
    pointer ... Files 0600 in a 0700 directory. Plus a derived, 0600,
    flock-guarded projection at <config_dir>/consent-state.json ...

    The log is authoritative; the projection is rebuildable. ... A
    projection that disagrees with the chain is not a warning — it is a
    Stop (§4.1), and the machine says which.

One event per capability per decision; narrowing needs no authority,
widening needs an owner on an authenticated first-party surface with
live OS re-auth; absence means never asked, never allowed.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from halbert_core.consent import denials as denials_mod
from halbert_core.consent.copy import digest_for
from halbert_core.consent import store as store_mod
from halbert_core.consent.store import (
    CONSENT_EVENT_KIND,
    ConsentStore,
    GrantRefused,
    record_from_payload,
    record_to_payload,
)
from halbert_core.persona.permission import (
    NEVER_CEILING_IDS,
    AffordanceTable,
    CapabilityCeiling,
    ConsentDecision,
    ConsentRecord,
    HaltReason,
    HaltState,
    OsGrantState,
    OsGrantTable,
    Principal,
    SurfaceReceipt,
    VOCABULARY,
    consent_state,
    effective_capability,
    takes_consent_records,
)


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture
def dirs(tmp_path):
    return {"data_dir": tmp_path / "data", "config_dir": tmp_path / "config"}


@pytest.fixture
def store(dirs):
    return ConsentStore(
        data_dir=str(dirs["data_dir"]), config_dir=str(dirs["config_dir"])
    )


def _reauth_receipt(surface="desktop-app/first-run") -> SurfaceReceipt:
    """The receipt a real OS re-auth handler will mint (A11-G12).

    R-08 Phase E: ``may_record_grant`` used to read ``Principal.authn``,
    a string the caller writes, so anything that could construct a
    Principal could mint the strongest grant on the machine by typing
    "os_reauth:touchid" into it. It reads the SERVER's own receipt now.
    Nothing in the tree mints one with ``os_reauth=True`` yet -- no OS
    re-authentication exists to mint it from -- so tests build it
    directly, and production correctly cannot record such a grant until
    that handler lands.
    """
    return SurfaceReceipt(
        surface=surface, principal_id="local:501",
        at_machine=True, os_reauth=True, method="test-only",
    )


def _owner(**kw) -> Principal:
    base = dict(
        kind="owner", id="local:501", name="Eric",
        authn="os_reauth:touchid", at_machine=True,
        surface_receipt=_reauth_receipt(),
    )
    base.update(kw)
    return Principal(**base)


def _grant(store, capability="sensor.screen", **kw) -> ConsentRecord:
    base = dict(
        capability=capability,
        decision=ConsentDecision.GRANTED,
        principal=_owner(),
        surface="desktop-app/first-run",
        # A11-G4: the digest has to be one the shipped copy can produce.
        # "9f2c" + zeros satisfied the old non-empty check, which is the
        # gap: the reason the digest is recorded is that the grant
        # resolves to specific wording the owner actually saw.
        text_shown_sha256=digest_for(capability),
        ts="2026-09-06T14:12:03Z",
    )
    base.update(kw)
    return store.record_decision(**base)


# ---------------------------------------------------------------------------
# Serialization — the record round-trips through the log's payload.
# ---------------------------------------------------------------------------


def test_the_record_round_trips_through_its_payload():
    record = ConsentRecord(
        capability="sensor.screen",
        decision=ConsentDecision.GRANTED,
        ts="2026-09-06T14:12:03Z",
        principal=_owner(),
        surface="desktop-app/first-run",
        text_shown_sha256="9f2c" + "0" * 60,
        via="profile:attentive",
        scope={"displays": ["*"], "redaction": "required"},
        channel="macos-pro",
        body="Studio",
        os_grant_at_time="undetermined",
        session_type="aqua",
        other_login_accounts=2,
        build_version="0.9.3",
        build_commit="ce9449f6",
        signing_subject=None,
        expires_at="2027-10-11T00:00:00Z",
        cause="",
    )

    payload = record_to_payload(record)
    # One event per capability per decision — the payload names them all.
    assert payload["capability"] == "sensor.screen"
    assert payload["principal"]["authn"] == "os_reauth:touchid"
    assert payload["scope"] == {"displays": ["*"], "redaction": "required"}

    restored = record_from_payload(payload)
    assert restored == record


def test_payload_is_plain_json():
    """The EventLog shards are JSONL; the payload must be jsonable."""
    payload = record_to_payload(_grant_payload_fixture())
    json.loads(json.dumps(payload))


def _grant_payload_fixture():
    return ConsentRecord(
        capability="sensor.camera",
        decision=ConsentDecision.GRANTED,
        ts="2026-09-06T14:12:03Z",
        principal=_owner(),
        surface="desktop-app/first-run",
        text_shown_sha256="9f2c" + "0" * 60,
    )


# ---------------------------------------------------------------------------
# The one writer.
# ---------------------------------------------------------------------------


def test_a_first_grant_appends_one_event(store):
    record = _grant(store)

    records = store.records()
    assert len(records) == 1
    assert records[0] == record
    assert record.prior is None  # never asked before


def test_the_second_decision_carries_the_prior(store):
    _grant(store)
    denied = store.record_decision(
        capability="sensor.screen",
        decision=ConsentDecision.DENIED,
        principal=_owner(authn="none"),
        surface="desktop-app/settings/permissions",
        ts="2026-09-06T15:00:00Z",
    )

    assert denied.prior is ConsentDecision.GRANTED
    assert store.state_for("sensor.screen") is ConsentDecision.DENIED


def test_a_grant_needs_no_narrowing_authority_but_records_provenance(store):
    record = _grant(store, via="profile:attentive", channel="macos-pro")

    assert record.via == "profile:attentive"
    assert store.state_for("sensor.screen") is ConsentDecision.GRANTED


def test_expiry_folds_at_read_time(store):
    _grant(store, expires_at="2027-10-11T00:00:00Z")

    assert store.state_for("sensor.screen") is ConsentDecision.GRANTED
    assert store.state_for(
        "sensor.screen", now="2027-10-12T00:00:00Z"
    ) is ConsentDecision.EXPIRED


# ---------------------------------------------------------------------------
# The widening-refusal quartet — Gate 4's proof half.
# ---------------------------------------------------------------------------


QUARTET = [
    # (principal kwargs, expected reason code)
    (dict(kind="agent", authn="none", at_machine=True), "not_owner"),
    (dict(kind="peer", authn="none", at_machine=False), "not_owner"),
    (dict(kind="mcp", authn="none", at_machine=False), "not_owner"),
    # The unauthenticated-loopback shape: claims to be the owner, arrives
    # over a wire with a session credential and no OS re-auth. Since
    # A11-G12 the string is irrelevant -- what refuses it is the absence
    # of a server-minted receipt recording one.
    (dict(kind="owner", authn="session", at_machine=True,
          surface_receipt=None), "no_live_os_reauth"),
    # And the forged shape: an authn string that SAYS os_reauth.
    (dict(kind="owner", authn="os_reauth:touchid", at_machine=True,
          surface_receipt=None), "no_live_os_reauth"),
]


@pytest.mark.parametrize("principal_kwargs,reason", QUARTET)
def test_the_widening_quartet_is_refused_with_a_reason_code(
    store, principal_kwargs, reason
):
    with pytest.raises(GrantRefused) as caught:
        store.record_decision(
            capability="sensor.screen",
            decision=ConsentDecision.GRANTED,
            principal=_owner(**principal_kwargs),
            surface="desktop-app/first-run",
            text_shown_sha256="9f2c" + "0" * 60,
        )

    assert caught.value.reason_code == reason
    # A refused widening wrote nothing — no half-record ever lands.
    assert store.records() == []


def test_a_remote_surface_refuses_even_an_owner_with_reauth(store):
    with pytest.raises(GrantRefused) as caught:
        store.record_decision(
            capability="sensor.screen",
            decision=ConsentDecision.GRANTED,
            principal=_owner(),
            surface="mcp",  # not a first-party surface (§3.4)
            text_shown_sha256="9f2c" + "0" * 60,
        )

    assert caught.value.reason_code == "not_first_party_surface"
    assert store.records() == []


def test_an_owner_over_a_wire_is_refused(store):
    with pytest.raises(GrantRefused) as caught:
        store.record_decision(
            capability="sensor.screen",
            decision=ConsentDecision.GRANTED,
            principal=_owner(at_machine=False),  # "arriving over a wire"
            surface="desktop-app/first-run",
            text_shown_sha256="9f2c" + "0" * 60,
        )

    assert caught.value.reason_code == "not_at_machine"


def test_a_grant_without_the_words_shown_is_refused(store):
    """Gate 4: text_shown_sha256 is the field that turns a record into
    evidence. A grant without it is a boolean anyone could have asserted."""
    with pytest.raises(GrantRefused) as caught:
        store.record_decision(
            capability="sensor.screen",
            decision=ConsentDecision.GRANTED,
            principal=_owner(),
            surface="desktop-app/first-run",
            text_shown_sha256="",
        )

    assert caught.value.reason_code == "no_text_shown"


@pytest.mark.parametrize("kind", ["agent", "peer", "mcp", "guest"])
def test_narrowing_by_a_non_owner_is_refused(store, kind):
    """A denial written by the agent would let it narrow what the owner
    granted and then blame the owner — narrowing is owner/os/system only."""
    with pytest.raises(GrantRefused) as caught:
        store.record_decision(
            capability="sensor.screen",
            decision=ConsentDecision.DENIED,
            principal=Principal(kind=kind, authn="none", at_machine=True),
            surface="desktop-app/first-run",
        )

    assert caught.value.reason_code == "unauthorized_narrower"
    assert store.records() == []


@pytest.mark.parametrize("kind", ["owner", "os", "system"])
def test_narrowing_by_owner_os_and_system_writes(store, kind):
    """Narrowing needs no authority (§1.5) — os writes the revocations it
    detected, system writes halt/expiry/new-capability defaults."""
    _grant(store)
    store.record_decision(
        capability="sensor.screen",
        decision=ConsentDecision.REVOKED,
        principal=Principal(kind=kind, authn="none"),
        surface="desktop-app/settings/permissions",
    )

    assert store.state_for("sensor.screen") is ConsentDecision.REVOKED


def test_absent_is_not_an_event(store):
    """Absence is the absence of a record — writing an ABSENT row would
    turn "never asked" into a recorded answer."""
    with pytest.raises(GrantRefused) as caught:
        store.record_decision(
            capability="sensor.screen",
            decision=ConsentDecision.ABSENT,
            principal=_owner(),
            surface="desktop-app/first-run",
        )

    assert caught.value.reason_code == "absent_is_not_an_event"
    assert store.records() == []


def test_a_consent_record_for_a_non_consenting_capability_is_refused(store):
    with pytest.raises(GrantRefused) as caught:
        store.record_decision(
            capability="sys.local_llm",  # affordance-only, no consent surface
            decision=ConsentDecision.DENIED,
            principal=_owner(),
            surface="desktop-app/settings/permissions",
        )

    assert caught.value.reason_code == "not_a_consent_capability"


def test_a_consent_record_for_an_unknown_id_is_refused(store):
    with pytest.raises(GrantRefused) as caught:
        store.record_decision(
            capability="sensor.mind_reader",
            decision=ConsentDecision.DENIED,
            principal=_owner(),
            surface="desktop-app/settings/permissions",
        )

    assert caught.value.reason_code == "not_a_consent_capability"


def test_a_grant_for_the_declared_absent_capability_is_refused(store):
    """egress.telemetry exists in the vocabulary so its absence is provable
    by test; the ledger must never carry a grant for it."""
    with pytest.raises(GrantRefused) as caught:
        store.record_decision(
            capability="egress.telemetry",
            decision=ConsentDecision.GRANTED,
            principal=_owner(),
            surface="desktop-app/first-run",
            text_shown_sha256="9f2c" + "0" * 60,
        )

    assert caught.value.reason_code == "declared_absent_capability"
    # Narrowing it is harmless and allowed (it is already absent).
    store.record_decision(
        capability="egress.telemetry",
        decision=ConsentDecision.DENIED,
        principal=_owner(),
        surface="desktop-app/settings/permissions",
    )


# ---------------------------------------------------------------------------
# The empty ledger — the fail-closed boot.
# ---------------------------------------------------------------------------


def test_an_empty_ledger_refuses_every_consenting_capability(store):
    """The D3-P2 verification gate: boot with an empty ledger and every
    sensor/reach/egress/auto call refuses. Every axis but consent is
    wired affirmative — consent is the only reason for the refusal.

    R-08 Phase A (A11 bug 6): "every axis but consent wired affirmative"
    now has to include halt. Omitting it used to read as "not halted";
    it reads as no halt evidence and denies HALTED, which would make
    every row here refuse for the wrong reason.
    """
    consenting = sorted(
        cap for cap in VOCABULARY
        if takes_consent_records(cap) and cap not in NEVER_CEILING_IDS
    )
    assert len(consenting) >= 30  # the vocabulary's four consenting kinds

    # The declared-absent id is a consenting kind but no ceiling may ever
    # carry it (P1's structural bar) — consent never gets a say there.
    assert "egress.telemetry" not in consenting

    for capability in consenting:
        decision = effective_capability(
            capability,
            ceiling=CapabilityCeiling(frozenset({capability})),
            affordance=AffordanceTable(present=frozenset({capability})),
            os_grants=OsGrantTable({capability: OsGrantState.GRANTED}),
            consent_records=store.records(),
            halt=HaltState(),
        )
        assert decision.allowed is False, capability
        assert decision.reason_code == "NOT_GRANTED", capability
        assert decision.decisive_axis == "consent", capability


def test_a_fresh_store_with_no_directory_reads_as_never_asked(dirs):
    """No consent directory at all — the first-boot state, not an error:
    absence means never asked, never allowed."""
    store = ConsentStore(
        data_dir=str(dirs["data_dir"]), config_dir=str(dirs["config_dir"])
    )
    assert store.records() == []
    assert store.state_for("sensor.screen") is ConsentDecision.ABSENT


def test_consent_state_reads_through_the_store(store):
    _grant(store)
    assert consent_state(store.records(), "sensor.screen") is ConsentDecision.GRANTED
    assert store.state_for("sensor.camera") is ConsentDecision.ABSENT


# ---------------------------------------------------------------------------
# File shape — 0600 in a 0700 dir.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_the_ledger_is_0600_in_a_0700_dir(store, dirs):
    _grant(store)

    consent_dir = dirs["data_dir"] / "consent"
    assert stat.S_IMODE(consent_dir.stat().st_mode) & 0o777 == 0o700
    shards = [p for p in consent_dir.iterdir() if p.suffix == ".jsonl"]
    assert shards
    for shard in shards:
        assert stat.S_IMODE(shard.stat().st_mode) & 0o777 == 0o600
    head = consent_dir / "head.json"
    assert stat.S_IMODE(head.stat().st_mode) & 0o777 == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_the_projection_is_0600(store, dirs):
    _grant(store)

    projection = dirs["config_dir"] / "consent-state.json"
    assert stat.S_IMODE(projection.stat().st_mode) & 0o777 == 0o600


# ---------------------------------------------------------------------------
# The projection: derived, rebuildable, and a Stop when it lies.
# ---------------------------------------------------------------------------


def test_record_decision_keeps_the_projection_in_step(store, dirs):
    _grant(store)
    _grant(store, capability="sensor.camera")

    projection = json.loads(
        (dirs["config_dir"] / "consent-state.json").read_text()
    )
    assert projection["state"]["sensor.screen"]["decision"] == "granted"
    assert projection["state"]["sensor.camera"]["decision"] == "granted"


def test_rebuild_reprojects_from_the_authoritative_log(store, dirs):
    _grant(store)
    projection_path = dirs["config_dir"] / "consent-state.json"
    projection_path.write_text("{}")  # a clobbered projection

    result = store.rebuild()

    assert result["records"] == 1
    assert (
        json.loads(projection_path.read_text())["state"]["sensor.screen"]["decision"]
        == "granted"
    )
    assert store.projection_status() == "agrees"


def test_a_disagreeing_projection_is_a_stop_not_a_warning(store):
    _grant(store)
    projection_path = store.projection_path
    tampered = json.loads(projection_path.read_text())
    tampered["state"]["sensor.screen"] = {
        "decision": "denied",
        "ts": tampered["state"]["sensor.screen"]["ts"],
        "expires_at": "",
    }
    projection_path.write_text(json.dumps(tampered))

    halt = HaltState()
    with pytest.raises(denials_mod.ConsentUnavailable) as caught:
        store.check_or_halt(halt)

    assert caught.value.halt_reason == HaltReason.CONSENT_CHAIN_BROKEN
    assert halt.is_halted()
    assert halt.reason_code == HaltReason.CONSENT_CHAIN_BROKEN


def test_a_disagreement_detected_by_hand_backed_by_head(store, dirs):
    _grant(store)
    projection_path = dirs["config_dir"] / "consent-state.json"
    tampered = json.loads(projection_path.read_text())
    tampered["head_seq"] = 99
    projection_path.write_text(json.dumps(tampered))

    assert store.projection_status() == "disagrees"


def test_a_missing_projection_is_rebuildable_not_a_stop(store):
    _grant(store)
    store.projection_path.unlink()

    halt = HaltState()
    store.check_or_halt(halt)  # rebuilds; no halt, no raise

    assert not halt.is_halted()
    assert store.projection_status() == "agrees"


def test_a_clean_ledger_passes_the_boot_check(store):
    _grant(store)
    halt = HaltState()

    store.check_or_halt(halt)

    assert not halt.is_halted()


# ---------------------------------------------------------------------------
# The chain — tamper, truncate, and the broken install.
# ---------------------------------------------------------------------------


def _shard_path(store) -> Path:
    consent_dir = Path(store.data_dir) / "consent"
    return sorted(consent_dir.glob("*.jsonl"))[0]


def test_an_in_place_edit_is_detected_and_stops_the_machine(store):
    _grant(store)
    shard = _shard_path(store)
    text = shard.read_text()
    shard.write_text(text.replace('"capability": "sensor.screen"', '"capability": "sensor.camera"'))

    halt = HaltState()
    with pytest.raises(denials_mod.ConsentUnavailable) as caught:
        store.check_or_halt(halt)

    assert caught.value.halt_reason == HaltReason.CONSENT_CHAIN_BROKEN
    assert halt.reason_code == HaltReason.CONSENT_CHAIN_BROKEN
    assert store.verify().ok is False


def test_a_truncated_log_is_detected(store):
    _grant(store)
    _grant(store, capability="sensor.camera")
    shard = _shard_path(store)
    lines = shard.read_text().splitlines()
    shard.write_text("\n".join(lines[:-1]) + "\n")

    assert store.verify().ok is False


def test_a_deleted_shard_is_detected(store):
    _grant(store)
    _shard_path(store).unlink()

    assert store.verify().ok is False


def test_rebuild_refuses_to_launder_a_tampered_log(store):
    _grant(store)
    shard = _shard_path(store)
    shard.write_text(shard.read_text().replace("granted", "denied"))

    with pytest.raises(denials_mod.ConsentUnavailable):
        store.rebuild()


def test_a_missing_integrity_primitive_halts_the_machine(store, monkeypatch):
    """§1.5's ruling: haloysius.integrity absent is a broken install — the
    machine boots halted and says so. No fallback chain, no warning."""
    monkeypatch.setattr(store_mod, "EventLog", None)
    halt = HaltState()

    with pytest.raises(denials_mod.ConsentUnavailable) as caught:
        store.check_or_halt(halt)

    assert caught.value.halt_reason == HaltReason.INTEGRITY_MISSING
    assert halt.reason_code == HaltReason.INTEGRITY_MISSING


def test_the_writer_refuses_to_run_without_integrity(store, monkeypatch):
    monkeypatch.setattr(store_mod, "EventLog", None)

    with pytest.raises(denials_mod.ConsentUnavailable):
        _grant(store)


def test_a_failed_ledger_write_leaves_no_grant(store, monkeypatch, dirs):
    """Fail-closed write: an action that cannot be recorded is not
    performed — the record either lands whole or does not land.

    R-08 Phase D (A11 bug 5): the append and the projection write became
    ONE critical section, so ``_append_locked`` -- which patched only the
    append -- is gone. The seam is the log's own append, which is what
    actually fails when the disk does.
    """
    def broken_append(self, kind, payload):
        raise OSError("disk full")

    log = store._log()
    monkeypatch.setattr(type(log), "append", broken_append)
    monkeypatch.setattr(store, "_log", lambda: log)

    with pytest.raises(OSError):
        _grant(store)

    assert store.records() == []
    # And the projection was never written for the failed event.
    assert not (dirs["config_dir"] / "consent-state.json").exists()


def test_every_event_in_the_log_is_a_consent_event(store):
    _grant(store)
    log = store._log()

    for event in log.read_all():
        assert event.kind == CONSENT_EVENT_KIND
        assert event.payload["capability"] == "sensor.screen"