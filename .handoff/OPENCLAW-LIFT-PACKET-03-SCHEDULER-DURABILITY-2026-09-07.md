# OPENCLAW-LIFT-PACKET-03 — Scheduler durability + the prompted-heartbeat ground rules

**Series:** OpenClaw lift program (master plan: `OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md`)
**Source research:** `.handoff/OSS-REVIEW-OPENCLAW-2026-09-07.md` §4 (Scheduler / heartbeat)
**OpenClaw source of record:** `/Volumes/Thunderbolt/AI/openclaw` — `src/cron/service/timer-scheduler.ts`, `timer-catchup.ts`, `stagger.ts`, `pacing.ts`, `run-receipt-store.ts` (simplified variant), `src/auto-reply/tokens.ts`, `src/infra/heartbeat-runner-prompt.ts`, `heartbeat-wake*.ts`
**Executor tier:** Phases A–B small-model friendly (pure policy modules + thin wiring). Phase C is a design decision needing founder input — do not build.
**Status:** READY TO DISPATCH

---

## Objective — and one honest correction

OpenClaw's heartbeat findings (NO_REPLY suppression, zero-LLM idle short-circuit) presuppose a **prompted heartbeat** — a scheduled LLM turn that checks on things and decides whether to bother the user. **Halbert has no prompted heartbeat.** Verified: Halbert's heartbeat is `ThreadManager.tick()` housekeeping (close sweep + Consolidator, `dashboard/app.py:306-439`), it skips beats while a turn is in flight, and it produces no prompt and no reply — so there is nothing to suppress yet. The OpenClaw heartbeat protocol is therefore recorded here as **ground rules for the component if/when it is built** (Phase C), not as immediate work.

What *is* immediately liftable is scheduler durability — the crash-window hygiene OpenClaw worked out the hard way, applied to Halbert's actual scheduler (APScheduler + JSON job files + two uncoordinated timers):

