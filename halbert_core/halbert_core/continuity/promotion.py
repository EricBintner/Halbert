# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Recall-driven promotion store (OpenClaw short-term-promotion pattern).

Design rules lifted from the review:
- promotion signals are USAGE facts (recall count, distinct queries, distinct days,
  average gate score) — never write-time confidence;
- decay multiplies ranking and never deletes;
- content derived from recalled material never re-enters (provenance guard) —
  "a fact recalled one hundred times stays one fact";
- hard gates (min recall count, min diversity) keep one-off trivia out.

Pure and deterministic: no model, no network. Phase A2 adds persistence to
the continuity state DB and wiring at the two live recall sites.
"""
from __future__ import annotations

import hashlib
import logging
import math
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Optional, Sequence, Tuple

from .state_store import default_state_db_path

logger = logging.getLogger("halbert.continuity.promotion")

__all__ = [
    "HALF_LIFE_DAYS",
    "MIN_RECALL_COUNT",
    "MIN_QUERY_DIVERSITY",
    "PromotionSignals",
    "PromotionCandidate",
    "PromotionStore",
    "get_promotion_store",
    "rank_candidates",
]

HALF_LIFE_DAYS = 30.0
MIN_RECALL_COUNT = 3
MIN_QUERY_DIVERSITY = 2

#: A signal key is a ledger claim key: ``(subject, predicate)``. Claim-shaped
#: on purpose (the promotion second-guess verdict) — never a memory-row id.
PromotionKey = Tuple[str, str]


@dataclass
class PromotionSignals:
    recall_count: int = 0
    query_diversity: int = 0
    recall_days: int = 0
    avg_score: float = 0.0
    #: A01-G2 + bug 2 (fix-first row 21): this is a SNAPSHOT, written at
    #: record time and reloaded verbatim, and both callers passed 0.0. So
    #: "decay multiplies ranking" was a no-op: a key recalled once, sixty
    #: days ago, ranked as if it had been recalled today. It is kept for
    #: the persisted shape; the ranker reads ``last_recalled_at`` and
    #: derives the age itself.
    last_recalled_days_ago: float = 0.0
    #: When this key was last recalled, in epoch seconds. The fact the
    #: age is derived FROM, rather than a number frozen at write time.
    last_recalled_at: float = 0.0

    def days_since_recall(self, now: Optional[float] = None) -> float:
        """How long ago this key was last recalled, derived at READ time."""
        if not self.last_recalled_at:
            return self.last_recalled_days_ago
        current = now if now is not None else time.time()
        return max(0.0, (current - self.last_recalled_at) / 86400.0)


@dataclass(frozen=True)
class PromotionCandidate:
    key: PromotionKey
    signals: PromotionSignals


def _signal_score(s: PromotionSignals, now: Optional[float] = None) -> float:
    utility = math.log1p(s.recall_count)
    diversity = s.query_diversity / 5.0
    spread = s.recall_days / 5.0
    # A01-G2: derived at RANK time. Reading the stored snapshot meant the
    # half-life did nothing, because the snapshot was always the value
    # the recorder wrote (0.0 from both callers).
    recency = math.exp(
        -math.log(2) / HALF_LIFE_DAYS * s.days_since_recall(now))
    return 0.5 * utility + 0.2 * diversity + 0.2 * spread + 0.1 * recency


def rank_candidates(
    candidates: Sequence[PromotionCandidate],
    limit: int,
    now: Optional[float] = None,
) -> list:
    """The candidates worth promoting, best first.

    ``now`` is the clock the recency decay is measured against, injected
    so a test can age a key without waiting (A01-G2).
    """
    eligible = [
        c for c in candidates
        if c.signals.recall_count >= MIN_RECALL_COUNT
        and c.signals.query_diversity >= MIN_QUERY_DIVERSITY
    ]
    ranked = sorted(
        eligible, key=lambda c: _signal_score(c.signals, now), reverse=True)
    return ranked[:limit]


#: Three tables, all brand-new (so plain ``CREATE TABLE IF NOT EXISTS`` is
#: the whole migration — the ``_ADDITIVE_COLUMNS`` pattern exists for *column
#: adds to tables that already shipped*, which this is not). The aggregate
#: table answers "what does this claim's signal say"; the two companion
#: tables keep the raw query hashes and recall days so diversity and spread
#: keep growing correctly across process restarts. Raw user text is never
#: stored — only its sha256 prefix.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS promotion_signals (
    subject               TEXT NOT NULL,
    predicate             TEXT NOT NULL,
    recall_count          INTEGER NOT NULL,
    query_diversity       INTEGER NOT NULL,
    recall_days           INTEGER NOT NULL,
    avg_score             REAL NOT NULL,
    last_recalled_days_ago REAL NOT NULL,
    updated_at            REAL NOT NULL,
    PRIMARY KEY (subject, predicate)
);
CREATE TABLE IF NOT EXISTS promotion_queries (
    subject    TEXT NOT NULL,
    predicate  TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    PRIMARY KEY (subject, predicate, query_hash)
);
CREATE TABLE IF NOT EXISTS promotion_recall_days (
    subject   TEXT NOT NULL,
    predicate TEXT NOT NULL,
    day       TEXT NOT NULL,
    PRIMARY KEY (subject, predicate, day)
);
"""


