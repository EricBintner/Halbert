# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Packet 03 B1: run receipts + restart budget wired into AutonomousExecutor.

The receipts-before-effects ordering is the packet's verification gate: the
'started' marker must be on disk BEFORE the task callable begins executing
— asserted from inside the task, reading the file, not the in-memory store.

Boot recovery then interrupts dead-owner running markers and gives the job
one bounded re-run when its callable re-registers (jobs are re-registered at
every boot, C4-01); the sliding-window restart budget is what keeps a
crash-looping job from re-running forever — on BLOCK the executor logs a
structured restart_budget_exhausted line and holds in safe-mode instead of
looping.
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("apscheduler")

from halbert_core.scheduler.executor import AutonomousExecutor  # noqa: E402


def _wait_for(predicate, timeout_s: float = 10.0, step_s: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step_s)
    return predicate()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Scheduler JSON records (and now receipts + the restart ledger) go
    under a throwaway data dir."""
    d = tmp_path / "data"
    monkeypatch.setenv("HALBERT_DATA_DIR", str(d))
    return d


def _make_executor(**kwargs) -> AutonomousExecutor:
    kwargs.setdefault("max_workers", 2)
    kwargs.setdefault("enable_llm", False)
    kwargs.setdefault("enable_guardrails", False)
    kwargs.setdefault("timezone", "UTC")
    return AutonomousExecutor(**kwargs)


def _read_receipts(data_dir) -> dict:
    return json.loads(
        (data_dir / "scheduler" / "receipts.json").read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# the ordering gate: the marker exists on disk before the side effects begin
# ---------------------------------------------------------------------------

def test_started_marker_is_on_disk_before_the_task_runs(data_dir):
    """The receipt-ordering proof: read receipts.json from inside the task
    and find this job's marker already there, status 'running'."""
    ex = _make_executor()
    seen: dict = {}

    def task():
        raw = _read_receipts(data_dir)
        seen["running"] = [
            rec
            for rec in raw["receipts"].values()
            if rec.get("job_id") == "proof" and rec.get("status") == "running"
        ]
        return "ran"

    ex.start()
    ex.schedule_one_time(
        job_id="proof",
        task_func=task,
        run_at=datetime.now(timezone.utc) + timedelta(seconds=0.2),
        max_retries=1,
        timeout_s=30,
    )
    assert _wait_for(
        lambda: ex.scheduler_engine.get_job("proof").state == "completed"
    ), "the job never completed"
    assert seen.get("running"), (
        "no 'running' receipt for the job was on disk while the task ran"
    )
    # The same receipt reached a terminal status once the run finished.
    raw = _read_receipts(data_dir)
    assert not any(
        rec.get("status") == "running" for rec in raw["receipts"].values()
    )
    assert any(
        rec.get("job_id") == "proof" and rec.get("status") == "ok"
        for rec in raw["receipts"].values()
    )
    ex.stop(wait=False)


def test_failed_task_records_an_error_receipt(data_dir):
    def boom():
        raise RuntimeError("disk on fire")

    ex = _make_executor()
    ex.start()
    ex.schedule_one_time(
        job_id="bad",
        task_func=boom,
        run_at=datetime.now(timezone.utc) + timedelta(seconds=0.2),
        max_retries=1,
    )
    assert _wait_for(lambda: ex.scheduler_engine.get_job("bad").state == "failed")
    raw = _read_receipts(data_dir)
    assert any(
        rec.get("job_id") == "bad"
        and rec.get("status") == "error"
        and "disk on fire" in (rec.get("error") or "")
        for rec in raw["receipts"].values()
    )
    ex.stop(wait=False)


# ---------------------------------------------------------------------------
# boot recovery: dead-owner markers become interrupted; the job re-runs once
# ---------------------------------------------------------------------------

