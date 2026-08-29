# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Behavior Store + Pattern Inferrer — learn routines from the timeline.

The behavior engine is what makes the house anticipate rather than react.
It reads the persistent TimelineStore and extracts recurring patterns:

- Time-of-day patterns (wakes at 6:30am on weekdays)
- Day-of-week patterns (movie night on Fridays at 8pm)
- Seasonal patterns (thermostat setpoint changes with outdoor temp)
- Guest patterns (parents visit monthly, stay 2 days)
- Device usage patterns (kitchen lights on at 7:15am every weekday)

A feedback loop adjusts confidence: when the house acts on a prediction
and the user accepts, confidence increases. When the user corrects,
confidence decreases. Patterns that haven't occurred in 4 weeks degrade.

Privacy: all behavior data stays local. Never sent to cloud.
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
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger("halbert.home.behavior")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS behavior_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT NOT NULL,
    person TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    day_of_week INTEGER,
    hour INTEGER,
    minute INTEGER,
    confidence REAL NOT NULL DEFAULT 0.5,
    occurrence_count INTEGER NOT NULL DEFAULT 0,
    last_occurrence REAL NOT NULL,
    confirmed INTEGER NOT NULL DEFAULT 0,
    dismissed INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(pattern_type, person, entity_id, action, day_of_week, hour, minute)
);

CREATE INDEX IF NOT EXISTS idx_behavior_type ON behavior_patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_behavior_entity ON behavior_patterns(entity_id);
CREATE INDEX IF NOT EXISTS idx_behavior_confidence ON behavior_patterns(confidence);
"""

# Pattern types
PATTERN_TIME_OF_DAY = "time_of_day"  # recurring at a specific time
PATTERN_DAY_OF_WEEK = "day_of_week"  # recurring on a specific day
PATTERN_DEVICE_USAGE = "device_usage"  # device state change pattern
PATTERN_OCCUPANCY = "occupancy"  # arrival/departure pattern
PATTERN_GUEST = "guest"  # guest visit pattern

# Confidence parameters
INITIAL_CONFIDENCE = 0.3
CONFIDENCE_INCREMENT = 0.1
CONFIDENCE_DECREMENT = 0.15
MAX_CONFIDENCE = 0.95
MIN_CONFIDENCE = 0.0
DEGRADATION_INTERVAL = 7 * 86400  # 1 week without occurrence
DEGRADATION_AMOUNT = 0.05
DISMISS_THRESHOLD = 0.1  # below this, pattern is effectively dead


@dataclass
class BehaviorPattern:
    """A learned behavioral pattern."""
    id: Optional[int] = None
    pattern_type: str = ""
    person: str = ""
    entity_id: str = ""
    action: str = ""
    day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday
    hour: Optional[int] = None
    minute: Optional[int] = None
    confidence: float = INITIAL_CONFIDENCE
    occurrence_count: int = 0
    last_occurrence: float = 0.0
    confirmed: bool = False
    dismissed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["last_occurrence_ago_seconds"] = time.time() - self.last_occurrence
        return d

    @property
    def is_active(self) -> bool:
        """A pattern is active if it hasn't been dismissed and has meaningful confidence."""
        return not self.dismissed and self.confidence > DISMISS_THRESHOLD


