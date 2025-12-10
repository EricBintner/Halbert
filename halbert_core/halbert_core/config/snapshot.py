from __future__ import annotations
import os
import json
from datetime import datetime, timezone
from typing import Dict, List, Any
from .manifest import Manifest
from .parser import parse as parse_config
from ..ingestion.redaction import redact_text
from ..utils.paths import data_subdir
from ..obs.tracing import trace_call

"""
Config Snapshot helper (Phase 1)
- Loads manifest
- Iterates include globs (minus exclude), parses files into canonical JSON
- Writes raw text and canonical JSON to data/config/
- Returns a summary list
"""

RAW_DIR = data_subdir("config", "raw")
CANON_DIR = data_subdir("config", "canon")
SNAP_DIR = data_subdir("config", "snapshots")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

@trace_call("config.snapshot")
def snapshot(manifest_path: str) -> List[Dict[str, Any]]:
    man = Manifest.from_file(manifest_path)
    files = man.iter_paths()
    ts = datetime.now(timezone.utc).isoformat()
    out: List[Dict[str, Any]] = []
    _ensure_dir(RAW_DIR)
    _ensure_dir(CANON_DIR)
    _ensure_dir(SNAP_DIR)

    for p in files:
        try:
            canon = parse_config(p)
            raw_txt = None
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    raw_txt = f.read()
            except Exception:
                raw_txt = None
            h = canon.get("hash", "")
            if raw_txt is not None and h:
                safe_txt = redact_text(raw_txt)
                with open(os.path.join(RAW_DIR, f"{h}.txt"), "w", encoding="utf-8") as f:
                    f.write(safe_txt)
            if h:
                with open(os.path.join(CANON_DIR, f"{h}.json"), "w", encoding="utf-8") as f:
                    json.dump(canon, f, ensure_ascii=False, indent=2)
            out.append({"ts": ts, "path": p, "hash": h, "kind": canon.get("kind", "text")})
        except Exception as e:
            out.append({"ts": ts, "path": p, "error": str(e)})
    # Persist snapshot summary for drift detection
    snap_path = os.path.join(SNAP_DIR, f"{ts.replace(':', '_')}.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    # Update latest.json pointer (write a copy)
    with open(os.path.join(SNAP_DIR, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out
