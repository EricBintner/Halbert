# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Storage management API routes (Phase 52).

Provides REST API for:
- ChromaDB storage metrics and health
- Orphan detection and cleanup
- Storage location info and recommendations
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from dataclasses import asdict
import logging
import threading
import time

logger = logging.getLogger('halbert.dashboard.storage')

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Background Cleanup State
# ─────────────────────────────────────────────────────────────────────────────
_cleanup_jobs: Dict[str, Dict[str, Any]] = {}
_cleanup_lock = threading.Lock()


class CleanupRequest(BaseModel):
    """Request to start cleanup operation."""
    dry_run: bool = False


class MigrationRequest(BaseModel):
    """Request to migrate ChromaDB to a new location."""
    new_path: str


class MigrationResponse(BaseModel):
    """Response from migration operation."""
    job_id: str
    status: str  # "pending", "copying", "verifying", "completed", "failed"
    source_path: str
    dest_path: str
    total_bytes: int
    copied_bytes: int
    files_total: int
    files_copied: int
    verified: bool
    error: Optional[str] = None
    progress_percent: float = 0.0


class CleanupResponse(BaseModel):
    """Response from cleanup operation."""
    job_id: str
    status: str  # "running", "completed", "failed"
    total_items: int
    completed_items: int
    bytes_freed: int
    bytes_freed_human: str
    error: Optional[str] = None


def _format_bytes(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    if size_bytes < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if abs(size_bytes) < 1024:
            if unit == "B":
                return f"{size_bytes} {unit}"
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} EB"


@router.get("/chromadb")
async def get_chromadb_metrics() -> Dict[str, Any]:
    """
    Get ChromaDB storage metrics and health status.
    
    Returns comprehensive information about:
    - Total storage size
    - Active collections
    - Orphaned data
    - Disk info and type
    - Performance tips
    """
    try:
        from ...storage.chromadb_manager import get_chromadb_manager
        
        manager = get_chromadb_manager()
        metrics = manager.get_storage_metrics()
        
        # Convert dataclasses to dicts
        result = {
            "status": metrics.status.value,
            "location": metrics.location,
            "total_size_bytes": metrics.total_size_bytes,
            "total_size_human": metrics.total_size_human,
            "sqlite_size_bytes": metrics.sqlite_size_bytes,
            "sqlite_size_human": metrics.sqlite_size_human,
            "active_collections": [
                {
                    "name": c.name,
                    "id": c.id,
                    "count": c.count,
                    "size_bytes": c.size_bytes,
                    "size_human": c.size_human
                }
                for c in metrics.active_collections
            ],
            "orphaned_data": metrics.orphaned_data,
            "disk_info": {
                "mount_point": metrics.disk_info.mount_point,
                "total_bytes": metrics.disk_info.total_bytes,
                "free_bytes": metrics.disk_info.free_bytes,
                "used_bytes": metrics.disk_info.used_bytes,
                "disk_type": metrics.disk_info.disk_type.value,
                "total_human": _format_bytes(metrics.disk_info.total_bytes),
                "free_human": _format_bytes(metrics.disk_info.free_bytes),
            },
            "last_cleanup": metrics.last_cleanup,
            "warnings": metrics.warnings,
            "tips": metrics.tips
        }
        
        return result
        
    except ImportError as e:
        logger.error(f"ChromaDB manager import failed: {e}")
        raise HTTPException(status_code=500, detail="ChromaDB manager not available")
    except Exception as e:
        logger.error(f"Failed to get ChromaDB metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chromadb/orphans")
