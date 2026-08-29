# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Deterministic config query functions — the primary config access path.

These functions read from the canon DB (``~/.local/share/halbert/config/canon/{hash}.json``)
and apply tier routing before returning.  They are the single source of truth
for both the MCP server and the agent context assembler.

Tier routing
------------
``get_config_value`` applies ``classify_sensitivity`` to decide what to return:

* **Tier 0** (public) or **Tier 1** with ``operational_tier="cloud_ok"``:
  the raw value.
* **Tier 1** with ``operational_tier="local_only"`` or **Tier 2** with
  ``secret_tier="local_only"``:
  a deterministic description via ``describe_secret`` — no raw value.
* **Tier 1** with ``operational_tier="redact"**:
  the value is stripped; only the key and tier are returned.
* **Tier 2** with ``secret_tier="cloud_ok_acknowledged"``:
  the raw value (user explicitly acknowledged the risk).

The other three functions (``get_config_structure``, ``get_config_diff``,
``get_config_dependencies``) return structure only — no values — and are
always cloud-safe.

Staleness
---------
The canon DB is a snapshot.  Before returning a value, the live file's hash
is compared to the canon hash.  If they differ, the file is re-parsed via
``config/parser.py`` so the caller always gets the current value.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from .parser import parse as parse_config
from .sensitivity import classify_sensitivity
from .secure_response import describe_secret
from .snapshot import CANON_DIR, SNAP_DIR
from ..utils.paths import data_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canon DB access
# ---------------------------------------------------------------------------