def test_boot_recovery_interrupts_a_dead_owner_and_reruns_once(data_dir):
    # The "crashed" boot leaves a running receipt whose owner (pid <= 0)
    # can never be alive.
    crashed = _make_executor()
    rid = crashed.receipts.mark_started("detector_sweep", owner_pid=-1)

    ex = _make_executor()
    ex.start()
    assert ex.receipts.status(rid) == "interrupted"

    ran = threading.Event()

    def task():
        ran.set()
        return "recovered"

    # Cron far in the future: only the re-run can fire the task during the
    # test, so the event proves the recovery run happened.
    ex.schedule_cron_job(
        job_id="detector_sweep",
        task_func=task,
        cron_expr={"hour": 23, "minute": 59},
        max_retries=2,
    )
    assert ran.wait(10), "the interrupted job's re-run never fired"
    # The re-run went through the scheduler as its own one-time job, and
    # the (durable, unlike APScheduler's memory store) engine record shows
    # it completed.
    assert _wait_for(
        lambda: ex.scheduler_engine.get_job("detector_sweep:recovery").state
        == "completed"
    )

    # Bounded: re-registering the job again does not arm a second re-run —
    # the pending set was consumed, and the durable ledger shows one arm.
    ex.schedule_cron_job(
        job_id="detector_sweep",
        task_func=task,
        cron_expr={"hour": 23, "minute": 58},
        max_retries=2,
    )
    ledger = json.loads(
        (data_dir / "scheduler" / "restarts.json").read_text(encoding="utf-8")
    )
    assert len(ledger["detector_sweep"]) == 1
    ex.stop(wait=False)


def test_boot_recovery_skips_jobs_without_a_retry_budget(data_dir, caplog):
    ex = _make_executor()
    ex.receipts.mark_started("no_budget", owner_pid=-1)
    ex.start()
    with caplog.at_level(logging.INFO, logger="halbert.scheduler.executor"):
        ex.schedule_cron_job(
            job_id="no_budget",
            task_func=lambda: None,
            cron_expr={"hour": 1, "minute": 1},
            max_retries=0,
        )
    assert not any(
        j["id"] == "no_budget:recovery" for j in ex.get_scheduled_jobs()
    )
    assert any(
        "no retry budget" in r.getMessage() for r in caplog.records
    )
    ex.stop(wait=False)


# ---------------------------------------------------------------------------
# the restart budget: a spent budget blocks the 6th restart and holds
# ---------------------------------------------------------------------------

def test_spent_restart_budget_blocks_the_sixth_restart_and_holds(data_dir, caplog):
    # Five restarts in the last hour, durable across boots: the ledger file
    # is what the next boot loads.
    ledger_path = data_dir / "scheduler" / "restarts.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    ledger_path.write_text(
        json.dumps({"crashy": [now - 60 * i for i in range(5, 0, -1)]}),
        encoding="utf-8",
    )

    ex = _make_executor()
    assert len(ex._restart_ledger["crashy"]) == 5  # loaded from disk

    # Simulate boot recovery having found an interrupted run of this job
    # (start() with an empty receipts store leaves the preset alone).
    ex._boot_recovery_pending = {"crashy"}

    holds: list = []

    class _FakeEnforcer:
        def enter_safe_mode(self, reason):
            holds.append(reason)

    ex.guardrail_enforcer = _FakeEnforcer()

    with caplog.at_level(logging.ERROR, logger="halbert.scheduler.executor"):
        ex.start()
        ex.schedule_cron_job(
            job_id="crashy",
            task_func=lambda: None,
            cron_expr={"hour": 3, "minute": 33},
            max_retries=3,
        )

    structured = [
        r.getMessage()
        for r in caplog.records
        if "restart_budget_exhausted" in r.getMessage()
    ]
    assert structured, "no structured restart_budget_exhausted line was logged"
    assert "job_id=crashy" in structured[0]
    assert "restarts_in_window=5" in structured[0]
    assert not any(
        j["id"] == "crashy:recovery" for j in ex.get_scheduled_jobs()
    ), "a job that failed 5x within the hour attempted a 6th restart"
    # Safe-mode hold, not a loop: the next restart must come from a human.
    assert holds and "restart_budget_exhausted" in holds[0]
    ex.stop(wait=False)