async def list_orphans() -> Dict[str, Any]:
    """
    List orphaned ChromaDB collection directories.
    
    These are directories that exist on disk but are not
    referenced by any active collection in the SQLite database.
    """
    try:
        from ...storage.chromadb_manager import get_chromadb_manager
        
        manager = get_chromadb_manager()
        orphans = manager.list_orphans()
        
        total_size = sum(o.size_bytes for o in orphans)
        
        return {
            "count": len(orphans),
            "total_size_bytes": total_size,
            "total_size_human": _format_bytes(total_size),
            "orphans": [
                {
                    "id": o.id,
                    "path": o.path,
                    "size_bytes": o.size_bytes,
                    "size_human": o.size_human,
                    "modified": o.modified
                }
                for o in orphans
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to list orphans: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chromadb/cleanup")
async def start_cleanup(
    request: CleanupRequest,
    background_tasks: BackgroundTasks
) -> CleanupResponse:
    """
    Start cleanup of orphaned ChromaDB directories.
    
    If dry_run is True, returns what would be deleted without
    actually deleting anything.
    
    The cleanup operation is:
    - Safe: Only deletes orphaned directories
    - Resumable: Tracks progress in state file
    - Non-destructive: Never touches active collections
    """
    try:
        from ...storage.chromadb_manager import get_chromadb_manager
        
        manager = get_chromadb_manager()
        
        if request.dry_run:
            # Synchronous dry run
            state = manager.cleanup_orphans(dry_run=True)
            return CleanupResponse(
                job_id=state.job_id,
                status="completed",
                total_items=len(state.orphans_to_delete),
                completed_items=0,
                bytes_freed=0,
                bytes_freed_human="0 B"
            )
        
        # Check if cleanup already running
        with _cleanup_lock:
            for job_id, job in _cleanup_jobs.items():
                if job.get("status") == "running":
                    return CleanupResponse(
                        job_id=job_id,
                        status="running",
                        total_items=job.get("total_items", 0),
                        completed_items=job.get("completed_items", 0),
                        bytes_freed=job.get("bytes_freed", 0),
                        bytes_freed_human=_format_bytes(job.get("bytes_freed", 0))
                    )
        
        # Start async cleanup
        orphans = manager.list_orphans()
        job_id = f"cleanup-{int(time.time())}"
        
        with _cleanup_lock:
            _cleanup_jobs[job_id] = {
                "status": "running",
                "total_items": len(orphans),
                "completed_items": 0,
                "bytes_freed": 0,
                "error": None
            }
        
        def run_cleanup():
            def progress_callback(completed: int, total: int, bytes_freed: int):
                with _cleanup_lock:
                    if job_id in _cleanup_jobs:
                        _cleanup_jobs[job_id]["completed_items"] = completed
                        _cleanup_jobs[job_id]["bytes_freed"] = bytes_freed
            
            try:
                state = manager.cleanup_orphans(
                    dry_run=False,
                    progress_callback=progress_callback
                )
                with _cleanup_lock:
                    if job_id in _cleanup_jobs:
                        _cleanup_jobs[job_id]["status"] = "completed"
                        _cleanup_jobs[job_id]["completed_items"] = len(state.deleted)
                        _cleanup_jobs[job_id]["bytes_freed"] = state.bytes_freed
                        if state.error:
                            _cleanup_jobs[job_id]["error"] = state.error
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")
                with _cleanup_lock:
                    if job_id in _cleanup_jobs:
                        _cleanup_jobs[job_id]["status"] = "failed"
                        _cleanup_jobs[job_id]["error"] = str(e)
        
        background_tasks.add_task(run_cleanup)
        
        return CleanupResponse(
            job_id=job_id,
            status="running",
            total_items=len(orphans),
            completed_items=0,
            bytes_freed=0,
            bytes_freed_human="0 B"
        )
        
    except Exception as e:
        logger.error(f"Failed to start cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chromadb/cleanup/{job_id}")
async def get_cleanup_status(job_id: str) -> CleanupResponse:
    """Get status of a cleanup job."""
    with _cleanup_lock:
        if job_id not in _cleanup_jobs:
            raise HTTPException(status_code=404, detail="Cleanup job not found")
        
        job = _cleanup_jobs[job_id]
        return CleanupResponse(
            job_id=job_id,
            status=job["status"],
            total_items=job["total_items"],
            completed_items=job["completed_items"],
            bytes_freed=job["bytes_freed"],
            bytes_freed_human=_format_bytes(job["bytes_freed"]),
            error=job.get("error")
        )


@router.get("/chromadb/tips")
async def get_performance_tips() -> Dict[str, Any]:
    """
    Get storage performance tips and recommendations.
    
    Returns guidance on:
    - Optimal storage types for vector databases
    - Memory management for large databases
    - Current disk type assessment
    """
    try:
        from ...storage.chromadb_manager import get_chromadb_manager
        
        manager = get_chromadb_manager()
        tips = manager.get_performance_tips()
        
        return {
            "tips": tips
        }
        
    except Exception as e:
        logger.error(f"Failed to get tips: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chromadb/collections")
async def list_collections() -> Dict[str, Any]:
    """
    List all active ChromaDB collections with details.
    
    Returns collection name, document count, and size.
    """
    try:
        from ...storage.chromadb_manager import get_chromadb_manager
        
        manager = get_chromadb_manager()
        collections = manager.get_active_collections()
        
        total_docs = sum(c.count for c in collections)
        total_size = sum(c.size_bytes for c in collections)
        
        return {
            "total_collections": len(collections),
            "total_documents": total_docs,
            "total_size_bytes": total_size,
            "total_size_human": _format_bytes(total_size),
            "collections": [
                {
                    "name": c.name,
                    "id": c.id,
                    "count": c.count,
                    "size_bytes": c.size_bytes,
                    "size_human": c.size_human
                }
                for c in collections
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Migration Endpoints
# ─────────────────────────────────────────────────────────────────────────────
_migration_jobs: Dict[str, Dict[str, Any]] = {}
_migration_lock = threading.Lock()


@router.post("/chromadb/migrate")
async def start_migration(request: MigrationRequest, background_tasks: BackgroundTasks) -> MigrationResponse:
    """
    Start migrating ChromaDB to a new location.
    
    This operation:
    1. Copies all data to the new location
    2. Verifies the copy is complete
    3. Returns status (user must confirm deletion of old location separately)
    """
    try:
        from ...storage.chromadb_manager import get_chromadb_manager, start_chromadb_migration, MigrationState
        from dataclasses import asdict
        
        manager = get_chromadb_manager()
        current_path = str(manager._chroma_path)
        new_path = request.new_path
        
        # Validate new path
        if not new_path or new_path == current_path:
            raise HTTPException(status_code=400, detail="New path must be different from current path")
        
        # Check if path is writable
        import os
        parent_dir = os.path.dirname(new_path)
        if parent_dir and not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Cannot create directory: {e}")
        
        job_id = f"migrate-{int(time.time())}"
        
        def run_migration():
            def progress_callback(state: MigrationState):
                with _migration_lock:
                    progress = 0.0
                    if state.total_bytes > 0:
                        progress = (state.copied_bytes / state.total_bytes) * 100
                    _migration_jobs[job_id] = {
                        "job_id": state.job_id,
                        "status": state.status,
                        "source_path": state.source_path,
                        "dest_path": state.dest_path,
                        "total_bytes": state.total_bytes,
                        "copied_bytes": state.copied_bytes,
                        "files_total": state.files_total,
                        "files_copied": state.files_copied,
                        "verified": state.verified,
                        "error": state.error,
                        "progress_percent": progress
                    }
            
            result = start_chromadb_migration(current_path, new_path, progress_callback)
            with _migration_lock:
                progress = 0.0
                if result.total_bytes > 0:
                    progress = (result.copied_bytes / result.total_bytes) * 100
                _migration_jobs[job_id] = {
                    "job_id": result.job_id,
                    "status": result.status,
                    "source_path": result.source_path,
                    "dest_path": result.dest_path,
                    "total_bytes": result.total_bytes,
                    "copied_bytes": result.copied_bytes,
                    "files_total": result.files_total,
                    "files_copied": result.files_copied,
                    "verified": result.verified,
                    "error": result.error,
                    "progress_percent": progress
                }
        
        # Initialize job
        with _migration_lock:
            _migration_jobs[job_id] = {
                "job_id": job_id,
                "status": "pending",
                "source_path": current_path,
                "dest_path": new_path,
                "total_bytes": 0,
                "copied_bytes": 0,
                "files_total": 0,
                "files_copied": 0,
                "verified": False,
                "error": None,
                "progress_percent": 0.0
            }
        
        # Run in background
        background_tasks.add_task(run_migration)
        
        return MigrationResponse(**_migration_jobs[job_id])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start migration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chromadb/migrate/{job_id}")
async def get_migration_status(job_id: str) -> MigrationResponse:
    """Get status of a migration operation."""
    with _migration_lock:
        if job_id not in _migration_jobs:
            raise HTTPException(status_code=404, detail="Migration job not found")
        return MigrationResponse(**_migration_jobs[job_id])


@router.delete("/chromadb/migrate/old")
async def delete_old_location() -> Dict[str, Any]:
    """
    Delete the old ChromaDB location after successful migration.
    
    Only works if:
    1. A migration has completed successfully
    2. The migration was verified
    """
    try:
        from ...storage.chromadb_manager import delete_old_chromadb, get_migration_status
        
        status = get_migration_status()
        if not status:
            raise HTTPException(status_code=400, detail="No migration has been performed")
        
        if status.status != "completed" or not status.verified:
            raise HTTPException(status_code=400, detail="Migration not completed or not verified")
        
        success, message = delete_old_chromadb(status.source_path)
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        return {
            "success": True,
            "message": message,
            "deleted_path": status.source_path
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete old location: {e}")
        raise HTTPException(status_code=500, detail=str(e))
