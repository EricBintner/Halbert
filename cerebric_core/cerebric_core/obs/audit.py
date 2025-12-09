from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict
import hashlib
from ..utils.paths import log_subdir

"""
Audit logger for tool executions (dry-run/apply) per Phase 1 schemas.
Writes JSON lines to <log_dir>/audit/YYYY/MM/DD/<tool>.jsonl
Adds tamper-evident hash chain per file (prev_hash -> hash).
"""


def write_audit(tool: str, mode: str, request_id: str, ok: bool, summary: str = "", **extra: Dict[str, Any]) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    base_dir = log_subdir("audit", datetime.now().strftime("%Y"), datetime.now().strftime("%m"), datetime.now().strftime("%d"))
    path = os.path.join(base_dir, f"{tool}.jsonl")
    rec: Dict[str, Any] = {
        "ts": ts,
        "tool": tool,
        "mode": mode,
        "request_id": request_id,
        "ok": ok,
        "summary": summary,
    }
    rec.update(extra or {})
    # Hash chain: compute prev_hash by reading last line if exists
    prev_hash = None
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                last = None
                for line in f:
                    last = line
                if last:
                    try:
                        prev = json.loads(last.decode("utf-8"))
                        prev_hash = prev.get("hash")
                    except Exception:
                        prev_hash = None
        except Exception:
            prev_hash = None
    rec["prev_hash"] = prev_hash
    # Compute current record hash on stable serialization excluding 'hash'
    to_hash = dict(rec)
    ser = json.dumps(to_hash, sort_keys=True, ensure_ascii=False).encode("utf-8")
    h = hashlib.sha256()
    if prev_hash:
        h.update(prev_hash.encode("utf-8"))
    h.update(ser)
    rec["hash"] = h.hexdigest()
    rec["chain"] = "sha256"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path
