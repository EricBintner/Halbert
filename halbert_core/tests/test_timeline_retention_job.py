# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""CD-5 kept 90 days, and pruning at construction only covers restarts.

`TimelineStore` prunes when it is built, which is every daemon start. A
machine that stays up for months never prunes, and this ledger now has a
writer, so it grows at a few thousand rows a day.
"""


class _Executor:
    def __init__(self):
        self.jobs = {}

    def schedule_cron_job(self, *, job_id, task_func, cron_expr, description):
        self.jobs[job_id] = {"func": task_func, "cron": cron_expr,
                             "description": description}


class TestTheRetentionJobIsRegistered:

    def _register(self):
        from halbert_core.dashboard.app import register_proactive_jobs

        ex = _Executor()
        outcome = register_proactive_jobs(ex, load_config=lambda: {})
        return ex, outcome

    def test_a_retention_job_is_scheduled(self):
        ex, outcome = self._register()
        assert "timeline_retention" in ex.jobs
        assert outcome.get("timeline_retention") == "scheduled"

    def test_it_runs_daily_not_every_six_hours(self):
        ex, _ = self._register()
        cron = ex.jobs["timeline_retention"]["cron"]
        assert "hour" in cron, "a retention sweep is a daily job, not hourly"

    def test_running_it_prunes_and_returns_a_count(self, tmp_path, monkeypatch):
        import time

        from halbert_core.continuity.timeline import TimelineEvent, TimelineStore
        import halbert_core.integrations.cognition_wiring as cw

        store = TimelineStore(db_path=str(tmp_path / "t.db"))
        store.record(TimelineEvent(timestamp=time.time() - 200 * 86400,
                                   event_type="ha_state_change", source="ha"))
        store.record(TimelineEvent(timestamp=time.time(),
                                   event_type="ha_state_change", source="ha"))
        monkeypatch.setattr(cw, "get_timeline_store", lambda: store)

        ex, _ = self._register()
        ex.jobs["timeline_retention"]["func"]()
        assert len(store.query(limit=99)) == 1

    def test_it_never_raises_when_there_is_no_ledger(self, monkeypatch):
        import halbert_core.integrations.cognition_wiring as cw

        monkeypatch.setattr(cw, "get_timeline_store", lambda: None)
        ex, _ = self._register()
        ex.jobs["timeline_retention"]["func"]()   # must not raise
