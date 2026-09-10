# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The Lease — one object doing five jobs (§1.6), D3-P3's pure half.

The gate does not return a boolean; it returns the thing that does the
work. ``require()`` is the only mint: it evaluates the five axes, raises
the D3-P2 typed ``Denied`` on any refusal, and mints a ``Lease`` whose
``__init__`` is module-private. The lease registers in an in-process
registry on open and deregisters on close — **an indicator is defined
as the set of open leases**. ``lease.check()`` runs every loop
iteration; revocation or halt sets the loop's ``threading.Event`` so
the thread *exits*. Redaction fails closed on the capability, not the
frame. The resolved-path check runs on the path the handler will
actually open, obtained once (F16).

The Lease-typed constructors on the six capture/exec/egress primitives
and the chokepoint lint are the review-gated half (task 6) and land
with the D3-P5 wiring pass.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from halbert_core.consent.denials import Denied
from halbert_core.persona.permission import (
    AffordanceTable,
    CapabilityCeiling,
    ConsentDecision,
    ConsentRecord,
    HaltReason,
    HaltState,
    OsGrantState,
    OsGrantTable,
    Principal,
    VOCABULARY,
    takes_consent_records,
)
from halbert_core.persona.permission.lease import (
    DEFAULT_REGISTRY,
    Lease,
    LeaseRegistry,
    Scope,
    require,
)

CAP = "sensor.screen"


def _owner() -> Principal:
    return Principal(
        kind="owner", id="local:501", authn="os_reauth:touchid", at_machine=True
    )


def _grant_record(capability=CAP, scope=None) -> ConsentRecord:
    return ConsentRecord(
        capability=capability,
        decision=ConsentDecision.GRANTED,
        ts="2026-09-06T14:12:03Z",
        principal=_owner(),
        surface="desktop-app/first-run",
        text_shown_sha256="9f2c" + "0" * 60,
        scope=scope if scope is not None else {},
    )


def _records(*records):
    return list(records)


def _affirmative(capability=CAP, records=None, halt=None):
    """The axis evidence for a fully-wired, fully-granted capability.

    R-08 Phase A (A11 bug 6): ``halt=None`` used to read as "not halted",
    so these tests could leave the axis unwired and still reach the axes
    they were about. An omitted halt is now no halt EVIDENCE, which
    denies like every other unwired axis -- so a caller that means "the
    machine is running" has to say so with a live state, which is what
    the wiring always did.
    """
    return dict(
        ceiling=CapabilityCeiling(frozenset({capability})),
        affordance=AffordanceTable(present=frozenset({capability})),
        os_grants=OsGrantTable({capability: OsGrantState.GRANTED}),
        consent_records=records if records is not None else _records(_grant_record(capability)),
        halt=halt if halt is not None else HaltState(),
    )


# ---------------------------------------------------------------------------
# require() is the only mint.
# ---------------------------------------------------------------------------


def test_a_lease_cannot_be_constructed_directly():
    """Red-first on the series' own task: no other way to obtain one.
    __init__ is module-private; the TypeError is the design's chosen
    bar (§1.6: 'the only mint is require()')."""
    with pytest.raises(TypeError):
        Lease()


def test_require_returns_a_lease_when_every_axis_affirms():
    lease = require(CAP, **_affirmative())

    assert isinstance(lease, Lease)
    assert lease.capability == CAP
    assert not lease.closed


def test_require_mints_on_the_default_registry_and_deregisters_on_close():
    registry = LeaseRegistry()
    lease = require(CAP, registry=registry, **_affirmative())

    assert registry.open_leases() == (lease,)
    assert lease in registry

    lease.close()
    assert registry.open_leases() == ()
    assert lease.closed


def test_the_module_default_registry_exists_but_never_leaks_into_tests():
    assert isinstance(DEFAULT_REGISTRY, LeaseRegistry)


def test_require_carries_the_activity_provenance():
    lease = require(
        CAP, actor="user", reason="what's on my screen?", turn_id="t42",
        **_affirmative(),
    )

    row = lease.activity_row()
    assert row["capability"] == CAP
    assert row["actor"] == "user"
    assert row["reason"] == "what's on my screen?"
    assert row["turn_id"] == "t42"
    assert row["opened_at"]


