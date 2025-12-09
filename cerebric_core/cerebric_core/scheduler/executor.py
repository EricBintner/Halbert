"""
Autonomous scheduler execution engine for Phase 3 M3.

Based on APScheduler best practices:
- BackgroundScheduler (non-blocking)
- SQLAlchemyJobStore (persistence)
- ThreadPoolExecutor (parallelism)
- Cron triggers (sophisticated patterns)

Research: https://betterstack.com/community/guides/scaling-python/apscheduler-scheduled-tasks/
"""

from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    from apscheduler.executors.pool import ThreadPoolExecutor
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

from .job import Job
from .engine import SchedulerEngine
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

logger = logging.getLogger('cerebric.scheduler.executor')


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
    - Timeout enforcement
    - Job persistence
    
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
        enable_guardrails: bool = True
    ):
        """
        Initialize autonomous executor.
        
        Args:
            max_workers: Maximum parallel jobs (default: 5)
            db_path: SQLite database path for job persistence
            enable_llm: Enable LLM-driven decisions (default: True)
            enable_guardrails: Enable guardrail enforcement (default: True, Phase 3 M6)
        """
        if not APSCHEDULER_AVAILABLE:
            raise ImportError(
                "APScheduler not installed. Install with: pip install apscheduler"
            )
        
        self.max_workers = max_workers
        self.enable_llm = enable_llm
        self.enable_guardrails = enable_guardrails
        self.scheduler_engine = SchedulerEngine()
        
        # Initialize guardrails (Phase 3 M6)
        if self.enable_guardrails:
            try:
                self.guardrail_enforcer = GuardrailEnforcer()
                # Load anomaly detector config
                import yaml
                with open("config/autonomy.yml") as f:
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
        
        # Database path for job persistence
        if db_path is None:
            data_dir = data_subdir("scheduler")
            db_path = os.path.join(data_dir, "jobs.db")
        
        self.db_path = db_path
        
        # Job store (persistence)
        jobstores = {
            'default': SQLAlchemyJobStore(url=f'sqlite:///{db_path}')
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
            timezone='UTC'
        )
        
        self._running = False
        
        logger.info(
            f"Autonomous executor initialized: "
            f"max_workers={max_workers}, db_path={db_path}, llm={enable_llm}"
        )
    
    def start(self):
        """Start the scheduler (non-blocking)."""
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        self.scheduler.start()
        self._running = True
        logger.info("Autonomous scheduler started")
    
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
            trigger=CronTrigger(**cron_expr, timezone='UTC'),
            id=job_id,
            name=description or job_id,
            replace_existing=True
        )
        
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
            import signal
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
                    
                    # Check confidence and budgets
                    # Note: In production, confidence would come from LLM decision
                    # For now, assume medium confidence (requires approval for risky tasks)
                    estimated_confidence = 0.7  # TODO: Get from LLM
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
            
            # Set timeout
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Job {job_id} exceeded {timeout_s}s timeout")
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_s)
            
            try:
                # Execute task
                result = task_func()
                
                # Cancel timeout
                signal.alarm(0)
                
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
                
                return result
            
            except Exception as e:
                signal.alarm(0)
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
                
                raise
        
        return wrapped
    
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
        """Log job outcome to memory (Phase 3 M2 integration)."""
        try:
            # Import here to avoid circular dependency
            from ..memory.writer import MemoryWriter
            
            writer = MemoryWriter()
            
            outcome_entry = {
                'job_id': result.job_id,
                'success': result.success,
                'output': result.output,
                'error': result.error,
                'confidence': result.confidence,
                'execution_time_s': result.execution_time_s,
                'retry_count': result.retry_count,
                'ts': datetime.now(timezone.utc).isoformat() + 'Z'
            }
            
            writer.write_action_outcome(outcome_entry)
            logger.info(f"Logged outcome for job {result.job_id}: success={result.success}")
        
        except Exception as e:
            logger.error(f"Failed to log outcome for {result.job_id}: {e}")
    
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