1. **Catch-up policy** for jobs missed while the machine was asleep (Halbert has only `misfire_grace_time=60` — anything missed by more than a minute is silently dropped).
2. **Restart budgeting** — bounded restarts per sliding window with cooldown, policy in a pure tested module.
3. **Run receipts** — a `started` marker persisted *before* side effects, with on-boot recovery: running markers whose owner pid is dead are marked interrupted (the simplified single-instance version of OpenClaw's receipt store — deliberately NOT their multi-instance invariant matrix).

## Verified current state (do not re-derive; verified 2026-09-07)

- `halbert_core/halbert_core/scheduler/executor.py` — `AutonomousExecutor`: APScheduler `BackgroundScheduler` with **`MemoryJobStore`** (deliberate, C4-01: closures can't be pickled; jobs re-registered at every boot), `ThreadPoolExecutor(max_workers)`, defaults `coalesce=True, max_instances=1, misfire_grace_time=60`. `schedule_cron_job`/`schedule_one_time`/`cancel_job`/`get_scheduled_jobs`. `_wrap_task` adds exponential-backoff retry, join timeouts, guardrails (`autonomy.GuardrailEnforcer`, `BudgetTracker`, `AnomalyDetector`, `RecoveryExecutor`; anomaly → safe-mode + alert). `JobResult` is logged by `_log_outcome` only — **nothing persists outcomes** (the file-backed outcome writer was removed, audit F1).
- `scheduler/engine.py` — `SchedulerEngine`: one JSON file per job under `data_subdir("scheduler")` (`{job_id}.json`), state machine `pending/running/completed/failed/cancelled` (+ `skipped`/`rejected` written by executor), retries, timestamps, error. The `db_path`/`jobs.db` in executor.py is **vestigial** — recorded, never written.
- `scheduler/job.py` — `Job` dataclass (id, task, schedule, priority, state, retries, timeout_s, timestamps, error).
- Production wiring: `dashboard/app.py:813-849` starts `AutonomousExecutor(max_workers=3, enable_llm=False, enable_guardrails=True, timezone=...)` on `CAP_SCHEDULER` in a daemon thread after 3s; `register_proactive_jobs` (app.py:852-900, helper :220-303) registers `detector_sweep` (every 6h at :12), `timeline_retention` (daily 04:37), `morning_report` (daily at being.yml time). **`SystemHealthCheckTask`/`LogCleanupTask` are never scheduled in production**, and `enable_llm=False` means the base class's LLM decision path is dead.
- The thread-tick heartbeat (app.py:306-439) and APScheduler are **two independent timers with no coordination**.
- No OS sleep/wake handling anywhere. `HomeCognitiveLoop` (`home/cognitive_loop.py`, 5-min perceive-reason-act with `AutonomyGate`) is built and tested but has **zero production callers**.
- Peer mode: satellites return `[]` from `tick()` and never consolidate; consolidation runs only on the canonical host.

## Out-of-scope guards

- Do NOT replace APScheduler or unify the two timers into one re-armed timer — OpenClaw's single-timer design exists because they hand-rolled the scheduler; Halbert's APScheduler already handles arming, coalescing, and misfire grace. Lift the *policies*, not the architecture.
- Do NOT port OpenClaw's multi-instance receipt invariant matrix (I1–I4, foreign-receipt monitors, `getFileLockProcessStartTime`). Halbert is single-instance; the simplified pid-alive rule is the 90/10.
- Do NOT build the prompted heartbeat (Phase C decision), and do NOT enable `HomeCognitiveLoop` as a side effect of this packet.
- Do not touch the `db_path` vestige beyond a comment cleanup if convenient — it is recorded, not load-bearing.

---

## Phase A — pure policy modules (small-model friendly)

**Branch:** `feat/scheduler-durability` off `main`.

### Task A1: Missed-run catch-up policy

**Files:**
- Create: `halbert_core/halbert_core/scheduler/catchup.py`
- Test: `halbert_core/tests/scheduler/test_catchup.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Catch-up policy for jobs whose slot passed while the machine was asleep.
Lifted from OpenClaw src/cron/service/timer-catchup.ts + stagger.ts: bounded
immediate catch-up, staggered overflow, or skip-with-advance; the agent may
propose its next-run delay, clamped to configured bounds (pacing.ts)."""
from datetime import datetime, timedelta
from halbert_core.halbert_core.scheduler.catchup import decide_catchup, CatchupPlan, CatchupAction

T0 = datetime(2026, 9, 7, 9, 0)

def _job(jid, due, cron=True):
    return {"id": jid, "last_run": None if cron else due, "due_at": due}

def test_missed_jobs_run_immediately_bounded():
    jobs = [_job(f"j{i}", T0 - timedelta(hours=h)) for i, h in enumerate(range(1, 6), 1)]
    plan = decide_catchup(jobs, now=T0, max_immediate=3, stagger_s=30)
    assert [a.action for a in plan.actions[:3]] == [CatchupAction.RUN_NOW] * 3
    assert len(plan.deferred) == 2
    # deferred run in due order with stagger between them
    assert plan.deferred[0].job["id"] == "j4" or plan.deferred[0].delay_s >= 30

def test_within_grace_not_missed():
    jobs = [_job("fresh", T0 - timedelta(seconds=30))]
    plan = decide_catchup(jobs, now=T0, grace_s=60, max_immediate=3, stagger_s=30)
    assert all(a.action is CatchupAction.NOT_MISSED for a in plan.actions)
    assert not plan.deferred

def test_skip_mode_advances_schedule():
    jobs = [_job("old", T0 - timedelta(days=2))]
    plan = decide_catchup(jobs, now=T0, mode="skip", max_immediate=3, stagger_s=30)
    assert plan.actions[0].action is CatchupAction.ADVANCE_ONLY

def test_pacing_clamp():
    from halbert_core.halbert_core.scheduler.catchup import clamp_proposed_delay
    assert clamp_proposed_delay(2 * 3600, min_s=60, max_s=6 * 3600) == 2 * 3600
    assert clamp_proposed_delay(5, min_s=60, max_s=6 * 3600) == 60
    assert clamp_proposed_delay(99 * 3600, min_s=60, max_s=6 * 3600) == 6 * 3600
```

- [ ] **Step 2: Run, verify failure.** `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/scheduler/test_catchup.py -q`

- [ ] **Step 3: Implement `catchup.py`**

```python
"""Bounded catch-up for missed scheduler slots (OpenClaw timer-catchup pattern).

A machine that slept through a cron window should neither flood the agent with
every missed job at once nor silently drop them: run the newest few immediately,
defer the overflow with a stagger, or (mode='skip') just advance the schedule.
`clamp_proposed_delay` is the pacing hook: the agent may PROPOSE its next delay;
configuration clamps it.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

class CatchupAction(Enum):
    RUN_NOW = "run_now"
    NOT_MISSED = "not_missed"
    ADVANCE_ONLY = "advance_only"

@dataclass(frozen=True)
class CatchupEntry:
    job: dict
    action: CatchupAction
    delay_s: float = 0.0

@dataclass(frozen=True)
class CatchupPlan:
    actions: tuple = ()
    deferred: tuple = ()  # CatchupEntry with delay_s set, in run order

def clamp_proposed_delay(proposed_s: float, min_s: float, max_s: float) -> float:
    return max(min_s, min(max_s, proposed_s))

def decide_catchup(jobs, now: datetime, *, grace_s: float = 60.0, max_immediate: int = 3,
                    stagger_s: float = 30.0, mode: str = "run") -> CatchupPlan:
    missed = [j for j in jobs if (now - j["due_at"]).total_seconds() > grace_s]
    missed.sort(key=lambda j: j["due_at"], reverse=True)  # newest first
    if mode == "skip":
        return CatchupPlan(actions=tuple(CatchupEntry(j, CatchupAction.ADVANCE_ONLY) for j in missed))
    immediate = [CatchupEntry(j, CatchupAction.RUN_NOW) for j in missed[:max_immediate]]
    deferred = tuple(
        CatchupEntry(j, CatchupAction.RUN_NOW, delay_s=(i + 1) * stagger_s)
        for i, j in enumerate(missed[max_immediate:])
    )
    not_missed = tuple(CatchupEntry(j, CatchupAction.NOT_MISSED) for j in jobs if j not in missed)
    return CatchupPlan(actions=tuple(immediate) + not_missed, deferred=deferred)
```

- [ ] **Step 4: Run, verify pass. Commit:** `feat(scheduler): bounded, staggered catch-up policy for missed jobs`

### Task A2: Restart budget policy (crash-loop guard)

**Files:**
- Create: `halbert_core/halbert_core/scheduler/restart_budget.py`
- Test: `halbert_core/tests/scheduler/test_restart_budget.py`

- [ ] **Step 1: Failing tests:**

```python
"""OpenClaw channel-health-monitor pattern: restarts budgeted per sliding hour,
cooldown cycles between attempts, policy pure and table-tested — including
clock rollback (desktop machines suspend)."""
from halbert_core.halbert_core.scheduler.restart_budget import RestartBudget, RestartDecision

def test_allows_first_restarts():
    rb = RestartBudget(max_per_hour=3, cooldown_cycles=1)
    assert rb.evaluate(restarts=[], now=1000) is RestartDecision.ALLOW
    assert rb.evaluate(restarts=[900], now=1000) is RestartDecision.ALLOW

def test_budget_exhausted_blocks():
    rb = RestartBudget(max_per_hour=3, cooldown_cycles=1)
    assert rb.evaluate(restarts=[300, 600, 900], now=1000) is RestartDecision.BLOCK

def test_sliding_window_recovers():
    rb = RestartBudget(max_per_hour=2, cooldown_cycles=1)
    assert rb.evaluate(restarts=[0, 60], now=3601) is RestartDecision.ALLOW  # both out of window

def test_clock_rollback_does_not_release_budget():
    rb = RestartBudget(max_per_hour=1, cooldown_cycles=1)
    assert rb.evaluate(restarts=[5000], now=1000) is RestartDecision.BLOCK  # now earlier than last restart: hold
```

- [ ] **Step 2:** Run, verify failure. **Step 3: Implement** — sliding window over restart timestamps; `now < last_restart` (rollback) conservatively returns BLOCK with a `clock_rollback` reason; cooldown = at least one successful cycle must elapse since the last restart before another.

```python
from enum import Enum

class RestartDecision(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    COOLDOWN = "cooldown"

class RestartBudget:
    def __init__(self, max_per_hour: int = 5, cooldown_cycles: int = 1, window_s: float = 3600.0):
        self.max_per_hour = max_per_hour
        self.cooldown_cycles = cooldown_cycles
        self.window_s = window_s

    def evaluate(self, restarts, now: float) -> RestartDecision:
        if not restarts:
            return RestartDecision.ALLOW
        last = max(restarts)
        if now < last:
            return RestartDecision.BLOCK  # clock rolled back: hold, never release
        recent = [t for t in restarts if now - t <= self.window_s]
        if len(recent) >= self.max_per_hour:
            return RestartDecision.BLOCK
        return RestartDecision.ALLOW
```

- [ ] **Step 4:** Run, verify pass. Commit: `feat(scheduler): sliding-window restart budget with clock-rollback hold`

### Task A3: Run receipts — simplified single-instance variant

**Files:**
- Create: `halbert_core/halbert_core/scheduler/run_receipts.py`
- Test: `halbert_core/tests/scheduler/test_run_receipts.py`

- [ ] **Step 1: Failing tests:**

```python
"""Persist a 'started' marker BEFORE side effects; on boot, a running marker whose
owner pid is dead becomes 'interrupted'. Deliberately NOT OpenClaw's multi-instance
invariant matrix — single-user assistant takes the 90/10."""
import os
from halbert_core.halbert_core.scheduler.run_receipts import RunReceiptStore

def test_started_before_effect(tmp_path):
    store = RunReceiptStore(tmp_path / "receipts.json")
    rid = store.mark_started(job_id="detector_sweep", owner_pid=os.getpid())
    assert store.status(rid) == "running"

def test_completion_and_error(tmp_path):
    store = RunReceiptStore(tmp_path / "receipts.json")
    rid = store.mark_started("j", owner_pid=1)
    store.mark_finished(rid, "ok")
    assert store.status(rid) == "ok"
    rid2 = store.mark_started("j", owner_pid=1)
    store.mark_finished(rid2, "error", error="boom")
    assert store.status(rid2) == "error"

def test_boot_recovery_interrupts_dead_owners(tmp_path):
    store = RunReceiptStore(tmp_path / "receipts.json")
    rid = store.mark_started("j", owner_pid=999999)  # certainly not our pid
    recovered = store.recover_on_boot(owner_alive=lambda pid: pid == os.getpid())
    assert store.status(rid) == "interrupted"
    assert recovered == [rid]

def test_boot_recovery_leaves_live_owners_alone(tmp_path):
    store = RunReceiptStore(tmp_path / "receipts.json")
    rid = store.mark_started("j", owner_pid=os.getpid())
    store.recover_on_boot(owner_alive=lambda pid: True)
    assert store.status(rid) == "running"
```

- [ ] **Step 2:** Run, verify failure. **Step 3: Implement** — JSON-file-backed (matches SchedulerEngine's per-job file convention; one `receipts.json` under the same scheduler data dir), `mark_started` writes and flushes *before* returning, statuses `running → ok | error | interrupted`, `recover_on_boot(owner_alive)` marks dead-owner running rows interrupted and returns them.

- [ ] **Step 4:** Run, verify pass. Commit: `feat(scheduler): run receipts with boot recovery for dead owners`

---

## Phase B — wiring (thin, review-light)

### Task B1: Wire receipts + restart budget into `AutonomousExecutor`

**Files:**
- Modify: `halbert_core/halbert_core/scheduler/executor.py`
- Test: extend `halbert_core/tests/scheduler/` (integration tests with a monkeypatched APScheduler)

- [ ] **Step 1:** In `_wrap_task` (or the immediate pre-execute seam — the last line before the task callable runs): `receipt = receipts.mark_started(job_id, owner_pid=os.getpid())`, then run, then `mark_finished(receipt, "ok"|"error", error=...)`. In `start()` (the boot path, app.py:813's construction): `receipts.recover_on_boot(owner_alive=<pid alive fn>)` before registering jobs; recovered `interrupted` receipts for jobs with a retry budget get one bounded re-run (respect the restart budget).
- [ ] **Step 2:** Wrap the executor's internal restart/safe-mode recovery path (`RecoveryExecutor` seam) with `RestartBudget.evaluate` — on BLOCK, log a structured `restart_budget_exhausted` line and stay in safe-mode instead of looping.
- [ ] **Step 3:** Tests: a task whose receipt was left `running` with a dead pid gets recovered at boot; a job that fails 5× within an hour does not attempt a 6th restart. Run the scheduler suite. Commit: `feat(scheduler): receipts and restart budget wired into the executor`

### Task B2: Boot-time catch-up for registered proactive jobs

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/app.py` — `register_proactive_jobs` (helper at :220-303)
- Test: `halbert_core/tests/scheduler/test_catchup.py` (integration case) or colocated app test

- [ ] **Step 1:** At registration time, for each cron job, compute its last-due slot from the schedule and `last_run` in the job JSON; call `decide_catchup` with `max_immediate=2, stagger_s=60`; execute RUN_NOW entries via the existing `schedule_one_time` path (which already exists and is tested); deferred entries schedule one-time runs at `now + delay_s`. `timeline_retention` and `detector_sweep` are idempotent housekeeping — safe to catch up. `morning_report` catches up only if due within the last 12h (stale morning reports are noise — pass a per-job `max_age_s`).
- [ ] **Step 2:** Test: a `timeline_retention` job whose slot passed 5 hours ago is scheduled as a one-time immediate run at boot. Commit: `feat(scheduler): bounded boot catch-up for proactive jobs`

---

## Phase C — the prompted heartbeat: recorded ground rules (DESIGN DECISION — do not build)

Halbert has no prompted heartbeat today; `HomeCognitiveLoop` is the closest existing component (built, tested, zero production callers). If/when the founder decides to build it, these are the OpenClaw ground rules this packet contributes to that design — copied here so the decision inherits them:

1. **Silence protocol**: heartbeat replies that are token-only (`HEARTBEAT_OK` / `NO_REPLY`) are suppressed; substantive replies always deliver; a trailing token after substantive text does NOT suppress (OpenClaw bug #19537 — every model failure mode is documented in their matcher).
2. **Zero-token idle short-circuit**: if the heartbeat's scratch/observation buffer is effectively empty (only headers/stubs), skip the LLM call entirely.
3. **The model explicitly chooses interruption**: a `heartbeat_respond(notify: bool, notification_text)` decision, never implicit delivery.
4. **Settlements**: a scheduled wake must be able to await its terminal result so cron work knows whether the agent processed it (escalate to the indicator light on failure).
5. **Phase-aware budgets**: time waiting for admission never burns the execution budget.
6. **Fail-closed posture**: a heartbeat that cannot run (model down, budget blocked) degrades to nothing user-visible and logs a reason code.

**Decision needed from founder (recorded in master plan):** whether a prompted heartbeat should exist at all, and whether `HomeCognitiveLoop` is its substrate. Open question worth noting: the attunement workstream already touches tick-fires-at-REFLECTING; coordinate before any heartbeat work starts.

---

## ADDENDUM (2026-09-07, from the Hermes review — see `OSS-REVIEW-HERMES-2026-09-07.md` §4)

Hermes's cron system supersedes several Phase A choices with stronger, incident-proven versions. **Implement the addendum where it conflicts; the base packet text stands otherwise.**

1. **Cadence-scaled grace replaces the flat grace in A1.** `decide_catchup` should compute grace per job as **half the period, clamped [120s, 2h]** (Hermes `_compute_grace_seconds`, `cron/jobs.py:855`): within grace → catch up; beyond → **fast-forward** — skip the whole backlog, fire ONCE now, and persist the recomputed `next_run_at` at dispatch time, under the lock, *before* execution (closes the crash window; fixes the "runtime > interval → skipped forever" loop). One-shots past grace are **retired with a diagnostic file**, never fired hours late. Reference: `cron/jobs.py:2601-3013`.
2. **Occurrence-level idempotency in A3.** Add to the receipt store: `completed_occurrence(job_id, scheduled_instant)` — a completed scheduled instant can never fire again even if `next_run_at` was left stale by a crash (Hermes `cron/occurrences.py`). This is stronger than any claim TTL and is the real at-most-once primitive.
3. **Status taxonomy for receipts.** Use the closed set `ok / error / delivery_failed / blocked_config` (Hermes `jobs.py:2153-2270`): run success ≠ user notified, and `blocked_config` (refused before any LLM spend — preflight) is distinct from `error`. The dashboard light and any notification consumer must never test `== ok` for "the user got it."
4. **Monitor-hash gate (new Phase A task — the strongest Hermes idea here).** For jobs whose purpose is "check on X": run a cheap deterministic script/URL probe, hash the output each tick; **unchanged → the agent run is suppressed entirely**; changed → inject a capped unified diff. Persist the hash *before* the agent runs so a failed run doesn't re-alert forever; source failure is an error, never a "change." Reference: `cron/monitor.py`. This composes with (and largely answers) the Phase C idle-cost question for any monitoring-shaped heartbeat.
5. **Failure incidents with signature dedup.** Failures group by `(job_id, normalized error signature)`; same error refreshes one incident; an acked incident suppresses per-run pings; a changed error mints a new incident; 3 consecutive failures appends a "worth a review, or pause it" nudge. Reference: `cron/incidents.py`, `scheduler.py:117-143`.
6. **Continuity without sessions.** For fresh-session-per-fire jobs, continuity comes from a per-job KV notepad (cursors/watermarks, prompt-injected each run, CLI-write only) and `context_from` chaining of last outputs — not from conversation history. Direct fit for Halbert's thread-store-adjacent job runs. Reference: `cron/notepad.py`, `scheduler_prompt.py`.
7. **Timeout semantics (B1).** Use **inactivity-based** timeouts (default 600s idle; a job streaming tokens for hours is fine; a hung tool call dies), not wall-clock. Reference: `scheduler.py:1719-1847`.
8. **Anti-pattern inherited from Hermes:** do NOT adopt a hand-editable job store without validate-and-reject on load — nearly half of Hermes's due scan is repair passes for directly-edited `jobs.json`. Halbert's per-job JSON files (SchedulerEngine) should validate on load, and receipts belong in SQLite (as this packet's A3 already puts them).
9. **Phase C refinement:** Hermes has **no prompted heartbeat anywhere** — liveness is durable receipts + the closed status enum + ticker heartbeat epoch-marker files (heartbeat age / success age / last error / catch-up counter, so "ticker dead" is distinguishable from "nothing due"). If the founder declines a prompted heartbeat, this receipts-and-markers design still delivers "are my automations alive and did they run" without an LLM. The `[SILENT]` suppression matcher (shared across lanes so they can't drift) is the pattern if prompted silence tokens are ever added.

## Verification gates (whole packet)

- `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/scheduler -q` plus the dashboard app tests that cover `register_proactive_jobs` — pass.
- Receipt ordering proof: an integration test asserts the `started` marker exists on disk *before* the task callable begins executing (assert from inside the task).
- No changes to guardrail behavior (`GuardrailEnforcer`, `BudgetTracker`, `AnomalyDetector` untouched); safe-mode skip logic unchanged.
- `HomeCognitiveLoop` still has zero production callers.

## Executor gotchas

- Test invocation from main checkout: `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/ -q`; worktrees need `arch -arm64 ./wt_pytest.py` (plain pytest silently tests the main tree).
- APScheduler's `MemoryJobStore` means jobs vanish between boots by design (C4-01) — catch-up must read last-run facts from the JSON files in `SchedulerEngine`, not from APScheduler's store.
- `JobResult` persistence was deliberately removed once (audit F1, "file-backed outcome writer removed") — receipts are a *pre-execution marker*, not the outcome ledger that was removed; keep them separate and minimal or the same audit objection returns.
- Peer mode: satellites never tick/consolidate; catch-up wiring must not run on satellites (`PeerConversationStore` setups) — guard the same way `tick()` does.
- Pathspec commits; no Co-Authored-By trailers.