def test_the_lease_is_a_context_manager():
    registry = LeaseRegistry()

    with require(CAP, registry=registry, **_affirmative()) as lease:
        assert registry.open_leases() == (lease,)

    assert registry.open_leases() == ()


# ---------------------------------------------------------------------------
# Every refusal is the typed denial — never a bare False.
# ---------------------------------------------------------------------------


def test_a_denied_capability_raises_the_typed_denial():
    with pytest.raises(Denied) as caught:
        require(
            CAP,
            ceiling=CapabilityCeiling(frozenset({CAP})),
            halt=HaltState(),
        )

    assert caught.value.reason_code == "NO_AFFORDANCE"


def test_require_with_no_wiring_at_all_denies():
    """R-08 Phase A (A11 bug 6): the FIRST unwired axis is halt.

    This used to reach the ceiling, because ``halt=None`` read as "not
    halted" -- the evaluator vouched for the machine not being stopped
    on no evidence at all. With halt evidence supplied, the ceiling
    answers as before; with nothing at all, the halt axis does.
    """
    with pytest.raises(Denied) as caught:
        require(CAP)
    assert caught.value.reason_code == "HALTED"

    with pytest.raises(Denied) as caught:
        require(CAP, halt=HaltState())
    assert caught.value.reason_code == "NO_CEILING"


def test_a_halted_machine_denies_every_capability_through_require():
    halt = HaltState()
    halt.halt(HaltReason.OWNER_STOP)

    with pytest.raises(Denied) as caught:
        require(CAP, **_affirmative(halt=halt))

    assert caught.value.reason_code == "HALTED"


def test_the_empty_ledger_refuses_every_consenting_capability_through_require():
    """The deny-all canary's pure half: no grant ever recorded, every
    sensor/reach/egress/auto call raises NOT_GRANTED. The canary drive of
    every registered tool is the D3-P5 registry's half."""
    for capability in sorted(
        cap for cap in VOCABULARY
        if takes_consent_records(cap) and cap != "egress.telemetry"
    ):
        with pytest.raises(Denied) as caught:
            require(capability, **_affirmative(capability, records=[]))
        assert caught.value.reason_code == "NOT_GRANTED", capability


def test_the_denial_carries_the_full_axis_evidence():
    with pytest.raises(Denied) as caught:
        require(CAP, ceiling=CapabilityCeiling(frozenset({CAP})))

    assert caught.value.decision is not None
    assert caught.value.decision.capability == CAP


# ---------------------------------------------------------------------------
# The registry — an indicator is the set of open leases.
# ---------------------------------------------------------------------------


def test_the_indicator_is_exactly_the_open_set():
    registry = LeaseRegistry()
    first = require(CAP, registry=registry, **_affirmative())
    second = require(CAP, registry=registry, **_affirmative())

    assert registry.open_leases() == (first, second)

    first.close()
    assert registry.open_leases() == (second,)
    assert len(registry) == 1


def test_a_lying_indicator_is_structurally_impossible():
    """There is no API to add a lease to the registry without opening one
    (require) and none to keep a closed one listed — the indicator has
    no second source of truth to drift from."""
    registry = LeaseRegistry()
    lease = require(CAP, registry=registry, **_affirmative())

    with pytest.raises(TypeError):
        registry.register("not a lease")

    lease.close()
    with pytest.raises(TypeError):
        registry.deregister("not a lease")
    assert registry.open_leases() == ()


def test_revoke_all_marks_every_open_lease():
    registry = LeaseRegistry()
    events = [threading.Event() for _ in range(3)]
    leases = [
        require(CAP, registry=registry, stop_event=e, **_affirmative())
        for e in events
    ]

    count = registry.revoke_all("HALTED", by="owner", surface="tray")

    assert count == 3
    for lease, event in zip(leases, events):
        assert lease.revoked
        assert event.is_set()


# ---------------------------------------------------------------------------
# lease.check() — the loop's liveness token.
# ---------------------------------------------------------------------------


