# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The suppression log has a caller (A-HB-25, plan §4.6 stage 1).

`SuppressionRecorder` and `ProactiveGate(recorder=...)` both existed and
nothing in production ever put them together, so the log that makes "why
did I not hear about this?" answerable was writing no rows at all — and
Phase C's outcome ledger, which is the same table, had nothing to learn
from.

These tests pin the wiring at each of the three places a gate is really
built, and pin that a log which cannot start does not take the proactive
path with it.
"""

import pytest

from halbert_core.attunement.shadow import SuppressionRecorder, default_recorder


def test_the_detector_sweep_builds_a_gate_that_records(monkeypatch, tmp_path):
    from halbert_core.attunement.store import AttunementStore
    import halbert_core.proactive.detector_runner as runner_mod

    made = []

    def _recorder(being_config=None, *, store=None):
        store = AttunementStore(db_path=str(tmp_path / "attunement.db"))
        rec = SuppressionRecorder(store=store)
        made.append(rec)
        return rec

    monkeypatch.setattr(runner_mod, "default_recorder", _recorder)
    runner = runner_mod.DetectorRunner(
        finding_store=_FakeFindingStore(),
        proposal_store=object(),
    )

    assert runner.gate.recorder is made[0]


def test_the_morning_report_builds_a_gate_that_records(monkeypatch):
    import halbert_core.attunement.shadow as shadow_mod
    from halbert_core.proactive.morning_report import MorningReportGenerator

    sentinel = SuppressionRecorder(store=None)
    monkeypatch.setattr(
        shadow_mod, "default_recorder", lambda *a, **kw: sentinel
    )

    gate = MorningReportGenerator(
        finding_store=_FakeFindingStore(), proposal_store=object()
    )._default_gate()

    assert gate is not None
    assert gate.recorder is sentinel


def test_a_log_that_cannot_start_returns_none_rather_than_raising(monkeypatch):
    """A proactive path that failed to start because its *log* failed to
    start would be the log making things worse."""
    import halbert_core.attunement.store as store_mod

    def _explode(*a, **kw):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(store_mod, "AttunementStore", _explode)
    assert default_recorder(None) is None


def test_the_default_recorder_carries_a_shadow(tmp_path):
    from halbert_core.attunement.store import AttunementStore

    rec = default_recorder(
        None, store=AttunementStore(db_path=str(tmp_path / "a.db"))
    )

    assert rec is not None
    assert rec.decider is not None


class _FakeFindingStore:
    """Enough of FindingStore for DetectorRunner's constructor."""

    def list_findings(self, *a, **kw):
        return []

    def get(self, *a, **kw):
        return None


def test_the_ignored_sweep_is_actually_scheduled(monkeypatch):
    """IGNORED is the arm nothing notifies us about, so if the sweep is not
    on the scheduler it never happens — the same trap the recorder itself
    was in."""
    import halbert_core.dashboard.app as dashboard_app

    scheduled = {}

    class _Executor:
        scheduler_engine = None

        def schedule_cron_job(self, *, job_id, task_func, cron_expr, description):
            scheduled[job_id] = (task_func, cron_expr)

    outcome = dashboard_app.register_proactive_jobs(
        _Executor(), load_config=lambda: None
    )

    assert outcome.get("attunement_sweep") == "scheduled"
    assert "attunement_sweep" in scheduled


def test_the_sweep_job_labels_and_trims(monkeypatch):
    import halbert_core.attunement.reactions as reactions
    import halbert_core.dashboard.app as dashboard_app

    calls = []

    class _Store:
        def trim_outcomes(self):
            calls.append("trim")
            return 7

    class _Recorder:
        store = _Store()

        def sweep_ignored(self):
            calls.append("sweep")
            return 2

    monkeypatch.setattr(reactions, "default_reactions", lambda: _Recorder())

    scheduled = {}

    class _Executor:
        scheduler_engine = None

        def schedule_cron_job(self, *, job_id, task_func, cron_expr, description):
            scheduled[job_id] = task_func

    dashboard_app.register_proactive_jobs(_Executor(), load_config=lambda: None)
    scheduled["attunement_sweep"]()

    assert calls == ["sweep", "trim"]
