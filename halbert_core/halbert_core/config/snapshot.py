# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
from __future__ import annotations
import os
import json
from datetime import datetime, timezone
from typing import Dict, List, Any
from .manifest import Manifest
from .parser import parse as parse_config
from ..ingestion.redaction import redact_lines, redact_parsed, redact_text
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


# The canonical JSON carries the same file twice over -- once parsed into
# `sections`/`tree`, once as a full-text `lines` array -- so writing it
# verbatim put every credential the raw sink had just redacted back on disk
# one line later. CANON_DIR is not staged into a searchable scope, so this was
# never an index leak, but it is plaintext credentials written by the pipeline
# whose stated job includes removing them, and drift.py and edge_extractor.py
# both read it.
#
# `path`, `hash` and `kind` are addressing, not content, and are left alone.
# `hash` especially: parser.parse() computes it over the *original* bytes and
# drift.py compares it to decide whether a file changed at all. A hash taken
# over redacted content would still be self-consistent, so drift would keep
# working while comparing the wrong thing -- the failure would be invisible.


def _redact_canon(canon: Dict[str, Any]) -> Dict[str, Any]:
    """Redact a parsed config's values, leaving its shape and hash intact."""
    out = dict(canon)
    for field in ("sections", "tree"):
        if field in out:
            out[field] = redact_parsed(out[field])
    lines = out.get("lines")
    if isinstance(lines, list):
        # Rejoined and redacted as one document, because the shapes that
        # matter here span lines -- a plist's `<key>` and its `<string>`, a
        # YAML block scalar's body. `redact_lines` guarantees the count, so
        # each record keeps the `n` that edge_extractor.py and citations use.
        texts = redact_lines([str(ln.get("text", "")) for ln in lines])
        out["lines"] = [
            {**ln, "text": text} for ln, text in zip(lines, texts)
        ]
    return out

@trace_call("config.snapshot")
def snapshot(manifest_path: str, *, redact: bool = True) -> List[Dict[str, Any]]:
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
                safe_txt = redact_text(raw_txt) if redact else raw_txt
                with open(os.path.join(RAW_DIR, f"{h}.txt"), "w", encoding="utf-8") as f:
                    f.write(safe_txt)
            if h:
                canon_out = _redact_canon(canon) if redact else canon
                with open(os.path.join(CANON_DIR, f"{h}.json"), "w", encoding="utf-8") as f:
                    json.dump(canon_out, f, ensure_ascii=False, indent=2)
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
