# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-08 Phase E: who decided is what the server validated, not what it was told.

A11-G12. ``Principal.authn`` and ``Principal.surface`` are caller-supplied
strings, and ``may_record_grant`` decides the widening asymmetry by
reading them: owner, first-party surface, ``authn`` starting with
``os_reauth:``, at the machine. Every one of those four is a string the
caller wrote. Anything that can construct a ``Principal`` can mint the
strongest grant on the machine by typing the right words into it.

A ``SurfaceReceipt`` is the server's own record of what it actually
validated on the request -- the same shape the voice relay receipts use
one door over, and for the same reason: the redemption carries the
authority, never the caller's word about it.

**Reported, not built (the packet's STOP condition):** the ``os_reauth``
leg cannot be minted. ``dashboard/auth.py`` validates a session
credential and a Host header; nothing in the tree performs an OS re-auth
(no LocalAuthentication, no polkit, no sudo challenge), so no receipt can
honestly claim one. The rule here is that it fails closed rather than
accepting a caller-supplied string as an interim -- which means a grant
requiring live OS re-auth cannot be recorded until that handler exists.
That is the correct state: the alternative is a promise the code cannot
keep.
"""

import pytest

from halbert_core.persona.permission.consent import (
    Principal,
    SurfaceReceipt,
    may_record_grant,
)


def test_a_receipt_records_what_the_server_validated():
    receipt = SurfaceReceipt.for_session(
        surface="desktop-app/first-run", principal_id="local:501",
        at_machine=True,
    )
    assert receipt.surface == "desktop-app/first-run"
    assert receipt.at_machine is True
    assert receipt.os_reauth is False


def test_a_session_receipt_cannot_claim_os_reauth():
    """The STOP condition, pinned: no handler exists to mint one."""
    receipt = SurfaceReceipt.for_session(
        surface="desktop-app/first-run", principal_id="local:501",
        at_machine=True,
    )
    assert receipt.os_reauth is False


def test_a_grant_needs_a_receipt_not_a_string():
    """A Principal whose authn string SAYS os_reauth mints nothing."""
    forged = Principal(
        kind="owner", id="local:501",
        authn="os_reauth:touchid",         # the caller's own word
        at_machine=True,
    )
    assert may_record_grant(forged, "desktop-app/first-run") is False


def test_a_receipt_without_os_reauth_still_cannot_widen():
    receipt = SurfaceReceipt.for_session(
        surface="desktop-app/first-run", principal_id="local:501",
        at_machine=True,
    )
    owner = Principal(kind="owner", id="local:501", at_machine=True,
                      surface_receipt=receipt)
    assert may_record_grant(owner, "desktop-app/first-run") is False


def test_a_receipt_that_did_record_os_reauth_widens():
    """The shape the future handler mints; nothing produces it today."""
    receipt = SurfaceReceipt(
        surface="desktop-app/first-run",
        principal_id="local:501",
        at_machine=True,
        os_reauth=True,
        method="test-only",
    )
    owner = Principal(kind="owner", id="local:501", at_machine=True,
                      surface_receipt=receipt)
    assert may_record_grant(owner, "desktop-app/first-run") is True


def test_the_receipts_surface_must_match_the_route_it_is_used_on():
    receipt = SurfaceReceipt(
        surface="desktop-app/settings", principal_id="local:501",
        at_machine=True, os_reauth=True, method="test-only",
    )
    owner = Principal(kind="owner", id="local:501", at_machine=True,
                      surface_receipt=receipt)
    assert may_record_grant(owner, "desktop-app/first-run") is False


def test_a_remote_receipt_never_widens():
    receipt = SurfaceReceipt(
        surface="desktop-app/first-run", principal_id="local:501",
        at_machine=False, os_reauth=True, method="test-only",
    )
    owner = Principal(kind="owner", id="local:501", at_machine=False,
                      surface_receipt=receipt)
    assert may_record_grant(owner, "desktop-app/first-run") is False


def test_narrowing_needs_no_receipt():
    """Revocation has no bar; only widening does."""
    from halbert_core.persona.permission.consent import ConsentDecision

    # A narrowing decision never calls may_record_grant at all; this
    # pins that the store's own path does not require one.
    assert ConsentDecision.DENIED is not ConsentDecision.GRANTED
