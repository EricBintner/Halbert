# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Packet 03 B2: boot catch-up for the registered proactive jobs.

At registration time, each cron job's last-due slot is computed from the
schedule (APScheduler 3.x has no get_prev_fire_time, so ``_last_due_slot``
walks forward) and checked against the previous boot's job record. Missed
slots go through ``decide_catchup`` (max_immediate=2, stagger 60s) and come
back as one-time runs on the existing ``schedule_one_time`` path:
``timeline_retention`` and ``detector_sweep`` are idempotent housekeeping so
always safe to serve, ``morning_report`` catches up only within 12h of its
slot (a stale morning report is noise), the monitor-hash gate suppresses a
``detector_sweep`` catch-up whose source is unchanged, and a satellite body
(the PeerConversationStore setups the idle tick already guards) never
catches up — the canonical host runs the proactive jobs.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("apscheduler")
pytest.importorskip("fastapi")

from halbert_core.dashboard import app as dashboard_app  # noqa: E402
from halbert_core.scheduler.job import Job  # noqa: E402
from halbert_core.scheduler.monitor_hash import MonitorHashGate  # noqa: E402
from halbert_core.scheduler.run_receipts import RunReceiptStore  # noqa: E402

T0 = datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)

CRONS = {
    "detector_sweep": {"hour": "*/6", "minute": 12},
    "timeline_retention": {"hour": 4, "minute": 37},
    "morning_report": {"hour": 8, "minute": 0},
}


class _FakeExecutor:
    """Records one-time catch-up scheduling; the catch-up path only needs
    ``schedule_one_time`` and the timezone name. ``receipts``, when given,
    is a real ``RunReceiptStore`` (or any object with ``occurrence_completed``)
    so a test can exercise the R-03 occurrence guard; the production
    executor always has one, but the guard is written to fail soft when it
    is absent, which is what a bare ``_FakeExecutor()`` exercises."""

    timezone = "UTC"

    def __init__(self, receipts=None):
        self.one_time = []
        if receipts is not None:
            self.receipts = receipts

    def schedule_one_time(self, *, job_id, task_func, run_at, **kwargs):
        self.one_time.append({"job_id": job_id, "task": task_func, "run_at": run_at, **kwargs})


def _spec(job_id, task=lambda: None, cron=None, one_shot=False):
    return {"task": task, "cron_expr": dict(cron or CRONS[job_id]), "one_shot": one_shot}


def _prior(job_id, *, ran_at=None, never_ran=False, cron=None, state="completed",
           **job_kwargs):
    # Defaults to the SAME schedule this boot registers (CRONS[job_id]):
    # "nothing about the schedule changed, only time passed" is the common
    # case every test but the schedule-change ones itself wants. Pass
    # `cron=` to simulate a prior boot's now-superseded schedule. Defaults
    # to state="completed": "the last run genuinely succeeded" is the
    # common case every test but the failed-slot ones itself wants (A15-G8).
    schedule = str(cron if cron is not None else CRONS.get(job_id, {}))
    job = Job(id=job_id, task="t", schedule=schedule, state=state, **job_kwargs)
    if never_ran:
        return job
    job.completed_at = (
        ran_at or (T0 - timedelta(days=2))
    ).isoformat()
    return job


def _run(ex, specs, prior, *, now=T0, gate="unset", probe=None):
    kwargs = {"now": now, "probe": probe}
    kwargs["gate"] = None if gate == "unset" else gate
    return dashboard_app._run_boot_catchup(ex, specs, prior, **kwargs)


def _ungated(tmp_path):
    """A gate whose named set is empty: nothing is suppressed, the probe is
    never consulted."""
    return MonitorHashGate(tmp_path / "monitor_hashes.json", jobs=frozenset())


# ---------------------------------------------------------------------------
# missed slots come back as one-time runs on the existing path
# ---------------------------------------------------------------------------

def test_timeline_retention_missed_five_hours_ago_is_scheduled_now(tmp_path):
    """The packet's gate test: a retention slot that passed while the
    machine was off is served as a one-time immediate run at boot."""
    ex = _FakeExecutor()
    specs = {"timeline_retention": _spec("timeline_retention")}
    prior = {"timeline_retention": _prior("timeline_retention")}

    result = _run(ex, specs, prior, gate=_ungated(tmp_path))

    assert result == {"timeline_retention": "caught_up"}
    (run,) = ex.one_time
    assert run["job_id"] == "timeline_retention:catchup"
    # Beyond grace the recurring job is fast-forwarded: fire ONCE now, no
    # backlog replay — run_at is the boot instant, not the missed slot.
    assert run["run_at"] == T0