class BehaviorStore:
    """SQLite-backed store for learned behavioral patterns.

    Thread-safe. Patterns are upserted (insert or update) based on
    the unique constraint on (pattern_type, person, entity_id, action,
    day_of_week, hour, minute).
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            data_dir = Path.home() / ".local" / "share" / "halbert"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "behavior.db")
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def upsert_pattern(self, pattern: BehaviorPattern) -> int:
        """Insert or update a pattern. Returns the row ID."""
        now = time.time()
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute(
                    """INSERT INTO behavior_patterns
                       (pattern_type, person, entity_id, action, day_of_week,
                        hour, minute, confidence, occurrence_count,
                        last_occurrence, confirmed, dismissed, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(pattern_type, person, entity_id, action,
                                   day_of_week, hour, minute)
                       DO UPDATE SET
                           occurrence_count = occurrence_count + 1,
                           last_occurrence = ?,
                           confidence = MIN(confidence + ?, ?),
                           updated_at = ?""",
                    (
                        pattern.pattern_type, pattern.person, pattern.entity_id,
                        pattern.action, pattern.day_of_week, pattern.hour,
                        pattern.minute, pattern.confidence, 1,
                        pattern.last_occurrence or now, 0, 0, now, now,
                        pattern.last_occurrence or now,
                        CONFIDENCE_INCREMENT, MAX_CONFIDENCE, now,
                    ),
                )
                conn.commit()
                return cursor.lastrowid
            finally:
                conn.close()

    def record_occurrence(
        self,
        pattern_type: str,
        entity_id: str = "",
        action: str = "",
        person: str = "",
        day_of_week: Optional[int] = None,
        hour: Optional[int] = None,
        minute: Optional[int] = None,
    ) -> None:
        """Record that a pattern occurred (increments count and confidence).

        Uses -1 as sentinel for None day_of_week/hour/minute to ensure
        SQLite UNIQUE constraint works (NULL != NULL in SQLite).
        """
        self.upsert_pattern(BehaviorPattern(
            pattern_type=pattern_type,
            person=person,
            entity_id=entity_id,
            action=action,
            day_of_week=day_of_week if day_of_week is not None else -1,
            hour=hour if hour is not None else -1,
            minute=minute if minute is not None else -1,
            last_occurrence=time.time(),
        ))

    def confirm_pattern(self, pattern_id: int) -> None:
        """User confirmed a pattern — boost confidence."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """UPDATE behavior_patterns
                       SET confirmed = 1, confidence = MIN(confidence + ?, ?), updated_at = ?
                       WHERE id = ?""",
                    (CONFIDENCE_INCREMENT * 2, MAX_CONFIDENCE, time.time(), pattern_id),
                )
                conn.commit()
            finally:
                conn.close()

    def dismiss_pattern(self, pattern_id: int) -> None:
        """User dismissed a pattern — drop confidence to zero."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """UPDATE behavior_patterns
                       SET dismissed = 1, confidence = 0, updated_at = ?
                       WHERE id = ?""",
                    (time.time(), pattern_id),
                )
                conn.commit()
            finally:
                conn.close()

    def record_correction(self, pattern_id: int) -> None:
        """User corrected a prediction based on this pattern — reduce confidence."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """UPDATE behavior_patterns
                       SET confidence = MAX(confidence - ?, ?), updated_at = ?
                       WHERE id = ?""",
                    (CONFIDENCE_DECREMENT, MIN_CONFIDENCE, time.time(), pattern_id),
                )
                conn.commit()
            finally:
                conn.close()

    def get_patterns(
        self,
        pattern_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        min_confidence: float = DISMISS_THRESHOLD,
        active_only: bool = True,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query learned patterns."""
        conditions = []
        params: List[Any] = []

        if pattern_type:
            conditions.append("pattern_type = ?")
            params.append(pattern_type)
        if entity_id:
            conditions.append("entity_id = ?")
            params.append(entity_id)
        if min_confidence > 0 and active_only:
            conditions.append("confidence >= ?")
            params.append(min_confidence)
        if active_only:
            conditions.append("dismissed = 0")

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"""SELECT * FROM behavior_patterns
                    WHERE {where}
                    ORDER BY confidence DESC, occurrence_count DESC
                    LIMIT ?""",
                params,
            ).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                # Convert -1 sentinels back to None for API consumers
                if d.get("day_of_week") == -1:
                    d["day_of_week"] = None
                if d.get("hour") == -1:
                    d["hour"] = None
                if d.get("minute") == -1:
                    d["minute"] = None
                results.append(d)
            return results
        finally:
            conn.close()

    def degrade_stale_patterns(self) -> int:
        """Reduce confidence of patterns that haven't occurred recently.

        Returns the number of patterns degraded.
        """
        cutoff = time.time() - DEGRADATION_INTERVAL
        now = time.time()
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute(
                    """UPDATE behavior_patterns
                       SET confidence = MAX(confidence - ?, 0), updated_at = ?
                       WHERE last_occurrence < ? AND dismissed = 0 AND confidence > 0""",
                    (DEGRADATION_AMOUNT, now, cutoff),
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def stats(self) -> Dict[str, Any]:
        """Get basic stats about learned patterns."""
        conn = sqlite3.connect(self.db_path)
        try:
            total = conn.execute("SELECT COUNT(*) FROM behavior_patterns").fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM behavior_patterns WHERE dismissed = 0 AND confidence > ?",
                (DISMISS_THRESHOLD,),
            ).fetchone()[0]
            confirmed = conn.execute(
                "SELECT COUNT(*) FROM behavior_patterns WHERE confirmed = 1"
            ).fetchone()[0]
            by_type = conn.execute(
                "SELECT pattern_type, COUNT(*) as count FROM behavior_patterns GROUP BY pattern_type"
            ).fetchall()
            return {
                "total_patterns": total,
                "active_patterns": active,
                "confirmed_patterns": confirmed,
                "by_type": {row[0]: row[1] for row in by_type},
            }
        finally:
            conn.close()


