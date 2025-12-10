from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from .job import Job
from ..utils.paths import data_subdir
from ..obs.tracing import trace_call


class SchedulerEngine:
    """
    Phase 2 scheduler engine (minimal).
    Manages job queue, persistence, and execution lifecycle.
    """
    def __init__(self, persist_dir: Optional[str] = None):
        self.persist_dir = persist_dir or data_subdir("scheduler")
        os.makedirs(self.persist_dir, exist_ok=True)
        self.jobs: Dict[str, Job] = {}
        self._load_jobs()

    def _job_path(self, job_id: str) -> str:
        return os.path.join(self.persist_dir, f"{job_id}.json")

    def _load_jobs(self) -> None:
        """Load persisted jobs from disk."""
        if not os.path.isdir(self.persist_dir):
            return
        for fname in os.listdir(self.persist_dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.persist_dir, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                job = Job(**data)
                self.jobs[job.id] = job
            except Exception:
                continue

    def _persist_job(self, job: Job) -> None:
        """Persist job state to disk."""
        path = self._job_path(job.id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(job.__dict__, f, ensure_ascii=False, indent=2)

    @trace_call("scheduler.add_job")
    def add_job(self, job: Job) -> None:
        """Add a job to the queue."""
        if not job.created_at:
            job.created_at = datetime.now(timezone.utc).isoformat()
        self.jobs[job.id] = job
        self._persist_job(job)

    @trace_call("scheduler.get_job")
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by ID."""
        return self.jobs.get(job_id)

    @trace_call("scheduler.list_jobs")
    def list_jobs(self, state: Optional[str] = None) -> List[Job]:
        """List jobs, optionally filtered by state."""
        jobs = list(self.jobs.values())
        if state:
            jobs = [j for j in jobs if j.state == state]
        return sorted(jobs, key=lambda j: (j.priority, j.created_at or ""))

    @trace_call("scheduler.cancel_job")
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job."""
        job = self.jobs.get(job_id)
        if not job or job.is_terminal():
            return False
        job.state = "cancelled"
        job.completed_at = datetime.now(timezone.utc).isoformat()
        self._persist_job(job)
        return True

    @trace_call("scheduler.update_job_state")
    def update_job_state(self, job_id: str, state: str, error: Optional[str] = None) -> None:
        """Update job state and persist."""
        job = self.jobs.get(job_id)
        if not job:
            return
        job.state = state
        if state == "running" and not job.started_at:
            job.started_at = datetime.now(timezone.utc).isoformat()
        if state in ("completed", "failed", "cancelled"):
            job.completed_at = datetime.now(timezone.utc).isoformat()
        if error:
            job.error = error
        self._persist_job(job)
