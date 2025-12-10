from __future__ import annotations
import json
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, Iterable, List, Optional
from .severity import map_priority
try:
    from systemd import journal as sd_journal  # type: ignore
except Exception:  # pragma: no cover
    sd_journal = None  # type: ignore

"""
Journald follower using python-systemd Reader when available; falls back to
`journalctl --follow --output=json` otherwise.
Normalization aligns with docs/Genesis and docs/Phase1 telemetry schema.
This is a generator that yields normalized event dicts.
"""


def _normalize(entry: Dict[str, Any]) -> Dict[str, Any]:
    ts = entry.get("__REALTIME_TIMESTAMP")
    # journalctl json provides _SOURCE_REALTIME_TIMESTAMP sometimes; for simplicity, use current time
    ts_iso = datetime.now(timezone.utc).isoformat()
    priority = entry.get("PRIORITY")
    severity = map_priority(int(priority)) if priority is not None else "info"
    unit = entry.get("_SYSTEMD_UNIT")
    identifier = entry.get("SYSLOG_IDENTIFIER")
    message = entry.get("MESSAGE", "")
    host = entry.get("_HOSTNAME", "")
    return {
        "ts": ts_iso,
        "source": "journald",
        "host": host,
        "type": "log",
        "subsystem": unit or identifier or "system",
        "severity": severity,
        "message": message,
        "data": {
            "unit": unit,
            "identifier": identifier,
            "pid": entry.get("_PID"),
            "priority": int(priority) if priority is not None else None,
        },
        "tags": ["log"],
    }


def _load_cursor(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            c = f.read().strip()
            return c or None
    except Exception:
        return None


def _save_cursor(path: Optional[str], cursor: Optional[str]) -> None:
    if not path or not cursor:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(cursor)
    except Exception:
        pass


def _follow_journalctl(filters: Optional[Dict[str, Any]] = None, cursor_path: Optional[str] = None, persist_every: int = 100) -> Iterable[Dict[str, Any]]:
    """
    Follow journald and yield normalized events.
    filters: optional dict with keys: identifiers (List[str]), units (List[str]), severities (List[str])
    """
    cmd = [
        "journalctl",
        "--follow",
        "--output=json",
    ]
    prev_cursor = _load_cursor(cursor_path)
    if prev_cursor:
        cmd.extend(["--after-cursor", prev_cursor])
    else:
        cmd.extend(["--since", "now"])  # start from now
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    assert proc.stdout is not None
    idents = set((filters or {}).get("identifiers", []) or [])
    units = set((filters or {}).get("units", []) or [])
    sevset = set((filters or {}).get("severities", []) or [])
    n = 0
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        evt = _normalize(entry)
        # Persist cursor occasionally
        cur = entry.get("__CURSOR")
        n += 1
        if cur and (n % persist_every == 0):
            _save_cursor(cursor_path, cur)
        # Filter
        if idents and (evt["data"].get("identifier") not in idents):
            # If identifier not in filter and unit also not in units, skip
            if not (units and (evt["data"].get("unit") in units)):
                continue
        if units and (evt["data"].get("unit") not in units) and not (evt["data"].get("identifier") in idents):
            continue
        if sevset and (evt["severity"] not in sevset):
            continue
        yield evt


def _follow_reader(filters: Optional[Dict[str, Any]] = None, cursor_path: Optional[str] = None, persist_every: int = 100) -> Iterable[Dict[str, Any]]:
    r = sd_journal.Reader()  # type: ignore
    # Apply matches
    if filters:
        for ident in (filters.get("identifiers") or []):
            try:
                r.add_match(SYSLOG_IDENTIFIER=ident)  # type: ignore
            except Exception:
                pass
        for unit in (filters.get("units") or []):
            try:
                r.add_match(_SYSTEMD_UNIT=unit)  # type: ignore
            except Exception:
                pass
    # Start from cursor if available; else tail
    started = False
    cur0 = _load_cursor(cursor_path)
    if cur0:
        try:
            r.seek_cursor(cur0)  # type: ignore
            r.get_next()  # type: ignore
            started = True
        except Exception:
            started = False
    if not started:
        try:
            r.seek_tail()  # type: ignore
        except Exception:
            try:
                r.seek_realtime(datetime.now())  # type: ignore
            except Exception:
                pass
    try:
        r.get_previous()  # type: ignore
    except Exception:
        pass

    sevset = set((filters or {}).get("severities", []) or [])
    n = 0
    while True:
        try:
            if r.wait(1000) == sd_journal.APPEND:  # type: ignore
                for entry in r:
                    try:
                        evt = _normalize(entry)
                        # Persist cursor occasionally
                        cur = entry.get("__CURSOR")
                        n += 1
                        if cur and (n % persist_every == 0):
                            _save_cursor(cursor_path, cur)
                        if sevset and (evt["severity"] not in sevset):
                            continue
                        yield evt
                    except Exception:
                        continue
        except KeyboardInterrupt:
            break
        except Exception:
            # On any reader error, break out to allow caller to restart
            break


def follow_journal(filters: Optional[Dict[str, Any]] = None, cursor_path: Optional[str] = None, persist_every: int = 100) -> Iterable[Dict[str, Any]]:
    if sd_journal is not None:
        try:
            yield from _follow_reader(filters, cursor_path=cursor_path, persist_every=persist_every)
            return
        except Exception:
            pass
    # Fallback
    yield from _follow_journalctl(filters, cursor_path=cursor_path, persist_every=persist_every)
