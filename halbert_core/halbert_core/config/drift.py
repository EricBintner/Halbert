from __future__ import annotations
import json
import os
from typing import Any, Dict, List, Tuple

"""
Drift detection between two snapshots.
- Snapshot format: list of { ts, path, hash, kind } from snapshot.py
- Load canonical JSONs by hash from data/config/canon/
- Compare sections/keys for ini-like; compare trees for yaml/json; text diffs not computed for Phase 1.
Output: list of changes per path.
"""

CANON_DIR = os.path.join("data", "config", "canon")


def _load_canon(h: str) -> Dict[str, Any] | None:
    p = os.path.join(CANON_DIR, f"{h}.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _diff_dict(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Tuple[Any, Any]]:
    keys = set(old.keys()) | set(new.keys())
    out: Dict[str, Tuple[Any, Any]] = {}
    for k in sorted(keys):
        ov = old.get(k)
        nv = new.get(k)
        if ov != nv:
            out[k] = (ov, nv)
    return out


def _diff_sections(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Dict[str, Tuple[Any, Any]]]:
    secs = set(old.keys()) | set(new.keys())
    out: Dict[str, Dict[str, Tuple[Any, Any]]] = {}
    for s in sorted(secs):
        dif = _diff_dict(old.get(s, {}), new.get(s, {}))
        if dif:
            out[s] = dif
    return out


def diff_snapshots(prev: List[Dict[str, Any]], curr: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Map by path
    prev_map = {e["path"]: e for e in prev if "hash" in e}
    curr_map = {e["path"]: e for e in curr if "hash" in e}
    paths = sorted(set(prev_map.keys()) | set(curr_map.keys()))
    changes: List[Dict[str, Any]] = []
    for path in paths:
        pe = prev_map.get(path)
        ce = curr_map.get(path)
        if not pe and ce:
            changes.append({"path": path, "change": "added", "hash": ce.get("hash")})
            continue
        if pe and not ce:
            changes.append({"path": path, "change": "removed", "hash": pe.get("hash")})
            continue
        if pe and ce and pe.get("hash") != ce.get("hash"):
            old = _load_canon(pe.get("hash")) if pe.get("hash") else None
            new = _load_canon(ce.get("hash")) if ce.get("hash") else None
            detail: Dict[str, Any] | None = None
            if old and new:
                kind = new.get("kind") or old.get("kind")
                if kind in {"ini"} or "sections" in new:
                    detail = {"sections": _diff_sections(old.get("sections", {}), new.get("sections", {}))}
                elif kind in {"yaml", "json"} and "tree" in new and "tree" in old:
                    detail = {"keys": _diff_dict(old.get("tree", {}), new.get("tree", {}))}
            changes.append({
                "path": path,
                "change": "modified",
                "old": pe.get("hash"),
                "new": ce.get("hash"),
                "detail": detail or {},
            })
    return changes
