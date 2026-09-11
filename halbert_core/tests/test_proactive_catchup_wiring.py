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

T0 = datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)

CRONS = {
    "detector_sweep": {"hour": "*/6", "minute": 12},
    "timeline_retention": {"hour": 4, "minute": 37},
    "morning_report": {"hour": 8, "minute": 0},
}


class _FakeExecutor:
    """Records one-time catch-up scheduling; the catch-up path only needs
    ``schedule_one_time`` and the timezone name."""

    timezone = "UTC"

    def __init__(self):
        self.one_time = []

    def schedule_one_time(self, *, job_id, task_func, run_at, **kwargs):
        self.one_time.append({"job_id": job_id, "task": task_func, "run_at": run_at})


def _spec(job_id, task=lambda: None, cron=None):
    return {"task": task, "cron_expr": dict(cron or CRONS[job_id])}


def _prior(job_id, *, ran_at=None, never_ran=False, **job_kwargs):
    job = Job(id=job_id, task="t", schedule="cron", **job_kwargs)
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
    prior = {jid: _prior(jid) for jid in specs}
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
            schedule="cron",
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
        "attunement_sweep": "scheduled",
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
        "attunement_sweep", "detector_sweep", "timeline_retention",
    }
    ex.stop(wait=False)