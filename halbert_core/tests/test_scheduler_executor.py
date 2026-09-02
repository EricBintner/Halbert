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
    assert outcome == {"detector_sweep": "scheduled", "morning_report": "scheduled"}
    scheduled = {j["id"]: j for j in executor.get_scheduled_jobs()}
    assert set(scheduled) == {"detector_sweep", "morning_report"}
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
    assert outcome == {"detector_sweep": "scheduled", "morning_report": "disabled"}
    assert {j["id"] for j in executor.get_scheduled_jobs()} == {"detector_sweep"}


def test_dashboard_proactive_jobs_never_raise(executor):
    pytest.importorskip("fastapi")
    from halbert_core.dashboard import app as dashboard_app

    def broken():
        raise RuntimeError("being.yml unreadable")

    executor.start()
    outcome = dashboard_app.register_proactive_jobs(executor, load_config=broken)
    assert outcome["detector_sweep"] == "scheduled"
    assert outcome["morning_report"].startswith("error")