def test_within_grace_slot_catches_up_immediately(tmp_path):
    """detector_sweep's 06:12 slot vs a 07:00 boot is 48 minutes old —
    inside the cadence-scaled grace, so a plain RUN_NOW."""
    ex = _FakeExecutor()
    specs = {"detector_sweep": _spec("detector_sweep")}
    prior = {"detector_sweep": _prior("detector_sweep")}
    boot = datetime(2026, 9, 7, 7, 0, tzinfo=timezone.utc)

    result = _run(ex, specs, prior, now=boot, gate=_ungated(tmp_path))

    assert result == {"detector_sweep": "caught_up"}
    assert ex.one_time[0]["run_at"] == boot


def test_morning_report_catches_up_only_within_twelve_hours(tmp_path):
    within = _FakeExecutor()
    specs = {"morning_report": _spec("morning_report")}
    prior = {"morning_report": _prior("morning_report")}
    # Slot 08:00, boot 15:00 — seven hours stale, within the 12h bound.
    result = _run(within, specs, prior, gate=_ungated(tmp_path))
    assert result == {"morning_report": "caught_up"}
    assert within.one_time[0]["job_id"] == "morning_report:catchup"

    # Slot 08:00, boot 21:00 — thirteen hours stale: a stale morning report
    # is noise, so the slot is skipped, not served.
    stale = _FakeExecutor()
    result = _run(
        stale, specs, prior, now=datetime(2026, 9, 7, 21, 0, tzinfo=timezone.utc),
        gate=_ungated(tmp_path),
    )
    assert result == {"morning_report": "stale_skipped"}
    assert stale.one_time == []


# ---------------------------------------------------------------------------
# A15-G4/A06-G10: a schedule edit re-anchors without firing -- a slot that
# only exists because the cron expression changed since the last boot is
# not a missed run.
# ---------------------------------------------------------------------------

def test_an_edited_schedule_does_not_catch_up_its_new_slot(tmp_path):
    # Last boot ran detector_sweep on a completely different cadence
    # (once a day at 20:00); this boot edits it to */6h. The 06:12 slot
    # this boot's schedule implies "missed" never existed under the old
    # schedule -- it must re-anchor silently, not fire a catch-up.
    ex = _FakeExecutor()
    specs = {"detector_sweep": _spec("detector_sweep")}  # this boot: */6h
    prior = {"detector_sweep": _prior("detector_sweep", cron={"hour": 20, "minute": 0})}

    result = _run(ex, specs, prior, gate=_ungated(tmp_path))

    assert result.get("detector_sweep") != "caught_up"
    assert ex.one_time == []


def test_an_unchanged_schedule_still_catches_up(tmp_path):
    # The common case, pinned against a regression in the guard itself:
    # no edit at all still catches up exactly as before.
    ex = _FakeExecutor()
    specs = {"detector_sweep": _spec("detector_sweep")}
    prior = {"detector_sweep": _prior("detector_sweep")}  # same schedule by default

    result = _run(ex, specs, prior, gate=_ungated(tmp_path))

    assert result == {"detector_sweep": "caught_up"}


def test_a_prior_record_with_no_schedule_at_all_still_catches_up(tmp_path):
    # A record from before this field was populated (or any other reason
    # it is blank) must fail soft to "assume unchanged", not "assume
    # edited" -- the guard is a refinement, not a new way to lose catch-up.
    ex = _FakeExecutor()
    specs = {"detector_sweep": _spec("detector_sweep")}
    prior = {"detector_sweep": _prior("detector_sweep", never_ran=True)}
    prior["detector_sweep"].schedule = ""

    result = _run(ex, specs, prior, gate=_ungated(tmp_path))

    assert result == {"detector_sweep": "caught_up"}


