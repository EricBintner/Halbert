# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Machine-state ledger — what is true of this host, when it changed, and why.

Halbert's own replacement for Haloysius's ``TemporalStateLedger`` (founder
direction D1: Haloysius has no cross-session understanding). Same core
semantics — recording a value closes the previous one's ``valid_to``, so
``current_state()`` answers *what is true now* and ``state_history()`` answers
*when it changed* — with three differences that follow from Halbert owning it:

- **No persona_id.** Halbert is the machine; there is exactly one subject of
  these facts. Memory is host-bound (design strategies §4.8).
- **A ``thread_id``.** A state change is traceable to the conversation that
  caused it. Haloysius could not express this: it has no idea what a thread is.
- **Provenance.** Every write carries ``reason``, ``actor`` and an optional
  ``request_id``, so ``why()`` answers *who changed this, and what for*.

Authority is not similarity. Retrieval may *propose* an old receipt; this table
*resolves* what is currently true. Nothing here ranks or guesses — a query
returns the open triple or nothing.

The table can live in its own file or inside a caller-owned connection, so it
folds into the Plan A thread database with no data move: pass ``conn=``.

Every method fails soft: a broken database logs and returns an empty result
rather than raising into a state tracker on the hot path. Provenance is the one
exception — see below.

Why ``reason`` and ``actor`` are mandatory
------------------------------------------
They are keyword-only parameters with **no default**, so a call site cannot
omit one silently; omitting it is a ``TypeError`` at the call, before the
fail-soft body is ever entered. That is deliberate. A reason exists exactly
once — at the instant of the write — and is destroyed if not captured there.
No later pass can recover it, and a *plausible* reason invented afterwards is
strictly worse than a blank one: it is unfalsifiable, it projects onward as
though it were provenance, and anything reasoning over the ledger then treats
it as evidence.

So a ``reason`` may only be one of three things:

1. a human utterance from the turn that caused the write;
2. a deterministic rule that names itself — ``"tracker: disk sweep"``,
   ``"policy: permissions remediation"``;
3. the sentinel :data:`UNRECORDED`, which renders as *unknown*.

:data:`UNRECORDED` is never to be replaced by a model-generated rationale.
A blank is a fact about our knowledge; a fabrication destroys the column.
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

__all__ = [
    "StateStore",
    "StateTriple",
    "StateWhy",
    "default_state_db_path",
    "UNRECORDED",
    "ACTOR_USER",
    "ACTOR_AGENT",
    "ACTOR_SYSTEM",
]

#: The only permitted stand-in for a reason we do not have. Renders as
#: *unknown*; never to be backfilled by a model.
UNRECORDED = "unrecorded"

#: The person asked for it, or did it themselves.
ACTOR_USER = "user"
#: The agent decided to, inside a turn.
ACTOR_AGENT = "agent"
#: A deterministic rule fired — a tracker, a sweep, a consolidation pass.
ACTOR_SYSTEM = "system"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS state_triples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    subject       TEXT NOT NULL,
    predicate     TEXT NOT NULL,
    object        TEXT NOT NULL,
    source        TEXT NOT NULL,
    confidence    REAL NOT NULL DEFAULT 1.0,
    valid_from    REAL NOT NULL,
    valid_to      REAL,
    thread_id     TEXT,
    reason        TEXT NOT NULL,
    actor         TEXT NOT NULL,
    request_id    TEXT,
    closed_reason TEXT,
    closed_by     TEXT,
    closed_by_request TEXT
);
CREATE INDEX IF NOT EXISTS idx_state_current
    ON state_triples(subject, predicate, valid_to);
CREATE INDEX IF NOT EXISTS idx_state_request
    ON state_triples(request_id);
