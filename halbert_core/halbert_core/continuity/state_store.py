# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Machine-state ledger — what is true of this host, and when it changed.

Halbert's own replacement for Haloysius's ``TemporalStateLedger`` (founder
direction D1: Haloysius has no cross-session understanding). Same core
semantics — recording a value closes the previous one's ``valid_to``, so
``current_state()`` answers *what is true now* and ``state_history()`` answers
*when it changed* — with two differences that follow from Halbert owning it:

- **No persona_id.** Halbert is the machine; there is exactly one subject of
  these facts. Memory is host-bound (design strategies §4.8).
- **A ``thread_id``.** A state change is traceable to the conversation that
  caused it. Haloysius could not express this: it has no idea what a thread is.

Authority is not similarity. Retrieval may *propose* an old receipt; this table
*resolves* what is currently true. Nothing here ranks or guesses — a query
returns the open triple or nothing.

The table can live in its own file or inside a caller-owned connection, so it
folds into the Plan A thread database with no data move: pass ``conn=``.

Every method fails soft: a broken database logs and returns an empty result
rather than raising into a state tracker on the hot path.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.continuity.state_store")

__all__ = ["StateStore", "StateTriple", "default_state_db_path"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS state_triples (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    subject    TEXT NOT NULL,
    predicate  TEXT NOT NULL,
    object     TEXT NOT NULL,
    source     TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    valid_from REAL NOT NULL,
    valid_to   REAL,
    thread_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_state_current
    ON state_triples(subject, predicate, valid_to);
"""


def default_state_db_path() -> Path:
    """Halbert's standalone state db, used until the table folds into the thread db."""
    p = Path.home() / ".local" / "share" / "halbert" / "state_ledger.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@dataclass(frozen=True)
class StateTriple:
    """One machine-state fact, with the window over which it was true."""

    id: int
    subject: str
    predicate: str
    object: str
    source: str
    confidence: float
    valid_from: float
    valid_to: Optional[float]
    thread_id: Optional[str]

    @property
    def is_current(self) -> bool:
        return self.valid_to is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "source": self.source,
            "confidence": self.confidence,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "thread_id": self.thread_id,
        }


def _row(r: sqlite3.Row) -> StateTriple:
    return StateTriple(
        id=r["id"], subject=r["subject"], predicate=r["predicate"],
        object=r["object"], source=r["source"], confidence=r["confidence"],
        valid_from=r["valid_from"], valid_to=r["valid_to"],
        thread_id=r["thread_id"],
    )


class StateStore:
    """SQLite-backed machine-state ledger (best-effort, never raises)."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ):
        """Open the ledger.

        Args:
            db_path: file to open. Ignored when ``conn`` is given.
            conn: a caller-owned connection to host the table in. The store
                will not close it — the owner does.
        """
        self._lock = threading.Lock()
        self._owns_conn = conn is None
        if conn is None:
            path = db_path or str(default_state_db_path())
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        self._conn = conn
        with self._conn:
            self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_state(
        self,
        subject: str,
        predicate: str,
        obj: str,
        source: str,
        confidence: float = 1.0,
        thread_id: Optional[str] = None,
        now: Optional[float] = None,
    ) -> Optional[int]:
        """Record a fact, closing whatever it supersedes.

        Re-recording the value that is already current is a no-op, so a tracker
        resyncing unchanged state does not churn the history. Returns the new
        row id, None if nothing was written or the write failed.
        """
        ts = time.time() if now is None else now
        try:
            with self._lock, self._conn:
                cur = self._conn.execute(
                    "SELECT id, object FROM state_triples "
                    "WHERE subject = ? AND predicate = ? AND valid_to IS NULL",
                    (subject, predicate),
                ).fetchone()
                if cur is not None:
                    if cur["object"] == obj:
                        return None            # unchanged; leave the history alone
                    self._conn.execute(
                        "UPDATE state_triples SET valid_to = ? WHERE id = ?",
                        (ts, cur["id"]),
                    )
                c = self._conn.execute(
                    "INSERT INTO state_triples "
                    "(subject, predicate, object, source, confidence, valid_from, "
                    " valid_to, thread_id) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
                    (subject, predicate, obj, source, confidence, ts, thread_id),
                )
                return c.lastrowid
        except Exception as e:
            logger.warning(f"Failed to record {subject}/{predicate}: {e}")
            return None

    def invalidate_state(self, subject: str, predicate: str,
                         now: Optional[float] = None) -> int:
        """Close the open triple for this key. Returns rows closed (0 or 1)."""
        ts = time.time() if now is None else now
        try:
            with self._lock, self._conn:
                c = self._conn.execute(
                    "UPDATE state_triples SET valid_to = ? "
                    "WHERE subject = ? AND predicate = ? AND valid_to IS NULL",
                    (ts, subject, predicate),
                )
                return c.rowcount or 0
        except Exception as e:
            logger.warning(f"Failed to invalidate {subject}/{predicate}: {e}")
            return 0

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def current_state(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
    ) -> List[StateTriple]:
        """Everything true right now, optionally narrowed to a subject/predicate."""
        sql = "SELECT * FROM state_triples WHERE valid_to IS NULL"
        args: List[Any] = []
        if subject is not None:
            sql += " AND subject = ?"
            args.append(subject)
        if predicate is not None:
            sql += " AND predicate = ?"
            args.append(predicate)
        sql += " ORDER BY subject, predicate"
        try:
            with self._lock:
                return [_row(r) for r in self._conn.execute(sql, args).fetchall()]
        except Exception as e:
            logger.warning(f"Failed to read current state: {e}")
            return []

    def state_history(self, subject: str, predicate: str) -> List[StateTriple]:
        """Every value this key has held, oldest first."""
        try:
            with self._lock:
                return [
                    _row(r)
                    for r in self._conn.execute(
                        "SELECT * FROM state_triples WHERE subject = ? AND predicate = ? "
                        "ORDER BY valid_from, id",
                        (subject, predicate),
                    ).fetchall()
                ]
        except Exception as e:
            logger.warning(f"Failed to read history for {subject}/{predicate}: {e}")
            return []

    def close(self) -> None:
        """Close the connection, unless a caller owns it."""
        if self._owns_conn:
            try:
                self._conn.close()
            except Exception:
                pass
