# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Run receipts, simplified single-instance variant (packet 03 A3 + Hermes
addendum): a 'started' marker persisted BEFORE side effects; on boot, a
running marker whose owner pid is dead becomes 'interrupted'; completed
scheduled instants are idempotent (a completed occurrence can never fire
again even if next_run_at was left stale by a crash); terminal statuses are
the closed Hermes set ok / error / delivery_failed / blocked_config.

Deliberately NOT OpenClaw's multi-instance invariant matrix — a single-user
assistant takes the 90/10."""
import json
import os

import pytest

from halbert_core.scheduler.run_receipts import (
    CLOSED_STATUSES,
    RunReceiptStore,
    delivered_to_user,
)


def test_started_marker_is_on_disk_before_returning(tmp_path):
    # The whole point: the marker survives a crash the instant mark_started
    # returns — Phase B's receipt-ordering gate relies on this.
    path = tmp_path / "receipts.json"
    store = RunReceiptStore(path)
    rid = store.mark_started(job_id="detector_sweep", owner_pid=os.getpid())
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["receipts"][rid]["status"] == "running"


def test_status_after_started_is_running(tmp_path):
    store = RunReceiptStore(tmp_path / "receipts.json")
    rid = store.mark_started(job_id="detector_sweep", owner_pid=os.getpid())
    assert store.status(rid) == "running"


def test_completion_and_error(tmp_path):
    store = RunReceiptStore(tmp_path / "receipts.json")
    rid = store.mark_started("j", owner_pid=1)
    store.mark_finished(rid, "ok")
    assert store.status(rid) == "ok"
    rid2 = store.mark_started("j", owner_pid=1)
    store.mark_finished(rid2, "error", error="boom")
    assert store.status(rid2) == "error"
    assert store.receipt(rid2)["error"] == "boom"


def test_closed_status_set_rejects_unknown(tmp_path):
    store = RunReceiptStore(tmp_path / "receipts.json")
    rid = store.mark_started("j", owner_pid=1)
    assert CLOSED_STATUSES == frozenset({"ok", "error", "delivery_failed", "blocked_config"})
    for status in CLOSED_STATUSES:
        r = store.mark_started("j2", owner_pid=1)
        store.mark_finished(r, status)
    with pytest.raises(ValueError):
        store.mark_finished(rid, "success")  # not in the closed set


def test_delivery_failed_is_not_ok_but_run_succeeded(tmp_path):
    # run success != user notified: the consumer must ask delivered_to_user,
    # never `status == "ok"`, for "the user got it".
    store = RunReceiptStore(tmp_path / "receipts.json")
    rid = store.mark_started("j", owner_pid=1)
    store.mark_finished(rid, "delivery_failed")
    assert store.status(rid) == "delivery_failed"
    assert delivered_to_user("ok")
    assert not delivered_to_user("delivery_failed")
    assert not delivered_to_user("error")
    assert not delivered_to_user("blocked_config")


def test_boot_recovery_interrupts_dead_owners(tmp_path):
    store = RunReceiptStore(tmp_path / "receipts.json")
    rid = store.mark_started("j", owner_pid=999999)  # certainly not our pid
    recovered = store.recover_on_boot(owner_alive=lambda pid: pid == os.getpid())
    assert store.status(rid) == "interrupted"
    assert recovered == [rid]


def test_boot_recovery_leaves_live_owners_alone(tmp_path):
    store = RunReceiptStore(tmp_path / "receipts.json")
    rid = store.mark_started("j", owner_pid=os.getpid())
    store.recover_on_boot(owner_alive=lambda pid: True)
    assert store.status(rid) == "running"


def test_boot_recovery_default_pid_check(tmp_path):
    store = RunReceiptStore(tmp_path / "receipts.json")
    rid = store.mark_started("j", owner_pid=999999)
    store.recover_on_boot()  # default: real pid-liveness probe
    assert store.status(rid) == "interrupted"


def test_completed_occurrence_is_idempotent_and_queryable(tmp_path):
    store = RunReceiptStore(tmp_path / "receipts.json")
    assert store.occurrence_completed("detector_sweep", 1796763600.0) is False
    store.completed_occurrence("detector_sweep", 1796763600.0)
    store.completed_occurrence("detector_sweep", 1796763600.0)  # repeat is a no-op
    assert store.occurrence_completed("detector_sweep", 1796763600.0) is True
    assert store.occurrence_completed("detector_sweep", 1796763601.0) is False


def test_terminal_receipt_records_its_occurrence(tmp_path):
    store = RunReceiptStore(tmp_path / "receipts.json")
    rid = store.mark_started("j", owner_pid=1, scheduled_instant=1796763600.0)
    store.mark_finished(rid, "ok")
    assert store.occurrence_completed("j", 1796763600.0)
    # an interrupted run proves nothing — no occurrence is recorded
    rid2 = store.mark_started("j", owner_pid=999999, scheduled_instant=1796763601.0)
    store.recover_on_boot(owner_alive=lambda pid: pid == os.getpid())
    assert store.status(rid2) == "interrupted"
    assert not store.occurrence_completed("j", 1796763601.0)


def test_receipts_survive_reopen(tmp_path):
    path = tmp_path / "receipts.json"
    store = RunReceiptStore(path)
    rid = store.mark_started("j", owner_pid=999999, scheduled_instant=42.0)
    store.mark_finished(rid, "blocked_config")
    store.completed_occurrence("j", 99.0)
    reopened = RunReceiptStore(path)
    assert reopened.status(rid) == "blocked_config"
    assert reopened.occurrence_completed("j", 99.0)