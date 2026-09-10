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
import re
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
    "MAX_AGE_DAYS",
    "MIN_RECALL_COUNT",
    "MIN_QUERY_DIVERSITY",
    "MIN_SCORE",
    "PromotionSignals",
    "PromotionCandidate",
    "PromotionStore",
    "context_diversity",
    "get_promotion_store",
    "normalize_query",
    "promotion_score",
    "rank_candidates",
]

HALF_LIFE_DAYS = 30.0

# A01-G7: the origin's gate block, and it carries its own calibration --
# "3-day/3-query durable facts at 0.750-0.756, versus repeated filler at
# 0.489-0.549 and high-relevance one-offs at 0.529-0.606". Halbert kept
# two of the four numbers, halved the diversity floor and counted queries
# alone. No handoff records a decision to drop the rest, and that is what
# makes it a gap rather than a difference: the numbers came from
# measurement and arrived here without it.
#
# All four are AND-ed. Each answers a different way a key looks durable
# and is not: recalled often in one burst; recalled from one intent
# spelled three ways; recalled a lot last spring; recalled often and
# weakly.
MIN_RECALL_COUNT = 3
MIN_QUERY_DIVERSITY = 3
MIN_SCORE = 0.75
MAX_AGE_DAYS = 30

_WHITESPACE = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    """The form a query is hashed in (A01-G11).

    The hash was taken over the RAW string, so "Printer Status", "printer
    status" and "  printer   status " were three distinct queries -- two of
    which cleared the old diversity floor from a single intent. The
    docstring on the store said the hash existed to stop exactly that.

    Trim and case-fold are the origin's (``normalizeNullableString``);
    collapsing internal whitespace is Halbert's addition and strictly
    stronger, because the same question retyped is the same question.
    """
    return _WHITESPACE.sub(" ", str(query or "")).strip().lower()

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


def context_diversity(s: PromotionSignals) -> int:
    """``max(unique_queries, recall_days)`` -- the origin's measure.

    Asking the same question on three different days is three pieces of
    evidence about durability. Counting queries alone threw two of them
    away, and counting days alone would throw away three different
    questions asked in one sitting.
    """
    return max(int(s.query_diversity), int(s.recall_days))


def promotion_score(s: PromotionSignals, now: Optional[float] = None) -> float:
    """The 0..1 score the gates are calibrated against."""
    return _signal_score(s, now)


#: Where each component stops buying anything. Recall count saturates at
#: ten (an eleventh recall of the same thing is not new evidence);
#: diversity and spread at four, one above the gate, so clearing the bar
#: is worth something and clearing it four times over is not worth four
#: times as much.
_UTILITY_SATURATION = 10
_EVIDENCE_SATURATION = 4

#: Weights, summing to 1 so the score is a 0..1 quantity that MIN_SCORE
#: can be compared against.
#:
#: A01-G7, and this is the half the gap rows do not say out loud: the
#: origin's MIN_SCORE=0.75 was measured against the ORIGIN's scale. The
#: score here summed an uncapped ``log1p`` with three fractions and could
#: exceed 1.0, so importing 0.75 onto it would have been a number that
#: passed everything with three recalls -- a gate in name. These weights
#: are fitted to the origin's own three calibration bands, quoted in its
#: comment at ``dreaming.ts:43-50``:
#:
#:   3-day/3-query durable facts   0.750-0.756  -> 0.78 here
#:   repeated filler               0.489-0.549  -> 0.55 here (10/1/1)
#:   high-relevance one-offs       0.529-0.606  -> 0.54 here (1/1/1, rel .9)
#:
#: Ordering and separation are what the gate rests on, and both hold. A
#: durable fact with NO relevance lands at 0.73 and is refused, which is
#: the behaviour the bands describe.
_W_UTILITY = 0.10
_W_DIVERSITY = 0.25
_W_SPREAD = 0.25
_W_RECENCY = 0.30
_W_RELEVANCE = 0.10


def _signal_score(s: PromotionSignals, now: Optional[float] = None) -> float:
    utility = min(1.0, math.log1p(s.recall_count)
                  / math.log1p(_UTILITY_SATURATION))
    diversity = min(1.0, context_diversity(s) / _EVIDENCE_SATURATION)
    spread = min(1.0, s.recall_days / _EVIDENCE_SATURATION)
    relevance = min(1.0, max(0.0, float(s.avg_score)))
    # A01-G2: derived at RANK time. Reading the stored snapshot meant the
    # half-life did nothing, because the snapshot was always the value
    # the recorder wrote (0.0 from both callers).
    recency = math.exp(
        -math.log(2) / HALF_LIFE_DAYS * s.days_since_recall(now))
    return (_W_UTILITY * utility
            + _W_DIVERSITY * diversity
            + _W_SPREAD * spread
            + _W_RECENCY * recency
            + _W_RELEVANCE * relevance)