"""

#: Exactly one open row per key, enforced by the storage layer.
#:
#: ``record_state`` is SELECT-then-UPDATE-then-INSERT and nothing held the
#: three together across callers: ``self._lock`` is per instance, and every
#: production call site builds its own ``StateStore`` over the same file. Two
#: concurrent writers could therefore both see no open row and both INSERT
#: one, leaving two permanently-current values for one key -- and the next
#: write would close only one of them, silently discarding a person's stated
#: reason for the other. The vault then maps both rows to one note path and
#: one overwrites the other.
#:
#: A partial unique index makes that unrepresentable. On its own, though, it
#: would make things WORSE: the loser of the race got an IntegrityError, was
#: failed soft, and its reason was dropped entirely -- trading a visible
#: duplicate for a silent loss, which is the opposite of the point. So the
#: index is paired with an immediate transaction around the whole
#: read-modify-write in ``record_state``, and one retry: the loser waits for
#: the winner, then supersedes it normally, and both reasons survive.
_OPEN_ROW_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_state_one_open "
    "ON state_triples(subject, predicate) WHERE valid_to IS NULL"
)

#: Columns added when provenance landed. A database written before that has a
#: ``state_triples`` without them.
_PROVENANCE_COLUMNS = ("reason", "actor", "request_id", "closed_reason", "closed_by")

#: Where a pre-provenance table is moved to. Not dropped: those rows are real
#: history, they simply cannot answer *why* and must never be backfilled with a
#: guess. Left on disk, unread.
_LEGACY_TABLE = "state_triples_pre_provenance"

#: Columns added *after* the provenance set, which are migrated in place.
#:
#: These are deliberately NOT in :data:`_PROVENANCE_COLUMNS`. That set decides
#: whether a database predates provenance entirely and should be set aside;
#: adding a later column to it would make an existing, perfectly good ledger
#: get renamed away and its rows orphaned — a worse outcome dressed as a fix.
#:
#: They also cannot be added by ``_SCHEMA`` alone. Every CREATE there is
#: ``IF NOT EXISTS``, so on an existing table the statement is a no-op, the
#: column never appears, ``_row()`` raises on the missing key, and every read
#: method's fail-soft ``except`` turns that into a logged warning and an empty
#: list. The ledger would read blank with nothing raising anywhere — and no
#: tmp-directory test could catch it, because a fresh database gets the column
#: from ``_SCHEMA`` on creation. Hence a real ``ALTER TABLE``.
_ADDITIVE_COLUMNS = {"closed_by_request": "TEXT"}


def default_state_db_path() -> Path:
    """Halbert's standalone state db, used until the table folds into the thread db.

    Resolved through ``utils.paths.data_dir`` at call time, so the ledger
    honours ``HALBERT_DATA_DIR`` like every other store (CFG-1) and a second
    instance does not write into the first one's history. With no override
    and a non-root user this is ``~/.local/share/halbert``, exactly where it
    has always been.
    """
    from ..utils.paths import data_dir

    p = Path(data_dir()) / "state_ledger.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _require(value: str, field: str) -> str:
    """Provenance fields must actually say something."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field} must be a non-empty string. Pass the real {field}, or "
            f"UNRECORDED if there genuinely is none — never a generated one."
        )
    return value.strip()


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
    reason: str
    actor: str
    request_id: Optional[str] = None
    closed_reason: Optional[str] = None
    closed_by: Optional[str] = None
    closed_by_request: Optional[str] = None

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
            "reason": self.reason,
            "actor": self.actor,
            "request_id": self.request_id,
            "closed_reason": self.closed_reason,
            "closed_by": self.closed_by,
            "closed_by_request": self.closed_by_request,
        }


@dataclass(frozen=True)
class StateWhy:
    """The answer to *why is this the way it is* for one (subject, predicate).

    ``current`` is the open triple, or None if the key holds nothing now.
    ``superseded`` is the value it replaced — the most recently closed triple
    for the same key — so a caller gets before and after from one query.
    """

    subject: str
    predicate: str
    current: Optional[StateTriple]
    superseded: Optional[StateTriple]

    @property
    def found(self) -> bool:
        return self.current is not None or self.superseded is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "current": self.current.to_dict() if self.current else None,
            "superseded": self.superseded.to_dict() if self.superseded else None,
        }


