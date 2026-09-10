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
from typing import Any, Dict, List, Optional, Tuple

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


def as_prompt_line(row: Dict[str, Any]) -> str:
    """One ledger row as a citable prompt line: ``[t12] Front door opened``.

    The ``t`` prefix is deliberate. ``observation_id`` is already the
    provenance type used for *retrieval* ids, and the state machine records
    that a plain string cannot be cited at all -- so a ledger reference needs
    to be distinguishable from a retrieval one at a glance and in
    ``_extract_provenance``.

    Falls back to the entity id when a row carries no title: an untitled row
    rendering as a bare ``[t12]`` would be a citation to nothing, which is
    worse than a rough description.

    Newlines are stripped here as well as at the sink. The sink is the right
    place for it and this is the last place it can be got wrong, and the cost
    of doing it twice is nothing.
    """
    rid = row.get("id")
    text = (row.get("title") or "").strip()
    if not text:
        text = (row.get("entity_id") or row.get("event_type") or "an event").strip()
    text = " ".join(text.split())
    return f"[t{rid}] {text}"


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
        self._prune_to_retention()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
            finally:
                conn.close()

    #: CD-5 kept 90 days. Pruning here rather than on a schedule because the
    #: store has to be constructed before anything can write to it, so this
    #: runs on every daemon start with no scheduler dependency. A machine that
    #: never restarts still grows -- a periodic job is tasked under MIND-1.
    RETENTION_DAYS = 90

    def _prune_to_retention(self) -> None:
        """Drop rows past the retention window. Never fatal.

        A store that cannot prune is still a usable store, and refusing to
        open it would take the integrations down with it -- the same rule as
        get_timeline_store() returning None rather than raising.
        """
        try:
            removed = self.cleanup(max_age_days=self.RETENTION_DAYS)
        except Exception as e:
            logger.warning(f"Timeline retention prune failed ({type(e).__name__}: {e})")
            return
        if removed:
            logger.info(
                f"Timeline: pruned {removed} row(s) older than "
                f"{self.RETENTION_DAYS} days"
            )

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

    #: Event types with a new/update/end lifecycle, where one tracked object
    #: produces several rows. Only Frigate has one; everything else is one row
    #: per occurrence, and filtering those to "end" would count none of them.
    _LIFECYCLE_EVENT_TYPES = ("frigate_event",)

    def count_by_entity(
        self,
        since: float,
        until: Optional[float] = None,
        event_type: Optional[str] = None,
    ) -> Dict[str, Tuple[int, float, float]]:
        """Recurrence per entity in a window: ``{entity_id: (count, first, last)}``.

        The arithmetic behind CD-3's selection. Deterministic on purpose: "this
        van, three times, with timestamps" is a fact, where clustering chat
        topics yields "docker" and "the thing we tried".

        Frigate rows are counted on ``end`` rather than ``new``
        (``DECISIONS.md`` 2026-09-06). One ``end`` per tracked object dedupes
        exactly as one ``new`` does, but Frigate assigns ``sub_label`` -- the
        plate or the face, the thing that makes it *that* van rather than *a*
        van -- only after an object is first tracked. Counting ``new`` grouped
        everything as ``front_door:person``.

        Rows with no ``entity_id`` are skipped: an empty group key is not an
        entity, and letting it through would produce a phantom row that
        recurs constantly.
        """
        lifecycle = ",".join("?" for _ in self._LIFECYCLE_EVENT_TYPES)
        where = [
            "timestamp >= ?",
            "entity_id != ''",
            # A lifecycle row counts only at its end; everything else counts
            # once per row.
            f"""(event_type NOT IN ({lifecycle})
                 OR json_extract(data, '$.type') = 'end')""",
        ]
        params: List[Any] = [since, *self._LIFECYCLE_EVENT_TYPES]
        if until is not None:
            where.append("timestamp <= ?")
            params.append(until)
        if event_type:
            where.append("event_type = ?")
            params.append(event_type)

        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                f"""SELECT entity_id, COUNT(*), MIN(timestamp), MAX(timestamp)
                    FROM timeline_events
                    WHERE {' AND '.join(where)}
                    GROUP BY entity_id""",
                params,
            ).fetchall()
        finally:
            conn.close()
        return {r[0]: (r[1], r[2], r[3]) for r in rows}

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

    #: Row kinds that are *about a person* rather than about the machine.
    #: An occupancy row is someone's arrival or departure; the state row that
    #: produced it names the same entity. A disk-health event names no person
    #: and is machine-state history, so subject erasure does not touch it.
    PERSON_SCOPED_EVENT_TYPES = ("occupancy_change", "ha_state_change")

    def forget_subject(self, entity_id: str) -> int:
        """Erase the rows this ledger holds *about* one entity.

        ``timeline_events`` has no ``request_id``, so ``forget_request``
        cannot reach it the way it reaches the change ledger. The entity id is
        what a person can actually point at -- "forget where I have been" --
        so subject is the key erasure uses here.

        Returns the number of rows removed, and the count is the report: a
        caller that says "forgotten" without one is the failure mode
        ``ERASURE_LIMITS`` exists to prevent. Secure-deletes and checkpoints
        afterwards so the old text is not left in the file, matching what the
        change ledger already promises.
        """
        if not entity_id:
            return 0
        placeholders = ",".join("?" for _ in self.PERSON_SCOPED_EVENT_TYPES)
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("PRAGMA secure_delete = ON")
                cur = conn.execute(
                    f"""DELETE FROM timeline_events
                        WHERE entity_id = ?
                          AND event_type IN ({placeholders})""",
                    (entity_id, *self.PERSON_SCOPED_EVENT_TYPES),
                )
                removed = cur.rowcount or 0
                conn.commit()
                if removed:
                    conn.execute("VACUUM")
            finally:
                conn.close()
        logger.info(
            "Timeline: erased %d row(s) for subject %s", removed, entity_id
        )
        return removed

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


# ---------------------------------------------------------------------------
# Module-level append (A01-G9)
# ---------------------------------------------------------------------------
#
# The ledger is ratified (DECISIONS.md CD-5) and every writer so far builds
# its own ``TimelineStore``. A pure module like ``continuity/promotion.py``
# should not be opening a database to say a sweep happened, and it must not
# raise into the sweep if the ledger is unavailable -- so the seam is here,
# beside the store, rather than as a fourth private copy of "construct,
# try, swallow".

_STORE: Optional["TimelineStore"] = None
_STORE_LOCK = threading.Lock()


def get_timeline_store() -> Optional["TimelineStore"]:
    """The process's timeline store, or None when it cannot be opened."""
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            try:
                _STORE = TimelineStore()
            except Exception as e:
                logger.warning("timeline unavailable: %s", e)
                return None
        return _STORE


def reset_timeline_store() -> None:
    """Drop the process store (tests, and a deliberate re-root)."""
    global _STORE
    with _STORE_LOCK:
        _STORE = None


def append_event(event_type: str, *, source: str = "", entity_id: str = "",
                 severity: str = "info", title: str = "",
                 description: str = "", data: Optional[Dict[str, Any]] = None
                 ) -> Optional[int]:
    """Record one event. Never raises.

    An observation that can break the thing it observes is not an
    observation, it is a dependency -- the same rule the turn-event tee
    and the skills telemetry seam already follow.
    """
    store = get_timeline_store()
    if store is None:
        return None
    try:
        return store.record_simple(
            event_type=event_type, source=source, entity_id=entity_id,
            severity=severity, title=title, description=description,
            data=data or {})
    except Exception as e:
        logger.debug("timeline append skipped (non-fatal): %s", e)
        return None
