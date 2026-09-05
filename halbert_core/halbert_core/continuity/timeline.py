# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Timeline Store — persistent event ledger for the sentient home.

Every significant event in the house is persisted here:
- HA state changes (device, old_state, new_state, timestamp)
- Frigate events (camera, label, zones, timestamp)
- Scanner discoveries (type, severity, timestamp)
- Findings and proposals (id, type, status, timestamp)
- Occupancy changes (who, direction, timestamp)
- User commands (what, when)
- Cognitive tick decisions (perceived, reasoned, acted, outcome)

This is the memory backbone that enables:
- The morning report to include home state
- The orchestration timeline (flight recorder)
- The correlation engine (what happened before X?)
- The behavior learning engine (pattern inference from history)

Privacy: all data stays local. Never sent to cloud.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.continuity.timeline")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS timeline_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_timeline_timestamp ON timeline_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_timeline_type ON timeline_events(event_type);
CREATE INDEX IF NOT EXISTS idx_timeline_source ON timeline_events(source);
CREATE INDEX IF NOT EXISTS idx_timeline_entity ON timeline_events(entity_id);
"""


@dataclass
class TimelineEvent:
    """A single event in the persistent timeline."""
    timestamp: float
    event_type: str  # ha_state_change, frigate_event, scanner_finding,
                     # finding, proposal, occupancy_change, user_command,
                     # cognitive_tick, security_event
    source: str = ""  # what produced it (ha, frigate, scanner, agent, etc.)
    entity_id: str = ""  # HA entity ID, camera name, finding ID, etc.
    severity: str = "info"  # info, warning, critical
    title: str = ""
    description: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TimelineStore:
    """SQLite-backed persistent event timeline.

    Thread-safe via a write lock. Reads are concurrent (SQLite allows
    multiple readers). The store is append-only — events are never
    deleted (except by explicit cleanup).

    Args:
        db_path: Path to the SQLite database file. Defaults to
            ~/.local/share/halbert/timeline.db (or HALBERT_DATA_DIR).
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            from ..utils.paths import data_dir as _data_dir

            data_dir = Path(_data_dir())
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "timeline.db")
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def record(self, event: TimelineEvent) -> int:
        """Record an event in the timeline.

        Returns:
            The row ID of the inserted event.
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute(
                    """INSERT INTO timeline_events
                       (timestamp, event_type, source, entity_id, severity,
                        title, description, data, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event.timestamp,
                        event.event_type,
                        event.source,
                        event.entity_id,
                        event.severity,
                        event.title,
                        event.description,
                        json.dumps(event.data, default=str),
                        time.time(),
                    ),
                )
                conn.commit()
                return cursor.lastrowid
            finally:
                conn.close()

    def record_simple(
        self,
        event_type: str,
        source: str = "",
        entity_id: str = "",
        severity: str = "info",
        title: str = "",
        description: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Convenience method to record an event without building a TimelineEvent."""
        return self.record(TimelineEvent(
            timestamp=time.time(),
            event_type=event_type,
            source=source,
            entity_id=entity_id,
            severity=severity,
            title=title,
            description=description,
            data=data or {},
        ))

    def query(
        self,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        entity_id: Optional[str] = None,
        severity: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query the timeline with optional filters.

        Args:
            event_type: Filter by event type.
            source: Filter by source.
            entity_id: Filter by entity ID.
            severity: Filter by severity.
            since: Only events after this timestamp.
            until: Only events before this timestamp.
            limit: Max results (default 100, newest first).

        Returns:
            List of event dicts, newest first.
        """
        conditions = []
        params: List[Any] = []

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if entity_id:
            conditions.append("entity_id = ?")
            params.append(entity_id)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        if since is not None:
            conditions.append("timestamp >= ?")
            params.append(since)
        if until is not None:
            conditions.append("timestamp <= ?")
            params.append(until)

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"""SELECT * FROM timeline_events
                    WHERE {where}
                    ORDER BY timestamp DESC
                    LIMIT ?""",
                params,
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]
        finally:
            conn.close()

    def get_recent(self, hours: float = 24, limit: int = 100) -> List[Dict[str, Any]]:
        """Get events from the last N hours."""
        since = time.time() - (hours * 3600)
        return self.query(since=since, limit=limit)

    def get_correlations(
        self,
        entity_id: str,
        window_seconds: float = 1800,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get events that occurred within a time window of a specific entity.

        Useful for questions like "what happened around the time the
        front door was unlocked?"

        Args:
            entity_id: The entity to find correlations around.
            window_seconds: Time window before and after each event (default 30min).
            limit: Max results.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            # First find timestamps of events for this entity
            target_rows = conn.execute(
                "SELECT timestamp FROM timeline_events WHERE entity_id = ? ORDER BY timestamp DESC LIMIT 50",
                (entity_id,),
            ).fetchall()

            if not target_rows:
                return []

            results = []
            for target in target_rows:
                ts = target["timestamp"]
                rows = conn.execute(
                    """SELECT * FROM timeline_events
                       WHERE timestamp BETWEEN ? AND ?
                       AND entity_id != ?
                       ORDER BY timestamp ASC LIMIT ?""",
                    (ts - window_seconds, ts + window_seconds, entity_id, limit),
                ).fetchall()
                for row in rows:
                    results.append(self._row_to_dict(row))

            # Deduplicate by ID
            seen = set()
            unique = []
            for event in results:
                if event["id"] not in seen:
                    seen.add(event["id"])
                    unique.append(event)
            return unique[:limit]
        finally:
            conn.close()

    def cleanup(self, max_age_days: int = 90) -> int:
        """Delete events older than max_age_days.

        Returns:
            Number of deleted rows.
        """
        cutoff = time.time() - (max_age_days * 86400)
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute(
                    "DELETE FROM timeline_events WHERE timestamp < ?",
                    (cutoff,),
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def stats(self) -> Dict[str, Any]:
        """Get basic stats about the timeline."""
        conn = sqlite3.connect(self.db_path)
        try:
            total = conn.execute("SELECT COUNT(*) FROM timeline_events").fetchone()[0]
            by_type = conn.execute(
                "SELECT event_type, COUNT(*) as count FROM timeline_events GROUP BY event_type ORDER BY count DESC"
            ).fetchall()
            oldest = conn.execute("SELECT MIN(timestamp) FROM timeline_events").fetchone()[0]
            newest = conn.execute("SELECT MAX(timestamp) FROM timeline_events").fetchone()[0]
            return {
                "total_events": total,
                "by_type": {row[0]: row[1] for row in by_type},
                "oldest_timestamp": oldest,
                "newest_timestamp": newest,
            }
        finally:
            conn.close()

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a database row to a dict, parsing the JSON data field."""
        d = dict(row)
        try:
            d["data"] = json.loads(d.get("data", "{}"))
        except (json.JSONDecodeError, TypeError):
            d["data"] = {}
        return d
