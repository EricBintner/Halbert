# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The halt state — axis 5 of five: is anything halted?

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §4.1: one action sets an
in-process halt state (and, in D3-P6, writes a persisted runtime/halt.json
read in Phase 0 before any subsystem starts). "Stop is also what failure
does" — the reason codes below are the design's failure list, plus the
owner's stop.
"""
from __future__ import annotations

import threading

from halbert_core.persona.permission.halt import HaltReason, HaltState


def test_reason_codes_are_the_designs_stop_and_failure_list():
    expected = {
        "owner_stop", "consent_unreadable", "consent_chain_broken",
        "integrity_missing", "audit_unwritable", "redaction_unavailable",
        "guardrail_trips",
    }
    codes = {
        HaltReason.OWNER_STOP, HaltReason.CONSENT_UNREADABLE,
        HaltReason.CONSENT_CHAIN_BROKEN, HaltReason.INTEGRITY_MISSING,
        HaltReason.AUDIT_UNWRITABLE, HaltReason.REDACTION_UNAVAILABLE,
        HaltReason.GUARDRAIL_TRIPS,
    }
    assert codes == expected


def test_fresh_state_is_not_halted():
    h = HaltState()
    assert h.is_halted() is False
    assert h.reason_code == ""


def test_halt_sets_flag_and_records_provenance():
    h = HaltState()
    h.halt(HaltReason.OWNER_STOP, by="owner", surface="tray")
    assert h.is_halted() is True
    assert h.reason_code == HaltReason.OWNER_STOP
    assert h.halted_by == "owner"
    assert h.halted_surface == "tray"
    assert h.halted_at is not None


def test_halt_wins_over_everything_by_being_checked_first():
    # the halt axis's precedence is the evaluator's concern (effective.py);
    # here we pin that a halted state cannot be read as anything but halted
    h = HaltState()
    h.halt(HaltReason.INTEGRITY_MISSING, by="system", surface="boot")
    assert h.is_halted()
    assert h.reason_code != ""


def test_a_second_halt_records_the_newer_reason():
    # stopped for one failure, then a second failure is detected while
    # stopped: the machine names the newest cause
    h = HaltState()
    h.halt(HaltReason.CONSENT_UNREADABLE, by="system", surface="boot")
    h.halt(HaltReason.AUDIT_UNWRITABLE, by="system", surface="boot")
    assert h.reason_code == HaltReason.AUDIT_UNWRITABLE
    assert h.is_halted()


def test_resume_clears_and_records_provenance():
    h = HaltState()
    h.halt(HaltReason.OWNER_STOP, by="owner", surface="tray")
    h.resume(by="owner", surface="settings")
    assert h.is_halted() is False
    assert h.reason_code == ""
    assert h.resumed_by == "owner"
    assert h.resumed_surface == "settings"
    assert h.resumed_at is not None


def test_resume_on_a_running_state_is_a_no_op():
    h = HaltState()
    h.resume(by="owner", surface="settings")
    assert h.is_halted() is False
    assert h.resumed_at is None  # nothing was resumed


def test_concurrent_halt_and_read_is_safe():
    h = HaltState()
    errors: list[str] = []

    def hammer():
        try:
            for reason in (HaltReason.OWNER_STOP, HaltReason.GUARDRAIL_TRIPS):
                h.halt(reason, by="t", surface="test")
                _ = h.is_halted(), h.reason_code
                h.resume(by="t", surface="test")
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(repr(exc))

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert h.is_halted() is False  # every hammer resumed what it halted