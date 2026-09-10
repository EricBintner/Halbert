# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-08 Phase C: a lease ends when its permission does.

- **A11-G3** -- narrowing consent reached the ledger and nothing else. A
  camera lease opened under a grant the owner then revoked kept running:
  the record said DENIED and the capture continued, because no open lease
  was ever told. "Failing the next call is not enough; the loop must end"
  was already the lease's own rule -- it just had no trigger.
- **A11-G8** -- ``max_session_lease`` is written on the Present profile's
  ``sensor.screen.continuous`` row and read by nothing. A lease held for
  a day was as open as one held for a minute.
- **A11-G10** -- ``sensor.voiceprint`` is a biometric with a mandatory
  400-day TTL in the design; a grant recorded without one lived forever.
- **A11-G11** -- ``retain(cleanup)``: a capture that must be deleted when
  the lease ends had nowhere to say so.
- **A11 bug 4** -- ``__enter__`` calls ``check()``, and a lease revoked
  between mint and ``with`` raises there. The lease was already
  registered, so the indicator kept showing an open lease nothing would
  ever close.
"""

import threading

import pytest

from halbert_core.persona.permission.affordance import AffordanceTable
from halbert_core.persona.permission.ceiling import CapabilityCeiling
from halbert_core.persona.permission.consent import ConsentDecision, Principal
from halbert_core.persona.permission.halt import HaltState
from halbert_core.persona.permission.lease import (
    Denied,
    LeaseRegistry,
    require,
)
from halbert_core.persona.permission.os_grant import OsGrantState, OsGrantTable

CAP = "sensor.screen"


def _owner():
    return Principal(kind="owner", id="local:501", authn="os_reauth:touchid",
                     at_machine=True)


def _record(capability=CAP, decision=ConsentDecision.GRANTED, **kw):
    from halbert_core.persona.permission.consent import ConsentRecord

    return ConsentRecord(
        capability=capability,
        decision=decision,
        ts="2026-01-01T00:00:00+00:00",
        principal=_owner(),
        surface="test",
        **kw,
    )


def _open(registry=None, **kw):
    capability = kw.pop("capability", CAP)
    records = kw.pop("consent_records", [_record(capability)])
    return require(
        capability,
        ceiling=CapabilityCeiling(frozenset({capability})),
        affordance=AffordanceTable(present=frozenset({capability})),
        os_grants=OsGrantTable({capability: OsGrantState.GRANTED}),
        consent_records=records,
        halt=HaltState(),
        registry=registry,
        **kw,
    )


# ---------------------------------------------------------------------------
# A11-G3: narrowing reaches the open leases
# ---------------------------------------------------------------------------

def test_narrowing_a_capability_revokes_its_open_leases():
    registry = LeaseRegistry()
    lease = _open(registry)
    assert lease in registry

    revoked = registry.revoke_capability(
        CAP, "NOT_GRANTED", by="owner", surface="settings")

    assert revoked == 1
    assert lease.revoked is True
    with pytest.raises(Denied):
        lease.check()


def test_narrowing_leaves_other_capabilities_alone():
    registry = LeaseRegistry()
    screen = _open(registry)
    mic = _open(registry, capability="sensor.mic.push_to_talk")

    registry.revoke_capability(CAP, "NOT_GRANTED")

    assert screen.revoked is True
    assert mic.revoked is False
    mic.close()


def test_a_revoked_lease_trips_its_stop_event():
    """The loop must END, not just fail its next call."""
    registry = LeaseRegistry()
    event = threading.Event()
    _open(registry, stop_event=event)
    registry.revoke_capability(CAP, "NOT_GRANTED")
    assert event.is_set()


def test_the_store_notifies_the_registry_when_a_grant_narrows():
    """The trigger A11-G3 was missing: recording a narrowing calls it."""
    from halbert_core.persona.permission import lease as lease_mod

    seen = []
    registry = LeaseRegistry()
    lease = _open(registry)
    lease_mod.set_revocation_registry(registry)
    try:
        lease_mod.notify_consent_narrowed(CAP, reason_code="NOT_GRANTED")
    finally:
        lease_mod.set_revocation_registry(None)
    assert lease.revoked is True


# ---------------------------------------------------------------------------
# A11-G8 / A11-G10: a lease expires, and a biometric grant must
# ---------------------------------------------------------------------------

def test_a_lease_expires_at_the_grants_max_session_lease():
    clock = {"t": 1000.0}
    lease = _open(
        capability="sensor.screen.continuous",
        consent_records=[_record(
            "sensor.screen.continuous",
            scope={"max_session_lease": "PT30M"},
        )],
    )
    lease._monotonic = lambda: clock["t"]
    lease._opened_monotonic = clock["t"]
    lease.check()                    # still inside the window
    clock["t"] += 30 * 60 + 1
    with pytest.raises(Denied) as excinfo:
        lease.check()
    assert excinfo.value.reason_code == "NOT_GRANTED"
    assert lease.revoked is True


def test_a_lease_without_a_max_session_lease_does_not_expire():
    clock = {"t": 1000.0}
    lease = _open()
    lease._monotonic = lambda: clock["t"]
    lease._opened_monotonic = clock["t"]
    clock["t"] += 10 * 3600
    lease.check()
    lease.close()


def test_a_voiceprint_grant_without_a_ttl_is_refused():
    """A11-G10: a biometric grant has a mandatory TTL in the design."""
    from halbert_core.persona.permission.consent import (
        MANDATORY_TTL_DAYS,
        mandatory_ttl_days,
    )

    assert mandatory_ttl_days("sensor.voiceprint") == 400
    assert "sensor.voiceprint" in MANDATORY_TTL_DAYS

    with pytest.raises(Denied) as excinfo:
        _open(
            capability="sensor.voiceprint",
            consent_records=[_record("sensor.voiceprint")],   # no expires_at
        )
    assert excinfo.value.reason_code == "NOT_GRANTED"


def test_a_voiceprint_grant_with_a_ttl_opens():
    lease = _open(
        capability="sensor.voiceprint",
        consent_records=[_record(
            "sensor.voiceprint", expires_at="2040-01-01T00:00:00+00:00")],
    )
    lease.close()


# ---------------------------------------------------------------------------
# A11-G11: retain(cleanup)
# ---------------------------------------------------------------------------

def test_retained_cleanup_runs_when_the_lease_closes():
    ran = []
    lease = _open()
    lease.retain(lambda: ran.append("deleted"))
    lease.close()
    assert ran == ["deleted"]


def test_retained_cleanup_runs_on_revocation_too():
    ran = []
    registry = LeaseRegistry()
    lease = _open(registry)
    lease.retain(lambda: ran.append("deleted"))
    registry.revoke_capability(CAP, "NOT_GRANTED")
    lease.close()
    assert ran == ["deleted"]


def test_a_failing_cleanup_does_not_stop_the_others():
    ran = []

    def _boom():
        raise RuntimeError("disk gone")

    lease = _open()
    lease.retain(_boom)
    lease.retain(lambda: ran.append("second"))
    lease.close()
    assert ran == ["second"]


def test_cleanup_runs_once():
    ran = []
    lease = _open()
    lease.retain(lambda: ran.append(1))
    lease.close()
    lease.close()
    assert ran == [1]


# ---------------------------------------------------------------------------
# A11 bug 4: a failed __enter__ deregisters
# ---------------------------------------------------------------------------

def test_a_lease_revoked_before_its_with_block_leaves_no_open_row():
    registry = LeaseRegistry()
    lease = _open(registry)
    lease.revoke("NOT_GRANTED")

    with pytest.raises(Denied):
        with lease:
            pass

    assert lease not in registry, "a failed __enter__ must not leak the row"
    assert lease.closed is True


def test_recording_a_revocation_revokes_the_open_lease(tmp_path):
    """The producer for A11-G3's hook: the store's own writer calls it.

    Without this the hook is dead vocabulary -- the exact defect shape
    the whole solidity pass is about.
    """
    from halbert_core.consent.store import ConsentStore
    from halbert_core.persona.permission import lease as lease_mod

    registry = LeaseRegistry()
    lease = _open(registry)
    lease_mod.set_revocation_registry(registry)
    try:
        store = ConsentStore(
            data_dir=str(tmp_path / "data"),
            config_dir=str(tmp_path / "config"),
        )
        store.record_decision(
            CAP,
            ConsentDecision.DENIED,
            principal=_owner(),
            surface="desktop-app/settings",
        )
    finally:
        lease_mod.set_revocation_registry(None)

    assert lease.revoked is True
