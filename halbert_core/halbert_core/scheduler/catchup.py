# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Bounded catch-up for missed scheduler slots (packet 03 A1, Hermes addendum).

A machine that slept through a cron window should neither flood the agent
with every missed job at once nor silently drop them. Per job:

* grace is **cadence-scaled** — half the job's period, clamped [120s, 2h]
  (Hermes ``_compute_grace_seconds``) — replacing the base packet's flat
  60s grace, which was tuned to APScheduler's ``misfire_grace_time`` and
  nothing else.
* within grace: the missed slot is simply **caught up** — run now, bounded
  by ``max_immediate`` with a stagger on the overflow (OpenClaw
  timer-catchup/stagger pattern).
* beyond grace, recurring job: **fast-forward** — skip the whole backlog,
  fire ONCE now, and persist the recomputed ``next_run_at`` at dispatch
  time, before execution (the dispatcher recomputes the true next slot;
  this module only marks the decision with ``advance_to``). Closes the
  crash window and the "runtime > interval -> skipped forever" loop.
* beyond grace, one-shot: **retired with a diagnostic file**, never fired
  hours late.

``clamp_proposed_delay`` is the pacing hook: the agent may PROPOSE its
next delay; configuration clamps it (OpenClaw pacing.ts).

Pure policy: no I/O here except the explicit retirement-diagnostic writer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

# Hermes clamp: grace in [120s, 2h] regardless of cadence.
GRACE_MIN_S = 120.0
GRACE_MAX_S = 7200.0

# Grace for jobs that declare neither a period nor one-shot-ness.
DEFAULT_GRACE_S = 120.0

# Grace before a one-shot is retired instead of fired late.
ONE_SHOT_GRACE_S = 120.0


class CatchupAction(Enum):
    RUN_NOW = "run_now"  # catch up a slot missed within grace
    NOT_MISSED = "not_missed"  # slot has not passed; the normal schedule owns it
    ADVANCE_ONLY = "advance_only"  # mode='skip': advance the schedule, never fire
    FAST_FORWARD = "fast_forward"  # beyond grace, recurring: fire once now, advance
    RETIRE = "retire"  # beyond grace, one-shot: never fire, write a diagnostic


@dataclass(frozen=True)
class CatchupEntry:
    job: dict
    action: CatchupAction
    delay_s: float = 0.0
    # FAST_FORWARD only: the instant from which the dispatcher recomputes the
    # next slot and persists next_run_at BEFORE executing (Hermes dispatch-time
    # persistence under the lock).
    advance_to: Optional[datetime] = None
    # RETIRE only: why the one-shot was not fired.
    reason: str = ""


@dataclass(frozen=True)
class CatchupPlan:
    actions: tuple = ()
    deferred: tuple = ()  # CatchupEntry with delay_s set, in run order


def compute_grace_seconds(
    period_s: float, *, min_s: float = GRACE_MIN_S, max_s: float = GRACE_MAX_S
) -> float:
    """Cadence-scaled grace: half the period, clamped [120s, 2h]."""
    return max(min_s, min(max_s, float(period_s) / 2.0))


def clamp_proposed_delay(proposed_s: float, min_s: float, max_s: float) -> float:
    """The agent proposes its next-run delay; configuration clamps it."""
    return max(min_s, min(max_s, proposed_s))


def _grace_for(job: dict, grace_s: Optional[float], one_shot_grace_s: float) -> float:
    if grace_s is not None:  # explicit override beats cadence scaling
        return float(grace_s)
    if job.get("one_shot"):
        return one_shot_grace_s
    period_s = job.get("period_s")
    if period_s and period_s > 0:
        return compute_grace_seconds(period_s)
    return DEFAULT_GRACE_S


def decide_catchup(
    jobs,
    now: datetime,
    *,
    grace_s: Optional[float] = None,
    one_shot_grace_s: float = ONE_SHOT_GRACE_S,
    max_immediate: int = 3,
    stagger_s: float = 30.0,
    mode: str = "run",
) -> CatchupPlan:
    """Decide what to do with jobs whose due slot passed before ``now``.

    ``jobs`` is an iterable of dicts with ``id`` and ``due_at`` (a datetime,
    the last missed slot), plus optionally ``period_s`` (recurring cadence,
    seconds) and ``one_shot`` (bool). ``grace_s`` overrides cadence scaling
    for every job (the base packet's flat grace; prefer leaving it None).

    Actions in the plan: RUN_NOW entries (bounded by ``max_immediate``) come
    first, then FAST_FORWARD (one fire now, advance next_run_at at dispatch),
    then RETIRE, then NOT_MISSED. Deferred catch-up overflow lives in
    ``plan.deferred`` with its stagger delays, in run order.
    """
    if mode not in ("run", "skip"):
        raise ValueError(f"unknown catchup mode: {mode!r}")

    catchup: List[dict] = []  # overdue, within grace
    advanced: List[CatchupEntry] = []  # beyond grace, or skip-mode everything
    not_missed: List[dict] = []  # slot has not passed

    for job in jobs:
        overdue_s = (now - job["due_at"]).total_seconds()
        if overdue_s <= 0:
            not_missed.append(job)
            continue
        if mode == "skip":
            advanced.append(CatchupEntry(job, CatchupAction.ADVANCE_ONLY))
            continue
        if overdue_s > _grace_for(job, grace_s, one_shot_grace_s):
            if job.get("one_shot"):
                advanced.append(
                    CatchupEntry(
                        job,
                        CatchupAction.RETIRE,
                        reason=(
                            f"one-shot {job['id']!r} missed its slot at "
                            f"{job['due_at'].isoformat()} by more than its grace "
                            f"({one_shot_grace_s}s); retired, not fired late"
                        ),
                    )
                )
            else:
                advanced.append(
                    CatchupEntry(job, CatchupAction.FAST_FORWARD, advance_to=now)
                )
        else:
            catchup.append(job)

    if mode == "skip":
        return CatchupPlan(
            actions=tuple(advanced)
            + tuple(CatchupEntry(j, CatchupAction.NOT_MISSED) for j in not_missed)
        )

    catchup.sort(key=lambda j: j["due_at"], reverse=True)  # newest first
    immediate = [CatchupEntry(j, CatchupAction.RUN_NOW) for j in catchup[:max_immediate]]
    deferred: Tuple[CatchupEntry, ...] = tuple(
        CatchupEntry(j, CatchupAction.RUN_NOW, delay_s=(i + 1) * stagger_s)
        for i, j in enumerate(catchup[max_immediate:])
    )
    return CatchupPlan(
        actions=tuple(immediate) + tuple(advanced)
        + tuple(CatchupEntry(j, CatchupAction.NOT_MISSED) for j in not_missed),
        deferred=deferred,
    )


def write_retirement_diagnostic(directory, entry: CatchupEntry) -> Path:
    """Persist a small diagnostic file for a retired one-shot.

    The job is deliberately NOT fired late; this file is the record of why,
    so a human (or the morning report) can see the one-shot was dropped.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"retired-{entry.job['id']}.json"
    payload = {
        "retired": True,
        "job_id": entry.job["id"],
        "due_at": entry.job["due_at"].isoformat(),
        "reason": entry.reason,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path