class PatternInferrer:
    """Infers behavioral patterns from the TimelineStore.

    Runs periodically (daily) to extract routines from the event stream.
    Reads the timeline and calls BehaviorStore.record_occurrence() for
    each detected pattern.
    """

    def __init__(
        self,
        timeline_store: Any,
        behavior_store: BehaviorStore,
    ) -> None:
        self.timeline = timeline_store
        self.behavior = behavior_store

    def infer_from_timeline(self, hours: float = 168) -> int:
        """Scan the timeline for the last N hours and record patterns.

        Default is 168 hours (1 week) to capture weekly patterns.

        Returns the number of patterns recorded.
        """
        count = 0
        since = time.time() - (hours * 3600)

        # Get all HA state changes in the window
        events = self.timeline.query(
            event_type="ha_state_change",
            since=since,
            limit=10000,
        )

        for event in events:
            entity_id = event.get("entity_id", "")
            data = event.get("data", {})
            new_state = data.get("new_state", event.get("description", ""))
            ts = event.get("timestamp", time.time())

            dt = datetime.fromtimestamp(ts)
            day_of_week = dt.weekday()
            hour = dt.hour
            # Round to nearest 15 minutes for pattern matching
            minute = (dt.minute // 15) * 15

            # Record device usage pattern
            self.behavior.record_occurrence(
                pattern_type=PATTERN_DEVICE_USAGE,
                entity_id=entity_id,
                action=new_state,
                day_of_week=day_of_week,
                hour=hour,
                minute=minute,
            )
            count += 1

            # Also record time-of-day pattern (ignoring day)
            self.behavior.record_occurrence(
                pattern_type=PATTERN_TIME_OF_DAY,
                entity_id=entity_id,
                action=new_state,
                hour=hour,
                minute=minute,
            )
            count += 1

        # Get occupancy changes
        occ_events = self.timeline.query(
            event_type="occupancy_change",
            since=since,
            limit=1000,
        )
        for event in occ_events:
            person = event.get("entity_id", "")
            data = event.get("data", {})
            direction = data.get("direction", "arrival")
            ts = event.get("timestamp", time.time())

            dt = datetime.fromtimestamp(ts)
            day_of_week = dt.weekday()
            hour = dt.hour
            minute = (dt.minute // 15) * 15

            self.behavior.record_occurrence(
                pattern_type=PATTERN_OCCUPANCY,
                person=person,
                action=direction,
                day_of_week=day_of_week,
                hour=hour,
                minute=minute,
            )
            count += 1

        logger.info(f"Inferred {count} pattern occurrences from {len(events)} timeline events")
        return count

    def predict_next(
        self,
        current_day_of_week: Optional[int] = None,
        current_hour: Optional[int] = None,
        current_minute: Optional[int] = None,
        lookahead_minutes: int = 60,
    ) -> List[Dict[str, Any]]:
        """Predict what patterns are likely to occur in the next N minutes.

        Returns a list of predicted actions sorted by confidence.
        """
        now = datetime.now()
        if current_day_of_week is None:
            current_day_of_week = now.weekday()
        if current_hour is None:
            current_hour = now.hour
        if current_minute is None:
            current_minute = now.minute

        # Get all active patterns
        patterns = self.behavior.get_patterns(active_only=True, limit=500)

        predictions: List[Dict[str, Any]] = []
        current_time = current_hour * 60 + current_minute

        for p in patterns:
            if p["hour"] is None or p["hour"] == -1:
                continue

            pattern_time = p["hour"] * 60 + (p["minute"] if p["minute"] and p["minute"] >= 0 else 0)

            # Check if pattern is within the lookahead window
            time_diff = pattern_time - current_time
            if time_diff < 0:
                time_diff += 24 * 60  # Next day
            if time_diff > lookahead_minutes:
                continue

            # Check day-of-week match if pattern has one
            dow = p["day_of_week"]
            if dow is not None and dow >= 0 and dow != current_day_of_week:
                continue

            predictions.append({
                "pattern_id": p["id"],
                "entity_id": p["entity_id"],
                "action": p["action"],
                "pattern_type": p["pattern_type"],
                "confidence": p["confidence"],
                "minutes_until": time_diff,
                "occurrence_count": p["occurrence_count"],
            })

        predictions.sort(key=lambda x: (-x["confidence"], x["minutes_until"]))
        return predictions
