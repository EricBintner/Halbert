from __future__ import annotations
import os
import json
import gzip
from datetime import datetime, timezone
from typing import Dict, Any

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _current_paths(base_dir: str, source: str, ts: datetime) -> str:
    day_dir = os.path.join(base_dir, source, ts.strftime("%Y"), ts.strftime("%m"), ts.strftime("%d"))
    _ensure_dir(day_dir)
    fname = ts.strftime("%H.jsonl")
    return os.path.join(day_dir, fname)


def append_event(base_dir: str, event: Dict[str, Any]) -> str:
    """
    Append an event as a JSON line into a time-partitioned file. Returns the file path.
    Rotation: if file exceeds MAX_FILE_BYTES, compress and roll to next suffix.
    """
    ts_str = event.get("ts")
    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else datetime.now(timezone.utc)
    source = event.get("source", "unknown")
    path = _current_paths(base_dir, source, ts)

    # Rotate if needed
    if os.path.exists(path) and os.path.getsize(path) > MAX_FILE_BYTES:
        gz = path + ".gz"
        with open(path, "rb") as f_in, gzip.open(gz, "wb") as f_out:
            f_out.writelines(f_in)
        os.remove(path)

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return path