# ---------------------------------------------------------------------------
# A15-G3: a job already armed by boot receipt-recovery is not double-armed
# by boot catch-up too (the audit's own proposed _boot_recovery_pending
# guard is broken -- executor.py drains that set during registration,
# before catch-up ever runs, so checking it here would always see it empty;
# _boot_recovery_armed is a separate, boot-scoped set that is only ever
# added to, never drained, during the same boot).
# ---------------------------------------------------------------------------

def test_a_job_already_armed_by_boot_recovery_is_not_double_armed(tmp_path):
    ex = _FakeExecutor()
    ex._boot_recovery_armed = {"detector_sweep"}
    specs = {
        "detector_sweep": _spec("detector_sweep"),
        "timeline_retention": _spec("timeline_retention"),
    }
    prior = {
        "detector_sweep": _prior("detector_sweep"),
        "timeline_retention": _prior("timeline_retention"),
    }

    result = _run(ex, specs, prior, gate=_ungated(tmp_path))

    assert result.get("detector_sweep") != "caught_up"
    assert not any(r["job_id"].startswith("detector_sweep") for r in ex.one_time)
    # the guard is job-specific, not a blanket suppression of the whole run
    assert result.get("timeline_retention") == "caught_up"
    assert any(r["job_id"].startswith("timeline_retention") for r in ex.one_time)


def test_the_guard_is_absent_when_no_boot_recovery_armed_anything(tmp_path):
    # A bare _FakeExecutor (no _boot_recovery_armed attribute at all) must
    # not be treated as "everything is guarded" -- fail soft to "nothing
    # is guarded", the same way the occurrence-store check already does.
    ex = _FakeExecutor()
    specs = {"detector_sweep": _spec("detector_sweep")}
    prior = {"detector_sweep": _prior("detector_sweep")}
    boot = datetime(2026, 9, 7, 7, 0, tzinfo=timezone.utc)

    result = _run(ex, specs, prior, now=boot, gate=_ungated(tmp_path))

    assert result == {"detector_sweep": "caught_up"}


def test_idempotent_housekeeping_has_no_age_bound(tmp_path):
    """detector_sweep missed by most of a day still catches up — it is
    idempotent, so a served slot can never hurt."""
    ex = _FakeExecutor()
    specs = {"detector_sweep": _spec("detector_sweep")}
    prior = {"detector_sweep": _prior("detector_sweep")}
    # Last slot 06:12, boot 23:00 — nearly 17 hours late.
    result = _run(
        ex, specs, prior, now=datetime(2026, 9, 7, 23, 0, tzinfo=timezone.utc),
        gate=_ungated(tmp_path),
    )
    assert result == {"detector_sweep": "caught_up"}
    assert ex.one_time[0]["job_id"] == "detector_sweep:catchup"


# ---------------------------------------------------------------------------
# nothing was actually missed
# ---------------------------------------------------------------------------

def test_slot_already_served_is_not_caught_up(tmp_path):
    ex = _FakeExecutor()
    specs = {"timeline_retention": _spec("timeline_retention")}
    # Last run an hour ago — after today's 04:37 slot: the slot was served.
    prior = {
        "timeline_retention": _prior(
            "timeline_retention", ran_at=T0 - timedelta(hours=1)
        )
    }
    assert _run(ex, specs, prior, gate=_ungated(tmp_path)) == {}
    assert ex.one_time == []


# ---------------------------------------------------------------------------
# A15-G8: a failed run is not "served" -- back off briefly (a transient
# failure should not spin into an immediate retry loop), then replay.
# Scenario: morning_report's 08:00 run fails because the findings store
# was locked; the user restarts 20 minutes later; the old logic saw
# completed_at >= due and skipped, silently, forever -- no report that day.
# ---------------------------------------------------------------------------

def test_a_failed_run_still_catches_up_after_its_backoff_window(tmp_path):
    ex = _FakeExecutor()
    specs = {"morning_report": _spec("morning_report")}
    # 08:00 slot ran (and failed) at 08:01; boot is 21 minutes later --
    # morning_report's backoff is min(period/2, 15min) = 15min, elapsed.
    prior = {
        "morning_report": _prior(
            "morning_report",
            ran_at=datetime(2026, 9, 7, 8, 1, tzinfo=timezone.utc),
            state="failed",
        )
    }
    boot = datetime(2026, 9, 7, 8, 22, tzinfo=timezone.utc)

    result = _run(ex, specs, prior, now=boot, gate=_ungated(tmp_path))

    assert result == {"morning_report": "caught_up"}
    assert ex.one_time[0]["job_id"] == "morning_report:catchup"