def _row(r: sqlite3.Row) -> StateTriple:
    return StateTriple(
        id=r["id"], subject=r["subject"], predicate=r["predicate"],
        object=r["object"], source=r["source"], confidence=r["confidence"],
        valid_from=r["valid_from"], valid_to=r["valid_to"],
        thread_id=r["thread_id"], reason=r["reason"], actor=r["actor"],
        request_id=r["request_id"], closed_reason=r["closed_reason"],
        closed_by=r["closed_by"], closed_by_request=r["closed_by_request"],
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
            # busy_timeout FIRST: switching journal_mode takes a lock, and a
            # concurrent first open would otherwise fail instantly instead of
            # waiting for the other process to finish.
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA journal_mode=WAL")
            # Overwritten cells are zeroed rather than left in free pages, so
            # a redacted reason does not survive in the file's slack space.
            # Costs a little write throughput; a ledger that leaks the words
            # it was asked to forget is not worth the speed.
            conn.execute("PRAGMA secure_delete=ON")
        conn.row_factory = sqlite3.Row
        self._conn = conn
        # BEGIN IMMEDIATE, so two processes opening the same new-schema file
        # cannot both decide to migrate. Python's sqlite3 opens no implicit
        # transaction for DDL, so `with self._conn:` alone would let the
        # rename and the create interleave.
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except Exception:  # pragma: no cover - already in a transaction
            pass
        with self._conn:
            self._set_legacy_table_aside()
            self._conn.executescript(_SCHEMA)
            self._add_missing_columns()
            self._enforce_one_open_row()

    def _set_legacy_table_aside(self) -> None:
        """Move a pre-provenance ``state_triples`` out of the way.

        There are no users, so nothing here migrates: backfilling ``reason``
        for rows written before the column existed could only invent one. The
        old table is renamed rather than dropped — the rows stay on disk and
        stay unread.
        """
        try:
            cols = {
                r["name"]
                for r in self._conn.execute("PRAGMA table_info(state_triples)").fetchall()
            }
        except Exception:
            return
        if not cols or all(c in cols for c in _PROVENANCE_COLUMNS):
            return
        target = _LEGACY_TABLE
        try:
            # Never DROP. A previous set-aside is real history too, and the
            # whole point of this branch is that pre-provenance rows are kept.
            # Pick a free name instead.
            existing = {
                r["name"]
                for r in self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            suffix = 2
            while target in existing:
                target = f"{_LEGACY_TABLE}_{suffix}"
                suffix += 1
            self._conn.execute(f"ALTER TABLE state_triples RENAME TO {target}")
            logger.info(
                "state ledger predates provenance; old rows set aside in %s "
                "(unread, never backfilled)", target,
            )
        except Exception as e:
            # Losing a race with another process that migrated first is the
            # expected case here, and is fine: it already did the work.
            logger.info(f"pre-provenance table not set aside ({e})")

    def _enforce_one_open_row(self) -> None:
        """Create the one-open-row index, or say loudly why it could not be.

        An existing database that already holds duplicate open rows cannot
        take the index. That is a real finding about that database, not a
        reason to fail to open it -- so log it and carry on unindexed rather
        than making the ledger unreadable.
        """
        try:
            self._conn.execute(_OPEN_ROW_INDEX)
        except Exception as e:
            logger.warning(
                "state ledger: could not enforce one-open-row-per-key (%s). "
                "The table already holds duplicates; `why()` will resolve one "
                "of them arbitrarily until they are closed.", e,
            )

    def _add_missing_columns(self) -> None:
        """Add later columns to a table that already exists.

        ``_SCHEMA``'s ``CREATE TABLE IF NOT EXISTS`` cannot do this: on an
        existing table it is a no-op, so a column declared there alone never
        appears on a real database. See :data:`_ADDITIVE_COLUMNS`.
        """
        try:
            cols = {
                r["name"]
                for r in self._conn.execute("PRAGMA table_info(state_triples)").fetchall()
            }
        except Exception:  # pragma: no cover - defensive
            return
        if not cols:
            return  # no table yet; _SCHEMA creates it complete
        for name, decl in _ADDITIVE_COLUMNS.items():
            if name in cols:
                continue
            try:
                self._conn.execute(
                    f"ALTER TABLE state_triples ADD COLUMN {name} {decl}"
                )
                logger.info("state ledger: added column %s", name)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"Could not add column {name}: {e}")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_state(
        self,
        subject: str,
        predicate: str,
        obj: str,
        source: str,
        *,
        reason: str,
        actor: str,
        request_id: Optional[str] = None,
        confidence: float = 1.0,
        thread_id: Optional[str] = None,
        now: Optional[float] = None,
    ) -> Optional[int]:
        """Record a fact, closing whatever it supersedes.

        Re-recording the value that is already current is a no-op, so a tracker
        resyncing unchanged state does not churn the history — and note that a
        no-op discards this call's ``reason``, correctly: nothing changed, so
        there is nothing to explain.

        Args:
            subject/predicate/obj: the triple.
            source: the mechanism that wrote it (``"state_tracker:disk"``).
            reason: **why** — a human utterance, a self-naming deterministic
                rule, or :data:`UNRECORDED`. Never a generated rationale.
            actor: **who** — :data:`ACTOR_USER`, :data:`ACTOR_AGENT`,
                :data:`ACTOR_SYSTEM`, or a specific identifier.
            request_id: joins this row to its audit record. The join key is
                ``request_id`` and never an event sequence number, which is not
                unique under a concurrent append.

        Returns the new row id, or None if nothing was written or the write
        failed.

        Raises:
            TypeError: if ``reason`` or ``actor`` is omitted.
            ValueError: if either is empty.
        """
        reason = _require(reason, "reason")
        actor = _require(actor, "actor")
        ts = time.time() if now is None else now
        try:
            with self._lock:
                try:
                    return self._record_locked(
                        subject, predicate, obj, source, reason, actor,
                        request_id, confidence, thread_id, ts,
                    )
                except sqlite3.IntegrityError:
                    # Lost the one-open-row race. The winner has now closed
                    # its own row, so a second attempt supersedes it normally
                    # and this reason survives. Retried once, not looped: a
                    # second failure is a real problem, not contention.
                    logger.info(
                        "state ledger: retrying %s/%s after a concurrent write",
                        subject, predicate,
                    )
                    return self._record_locked(
                        subject, predicate, obj, source, reason, actor,
                        request_id, confidence, thread_id, ts,
                    )
        except Exception as e:
            logger.warning(f"Failed to record {subject}/{predicate}: {e}")
            return None

    def _record_locked(self, subject, predicate, obj, source, reason, actor,
                       request_id, confidence, thread_id, ts):
        """The read-modify-write, under one immediate transaction.

        BEGIN IMMEDIATE takes the write lock before the SELECT. Without it
        sqlite3 defers the transaction to the first DML, so the read sat
        outside the lock and two writers could both see no open row.
        """
        began = False
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            began = True
        except sqlite3.OperationalError:
            # Already inside a transaction -- a caller-owned connection
            # mid-work. Degrade to the previous behaviour rather than
            # hijacking their transaction.
            pass
        try:
            result = self._record_body(
                subject, predicate, obj, source, reason, actor,
                request_id, confidence, thread_id, ts,
            )
            if began:
                self._conn.commit()
            return result
        except Exception:
            if began:
                self._conn.rollback()
            raise

    def _record_body(self, subject, predicate, obj, source, reason, actor,
                     request_id, confidence, thread_id, ts):
        """Close whatever this supersedes, then insert. Assumes the caller
        holds the write transaction."""
        cur = self._conn.execute(
            "SELECT id, object FROM state_triples "
            "WHERE subject = ? AND predicate = ? AND valid_to IS NULL",
            (subject, predicate),
        ).fetchone()
        if cur is not None:
            if cur["object"] == obj:
                return None            # unchanged; leave the history alone
            # The predecessor closed *because of this write*, so it records
            # this write's request id too. Without that, the predecessor
            # carries a copy of this reason under a *different* request_id,
            # and a request-keyed redaction leaves the words standing on a
            # row it cannot find.
            self._conn.execute(
                "UPDATE state_triples "
                "SET valid_to = ?, closed_reason = ?, closed_by = ?, "
                "    closed_by_request = ? "
                "WHERE id = ?",
                (ts, f"superseded: {reason}", actor, request_id, cur["id"]),
            )
        c = self._conn.execute(
            "INSERT INTO state_triples "
            "(subject, predicate, object, source, confidence, valid_from, "
            " valid_to, thread_id, reason, actor, request_id) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)",
            (subject, predicate, obj, source, confidence, ts, thread_id,
             reason, actor, request_id),
        )
        return c.lastrowid

    def invalidate_state(
        self,
        subject: str,
        predicate: str,
        *,
        reason: str,
        actor: str,
        request_id: Optional[str] = None,
        now: Optional[float] = None,
    ) -> int:
        """Close the open triple for this key. Returns rows closed (0 or 1).

        Closing is a change, so it carries provenance for the same reason a
        write does: nothing later can recover why a fact stopped being true.

        ``request_id`` matters more than it looks: without it these words are
        unreachable by ``redact_request``, which finds closed rows through
        ``closed_by_request``. A reason that cannot be forgotten is a reason
        that should not have been recorded.
        """
        reason = _require(reason, "reason")
        actor = _require(actor, "actor")
        ts = time.time() if now is None else now
        try:
            with self._lock, self._conn:
                c = self._conn.execute(
                    "UPDATE state_triples "
                    "SET valid_to = ?, closed_reason = ?, closed_by = ?, "
                    "    closed_by_request = ? "
                    "WHERE subject = ? AND predicate = ? AND valid_to IS NULL",
                    (ts, reason, actor, request_id, subject, predicate),
                )
                return c.rowcount or 0
        except Exception as e:
            logger.warning(f"Failed to invalidate {subject}/{predicate}: {e}")
            return 0

    def redact_request(self, request_id: str, *, actor: str) -> int:
        """Replace the stated reasons written under one request with UNRECORDED.

        This is the ledger's half of "forget that". It removes the *words* —
        which is where a human utterance lives — while leaving the facts and
        their timeline intact: what was true and when is not the thing being
        forgotten, and deleting rows would make the history lie.

        Two sets of rows carry those words, and missing the second is a real
        leak. The rows this request *wrote* hold it in ``reason``; the rows
        this request *closed* hold a copy in ``closed_reason``, under their
        own different ``request_id``. ``closed_by_request`` is what makes the
        second set findable — string-matching ``"superseded: " + reason``
        would be a guess, and would miss anything already partly redacted.

        Returns the number of rows changed. Calling it twice is safe and the
        second call returns 0: already forgotten is not a failure.

        Raises on a write failure rather than returning 0. This is the one
        method here that does: everywhere else an empty result is a fine
        approximation of a failure, but a caller that reports "the words are
        gone" must not be able to say so because the UPDATE quietly did not
        happen.
        """
        actor = _require(actor, "actor")
        request_id = _require(request_id, "request_id")
        try:
            with self._lock, self._conn:
                own = self._conn.execute(
                    "UPDATE state_triples SET reason = ? "
                    "WHERE request_id = ? AND reason != ?",
                    (UNRECORDED, request_id, UNRECORDED),
                ).rowcount or 0
                # closed_by is NOT touched: who closed a row is a fact, like
                # the timestamp beside it, and forgetting is about the words.
                closed = self._conn.execute(
                    "UPDATE state_triples SET closed_reason = ? "
                    "WHERE closed_by_request = ? AND closed_reason != ?",
                    (UNRECORDED, request_id, UNRECORDED),
                ).rowcount or 0
                changed = own + closed
            if changed:
                # secure_delete zeroes the page, but the pre-redaction image
                # can still sit in the WAL until it is folded back in.
                #
                # PRAGMA wal_checkpoint does NOT raise when it cannot run: it
                # returns (busy, log, checkpointed) with busy=1, so ignoring
                # the row let a refused checkpoint pass for a completed one
                # and forget_request reported success while the words were
                # still readable in the file.
                self._checkpoint_or_raise()
            return changed
        except Exception as e:
            logger.warning(f"Failed to redact request {request_id}: {e}")
            # NOT a swallowed 0. A caller reporting on a forget cannot tell a
            # failed redaction from "nothing matched" if both return the same
            # value, and would say the words were removed when they were not.
            raise

    def _checkpoint_or_raise(self, attempts: int = 3) -> None:
        """Fold the WAL back into the database, or say it could not be done."""
        for attempt in range(attempts):
            row = self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if row is None or not row[0]:
                return
            time.sleep(0.05 * (attempt + 1))
        raise RuntimeError(
            "the redaction was written but the write-ahead log could not be "
            "checkpointed, so a copy of the old text may remain readable in "
            "the database file. A reader is holding it open."
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def current_state(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        *,
        strict: bool = False,
    ) -> List[StateTriple]:
        """Everything true right now, optionally narrowed to a subject/predicate.

        ``strict`` re-raises a read failure instead of returning an empty
        list. The default exists for state trackers on the hot path, which
        would rather lose a reading than break a turn. Any caller that
        REPORTS the result must pass ``strict=True``: an empty list and a
        failed read are the same value here, and rendering the second as the
        first tells the reader that nothing was recorded when the truth is
        that nothing could be looked at.
        """
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
            if strict:
                raise
            return []

    def state_history(self, subject: str, predicate: str, *,
                      strict: bool = False) -> List[StateTriple]:
        """Every value this key has held, oldest first.

        See :meth:`current_state` on ``strict``.
        """
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
            if strict:
                raise
            return []

    def why(self, subject: str, predicate: str, *,
            strict: bool = False) -> StateWhy:
        """*What is true, since when, who changed it, and why* — in one query.

        Returns the open triple together with the value it replaced, which is
        the before/after pair a config diff and a "why is X configured this
        way" answer both need. ``StateWhy.found`` is False when the key is
        unknown; the ledger abstains rather than guessing.
        """
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT * FROM state_triples "
                    "WHERE subject = ? AND predicate = ? AND valid_to IS NULL "
                    "ORDER BY valid_from DESC, id DESC LIMIT 1",
                    (subject, predicate),
                ).fetchone()
                prev = self._conn.execute(
                    "SELECT * FROM state_triples "
                    "WHERE subject = ? AND predicate = ? AND valid_to IS NOT NULL "
                    "ORDER BY valid_to DESC, id DESC LIMIT 1",
                    (subject, predicate),
                ).fetchone()
        except Exception as e:
            logger.warning(f"Failed to read why for {subject}/{predicate}: {e}")
            if strict:
                raise
            return StateWhy(subject, predicate, None, None)
        return StateWhy(
            subject=subject,
            predicate=predicate,
            current=_row(cur) if cur is not None else None,
            superseded=_row(prev) if prev is not None else None,
        )

    def by_request(self, request_id: str, *,
                   strict: bool = False) -> List[StateTriple]:
        """Every triple written under one request — the join to the audit log.

        ``request_id`` is the join key on purpose. An event sequence number is
        not unique under a concurrent append, so a seq-keyed join can silently
        point at the wrong record.
        """
        try:
            with self._lock:
                return [
                    _row(r)
                    for r in self._conn.execute(
                        "SELECT * FROM state_triples WHERE request_id = ? "
                        "ORDER BY valid_from, id",
                        (request_id,),
                    ).fetchall()
                ]
        except Exception as e:
            logger.warning(f"Failed to read triples for request {request_id}: {e}")
            if strict:
                raise
            return []

    def close(self) -> None:
        """Close the connection, unless a caller owns it."""
        if self._owns_conn:
            try:
                self._conn.close()
            except Exception:
                pass