def test_check_passes_on_a_live_lease():
    lease = require(CAP, **_affirmative())
    lease.check()  # no raise


def test_a_halt_mid_lease_fails_the_next_check_and_sets_the_event():
    halt = HaltState()
    event = threading.Event()
    lease = require(CAP, stop_event=event, **_affirmative(halt=halt))

    halt.halt(HaltReason.OWNER_STOP)

    with pytest.raises(Denied) as caught:
        lease.check()

    assert caught.value.reason_code == "HALTED"
    assert caught.value.detail  # the machine says which stop
    assert event.is_set()  # the loop's thread exits rather than failing


def test_a_loop_that_checks_exits_when_halted():
    halt = HaltState()
    event = threading.Event()
    lease = require(CAP, stop_event=event, **_affirmative(halt=halt))

    iterations = 0
    with pytest.raises(Denied):
        while True:  # the capture-loop shape
            lease.check()
            iterations += 1
            if iterations == 2:
                halt.halt(HaltReason.OWNER_STOP)

    assert iterations == 2  # the very next iteration ended the loop


def test_a_revoked_lease_fails_the_next_check():
    event = threading.Event()
    lease = require(CAP, stop_event=event, **_affirmative())

    lease.revoke("NOT_GRANTED", by="owner")

    with pytest.raises(Denied) as caught:
        lease.check()

    assert caught.value.reason_code == "NOT_GRANTED"
    assert event.is_set()


def test_revocation_reasons_stay_in_the_closed_vocabulary():
    lease = require(CAP, **_affirmative())

    with pytest.raises(ValueError):
        lease.revoke("JUST_BECAUSE")


def test_checking_a_closed_lease_is_a_programming_error():
    lease = require(CAP, **_affirmative())
    lease.close()

    with pytest.raises(RuntimeError):
        lease.check()


def test_revoke_is_idempotent():
    lease = require(CAP, **_affirmative())
    lease.revoke("NOT_GRANTED", by="owner")
    lease.revoke("HALTED", by="owner")

    assert lease.revoked_reason == "HALTED"


# ---------------------------------------------------------------------------
# Redaction fails closed on the capability, not the frame.
# ---------------------------------------------------------------------------


def test_a_redaction_required_scope_refuses_to_open_without_a_backend():
    halt = HaltState()
    records = [_grant_record(
        scope={"displays": ["*"], "redaction": "required"},
    )]

    with pytest.raises(Denied) as caught:
        require(CAP, halt=halt, consent_records=records, **{
            k: v for k, v in _affirmative(records=records, halt=halt).items()
            if k not in ("consent_records", "halt")
        })

    # The §4.1 ruling: redaction-unavailable is a halt, and the refusal
    # says so — the machine stops rather than capture and mislabel.
    assert caught.value.reason_code == "HALTED"
    assert halt.is_halted()
    assert halt.reason_code == HaltReason.REDACTION_UNAVAILABLE


def test_a_redaction_required_scope_opens_with_a_working_backend():
    records = [_grant_record(
        scope={"displays": ["*"], "redaction": "required"},
    )]

    lease = require(
        CAP, consent_records=records, redaction_backend_available=True,
        **{k: v for k, v in _affirmative(records=records).items()
           if k != "consent_records"},
    )

    assert isinstance(lease, Lease)


def test_redaction_is_only_required_when_the_grant_declares_it():
    # No scope declared -> no redaction requirement -> opens without one.
    lease = require(CAP, **_affirmative())

    assert isinstance(lease, Lease)


# ---------------------------------------------------------------------------
# Scope binding — the F16 shape.
# ---------------------------------------------------------------------------


def _reach_affirmative(root: Path, capability="reach.fs.write"):
    return dict(
        ceiling=CapabilityCeiling(frozenset({capability})),
        affordance=AffordanceTable(present=frozenset({capability})),
        os_grants=OsGrantTable({capability: OsGrantState.GRANTED}),
        consent_records=[_grant_record(
            capability, scope={"reach_roots": [str(root)]},
        )],
        halt=HaltState(),
    )