def test_a_failed_run_still_backs_off_within_its_window(tmp_path):
    ex = _FakeExecutor()
    specs = {"morning_report": _spec("morning_report")}
    # Same failure, but the restart happens only 5 minutes later -- still
    # inside the 15-minute backoff, so no immediate replay yet.
    prior = {
        "morning_report": _prior(
            "morning_report",
            ran_at=datetime(2026, 9, 7, 8, 1, tzinfo=timezone.utc),
            state="failed",
        )
    }
    boot = datetime(2026, 9, 7, 8, 6, tzinfo=timezone.utc)

    result = _run(ex, specs, prior, now=boot, gate=_ungated(tmp_path))

    assert result.get("morning_report") != "caught_up"
    assert ex.one_time == []


def test_a_completed_run_is_served_forever_unlike_a_failed_one(tmp_path):
    # Regression guard: only 'failed' gets the backoff/expiry treatment. A
    # genuinely completed run stays served long past any backoff window --
    # the exact boot timing that replays a 'failed' slot above must NOT
    # replay a 'completed' one.
    ex = _FakeExecutor()
    specs = {"morning_report": _spec("morning_report")}
    prior = {
        "morning_report": _prior(
            "morning_report",
            ran_at=datetime(2026, 9, 7, 8, 1, tzinfo=timezone.utc),
            state="completed",
        )
    }
    boot = datetime(2026, 9, 7, 8, 22, tzinfo=timezone.utc)  # same timing as the replay test

    result = _run(ex, specs, prior, now=boot, gate=_ungated(tmp_path))

    assert result.get("morning_report") != "caught_up"
    assert ex.one_time == []


def test_occurrence_already_completed_overrides_a_blanked_job_record(tmp_path):
    """R-03 (A06-G1/A15-G1/G2, own-bug 1's other half): the occurrence store
    is authoritative even when the parent job record was blanked by a
    re-registration — e.g. a slot served by an earlier catch-up run, which
    credits the PARENT's occurrence rather than its own sibling id."""
    ex = _FakeExecutor(receipts=RunReceiptStore(tmp_path / "receipts.json"))
    due = datetime(2026, 9, 7, 4, 37, tzinfo=timezone.utc)
    ex.receipts.completed_occurrence("timeline_retention", due.isoformat())
    specs = {"timeline_retention": _spec("timeline_retention")}
    # never_ran: the job record itself has no last-run facts at all, which
    # would normally look like an unmissed... i.e. missed, unserved slot.
    prior = {"timeline_retention": _prior("timeline_retention", never_ran=True)}

    result = _run(ex, specs, prior, gate=_ungated(tmp_path))

    assert result == {}
    assert ex.one_time == []


def test_catchup_credits_the_parent_occurrence_for_the_missed_slot(tmp_path):
    """The scheduled run must record the ORIGINAL missed slot (due_at)
    against the PARENT id — not "now" (run_at) and not the ':catchup'
    sibling id — or the next boot's occurrence check could never match it."""
    ex = _FakeExecutor(receipts=RunReceiptStore(tmp_path / "receipts.json"))
    specs = {"timeline_retention": _spec("timeline_retention")}
    prior = {"timeline_retention": _prior("timeline_retention")}

    result = _run(ex, specs, prior, gate=_ungated(tmp_path))

    assert result == {"timeline_retention": "caught_up"}
    (run,) = ex.one_time
    assert run["job_id"] == "timeline_retention:catchup"
    assert run["occurrence_job_id"] == "timeline_retention"
    assert run["scheduled_instant"] == datetime(2026, 9, 7, 4, 37, tzinfo=timezone.utc).isoformat()
    assert run["scheduled_instant"] != run["run_at"].isoformat()


def test_fresh_install_catches_up_nothing(tmp_path):
    """No prior job record means the cron was never registered before —
    there is no missed slot to serve, only a first one coming."""
    ex = _FakeExecutor()
    specs = {
        "detector_sweep": _spec("detector_sweep"),
        "timeline_retention": _spec("timeline_retention"),
        "morning_report": _spec("morning_report"),
    }
    assert _run(ex, specs, {}, gate=_ungated(tmp_path)) == {}
    assert ex.one_time == []