class PromotionStore:
    """In-process signal accumulator; snapshots persist to the continuity DB (A2).
    Queries are stored as sha256 so chatty loops can't inflate diversity with
    trivially different strings, and raw user text never lands in the store.

    Built with no ``db_path``/``conn`` the store is pure in-memory — that is
    what the pure tests and any fail-soft fallback want. Built with a path it
    loads existing signals on open and upserts on every record; every
    persistence failure degrades to in-memory and never raises.
    """

    def __init__(self, db_path: Optional[str] = None,
                 conn: Optional[sqlite3.Connection] = None):
        self._signals: Dict[PromotionKey, PromotionSignals] = {}
        self._queries: Dict[PromotionKey, set] = {}
        self._days: Dict[PromotionKey, set] = {}
        #: A01-G5: key -> the request that recorded it, so a forget can
        #: reach the evidence. In-process only: the tables themselves are
        #: keyed by claim, and a persisted request link would be one more
        #: durable fact about the person than the signal needs.
        self._request_keys: Dict[PromotionKey, str] = {}
        self._lock = threading.Lock()
        self._owns_conn = conn is None
        self._conn: Optional[sqlite3.Connection] = None
        if db_path is not None or conn is not None:
            self._attach(db_path=db_path, conn=conn)

    # -- persistence ---------------------------------------------------

    def _attach(self, *, db_path: Optional[str],
                conn: Optional[sqlite3.Connection]) -> None:
        """Open the DB, create the tables, load what is there. Fail-soft:
        any failure leaves the store in-memory-only, which still records."""
        try:
            if conn is None:
                conn = sqlite3.connect(db_path, check_same_thread=False)
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            conn.executescript(_SCHEMA)
            self._conn = conn
            self._load(conn)
        except Exception as e:
            # A signal store that cannot persist is a quieter store, not a
            # broken one. Never raise into the caller that asked for it.
            logger.warning(
                f"promotion store: persistence unavailable, continuing "
                f"in memory: {e}")
            self._conn = None

    def _load(self, conn: sqlite3.Connection) -> None:
        for r in conn.execute(
                "SELECT subject, predicate, avg_score, "
                "last_recalled_days_ago, updated_at FROM promotion_signals"):
            key = (r["subject"], r["predicate"])
            self._signals[key] = PromotionSignals(
                avg_score=float(r["avg_score"]),
                last_recalled_days_ago=float(r["last_recalled_days_ago"]),
                # A01-G2: the timestamp the age is derived from. Written
                # as ``updated_at`` since the column existed; it was
                # never read back, which is what made the decay inert.
                last_recalled_at=float(r["updated_at"] or 0.0))
        for r in conn.execute(
                "SELECT subject, predicate, query_hash FROM promotion_queries"):
            self._queries.setdefault(
                (r["subject"], r["predicate"]), set()).add(r["query_hash"])
        for r in conn.execute(
                "SELECT subject, predicate, day FROM promotion_recall_days"):
            self._days.setdefault(
                (r["subject"], r["predicate"]), set()).add(
                date.fromisoformat(r["day"]))
        # The raw sets are the source of truth for the derived fields, so a
        # reloaded store recomputes them instead of trusting the aggregate.
        for key, sig in self._signals.items():
            sig.recall_count = max(sig.recall_count,
                                   len(self._queries.get(key, ())))
            sig.query_diversity = len(self._queries.get(key, ()))
            sig.recall_days = len(self._days.get(key, ()))

    def _persist(self, key: PromotionKey, sig: PromotionSignals,
                 query_hash: str, day: date) -> None:
        subject, predicate = key
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO promotion_signals (subject, predicate, "
                    "recall_count, query_diversity, recall_days, avg_score, "
                    "last_recalled_days_ago, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(subject, predicate) DO UPDATE SET "
                    "recall_count=excluded.recall_count, "
                    "query_diversity=excluded.query_diversity, "
                    "recall_days=excluded.recall_days, "
                    "avg_score=excluded.avg_score, "
                    "last_recalled_days_ago=excluded.last_recalled_days_ago, "
                    "updated_at=excluded.updated_at",
                    (subject, predicate, sig.recall_count, sig.query_diversity,
                     sig.recall_days, sig.avg_score,
                     sig.last_recalled_days_ago, time.time()))
                self._conn.execute(
                    "INSERT OR IGNORE INTO promotion_queries "
                    "(subject, predicate, query_hash) VALUES (?, ?, ?)",
                    (subject, predicate, query_hash))
                self._conn.execute(
                    "INSERT OR IGNORE INTO promotion_recall_days "
                    "(subject, predicate, day) VALUES (?, ?, ?)",
                    (subject, predicate, day.isoformat()))
        except sqlite3.Error as e:
            logger.warning(
                f"promotion store: write failed, signal kept in memory: {e}")

    def close(self) -> None:
        if self._conn is not None and self._owns_conn:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
        self._conn = None

    # -- recording -----------------------------------------------------

    def record_recall(self, key: PromotionKey, query: str, *,
                      request_id: str = "", days_ago: float = 0.0,
                      score: float = 0.0, provenance: str = "agent_query") -> None:
        if provenance == "recalled_content":
            return  # recall-loop hygiene: never re-enter
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        # A recall recorded as ``days_ago`` happened that many days back; the
        # day set must reflect *when*, not when the signal happened to be
        # written, or multi-day recurrence is invisible.
        day = date.today() - timedelta(days=days_ago)
        with self._lock:
            sig = self._signals.setdefault(key, PromotionSignals())
            sig.recall_count += 1
            self._queries.setdefault(key, set()).add(query_hash)
            self._days.setdefault(key, set()).add(day)
            sig.query_diversity = len(self._queries[key])
            sig.recall_days = len(self._days[key])
            # Running average, weighted by the count so a store reloaded from
            # persistence keeps the same mean.
            prev_n = sig.recall_count - 1
            sig.avg_score = ((sig.avg_score * prev_n) + score) / sig.recall_count
            sig.last_recalled_days_ago = days_ago
            # A01-G2: the TIMESTAMP is what the ranker reads, so
            # ``days_ago`` means what it says -- "this recall happened N
            # days ago" -- rather than writing a snapshot nobody read
            # back. Both production callers pass 0.0, which is now
            # simply "just then"; a caller that back-dates gets a
            # back-dated key.
            sig.last_recalled_at = time.time() - (float(days_ago) * 86400.0)
            # A01-G5: which request this evidence came from, so a forget
            # can find it. The signal itself stores no words -- only the
            # link back to the run that produced it.
            if request_id:
                self._request_keys[key] = request_id
            if self._conn is not None:
                self._persist(key, sig, query_hash, day)

    def signals(self, key: PromotionKey) -> Optional[PromotionSignals]:
        return self._signals.get(key)

    def forget_request(self, request_id: str) -> int:
        """Erase every signal recorded under one request id (A01-G5).

        The three tables move together: a signal row whose companion
        query hashes and recall days survived would keep contributing
        diversity and spread to a key that is supposed to be gone.
        """
        if not request_id:
            return 0
        removed = 0
        with self._lock:
            keys = [k for k, rid in self._request_keys.items() if rid == request_id]
            for key in keys:
                self._signals.pop(key, None)
                self._queries.pop(key, None)
                self._days.pop(key, None)
                self._request_keys.pop(key, None)
                removed += 1
            if self._conn is not None and keys:
                try:
                    with self._conn:
                        for subject, predicate in keys:
                            for table in ("promotion_signals",
                                          "promotion_queries",
                                          "promotion_recall_days"):
                                self._conn.execute(
                                    f"DELETE FROM {table} WHERE subject = ? "
                                    f"AND predicate = ?",
                                    (subject, predicate))
                except Exception as e:
                    logger.warning(
                        "promotion signals for %s could not be erased: %s",
                        request_id, e)
        return removed


_store: Optional[PromotionStore] = None
_store_lock = threading.Lock()


def get_promotion_store() -> PromotionStore:
    """The process-wide store, persisted beside the state ledger.

    Fail-soft on construction: a state DB that cannot be opened (read-only
    directory, missing parent) degrades this store to in-memory signals.
    Recording must never raise into a turn — memory failures never eat a
    turn.
    """
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                try:
                    path = str(default_state_db_path())
                except Exception as e:
                    logger.warning(
                        f"promotion store: no state db path ({e}); signals "
                        f"stay in memory")
                    path = None
                _store = PromotionStore(db_path=path) if path else PromotionStore()
    return _store


def forget_request_signals(request_id: str) -> int:
    """Erase the promotion evidence recorded under one request (A01-G5).

    "Forget that session" reached the change ledger, the audit records
    and the conversation messages, and left the promotion tables holding
    a durable record that those words mattered -- keyed to a claim, and
    therefore about the person who said them.

    Returns how many signal rows were removed, so the caller's report can
    say what it actually erased rather than what it hoped to.
    """
    store = get_promotion_store()
    return store.forget_request(request_id)
