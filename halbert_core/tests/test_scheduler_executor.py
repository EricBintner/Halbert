# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""C4-01: the autonomous executor can register and run jobs.

Three faults kept every dashboard job (detector sweep, morning report)
from ever running:

1. The APScheduler store was a SQLAlchemyJobStore, which pickles the job's
   callable. ``_wrap_task`` returns a local closure, so every
   ``add_job`` on a started scheduler raised
   ``ValueError: This Job cannot be serialized``.
2. The per-job timeout used ``signal.SIGALRM``, which only works on the
   main thread — and APScheduler runs jobs on its worker pool, so the
   wrapped task raised ``ValueError: signal only works in main thread``
   before the task ran.
3. The guardrail confidence branch read an undefined name ``job``
   (``NameError`` on every guarded run, caught by nothing).

Jobs are re-registered at every boot, so the APScheduler store is now in
memory; the SchedulerEngine's JSON records keep status and history.
"""

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
    """SchedulerEngine JSON records go under a throwaway data dir."""
    d = tmp_path / "data"
    monkeypatch.setenv("HALBERT_DATA_DIR", str(d))
    return d


def _make_executor(**kwargs) -> AutonomousExecutor:
    kwargs.setdefault("max_workers", 2)
    kwargs.setdefault("enable_llm", False)
    kwargs.setdefault("enable_guardrails", False)
    kwargs.setdefault("timezone", "UTC")
    return AutonomousExecutor(**kwargs)


@pytest.fixture
def executor(data_dir):
    ex = _make_executor()
    yield ex
    ex.stop(wait=False)


@pytest.fixture
def guarded_executor(data_dir):
    ex = _make_executor(enable_guardrails=True)
    yield ex
    ex.stop(wait=False)


# ---------------------------------------------------------------------------
# (1) registration: a local closure must be schedulable on a started scheduler
# ---------------------------------------------------------------------------

def test_schedule_cron_job_accepts_a_local_closure(executor):
    executor.start()
    job_id = executor.schedule_cron_job(
        job_id="detector_sweep",
        task_func=lambda: None,
        cron_expr={"hour": "*/6", "minute": 12},
        description="Detector sweep",
    )
    assert job_id == "detector_sweep"
    scheduled = {j["id"]: j for j in executor.get_scheduled_jobs()}
    assert "detector_sweep" in scheduled
    assert scheduled["detector_sweep"]["next_run"] is not None
    record = executor.scheduler_engine.get_job("detector_sweep")
    assert record is not None and record.state == "pending"


def test_schedule_one_time_accepts_a_local_closure(executor):
    executor.start()
    run_at = datetime.now(timezone.utc) + timedelta(hours=1)
    executor.schedule_one_time(job_id="once", task_func=lambda: None, run_at=run_at)
    assert "once" in {j["id"] for j in executor.get_scheduled_jobs()}


class TestCadenceScaledMisfireGrace:
    """R-03 Phase C (A06-G3): the flat 60s misfire_grace_time was tuned to
    nothing in particular; a job missed while the process is alive but the
    machine is briefly busy (not asleep -- that needs boot/wake catch-up,
    a separate mechanism) should get a grace scaled to its own cadence,
    the same halved-clamped rule the boot catch-up path already uses."""

    def test_a_period_scales_the_grace(self, executor):
        executor.start()
        executor.schedule_cron_job(
            job_id="morning_report", task_func=lambda: None,
            cron_expr={"hour": 8, "minute": 0}, period_s=3600.0,
        )
        job = executor.scheduler.get_job("morning_report")
        assert job.misfire_grace_time == 1800  # half of 1h, well inside [120s, 2h]

    def test_a_long_period_clamps_to_the_two_hour_cap(self, executor):
        executor.start()
        executor.schedule_cron_job(
            job_id="detector_sweep", task_func=lambda: None,
            cron_expr={"hour": "*/6", "minute": 12}, period_s=6 * 3600.0,
        )
        job = executor.scheduler.get_job("detector_sweep")
        assert job.misfire_grace_time == 7200  # half of 6h (10800s) clamps to the 2h cap

    def test_no_period_keeps_todays_default(self, executor):
        executor.start()
        executor.schedule_cron_job(
            job_id="adhoc", task_func=lambda: None, cron_expr={"minute": "*/5"},
        )
        job = executor.scheduler.get_job("adhoc")
        assert job.misfire_grace_time == 60


def test_apscheduler_store_is_in_memory(executor, data_dir):
    from apscheduler.jobstores.memory import MemoryJobStore

    assert isinstance(executor.scheduler._lookup_jobstore("default"), MemoryJobStore)
    assert not (data_dir / "scheduler" / "jobs.db").exists()


# ---------------------------------------------------------------------------
# (2) execution off the main thread, with a working timeout
# ---------------------------------------------------------------------------

def test_wrapped_task_runs_off_the_main_thread(executor):
    executor.scheduler_engine.add_job(
        __import__("halbert_core.scheduler.job", fromlist=["Job"]).Job(
            id="bg", task="t", schedule="x"
        )
    )
    wrapped = executor._wrap_task("bg", lambda: "ran", max_retries=1, timeout_s=5)
    outcome = {}

    def worker():
        try:
            outcome["result"] = wrapped()
        except Exception as e:  # pragma: no cover - the failure we are testing for
            outcome["error"] = e

    t = threading.Thread(target=worker)
    t.start()
    t.join(10)
    assert "error" not in outcome, outcome.get("error")
    assert outcome["result"] == "ran"
    assert executor.scheduler_engine.get_job("bg").state == "completed"


def _run_wrapped(executor, job_id, task, *, occurrence_job_id=None, scheduled_instant_fn=None):
    from halbert_core.scheduler.job import Job

    executor.scheduler_engine.add_job(Job(id=job_id, task="t", schedule="x"))
    wrapped = executor._wrap_task(
        job_id, task, max_retries=1, timeout_s=5,
        occurrence_job_id=occurrence_job_id, scheduled_instant_fn=scheduled_instant_fn,
    )
    outcome = {}

    def worker():
        try:
            outcome["result"] = wrapped()
        except Exception as e:  # pragma: no cover
            outcome["error"] = e

    t = threading.Thread(target=worker)
    t.start()
    t.join(10)
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("result")


class TestOccurrenceIdempotency:
    """R-03 (A06-G1/A15-G1/G2): occurrence_completed exists and is now
    checked before dispatch and populated on completion -- previously the
    primitive existed with zero production callers."""

    def test_an_already_completed_occurrence_is_never_dispatched(self, executor):
        calls = []
        executor.receipts.completed_occurrence("morning_report", "2026-09-07T08:00:00+00:00")
        result = _run_wrapped(
            executor, "morning_report", lambda: calls.append(1) or "ran",
            scheduled_instant_fn=lambda: "2026-09-07T08:00:00+00:00",
        )
        assert calls == []
        assert result is None
        # Skipped before dispatch: the job record is untouched (still pending),
        # not marked completed for a run that never happened.
        assert executor.scheduler_engine.get_job("morning_report").state == "pending"

    def test_a_fresh_instant_runs_and_is_then_recorded_completed(self, executor):
        instant = "2026-09-07T08:00:00+00:00"
        result = _run_wrapped(
            executor, "morning_report", lambda: "ran",
            scheduled_instant_fn=lambda: instant,
        )
        assert result == "ran"
        assert executor.receipts.occurrence_completed("morning_report", instant) is True

    def test_no_instant_function_never_checks_or_records_an_occurrence(self, executor):
        """A job with no cadence to compute an instant from (or a one-time
        job with no scheduled_instant_fn at all) is unaffected — this is an
        additive check, not a new requirement on every caller."""
        result = _run_wrapped(executor, "adhoc", lambda: "ran")
        assert result == "ran"

    def test_occurrence_credits_a_different_id_than_the_execution_id(self, executor):
        """A catch-up run executes under 'morning_report:catchup' but must
        credit the PARENT job's occurrence — the same slot served by a
        regular fire, a catch-up, or a boot recovery must read as served
        either way (own-bug 1's other half: crediting a sibling id instead
        of the parent record)."""
        instant = "2026-09-07T08:00:00+00:00"
        result = _run_wrapped(
            executor, "morning_report:catchup", lambda: "caught up",
            occurrence_job_id="morning_report",
            scheduled_instant_fn=lambda: instant,
        )
        assert result == "caught up"
        assert executor.receipts.occurrence_completed("morning_report", instant) is True
        assert executor.receipts.occurrence_completed("morning_report:catchup", instant) is False


def _read_receipts_dict(executor):
    return {rid: dict(rec) for rid, rec in executor.receipts._receipts.items()}


class TestResultProtocolAndRejectionReceipts:
    """R-03 Phase B: own-bug 2 (a timeout retries a still-running task),
    own-bug 3 / A06-G8 (a task's own {'status': 'error'} return is recorded
    as a success), own-bug 5 (a guardrail rejection or safe-mode skip
    leaves no receipt at all)."""

    def test_a_task_returning_status_error_is_recorded_as_failed(self, executor):
        # A task-level {'status': 'error'} return is now a genuine failure,
        # the same as the task raising — the retry decorator sees it too
        # (max_retries=1 here means no retry budget left, so it propagates).
        with pytest.raises(RuntimeError, match="smtp unreachable"):
            _run_wrapped(
                executor, "morning_report",
                lambda: {"status": "error", "error": "smtp unreachable"},
            )
        job = executor.scheduler_engine.get_job("morning_report")
        assert job.state == "failed"
        assert "smtp unreachable" in (job.error or "")
        receipts = _read_receipts_dict(executor)
        assert any(r["job_id"] == "morning_report" and r["status"] == "error"
                  for r in receipts.values())

    def test_a_task_returning_status_ok_is_still_a_success(self, executor):
        result = _run_wrapped(
            executor, "morning_report", lambda: {"status": "ok", "event_id": "e1"},
        )
        assert result == {"status": "ok", "event_id": "e1"}
        assert executor.scheduler_engine.get_job("morning_report").state == "completed"

    def test_a_plain_non_dict_result_is_still_a_success(self, executor):
        # Most tasks return a plain string/None; the result-protocol check
        # is additive and must not demand every task adopt a dict shape.
        result = _run_wrapped(executor, "detector_sweep", lambda: "swept 3 issues")
        assert result == "swept 3 issues"
        assert executor.scheduler_engine.get_job("detector_sweep").state == "completed"

    def test_a_timeout_is_not_retried_while_the_worker_still_runs(self, executor):
        calls = []
        started = threading.Event()

        def slow():
            calls.append(1)
            started.set()
            time.sleep(2)
            return "too late"

        from halbert_core.scheduler.job import Job

        executor.scheduler_engine.add_job(Job(id="slow", task="t", schedule="x"))
        wrapped = executor._wrap_task("slow", slow, max_retries=3, timeout_s=0.2)
        # A timeout is handled (job marked failed, receipt closed) but not
        # re-raised into the retry decorator, which is exactly what stops
        # it from re-entering the task while the first attempt's worker
        # thread — a daemon thread nothing can actually stop — is still
        # alive underneath it.
        assert wrapped() is None
        assert started.wait(1)
        assert len(calls) == 1
        assert executor.scheduler_engine.get_job("slow").state == "failed"

    def test_safe_mode_skip_leaves_a_blocked_config_receipt(self, guarded_executor):
        executor = guarded_executor
        # In-memory only: GuardrailEnforcer.enter_safe_mode() writes a real
        # marker file at a cwd-relative path (a separate, pre-existing bug,
        # not this test's concern) that would leak across unrelated test
        # runs; setting the flag directly avoids that side effect.
        executor.guardrail_enforcer.safe_mode_active = True
        result = _run_wrapped(executor, "morning_report", lambda: "should not run")
        assert result is None
        receipts = _read_receipts_dict(executor)
        assert any(
            r["job_id"] == "morning_report" and r["status"] == "blocked_config"
            for r in receipts.values()
        )

    def test_guardrail_rejection_leaves_a_blocked_config_receipt(self, guarded_executor, monkeypatch):
        executor = guarded_executor
        from halbert_core.autonomy import GuardrailViolation

        def _reject(**kwargs):
            raise GuardrailViolation("budget exceeded")

        monkeypatch.setattr(executor.guardrail_enforcer, "check_all", _reject)
        result = _run_wrapped(executor, "morning_report", lambda: "should not run")
        assert result is None
        receipts = _read_receipts_dict(executor)
        assert any(
            r["job_id"] == "morning_report" and r["status"] == "blocked_config"
            for r in receipts.values()
        )


def test_one_time_job_runs_and_records_outcome(guarded_executor):
    executor = guarded_executor
    # The guardrail branch is the one with the undefined name; make sure it
    # is actually on rather than silently disabled by a config lookup miss.
    assert executor.enable_guardrails and executor.guardrail_enforcer is not None

    ran = threading.Event()

    def task():
        ran.set()
        return "sweep ok"

    executor.start()
    executor.schedule_one_time(
        job_id="soon",
        task_func=task,
        run_at=datetime.now(timezone.utc) + timedelta(seconds=0.3),
        max_retries=1,
        timeout_s=30,
    )
    assert ran.wait(10), "one-time job never ran"
    assert _wait_for(lambda: executor.scheduler_engine.get_job("soon").state == "completed")
    record = executor.scheduler_engine.get_job("soon")
    assert record.started_at and record.completed_at and record.error is None


def test_timeout_is_enforced_off_the_main_thread(executor):
    executor.start()
    executor.schedule_one_time(
        job_id="slow",
        task_func=lambda: time.sleep(5),
        run_at=datetime.now(timezone.utc) + timedelta(seconds=0.2),
        max_retries=1,
        timeout_s=1,
    )
    assert _wait_for(lambda: executor.scheduler_engine.get_job("slow").state == "failed", timeout_s=8)
    error = executor.scheduler_engine.get_job("slow").error or ""
    assert "timeout" in error.lower(), error


def test_failed_task_records_failure(executor):
    def boom():
        raise RuntimeError("disk on fire")

    executor.start()
    executor.schedule_one_time(
        job_id="bad",
        task_func=boom,
        run_at=datetime.now(timezone.utc) + timedelta(seconds=0.2),
        max_retries=1,
    )
    assert _wait_for(lambda: executor.scheduler_engine.get_job("bad").state == "failed")
    assert "disk on fire" in (executor.scheduler_engine.get_job("bad").error or "")


# ---------------------------------------------------------------------------
# dashboard registration: the two production jobs go through the same path
# ---------------------------------------------------------------------------

def test_dashboard_proactive_jobs_register(executor):
    pytest.importorskip("fastapi")
    from halbert_core.config.being_config import BeingConfig
    from halbert_core.dashboard import app as dashboard_app

    executor.start()
    outcome = dashboard_app.register_proactive_jobs(
        executor,
        load_config=lambda: BeingConfig(morning_report={"enabled": True, "time": "07:45"}),
    )
    assert outcome == {
        "detector_sweep": "scheduled",
        "morning_report": "scheduled",
        # CD-5's 90-day event-ledger retention. The exact-dict assertion is
        # the point: a job appearing here unannounced should fail this test.
        "timeline_retention": "scheduled",
    }
    scheduled = {j["id"]: j for j in executor.get_scheduled_jobs()}
    assert set(scheduled) == {
        "detector_sweep", "morning_report", "timeline_retention",
    }
    assert "hour='7'" in scheduled["morning_report"]["trigger"]
    assert "minute='45'" in scheduled["morning_report"]["trigger"]


def test_dashboard_proactive_jobs_default_config_schedules_the_report(executor):
    """C2-10: a fresh being.yml (all defaults) schedules the report at 08:00."""
    pytest.importorskip("fastapi")
    from halbert_core.config.being_config import BeingConfig
    from halbert_core.dashboard import app as dashboard_app

    executor.start()
    outcome = dashboard_app.register_proactive_jobs(executor, load_config=BeingConfig)
    assert outcome["morning_report"] == "scheduled"
    trigger = {j["id"]: j["trigger"] for j in executor.get_scheduled_jobs()}["morning_report"]
    assert "hour='8'" in trigger and "minute='0'" in trigger


def test_dashboard_proactive_jobs_disabled_report_is_skipped(executor):
    pytest.importorskip("fastapi")
    from halbert_core.config.being_config import BeingConfig
    from halbert_core.dashboard import app as dashboard_app

    executor.start()
    outcome = dashboard_app.register_proactive_jobs(
        executor, load_config=lambda: BeingConfig(morning_report={"enabled": False}),
    )
    assert outcome == {
        "detector_sweep": "scheduled",
        "morning_report": "disabled",
        "timeline_retention": "scheduled",
    }
    # Retention is not the report: turning the morning report off must not
    # stop the ledger being pruned.
    assert {j["id"] for j in executor.get_scheduled_jobs()} == {
        "detector_sweep", "timeline_retention",
    }


def test_dashboard_proactive_jobs_never_raise(executor):
    pytest.importorskip("fastapi")
    from halbert_core.dashboard import app as dashboard_app

    def broken():
        raise RuntimeError("being.yml unreadable")

    executor.start()
    outcome = dashboard_app.register_proactive_jobs(executor, load_config=broken)
    assert outcome["detector_sweep"] == "scheduled"
    assert outcome["morning_report"].startswith("error")