def test_the_resolved_path_is_obtained_once_and_used_for_both(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "sub").mkdir()
    lease = require("reach.fs.write", **_reach_affirmative(allowed))

    raw = str(allowed / "sub" / ".." / "notes.txt")
    resolved = lease.bind_path(raw)

    assert resolved == os.path.realpath(raw)
    assert Path(resolved).parent == allowed.resolve()


def test_a_path_outside_the_granted_roots_is_out_of_scope(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "secrets").write_text("x")
    lease = require("reach.fs.write", **_reach_affirmative(allowed))

    with pytest.raises(Denied) as caught:
        lease.bind_path(str(outside / "secrets"))

    assert caught.value.reason_code == "OUT_OF_SCOPE"


def test_a_symlink_inside_the_roots_pointing_outside_is_caught(tmp_path):
    """The raw argument is inside the granted root; the file it opens is
    not. The check runs on the resolved path — F16's exact trap."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "escape").write_text("x")
    os.symlink(outside / "escape", allowed / "innocent.txt")

    lease = require("reach.fs.write", **_reach_affirmative(allowed))

    with pytest.raises(Denied) as caught:
        lease.bind_path(str(allowed / "innocent.txt"))

    assert caught.value.reason_code == "OUT_OF_SCOPE"


def test_a_grant_without_reach_roots_binds_nothing(tmp_path):
    lease = require(CAP, **_affirmative())

    with pytest.raises(Denied) as caught:
        lease.bind_path(str(tmp_path / "anything"))
    assert caught.value.reason_code == "OUT_OF_SCOPE"


def test_the_requested_scope_must_be_inside_the_granted_scope(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    records = [_grant_record(
        CAP, scope={"displays": ["Studio"], "redaction": ""},
    )]

    # A named display the grant covers, and the wildcard.
    assert Scope(displays=("Studio",)).admits(Scope(displays=("Studio",)))
    lease = require(CAP, scope=Scope(displays=("Studio",)), **_affirmative(records=records))
    assert lease.bind_display("Studio") == "Studio"
    lease.close()

    # A display the grant does not name and does not wildcard.
    with pytest.raises(Denied) as caught:
        require(CAP, scope=Scope(displays=("Basement TV",)), **_affirmative(records=records))
    assert caught.value.reason_code == "OUT_OF_SCOPE"


def test_bind_display_and_camera_refuse_outside_the_grant():
    records = [_grant_record(CAP, scope={"displays": ["*"]})]
    lease = require(CAP, **_affirmative(records=records))

    assert lease.bind_display("Studio") == "Studio"
    # The grant covers displays only — a camera binding is out of scope.
    with pytest.raises(Denied) as caught:
        lease.bind_camera("Front")
    assert caught.value.reason_code == "OUT_OF_SCOPE"


def test_scope_from_mapping_is_strict_about_unknown_keys():
    with pytest.raises(ValueError):
        Scope.from_mapping({"displays": ["*"], "surprise": 1})


def test_scope_from_mapping_is_strict_about_unknown_redaction_modes():
    with pytest.raises(ValueError):
        Scope.from_mapping({"redaction": "sometimes"})


def test_a_requested_scope_with_no_granted_scope_is_out_of_scope(tmp_path):
    # Grant with an empty scope: admitted names nothing.
    with pytest.raises(Denied) as caught:
        require(CAP, scope=Scope(displays=("Studio",)), **_affirmative())
    assert caught.value.reason_code == "OUT_OF_SCOPE"


def test_no_requested_scope_is_vacuously_in_scope():
    lease = require(CAP, **_affirmative())
    assert isinstance(lease, Lease)


def test_reach_roots_admit_by_resolved_prefix(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    granted = Scope(reach_roots=(str(root),))

    assert granted.admits(Scope(reach_roots=(str(root / "nested"),)))
    assert not granted.admits(Scope(reach_roots=(str(tmp_path / "other"),)))
    assert not Scope().admits(Scope(reach_roots=(str(root),)))  # no roots granted


def test_an_empty_requested_scope_admits_against_any_grant():
    assert Scope().admits(Scope())