def _load_latest_snapshot() -> List[Dict[str, Any]]:
    """Load the latest snapshot manifest (path → hash mapping)."""
    latest = os.path.join(SNAP_DIR, "latest.json")
    if not os.path.exists(latest):
        return []
    try:
        with open(latest, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _path_to_hash(path: str) -> Optional[str]:
    """Look up the canon hash for a given host path from the latest snapshot."""
    for entry in _load_latest_snapshot():
        if entry.get("path") == path and "hash" in entry:
            return entry["hash"]
    return None


def _load_canon(h: str) -> Optional[Dict[str, Any]]:
    """Load a canonical JSON record by hash."""
    p = os.path.join(CANON_DIR, f"{h}.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _live_hash(path: str) -> Optional[str]:
    """Compute the SHA-256 hash of the live file, or None if it doesn't exist."""
    if not os.path.exists(path):
        return None
    try:
        import hashlib
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _get_current_canon(path: str) -> Optional[Dict[str, Any]]:
    """Get the current canonical record for ``path``, re-parsing if stale.

    Compares the live file's hash to the canon hash.  If they differ (or
    no canon record exists), re-parses the live file and writes the new
    canon record to the canon DB so subsequent calls don't re-parse.
    """
    canon_hash = _path_to_hash(path)
    live_hash = _live_hash(path)

    if live_hash and (not canon_hash or canon_hash != live_hash):
        # File is stale or not yet snapshotted — re-parse live.
        try:
            canon = parse_config(path)
            # Write the new canon record so subsequent calls don't re-parse.
            _write_canon(path, live_hash, canon)
            return canon
        except Exception as e:
            logger.warning("Failed to re-parse %s: %s", path, e)
            # Fall through to load the stale canon if it exists.

    if canon_hash:
        return _load_canon(canon_hash)
    return None


def _write_canon(path: str, file_hash: str, canon: Dict[str, Any]) -> None:
    """Write a canon record to the canon DB and update the latest snapshot.

    This keeps the canon DB current when files change between snapshot
    runs, so _get_current_canon doesn't re-parse on every call.
    """
    try:
        canon_path = os.path.join(CANON_DIR, f"{file_hash}.json")
        os.makedirs(CANON_DIR, exist_ok=True)
        canon["hash"] = file_hash
        canon["path"] = path
        with open(canon_path, "w", encoding="utf-8") as f:
            json.dump(canon, f, indent=2)
        # Update latest snapshot manifest
        _update_latest_snapshot(path, file_hash)
    except OSError as e:
        logger.debug("Failed to write canon record for %s: %s", path, e)


def _update_latest_snapshot(path: str, file_hash: str) -> None:
    """Update or add an entry in the latest snapshot manifest."""
    latest_path = os.path.join(SNAP_DIR, "latest.json")
    entries = _load_latest_snapshot()
    found = False
    for entry in entries:
        if entry.get("path") == path:
            entry["hash"] = file_hash
            found = True
            break
    if not found:
        entries.append({"path": path, "hash": file_hash})
    try:
        os.makedirs(SNAP_DIR, exist_ok=True)
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
    except OSError as e:
        logger.debug("Failed to update latest snapshot: %s", e)


# ---------------------------------------------------------------------------
# Value extraction from parsed structures
# ---------------------------------------------------------------------------

def _extract_value(canon: Dict[str, Any], key: str) -> Tuple[Optional[Any], str]:
    """Extract a value by key from a parsed config structure.

    Returns ``(value, section_or_context)`` where ``section_or_context``
    describes where the key was found (section name for ini, ``"tree"`` for
    yaml/json, ``"text"`` for text files).

    For ini-like files, searches all sections.  For yaml/json, does a
    top-level key lookup.  For text files, returns ``(None, "text")``.
    """
    kind = canon.get("kind", "text")

    if kind == "ini":
        sections = canon.get("sections", {})
        for section_name, items in sections.items():
            if key in items:
                return items[key], section_name
        # Case-insensitive fallback
        for section_name, items in sections.items():
            for k, v in items.items():
                if k.lower() == key.lower():
                    return v, section_name
        return None, ""

    if kind in ("yaml", "json", "plist"):
        tree = canon.get("tree")
        if isinstance(tree, dict) and key in tree:
            return tree[key], "tree"
        if isinstance(tree, dict):
            for k, v in tree.items():
                if k.lower() == key.lower():
                    return v, "tree"
        return None, ""

    return None, "text"


def _strip_values_from_structure(node: Any) -> Any:
    """Recursively strip values from a parsed structure, keeping keys and shape.

    Returns a structure where every leaf value is replaced with its type name
    (``"str"``, ``"int"``, ``"bool"``, ``"float"``, ``"list"``, ``"dict"``).
    Keys and nesting are preserved.
    """
    if isinstance(node, dict):
        return {k: _strip_values_from_structure(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_strip_values_from_structure(v) for v in node]
    if isinstance(node, bool):
        return "bool"
    if isinstance(node, int):
        return "int"
    if isinstance(node, float):
        return "float"
    if isinstance(node, str):
        return "str"
    if node is None:
        return "null"
    return str(type(node).__name__)


# ---------------------------------------------------------------------------
# Public query API
# ---------------------------------------------------------------------------

def get_config_value(
    path: str,
    key: str,
    *,
    operational_tier: str = "cloud_ok",
    secret_tier: str = "local_only",
    public_files: Optional[Set[str]] = None,
    extra_secret_keys: Optional[List[str]] = None,
    cloud_ok_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Get a config value with tier routing applied.

    Returns a dict with keys: ``path``, ``key``, ``tier``, and either
    ``value`` (for cloud-safe tiers) or ``description`` (for secure tiers).

    Per-key escape hatch: if ``cloud_ok_keys`` is provided and ``key``
    matches one of its entries (case-insensitive, normalized), the value
    is returned raw even when the global ``secret_tier`` is
    ``local_only``. This lets a user expose specific secrets (e.g.
    database passwords) while keeping others local-only.
    """
    canon = _get_current_canon(path)
    if canon is None:
        return {"path": path, "key": key, "error": "file not found or not parseable"}

    value, section = _extract_value(canon, key)
    if value is None and section != "text":
        return {"path": path, "key": key, "error": f"key '{key}' not found"}

    tier = classify_sensitivity(
        key, value, path,
        public_files=public_files,
        extra_secret_keys=extra_secret_keys,
    )

    result: Dict[str, Any] = {
        "path": path,
        "key": key,
        "tier": tier,
        "section": section,
    }

    # --- Per-key escape hatch check ---
    key_is_cloud_ok = False
    if cloud_ok_keys:
        norm_key = key.strip().lower().replace("-", "").replace("_", "")
        for ok_key in cloud_ok_keys:
            if ok_key.strip().lower().replace("-", "").replace("_", "") == norm_key:
                key_is_cloud_ok = True
                break

    # --- Tier 0: always return raw value ---
    if tier == 0:
        result["value"] = value
        return result

    # --- Tier 1: route by operational_tier ---
    if tier == 1:
        if operational_tier == "cloud_ok":
            result["value"] = value
        elif operational_tier == "redact":
            result["redacted"] = True
        else:  # local_only
            result["description"] = describe_secret(key, value, path)
            result["redacted"] = True
        return result

    # --- Tier 2: route by secret_tier ---
    if tier == 2:
        if key_is_cloud_ok or secret_tier == "cloud_ok_acknowledged":
            result["value"] = value
            result["acknowledged"] = True
        else:  # local_only (default)
            result["description"] = describe_secret(key, value, path)
            result["redacted"] = True
        return result

    return result


def get_config_structure(path: str) -> Dict[str, Any]:
    """Get the parsed structure of a config file — keys and shape, no values.

    Always cloud-safe: every leaf value is replaced with its type name.
    """
    canon = _get_current_canon(path)
    if canon is None:
        return {"path": path, "error": "file not found or not parseable"}

    kind = canon.get("kind", "text")
    result: Dict[str, Any] = {
        "path": path,
        "kind": kind,
        "hash": canon.get("hash", ""),
    }

    if kind == "ini":
        sections = canon.get("sections", {})
        result["sections"] = {
            section: {k: _type_name(v) for k, v in items.items()}
            for section, items in sections.items()
        }
    elif kind in ("yaml", "json", "plist"):
        result["tree"] = _strip_values_from_structure(canon.get("tree"))
    else:
        # text: return line count only
        lines = canon.get("lines", [])
        result["line_count"] = len(lines)

    return result


def get_config_diff(since: str = "") -> Dict[str, Any]:
    """Get structured changes since a given snapshot timestamp.

    Returns change types and key names only — no values.  Always cloud-safe.

    Parameters
    ----------
    since
        ISO timestamp of the baseline snapshot.  If empty, diffs against
        the earliest available snapshot.
    """
    from .drift import diff_snapshots, _load_canon as drift_load_canon

    # Load all snapshots and find the baseline + current
    snap_dir = SNAP_DIR
    if not os.path.isdir(snap_dir):
        return {"error": "no snapshots directory", "changes": []}

    snapshots = []
    for fname in sorted(os.listdir(snap_dir)):
        if not fname.endswith(".json") or fname == "latest.json":
            continue
        fpath = os.path.join(snap_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                snapshots.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue

    if len(snapshots) < 2:
        return {"changes": [], "note": "need at least 2 snapshots for diff"}

    # Find baseline: the one matching `since`, or the earliest
    baseline = None
    current = snapshots[-1]
    if since:
        for snap in snapshots:
            if snap and snap[0].get("ts", "").startswith(since):
                baseline = snap
                break
    if baseline is None:
        baseline = snapshots[0]

    changes = diff_snapshots(baseline, current)

    # Strip values from diff details — keep only key names and change types
    safe_changes: List[Dict[str, Any]] = []
    for change in changes:
        safe: Dict[str, Any] = {
            "path": change.get("path"),
            "change": change.get("change"),
        }
        detail = change.get("detail")
        if detail:
            safe_detail: Dict[str, Any] = {}
            for detail_key, detail_val in detail.items():
                if isinstance(detail_val, dict):
                    # sections or keys dict: keep only the key names
                    safe_detail[detail_key] = list(detail_val.keys())
                else:
                    safe_detail[detail_key] = detail_val
            safe["detail"] = safe_detail
        safe_changes.append(safe)

    return {"changes": safe_changes}


def get_config_dependencies(path: str) -> Dict[str, Any]:
    """Get dependency edges for a config file — relationships only, no values.

    Always cloud-safe: uses ``edge_extractor`` which extracts relationships
    (systemd deps, includes, fstab→mount) without sending file content.
    """
    from .edge_extractor import ConfigEdgeExtractor

    extractor = ConfigEdgeExtractor()
    extractor._load()

    # Find edges where this path is the source
    edges: List[Dict[str, Any]] = []
    for canon in extractor._canon_files:
        if canon.get("path") != path:
            continue
        kind = canon.get("kind", "text")
        src_id = f"file:{path}"
        file_edges: List[Any] = []
        if kind == "ini":
            file_edges.extend(extractor._extract_systemd_edges(path, canon))
            file_edges.extend(extractor._extract_ini_file_refs(path, canon))
        else:
            file_edges.extend(extractor._extract_reference_edges(path, canon))
        file_edges.extend(extractor._extract_include_edges(path, canon))
        if path == "/etc/fstab" or path.endswith("fstab"):
            file_edges.extend(extractor._extract_fstab_edges(path, canon))
        file_edges.extend(extractor._extract_dropin_edges(path, canon))

        for edge in file_edges:
            edges.append({
                "source": edge.source,
                "target": edge.target,
                "kind": edge.kind,
                "metadata": edge.metadata,
            })
        break

    return {"path": path, "dependencies": edges}


def _type_name(v: Any) -> str:
    """Return a short type name for a scalar value."""
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if v is None:
        return "null"
    if isinstance(v, dict):
        return "dict"
    if isinstance(v, list):
        return "list"
    return type(v).__name__
