#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P-07 — one-time job outcome recording is load-sensitive (observational).

The seam (collected empirically 2026-09-07): ``test_scheduler_executor.py::
test_one_time_job_runs_and_records_outcome`` failed twice during collection
(a solo run at 11s and the full-file run), then passed five times solo.
The job is scheduled 0.3s out on a started APScheduler with guardrails on
and asserts the task ran and the outcome record reached "completed" within
10s — timing-sensitive under load.

This probe drives the same path once and reports what it saw.  Flaky reds
are recorded, not chased: the fix, if one is wanted, is separate work.
"""

import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import bootstrap  # noqa: E402

bootstrap()

PROBE_ID = "P-07"


def _wait_for(predicate, timeout_s=10.0, step_s=0.05):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step_s)
    return predicate()


def main() -> int:
    import os
    import tempfile

    try:
        from halbert_core.scheduler.executor import AutonomousExecutor
    except ImportError as exc:
        print(f"PROBE {PROBE_ID} scheduler-one-time: OBSERVED -- apscheduler not importable: {exc}")
        return 0

    with tempfile.TemporaryDirectory() as td:
        os.environ["HALBERT_DATA_DIR"] = str(Path(td) / "data")
        ex = AutonomousExecutor(
            max_workers=2, enable_llm=False, enable_guardrails=True, timezone="UTC"
        )
        ran = threading.Event()

        def task():
            ran.set()
            return "sweep ok"

        try:
            ex.start()
            ex.schedule_one_time(
                job_id="soon",
                task_func=task,
                run_at=datetime.now(timezone.utc) + timedelta(seconds=0.3),
                max_retries=1,
                timeout_s=30,
            )
            ran_within = ran.wait(10)
            completed = _wait_for(lambda: (ex.scheduler_engine.get_job("soon") or type("J", (), {"state": None})()).state == "completed")
            record = ex.scheduler_engine.get_job("soon")
            state = record.state if record else "<no record>"
        finally:
            ex.stop(wait=False)

        print(
            f"PROBE {PROBE_ID} scheduler-one-time: OBSERVED -- task ran: {ran_within}; "
            f"outcome state: {state}; completed flag: {completed}"
        )
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"PROBE {PROBE_ID} scheduler-one-time: HARNESS-ERROR -- {exc!r}")
        raise SystemExit(3)