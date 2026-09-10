# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-08 Phase B: the ask axis is enforced, not just recorded.

A11-G1 + bug 2 -- ``role_gate.py`` said it in its own comment: "Recorded,
never enforced". The review screen promises that ``reach.config.write``
and ``reach.privileged`` ask before every use; ``accept_profile`` dropped
``ask_every_use`` on the floor, so those rows landed in the ledger as
GRANTED, indistinguishable from an unconditional grant, and the per-use
confirmation existed only as a Python constant.

A11-G9 (FD-6) -- the confirmation, when it happens, has to be redeemable
against the thing that was approved. One ``ApprovalReceipt`` carries the
capability, the artefact digest and a single-use token, so approving one
config write cannot silently authorise a different one, and a receipt
cannot be spent twice.
"""

import pytest

from halbert_core.persona.permission.consent import ConsentDecision, Principal
from halbert_core.persona.permission.effective import axis_floor
from halbert_core.persona.permission.halt import HaltState
from halbert_core.persona.policy import AskPolicy, SecurityLevel


def _owner():
    return Principal(kind="owner", id="local:501", authn="os_reauth:touchid",
                     at_machine=True)


def _record(capability, *, ask="off", **kw):
    from halbert_core.persona.permission.consent import ConsentRecord

    return ConsentRecord(
        capability=capability,
        decision=ConsentDecision.GRANTED,
        ts="2026-01-01T00:00:00+00:00",
        principal=_owner(),
        surface="test",
        ask=ask,
        **kw,
    )


# ---------------------------------------------------------------------------
# A11-G1 + bug 2: the ask survives acceptance and reaches the lattice
# ---------------------------------------------------------------------------

def test_an_ask_row_is_written_as_ask_every_use():
    """``accept_profile`` used to drop it, so the ledger could not tell an
    ask-every-use grant from an unconditional one."""
    import halbert_core.persona.permission.profiles as profiles

    asks = [
        row.capability
        for row in profiles._ATTENTIVE.grants
        if row.ask_every_use
    ]
    assert "reach.config.write" in asks
    assert "reach.privileged" in asks


def test_the_consent_record_carries_the_ask_disposition():
    record = _record("reach.config.write", ask="every_use")
    assert record.ask == "every_use"


def test_an_unknown_ask_disposition_is_refused():
    with pytest.raises(ValueError):
        _record("reach.config.write", ask="sometimes")


def test_the_payload_codec_round_trips_the_ask():
    from halbert_core.consent.store import record_from_payload, record_to_payload

    record = _record("reach.config.write", ask="every_use")
    assert record_from_payload(record_to_payload(record)).ask == "every_use"


def test_an_ask_every_use_grant_contributes_always_to_the_lattice():
    """A11-G1: ``axis_floor`` was a constant OFF, so the ask axis could
    never reach a caller even once the record carried it."""
    from halbert_core.persona.permission.ceiling import CapabilityCeiling
    from halbert_core.persona.permission.affordance import AffordanceTable
    from halbert_core.persona.permission.effective import effective_capability
    from halbert_core.persona.permission.os_grant import (
        OsGrantState, OsGrantTable,
    )

    cap = "reach.config.write"
    decision = effective_capability(
        cap,
        ceiling=CapabilityCeiling(frozenset({cap})),
        affordance=AffordanceTable(present=frozenset({cap})),
        os_grants=OsGrantTable({cap: OsGrantState.GRANTED}),
        consent_records=[_record(cap, ask="every_use")],
        halt=HaltState(),
    )
    assert decision.allowed is True
    floor = axis_floor(decision)
    assert floor.ask is AskPolicy.ALWAYS
    assert floor.security is SecurityLevel.FULL


def test_an_unconditional_grant_still_contributes_off():
    from halbert_core.persona.permission.ceiling import CapabilityCeiling
    from halbert_core.persona.permission.affordance import AffordanceTable
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
    )
    assert axis_floor(decision).ask is AskPolicy.OFF


def test_require_reports_that_this_use_must_be_approved():
    """The caller has to be able to see it without re-deriving the ledger."""
    from halbert_core.persona.permission.ceiling import CapabilityCeiling
    from halbert_core.persona.permission.affordance import AffordanceTable
    from halbert_core.persona.permission.lease import Denied, require
    from halbert_core.persona.permission.os_grant import (
        OsGrantState, OsGrantTable,
    )

    cap = "reach.config.write"
    with pytest.raises(Denied) as excinfo:
        require(
            cap,
            ceiling=CapabilityCeiling(frozenset({cap})),
            affordance=AffordanceTable(present=frozenset({cap})),
            os_grants=OsGrantTable({cap: OsGrantState.GRANTED}),
            consent_records=[_record(cap, ask="every_use")],
            halt=HaltState(),
        )
    # No approval offered: an ask-every-use grant is not a grant yet.
    assert excinfo.value.reason_code == "NEEDS_APPROVAL"


# ---------------------------------------------------------------------------
# A11-G9 (FD-6): one ApprovalReceipt, carrying the artefact digest
# ---------------------------------------------------------------------------

def test_a_receipt_redeems_once_for_the_artefact_it_approved():
    from halbert_core.persona.permission.approval import ApprovalReceipts

    receipts = ApprovalReceipts()
    token = receipts.mint("reach.config.write", artefact_sha256="a" * 64)
    redeemed = receipts.redeem(
        token, "reach.config.write", artefact_sha256="a" * 64)
    assert redeemed is not None
    # Single use.
    assert receipts.redeem(
        token, "reach.config.write", artefact_sha256="a" * 64) is None


def test_a_receipt_does_not_redeem_for_a_different_artefact():
    """Approving one config write must not authorise a different one."""
    from halbert_core.persona.permission.approval import ApprovalReceipts

    receipts = ApprovalReceipts()
    token = receipts.mint("reach.config.write", artefact_sha256="a" * 64)
    assert receipts.redeem(
        token, "reach.config.write", artefact_sha256="b" * 64) is None


def test_a_receipt_does_not_redeem_for_a_different_capability():
    from halbert_core.persona.permission.approval import ApprovalReceipts

    receipts = ApprovalReceipts()
    token = receipts.mint("reach.config.write", artefact_sha256="a" * 64)
    assert receipts.redeem(
        token, "reach.privileged", artefact_sha256="a" * 64) is None


def test_an_expired_receipt_does_not_redeem():
    from halbert_core.persona.permission.approval import ApprovalReceipts

    receipts = ApprovalReceipts()
    clock = {"t": 1000.0}
    receipts._now = lambda: clock["t"]
    token = receipts.mint("reach.config.write", artefact_sha256="a" * 64)
    clock["t"] += receipts.TTL_S + 1
    assert receipts.redeem(
        token, "reach.config.write", artefact_sha256="a" * 64) is None


def test_an_approved_use_opens_the_lease():
    from halbert_core.persona.permission.affordance import AffordanceTable
    from halbert_core.persona.permission.approval import ApprovalReceipts
    from halbert_core.persona.permission.ceiling import CapabilityCeiling
    from halbert_core.persona.permission.lease import require
    from halbert_core.persona.permission.os_grant import (
        OsGrantState, OsGrantTable,
    )

    cap = "reach.config.write"
    receipts = ApprovalReceipts()
    token = receipts.mint(cap, artefact_sha256="a" * 64)
    lease = require(
        cap,
        ceiling=CapabilityCeiling(frozenset({cap})),
        affordance=AffordanceTable(present=frozenset({cap})),
        os_grants=OsGrantTable({cap: OsGrantState.GRANTED}),
        consent_records=[_record(cap, ask="every_use")],
        halt=HaltState(),
        approval_token=token,
        approval_receipts=receipts,
        artefact_sha256="a" * 64,
    )
    assert lease is not None
    lease.close()
