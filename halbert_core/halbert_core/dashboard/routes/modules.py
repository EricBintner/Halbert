"""
Module API routes — list available modules and fetch module data.

Security notes:
- Module props are LLM-controlled (they arrive from the frontend, which
  relays LLM-emitted module invocations), so every file-access fetcher
  restricts paths to an allowlist of roots (/etc/, ~/.config/, and the
  host-config staging dir). Paths that resolve (via pathlib .resolve(),
  which also resolves symlinks) outside those roots are rejected with 403;
  missing files return 404.
- All handlers are synchronous `def` endpoints so FastAPI runs them in a
  threadpool. None of the blocking calls here (psutil polling, subprocess
  journald reads, file I/O) ever hit the event loop directly.
- drive-health reports partition usage via psutil, NOT real SMART/temperature
  telemetry; the payload carries telemetry_source="psutil-partitions" so
  consumers do not mistake it for drive-health data. SMART/temperature is
  platform-dependent and not available cross-platform.

Phase 8 / T8b.1.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from ...modules.registry import get_module_registry
from ...tools.register_host_project import STAGING_DIR as HOST_CONFIG_STAGING_DIR

logger = logging.getLogger("halbert.dashboard.modules")

router = APIRouter()


def _allowed_roots() -> List[Path]:
    """Resolved allowlist roots for file-backed module reads."""
    home = Path.home()
    roots = [
        Path("/etc"),
        home / ".config",
        Path(HOST_CONFIG_STAGING_DIR),
    ]
    return [r.expanduser().resolve() for r in roots]


def _resolve_allowed_path(raw_path: str) -> Path:
    """Resolve a client-supplied path and enforce the allowlist.

    Returns the resolved absolute path, or raises:
        403 — the resolved path escapes every allowlisted root (including
              via symlink), or
        404 — the resolved path does not exist / is not a regular file.
    """
    resolved = Path(raw_path).expanduser().resolve()
    roots = _allowed_roots()
    if not any(resolved == root or root in resolved.parents for root in roots):
        logger.warning(f"Rejected module file access outside allowlist: {resolved}")
        raise HTTPException(
            status_code=403,
            detail="Path is outside the allowed roots (/etc, ~/.config, host-config staging)",
        )
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {raw_path}")
    return resolved


@router.get("/modules")
def list_modules() -> Dict[str, Any]:
    """List all available modules."""
    registry = get_module_registry()
    modules = [m.to_dict() for m in registry.list_all()]
    return {"status": "ok", "modules": modules}


@router.get("/modules/{module_name}/data")
def get_module_data(
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
            return _fetch_config_diff(path, finding_id)
        elif module_name == "vitals":
            return _fetch_vitals(timeframe)
        elif module_name == "drive-health":
            return _fetch_drive_health()
        elif module_name == "evidence":
            return _fetch_evidence(source, cursor, query)
        else:
            raise HTTPException(status_code=400, detail=f"No data fetcher for '{module_name}'")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Module data fetch failed for '{module_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _fetch_config_diff(path: str, finding_id: str) -> Dict[str, Any]:
    """Fetch config diff data (allowlisted roots only)."""
    if not path:
        raise HTTPException(status_code=400, detail="path parameter required")
    resolved = _resolve_allowed_path(path)

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
        return {
            "status": "ok",
            "path": str(resolved),
            "content": content,
            "finding_id": finding_id,
        }
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))


def _fetch_vitals(timeframe: str) -> Dict[str, Any]:
    """Fetch system vitals data."""
    import psutil
    import time as _time

    # Blocking psutil poll — safe here because this handler is a sync
    # endpoint, so FastAPI runs it in a threadpool off the event loop.
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


def _fetch_drive_health() -> Dict[str, Any]:
    """Fetch drive partition capacity/usage data.

    This is psutil partition usage only — no SMART attributes or
    temperature sensors (not available cross-platform). The
    telemetry_source field makes the data's provenance explicit.
    """
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
        # Not SMART/temperature — partition usage only (platform limit).
        "telemetry_source": "psutil-partitions",
        "drives": partitions,
    }


def _fetch_evidence(source: str, cursor: str, query: str) -> Dict[str, Any]:
    """Fetch log evidence data.

    file: sources are restricted to the allowlisted roots; journald:
    sources shell out to journalctl (threadpool-safe here).
    """
    if not source:
        raise HTTPException(status_code=400, detail="source parameter required")

    # For v1, support reading from log files
    if source.startswith("file:"):
        resolved = _resolve_allowed_path(source[5:])
        try:
            lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
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
