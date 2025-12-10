from __future__ import annotations
"""
Golden tasks harness (minimal) for Phase 1. See `docs/Phase1/golden-tasks.md`.
This harness:
- Checks for presence of telemetry (hwmon/journald) files where applicable
- Exercises tools in dry-run mode (write_config, schedule_cron)
- Produces a JSON report under data/eval/ with per-task statuses (pass/fail/skip)

Statuses:
- pass: criteria met or dry-run produced expected outputs
- fail: unexpected exception or output missing
- skip: prerequisite data not available (e.g., no journald/hwmon files yet)
"""

from datetime import datetime, timezone
import glob
import json
import os
from typing import Any, Dict

from ..utils.paths import data_subdir
from ..tools.base import ToolRequest
from ..tools.write_config import WriteConfig
from ..tools.schedule_cron import ScheduleCron
from ..index.chroma_index import Index


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result(status: str, note: str = "", details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": status, "note": note}
    if details:
        out["details"] = details
    return out


def _has_files(pattern: str) -> bool:
    paths = glob.glob(pattern, recursive=True)
    return len(paths) > 0


def _task_temps() -> Dict[str, Any]:
    # Check for any hwmon telemetry files
    base = data_subdir("raw", "hwmon")  # ensures directory exists under user data dir
    # We don't want to create false positives; check with a glob for *.jsonl
    # but allow pass if any files exist
    has_any = _has_files(os.path.join(base, "**", "*.jsonl"))
    if not has_any:
        return _result("skip", "no hwmon telemetry files found; run ingest-hwmon first")
    return _result("pass", "found hwmon telemetry files")


def _task_health_summary() -> Dict[str, Any]:
    base = data_subdir("raw", "journald")
    has_any = _has_files(os.path.join(base, "**", "*.jsonl"))
    if not has_any:
        return _result("skip", "no journald telemetry files found; run ingest-journald first")
    return _result("pass", "found journald telemetry files")


def _task_write_config_dry_run() -> Dict[str, Any]:
    try:
        tool = WriteConfig()
        # Use a JSON example by default; path may not exist (treated as empty baseline)
        req = ToolRequest(
            tool=tool.name,
            request_id=f"golden-{_now_iso()}",
            dry_run=True,
            confirm=False,
            inputs={
                "path": os.path.join(data_subdir("tmp"), "example.json"),
                "changes": {"settings": {"fan_threshold": 75}},
                "backup": False,
            },
        )
        res = tool.execute(req)
        ok = res.ok and isinstance(res.outputs.get("diff"), str)
        return _result("pass" if ok else "fail", "write_config dry-run executed", {"applied": res.outputs.get("applied", False)})
    except Exception as e:
        return _result("fail", f"exception: {e}")


def _task_schedule_cron_dry_run() -> Dict[str, Any]:
    try:
        tool = ScheduleCron()
        req = ToolRequest(
            tool=tool.name,
            request_id=f"golden-{_now_iso()}",
            dry_run=True,
            confirm=False,
            inputs={
                "name": "halbert-daily-summary",
                "schedule": "0 8 * * *",
                "command": "halbert summary --yesterday",
            },
        )
        res = tool.execute(req)
        ok = res.ok and isinstance(res.outputs.get("diff"), str)
        return _result("pass" if ok else "fail", "schedule_cron dry-run executed", {"installed": res.outputs.get("installed", False)})
    except Exception as e:
        return _result("fail", f"exception: {e}")


def _task_index_query() -> Dict[str, Any]:
    try:
        idx = Index(None)  # memory fallback always available
        res = idx.query("health status", k=3)
        # Memory fallback returns a list (possibly empty); do not fail on empty
        return _result("pass", "index query executed", {"results": len(res)})
    except Exception as e:
        return _result("fail", f"exception: {e}")


def run_all() -> Dict[str, Any]:
    tasks = {
        "temps_readout": _task_temps(),
        "health_summary": _task_health_summary(),
        "write_config_dry_run": _task_write_config_dry_run(),
        "schedule_cron_dry_run": _task_schedule_cron_dry_run(),
        "index_query": _task_index_query(),
        # Future: explain_failed_service, detect_thermal_anomaly with basic heuristics
    }
    # Aggregate
    totals = {"pass": 0, "fail": 0, "skip": 0}
    for t in tasks.values():
        s = t.get("status", "skip")
        totals[s] = totals.get(s, 0) + 1
    out: Dict[str, Any] = {
        "ts": _now_iso(),
        "summary": totals,
        "tasks": tasks,
    }
    # Persist report
    rep_dir = data_subdir("eval")
    name = f"report-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path = os.path.join(rep_dir, name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        out["report_path"] = path
    except Exception:
        # Non-fatal
        pass
    return out
