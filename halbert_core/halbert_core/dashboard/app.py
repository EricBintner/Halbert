# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
FastAPI dashboard application.

Provides REST API + WebSocket for Halbert dashboard.
"""

from __future__ import annotations
import asyncio
import logging
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

logger = logging.getLogger('halbert.dashboard')

# Phase 23: Global scheduler executor reference
_scheduler_executor = None

# Phase 5+7: Global ConfigWatcher reference (T5a.2 + T7e.1)
_config_watcher = None

# Frigate MQTT subscriber + event mapper (global for shutdown)
_frigate_mqtt_subscriber = None
_frigate_event_mapper = None

# Phase 4: Wyoming voice agent (global for shutdown)
_wyoming_agent = None


def _parse_hhmm(value) -> tuple:
    """Parse an 'HH:MM' string into (hour, minute). Raises ValueError if malformed."""
    if not isinstance(value, str):
        raise ValueError(f"morning_report.time must be a string, got {type(value).__name__}")
    hh, sep, mm = value.partition(":")
    if not sep:
        raise ValueError(f"morning_report.time must be 'HH:MM', got {value!r}")
    hour, minute = int(hh), int(mm)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"morning_report.time out of range: {value!r}")
    return hour, minute


def _find_config_registry():
    """The config registry for this body. See config.manifest.find_registry."""
    from ..config.manifest import find_registry

    return find_registry()


#: Client-side routes served with index.html (W3-S09). Explicit rather than
#: a catch-all so a mistyped API URL still 404s instead of returning the
#: shell. Every ``<Route path=...>`` in frontend/src/App.tsx must appear
#: here or it is a 404 as a deep link under the systemd deployment — which
#: is how the kiosk's ``/voice`` served nothing. tests/test_spa_routes.py
#: keeps the two in step. "/" is served by its own handler.
SPA_ROUTES = (
    "/dashboard",
    "/terminal",
    "/bodies",
    "/services",
    "/storage",
    "/gpu",
    "/containers",
    "/development",
    "/network",
    "/sharing",
    "/findings",
    "/security",
    "/backups",
    "/apps",
    "/approvals",
    "/settings",
    "/home",
    "/voice",
    "/voice-hud",
    "/frigate",
)

_NO_STORE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def mount_frontend(app: FastAPI, frontend_dist: Path) -> None:
    """Serve the built React app from ``frontend_dist``.

    Static assets, the self-hosted fonts, the brand logo, "/" and every
    path in ``SPA_ROUTES`` (all of which get index.html so the client
    router can take over). Split out of ``create_app`` so the route table
    is testable against a throwaway dist directory.
    """
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    # The self-hosted brand typefaces. This mount is load-bearing: the SPA
    # route table is explicit rather than a catch-all, so without it
    # /fonts/fonts.css 404s and the whole triad silently falls back to
    # system faces in the packaged app — which is the one place a CDN is
    # not available to paper over it.
    fonts_dir = frontend_dist / "fonts"
    if fonts_dir.exists():
        app.mount("/fonts", StaticFiles(directory=fonts_dir), name="fonts")
    else:
        logger.warning(
            "frontend/dist/fonts is missing - run scripts/sync_fonts.py before "
            "building the frontend, or the app will render without its typefaces"
        )

    index_html = frontend_dist / "index.html"

    @app.get("/Halbert.png")
    async def serve_logo():
        """Serve brand logo."""
        return FileResponse(frontend_dist / "Halbert.png")

    @app.get("/")
    async def serve_frontend():
        """Serve React app."""
        return FileResponse(index_html, headers=_NO_STORE)

    async def serve_spa():
        """Serve React app for frontend routes."""
        return FileResponse(index_html, headers=_NO_STORE)

    for path in SPA_ROUTES:
        app.get(path, include_in_schema=False)(serve_spa)


def run_conversation_boot_hooks() -> dict:
    """Plan A boot hooks for the one continuous conversation (spec §8, §12).

    1. Migrate the two legacy JSON conversation stores into the SQLite
       thread store as closed threads (idempotent, counts successful saves).
    2. Mark every message row still ``in_progress`` from a previous process
       as ``interrupted`` so the timeline can render "(Halbert restarted here)".

    Runs synchronously at startup, before the background starters. Never
    raises: a failure here must not stop the dashboard from serving.
    """
    result = {"agent_json": 0, "legacy_json": 0, "interrupted": 0}
    try:
        from ..agents.threads import get_thread_manager
        from ..agents.migrations import migrate_legacy_conversations

        tm = get_thread_manager()
        counts = migrate_legacy_conversations(tm.store)
        result["agent_json"] = int(counts.get("agent_json", 0))
        result["legacy_json"] = int(counts.get("legacy_json", 0))
        try:
            result["interrupted"] = int(tm.mark_interrupted())
        except Exception as e:
            logger.warning(f"Could not mark interrupted turns (non-fatal): {e}")
        logger.info(
            "Conversation boot hooks: migrated %d agent JSON + %d dashboard JSON "
            "conversations, %d interrupted turn(s) marked",
            result["agent_json"], result["legacy_json"], result["interrupted"],
        )
    except Exception as e:
        logger.warning(f"Conversation boot hooks failed (non-fatal): {e}")
    return result


def start_terminal_subsystem() -> Dict[str, bool]:
    """Turn on the terminal pool and the session reaper (Plan B).

    The pool is what produces *blocks*: a command run through it carries OSC
    133 markers, so it has a block id, a ``terminal_blocks`` row, head/tail
    output, and a lifecycle the conversation can render as a live tile that
    settles into a one-line result. Without it ``_run_command`` falls through
    to the subprocess path, which streams raw output under no block id at
    all -- every command equally loud, none of them ever quieter.

    ``terminal_pool_wanted()`` gates that on a module flag whose only caller
    in the repository used to be a test, so none of it ran in production.
    This is that caller.

    The two halves are started independently on purpose. A reaper that fails
    leaves exited PTY sessions occupying the cap -- visible, and eventually
    loud. A pool that silently stays off produces no blocks at all, which
    looks like a frontend bug for as long as it takes someone to find this
    function. Coupling them would trade the loud failure for the quiet one.

    Never raises: the dashboard without a terminal pool is still a dashboard.
    """
    result = {"pool": False, "reaper": False}
    try:
        from ..streaming.terminal_bridge import set_terminal_pool_enabled

        set_terminal_pool_enabled(True)
        result["pool"] = True
    except Exception as e:
        logger.warning(f"Terminal pool could not be enabled (non-fatal): {e}")
    try:
        from ..streaming.session_manager import get_terminal_manager

        get_terminal_manager().start_reaper()
        result["reaper"] = True
    except Exception as e:
        logger.warning(f"Terminal session reaper failed to start (non-fatal): {e}")
    logger.info(
        "Terminal subsystem: pool %s, reaper %s",
        "on" if result["pool"] else "OFF",
        "started" if result["reaper"] else "NOT started",
    )
    return result


def register_proactive_jobs(
    executor,
    *,
    load_config=None,
    catchup_now: Optional[datetime] = None,
    catchup_gate=None,
    catchup_probe=None,
) -> Dict[str, str]:
    """Register the scheduled background jobs on a started executor.

    T7e.1 detector sweep every 6 hours, and the T7d.2 daily morning report
    at being.yml ``morning_report.time`` when ``morning_report.enabled``
    (on by default at Balanced, C2-10). Returns a per-job outcome —
    ``"scheduled"``, ``"disabled"`` or ``"error: ..."`` — and never raises:
    a missing or malformed being.yml must not stop the dashboard.

    ``load_config`` is the being.yml loader (tests inject one). Split out of
    the startup thread so the registration path is testable; before C4-01
    every call here failed inside APScheduler and the failure was only ever
    a warning in the log.

    Packet 03 B2: after registration, serve slots the cron jobs missed
    while the machine was off (``_run_boot_catchup``; the ``catchup_*``
    kwargs exist so tests can pin the clock, the monitor-hash gate and the
    probe). The prior-boot job records must be read BEFORE registration —
    ``schedule_cron_job`` re-creates the record, which is why the last-run
    facts are captured first.
    """
    from ..scheduler.autonomous_tasks import create_autonomous_task

    outcome: Dict[str, str] = {}
    catchup_specs: Dict[str, Dict[str, Any]] = {}

    # Last-run facts from the previous boot's per-job JSON records, read
    # before registration overwrites them.
    prior_records: Dict[str, Any] = {}
    try:
        engine = getattr(executor, "scheduler_engine", None)
        if engine is not None:
            for jid in ("detector_sweep", "timeline_retention", "morning_report"):
                rec = engine.get_job(jid)
                if rec is not None:
                    prior_records[jid] = rec
    except Exception as e:
        logger.debug(f"Boot catch-up: no prior job records ({e})")

    # T7e.1: scheduled detector sweep every 6 hours
    try:
        sweep_task = create_autonomous_task('detector_sweep')
        sweep_func = lambda: sweep_task.execute({})  # noqa: E731
        executor.schedule_cron_job(
            job_id='detector_sweep',
            task_func=sweep_func,
            cron_expr={'hour': '*/6', 'minute': 12},
            description='Detector sweep (drop-ins, fstab, permissions)',
        )
        logger.info("Detector sweep scheduled every 6 hours")
        outcome['detector_sweep'] = 'scheduled'
        catchup_specs['detector_sweep'] = {
            'task': sweep_func,
            'cron_expr': {'hour': '*/6', 'minute': 12},
        }
    except Exception as e:
        logger.warning(f"Failed to schedule detector sweep: {e}")

    # CD-5 kept 90 days of event-ledger retention. TimelineStore prunes when
    # it is constructed, which covers every daemon start -- this covers the
    # machine that stays up for months, which is the one that actually grows.
    try:
        def _prune_timeline() -> None:
            from ..integrations.cognition_wiring import get_timeline_store

            store = get_timeline_store()
            if store is None:
                logger.debug("Timeline retention: no ledger, nothing to prune")
                return
            removed = store.cleanup(max_age_days=store.RETENTION_DAYS)
            logger.info("Timeline retention: pruned %s row(s)", removed)

        executor.schedule_cron_job(
            job_id='timeline_retention',
            task_func=_prune_timeline,
            cron_expr={'hour': 4, 'minute': 37},
            description='Event ledger retention sweep (90 days)',
        )
        logger.info("Timeline retention sweep scheduled daily")
        outcome['timeline_retention'] = 'scheduled'
        catchup_specs['timeline_retention'] = {
            'task': _prune_timeline,
            'cron_expr': {'hour': 4, 'minute': 37},
        }
    except Exception as e:
        logger.warning(f"Failed to schedule timeline retention: {e}")
        outcome['timeline_retention'] = f'error: {e}'
        outcome['detector_sweep'] = f'error: {e}'

    # T7d.2: daily morning report per being.yml
    try:
        if load_config is None:
            from ..config.being_config import load_being_config as load_config
        being_config = load_config()
        report_cfg = being_config.morning_report or {}
        if not isinstance(report_cfg, dict) or not report_cfg.get('enabled'):
            logger.info("Morning report disabled; not scheduled")
            outcome['morning_report'] = 'disabled'
        else:
            hour, minute = _parse_hhmm(report_cfg.get('time', '08:00'))
            report_task = create_autonomous_task('morning_report')
            report_func = lambda: report_task.execute({})  # noqa: E731
            executor.schedule_cron_job(
                job_id='morning_report',
                task_func=report_func,
                cron_expr={'hour': hour, 'minute': minute},
                description='Daily morning report',
            )
            logger.info(
                f"Morning report scheduled daily at {hour:02d}:{minute:02d} "
                f"{getattr(executor, 'timezone', '')}"
            )
            outcome['morning_report'] = 'scheduled'
            catchup_specs['morning_report'] = {
                'task': report_func,
                'cron_expr': {'hour': hour, 'minute': minute},
            }
    except Exception as e:
        logger.warning(f"Failed to schedule morning report: {e}")
        outcome['morning_report'] = f'error: {e}'

    # Packet 03 B2: serve the slots the crons missed while the machine was
    # off — bounded, staggered, age-gated per job, monitor-hash-gated for
    # the named check-on-X job. Never disturbs the outcome above.
    try:
        _run_boot_catchup(
            executor,
            catchup_specs,
            prior_records,
            now=catchup_now,
            gate=catchup_gate,
            probe=catchup_probe,
        )
    except Exception as e:
        logger.warning(f"Boot catch-up failed (non-fatal): {e}")

    return outcome


# ---------------------------------------------------------------------------
# Packet 03 B2: boot catch-up for the proactive jobs
# ---------------------------------------------------------------------------

#: Cadence of each proactive cron job, for the catch-up module's
#: cadence-scaled grace (half the period, clamped [120s, 2h]).
_PROACTIVE_PERIOD_S = {
    'detector_sweep': 6 * 3600.0,
    'timeline_retention': 24 * 3600.0,
    'morning_report': 24 * 3600.0,
}

#: Per-job catch-up age bound. detector_sweep and timeline_retention are
#: idempotent housekeeping, so a missed slot is always safe to serve; a
#: stale morning report is noise, so it catches up only within 12h of its
#: slot.
_PROACTIVE_MAX_AGE_S = {
    'morning_report': 12 * 3600.0,
}

#: Catch-up shape (OpenClaw timer-catchup/stagger): at most this many
#: immediate one-time runs, the overflow staggered by this many seconds.
_CATCHUP_MAX_IMMEDIATE = 2
_CATCHUP_STAGGER_S = 60.0


def _is_satellite_body() -> bool:
    """Is this body a satellite of a canonical host (singular entity mode)?

    The same guard ``_tick_thread_manager`` uses for the idle sweep,
    expressed the cheap way: a satellite's conversation store proxies to the
    canonical host over the peer link, and host-side proactive jobs belong
    to the host — the satellite must not catch up work it would run twice.
    Reads the config only (never constructs the thread manager); never
    raises.
    """
    try:
        from ..integrations.cognition_wiring import _get_canonical_thread_url

        return bool(_get_canonical_thread_url())
    except Exception:
        return False


def _detector_sweep_probe():
    """Cheap deterministic snapshot of what the detector sweep looks at.

    The monitor-hash gate (packet 03 addendum item 4) hashes this instead of
    running the sweep: if the surface the detectors read has not changed
    since the last evaluation, the catch-up run is suppressed entirely.
    Names, sizes, modes and mtimes only — never file contents (a content
    hash stands in for fstab). Returns ``(ok, text)``; a probe that cannot
    read its sources comes back ``ok=False``, which the gate treats as an
    error, never a "change".
    """
    import hashlib

    lines: List[str] = []
    ok = True

    def _surface(path: str, recursive: bool) -> None:
        nonlocal ok
        try:
            if not os.path.isdir(path):
                lines.append(f"{path}: absent")
                return
            lines.append(f"{path}:")
            entries: List[str] = []
            if recursive:
                for root, dirs, files in os.walk(path):
                    dirs.sort()
                    for name in sorted(files):
                        entries.append(os.path.join(root, name))
            else:
                entries = [os.path.join(path, n) for n in sorted(os.listdir(path))]
            for p in entries[:2000]:
                try:
                    st = os.stat(p)
                    lines.append(
                        f"  {p} size={st.st_size} mode={oct(st.st_mode & 0o777)} "
                        f"mtime={int(st.st_mtime)}"
                    )
                except OSError as e:
                    lines.append(f"  {p} stat-error={e.errno}")
            if len(entries) > 2000:
                lines.append(f"  ... ({len(entries) - 2000} more)")
        except OSError:
            ok = False

    _surface("/etc/systemd/system", recursive=True)  # drop-in conflicts
    _surface(os.path.join(os.path.expanduser("~"), ".ssh"), recursive=False)  # permissions hygiene
    try:
        if os.path.isfile("/etc/fstab"):
            with open("/etc/fstab", "rb") as f:
                lines.append(f"/etc/fstab: sha256={hashlib.sha256(f.read()).hexdigest()}")
        else:
            lines.append("/etc/fstab: absent")
    except OSError:
        ok = False
    return ok, "\n".join(lines)


def _last_run_of(record) -> Optional[datetime]:
    """When did this job record's run actually happen? (completed_at, or the
    first start if it never completed.) None when it never ran. The
    SchedulerEngine writes these as UTC ISO strings."""
    for attr in ("completed_at", "started_at"):
        value = getattr(record, attr, None)
        if not value:
            continue
        try:
            ts = datetime.fromisoformat(value)
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    return None


def _last_due_slot(trigger, now: datetime, *, horizon_s: float = 7 * 86400.0,
                   max_steps: int = 64):
    """The most recent slot at or before ``now`` for an APScheduler trigger.

    APScheduler 3.x has no ``get_prev_fire_time``, so binary-search the
    anchor whose "next slot" is the last one not after ``now``:
    ``f(anchor) = get_next_fire_time(None, anchor)`` is monotonic, the last
    due slot is ``f`` evaluated just below the point where ``f`` jumps past
    ``now``, and the search is bounded regardless of how fast the cron
    runs (a forward walk from a horizon is not — a 15-minute cron walks
    672 slots in 7 days). None when no slot lies in the window.
    """
    lo = now - timedelta(seconds=horizon_s)
    hi = now
    first = trigger.get_next_fire_time(None, lo)
    if first is None or first > now:
        return None  # no slot between the horizon and now
    for _ in range(max_steps):
        mid = lo + (hi - lo) / 2
        cand = trigger.get_next_fire_time(None, mid)
        if cand is not None and cand <= now:
            lo = mid
        else:
            hi = mid
        if hi - lo <= timedelta(microseconds=1):
            break
    return trigger.get_next_fire_time(None, lo)


def _run_boot_catchup(
    executor,
    specs: Dict[str, Dict[str, Any]],
    prior_records: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
    gate=None,
    probe: Optional[Callable] = None,
) -> Dict[str, str]:
    """Serve slots the proactive cron jobs missed while the machine was off.

    For each job that registered this boot, compute the slot its cron last
    passed (``_last_due_slot``) and whether the previous boot's record shows
    it was served. Missed slots go through ``decide_catchup``
    (max_immediate=2, stagger 60s) and come back as one-time runs on the
    existing ``schedule_one_time`` path. A job past its per-job
    ``max_age_s`` is skipped (a stale morning report is noise);
    the monitor-hash gate suppresses a detector_sweep catch-up whose source
    has not changed. Satellites never catch up — the canonical host runs
    the proactive jobs. Never raises; returns per-job outcomes.
    """
    result: Dict[str, str] = {}
    if not specs:
        return result
    if _is_satellite_body():
        logger.info(
            "Boot catch-up skipped: satellite body (the canonical host "
            "runs the proactive jobs)"
        )
        return result
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        return result
    from ..scheduler.catchup import CatchupAction, decide_catchup
    from ..scheduler.monitor_hash import MonitorDecision, MonitorHashGate
    from ..utils.paths import data_subdir

    if now is None:
        now = datetime.now(timezone.utc)
    if probe is None:
        probe = _detector_sweep_probe
    tz = getattr(executor, "timezone", "UTC")

    candidates = []
    for job_id, spec in specs.items():
        try:
            trigger = CronTrigger(**spec["cron_expr"], timezone=tz)
            due = _last_due_slot(trigger, now)
        except Exception as e:
            logger.warning(
                f"Boot catch-up: no last-due slot for {job_id} (non-fatal): {e}"
            )
            continue
        if due is None:
            continue  # no slot has passed in the window: the schedule owns it
        if job_id not in prior_records:
            # Never registered before (fresh install): nothing was missed.
            continue
        last_run = _last_run_of(prior_records[job_id])
        if last_run is not None and last_run >= due:
            continue  # the slot was served by the previous boot's run
        max_age_s = _PROACTIVE_MAX_AGE_S.get(job_id)
        if max_age_s is not None and (now - due).total_seconds() > max_age_s:
            logger.info(
                f"Boot catch-up: {job_id} slot at {due.isoformat()} is stale "
                f"(older than its {max_age_s:g}s bound); skipped"
            )
            result[job_id] = "stale_skipped"
            continue
        candidates.append({
            "id": job_id,
            "due_at": due,
            "period_s": _PROACTIVE_PERIOD_S.get(job_id),
            "one_shot": False,
            "task": spec["task"],
        })

    if not candidates:
        return result

    plan = decide_catchup(
        candidates,
        now=now,
        max_immediate=_CATCHUP_MAX_IMMEDIATE,
        stagger_s=_CATCHUP_STAGGER_S,
    )

    if gate is None:
        try:
            gate = MonitorHashGate(
                os.path.join(data_subdir("scheduler"), "monitor_hashes.json")
            )
        except Exception as e:
            logger.warning(
                f"Boot catch-up: monitor-hash gate unavailable ({e}); "
                f"running ungated"
            )
            gate = None

    def _monitor_allows(job_id: str) -> bool:
        """Named-job-set-only monitor gate: detector_sweep-class check-on-X
        jobs are suppressed when their source is unchanged; everything else
        (morning_report, timeline_retention) runs unconditionally."""
        if gate is None or not gate.is_gated(job_id):
            return True
        try:
            outcome = gate.evaluate(job_id, probe())
        except Exception as e:
            logger.warning(
                f"Boot catch-up: monitor probe for {job_id} failed ({e}); "
                f"running anyway"
            )
            return True
        if outcome.decision is MonitorDecision.SUPPRESS:
            logger.info(
                f"Boot catch-up: {job_id} suppressed (source unchanged)"
            )
            return False
        if outcome.decision is MonitorDecision.BASELINE:
            logger.info(
                f"Boot catch-up: {job_id} monitor baseline established; "
                f"catch-up suppressed"
            )
            return False
        if outcome.decision is MonitorDecision.SOURCE_ERROR:
            logger.warning(
                f"Boot catch-up: monitor source for {job_id} errored; "
                f"running anyway (a source failure is never a 'change')"
            )
            return True
        if outcome.diff:
            logger.info(f"Boot catch-up: {job_id} source changed:\n{outcome.diff}")
        return True

    def _schedule_one_time(job: Dict[str, Any], run_at: datetime, tag: str) -> None:
        run_id = f"{job['id']}:catchup"
        try:
            executor.schedule_one_time(
                job_id=run_id,
                task_func=job["task"],
                run_at=run_at,
            )
        except Exception as e:
            logger.warning(
                f"Boot catch-up: could not schedule {run_id} (non-fatal): {e}"
            )
            return
        logger.info(
            f"Boot catch-up: {job['id']} scheduled one-time as {run_id} "
            f"at {run_at.isoformat()}"
        )
        result[job["id"]] = tag

    for entry in plan.actions:
        job = entry.job
        if entry.action in (CatchupAction.RUN_NOW, CatchupAction.FAST_FORWARD):
            # FAST_FORWARD (beyond grace, recurring) also fires ONCE now:
            # the cron registration owns the true next slot, so advancing
            # the schedule is inherent — no backlog is replayed.
            if _monitor_allows(job["id"]):
                _schedule_one_time(job, now, "caught_up")
        elif entry.action is CatchupAction.ADVANCE_ONLY:
            result.setdefault(job["id"], "advanced")
        elif entry.action is CatchupAction.RETIRE:
            result.setdefault(job["id"], "retired")
    for entry in plan.deferred:
        job = entry.job
        if _monitor_allows(job["id"]):
            _schedule_one_time(
                job, now + timedelta(seconds=entry.delay_s), "caught_up_deferred"
            )
    return result


# ---------------------------------------------------------------------------
# C4-03: the idle heartbeat — ThreadManager.tick() gets a production caller
# ---------------------------------------------------------------------------

#: Cadence of the idle thread sweep + consolidator when being.yml does not
#: set ``heartbeat_s``. tick() is cheap when nothing is due (one indexed
#: list of paused rows), so a minute is about visibility, not cost.
DEFAULT_HEARTBEAT_S = 60.0
#: Floor for a configured ``heartbeat_s``: below this the sweep would
#: compete with turns for the store for no benefit.
MIN_HEARTBEAT_S = 5.0


def heartbeat_interval_s(default: float = DEFAULT_HEARTBEAT_S) -> float:
    """Idle-tick cadence: being.yml ``heartbeat_s`` when set, else 60 s.

    Read straight from the file rather than BeingConfig — the dataclass
    drops keys it does not declare, and the heartbeat is a runtime knob of
    the host process, not a persona field to be written back on every save.
    Never raises: a missing or broken being.yml means the default.
    """
    try:
        import yaml
        from ..utils.platform import get_config_dir

        path = get_config_dir() / "being.yml"
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            value = data.get("heartbeat_s") if isinstance(data, dict) else None
            if value is not None:
                return max(MIN_HEARTBEAT_S, float(value))
    except Exception as e:
        logger.debug(f"heartbeat_s not read from being.yml ({e}); using {default}s")
    return default


def _agent_turn_busy() -> bool:
    """Is a conversation turn in flight?

    The process-wide agent (routes/agent.py) holds ``turn_lock`` for the
    whole of ``process()``; the lock is built lazily, so ``None`` means no
    turn has ever run. Fail-soft: an unreadable agent reads as "not busy" —
    tick() is lock-safe in its own right, this check only keeps the sweep
    out of the user's turn time.
    """
    try:
        from .routes import agent as agent_routes

        agent = agent_routes._agent_instance
        lock = getattr(agent, "_turn_lock", None) if agent is not None else None
        return bool(lock is not None and lock.locked())
    except Exception:
        return False


def _tick_thread_manager() -> list:
    """One idle tick on the process-wide ThreadManager; returns closed ids.

    A satellite's manager proxies to the canonical host's store (singular
    entity mode); the host sweeps its own threads, so the satellite does
    not tick through the peer link.
    """
    from ..agents import threads as threads_mod

    manager = threads_mod.get_thread_manager()
    if isinstance(manager.store, threads_mod._PeerConversationStoreType):
        return []
    return manager.tick()


async def run_thread_tick_loop(
    interval_s: float,
    *,
    tick: Callable[[], Any] = _tick_thread_manager,
    turn_busy: Callable[[], bool] = _agent_turn_busy,
    max_beats: Optional[int] = None,
) -> int:
    """Every ``interval_s`` seconds, run ``tick`` off the event loop unless a
    turn is in flight (then wait for the next beat). Returns the number of
    beats (tests pass ``max_beats``; production cancels the task instead).

    A failing tick is logged and the loop carries on: the sweep is the
    being's housekeeping, and a locked store this minute is not a reason to
    stop sweeping for the rest of the process's life.
    """
    beats = 0
    while max_beats is None or beats < max_beats:
        await asyncio.sleep(interval_s)
        beats += 1
        if turn_busy():
            continue
        try:
            closed = await asyncio.to_thread(tick)
            if closed:
                logger.info(f"Idle tick closed {len(closed)} thread(s)")
        except Exception as e:
            logger.warning(f"Thread tick failed (non-fatal): {e}")
    return beats


def start_thread_tick_heartbeat(
    app: FastAPI,
    *,
    interval_s: Optional[float] = None,
    tick: Callable[[], Any] = _tick_thread_manager,
    turn_busy: Callable[[], bool] = _agent_turn_busy,
) -> "asyncio.Task":
    """Start the heartbeat task on the running loop and park it on ``app.state``."""
    if interval_s is None:
        interval_s = heartbeat_interval_s()
    task = asyncio.get_running_loop().create_task(
        run_thread_tick_loop(interval_s, tick=tick, turn_busy=turn_busy),
        name="halbert-thread-tick",
    )
    app.state.thread_tick_task = task
    logger.info(f"Thread tick heartbeat started (every {interval_s:g}s)")
    return task


async def stop_thread_tick_heartbeat(app: FastAPI) -> None:
    """Cancel the heartbeat task started by ``start_thread_tick_heartbeat``."""
    task = getattr(app.state, "thread_tick_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"Thread tick heartbeat ended with an error: {e}")
    app.state.thread_tick_task = None
    logger.info("Thread tick heartbeat stopped")


def get_recent_config_changes(within_hours: int = 24) -> list:
    """Recent config changes recorded by the running ConfigWatcher.

    Consumed by MorningReportTask (T7d.1) via attribute lookup — returns
    an empty list when no watcher is running.
    """
    watcher = _config_watcher
    if watcher is None:
        return []
    try:
        return watcher.get_recent_changes(within_hours=within_hours)
    except Exception as e:
        logger.warning(f"Failed to read recent config changes: {e}")
        return []


class ConnectionManager:
    """
    WebSocket connection manager for real-time updates.
    
    Broadcasts events to all connected clients:
    - System status updates
    - New approval requests
    - Job status changes
    - LLM decisions
    """
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """Accept and track new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """
        Broadcast message to all connected clients.
        
        Args:
            message: Dict with 'type' and 'data' keys
        """
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to WebSocket: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
    
    async def send_system_status(self, status: dict):
        """Broadcast system status update."""
        await self.broadcast({
            'type': 'system_status',
            'data': status
        })
    
    async def send_approval_request(self, request: dict):
        """Broadcast new approval request."""
        await self.broadcast({
            'type': 'approval_request',
            'data': request
        })
    
    async def send_job_update(self, job_id: str, status: str, progress: float = None):
        """Broadcast job status update."""
        await self.broadcast({
            'type': 'job_update',
            'data': {
                'job_id': job_id,
                'status': status,
                'progress': progress
            }
        })
    
    async def send_decision(self, decision: dict):
        """Broadcast LLM decision."""
        await self.broadcast({
            'type': 'decision',
            'data': decision
        })
    
    async def send_chat_token(self, request_id: str, token: str, done: bool = False):
        """Stream chat response tokens in real-time."""
        await self.broadcast({
            'type': 'chat_token',
            'data': {
                'request_id': request_id,
                'token': token,
                'done': done
            }
        })
    
    async def send_chat_complete(self, request_id: str, full_response: str, metadata: dict = None):
        """Signal chat response completion."""
        await self.broadcast({
            'type': 'chat_complete',
            'data': {
                'request_id': request_id,
                'response': full_response,
                'metadata': metadata or {}
            }
        })


