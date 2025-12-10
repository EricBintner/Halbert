from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, Any
import os

"""Minimal hwmon collector stub for Phase 1."""

def collect_temp(sensor_path: str, label: str | None = None) -> Dict[str, Any]:
    ts = datetime.now(timezone.utc).isoformat()
    try:
        with open(sensor_path, "r") as f:
            raw = f.read().strip()
        val = float(raw)
        if val > 1000:
            val = val / 1000.0
        return {
            "ts": ts,
            "source": "hwmon",
            "type": "sensor_reading",
            "subsystem": "thermal",
            "severity": "info",
            "message": f"temp={val}",
            "data": {"label": label or "", "temp_c": val},
            "tags": ["thermal"],
        }
    except Exception as e:
        return {
            "ts": ts,
            "source": "hwmon",
            "type": "sensor_reading",
            "subsystem": "thermal",
            "severity": "error",
            "message": str(e),
            "data": {"label": label or ""},
            "tags": ["thermal", "error"],
        }