def test_registered_but_never_ran_still_catches_up(tmp_path):
    """A prior record with no timestamps: the job was registered in a
    previous boot and its slot passed unserved."""
    ex = _FakeExecutor()
    specs = {"timeline_retention": _spec("timeline_retention")}
    prior = {"timeline_retention": _prior("timeline_retention", never_ran=True)}
    result = _run(ex, specs, prior, gate=_ungated(tmp_path))
    assert result == {"timeline_retention": "caught_up"}


# ---------------------------------------------------------------------------
# shape: max_immediate=2 with a 60s stagger on the overflow
# ---------------------------------------------------------------------------

def test_overflow_is_staggered_sixty_seconds(tmp_path):
    ex = _FakeExecutor()
    fast = {"minute": "*/15"}  # every job's last slot is minutes old
    specs = {
        jid: _spec(jid, cron=fast)
        for jid in ("detector_sweep", "timeline_retention", "morning_report")
    }
    prior = {jid: _prior(jid, cron=fast) for jid in specs}
    boot = datetime(2026, 9, 7, 9, 7, tzinfo=timezone.utc)

    result = _run(ex, specs, prior, now=boot, gate=_ungated(tmp_path))

    scheduled = {r["job_id"]: r["run_at"] for r in ex.one_time}
    assert len(scheduled) == 3
    immediate = [jid for jid, at in scheduled.items() if at == boot]
    deferred = {jid: at for jid, at in scheduled.items() if at != boot}
    assert len(immediate) == 2
    assert len(deferred) == 1
    assert list(deferred.values())[0] == boot + timedelta(seconds=60)
    tags = sorted(result.values())
    assert tags == ["caught_up", "caught_up", "caught_up_deferred"]


# ---------------------------------------------------------------------------
# the monitor-hash gate: named job set only (detector_sweep)
# ---------------------------------------------------------------------------

def test_monitor_hash_gate_suppresses_an_unchanged_detector_sweep(tmp_path):
    ex = _FakeExecutor()
    specs = {"detector_sweep": _spec("detector_sweep")}
    prior = {"detector_sweep": _prior("detector_sweep")}
    gate = MonitorHashGate(tmp_path / "monitor_hashes.json")  # names detector_sweep
    probes = []

    def probe():
        return probes.pop(0)

    # First evaluation: baseline established, catch-up suppressed.
    probes.append((True, "state-A"))
    assert _run(ex, specs, prior, gate=gate, probe=probe) == {}
    assert ex.one_time == []

    # Source unchanged: the catch-up run is suppressed entirely.
    probes.append((True, "state-A"))
    assert _run(ex, specs, prior, gate=gate, probe=probe) == {}
    assert ex.one_time == []

    # Source changed: the catch-up runs.
    probes.append((True, "state-B"))
    result = _run(ex, specs, prior, gate=gate, probe=probe)
    assert result == {"detector_sweep": "caught_up"}
    assert ex.one_time[0]["job_id"] == "detector_sweep:catchup"


def test_monitor_source_error_runs_the_catchup_anyway(tmp_path):
    """A probe failure is an error, never a 'change' — and never a reason
    to silently skip a check-on-X job."""
    ex = _FakeExecutor()
    specs = {"detector_sweep": _spec("detector_sweep")}
    prior = {"detector_sweep": _prior("detector_sweep")}
    gate = MonitorHashGate(tmp_path / "monitor_hashes.json")

    result = _run(ex, specs, prior, gate=gate, probe=lambda: (False, "probe broke"))
    assert result == {"detector_sweep": "caught_up"}
    assert ex.one_time[0]["job_id"] == "detector_sweep:catchup"


def test_morning_report_is_never_gate_suppressed(tmp_path):
    """The named set is the whole policy: a job not in it must run even
    with an unchanged 'source' — the gate is never even consulted."""
    ex = _FakeExecutor()
    specs = {"morning_report": _spec("morning_report")}
    prior = {"morning_report": _prior("morning_report")}
    gate = MonitorHashGate(tmp_path / "monitor_hashes.json")  # names detector_sweep
    probed = []

    def probe():
        probed.append(True)
        return (True, "unchanged")

    result = _run(ex, specs, prior, gate=gate, probe=probe)
    assert result == {"morning_report": "caught_up"}
    assert not probed, "the gate evaluated a job that is not in its named set"
    assert ex.one_time[0]["job_id"] == "morning_report:catchup"