def create_app(enable_cors: bool = True) -> FastAPI:
    """
    Create FastAPI dashboard application.
    
    Args:
        enable_cors: Enable CORS for local development
    
    Returns:
        Configured FastAPI app
    """
    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn")
    
    # SEC-1: /docs, /redoc and /openapi.json are generated by FastAPI and were
    # served to anyone — a complete, machine-readable map of all 334 routes with
    # their request schemas, which is the first thing an attacker would want and
    # the last thing this machine should volunteer. Off unless a developer asks
    # for them; they cannot be authenticated in place because Swagger fetches
    # openapi.json from the browser with no credential.
    _dev_docs = os.environ.get("HALBERT_DEV_DOCS", "").strip().lower() in ("1", "true", "yes")

    app = FastAPI(
        title="Halbert Dashboard",
        description="Web UI for Halbert autonomous IT management",
        version="0.1.1",
        docs_url="/docs" if _dev_docs else None,
        redoc_url="/redoc" if _dev_docs else None,
        openapi_url="/openapi.json" if _dev_docs else None,
    )
    
    # CORS for local development and the Tauri desktop webview.
    # allow_credentials=True forbids the "*" wildcard, so origins are explicit;
    # HALBERT_CORS_ORIGINS (comma-separated) adds more.
    if enable_cors:
        default_origins = [
            "http://localhost:5173", "http://localhost:3000",   # Vite, CRA
            "tauri://localhost", "http://tauri.localhost",       # Tauri v2 webview
        ]
        extra = []
        for raw in os.environ.get("HALBERT_CORS_ORIGINS", "").split(","):
            origin = raw.strip()
            if not origin:
                continue
            if "*" in origin:
                # A wildcard with allow_credentials=True would let any site
                # make credentialed requests; never honour it.
                logger.warning(
                    "HALBERT_CORS_ORIGINS: ignoring wildcard entry %r (explicit origins only)",
                    origin,
                )
                continue
            extra.append(origin)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=default_origins + extra,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    # WebSocket connection manager
    manager = ConnectionManager()
    
    # Store in app state
    app.state.ws_manager = manager
    
    # SEC-1 — one door.
    #
    # Every router below is registered through `mount_api`, which attaches
    # `require_owner` unless the router authenticates itself. That inversion is
    # the point: a route added tomorrow with no auth dependency is protected by
    # *omission* rather than by its author remembering. The previous design
    # needed 334 separate acts of remembering and got 19 of them.
    from . import auth as _auth

    app.state.auth = _auth.AuthState()
    app.add_middleware(_auth.HostHeaderMiddleware)
    app.include_router(_auth.build_auth_router(), tags=["auth"])

    def mount_api(router, *, prefix: str = "", tags=None):
        _auth.mount_router(app, router, prefix=prefix, tags=tags)

    # Register routes
    from ..federation import compute_endpoint
    from .routes import approvals, jobs, memory, settings, system, websocket, persona, discovery, terminal, alerts, rag, services, web_search, gpu, containers, development, editor, storage, downloads, agent, compression, being, modules, llm, legal, compute, vision, home, frigate, instance, peers, fleet, audio, conversations, devices, findings, state, guest as guest_persona

    mount_api(system.router, prefix="/api", tags=["system"])
    mount_api(agent.router, tags=["agent"])  # Phase 36: Agent state machine
    mount_api(approvals.router, prefix="/api/approvals", tags=["approvals"])
    mount_api(jobs.router, prefix="/api/jobs", tags=["jobs"])
    mount_api(memory.router, prefix="/api/memory", tags=["memory"])
    mount_api(state.router, prefix="/api/state", tags=["state"])  # LEDGER-1: "why is X configured this way"
    mount_api(settings.router, prefix="/api/settings", tags=["settings"])
    mount_api(discovery.router, prefix="/api/discoveries", tags=["discoveries"])  # Phase 11
    mount_api(terminal.router, prefix="/api/terminal", tags=["terminal"])  # Phase 11
    mount_api(alerts.router, prefix="/api/alerts", tags=["alerts"])  # Phase 11
    mount_api(rag.router, prefix="/api", tags=["rag"])  # Phase 10
    mount_api(services.router, prefix="/api/services", tags=["services"])  # Service explanations
    mount_api(web_search.router, prefix="/api", tags=["web-search"])  # Web grounding
    mount_api(gpu.router, prefix="/api", tags=["gpu"])  # Phase 14: GPU
    mount_api(containers.router, prefix="/api", tags=["containers"])  # Phase 15: Containers
    mount_api(development.router, prefix="/api", tags=["development"])  # Phase 16: Development
    mount_api(editor.router, tags=["editor"])  # Phase 18: Config Editor
    mount_api(persona.router, tags=["persona"])  # Phase 4 M3
    mount_api(websocket.router, tags=["websocket"])
    mount_api(storage.router, prefix="/api/storage", tags=["storage"])  # Phase 52: ChromaDB management
    mount_api(downloads.router, prefix="/api/downloads", tags=["downloads"])  # Dataset downloads
    mount_api(compression.router, tags=["compression"])  # Phase 72: Compression cascade
    mount_api(being.router, prefix="/api", tags=["being"])  # Phase 7: Proactive channel
    # prefix="/api": findings.py writes its paths as "/findings/...".
    mount_api(findings.router, prefix="/api", tags=["findings"])  # C2-03: Finding is the unit of attention
    mount_api(modules.router, prefix="/api", tags=["modules"])  # Phase 8: Module registry
    mount_api(llm.router, tags=["llm"])  # Unified LLM model picker
    mount_api(compute.router, tags=["compute"])  # Endpoint capacity probe
    # The workstation side of peer compute. routes/compute is the capacity
    # PROBE — a different module — so mounting only that left
    # /api/compute/v1/* served by nothing: a home node linked through the
    # Compute Peer card 404'd on every turn (SE-09 / R10-F2).
    mount_api(compute_endpoint.router, tags=["compute-peer"])
    mount_api(legal.router, tags=["legal"])  # LEG-MOD-01/02: Legal notices & cloud disclosure
    mount_api(vision.router, prefix="/api", tags=["vision"])  # Screen capture for vision model
    mount_api(audio.router, prefix="/api", tags=["audio"])  # Auditory cortex
    mount_api(home.router, prefix="/api", tags=["home"])  # Home Assistant panel
    mount_api(frigate.router, prefix="/api", tags=["frigate"])  # Frigate NVR panel
    mount_api(instance.router, tags=["instance"])  # Multi-instance info
    # GP-1: a borrowed face over the body. Mounted through mount_api, not
    # app.include_router as the branch had it, so the guest routes sit behind
    # the same auth as every other router.
    mount_api(guest_persona.router, tags=["guest"])
    mount_api(peers.router, tags=["peers"])  # Phase 9.1: Peer pairing
    # prefix="/api": devices.py writes its paths as "/devices/..." (unlike
    # peers.py, which spells "/api/peers/..." into each decorator), so
    # mounting it bare put every route at /devices/* while the frontend and
    # the G12 design both call /api/devices/* — Settings > Devices was a 404
    # from the day it shipped (ROUTE-01 / R10-N1).
    mount_api(devices.router, prefix="/api", tags=["devices"])  # P7a: Devices page & entity mode
    mount_api(fleet.router, tags=["fleet"])  # Phase 9.9: Fleet Cockpit
    mount_api(conversations.router, prefix="/api/conversations", tags=["conversations"])  # P3b: Peer conversation API
    
    # Serve static frontend (production)
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    if frontend_dist.exists():
        mount_frontend(app, frontend_dist)
    
    # Startup event: auto-start services
    @app.on_event("startup")
    async def startup_event():
        """Start background services on app startup."""
        # Multi-instance identity logging
        import os
        _persona = os.environ.get("HALBERT_PERSONA_ID", "halbert")
        _scene = os.environ.get("HALBERT_SCENE_CONTEXT", "")
        _port = os.environ.get("HALBERT_PORT", "8000")
        _data = os.environ.get("HALBERT_DATA_DIR") or os.environ.get("Halbert_DATA_DIR", "")
        _config = os.environ.get("HALBERT_CONFIG_DIR") or os.environ.get("Halbert_CONFIG_DIR", "")
        logger.info(
            f"Halbert instance starting — persona={_persona}, scene={_scene or '(default)'}, "
            f"port={_port}, data_dir={_data or '(default)'}, config_dir={_config or '(default)'}"
        )

        # Sidecar mode (Tauri sets HALBERT_PARENT_PID): stop when the shell dies.
        try:
            from .parent_watchdog import start_parent_watchdog
            start_parent_watchdog()
        except Exception as e:
            logger.warning(f"Parent watchdog not started: {e}")

        # Reset indexing state to prevent stuck state from hot-reload
        try:
            from .routes.settings import _reset_indexing_state
            _reset_indexing_state()
            logger.info("Indexing state reset on startup")
        except Exception as e:
            logger.warning(f"Failed to reset indexing state: {e}")

        # Plan A: one-time JSON -> SQLite conversation migration, then mark any
        # turn that was in flight when the last process died as interrupted.
        # Synchronous on purpose: the first /api/agent/message must see the
        # migrated threads and no phantom in_progress rows.
        run_conversation_boot_hooks()

        # C4-03: the idle heartbeat. ThreadManager.tick() (grace-window
        # close sweep + R8 Consolidator) had no production caller; this
        # task runs it every heartbeat_s (being.yml, else 60 s) whenever no
        # turn is in flight. Cancelled in shutdown_event.
        try:
            start_thread_tick_heartbeat(app)
        except Exception as e:
            logger.warning(f"Thread tick heartbeat not started (non-fatal): {e}")
        
        # Bootstrap system identity (if not already done)
        try:
            from ..knowledge import get_self_knowledge, bootstrap_identity
            sk = get_self_knowledge()
            if not sk.get_identity():
                logger.info("Bootstrapping system identity...")
                bootstrap_identity()
            else:
                logger.info(f"Self-knowledge loaded: {len(sk._knowledge)} entries")
        except Exception as e:
            logger.warning(f"Failed to bootstrap identity: {e}")
        
        # Start ingestion service in background (non-blocking)
        # Uses daemon threads so won't block shutdown
        # Capability-based gating: a node runs ingestion only if it has
        # the ingestion capability. The variant preset sets defaults
        # (home = no ingestion), but being.yml capabilities: section can
        # override — a Mac Studio with HA configured can do both.
        from ..capabilities import get_capability_registry, CAP_INGESTION, CAP_DISCOVERY, CAP_SCHEDULER, CAP_CONFIG_WATCHER, CAP_SOURCEPREP, CAP_TERMINAL, CAP_HA_CONNECTION, CAP_AUDIO
        _caps = get_capability_registry()
        _caps.probe()
        if not _caps.has(CAP_INGESTION):
            logger.info("Ingestion service skipped (no ingestion capability)")
        else:
            def start_ingestion_delayed():
                """Start ingestion after a short delay to let ChromaDB initialize."""
                import time
                time.sleep(2)  # Wait for ChromaDB to be ready
                try:
                    from ..ingestion.service import get_ingestion_service
                    service = get_ingestion_service()
                    service.start()
                    logger.info("Ingestion service started (journald + hwmon)")
                except Exception as e:
                    logger.warning(f"Failed to start ingestion: {e}")

            import threading
            ingestion_starter = threading.Thread(target=start_ingestion_delayed, daemon=True)
            ingestion_starter.start()
            logger.info("Ingestion service starting in background...")

        # Auto-scan discovery engine on startup so dashboard pages have data
        # without requiring a manual scan click. Runs in a daemon thread after
        # a short delay to avoid competing with ChromaDB/ingestion init.
        # Capability-based: skip if no discovery capability.
        if not _caps.has(CAP_DISCOVERY):
            logger.info("Discovery scan skipped (no discovery capability)")
        else:
            def start_discovery_scan_delayed():
                """Run all discovery scanners in the background on startup."""
                import time
                time.sleep(5)  # Wait for other services to initialize
                try:
                    from ..discovery.engine import get_engine
                    engine = get_engine()
                    discoveries = engine.scan_all()
                    logger.info(f"Startup discovery scan complete: {len(discoveries)} items found")
                except Exception as e:
                    logger.warning(f"Startup discovery scan failed (non-fatal): {e}")

            discovery_starter = threading.Thread(target=start_discovery_scan_delayed, daemon=True)
            discovery_starter.start()
            logger.info("Discovery scan starting in background...")
        
        # Phase 23: Start scheduler (re-enabled with delayed start)
        # Capability-based: skip if no scheduler capability.
        if not _caps.has(CAP_SCHEDULER):
            logger.info("Scheduler skipped (no scheduler capability)")
        else:
            def start_scheduler_delayed():
                """Start scheduler after a short delay."""
                import time
                time.sleep(3)  # Wait for other services to initialize
                try:
                    from ..scheduler.executor import AutonomousExecutor, APSCHEDULER_AVAILABLE
                    if APSCHEDULER_AVAILABLE:
                        global _scheduler_executor
                        # Resolve timezone from being config (default: local system tz)
                        scheduler_tz = 'UTC'
                        try:
                            from ..config.being_config import load_being_config, resolve_timezone
                            being_cfg = load_being_config()
                            scheduler_tz = resolve_timezone(being_cfg.timezone)
                        except Exception:
                            pass  # Fall back to UTC
                        _scheduler_executor = AutonomousExecutor(
                            max_workers=3,
                            enable_llm=False,  # Disable LLM for scheduler jobs
                            enable_guardrails=True,
                            timezone=scheduler_tz,
                        )
                        _scheduler_executor.start()
                        logger.info(f"Scheduler started successfully (timezone: {scheduler_tz})")
                    else:
                        logger.info("APScheduler not available, scheduler disabled")
                except Exception as e:
                    logger.warning(f"Failed to start scheduler: {e}")

            scheduler_starter = threading.Thread(target=start_scheduler_delayed, daemon=True)
            scheduler_starter.start()
            logger.info("Scheduler starting in background...")

            # Phase 7 / T7d.2 + T7e.1: schedule morning report and detector sweep
            def schedule_proactive_jobs_delayed():
                """Register proactive jobs once the scheduler has had time to start."""
                import time
                time.sleep(4)  # after the delayed scheduler start above
                try:
                    executor = _scheduler_executor
                    if executor is None:
                        logger.info("Scheduler not running; proactive jobs not scheduled")
                        return

                    # Detector sweep + morning report (C4-01: registration
                    # is a plain helper so it is tested; missing / disabled /
                    # malformed being.yml is logged, never a startup crash).
                    register_proactive_jobs(executor)

                    # VisualWatcher: standalone background thread for proactive
                    # screen monitoring. NOT a cron job — cadence is adaptive
                    # (30s-5min), too fast for the cron scheduler. Gated by
                    # both vision_config.yml (system) and being.yml (persona).
                    try:
                        from ..config.being_config import load_being_config
                        from ..vision.config import is_screen_capture_enabled
                        being_config = load_being_config()
                        if (being_config.senses.vision.enabled
                                and being_config.senses.vision.proactive_monitoring
                                and is_screen_capture_enabled()):
                            from ..vision.watcher import VisualWatcher
                            from ..proactive.gate import ProactiveGate
                            from ..autonomy.guardrails import GuardrailEnforcer
                            from ..findings.store import FindingStore
                            gate = ProactiveGate(
                                being_config=being_config,
                                guardrail_enforcer=GuardrailEnforcer(),
                                finding_store=FindingStore(),
                            )
                            watcher = VisualWatcher(
                                being_config=being_config,
                                gate=gate,
                                finding_store=FindingStore(),
                            )
                            watcher.start()
                            logger.info("VisualWatcher started (proactive screen monitoring)")
                    except Exception as e:
                        logger.warning(f"Failed to start VisualWatcher: {e}")
                except Exception as e:
                    logger.warning(f"Failed to schedule proactive jobs: {e}")

            proactive_starter = threading.Thread(target=schedule_proactive_jobs_delayed, daemon=True)
            proactive_starter.start()

        # Phase 5+7 / T5a.2 + T7e.1: watch host config files (Linux hosts only).
        # The whole thing no-ops gracefully if the platform is unsupported,
        # the manifest is missing/unwatched, or SourcePrep is down.
        # Capability-based: skip if no config_watcher capability.
        if not _caps.has(CAP_CONFIG_WATCHER):
            logger.info("Config watcher skipped (no config_watcher capability)")
        else:
            def start_config_watcher():
                global _config_watcher
                try:
                    # No platform gate. What to watch is a fact about the
                    # platform and lives in the registry, which is chosen by
                    # platform; the parser handles plists natively and the
                    # watcher uses watchdog, which is cross-platform. The old
                    # `if not is_linux(): return` kept the whole subsystem off
                    # on the machine capabilities.py names in its own
                    # docstring as the case it exists for.
                    manifest = _find_config_registry()
                    if manifest is None:
                        logger.info("No config-registry.yml found; config watcher not started")
                        return
                    from ..config.watcher import (
                        ConfigWatcher,
                        create_sourceprep_reindex_callback,
                        create_detector_trigger_callback,
                    )
                    change_callbacks = [create_detector_trigger_callback()]
                    # SourcePrep re-index callback only if sourceprep capability
                    if _caps.has(CAP_SOURCEPREP):
                        change_callbacks.insert(0, create_sourceprep_reindex_callback())
                    watcher = ConfigWatcher(
                        manifest_path=str(manifest),
                        change_callbacks=change_callbacks,
                    )
                    watcher.start()
                    _config_watcher = watcher
                    logger.info(f"Config watcher started on {manifest}")
                except Exception as e:
                    logger.warning(f"Config watcher failed to start (non-fatal): {e}")

            start_config_watcher()

        # Terminal subsystem (B1b + B7): the block-producing pool and the
        # idle/dead session reaper. Capability-based: skip with no terminal
        # capability. See start_terminal_subsystem for why the two halves do
        # not share a failure.
        if _caps.has(CAP_TERMINAL):
            start_terminal_subsystem()

        # Voice mode (O2): audio pipeline coordinator — the dashboard's ears.
        # Capability-gated presence check (config enabled + sherpa-onnx, probed
        # in capabilities.py — never a variant check). being.yml
        # ``capabilities: {audio: false}`` is the operator override. Audio is
        # optional: a coordinator that fails to start leaves the coordinator
        # slot None and the dashboard keeps booting (/api/audio/stream then
        # answers 1013 "try again later").
        app.state.audio_coordinator = None
        if not _caps.has(CAP_AUDIO):
            logger.info("Audio pipeline skipped (no audio capability)")
        else:
            coordinator = None
            # Imported before the try: the handler below calls it, so a
            # failure in one of the audio imports must not turn into a
            # NameError in the cleanup path.
            from .routes.audio import set_audio_pipeline
            try:
                from ..audio.config import load_config as load_audio_config
                from ..audio.pipeline import AudioPipelineCoordinator
                from ..audio.ingress.webrtc_ingress import WebRtcIngress
                coordinator = AudioPipelineCoordinator(config=load_audio_config())
                attached = await coordinator.add_ingress(
                    WebRtcIngress(area_id="dashboard_voice")
                )
                if not attached:
                    logger.warning(
                        "Dashboard audio ingress failed to start — "
                        "/api/audio/stream will answer 1013"
                    )
                await coordinator.start()
                app.state.audio_coordinator = coordinator
                # Publish it where code outside a request can see it. The
                # channel capability asks this to decide whether Halbert has
                # a mouth; until it did, has_speaker() was always False and
                # every downstream voice seam — should_speak(), the TTS
                # egress hook, the speaking state, the HUD relay — was
                # unreachable in production (U2-15 / R9-F05).
                set_audio_pipeline(coordinator)
                logger.info(
                    "Audio pipeline coordinator started "
                    f"(dashboard ingress {'attached' if attached else 'NOT attached'})"
                )
            except Exception as e:
                logger.warning(f"Audio pipeline failed to start (non-fatal): {e}")
                # Best-effort cleanup: start() can raise after the ingress was
                # started or after loop tasks were created (and gains more raise
                # points as it grows, e.g. O3) — stop whatever partially came up
                # so no adapter or task is left orphaned spinning forever.
                if coordinator is not None:
                    try:
                        await coordinator.stop()
                    except Exception as stop_err:
                        logger.debug(f"Coordinator cleanup after failed start: {stop_err}")
                app.state.audio_coordinator = None
                set_audio_pipeline(None)

        # Voice mode: a spoken turn has to reach the page that spoke it.
        #
        # ``on_voice_turn`` was declared on the coordinator and invoked by
        # the speech track, and nothing ever set it — so a completed voice
        # turn produced a VoiceTurnObservation that went nowhere, /voice's
        # "Tap to speak" ended in an empty turn, and the on-screen keyboard
        # was the only working input. The status endpoint deliberately never
        # carries the transcript (it answers who spoke, not what was said),
        # so the return path is the mic uplink the browser is already holding
        # open (VM-STT).
        if app.state.audio_coordinator is not None:
            try:
                _coordinator = app.state.audio_coordinator

                async def _relay_voice_turn(observation) -> None:
                    # Packet 04 A1 + Hermes addendum. Transcribe-once: the
                    # VoiceTurnObservation IS the single STT+identification
                    # result for this utterance (StreamingASR + SpeakerIdentifier
                    # ran once in the speech track, and the result is cached
                    # on this event); every consumer — the speaker badge via
                    # /api/audio/status, this relay, the browser's turn
                    # submission — reads it, never a second STT call.
                    #
                    # Empty/failure sentinels: an empty transcript broadcasts
                    # NOTHING and creates no turn — the agent is never handed
                    # an empty utterance to guess at, and the browser's
                    # recognition watchdog returns to listening with a
                    # neutral note that never mentions STT setup (the Hermes
                    # #41603 lesson: setup-advice text that persists and the
                    # model keeps volunteering it).
                    #
                    # The transcript reaches the browser as a plain line — no
                    # wrapper phrase (a wrapper reads as a meta-instruction);
                    # the browser echoes it back to the user verbatim and
                    # submits it as the turn text. C2 (voice honesty): the
                    # relay records this observation under a server-minted
                    # single-use receipt token BEFORE broadcasting, and the
                    # token rides with the transcript — the browser redeems
                    # it with the turn, and the talk door stamps the turn's
                    # claim from what the pipeline actually observed, never
                    # from the wire's word (dashboard/voice_relay.py). The
                    # transcript IS the command text
                    # (transcribe_before_command): the receipt is bound to
                    # these exact words, so a redeemed token cannot carry
                    # the observed speaker's identity onto others.
                    text = getattr(observation, "text", "") or ""
                    if not text.strip():
                        return
                    from .voice_relay import get_voice_relay_receipts
                    relay_token = get_voice_relay_receipts().record(observation)
                    ingress = _coordinator.get_ingress("dashboard")
                    if ingress is None or not hasattr(ingress, "broadcast"):
                        return
                    await ingress.broadcast({
                        "type": "transcript",
                        "text": text,
                        "speaker_name": getattr(observation, "speaker_name", ""),
                        "speaker_role": getattr(observation, "speaker_role", "unknown"),
                        "area_id": getattr(observation, "area_id", ""),
                        "relay_token": relay_token,
                    })

                _coordinator.on_voice_turn = _relay_voice_turn
                logger.info("Voice turn relay wired to the dashboard uplink")
            except Exception as e:
                logger.warning(f"Voice turn relay not wired (non-fatal): {e}")

        # Voice mode (O5): acoustic anomalies ride the findings chain. The
        # bridge sets the coordinator's on_acoustic_event callback; a tagged
        # anomaly then flows AcousticAnomalyDetector -> DetectorRunner ->
        # ProactiveEventBus -> /api/being/events. Strictly optional — the
        # DetectorRunner is built lazily on the first event, and a broken
        # findings stack degrades to a warning-once drop, never a boot
        # failure.
        if app.state.audio_coordinator is not None:
            try:
                from ..proactive.acoustic_bridge import attach_acoustic_bridge
                attach_acoustic_bridge(app.state.audio_coordinator)
            except Exception as e:
                logger.warning(f"Acoustic anomaly bridge attach failed (non-fatal): {e}")

        # Voice mode (O3): TTS egress hub — the dashboard's mouth. A dumb
        # relay from the agent state machine to /api/audio/tts subscribers,
        # deliberately NOT gated on the audio capability: it forwards
        # nothing until a browser subscribes, and only the synthesis (in the
        # state machine hook) needs the audio stack. Aliased onto app.state
        # per the plan; the state machine reaches it through the module
        # singleton (the get_event_bus pattern) because it holds no app ref.
        from .routes.tts_egress import get_tts_egress_hub
        app.state.tts_egress = get_tts_egress_hub()
        # When the pipeline runs, the state machine's TTS hook mints
        # coordinator-owned barge-in tokens through this reference (so VAD
        # barge-in cancels browser playback too); without it the hook falls
        # back to a standalone token.
        app.state.tts_egress.set_pipeline(app.state.audio_coordinator)

        # Phase 2: Start HA WebSocket event stream if configured
        # Capability-based: start if HA connection is configured.
        if _caps.has(CAP_HA_CONNECTION):
            try:
                from ..config.being_config import load_being_config
                from ..integrations.home_assistant.ha_config import seed_ha_config_from_being
                being_cfg = load_being_config()
                if being_cfg.ha_url and being_cfg.ha_token:
                    seed_ha_config_from_being(being_cfg.ha_url, being_cfg.ha_token)
            except Exception as e:
                logger.warning(f"Failed to seed HA config from being.yml: {e}")
        try:
            from ..integrations.cognition_wiring import start_ha_event_stream
            start_ha_event_stream()
            # The event stream needs async start; do it in a delayed thread
            def start_ha_stream_delayed():
                import time, asyncio
                time.sleep(5)  # Wait for other services
                try:
                    from ..integrations.cognition_wiring import _ha_event_stream
                    if _ha_event_stream is not None:
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(_ha_event_stream.start())
                        loop.run_forever()
                except Exception as e:
                    logger.warning(f"HA event stream start failed: {e}")
            ha_starter = threading.Thread(target=start_ha_stream_delayed, daemon=True)
            ha_starter.start()
            logger.info("HA event stream starting in background...")
        except Exception as e:
            logger.warning(f"HA event stream not started: {e}")

        # Phase 4: Start Wyoming voice agent if enabled
        try:
            from ..integrations.wyoming_agent import HalbertWyomingAgent, WyomingConfig
            wyoming_cfg = WyomingConfig.from_env()
            if wyoming_cfg.enabled:
                global _wyoming_agent
                # Hand it this loop: the Wyoming server runs on its own loop
                # in a daemon thread but shares this process's state machine,
                # whose turn lock is per-loop — so without this, voice and
                # dashboard turns ran concurrently on a machine designed for
                # one at a time (R9-F02).
                import asyncio as _asyncio
                _wyoming_agent = HalbertWyomingAgent(
                    config=wyoming_cfg,
                    main_loop=_asyncio.get_running_loop(),
                )
                def start_wyoming_delayed():
                    import time, asyncio
                    time.sleep(7)  # after Frigate
                    try:
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(_wyoming_agent.start())
                        loop.run_forever()
                    except Exception as e:
                        logger.warning(f"Wyoming agent start failed: {e}")
                wyoming_starter = threading.Thread(target=start_wyoming_delayed, daemon=True)
                wyoming_starter.start()
                logger.info(f"Wyoming voice agent starting on {wyoming_cfg.host}:{wyoming_cfg.port}...")
        except Exception as e:
            logger.warning(f"Wyoming voice agent not started: {e}")

        # Frigate MQTT subscriber — start if MQTT is configured
        try:
            from ..integrations.frigate.frigate_config import load_frigate_config
            frigate_cfg = load_frigate_config()
            if frigate_cfg.is_mqtt_configured():
                from ..integrations.cognition_wiring import get_frigate_event_mapper
                from ..integrations.frigate.frigate_mqtt_subscriber import FrigateMQTTSubscriber
                global _frigate_mqtt_subscriber, _frigate_event_mapper
                # Use the cognition_wiring singleton so the same mapper
                # (with its timeline store already injected) is used by
                # both the MQTT subscriber and the composite event mapper
                # in the agent state machine. get_frigate_event_mapper()
                # now checks is_mqtt_configured() too, so an MQTT-only
                # install (no REST url) still gets this same instance
                # rather than a bare uninjected fallback.
                _frigate_event_mapper = get_frigate_event_mapper()
                if _frigate_event_mapper is None:
                    logger.warning(
                        "Frigate MQTT configured but the event mapper could "
                        "not be created — MQTT subscriber not started"
                    )
                else:
                    _frigate_mqtt_subscriber = FrigateMQTTSubscriber(
                        config=frigate_cfg,
                        on_event=_frigate_event_mapper.handle_event,
                    )
                    def start_frigate_mqtt_delayed():
                        import time, asyncio
                        time.sleep(6)  # after HA stream
                        try:
                            loop = asyncio.new_event_loop()
                            loop.run_until_complete(_frigate_mqtt_subscriber.start())
                            loop.run_forever()
                        except Exception as e:
                            logger.warning(f"Frigate MQTT start failed: {e}")
                    frigate_starter = threading.Thread(target=start_frigate_mqtt_delayed, daemon=True)
                    frigate_starter.start()
                    logger.info("Frigate MQTT subscriber starting in background...")
        except Exception as e:
            logger.warning(f"Frigate MQTT subscriber not started: {e}")

    # Shutdown event: stop background services
    @app.on_event("shutdown")
    async def shutdown_event():
        """Stop background services on app shutdown."""
        global _scheduler_executor
        global _config_watcher

        # C4-03: stop the idle heartbeat first so no sweep starts while the
        # stores below are being closed.
        try:
            await stop_thread_tick_heartbeat(app)
        except Exception as e:
            logger.warning(f"Failed to stop thread tick heartbeat: {e}")

        # Stop config watcher (T5a.2 + T7e.1)
        if _config_watcher is not None:
            try:
                _config_watcher.stop()
                _config_watcher = None
                logger.info("Config watcher stopped")
            except Exception as e:
                logger.warning(f"Failed to stop config watcher: {e}")

        # Stop scheduler
        if _scheduler_executor is not None:
            try:
                _scheduler_executor.stop()
                logger.info("Scheduler stopped")
            except Exception as e:
                logger.warning(f"Failed to stop scheduler: {e}")

        # Stop ingestion
        try:
            from ..ingestion.service import get_ingestion_service
            service = get_ingestion_service()
            service.stop()
            logger.info("Ingestion service stopped")
        except Exception as e:
            logger.warning(f"Failed to stop ingestion: {e}")

        # Stop terminal session manager (stops the reaper, kills live sessions)
        try:
            from ..streaming.session_manager import get_terminal_manager
            await get_terminal_manager().shutdown()
            logger.info("Terminal session manager shut down")
        except Exception as e:
            logger.warning(f"Failed to shut down terminal session manager: {e}")

        # Phase 2: Stop HA WebSocket event stream
        try:
            from ..integrations.cognition_wiring import _ha_event_stream, shutdown as cognition_shutdown
            if _ha_event_stream is not None:
                await _ha_event_stream.stop()
                logger.info("HA event stream stopped")
            cognition_shutdown()
        except Exception as e:
            logger.warning(f"Failed to stop HA event stream: {e}")

        # Stop Frigate MQTT subscriber
        try:
            global _frigate_mqtt_subscriber
            if _frigate_mqtt_subscriber is not None:
                await _frigate_mqtt_subscriber.stop()
                _frigate_mqtt_subscriber = None
                logger.info("Frigate MQTT subscriber stopped")
        except Exception as e:
            logger.warning(f"Failed to stop Frigate MQTT subscriber: {e}")

        # Phase 4: Stop Wyoming voice agent
        try:
            global _wyoming_agent
            if _wyoming_agent is not None:
                await _wyoming_agent.stop()
                _wyoming_agent = None
                logger.info("Wyoming voice agent stopped")
        except Exception as e:
            logger.warning(f"Failed to stop Wyoming voice agent: {e}")

        # Voice mode (O2): stop the audio pipeline coordinator (also closes
        # any open /api/audio/stream WebSocket via the ingress stop()).
        audio_coordinator = getattr(app.state, "audio_coordinator", None)
        if audio_coordinator is not None:
            try:
                await audio_coordinator.stop()
                app.state.audio_coordinator = None
                logger.info("Audio pipeline coordinator stopped")
            except Exception as e:
                logger.warning(f"Failed to stop audio pipeline coordinator: {e}")
        # Cleared unconditionally: a stop() that raised still leaves a
        # coordinator nobody should answer has_speaker() from.
        from .routes.audio import set_audio_pipeline as _clear_audio_pipeline
        _clear_audio_pipeline(None)

        # Voice mode (O3): drop the hub's pipeline reference on shutdown so
        # it can never mint barge-in tokens against a stopped coordinator.
        tts_hub = getattr(app.state, "tts_egress", None)
        if tts_hub is not None:
            tts_hub.set_pipeline(None)

        # Close Frigate tools singleton client
        try:
            from ..integrations.frigate.frigate_tools import close_client as close_frigate_client
            await close_frigate_client()
            logger.info("Frigate tools client closed")
        except Exception as e:
            logger.warning(f"Failed to close Frigate tools client: {e}")
    
    logger.info("Halbert Dashboard API created")
    
    return app


# Module-level app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("HALBERT_PORT", "8000"))
    host = os.environ.get("HALBERT_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