def _is_eligible(c: PromotionCandidate, now: Optional[float]) -> bool:
    """The four gates, AND-ed, in the origin's order (A01-G7)."""
    s = c.signals
    if s.recall_count < MIN_RECALL_COUNT:
        return False
    if context_diversity(s) < MIN_QUERY_DIVERSITY:
        return False
    if s.days_since_recall(now) > MAX_AGE_DAYS:
        return False
    return _signal_score(s, now) >= MIN_SCORE


def _live(candidate: PromotionCandidate, is_live) -> bool:
    """A01-G13: is the claim this signal is about still there?

    A signal outlives the claim it was recorded for -- ``invalidate_state``
    closes a row with no hook toward promotion, and forgetting a
    conversation deletes messages rather than signals -- so a key can go on
    ranking for something that no longer exists.

    A predicate that RAISES keeps the candidate. A liveness check that
    cannot answer is not a licence to promote, and it is not a reason to
    promote nothing either: the sweep continues and the failure is a log
    line.
    """
    if is_live is None:
        return True
    try:
        return bool(is_live(candidate.key))
    except Exception as e:
        logger.warning("promotion liveness check failed for %r: %s",
                       candidate.key, e)
        return True


def rank_candidates(
    candidates: Sequence[PromotionCandidate],
    limit: int,
    now: Optional[float] = None,
    *,
    is_live=None,
    emit_events: bool = False,
) -> list:
    """The candidates worth promoting, best first.

    ``now`` is the clock the recency decay is measured against, injected
    so a test can age a key without waiting (A01-G2). ``is_live`` is the
    optional liveness predicate (A01-G13). ``emit_events`` records the
    sweep on the timeline (A01-G9) -- off by default, because this is a
    pure function and an event per call would surprise every caller that
    is asking a question rather than taking an action.
    """
    eligible = [
        c for c in candidates
        if _is_eligible(c, now) and _live(c, is_live)
    ]
    ranked = sorted(
        eligible, key=lambda c: _signal_score(c.signals, now), reverse=True)
    ranked = ranked[:limit]
    if emit_events:
        _record_event(
            "promotion.ranked" if ranked else "promotion.skipped",
            title=(f"{len(ranked)} of {len(candidates)} signals ranked"
                   if ranked else
                   f"nothing eligible out of {len(candidates)} signals"),
            data={
                "considered": len(candidates),
                "promoted": len(ranked),
                # Keys, counts and scores -- never the words that were
                # recalled. The signal store holds no text and neither
                # does its ledger row.
                "keys": [
                    {"subject": c.key[0], "predicate": c.key[1],
                     "score": round(_signal_score(c.signals, now), 4),
                     "recall_count": c.signals.recall_count}
                    for c in ranked
                ],
            },
        )
    return ranked


def _record_event(event_type: str, *, title: str, data: dict) -> None:
    """One promotion event on the ratified ledger (A01-G9).

    Never raises: an observation that can break the thing it observes is
    not an observation, it is a dependency.
    """
    try:
        from . import timeline

        timeline.append_event(
            event_type, source="promotion", severity="info",
            title=title, data=data)
    except Exception as e:  # pragma: no cover - append_event swallows its own
        logger.debug("promotion event skipped (non-fatal): %s", e)


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
            # A01-G12: one malformed day used to take the whole load with
            # it. ``date.fromisoformat`` ran inside the single try around
            # ``_attach``, so the exception disabled persistence for the
            # process AND left the store half-loaded -- the signals loop
            # above had already run, so a previously persisted key came
            # back with zeroed counts rather than being absent, which is
            # worse than missing: it looks loaded.
            try:
                day = date.fromisoformat(r["day"])
            except (ValueError, TypeError) as e:
                logger.warning(
                    "promotion store: skipping malformed recall day %r for "
                    "%s/%s (%s)", r["day"], r["subject"], r["predicate"], e)
                continue
            self._days.setdefault(
                (r["subject"], r["predicate"]), set()).add(day)
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
        # A01-G11: the NORMALISED query. Hashing the raw string made
        # three spellings of one intent three "distinct queries", which is
        # the inflation the hash was introduced to prevent.
        query_hash = hashlib.sha256(
            normalize_query(query).encode()).hexdigest()[:16]
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
            recorded = PromotionSignals(**vars(sig))
        # A01-G9, outside the lock: the ledger write is I/O and the
        # signal store's lock guards an in-memory dict.
        _record_event(
            "recall.recorded",
            title=f"{key[0]}/{key[1]} recalled ({recorded.recall_count})",
            data={
                "subject": key[0], "predicate": key[1],
                "recall_count": recorded.recall_count,
                "query_diversity": recorded.query_diversity,
                "recall_days": recorded.recall_days,
                # The query itself is never recorded -- not here and not
                # in the store. Only that one was asked.
            },
        )

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
