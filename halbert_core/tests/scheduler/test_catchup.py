# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Catch-up policy for jobs whose slot passed while the machine was asleep.

Lifted from OpenClaw timer-catchup.ts + stagger.ts (bounded immediate
catch-up, staggered overflow, skip-with-advance, pacing clamp), then
upgraded by the Hermes addendum: the flat grace is replaced by
**cadence-scaled grace** — half the job's period, clamped [120s, 2h].
Within grace the missed slot is simply caught up (bounded, staggered);
beyond grace a recurring job is fast-forwarded (skip the whole backlog,
fire ONCE now, advance next_run_at at dispatch) and a one-shot is RETIRED
with a diagnostic file — never fired hours late.
"""
from datetime import datetime, timedelta

import pytest

from halbert_core.scheduler.catchup import (
    CatchupAction,
    clamp_proposed_delay,
    compute_grace_seconds,
    decide_catchup,
    write_retirement_diagnostic,
)

T0 = datetime(2026, 9, 7, 9, 0)


def _job(jid, due, period_s=None, one_shot=False):
    return {"id": jid, "due_at": due, "period_s": period_s, "one_shot": one_shot}


def test_grace_is_half_the_period_clamped():
    assert compute_grace_seconds(3600) == 1800  # half the period, in range
    assert compute_grace_seconds(60) == 120  # floored at 120s
    assert compute_grace_seconds(14 * 24 * 3600) == 7200  # capped at 2h


def test_missed_within_grace_run_immediately_bounded():
    # 4h cadence -> 2h grace: jobs 1h..5h late. First two are within grace
    # (caught up), the rest are beyond grace (fast-forwarded).
    jobs = [
        _job("j1", T0 - timedelta(hours=1), period_s=4 * 3600),
        _job("j2", T0 - timedelta(hours=2), period_s=4 * 3600),
        _job("j3", T0 - timedelta(hours=3), period_s=4 * 3600),
        _job("j4", T0 - timedelta(hours=4), period_s=4 * 3600),
    ]
    plan = decide_catchup(jobs, now=T0, max_immediate=2, stagger_s=30)
    assert [a.action for a in plan.actions[:2]] == [CatchupAction.RUN_NOW] * 2
    # beyond grace -> fast-forward, not a slot-by-slot replay of the backlog
    assert all(a.action is CatchupAction.FAST_FORWARD for a in plan.actions[2:])


def test_catchup_overflow_is_staggered():
    # 1h cadence -> 30min grace: 30s, 30min late are within grace; keep the
    # bounded/staggered shape by asking for a tiny immediate batch.
    jobs = [
        _job("j1", T0 - timedelta(minutes=29), period_s=3600),
        _job("j2", T0 - timedelta(minutes=30), period_s=3600),
    ]
    plan = decide_catchup(jobs, now=T0, max_immediate=1, stagger_s=30)
    assert plan.actions[0].action is CatchupAction.RUN_NOW
    assert len(plan.deferred) == 1
    assert plan.deferred[0].delay_s >= 30


def test_within_grace_not_missed_when_fresh():
    # Freshly overdue relative to a long grace: NOT_MISSED is for jobs whose
    # slot has not passed at all (or the scheduler's own misfire grace will
    # still fire) — a job due in the future is never a catch-up candidate.
    jobs = [_job("fresh", T0 + timedelta(seconds=30), period_s=3600)]
    plan = decide_catchup(jobs, now=T0, max_immediate=3, stagger_s=30)
    assert all(a.action is CatchupAction.NOT_MISSED for a in plan.actions)
    assert not plan.deferred


def test_beyond_grace_fast_forward_fires_once():
    # 6h cadence -> 1h grace; 5h late is far beyond grace: skip the backlog,
    # fire once now.
    jobs = [_job("old", T0 - timedelta(hours=5), period_s=6 * 3600)]
    plan = decide_catchup(jobs, now=T0)
    assert plan.actions[0].action is CatchupAction.FAST_FORWARD
    assert plan.actions[0].advance_to is not None


def test_one_shot_past_grace_is_retired_not_fired():
    jobs = [_job("old_once", T0 - timedelta(days=2), one_shot=True)]
    plan = decide_catchup(jobs, now=T0)
    assert plan.actions[0].action is CatchupAction.RETIRE


def test_one_shot_within_grace_still_runs():
    jobs = [_job("once_soon", T0 - timedelta(seconds=60), one_shot=True)]
    plan = decide_catchup(jobs, now=T0)
    assert plan.actions[0].action is CatchupAction.RUN_NOW


def test_skip_mode_advances_schedule():
    jobs = [_job("old", T0 - timedelta(days=2), period_s=6 * 3600)]
    plan = decide_catchup(jobs, now=T0, mode="skip")
    assert plan.actions[0].action is CatchupAction.ADVANCE_ONLY


def test_retirement_diagnostic_file(tmp_path):
    jobs = [_job("old_once", T0 - timedelta(days=2), one_shot=True)]
    plan = decide_catchup(jobs, now=T0)
    path = write_retirement_diagnostic(tmp_path, plan.actions[0])
    text = path.read_text(encoding="utf-8")
    assert "old_once" in text
    assert "retired" in text.lower()


def test_pacing_clamp():
    assert clamp_proposed_delay(2 * 3600, min_s=60, max_s=6 * 3600) == 2 * 3600
    assert clamp_proposed_delay(5, min_s=60, max_s=6 * 3600) == 60
    assert clamp_proposed_delay(99 * 3600, min_s=60, max_s=6 * 3600) == 6 * 3600