def test_default_gate_lives_in_the_scheduler_data_dir(tmp_path, monkeypatch):
    """gate=None constructs the real store under the scheduler data dir —
    and the real probe's first observation is a baseline (suppressed)."""
    data = tmp_path / "data"
    monkeypatch.setenv("HALBERT_DATA_DIR", str(data))
    ex = _FakeExecutor()
    specs = {"detector_sweep": _spec("detector_sweep")}
    prior = {"detector_sweep": _prior("detector_sweep")}

    result = _run(ex, specs, prior)  # gate defaults

    assert result == {}
    assert ex.one_time == []
    store = data / "scheduler" / "monitor_hashes.json"
    assert store.exists()
    hashes = json.loads(store.read_text(encoding="utf-8"))["hashes"]
    assert "detector_sweep" in hashes


# ---------------------------------------------------------------------------
# the satellite guard, as the idle tick guards
# ---------------------------------------------------------------------------

def test_a_satellite_body_never_catches_up(tmp_path, monkeypatch):
    import halbert_core.integrations.cognition_wiring as cw

    monkeypatch.setattr(
        cw, "_get_canonical_thread_url", lambda: "http://canonical-host:8123"
    )
    ex = _FakeExecutor()
    specs = {"timeline_retention": _spec("timeline_retention")}
    prior = {"timeline_retention": _prior("timeline_retention")}
    assert _run(ex, specs, prior, gate=_ungated(tmp_path)) == {}
    assert ex.one_time == []


# ---------------------------------------------------------------------------
# the production path: registration serves what it missed
# ---------------------------------------------------------------------------

def test_register_proactive_jobs_catches_up_a_missed_retention_slot(tmp_path, monkeypatch):
    """Integration through the real registration path: a previous boot's
    record shows the retention job last ran two days ago, so this boot
    serves the missed slot as a one-time run (scheduled in the future so
    the test never actually prunes anyone's ledger)."""
    from halbert_core.config.being_config import BeingConfig
    from halbert_core.scheduler.executor import AutonomousExecutor

    data = tmp_path / "data"
    monkeypatch.setenv("HALBERT_DATA_DIR", str(data))

    def make_executor():
        return AutonomousExecutor(
            max_workers=2, enable_llm=False, enable_guardrails=False,
            timezone="UTC",
        )

    # The previous boot: retention ran two days ago.
    previous = make_executor()
    previous.scheduler_engine.add_job(
        Job(
            id="timeline_retention",
            task="_prune_timeline",
            # The real cron_expr string register_proactive_jobs registers
            # below, unchanged since this "previous boot" — the A15-G4
            # schedule-change guard must not mistake a matching schedule
            # for an edited one.
            schedule=str({"hour": 4, "minute": 37}),
            state="completed",
            completed_at=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        )
    )

    ex = make_executor()
    ex.start()
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    outcome = dashboard_app.register_proactive_jobs(
        ex,
        load_config=lambda: BeingConfig(
            morning_report={"enabled": True, "time": "07:45"}
        ),
        catchup_now=future,
    )
    assert outcome == {
        "detector_sweep": "scheduled",
        "morning_report": "scheduled",
        "timeline_retention": "scheduled",
    }
    assert "timeline_retention:catchup" in {
        j["id"] for j in ex.get_scheduled_jobs()
    }
    ex.stop(wait=False)


def test_register_proactive_jobs_on_a_fresh_install_serves_nothing(tmp_path, monkeypatch):
    from halbert_core.config.being_config import BeingConfig
    from halbert_core.scheduler.executor import AutonomousExecutor

    data = tmp_path / "data"
    monkeypatch.setenv("HALBERT_DATA_DIR", str(data))
    ex = AutonomousExecutor(
        max_workers=2, enable_llm=False, enable_guardrails=False, timezone="UTC",
    )
    ex.start()
    outcome = dashboard_app.register_proactive_jobs(
        ex, load_config=lambda: BeingConfig(morning_report={"enabled": False}),
    )
    assert outcome["morning_report"] == "disabled"
    assert {j["id"] for j in ex.get_scheduled_jobs()} == {
        "detector_sweep", "timeline_retention",
    }
    ex.stop(wait=False)


