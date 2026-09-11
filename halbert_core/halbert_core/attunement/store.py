# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert's standing-request store (A-HB-2, A-HB-24, A-HB-25).

The engine's default store is one JSON document per subject under its own
``data_home()``. Two things make that wrong here:

* **Multi-writer.** This store is reached from the dashboard, the MCP server
  (its own ``main()``), the scheduler, the detector runner and the home
  cognitive loop. ``FindingStore`` is constructed independently in ten places
  across those entry points and survives only because it is SQLite. A
  read-modify-write JSON document under the same access pattern loses updates,
  and the update it loses is a withdrawal.
* **One mind, several bodies.** ``federation/peers_config.py`` defines a peer
  with ``role="body"`` as another body of the same entity. A per-host store
  means "leave me alone" in the kitchen is unknown to the study.

So Halbert injects this store through the engine's ``StandingRequestStore``
Protocol instead of taking the default.

The class speaks **dicts** natively so the storage mechanics are testable with
the engine absent; :mod:`halbert_core.attunement.codec` binds the engine's
frozen dataclasses to it when they are importable.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..utils.paths import data_subdir

logger = logging.getLogger("halbert.attunement.store")

DEFAULT_RETENTION_DAYS = 90

_SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
    persona_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    record     TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (persona_id, subject_id)
);
CREATE TABLE IF NOT EXISTS outcomes (
    attempt_id TEXT PRIMARY KEY,
    persona_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    outcome    TEXT NOT NULL,
    reaction   TEXT,
    ts         TEXT NOT NULL,
    payload    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outcomes_persona ON outcomes(persona_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_outcomes_subject ON outcomes(persona_id, subject_id, ts DESC);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AttunementStore:
    """SQLite-backed standing requests, subject state and attempt outcomes.

    One database, three concerns, because they share a purge boundary: a
    subject's requests, that subject's per-persona state, and the append-only
    record of every engagement decision taken about them — SPEAK and suppressed
    alike (A-HB-25).

    Not inside ``findings.db``: findings are user-facing records with their own
    export and retention semantics; this is behavioural state.
    """

    def __init__(self, db_path: Optional[str] = None, *,
                 retention_days: int = DEFAULT_RETENTION_DAYS):
        if db_path is None:
            db_path = str(Path(data_subdir("attunement")) / "attunement.db")
        self.db_path = db_path
        self.retention_days = retention_days
        # Re-entrant: a transaction holds the lock while the typed façade
        # calls back into load/save, exactly as ``integrity/eventlog.py``
        # re-enters its own directory lock.
        self._lock = threading.RLock()
        self._local = threading.local()
        self._init_db()

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # WAL lets the readers (dashboard, MCP) run while a writer (scheduler,
        # cognitive loop) commits. ``:memory:`` cannot take it and does not
        # need it.
        if self.db_path != ":memory:":
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError as exc:  # pragma: no cover
                logger.debug("WAL unavailable for %s: %s", self.db_path, exc)
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init_db(self) -> None:
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
            self._conn: Optional[sqlite3.Connection] = None
        else:
            # An in-memory database dies with its connection, so hold one open.
            self._conn = self._connect()
        with self._write() as conn:
            conn.executescript(_SCHEMA)

    class _Ctx:
        def __init__(self, store: "AttunementStore", write: bool):
            self._store = store
            self._write = write
            self._conn: Optional[sqlite3.Connection] = None
            self._owned = False
            self._in_transaction = False

        def __enter__(self) -> sqlite3.Connection:
            if self._write:
                self._store._lock.acquire()
            active = getattr(self._store._local, "conn", None)
            if active is not None:
                # Inside a transaction: use its connection and let it commit.
                self._conn = active
                self._in_transaction = True
            elif self._store._conn is not None:
                self._conn = self._store._conn
            else:
                self._conn = self._store._connect()
                self._owned = True
            return self._conn

        def __exit__(self, exc_type, exc, tb) -> None:
            try:
                if self._conn is not None and not self._in_transaction:
                    if exc_type is None and self._write:
                        self._conn.commit()
                    elif exc_type is not None and self._write:
                        self._conn.rollback()
                    if self._owned:
                        self._conn.close()
            finally:
                if self._write:
                    self._store._lock.release()

    def _write(self) -> "AttunementStore._Ctx":
        return AttunementStore._Ctx(self, write=True)

    def _read(self) -> "AttunementStore._Ctx":
        return AttunementStore._Ctx(self, write=False)

    # ------------------------------------------------------------------
    # Subjects
    # ------------------------------------------------------------------

    def load_subject_raw(self, persona_id: str, subject_id: str) -> Dict[str, Any]:
        """The subject's requests and state, or an empty record.

        A first-ever turn must not raise; an unreadable row must not either.
        Corruption reads as empty, loudly, which is the engine's own rule.
        """
        with self._read() as conn:
            row = conn.execute(
                "SELECT record FROM subjects WHERE persona_id=? AND subject_id=?",
                (persona_id, subject_id),
            ).fetchone()
        if row is None:
            return {"requests": [], "state": {}}
        try:
            data = json.loads(row["record"])
        except (ValueError, TypeError):
            logger.error(
                "attunement: unreadable record for %s/%s; treating as empty",
                persona_id, subject_id,
            )
            return {"requests": [], "state": {}}
        data.setdefault("requests", [])
        data.setdefault("state", {})
        return data

    def save_subject_raw(self, persona_id: str, subject_id: str,
                         record: Dict[str, Any]) -> None:
        payload = json.dumps(record)
        with self._write() as conn:
            conn.execute(
                "INSERT INTO subjects (persona_id, subject_id, record, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(persona_id, subject_id) DO UPDATE SET "
                "record=excluded.record, updated_at=excluded.updated_at",
                (persona_id, subject_id, payload, _now_iso()),
            )

    # ------------------------------------------------------------------
    # Outcomes — every decision, not only the ones that spoke
    # ------------------------------------------------------------------

    def record_outcome_raw(self, entry: Dict[str, Any]) -> None:
        """Append one attempt. Suppressions are attempts (A-HB-25)."""
        attempt_id = entry.get("attempt_id")
        if not attempt_id:
            raise ValueError("outcome entry requires an attempt_id")
        ts = entry.get("ts") or _now_iso()
        entry = {**entry, "ts": ts}
        with self._write() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO outcomes "
                "(attempt_id, persona_id, subject_id, outcome, reaction, ts, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    attempt_id,
                    entry.get("persona_id", ""),
                    entry.get("subject_id", ""),
                    str(entry.get("outcome", "")),
                    entry.get("reaction"),
                    ts,
                    json.dumps(entry),
                ),
            )

    def update_reaction(self, attempt_id: str, reaction: Any) -> bool:
        """Attach how the person reacted. False when the attempt is unknown.

        Accepts the engine's ``Reaction`` or its bare value.
        """
        reaction = getattr(reaction, "value", reaction)
        with self._write() as conn:
            row = conn.execute(
                "SELECT payload FROM outcomes WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if row is None:
                return False
            try:
                payload = json.loads(row["payload"])
            except (ValueError, TypeError):
                payload = {}
            payload["reaction"] = reaction
            conn.execute(
                "UPDATE outcomes SET reaction=?, payload=? WHERE attempt_id=?",
                (reaction, json.dumps(payload), attempt_id),
            )
            return True

    def latest_attempt_for_context(
        self, context_key: Optional[str], *, persona_id: str,
        subject_id: Optional[str] = None,
    ) -> Optional[str]:
        """The newest attempt recorded against ``context_key``, or None.

        This is the join that lets a dismissal or a snooze find the attempt
        it is a reaction to: the recorder stashes the finding id in
        ``context_key``, and the findings surfaces know only the finding id.

        A blank key matches nothing. Most rows carry no context key at all
        — a morning report is not about a finding — so a blank lookup that
        matched would attach a real person's reaction to an unrelated
        attempt, which is worse than recording no reaction.

        ``json_extract`` is SQLite's own and does the filtering in one
        indexed scan; the Python fallback covers a build without JSON1
        rather than letting the reaction quietly not happen.
        """
        if not context_key:
            return None
        where = "persona_id=?"
        args: List[Any] = [persona_id]
        if subject_id is not None:
            where += " AND subject_id=?"
            args.append(subject_id)
        order = " ORDER BY ts DESC, rowid DESC LIMIT 1"
        try:
            with self._read() as conn:
                row = conn.execute(
                    f"SELECT attempt_id FROM outcomes WHERE {where} "
                    f"AND json_extract(payload, '$.context_key')=?{order}",
                    (*args, context_key),
                ).fetchone()
            return row["attempt_id"] if row else None
        except sqlite3.OperationalError as exc:  # pragma: no cover - no JSON1
            logger.debug("attunement: json_extract unavailable (%s); scanning", exc)

        for entry in self.list_outcomes_raw(persona_id, subject_id, limit=2000):
            if entry.get("context_key") == context_key:
                return entry.get("attempt_id")
        return None

    def unanswered_attempts(
        self, persona_id: str, *, before_ts: str, subject_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Attempts older than ``before_ts`` that carry no reaction yet."""
        sql = "SELECT payload FROM outcomes WHERE persona_id=? AND reaction IS NULL AND ts < ?"
        args: List[Any] = [persona_id, before_ts]
        if subject_id is not None:
            sql += " AND subject_id=?"
            args.append(subject_id)
        sql += " ORDER BY ts DESC, rowid DESC LIMIT ?"
        args.append(int(limit))
        with self._read() as conn:
            rows = conn.execute(sql, args).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                out.append(json.loads(row["payload"]))
            except (ValueError, TypeError):  # pragma: no cover
                continue
        return out

    def list_outcomes_raw(self, persona_id: str, subject_id: Optional[str] = None,
                          limit: int = 500) -> List[Dict[str, Any]]:
        """Attempts, newest first."""
        sql = "SELECT payload FROM outcomes WHERE persona_id=?"
        args: List[Any] = [persona_id]
        if subject_id is not None:
            sql += " AND subject_id=?"
            args.append(subject_id)
        sql += " ORDER BY ts DESC, rowid DESC LIMIT ?"
        args.append(int(limit))
        with self._read() as conn:
            rows = conn.execute(sql, args).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                out.append(json.loads(row["payload"]))
            except (ValueError, TypeError):  # pragma: no cover
                continue
        return out

    def trim_outcomes(self, retention_days: Optional[int] = None) -> int:
        """Drop attempts past the retention horizon. Returns rows removed."""
        days = self.retention_days if retention_days is None else retention_days
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._write() as conn:
            cur = conn.execute("DELETE FROM outcomes WHERE ts < ?", (cutoff,))
            return cur.rowcount or 0

    # ------------------------------------------------------------------
    # Erasure
    # ------------------------------------------------------------------

    def purge(self, persona_id: str, subject_id: str) -> None:
        """Erase one subject: requests, state and every attempt about them."""
        with self._write() as conn:
            conn.execute(
                "DELETE FROM subjects WHERE persona_id=? AND subject_id=?",
                (persona_id, subject_id),
            )
            conn.execute(
                "DELETE FROM outcomes WHERE persona_id=? AND subject_id=?",
                (persona_id, subject_id),
            )

    def purge_all(self, persona_id: str) -> None:
        """Erase everything for one persona, leaving other personas intact."""
        with self._write() as conn:
            conn.execute("DELETE FROM subjects WHERE persona_id=?", (persona_id,))
            conn.execute("DELETE FROM outcomes WHERE persona_id=?", (persona_id,))

    # ------------------------------------------------------------------
    # Transaction (StandingRequestStore.transaction)
    # ------------------------------------------------------------------

    @contextlib.contextmanager
    def transaction(self, persona_id: str, subject_id: str):
        """Serialize a read-modify-write of one subject.

        The Protocol requires this against every other writer, in-process and
        cross-process. ``BEGIN IMMEDIATE`` takes SQLite's write lock for the
        body's duration, which covers other processes; the re-entrant lock
        covers other threads and lets the typed façade call back in.

        ``persona_id`` and ``subject_id`` are part of the signature but not
        used to narrow the lock: SQLite's write lock is database-wide, and a
        finer-grained scheme would be a second locking protocol to get wrong.
        Contention here is a handful of writes a minute.
        """
        with self._lock:
            existing = getattr(self._local, "conn", None)
            if existing is not None:
                # Already inside one — re-entering is a no-op, as the engine's
                # own eventlog treats a nested acquire.
                yield existing
                return
            conn = self._conn if self._conn is not None else self._connect()
            owned = self._conn is None
            self._local.conn = conn
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                self._local.conn = None
                if owned:
                    conn.close()

    # ------------------------------------------------------------------
    # Typed facade (StandingRequestStore) — engine types in and out
    # ------------------------------------------------------------------

    def load_subject(self, persona_id: str, subject_id: str) -> Any:
        from haloysius.attunement.types import SubjectRecord

        from .codec import from_dict

        return from_dict(SubjectRecord, self.load_subject_raw(persona_id, subject_id))

    def save_subject(self, persona_id: str, subject_id: str, record: Any) -> None:
        from .codec import to_dict

        self.save_subject_raw(persona_id, subject_id, to_dict(record))

    def list_subjects(self, persona_id: str) -> Sequence[str]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT subject_id FROM subjects WHERE persona_id=?", (persona_id,)
            ).fetchall()
        return [r["subject_id"] for r in rows]

    def record_outcome(self, entry: Any) -> None:
        from .codec import to_dict

        self.record_outcome_raw(to_dict(entry))

    def list_outcomes(self, persona_id: str, subject_id: Optional[str] = None,
                      limit: int = 500) -> Sequence[Any]:
        from haloysius.attunement.types import OutcomeEntry

        from .codec import from_dict

        return [
            from_dict(OutcomeEntry, row)
            for row in self.list_outcomes_raw(persona_id, subject_id, limit)
        ]
