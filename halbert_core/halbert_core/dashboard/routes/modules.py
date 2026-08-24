"""
Module API routes — list available modules and fetch module data.

Phase 8 / T8b.1.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from ..modules.registry import get_module_registry

logger = logging.getLogger("halbert.dashboard.modules")

router = APIRouter()


@router.get("/modules")
async def list_modules() -> Dict[str, Any]:
    """List all available modules."""
    registry = get_module_registry()
    modules = [m.to_dict() for m in registry.list_all()]
    return {"status": "ok", "modules": modules}


@router.get("/modules/{module_name}/data")
async def get_module_data(
    module_name: str,
    path: str = Query(None),
    timeframe: str = Query("1h"),
    source: str = Query(None),
    cursor: str = Query(None),
    query: str = Query(None),
    finding_id: str = Query(None),
) -> Dict[str, Any]:
    """Fetch data for a specific module.

    Query params are module-specific:
    - config-diff: path (required), finding_id (optional)
    - vitals: timeframe (default "1h")
    - drive-health: (no params)
    - evidence: source, cursor, query
    """
    registry = get_module_registry()
    module = registry.get(module_name)
    if not module:
        raise HTTPException(status_code=404, detail=f"Module '{module_name}' not found")

    try:
        if module_name == "config-diff":
            return await _fetch_config_diff(path, finding_id)
        elif module_name == "vitals":
            return await _fetch_vitals(timeframe)
        elif module_name == "drive-health":
            return await _fetch_drive_health()
        elif module_name == "evidence":
            return await _fetch_evidence(source, cursor, query)
        else:
            raise HTTPException(status_code=400, detail=f"No data fetcher for '{module_name}'")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Module data fetch failed for '{module_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_config_diff(path: str, finding_id: str) -> Dict[str, Any]:
    """Fetch config diff data."""
    if not path:
        raise HTTPException(status_code=400, detail="path parameter required")
    import os
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {
            "status": "ok",
            "path": path,
            "content": content,
            "finding_id": finding_id,
        }
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_vitals(timeframe: str) -> Dict[str, Any]:
    """Fetch system vitals data."""
    import psutil
    import time as _time

    cpu_percent = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    return {
        "status": "ok",
        "timeframe": timeframe,
        "vitals": {
            "cpu": {
                "percent": cpu_percent,
                "count": psutil.cpu_count(),
            },
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "percent": memory.percent,
                "used": memory.used,
            },
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent,
            },
            "network": {
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
            },
            "timestamp": _time.time(),
        },
    }


async def _fetch_drive_health() -> Dict[str, Any]:
    """Fetch drive health data."""
    import psutil

    partitions = []
    for p in psutil.disk_partitions(all=True):
        try:
            usage = psutil.disk_usage(p.mountpoint) if p.mountpoint else None
            partitions.append({
                "device": p.device,
                "mountpoint": p.mountpoint,
                "fstype": p.fstype,
                "opts": p.opts,
                "total": usage.total if usage else None,
                "used": usage.used if usage else None,
                "free": usage.free if usage else None,
                "percent": usage.percent if usage else None,
            })
        except (PermissionError, OSError):
            partitions.append({
                "device": p.device,
                "mountpoint": p.mountpoint,
                "fstype": p.fstype,
                "error": "permission denied",
            })

    return {
        "status": "ok",
        "drives": partitions,
    }


async def _fetch_evidence(source: str, cursor: str, query: str) -> Dict[str, Any]:
    """Fetch log evidence data."""
    if not source:
        raise HTTPException(status_code=400, detail="source parameter required")

    # For v1, support reading from log files
    import os
    if source.startswith("file:"):
        path = source[5:]
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail=f"Log file not found: {path}")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            # Apply cursor (line range) if specified
            if cursor and "-" in cursor:
                start, _, end = cursor.partition("-")
                try:
                    start_idx = int(start) - 1
                    end_idx = int(end)
                    lines = lines[start_idx:end_idx]
                except ValueError:
                    pass
            # Apply query filter if specified
            if query:
                lines = [l for l in lines if query.lower() in l.lower()]

            return {
                "status": "ok",
                "source": source,
                "cursor": cursor,
                "query": query,
                "lines": [{"line_no": i + 1, "content": l.rstrip()} for i, l in enumerate(lines)],
                "total_lines": len(lines),
            }
        except OSError as e:
            raise HTTPException(status_code=500, detail=str(e))

    # journald source (Linux only)
    if source.startswith("journald:"):
        try:
            import subprocess
            cmd = ["journalctl", "--no-pager", "-n", "50"]
            if cursor:
                cmd.extend(["--since", cursor])
            if query:
                cmd.extend(["-g", query])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            lines = result.stdout.strip().split("\n") if result.stdout else []
            return {
                "status": "ok",
                "source": source,
                "cursor": cursor,
                "query": query,
                "lines": [{"line_no": i + 1, "content": l} for i, l in enumerate(lines)],
                "total_lines": len(lines),
            }
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return {
                "status": "ok",
                "source": source,
                "lines": [],
                "total_lines": 0,
                "note": "journald not available on this system",
            }

    raise HTTPException(status_code=400, detail=f"Unsupported evidence source: {source}")