# ---------------------------------------------------------------------------
# A15-G9: RETIRE (beyond grace, one-shot) writes its diagnostic instead of
# silently discarding the job. No production proactive job is one-shot
# today (one_shot defaults to False, unchanged) -- this proves the branch
# does the right thing on the day something routes a one-shot spec through
# this same catch-up path, instead of it being dead code that LOOKS wired.
# ---------------------------------------------------------------------------

def test_a_retired_one_shot_job_writes_a_diagnostic_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    ex = _FakeExecutor()
    specs = {"detector_sweep": _spec("detector_sweep", one_shot=True)}
    # Two days late, one-shot: ONE_SHOT_GRACE_S (120s) is long past.
    prior = {"detector_sweep": _prior("detector_sweep")}
    boot = datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc)

    result = _run(ex, specs, prior, now=boot, gate=_ungated(tmp_path))

    assert result.get("detector_sweep") == "retired"
    assert ex.one_time == []
    diagnostics = list((tmp_path / "data" / "scheduler").glob("*retire*"))
    assert diagnostics, "no retirement diagnostic file was written"
    assert "detector_sweep" in diagnostics[0].read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A06-G7: the monitor gate suppressed only a boot catch-up replay before
# this fix -- the REGULAR cron fire ran detector_sweep every cadence
# regardless of whether its probed source had changed at all.
# ---------------------------------------------------------------------------

def test_the_regular_fire_is_suppressed_when_the_source_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    calls = []
    gated = dashboard_app._gate_regular_fire(
        "detector_sweep", lambda: calls.append(1), probe=lambda: (True, "same output"),
    )

    first = gated()   # baseline established
    second = gated()  # unchanged since baseline

    assert calls == []
    assert first == {"status": "suppressed", "reason": "monitor_source_unchanged"}
    assert second == {"status": "suppressed", "reason": "monitor_source_unchanged"}


def test_the_regular_fire_runs_when_the_source_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    calls = []
    probes = iter(["v1", "v2"])
    gated = dashboard_app._gate_regular_fire(
        "detector_sweep", lambda: calls.append(1) or "ran",
        probe=lambda: (True, next(probes)),
    )

    gated()          # baseline
    result = gated()  # changed -> runs

    assert calls == [1]
    assert result == "ran"


def test_the_regular_fire_runs_when_the_gate_is_unavailable(tmp_path, monkeypatch):
    # A directory HALBERT_DATA_DIR cannot create (e.g. a file sits where
    # the dir should be) must fail open to running the task, never silently
    # never-run it.
    blocked = tmp_path / "not_a_dir"
    blocked.write_text("x")
    monkeypatch.setenv("HALBERT_DATA_DIR", str(blocked))
    calls = []
    gated = dashboard_app._gate_regular_fire(
        "detector_sweep", lambda: calls.append(1) or "ran", probe=lambda: (True, "v"),
    )

    result = gated()

    assert calls == [1]
    assert result == "ran"


def test_register_proactive_jobs_wires_the_regular_fire_through_the_gate(tmp_path, monkeypatch):
    # register_proactive_jobs must pass a GATED task_func to
    # schedule_cron_job for detector_sweep's regular fire, distinct from
    # the unwrapped one it keeps for catch-up's own already-gated path.
    from halbert_core.config.being_config import BeingConfig

    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(dashboard_app, "_detector_sweep_probe", lambda: (True, "unchanged"))

    scheduled = {}

    class _RecordingExecutor(_FakeExecutor):
        timezone = "UTC"

        def schedule_cron_job(self, *, job_id, task_func, **kwargs):
            scheduled[job_id] = task_func

    ex = _RecordingExecutor()
    dashboard_app.register_proactive_jobs(
        ex, load_config=lambda: BeingConfig(morning_report={"enabled": False}),
    )

    sweep_task_func = scheduled["detector_sweep"]
    first = sweep_task_func()   # baseline established
    second = sweep_task_func()  # unchanged since baseline
    assert first == {"status": "suppressed", "reason": "monitor_source_unchanged"}
    assert second == {"status": "suppressed", "reason": "monitor_source_unchanged"}