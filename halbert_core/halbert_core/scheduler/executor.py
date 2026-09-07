# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Autonomous scheduler execution engine for Phase 3 M3.

Based on APScheduler best practices:
- BackgroundScheduler (non-blocking)
- MemoryJobStore (jobs are re-registered at every boot; see below)
- ThreadPoolExecutor (parallelism)
- Cron triggers (sophisticated patterns)

Why the APScheduler store is in memory (C4-01): ``_wrap_task`` hands
APScheduler a local closure, and a persistent store pickles the job's
callable — so the SQLAlchemyJobStore this module started with refused every
``add_job`` on a started scheduler ("This Job cannot be serialized"). No
dashboard job ever registered. Every caller re-registers its jobs at boot
anyway; durable status and history live in the SchedulerEngine's JSON
records, not in APScheduler.

Research: https://betterstack.com/community/guides/scaling-python/apscheduler-scheduled-tasks/
"""

from __future__ import annotations
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.jobstores.memory import MemoryJobStore
    from apscheduler.executors.pool import ThreadPoolExecutor
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

from .job import Job
from .engine import SchedulerEngine
from .restart_budget import RestartBudget, RestartDecision
from .run_receipts import RunReceiptStore
from ..utils.retry import exponential_backoff_retry, STANDARD_TASK_POLICY
from ..utils.paths import data_subdir
from ..obs.tracing import trace_call
from ..autonomy import (
    GuardrailEnforcer,
    GuardrailViolation,
    BudgetTracker,
    BudgetExceeded,
    AnomalyDetector,
    RecoveryExecutor
)

logger = logging.getLogger('halbert.scheduler.executor')


def _call_with_timeout(func: Callable[[], Any], timeout_s: Optional[float], job_id: str) -> Any:
    """Run ``func()`` on a helper thread and wait at most ``timeout_s``.

    Raises ``TimeoutError`` when the deadline passes; the task thread is a
    daemon and is left to finish on its own (a thread cannot be killed, and
    the previous SIGALRM approach only ever worked on the main thread, which
    APScheduler's worker pool is not). ``timeout_s`` of ``None`` or ``<= 0``
    waits without a deadline. Exceptions from ``func`` propagate unchanged.
    """
    outcome: Dict[str, Any] = {}

    def runner():
        try:
            outcome['result'] = func()
        except BaseException as exc:  # re-raised on the calling thread
            outcome['error'] = exc

    worker = threading.Thread(target=runner, name=f"halbert-job-{job_id}", daemon=True)
    worker.start()
    worker.join(timeout_s if timeout_s and timeout_s > 0 else None)
    if worker.is_alive():
        raise TimeoutError(f"Job {job_id} exceeded {timeout_s}s timeout")
    if 'error' in outcome:
        raise outcome['error']
    return outcome.get('result')


@dataclass
class JobResult:
    """Result of autonomous job execution."""
    job_id: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    confidence: float = 0.0
    execution_time_s: float = 0.0
    retry_count: int = 0


class AutonomousExecutor:
    """
    Phase 3 M3: Autonomous job executor with LLM integration.
    
    Features:
    - APScheduler for cron execution
    - Exponential backoff retry
    - LLM-driven decision making
    - Memory integration for outcomes
    - Timeout enforcement (thread-based, so it works on the worker pool)
    - Job status/history persistence (SchedulerEngine JSON records)
    
    Example:
        executor = AutonomousExecutor()
        executor.start()
        
        # Schedule daily maintenance at 2 AM
        executor.schedule_cron_job(
            job_id='daily_maintenance',
            task_func=run_maintenance,
            cron_expr={'hour': 2, 'minute': 0}
        )
    """
    
    def __init__(
        self,
        max_workers: int = 5,
        db_path: Optional[str] = None,
        enable_llm: bool = True,
        enable_guardrails: bool = True,
        timezone: str = 'UTC'
    ):
        """
        Initialize autonomous executor.

        Args:
            max_workers: Maximum parallel jobs (default: 5)
            db_path: Kept for call compatibility. APScheduler jobs are no
                longer persisted (see the module docstring); the path is
                recorded on ``self.db_path`` and nothing is written there.
            enable_llm: Enable LLM-driven decisions (default: True)
            enable_guardrails: Enable guardrail enforcement (default: True, Phase 3 M6)
            timezone: Timezone for cron triggers (default: UTC; use IANA name or "local")
        """
        if not APSCHEDULER_AVAILABLE:
            raise ImportError(
                "APScheduler not installed. Install with: pip install apscheduler"
            )
        
        self.max_workers = max_workers
        self.enable_llm = enable_llm
        self.enable_guardrails = enable_guardrails
        self.timezone = timezone
        self.scheduler_engine = SchedulerEngine()

        # Packet 03 B1: pre-execution run receipts (JSON-backed, atomic
        # fsync — deliberately not SQLite, matching the SchedulerEngine
        # convention) and the sliding-window restart budget that bounds boot
        # re-runs of interrupted jobs. The receipts are a *pre-execution
        # marker*, not the outcome ledger that was deliberately removed
        # (audit F1) — keep them minimal or the same objection returns.
        # The lock serializes receipt writes across the worker pool: the
        # store's whole-file flush is not safe under concurrent mutations.
        self._receipts_lock = threading.Lock()
        self.receipts = RunReceiptStore(
            os.path.join(data_subdir("scheduler"), "receipts.json")
        )
        self.restart_budget = RestartBudget()
        self._restart_ledger_path = os.path.join(
            data_subdir("scheduler"), "restarts.json"
        )
        self._restart_ledger = self._load_restart_ledger()
        #: Jobs whose boot recovery found an interrupted receipt; they get
        #: one budget-checked re-run when their callable re-registers.
        self._boot_recovery_pending: set = set()
        
        # Initialize guardrails (Phase 3 M6)
        if self.enable_guardrails:
            try:
                self.guardrail_enforcer = GuardrailEnforcer()
                # Load anomaly detector config
                import yaml
                from ..autonomy.guardrails import _resolve_autonomy_path
                with open(_resolve_autonomy_path()) as f:
                    autonomy_config = yaml.safe_load(f)
                self.anomaly_detector = AnomalyDetector(autonomy_config["anomalies"])
                self.recovery_executor = RecoveryExecutor(autonomy_config["recovery"])
                logger.info("Guardrails enabled for autonomous execution")
            except Exception as e:
                logger.warning(f"Failed to initialize guardrails: {e}. Continuing without guardrails.")
                self.enable_guardrails = False
                self.guardrail_enforcer = None
                self.anomaly_detector = None
                self.recovery_executor = None
        else:
            self.guardrail_enforcer = None
            self.anomaly_detector = None
            self.recovery_executor = None
        
        # Recorded only: the SchedulerEngine above owns persistence.
        if db_path is None:
            db_path = os.path.join(data_subdir("scheduler"), "jobs.db")
        self.db_path = db_path
        
        # Job store: in memory. A persistent store pickles the callable and
        # the wrapped closures cannot be pickled (C4-01); jobs are
        # re-registered at every boot regardless.
        jobstores = {
            'default': MemoryJobStore()
        }
        
        # Executors (parallelism)
        executors = {
            'default': ThreadPoolExecutor(max_workers)
        }
        
        # Job defaults
        job_defaults = {
            'coalesce': True,  # Combine missed runs
            'max_instances': 1,  # Prevent concurrent instances
            'misfire_grace_time': 60  # Allow 60s late execution
        }
        
        # Initialize APScheduler
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=self.timezone
        )
        
        self._running = False
        
        logger.info(
            f"Autonomous executor initialized: "
            f"max_workers={max_workers}, db_path={db_path}, llm={enable_llm}"
        )
    
    def start(self):
        """Start the scheduler (non-blocking).

        Packet 03 B1: before any job is (re-)registered, receipts left
        ``running`` by a dead owner are marked ``interrupted``. The jobs
        they name go into ``_boot_recovery_pending`` and get one bounded,
        restart-budget-checked re-run when their callable re-registers
        (jobs are re-registered at every boot; see the C4-01 module note).
        """
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._recover_receipts_on_boot()
        self.scheduler.start()
        self._running = True
        logger.info("Autonomous scheduler started")

    # -- packet 03 B1: boot recovery ---------------------------------------

    def _recover_receipts_on_boot(self) -> None:
        """Interrupt dead-owner running receipts; queue one re-run per job."""
        try:
            recovered = self.receipts.recover_on_boot()
        except Exception as e:
            logger.warning(f"Boot receipt recovery failed (non-fatal): {e}")
            return
        if not recovered:
            return
        pending = set()
        for rid in recovered:
            job_id = self.receipts.receipt(rid).get("job_id")
            if job_id:
                pending.add(job_id)
        self._boot_recovery_pending = pending
        logger.info(
            f"Boot recovery: {len(recovered)} interrupted receipt(s), "
            f"re-run queued for {sorted(pending)}"
        )

    def _load_restart_ledger(self) -> Dict[str, List[float]]:
        """Per-job restart epochs, surviving reboots (crash-loop across
        boots is the case the budget exists for). Malformed entries are
        dropped loudly-by-omission; the ledger is bookkeeping, not truth."""
        try:
            with open(self._restart_ledger_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        ledger: Dict[str, List[float]] = {}
        for job_id, stamps in raw.items():
            if isinstance(stamps, list):
                ledger[job_id] = [
                    float(t) for t in stamps if isinstance(t, (int, float))
                ]
        return ledger

    def _persist_restart_ledger(self) -> None:
        """Write the ledger, pruning entries outside the budget window."""
        now = time.time()
        window = self.restart_budget.window_s
        pruned = {
            job_id: [t for t in stamps if now - t <= window]
            for job_id, stamps in self._restart_ledger.items()
        }
        pruned = {job_id: stamps for job_id, stamps in pruned.items() if stamps}
        self._restart_ledger = pruned
        tmp = f"{self._restart_ledger_path}.{os.getpid()}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(pruned, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._restart_ledger_path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _maybe_arm_boot_recovery(
        self,
        job_id: str,
        task_func: Callable,
        max_retries: int,
        timeout_s: int,
    ) -> None:
        """Arm the boot re-run for a just-registered job that had an
        interrupted receipt, if the restart budget allows it.

        Bounded: a job leaves the pending set on its first registration this
        boot (one re-run per boot), and the sliding window over the durable
        ledger is what stops a crash-looping job from re-running forever.
        On BLOCK the executor logs a structured ``restart_budget_exhausted``
        line and holds in safe-mode instead of looping.
        """
        if job_id not in self._boot_recovery_pending:
            return
        self._boot_recovery_pending.discard(job_id)
        if max_retries <= 0:
            logger.info(
                f"Boot re-run skipped for {job_id}: job has no retry budget"
            )
            return
        now = time.time()
        restarts = self._restart_ledger.get(job_id, [])
        decision = self.restart_budget.evaluate(restarts, now)
        if decision is not RestartDecision.ALLOW:
            recent = [
                t for t in restarts if now - t <= self.restart_budget.window_s
            ]
            logger.error(
                "restart_budget_exhausted job_id=%s restarts_in_window=%d "
                "max_per_hour=%d window_s=%g decision=%s",
                job_id,
                len(recent),
                self.restart_budget.max_per_hour,
                self.restart_budget.window_s,
                decision.value,
            )
            # Hold in safe-mode rather than loop: the budget being spent is
            # the crash-loop signal, so the next restart attempt must come
            # from a human decision, not from the next boot.
            if self.guardrail_enforcer is not None:
                self.guardrail_enforcer.enter_safe_mode(
                    "restart_budget_exhausted: job "
                    f"{job_id} blocked from a {len(recent) + 1}th restart "
                    f"within {self.restart_budget.window_s:g}s"
                )
            return
        self._restart_ledger.setdefault(job_id, []).append(now)
        self._persist_restart_ledger()
        recovery_id = f"{job_id}:recovery"
        self.schedule_one_time(
            job_id=recovery_id,
            task_func=task_func,
            run_at=datetime.now(timezone.utc),
            max_retries=max_retries,
            timeout_s=timeout_s,
        )
        logger.info(
            f"Boot recovery: one bounded re-run armed for {job_id} "
            f"as one-time job {recovery_id}"
        )
    
    def stop(self, wait: bool = True):
        """
        Stop the scheduler.
        
        Args:
            wait: Wait for running jobs to complete (default: True)
        """
        if not self._running:
            return
        
        self.scheduler.shutdown(wait=wait)
        self._running = False
        logger.info("Autonomous scheduler stopped")
    
    @trace_call("executor.schedule_cron_job")
    def schedule_cron_job(
        self,
        job_id: str,
        task_func: Callable,
        cron_expr: Dict[str, Any],
        max_retries: int = 3,
        timeout_s: int = 600,
        description: str = ''
    ) -> str:
        """
        Schedule a cron job with retry logic.
        
        Args:
            job_id: Unique job identifier
            task_func: Function to execute
            cron_expr: Cron expression dict, e.g.:
                {'day_of_week': 'mon-fri', 'hour': 9, 'minute': 0}
                {'hour': 2, 'minute': 0}  # Daily at 2 AM
                {'minute': '*/15'}  # Every 15 minutes
            max_retries: Maximum retry attempts (default: 3)
            timeout_s: Timeout in seconds (default: 600)
            description: Human-readable description
        
        Returns:
            Job ID
        
        Example:
            # Every weekday at 9 AM
            executor.schedule_cron_job(
                job_id='weekday_maintenance',
                task_func=run_maintenance,
                cron_expr={'day_of_week': 'mon-fri', 'hour': 9}
            )
            
            # Every 5 minutes during business hours
            executor.schedule_cron_job(
                job_id='frequent_check',
                task_func=check_health,
                cron_expr={'day_of_week': 'mon-fri', 'hour': '9-17', 'minute': '*/5'}
            )
        """
        # Create Job record for tracking
        job = Job(
            id=job_id,
            task=task_func.__name__,
            schedule=str(cron_expr),
            max_retries=max_retries,
            timeout_s=timeout_s
        )
        self.scheduler_engine.add_job(job)
        
        # Wrap task with retry logic
        wrapped_func = self._wrap_task(
            job_id=job_id,
            task_func=task_func,
            max_retries=max_retries,
            timeout_s=timeout_s
        )
        
        # Schedule with APScheduler
        self.scheduler.add_job(
            func=wrapped_func,
            trigger=CronTrigger(**cron_expr, timezone=self.timezone),
            id=job_id,
            name=description or job_id,
            replace_existing=True
        )

        # Packet 03 B1: a job whose previous boot's run was interrupted
        # gets one budget-checked re-run now that its callable is back.
        self._maybe_arm_boot_recovery(job_id, task_func, max_retries, timeout_s)
        logger.info(
            f"Scheduled cron job: {job_id} with expr: {cron_expr}, "
            f"retries: {max_retries}, timeout: {timeout_s}s"
        )
        
        return job_id
    
    @trace_call("executor.schedule_one_time")
    def schedule_one_time(
        self,
        job_id: str,
        task_func: Callable,
        run_at: datetime,
        max_retries: int = 3,
        timeout_s: int = 600
    ) -> str:
        """
        Schedule a one-time job.
        
        Args:
            job_id: Unique job identifier
            task_func: Function to execute
            run_at: Execution time (datetime)
            max_retries: Maximum retry attempts
            timeout_s: Timeout in seconds
        
        Returns:
            Job ID
        """
        job = Job(
            id=job_id,
            task=task_func.__name__,
            schedule=run_at.isoformat(),
            max_retries=max_retries,
            timeout_s=timeout_s
        )
        self.scheduler_engine.add_job(job)
        
        wrapped_func = self._wrap_task(job_id, task_func, max_retries, timeout_s)
        
        self.scheduler.add_job(
            func=wrapped_func,
            trigger='date',
            run_date=run_at,
            id=job_id,
            replace_existing=True
        )

        # Packet 03 B1: one-time jobs participate in boot recovery too (a
        # re-armed recovery run is itself a one-time job).
        self._maybe_arm_boot_recovery(job_id, task_func, max_retries, timeout_s)

        logger.info(f"Scheduled one-time job: {job_id} at {run_at}")
        return job_id
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a scheduled job.
        
        Args:
            job_id: Job identifier
        
        Returns:
            True if cancelled, False if not found
        """
        try:
            self.scheduler.remove_job(job_id)
            self.scheduler_engine.cancel_job(job_id)
            logger.info(f"Cancelled job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False
    
    def get_scheduled_jobs(self) -> List[Dict[str, Any]]:
        """Get list of all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs
    
    def _wrap_task(
        self,
        job_id: str,
        task_func: Callable,
        max_retries: int,
        timeout_s: int
    ) -> Callable:
        """
        Wrap task with retry logic, timeout, and outcome tracking.
        
        Returns:
            Wrapped function
        """
        @exponential_backoff_retry(
            max_attempts=max_retries,
            base_delay=1.0,
            max_delay=60.0,
            jitter=True,
            on_retry=lambda attempt, exc, delay: self._on_retry(
                job_id, attempt, exc, delay
            )
        )
        def wrapped():
            import time
            
            start_time = time.time()
            
            # Phase 3 M6: Check guardrails before execution
            if self.enable_guardrails and self.guardrail_enforcer:
                try:
                    # Check safe-mode
                    if self.guardrail_enforcer.is_safe_mode_active():
                        logger.warning(f"Job {job_id} skipped: safe-mode active")
                        self.scheduler_engine.update_job_state(
                            job_id, 'skipped', error='safe_mode_active'
                        )
                        return None
                    
                    # Check confidence and budgets. Confidence comes from
                    # the job record's inputs when the caller set one, else
                    # medium. (This read an undefined name before C4-01.)
                    job_record = self.scheduler_engine.get_job(job_id)
                    estimated_confidence = 0.7
                    if job_record is not None:
                        try:
                            estimated_confidence = float(
                                (job_record.inputs or {}).get('confidence', 0.7)
                            )
                        except (TypeError, ValueError):
                            estimated_confidence = 0.7
                    estimated_resources = {
                        'cpu_percent': 30,  # Conservative estimate
                        'memory_mb': 512,
                        'time_minutes': timeout_s / 60
                    }
                    
                    allowed, reason = self.guardrail_enforcer.check_all(
                        confidence=estimated_confidence,
                        estimated_resources=estimated_resources,
                        task=job_id
                    )
                    
                    if not allowed:
                        logger.info(f"Job {job_id} requires approval: {reason}")
                        # In production, this would trigger approval workflow
                        # For now, we'll execute but log the approval requirement
                
                except GuardrailViolation as e:
                    logger.error(f"Job {job_id} rejected by guardrails: {e}")
                    self.scheduler_engine.update_job_state(
                        job_id, 'rejected', error=str(e)
                    )
                    if self.anomaly_detector:
                        self.anomaly_detector.record_job_outcome(False, job_id)
                    return None
            
            # Update job state
            self.scheduler_engine.update_job_state(job_id, 'running')

            # Phase 3 M6: Start budget tracking
            budget_tracker = None
            if self.enable_guardrails and self.guardrail_enforcer:
                budget_tracker = BudgetTracker.from_config(
                    self.guardrail_enforcer.config["budgets"]
                )
                budget_tracker.start()

            # Packet 03 B1: persist the 'started' receipt BEFORE the task
            # callable runs — the marker must be on disk before any side
            # effect begins, so a crash mid-run is distinguishable at the
            # next boot (recover_on_boot interrupts dead-owner markers).
            # Locked across the worker pool: the store flushes whole-file.
            with self._receipts_lock:
                receipt_id = self.receipts.mark_started(
                    job_id, owner_pid=os.getpid()
                )

            try:
                # Execute task under the timeout. SIGALRM is main-thread
                # only and APScheduler runs jobs on its worker pool, so the
                # deadline is a thread join, not a signal (C4-01).
                result = _call_with_timeout(task_func, timeout_s, job_id)
                
                # Phase 3 M6: Check budgets during execution
                if budget_tracker:
                    try:
                        budget_tracker.check()
                    except BudgetExceeded as e:
                        logger.error(f"Job {job_id} exceeded budget: {e}")
                        if self.anomaly_detector:
                            self.anomaly_detector.record_job_outcome(False, job_id)
                        raise
                
                # Calculate execution time
                execution_time = time.time() - start_time
                
                # Phase 3 M6: Stop budget tracking
                resource_usage = None
                if budget_tracker:
                    resource_usage = budget_tracker.stop()
                    logger.info(f"Job {job_id} resource usage: {resource_usage}")
                
                # Log outcome
                self._log_outcome(
                    JobResult(
                        job_id=job_id,
                        success=True,
                        output=str(result) if result else None,
                        execution_time_s=execution_time
                    )
                )
                
                # Phase 3 M6: Record successful outcome
                if self.anomaly_detector:
                    self.anomaly_detector.record_job_outcome(True, job_id)
                
                # Update job state
                self.scheduler_engine.update_job_state(job_id, 'completed')

                self._finish_receipt(receipt_id, 'ok')

                return result
            
            except Exception as e:
                execution_time = time.time() - start_time
                
                # Phase 3 M6: Stop budget tracking on failure
                if budget_tracker:
                    try:
                        budget_tracker.stop()
                    except Exception:
                        pass  # Budget tracking failed, but we're already handling an error
                
                # Log failure
                self._log_outcome(
                    JobResult(
                        job_id=job_id,
                        success=False,
                        error=str(e),
                        execution_time_s=execution_time
                    )
                )
                
                # Phase 3 M6: Record failure and check for anomalies
                if self.anomaly_detector:
                    try:
                        self.anomaly_detector.record_job_outcome(False, job_id)
                    except Exception as anomaly_exc:
                        # Anomaly detected (e.g., repeated failures)
                        logger.critical(f"ANOMALY DETECTED: {anomaly_exc}")
                        
                        # Enter safe-mode
                        if self.guardrail_enforcer:
                            self.guardrail_enforcer.enter_safe_mode(
                                f"Anomaly: {anomaly_exc}"
                            )
                        
                        # Trigger recovery
                        if self.recovery_executor:
                            self.recovery_executor.execute_alert_user(
                                f"Job {job_id} triggered anomaly: {anomaly_exc}",
                                severity="critical"
                            )
                
                # Update job state
                self.scheduler_engine.update_job_state(
                    job_id, 'failed', error=str(e)
                )

                self._finish_receipt(receipt_id, 'error', error=str(e))

                raise
        
        return wrapped

    def _finish_receipt(
        self, receipt_id: str, status: str, error: Optional[str] = None
    ) -> None:
        """Record the terminal receipt status. Never raises: a bookkeeping
        failure must not turn a completed job into a failed one — the next
        boot's recover_on_boot treats the stale running marker
        conservatively (interrupted, one budgeted re-run)."""
        try:
            with self._receipts_lock:
                self.receipts.mark_finished(receipt_id, status, error=error)
        except Exception as e:
            logger.warning(
                f"Failed to record receipt {receipt_id} as {status}: {e}"
            )

    def _on_retry(self, job_id: str, attempt: int, exc: Exception, delay: float):
        """Callback for retry attempts."""
        logger.warning(
            f"Job {job_id} retry {attempt} after {delay:.2f}s: {exc}"
        )
        
        # Update retry count
        job = self.scheduler_engine.get_job(job_id)
        if job:
            job.retries = attempt
            self.scheduler_engine._persist_job(job)
    
    def _log_outcome(self, result: JobResult):
        """Record a job outcome.

        The file-backed MemoryWriter was removed (audit F1): it wrote entries that
        MemoryRetrieval could never return. Job outcomes live in the scheduler's own
        store; durable cross-session state belongs in the state ledger
        (``continuity.state_store.StateStore``, MEM-02).
        """
        logger.info(
            f"Job {result.job_id} outcome: success={result.success} "
            f"confidence={result.confidence} time={result.execution_time_s}s"
        )

    def get_status(self) -> Dict[str, Any]:
        """Get executor status (Phase 3 M6: includes guardrail status)."""
        status = {
            'running': self._running,
            'max_workers': self.max_workers,
            'scheduled_jobs': len(self.scheduler.get_jobs()) if self._running else 0,
            'pending_jobs': len(self.scheduler_engine.list_jobs('pending')),
            'completed_jobs': len(self.scheduler_engine.list_jobs('completed')),
            'failed_jobs': len(self.scheduler_engine.list_jobs('failed')),
            'guardrails_enabled': self.enable_guardrails
        }
        
        # Add guardrail status (Phase 3 M6)
        if self.enable_guardrails and self.guardrail_enforcer:
            status['safe_mode_active'] = self.guardrail_enforcer.is_safe_mode_active()
            
            if self.anomaly_detector:
                status['anomalies'] = self.anomaly_detector.get_summary()
            
            if self.recovery_executor:
                status['recovery'] = self.recovery_executor.get_summary()
        
        return status
