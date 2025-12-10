"""
Job monitoring API routes.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

router = APIRouter()


@router.get("")
async def list_jobs(state: str | None = None) -> List[Dict[str, Any]]:
    """
    List all scheduled jobs.
    
    Args:
        state: Filter by state (pending, running, completed, failed)
    """
    try:
        from ...scheduler.engine import SchedulerEngine
        from ...scheduler.executor import AutonomousExecutor
        
        # Get persisted jobs
        scheduler = SchedulerEngine()
        jobs = scheduler.list_jobs(state=state)
        
        # Get scheduled jobs (APScheduler)
        try:
            executor = AutonomousExecutor()
            executor.start()
            scheduled = executor.get_scheduled_jobs()
            executor.stop(wait=False)
        except:
            scheduled = []
        
        # Merge information
        result = []
        for job in jobs:
            job_info = {
                'id': job.id,
                'task': job.task,
                'schedule': job.schedule,
                'state': job.state,
                'priority': job.priority,
                'created_at': job.created_at,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'error': job.error,
                'retries': job.retries,
                'max_retries': job.max_retries
            }
            
            # Add next_run from APScheduler if available
            for sched_job in scheduled:
                if sched_job['id'] == job.id:
                    job_info['next_run'] = sched_job['next_run']
                    break
            
            result.append(job_info)
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}")
async def get_job_details(job_id: str) -> Dict[str, Any]:
    """Get detailed information about a job."""
    try:
        from ...scheduler.engine import SchedulerEngine
        
        scheduler = SchedulerEngine()
        job = scheduler.get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return {
            'id': job.id,
            'task': job.task,
            'schedule': job.schedule,
            'state': job.state,
            'priority': job.priority,
            'inputs': job.inputs,
            'created_at': job.created_at,
            'started_at': job.started_at,
            'completed_at': job.completed_at,
            'error': job.error,
            'retries': job.retries,
            'max_retries': job.max_retries,
            'timeout_s': job.timeout_s
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running or pending job."""
    try:
        from ...scheduler.engine import SchedulerEngine
        
        scheduler = SchedulerEngine()
        success = scheduler.cancel_job(job_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Job not found or already terminal")
        
        return {
            'success': True,
            'message': f'Job {job_id} cancelled'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
