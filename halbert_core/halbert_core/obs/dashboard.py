from __future__ import annotations
import glob
import json
import os
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Tuple

from ..config.drift import diff_snapshots
from ..utils.paths import data_subdir
from ..obs.tracing import trace_call

DASH_DIR = data_subdir("dashboard")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _snapshots_dir() -> str:
    return data_subdir("config", "snapshots")


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _latest_two_snapshots() -> Tuple[List[Dict[str, Any]] | None, List[Dict[str, Any]] | None]:
    d = _snapshots_dir()
    if not os.path.isdir(d):
        return None, None
    files = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json") and f != "latest.json"]
    files.sort()
    if len(files) < 2:
        return None, None
    return _load_json(files[-2]), _load_json(files[-1])


@trace_call("dashboard.build_config_changes")
def build_config_changes() -> str:
    """Write recent config changes JSON for the dashboard."""
    _ensure_dir(DASH_DIR)
    prev, curr = _latest_two_snapshots()
    out: Dict[str, Any] = {"changes": []}
    if prev and curr:
        changes = diff_snapshots(prev, curr)
        out["changes"] = changes
    path = os.path.join(DASH_DIR, "config_changes.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return path


def _latest_journald_files(limit: int = 2) -> List[str]:
    base = data_subdir("raw", "journald")
    if not os.path.isdir(base):
        return []
    # Collect all jsonl files under latest day
    paths = glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True)
    paths.sort()
    return paths[-limit:]


@trace_call("dashboard.build_journald_summary")
def build_journald_summary() -> str:
    """Aggregate basic counts of severities and identifiers from recent journald JSONL."""
    _ensure_dir(DASH_DIR)
    sev = Counter()
    ident = Counter()
    for f in _latest_journald_files(4):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        evt = json.loads(line)
                        sev.update([evt.get("severity", "info")])
                        ident.update([((evt.get("data") or {}).get("identifier") or "unknown")])
                    except Exception:
                        continue
        except Exception:
            continue
    out = {"severity": sev, "identifiers": ident}
    # Convert Counters to plain dicts
    out = {k: dict(v) for k, v in out.items()}
    path = os.path.join(DASH_DIR, "journald_summary.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return path


def _latest_hwmon_files(limit: int = 2) -> List[str]:
    base = data_subdir("raw", "hwmon")
    if not os.path.isdir(base):
        return []
    paths = glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True)
    paths.sort()
    return paths[-limit:]


@trace_call("dashboard.build_hwmon_temps")
def build_hwmon_temps() -> str:
    """Compute latest temperature readings per label from recent hwmon files."""
    _ensure_dir(DASH_DIR)
    latest: Dict[str, float] = {}
    for f in _latest_hwmon_files(4):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        evt = json.loads(line)
                        if evt.get("source") != "hwmon":
                            continue
                        data = evt.get("data") or {}
                        label = data.get("label") or "sensor"
                        temp = data.get("temp_c")
                        if isinstance(temp, (int, float)):
                            latest[label] = float(temp)
                    except Exception:
                        continue
        except Exception:
            continue
    out = {"temps": latest}
    path = os.path.join(DASH_DIR, "hwmon_temps.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return path


@trace_call("dashboard.build_policy_status")
def build_policy_status() -> str:
    """Phase 2: Show policy status and recent denials from audit log."""
    _ensure_dir(DASH_DIR)
    try:
        from ..policy.loader import load_policy
        pol = load_policy()
        tools_summary = {}
        for tool_name, tcfg in (pol.get("tools") or {}).items():
            tools_summary[tool_name] = {
                "allow": tcfg.get("allow", True),
                "simulation_required": tcfg.get("simulation_required", False),
                "rollback_required": tcfg.get("rollback_required", False),
                "approvals": tcfg.get("approvals", []),
            }
        out = {
            "default_allow": pol.get("default_allow", True),
            "tools": tools_summary,
        }
        path = os.path.join(DASH_DIR, "policy_status.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return path
    except Exception as e:
        # Fallback: policy engine unavailable
        path = os.path.join(DASH_DIR, "policy_status.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"error": str(e)}, f, ensure_ascii=False, indent=2)
        return path


@trace_call("dashboard.build_recommended_actions")
def build_recommended_actions() -> str:
    """Stub: derive recommended actions from changes/summary (Phase 1)."""
    _ensure_dir(DASH_DIR)
    recs: List[Dict[str, Any]] = []
    # Example: if many errors for an identifier, recommend check status
    try:
        sum_path = os.path.join(DASH_DIR, "journald_summary.json")
        if os.path.exists(sum_path):
            summary = _load_json(sum_path)
            ids = summary.get("identifiers", {})
            sev = summary.get("severity", {})
            if sev.get("error", 0) > 0:
                # Pick the top error-prone identifier
                top_ident = next(iter(sorted(ids.items(), key=lambda kv: kv[1], reverse=True)), ("unknown", 0))[0]
                recs.append({
                    "title": "Investigate frequent errors",
                    "identifier": top_ident,
                    "dry_run": f"journalctl -u {top_ident} -p err --since '1 hour ago'",
                })
    except Exception:
        pass
    path = os.path.join(DASH_DIR, "recommended_actions.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"actions": recs}, f, ensure_ascii=False, indent=2)
    return path


def build_all() -> List[str]:
    paths = [
        build_config_changes(),
        build_journald_summary(),
        build_hwmon_temps(),
        build_policy_status(),
        build_recommended_actions(),
    ]
    return paths
