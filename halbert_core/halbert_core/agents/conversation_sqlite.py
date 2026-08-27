# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SQLite + FTS5 store of record for the one continuous conversation.

``conversations`` rows are *threads* (the physical column ``conversation_id``
on ``messages`` is the thread id everywhere). ``append_message`` is the only
message write path; ``save`` upserts the thread row and never touches
messages. Every write runs inside ``with self._conn:`` so a failed write
rolls back as a unit. Failures are logged at WARNING and reported as
``None``/``False`` so a route can emit ``thread_store_error`` once.

See documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md §8.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .blocks import content_to_text
from .conversation import Conversation, Message

logger = logging.getLogger("halbert.agents.conversation_sqlite")

_DEFAULT_DB = str(Path.home() / ".halbert" / "conversations.db")

#: Bump when a migration step below must run on existing databases.
SCHEMA_VERSION = 2

# Columns added to the legacy tables. ``_ensure_schema`` applies each one
# with ``ALTER TABLE ... ADD COLUMN`` when ``PRAGMA table_info`` lacks it.
_THREAD_COLUMNS: List[Tuple[str, str]] = [
    ("status", "TEXT NOT NULL DEFAULT 'open'"),
    ("receipt", "TEXT NOT NULL DEFAULT ''"),
    ("receipt_updated_at", "REAL"),
    ("topic_domains", "TEXT NOT NULL DEFAULT '[]'"),
    ("entities_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("last_active", "REAL"),
    ("stale", "INTEGER NOT NULL DEFAULT 0"),
    ("ephemeral", "INTEGER NOT NULL DEFAULT 0"),
    ("parent_thread_id", "TEXT"),
    ("merged_into", "TEXT"),
    ("recalled_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("unread", "INTEGER NOT NULL DEFAULT 0"),
    ("paused_at", "REAL"),
    ("turns_since_pause", "INTEGER NOT NULL DEFAULT 0"),
    ("title_source", "TEXT NOT NULL DEFAULT 'provisional'"),
]
_MESSAGE_COLUMNS: List[Tuple[str, str]] = [
    ("turn_id", "TEXT"),
    ("session_id", "TEXT"),
    ("origin", "TEXT NOT NULL DEFAULT 'human'"),
    ("status", "TEXT NOT NULL DEFAULT 'complete'"),
    ("blocks_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("terminal_block_ids", "TEXT NOT NULL DEFAULT '[]'"),
    ("diff_proposals_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("visible_in_timeline", "INTEGER NOT NULL DEFAULT 1"),
]

# update_message field -> column
_MESSAGE_UPDATABLE = {
    "content": "content",
    "status": "status",
    "blocks": "blocks_json",
    "terminal_block_ids": "terminal_block_ids",
    "diff_proposals": "diff_proposals_json",
    "metadata": "metadata",
    "thread_id": "conversation_id",
}
_MESSAGE_JSON_COLUMNS = {"blocks_json", "terminal_block_ids", "diff_proposals_json", "metadata"}

_THREAD_JSON_LISTS = ("topic_domains", "entities_json", "recalled_json")
_THREAD_FLAGS = ("stale", "ephemeral", "unread")
_THREAD_UPDATABLE = {"title", "updated_at", "user_id", "metadata"} | {
    name for name, _ in _THREAD_COLUMNS
}

_THREAD_SELECT = """SELECT c.*,
    (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count,
    (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id AND m.role = 'user') AS turn_count
    FROM conversations c"""

_TURN_KEY = "COALESCE(turn_id, 'm' || id)"
_TURN_KEYS_SQL = (
    f"SELECT {_TURN_KEY} AS turn_key, MIN(id) AS first_id "
    "FROM messages WHERE visible_in_timeline = 1 GROUP BY turn_key"
)
# PERF NOTE (A1b round-3 review, finding 2): this expression can't be served
# by `idx_messages_turn`, so every `list_turns` call does a full GROUP BY
# scan of the whole `messages` table -- and does it three times over (this
# query, `_turn_first_id`, and the final `visible_in_timeline` fetch by key),
# all inside the same `self._lock` RLock `append_message` needs. That is
# O(total messages) on the hot read path of a conversation designed never to
# end, and it blocks concurrent writes for the whole page. Measured on this
# branch: ~20ms/40k messages, ~120-190ms/200k messages. This matches the
# design specified in the Plan A task text, so it is not a deviation -- but
# it should not be assumed to stay flat as the corpus grows. Before A11 (or
# any other paging consumer) leans on this at scale, either bound the GROUP
# BY to an id window (turns have bounded row counts, so
# `id > anchor - limit * K` is safe) or backfill `turn_id` on legacy rows so
# a plain indexed column can be grouped instead.

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Dropped from receipt queries so a score reflects topical words only.
_QUERY_STOPWORDS = frozenset("""
a about above actually add after again against ago all also am an and another any anything are as at
back be because been before being below between both but by can cannot check could day days did do does
doing done down during each earlier else ever everything few fine fix for from further get give go going
got had has have having he hello help her here hers hey hi him his how i if in into is it its itself just
know last let like look luck make maybe me might month months more most much must my need needed no nor not
nothing now of off ok okay on once one only or other our ours out over own please put really remember run
same see set shall she should show since so some something still such sure take tell than thank thanks
that the their theirs them then there these they thing think this those through time to today tomorrow
too try under until up us use used using very want wanted was way we week weeks well were what when where
which while who whom why will with work working works would yes yesterday yet you your yours
""".split())


def _fts_terms(query: str, *, drop_stopwords: bool = True, max_terms: int = 12) -> List[str]:
    """Lowercase alphanumeric tokens of ``query`` (deduplicated, ordered)."""
    out: List[str] = []
    for tok in _TOKEN_RE.findall((query or "").lower()):
        if drop_stopwords and (len(tok) < 2 or tok in _QUERY_STOPWORDS):
            continue
        if tok not in out:
            out.append(tok)
        if len(out) >= max_terms:
            break
    return out


def _fts_query(terms: Sequence[str]) -> str:
    """Each term quoted so FTS5 syntax characters (``.``/``'``) cannot abort a MATCH."""
    return " OR ".join(f'"{t}"' for t in terms)


def _term_hits(terms: Sequence[str], haystack: str) -> List[str]:
    """Terms whose crude stem (drop the last letter past 4 chars) starts a word in ``haystack``."""
    out: List[str] = []
    for t in terms:
        stem = t[:-1] if len(t) > 4 else t
        if re.search(r"\b" + re.escape(stem), haystack):
            out.append(t)
    return out


def _receipt_snippet(receipt: str, matched: Sequence[str]) -> str:
    """Line of ``receipt`` most likely to contain a ``matched`` term.

    Literal substring first -- this already covers the common direction,
    where the receipt line holds the longer inflected word and a shorter
    query term/stem is a substring of it (e.g. line "...the resilver has
    not finished..." vs. query term "resilver"). When nothing matches
    literally, a shared-prefix word scan steps in for the *other*
    direction: a query term such as "resilvering" that only matched via
    the porter stemmer's -ing/-ed/-ion suffix stripping, where the shorter
    receipt word ("resilver") is a prefix of the longer query term rather
    than the reverse, so no substring check in either direction finds it
    (A3 review round 2, finding 3). Porter only strips suffixes, so an
    inflected form and its stem always share a prefix -- this is the same
    reason ``match_terms`` above stopped trying to reimplement Porter
    itself, but there it could re-ask the live FTS index per term; there
    is no per-line index here to ask the same question of, so a prefix
    scan over the line's own words is the cheap stand-in.
    """
    lines = [ln for ln in (receipt or "").splitlines() if ln.strip()]
    for ln in lines:
        low = ln.lower()
        if any(t in low for t in matched):
            return ln[:200]
    for ln in lines:
        words = _TOKEN_RE.findall(ln.lower())
        if any(
            len(t) >= 4 and len(w) >= 4 and (t.startswith(w) or w.startswith(t))
            for t in matched
            for w in words
        ):
            return ln[:200]
    return lines[0][:200] if lines else ""


def _loads(text: Any, default: Any) -> Any:
    if not text:
        return default
    try:
        value = json.loads(text)
    except Exception:
        return default
    return value if value is not None else default


class SqliteConversationStore:
    """SQLite-backed thread/message store with FTS5 search.

    Thread-safe (single connection + re-entrant lock). Best-effort: methods
    log at WARNING and return ``None``/``False``/``[]`` rather than raise.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._fts_ok = False
        try:
            if self._db_path != ":memory:":
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._ensure_schema()
        except Exception as e:
            logger.warning(f"SqliteConversationStore init failed (non-fatal): {e}")
            self._conn = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    @staticmethod
    def _add_missing_columns(cur: sqlite3.Cursor, table: str, columns: List[Tuple[str, str]]) -> None:
        existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, decl in columns:
            if name in existing:
                continue
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
            except sqlite3.OperationalError as e:
                # A concurrent opener may have added this column between our
                # PRAGMA table_info read and this ALTER (belt-and-suspenders:
                # _ensure_schema also serializes openers with BEGIN IMMEDIATE,
                # but this keeps a single column race from aborting every
                # column after it — see A1 review finding 1).
                if "duplicate column name" in str(e):
                    continue
                raise

    def _ensure_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            # busy_timeout first: it must be in effect before anything below
            # (the WAL pragma, then BEGIN IMMEDIATE) can hit SQLITE_BUSY.
            try:
                cur.execute("PRAGMA busy_timeout=5000")
            except Exception as e:
                logger.warning(f"SqliteConversationStore schema failed (busy_timeout pragma): {e}")
                self._conn = None
                return
            # A journal-mode change requires SQLite to grab an exclusive lock,
            # and — unlike BEGIN IMMEDIATE below — that lock request does NOT
            # go through the busy handler: SQLite returns SQLITE_BUSY
            # immediately if any other connection currently holds the write
            # lock, busy_timeout or no busy_timeout. Treating that as fatal
            # used to abort the migration before a single CREATE/ALTER TABLE
            # ran while leaving ``self._conn`` set, so the instance silently
            # lost every future write for the rest of its life (A1 review
            # finding 1). WAL is a nice-to-have, not required for
            # correctness, so tolerate the failure and keep going in the
            # connection's default rollback-journal mode — BEGIN IMMEDIATE
            # right below still waits out busy_timeout for the migration
            # itself.
            try:
                cur.execute("PRAGMA journal_mode=WAL")
            except Exception as e:
                logger.warning(f"PRAGMA journal_mode=WAL failed, continuing without WAL: {e}")
            # Serialize schema creation/migration across concurrent openers of
            # the same database file. BEGIN IMMEDIATE claims the write lock
            # up front (busy_timeout above governs how long a racing opener
            # waits here) instead of letting every opener's PRAGMA table_info
            # + ALTER TABLE sequence race one another: the loser used to see
            # a schema missing the exact columns another opener was mid-way
            # through adding, raise, and abort the rest of its own migration
            # (A1 review finding 1).
            try:
                cur.execute("BEGIN IMMEDIATE")
            except Exception as e:
                logger.warning(f"SqliteConversationStore schema failed (lock): {e}")
                self._conn = None
                return
            try:
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS conversations (
                        id         TEXT PRIMARY KEY,
                        user_id    TEXT,
                        title      TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        metadata   TEXT NOT NULL DEFAULT '{}'
                    )"""
                )
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS messages (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id  TEXT NOT NULL,
                        role             TEXT NOT NULL,
                        content          TEXT NOT NULL,
                        timestamp        REAL NOT NULL,
                        metadata         TEXT NOT NULL DEFAULT '{}'
                    )"""
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_messages_conv "
                    "ON messages(conversation_id)"
                )
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS session_somatic_blocks (
                        id         TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        block_id   TEXT NOT NULL,
                        block_type TEXT,
                        status     TEXT,
                        created_at REAL NOT NULL,
                        metadata   TEXT NOT NULL DEFAULT '{}'
                    )"""
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ssb_session "
                    "ON session_somatic_blocks(session_id)"
                )
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
                )
                # Opt-in LLM summaries (spec §8, §14): the table ships in Plan A
                # with no writers — compaction stays default-off until a later plan.
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS compact_boundaries (
                        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                        thread_id             TEXT NOT NULL,
                        trigger               TEXT NOT NULL,
                        pre_tokens            INTEGER,
                        post_tokens           INTEGER,
                        preserved_message_ids TEXT NOT NULL DEFAULT '[]',
                        summary_message_id    INTEGER,
                        created_at            REAL NOT NULL
                    )"""
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_compact_thread "
                    "ON compact_boundaries(thread_id)"
                )
                self._add_missing_columns(cur, "conversations", _THREAD_COLUMNS)
                self._add_missing_columns(cur, "messages", _MESSAGE_COLUMNS)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_messages_turn ON messages(turn_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_conversations_status "
                    "ON conversations(status)"
                )
                row = cur.execute("SELECT MAX(version) FROM schema_version").fetchone()
                version = int(row[0]) if row and row[0] is not None else 0
                # Tracked locally and only committed to ``self._fts_ok`` once the
                # whole migration (including the schema_version bump below and
                # the final commit) has actually succeeded — see the comment on
                # the outer ``except`` for why (A1 review finding 2).
                fts_ready = False
                try:
                    if version < 2:
                        # v2: porter stemming + rowid == messages.id (for snippets).
                        cur.execute("DROP TABLE IF EXISTS messages_fts")
                        cur.execute(
                            "CREATE VIRTUAL TABLE messages_fts USING fts5("
                            "conversation_id UNINDEXED, content, "
                            "tokenize='porter unicode61')"
                        )
                        cur.execute(
                            "INSERT INTO messages_fts(rowid, conversation_id, content) "
                            "SELECT id, conversation_id, content FROM messages"
                        )
                        fts_ready = True
                    else:
                        cur.execute(
                            "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
                            "conversation_id UNINDEXED, content, "
                            "tokenize='porter unicode61')"
                        )
                        # Backfill: an already-versioned DB whose messages_fts
                        # table was just (re)created by ``IF NOT EXISTS`` (e.g.
                        # a runtime without FTS5 wrote unindexed rows, and this
                        # runtime has it) would otherwise report ``healthy``
                        # over a permanently empty index (A1 review finding 2).
                        cur.execute(
                            "INSERT INTO messages_fts(rowid, conversation_id, content) "
                            "SELECT id, conversation_id, content FROM messages "
                            "WHERE id NOT IN (SELECT rowid FROM messages_fts)"
                        )
                        fts_ready = True
                    cur.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS receipts_fts USING fts5("
                        "thread_id UNINDEXED, title, receipt, "
                        "tokenize='porter unicode61')"
                    )
                    # Backfill: same rationale as the messages_fts backfill
                    # just above -- a DB that had receipts written while a
                    # runtime without FTS5 was in charge would otherwise
                    # reopen "healthy" over a receipts_fts table missing
                    # those rows forever (mirrors A1 review finding 2, closed
                    # here for receipts_fts per the A3 review).
                    cur.execute(
                        "INSERT INTO receipts_fts(thread_id, title, receipt) "
                        "SELECT id, title, receipt FROM conversations "
                        "WHERE receipt != '' AND id NOT IN "
                        "(SELECT thread_id FROM receipts_fts)"
                    )
                except sqlite3.OperationalError as e:
                    logger.warning(f"FTS5 unavailable, falling back to LIKE: {e}")
                    fts_ready = False
                if version < SCHEMA_VERSION:
                    cur.execute("DELETE FROM schema_version")
                    cur.execute(
                        "INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,)
                    )
                self._conn.commit()
                # Only now, after a successful commit, does the flag reflect
                # reality. Setting it earlier (as before) meant a later
                # statement raising would roll back the just-created FTS
                # tables while the flag stayed True, and ``_fts_recover()``
                # short-circuits on a True flag, so it would never have
                # re-verified (A1 review finding 2, the mirror of finding 3's
                # False-latch bug).
                self._fts_ok = fts_ready
            except Exception as e:
                self._conn.rollback()
                logger.warning(f"SqliteConversationStore schema failed: {e}")
                self._fts_ok = False
                # A half-applied migration (e.g. the messages table missing
                # thread columns) must not look like a healthy, usable store:
                # every subsequent method already treats ``self._conn is None``
                # as "fail loudly/return the documented empty result" instead
                # of quietly writing against a schema that doesn't match what
                # the rest of this class assumes (A1 review finding 1).
                self._conn = None

    @property
    def healthy(self) -> bool:
        """``False`` while degraded: no connection, or FTS5 unavailable so
        ``search`` falls back to title-only ``LIKE`` matching. A route can
        poll this to emit ``thread_store_error`` once instead of finding out
        only when a search silently comes back thin."""
        return self._conn is not None and self._fts_ok

    def _fts_recover(self) -> bool:
        """Return whether FTS5 is currently usable, retrying table creation
        when it previously was not.

        ``_fts_ok`` is not a permanent kill switch: a transient failure at
        connect time (a migration race, a momentarily-unavailable extension)
        should not disable search for the rest of the process's life, so
        every caller that used to gate on ``self._fts_ok`` directly now calls
        this instead (A1 review finding 3). Safe to call from inside an
        already-open write transaction (e.g. from ``append_message``): when
        one is already open (``self._conn.in_transaction``) it leaves the
        commit/rollback to that caller's own ``with self._conn:`` block;
        otherwise (a standalone call, e.g. from ``search``) it commits its
        own work itself so nothing is left dangling uncommitted.

        Recovery also backfills: any ``messages`` row not yet present in
        ``messages_fts`` is indexed, so a table that was just (re)created
        by ``CREATE VIRTUAL TABLE IF NOT EXISTS`` does not report healthy
        over what would otherwise stay a permanently empty index for rows
        written before recovery (A1 review finding 2). ``receipts_fts`` gets
        the identical backfill for the identical reason: ``upsert_receipt``
        writes ``conversations.receipt`` unconditionally but only mirrors it
        into ``receipts_fts`` while ``self._fts_recover()`` reports healthy,
        so any receipt written during a degraded window would otherwise
        never appear in the index, even after recovery (A3 review finding 1).
        """
        if self._fts_ok or self._conn is None:
            return self._fts_ok
        try:
            with self._lock:
                nested = self._conn.in_transaction
                self._conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
                    "conversation_id UNINDEXED, content, "
                    "tokenize='porter unicode61')"
                )
                self._conn.execute(
                    "INSERT INTO messages_fts(rowid, conversation_id, content) "
                    "SELECT id, conversation_id, content FROM messages "
                    "WHERE id NOT IN (SELECT rowid FROM messages_fts)"
                )
                self._conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS receipts_fts USING fts5("
                    "thread_id UNINDEXED, title, receipt, "
                    "tokenize='porter unicode61')"
                )
                self._conn.execute(
                    "INSERT INTO receipts_fts(thread_id, title, receipt) "
                    "SELECT id, title, receipt FROM conversations "
                    "WHERE receipt != '' AND id NOT IN "
                    "(SELECT thread_id FROM receipts_fts)"
                )
                if not nested:
                    self._conn.commit()
            self._fts_ok = True
            logger.info("FTS5 recovered; search is no longer degraded to title-only")
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS5 still unavailable, staying in LIKE-only fallback: {e}")
        return self._fts_ok

    # ------------------------------------------------------------------
    # Legacy CRUD (Conversation dataclass shape)
    # ------------------------------------------------------------------

    def get(self, conversation_id: str) -> Optional[Conversation]:
        if self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
                ).fetchone()
                if row is None:
                    return None
                msgs = self._conn.execute(
                    "SELECT role, content, timestamp, metadata FROM messages "
                    "WHERE conversation_id = ? ORDER BY id ASC", (conversation_id,)
                ).fetchall()
        except Exception as e:
            logger.warning(f"sqlite get failed: {e}")
            return None
        conv = Conversation(
            conversation_id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=_loads(row["metadata"], {}),
        )
        conv.messages = [
            Message(
                role=m["role"],
                content=m["content"],
                timestamp=m["timestamp"],
                metadata=_loads(m["metadata"], {}),
            )
            for m in msgs
        ]
        return conv

    def create(self, conversation_id: str, user_id: Optional[str] = None) -> Conversation:
        conv = Conversation(conversation_id=conversation_id, user_id=user_id)
        self.save(conv)
        return conv

    def get_or_create(self, conversation_id: str, user_id: Optional[str] = None) -> Conversation:
        conv = self.get(conversation_id)
        return conv if conv is not None else self.create(conversation_id, user_id)

    def save(self, conversation: Conversation) -> bool:
        """Upsert the thread row only. Messages are written by ``append_message``."""
        if self._conn is None:
            return False
        cid = conversation.conversation_id
        meta = json.dumps(conversation.metadata or {})
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    """INSERT INTO conversations
                       (id, user_id, title, created_at, updated_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                         user_id    = excluded.user_id,
                         title      = excluded.title,
                         updated_at = MAX(conversations.updated_at, excluded.updated_at),
                         metadata   = excluded.metadata""",
                    (cid, conversation.user_id, conversation.title,
                     conversation.created_at, conversation.updated_at, meta),
                )
            return True
        except Exception as e:
            logger.warning(f"sqlite save failed: {e}")
            return False

    def delete(self, conversation_id: str) -> bool:
        if self._conn is None:
            return False
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "DELETE FROM conversations WHERE id = ?", (conversation_id,)
                )
                self._conn.execute(
                    "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
                )
                if self._fts_ok:
                    self._conn.execute(
                        "DELETE FROM messages_fts WHERE conversation_id = ?",
                        (conversation_id,),
                    )
                    self._conn.execute(
                        "DELETE FROM receipts_fts WHERE thread_id = ?",
                        (conversation_id,),
                    )
            return True
        except Exception as e:
            logger.warning(f"sqlite delete failed: {e}")
            return False

    def list_conversations(
        self, user_id: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        if self._conn is None:
            return []
        try:
            with self._lock:
                if user_id:
                    cur = self._conn.execute(
                        """SELECT c.id, c.title, c.user_id, c.created_at, c.updated_at,
                                  (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
                           FROM conversations c WHERE c.user_id = ?
                           ORDER BY c.updated_at DESC LIMIT ? OFFSET ?""",
                        (user_id, limit, offset),
                    )
                else:
                    cur = self._conn.execute(
                        """SELECT c.id, c.title, c.user_id, c.created_at, c.updated_at,
                                  (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
                           FROM conversations c
                           ORDER BY c.updated_at DESC LIMIT ? OFFSET ?""",
                        (limit, offset),
                    )
                rows = cur.fetchall()
            return [{
                "conversation_id": r["id"],
                "title": r["title"],
                "user_id": r["user_id"],
                "message_count": r["message_count"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            } for r in rows]
        except Exception as e:
            logger.warning(f"sqlite list_conversations failed: {e}")
            return []

    def search(
        self, query: str, user_id: Optional[str] = None, limit: int = 20
    ) -> List[str]:
        """Full-text search over message content (+ title LIKE). Returns thread ids."""
        if self._conn is None or not query:
            return []
        results: List[str] = []
        terms = _fts_terms(query, drop_stopwords=False)
        if self._fts_recover() and terms:
            try:
                with self._lock:
                    rows = self._conn.execute(
                        """SELECT DISTINCT m.conversation_id
                           FROM messages_fts m
                           JOIN conversations c ON c.id = m.conversation_id
                           WHERE messages_fts MATCH ? AND (? IS NULL OR c.user_id = ?)
                           LIMIT ?""",
                        (_fts_query(terms), user_id, user_id, limit),
                    ).fetchall()
                results = [r[0] for r in rows]
            except Exception as e:
                logger.warning(f"sqlite FTS search failed (LIKE fallback only): {e}")
        try:
            with self._lock:
                trows = self._conn.execute(
                    """SELECT id FROM conversations
                       WHERE lower(title) LIKE ? AND (? IS NULL OR user_id = ?)
                       LIMIT ?""",
                    (f"%{query.lower()}%", user_id, user_id, limit),
                ).fetchall()
            for r in trows:
                if r[0] not in results:
                    results.append(r[0])
        except Exception as e:
            logger.warning(f"sqlite title search failed: {e}")
        return results[:limit]

    # ------------------------------------------------------------------
    # Messages (append-only write path)
    # ------------------------------------------------------------------

    def append_message(
        self,
        thread_id: str,
        role: str,
        content: Any,
        *,
        origin: str = "human",
        turn_id: Optional[str] = None,
        session_id: Optional[str] = None,
        status: str = "complete",
        blocks: Optional[list] = None,
        terminal_block_ids: Optional[List[str]] = None,
        diff_proposals: Optional[list] = None,
        metadata: Optional[dict] = None,
        timestamp: Optional[float] = None,
        visible_in_timeline: bool = True,
    ) -> Optional[int]:
        """Insert one message row + its FTS row in a single transaction.

        Returns the new row id, or ``None`` (after a WARNING) when the write
        failed; nothing is left behind on failure. ``None`` is also returned,
        with no row written, when ``thread_id`` does not name an existing
        conversation (there is no FK, so a typo'd/deleted/merged thread id
        would otherwise write a message no ``get``/``search``/``list_threads``
        call can ever surface again — A1 review finding 4).
        """
        if self._conn is None:
            return None
        if isinstance(content, str):
            text = content
        else:
            text = content_to_text(content)
            if blocks is None and isinstance(content, list):
                blocks = [
                    b.to_dict() if hasattr(b, "to_dict") and callable(b.to_dict) else b
                    for b in content
                ]
        ts = float(timestamp) if timestamp is not None else time.time()
        try:
            with self._lock, self._conn:
                if self._conn.execute(
                    "SELECT 1 FROM conversations WHERE id = ?", (thread_id,)
                ).fetchone() is None:
                    raise ValueError(f"no such thread_id {thread_id!r}")
                cur = self._conn.execute(
                    """INSERT INTO messages
                       (conversation_id, role, content, timestamp, metadata, turn_id,
                        session_id, origin, status, blocks_json, terminal_block_ids,
                        diff_proposals_json, visible_in_timeline)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (thread_id, role, text, ts, json.dumps(metadata or {}), turn_id,
                     session_id, origin, status, json.dumps(blocks or []),
                     json.dumps(terminal_block_ids or []),
                     json.dumps(diff_proposals or []), 1 if visible_in_timeline else 0),
                )
                message_id = int(cur.lastrowid)
                if self._fts_recover():
                    # OR REPLACE: ``_fts_recover()`` may itself have just
                    # backfilled this exact row (it runs its NOT-IN-fts
                    # backfill against ``messages`` as it stands right now,
                    # which already includes the row inserted immediately
                    # above) -- a plain INSERT would then collide on rowid
                    # with what recovery already wrote (same content either
                    # way, so replacing is a no-op in substance).
                    self._conn.execute(
                        "INSERT OR REPLACE INTO messages_fts(rowid, conversation_id, content) "
                        "VALUES (?, ?, ?)",
                        (message_id, thread_id, text),
                    )
                # MAX(...): agrees with save()'s ON CONFLICT clause (A1 review
                # finding 3) so the two write paths can't rewind each other.
                # migrate_json_conversations_to_sqlite backfills with an
                # explicit, often much older, ``timestamp=`` — an
                # unconditional assignment here would otherwise drop a
                # thread's recency below whatever it already was, corrupting
                # ``ORDER BY updated_at DESC`` in list_conversations/list_threads
                # (A1 review finding 3).
                self._conn.execute(
                    "UPDATE conversations SET updated_at = MAX(updated_at, ?) WHERE id = ?",
                    (ts, thread_id),
                )
            return message_id
        except Exception as e:
            logger.warning(f"append_message failed for thread {thread_id}: {e}")
            return None

    def update_message(self, message_id: int, **fields: Any) -> bool:
        """Update allowed columns of one message row (re-indexes FTS when needed).

        Allowed: content, status, blocks, terminal_block_ids, diff_proposals,
        metadata, thread_id.
        """
        if self._conn is None or not fields:
            return False
        sets: List[str] = []
        params: List[Any] = []
        for key, value in fields.items():
            col = _MESSAGE_UPDATABLE.get(key)
            if col is None:
                logger.warning(f"update_message: unknown field {key!r}")
                return False
            if col in _MESSAGE_JSON_COLUMNS:
                if value is None:
                    value = {} if col == "metadata" else []
                value = json.dumps(value)
            elif col == "content" and not isinstance(value, str):
                value = content_to_text(value)
            sets.append(f"{col} = ?")
            params.append(value)
        params.append(message_id)
        reindex = "content" in fields or "thread_id" in fields
        try:
            with self._lock, self._conn:
                if "thread_id" in fields:
                    # Same orphaning bug append_message's existence check
                    # closed (A1 review finding 4), left open on this sibling
                    # write path: with no FK on conversation_id, moving a
                    # message to a thread id that doesn't exist would silently
                    # make it invisible to every reader (get/search/list) for
                    # good, and thread_id moves are exactly what merge/split
                    # tasks later in Plan A use this method for.
                    new_thread_id = fields["thread_id"]
                    if self._conn.execute(
                        "SELECT 1 FROM conversations WHERE id = ?", (new_thread_id,)
                    ).fetchone() is None:
                        raise ValueError(f"no such thread_id {new_thread_id!r}")
                cur = self._conn.execute(
                    f"UPDATE messages SET {', '.join(sets)} WHERE id = ?", params
                )
                if cur.rowcount == 0:
                    return False
                if reindex and self._fts_recover():
                    row = self._conn.execute(
                        "SELECT conversation_id, content FROM messages WHERE id = ?",
                        (message_id,),
                    ).fetchone()
                    self._conn.execute(
                        "DELETE FROM messages_fts WHERE rowid = ?", (message_id,)
                    )
                    self._conn.execute(
                        "INSERT INTO messages_fts(rowid, conversation_id, content) "
                        "VALUES (?, ?, ?)",
                        (message_id, row["conversation_id"], row["content"]),
                    )
            return True
        except Exception as e:
            logger.warning(f"update_message {message_id} failed: {e}")
            return False

    def mark_in_progress_interrupted(self) -> int:
        """Boot-time sweep: every ``in_progress`` row becomes ``interrupted``."""
        if self._conn is None:
            return 0
        try:
            with self._lock, self._conn:
                cur = self._conn.execute(
                    "UPDATE messages SET status = 'interrupted' WHERE status = 'in_progress'"
                )
                return int(cur.rowcount or 0)
        except Exception as e:
            logger.warning(f"mark_in_progress_interrupted failed: {e}")
            return 0

    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------

    def create_thread(
        self,
        thread_id: str,
        title: str,
        *,
        status: str = "open",
        title_source: str = "provisional",
        created_at: Optional[float] = None,
        parent_thread_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        """Insert a new thread row. False when the id exists or the write fails."""
        if self._conn is None:
            return False
        ts = float(created_at) if created_at is not None else time.time()
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    """INSERT INTO conversations
                       (id, user_id, title, created_at, updated_at, metadata,
                        status, title_source, parent_thread_id)
                       VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)""",
                    (thread_id, title, ts, ts, json.dumps(metadata or {}),
                     status, title_source, parent_thread_id),
                )
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"create_thread: thread {thread_id} already exists")
            return False
        except Exception as e:
            logger.warning(f"create_thread failed: {e}")
            return False

    def update_thread(self, thread_id: str, **fields: Any) -> bool:
        """Update thread columns. Lists/dicts are JSON-encoded; flags coerced to 0/1."""
        if self._conn is None or not fields:
            return False
        sets: List[str] = []
        params: List[Any] = []
        for key, value in fields.items():
            if key not in _THREAD_UPDATABLE:
                logger.warning(f"update_thread: unknown field {key!r}")
                return False
            if key in _THREAD_JSON_LISTS:
                value = json.dumps(list(value or []))
            elif key == "metadata":
                value = json.dumps(value or {})
            elif key in _THREAD_FLAGS:
                value = 1 if value else 0
            sets.append(f"{key} = ?")
            params.append(value)
        params.append(thread_id)
        try:
            with self._lock, self._conn:
                cur = self._conn.execute(
                    f"UPDATE conversations SET {', '.join(sets)} WHERE id = ?", params
                )
                return cur.rowcount > 0
        except Exception as e:
            logger.warning(f"update_thread {thread_id} failed: {e}")
            return False

    @staticmethod
    def _row_to_thread(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        out: Dict[str, Any] = {"thread_id": d["id"]}
        out.update(d)
        for key in _THREAD_JSON_LISTS:
            out[key] = _loads(d.get(key), [])
        out["metadata"] = _loads(d.get("metadata"), {})
        return out

    def get_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        if self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    _THREAD_SELECT + " WHERE c.id = ?", (thread_id,)
                ).fetchone()
            return self._row_to_thread(row) if row is not None else None
        except Exception as e:
            logger.warning(f"get_thread {thread_id} failed: {e}")
            return None

    def list_threads(
        self, status: Optional[Any] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Threads newest-activity-first, optionally filtered by status(es)."""
        if self._conn is None:
            return []
        statuses: List[str] = []
        if isinstance(status, str):
            statuses = [status]
        elif status:
            statuses = [str(s) for s in status]
        where = ""
        params: List[Any] = []
        if statuses:
            where = " WHERE c.status IN (" + ",".join("?" * len(statuses)) + ")"
            params.extend(statuses)
        params.append(limit)
        try:
            with self._lock:
                rows = self._conn.execute(
                    _THREAD_SELECT + where
                    + " ORDER BY COALESCE(c.last_active, c.updated_at) DESC, c.created_at DESC"
                    + " LIMIT ?",
                    params,
                ).fetchall()
            return [self._row_to_thread(r) for r in rows]
        except Exception as e:
            logger.warning(f"list_threads failed: {e}")
            return []

    def current_open_thread(self) -> Optional[Dict[str, Any]]:
        if self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    _THREAD_SELECT
                    + " WHERE c.status = 'open' ORDER BY c.updated_at DESC LIMIT 1"
                ).fetchone()
            return self._row_to_thread(row) if row is not None else None
        except Exception as e:
            logger.warning(f"current_open_thread failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Message readers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "message_id": row["id"],
            "thread_id": row["conversation_id"],
            "role": row["role"],
            "content": row["content"],
            "timestamp": row["timestamp"],
            "origin": row["origin"],
            "status": row["status"],
            "turn_id": row["turn_id"],
            "session_id": row["session_id"],
            "blocks": _loads(row["blocks_json"], []),
            "terminal_block_ids": _loads(row["terminal_block_ids"], []),
            "diff_proposals": _loads(row["diff_proposals_json"], []),
            "metadata": _loads(row["metadata"], {}),
            "visible_in_timeline": bool(row["visible_in_timeline"]),
        }

    def list_messages(self, thread_id: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Every row of a thread, oldest-first, with decoded JSON columns."""
        if self._conn is None:
            return []
        sql = "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC"
        params: List[Any] = [thread_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        try:
            with self._lock:
                rows = self._conn.execute(sql, params).fetchall()
            return [self._row_to_message(r) for r in rows]
        except Exception as e:
            logger.warning(f"list_messages {thread_id} failed: {e}")
            return []

    def recent_messages(self, thread_id: str, limit: int = 12) -> List[Dict[str, Any]]:
        """Last ``limit`` human/assistant rows of a thread, oldest-first."""
        if self._conn is None:
            return []
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT role, content, timestamp, origin FROM messages
                       WHERE conversation_id = ? AND origin IN ('human', 'assistant')
                       ORDER BY id DESC LIMIT ?""",
                    (thread_id, int(limit)),
                ).fetchall()
            return [
                {"role": r["role"], "content": r["content"],
                 "timestamp": r["timestamp"], "origin": r["origin"]}
                for r in reversed(rows)
            ]
        except Exception as e:
            logger.warning(f"recent_messages {thread_id} failed: {e}")
            return []

    def _turn_first_id(self, turn_id: str) -> Optional[int]:
        """First *visible* row id for a turn key -- must agree with
        ``_TURN_KEYS_SQL`` (also visible-only) or an anchor computed here
        can sit earlier than a turn's real timeline position when its
        lowest-id row happens to be hidden, silently excluding turns that
        genuinely precede it from a ``before_turn_id``/``around_turn_id``
        page (A1b round-3 review, finding 1)."""
        row = self._conn.execute(
            f"SELECT MIN(id) FROM messages WHERE {_TURN_KEY} = ? AND visible_in_timeline = 1",
            (turn_id,),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def list_turns(
        self,
        *,
        before_turn_id: Optional[str] = None,
        around_turn_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Timeline page: visible rows grouped by turn, newest-last.

        ``before_turn_id`` pages backwards (turns strictly older); ``around_turn_id``
        centres a page on a turn. Callers ask for ``limit + 1`` to learn ``has_more``.
        """
        if self._conn is None or limit <= 0:
            return []
        try:
            with self._lock:
                if before_turn_id is not None:
                    anchor = self._turn_first_id(before_turn_id)
                    if anchor is None:
                        return []
                    rows = self._conn.execute(
                        f"SELECT turn_key FROM ({_TURN_KEYS_SQL}) WHERE first_id < ? "
                        "ORDER BY first_id DESC LIMIT ?",
                        (anchor, limit),
                    ).fetchall()
                    keys = [r["turn_key"] for r in rows][::-1]
                elif around_turn_id is not None:
                    anchor = self._turn_first_id(around_turn_id)
                    if anchor is None:
                        return []
                    # Fetch up to `limit` on each side so a shortfall on one
                    # side can be topped up from the other -- otherwise a
                    # page anchored near either end of the timeline returns
                    # fewer than `limit` turns with nothing backfilling it.
                    before = self._conn.execute(
                        f"SELECT turn_key FROM ({_TURN_KEYS_SQL}) WHERE first_id < ? "
                        "ORDER BY first_id DESC LIMIT ?",
                        (anchor, limit),
                    ).fetchall()
                    after = self._conn.execute(
                        f"SELECT turn_key FROM ({_TURN_KEYS_SQL}) WHERE first_id >= ? "
                        "ORDER BY first_id ASC LIMIT ?",
                        (anchor, limit),
                    ).fetchall()
                    before_keys = [r["turn_key"] for r in before]  # newest-first
                    after_keys = [r["turn_key"] for r in after]  # oldest-first
                    want_before = limit // 2
                    want_after = limit - want_before
                    if len(before_keys) < want_before:
                        want_after = min(len(after_keys), want_after + (want_before - len(before_keys)))
                        want_before = len(before_keys)
                    elif len(after_keys) < want_after:
                        want_before = min(len(before_keys), want_before + (want_after - len(after_keys)))
                        want_after = len(after_keys)
                    keys = before_keys[:want_before][::-1] + after_keys[:want_after]
                else:
                    rows = self._conn.execute(
                        f"SELECT turn_key FROM ({_TURN_KEYS_SQL}) "
                        "ORDER BY first_id DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                    keys = [r["turn_key"] for r in rows][::-1]
                if not keys:
                    return []
                placeholders = ",".join("?" * len(keys))
                msgs = self._conn.execute(
                    f"SELECT * FROM messages WHERE visible_in_timeline = 1 "
                    f"AND {_TURN_KEY} IN ({placeholders}) ORDER BY id ASC",
                    keys,
                ).fetchall()
            return self._group_turns(msgs)
        except Exception as e:
            logger.warning(f"list_turns failed: {e}")
            return []

    def _group_turns(self, rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
        turns: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            m = self._row_to_message(row)
            key = m["turn_id"] or f"m{m['message_id']}"
            turn = turns.get(key)
            if turn is None:
                turn = turns[key] = {
                    "turn_id": key,
                    "thread_id": m["thread_id"],
                    "timestamp": m["timestamp"],
                    "user": None,
                    "assistant": None,
                    "blocks": [],
                    "terminal_block_ids": [],
                    "diff_proposals": [],
                    "origin": m["origin"],
                }
            slot = {
                "message_id": m["message_id"],
                "content": m["content"],
                "timestamp": m["timestamp"],
                "status": m["status"],
            }
            if m["role"] == "user":
                if turn["user"] is None:
                    turn["user"] = slot
            elif turn["assistant"] is None:
                turn["assistant"] = slot
            turn["blocks"].extend(m["blocks"])
            for tid in m["terminal_block_ids"]:
                if tid not in turn["terminal_block_ids"]:
                    turn["terminal_block_ids"].append(tid)
            turn["diff_proposals"].extend(m["diff_proposals"])
        return list(turns.values())

    # ------------------------------------------------------------------
    # Receipts (FTS over receipts, not raw messages)
    # ------------------------------------------------------------------

    def upsert_receipt(self, thread_id: str, title: str, receipt: str) -> bool:
        """Store a thread's receipt and replace its ``receipts_fts`` row."""
        if self._conn is None:
            return False
        try:
            with self._lock, self._conn:
                cur = self._conn.execute(
                    "UPDATE conversations SET receipt = ?, receipt_updated_at = ? WHERE id = ?",
                    (receipt or "", time.time(), thread_id),
                )
                if cur.rowcount == 0:
                    return False
                # ``_fts_recover()``, not ``self._fts_ok`` directly: a stale
                # degraded flag from a past transient failure must not skip
                # this row forever -- the same rule A1 review finding 3 set
                # for every other FTS-gated caller in this file, which this
                # method (added by A3) had not been following (A3 review
                # finding 1).
                if self._fts_recover():
                    self._conn.execute(
                        "DELETE FROM receipts_fts WHERE thread_id = ?", (thread_id,)
                    )
                    self._conn.execute(
                        "INSERT INTO receipts_fts(thread_id, title, receipt) VALUES (?, ?, ?)",
                        (thread_id, title or "", receipt or ""),
                    )
            return True
        except Exception as e:
            logger.warning(f"upsert_receipt {thread_id} failed: {e}")
            return False

    def _fts_term_hits_map(self, terms: Sequence[str]) -> Dict[str, frozenset]:
        """Which thread_ids the real ``receipts_fts`` index matches, per
        query term, checked against the tokenizer/stemmer the index
        actually runs (``porter unicode61``) -- one MATCH per term, not
        one per candidate row per term.

        PERF NOTE (A3 review round 2, finding 1): the per-row version this
        replaced ran a MATCH scoped by ``thread_id = ?`` for every
        candidate row for every term, and ``thread_id`` is an UNINDEXED FTS
        column, so each of those queries scanned that term's whole posting
        list looking for one thread. With the default ``limit=5`` that was
        up to ``max(limit*4,20)=20`` candidate rows x up to 12 terms = up
        to 240 MATCH queries per ``search_receipts`` call, and
        ``search_receipts`` runs on every user turn (plan-a-contracts.md
        line 89; the plan's ``_gather_candidates``,
        CONTINUOUS-CONVERSATION-PLAN-A-2026-08-26.md:2588) -- i.e. on the
        interactive hot path, with cost growing with the corpus (measured:
        200 threads 10ms, 2 000 threads 51ms, 10 000 threads 267ms; >90%
        of that was the recheck). Running one MATCH per *term* here instead
        -- independent of how many rows are being scored -- cuts that to
        O(terms): measured ~3.5x faster (14.9ms @2k threads, 78.6ms @10k,
        12 queries instead of up to 160). See the PERF NOTE on
        ``_TURN_KEYS_SQL`` above for the same class of issue elsewhere in
        this file.

        A3 review finding 2 (unchanged rationale, now applied per term
        instead of per row): the crude local stem in ``_term_hits`` (drop
        the last letter past 4 chars) only catches suffixes exactly one
        letter long, so a real porter match on an -ing/-ed/-ion form (e.g.
        query "resilvering" against an indexed "resilver") scored zero
        locally even though the row was returned by the very MATCH query
        that used that same term. Re-asking FTS per term instead of
        re-implementing Porter in Python is by construction never out of
        step with what indexed the row: this table's OR-joined MATCH
        (``_fts_query``) guarantees at least one term individually matches
        any row it returns.
        """
        out: Dict[str, frozenset] = {}
        failed: Optional[Exception] = None
        for t in terms:
            try:
                with self._lock:
                    rows = self._conn.execute(
                        "SELECT thread_id FROM receipts_fts WHERE receipts_fts MATCH ?",
                        (_fts_query([t]),),
                    ).fetchall()
                out[t] = frozenset(r["thread_id"] for r in rows)
            except Exception as e:
                failed = e
                out[t] = frozenset()
        if failed is not None:
            # A3 review round 2, finding 2: log once per call, not once per
            # term -- the old per-row helper swallowed every exception with
            # a bare ``except Exception: hit = None`` and never logged at
            # all, contradicting this class's own documented contract
            # (docstring above: "methods log at WARNING ... rather than
            # raise") and every other except block in this file, all of
            # which log. A broken/corrupt receipts_fts fails every term the
            # same way, so one WARNING per call (not N) says the same thing
            # without spamming the log once per query term.
            logger.warning(
                "receipt term recheck against receipts_fts failed for one "
                f"or more terms (falling back to score=0.25 for affected "
                f"rows): {failed}"
            )
        return out

    def _receipt_hit(
        self,
        row: sqlite3.Row,
        terms: Sequence[str],
        *,
        real_fts: bool,
        term_hits: Optional[Dict[str, frozenset]] = None,
    ) -> Dict[str, Any]:
        """``real_fts=True`` for a row the ``receipts_fts`` MATCH query
        itself returned (re-derive matched terms from ``term_hits``, the
        per-term thread_id map from ``_fts_term_hits_map`` -- pass one map
        in once per ``search_receipts`` call rather than recomputing it per
        row; omitted here it is computed for just this one row, e.g. for a
        direct/standalone call); ``real_fts=False`` for a row found only
        via the title LIKE fallback, where there is no live FTS match to
        re-ask and the crude local stem is the best available signal."""
        if real_fts:
            if term_hits is None:
                term_hits = self._fts_term_hits_map(terms)
            matched = [t for t in terms if row["thread_id"] in term_hits.get(t, ())]
        else:
            haystack = f"{row['title'] or ''} {row['receipt'] or ''}".lower()
            matched = _term_hits(terms, haystack)
        # Two topical terms are enough for a full score; a single hit on a
        # one-word query also scores 1.0. Unverifiable FTS hits keep 0.25 --
        # kept as a defensive default (e.g. every per-term recheck above
        # raising); reachable rows can no longer land here empty by
        # construction now that ``matched`` is re-derived from the same
        # index that selected the row (finding 2).
        score = min(1.0, len(matched) / max(1, min(len(terms), 3))) if matched else 0.25
        return {
            "thread_id": row["thread_id"],
            "title": row["title"] or "",
            "score": round(score, 3),
            "match_terms": matched,
            "snippet": _receipt_snippet(row["receipt"] or "", matched),
            "last_active": row["last_active"],
            "status": row["status"],
        }

    def search_receipts(
        self, query: str, *, exclude_thread_id: Optional[str] = None, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Rank threads by receipt/title relevance to ``query``.

        Query terms are quoted and OR-joined; the MATCH runs in its own try so
        an FTS failure degrades to the title LIKE pass instead of aborting.
        """
        if self._conn is None or not query:
            return []
        terms = _fts_terms(query)
        if not terms:
            return []
        hits: Dict[str, Dict[str, Any]] = {}
        if self._fts_recover():
            try:
                with self._lock:
                    rows = self._conn.execute(
                        """SELECT r.thread_id, r.title, r.receipt,
                                  c.last_active, c.status, c.created_at
                           FROM receipts_fts r JOIN conversations c ON c.id = r.thread_id
                           WHERE receipts_fts MATCH ? AND c.status != 'merged'
                             AND c.ephemeral = 0 AND (? IS NULL OR r.thread_id != ?)
                           ORDER BY bm25(receipts_fts) LIMIT ?""",
                        (_fts_query(terms), exclude_thread_id, exclude_thread_id,
                         max(limit * 4, 20)),
                    ).fetchall()
                if rows:
                    # One term-hit map for every row, not one per row (A3
                    # review round 2, finding 1) -- see the PERF NOTE on
                    # ``_fts_term_hits_map`` above.
                    term_hits = self._fts_term_hits_map(terms)
                    for r in rows:
                        hits[r["thread_id"]] = self._receipt_hit(
                            r, terms, real_fts=True, term_hits=term_hits
                        )
            except Exception as e:
                logger.warning(f"receipt FTS search failed (LIKE fallback only): {e}")
        try:
            like_rows: List[sqlite3.Row] = []
            with self._lock:
                for term in terms[:6]:
                    like_rows.extend(self._conn.execute(
                        """SELECT id AS thread_id, title, receipt, last_active, status, created_at
                           FROM conversations
                           WHERE lower(title) LIKE ? AND status != 'merged' AND ephemeral = 0
                             AND (? IS NULL OR id != ?)
                           LIMIT ?""",
                        (f"%{term}%", exclude_thread_id, exclude_thread_id, limit),
                    ).fetchall())
            for r in like_rows:
                if r["thread_id"] not in hits:
                    hits[r["thread_id"]] = self._receipt_hit(r, terms, real_fts=False)
        except Exception as e:
            logger.warning(f"receipt title search failed: {e}")
        ranked = sorted(
            hits.values(), key=lambda h: (-h["score"], -(h["last_active"] or 0.0))
        )
        return ranked[:limit]

    def search_snippets(self, thread_id: str, query: str, limit: int = 5) -> List[str]:
        """FTS snippets of one thread's messages matching ``query`` (best
        first), excluding hidden (``visible_in_timeline = 0``) rows -- the
        same rule every other reader in this file applies (A3 review finding
        3: internal bookkeeping rows such as A6d's retracted-recall marker
        must not surface as a user-facing recall snippet).
        """
        if self._conn is None or not query:
            return []
        terms = _fts_terms(query)
        if not terms:
            return []
        if not self._fts_recover():
            return []
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT snippet(messages_fts, 1, '', '', '…', 12) AS snip
                       FROM messages_fts
                       WHERE conversation_id = ? AND messages_fts MATCH ?
                         AND EXISTS (
                             SELECT 1 FROM messages m
                             WHERE m.id = messages_fts.rowid AND m.visible_in_timeline = 1
                         )
                       ORDER BY bm25(messages_fts) LIMIT ?""",
                    (thread_id, _fts_query(terms), int(limit)),
                ).fetchall()
            return [r["snip"] for r in rows if r["snip"]]
        except Exception as e:
            logger.warning(f"search_snippets {thread_id} failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Merge-back (spec §5 "Merge")
    # ------------------------------------------------------------------

    def merge_thread(
        self, src_thread_id: str, dst_thread_id: str, *, now: Optional[float] = None
    ) -> Optional[int]:
        """Fold thread ``src`` into thread ``dst`` in one transaction.

        Moves every message row (and its ``messages_fts`` row) of ``src`` onto
        ``dst``; marks ``src`` ``merged`` (``merged_into = dst``, receipt
        dropped, ``receipts_fts`` row deleted); reopens ``dst`` (status open,
        ``paused_at`` cleared, ``turns_since_pause`` reset). Returns the number
        of rows moved, or ``None`` when either thread is missing or the write
        failed (nothing is left half-done).
        """
        if self._conn is None or not src_thread_id or src_thread_id == dst_thread_id:
            return None
        ts = float(now) if now is not None else time.time()
        try:
            with self._lock, self._conn:
                present = self._conn.execute(
                    "SELECT COUNT(*) FROM conversations WHERE id IN (?, ?)",
                    (src_thread_id, dst_thread_id),
                ).fetchone()[0]
                if int(present) != 2:
                    return None
                cur = self._conn.execute(
                    "UPDATE messages SET conversation_id = ? WHERE conversation_id = ?",
                    (dst_thread_id, src_thread_id),
                )
                moved = int(cur.rowcount or 0)
                if self._fts_ok:
                    self._conn.execute(
                        "UPDATE messages_fts SET conversation_id = ? WHERE conversation_id = ?",
                        (dst_thread_id, src_thread_id),
                    )
                    self._conn.execute(
                        "DELETE FROM receipts_fts WHERE thread_id = ?", (src_thread_id,)
                    )
                self._conn.execute(
                    """UPDATE conversations
                       SET status = 'merged', merged_into = ?, receipt = '',
                           receipt_updated_at = NULL, paused_at = NULL, updated_at = ?
                       WHERE id = ?""",
                    (dst_thread_id, ts, src_thread_id),
                )
                self._conn.execute(
                    """UPDATE conversations
                       SET status = 'open', paused_at = NULL, stale = 0,
                           turns_since_pause = 0, updated_at = ?
                       WHERE id = ?""",
                    (ts, dst_thread_id),
                )
            return moved
        except Exception as e:
            logger.warning(f"merge_thread {src_thread_id} -> {dst_thread_id} failed: {e}")
            return None

    # ------------------------------------------------------------------
    # session_somatic_blocks (C1 link)
    # ------------------------------------------------------------------

    def add_somatic_block(
        self, session_id: str, block_id: str, block_type: str = "",
        status: str = "", metadata: Optional[Dict] = None,
    ) -> bool:
        if self._conn is None:
            return False
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    """INSERT OR REPLACE INTO session_somatic_blocks
                       (id, session_id, block_id, block_type, status, created_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (f"{session_id}:{block_id}", session_id, block_id, block_type,
                     status, time.time(), json.dumps(metadata or {})),
                )
            return True
        except Exception as e:
            logger.warning(f"add_somatic_block failed: {e}")
            return False

    def list_somatic_blocks(self, session_id: str) -> List[Dict[str, Any]]:
        if self._conn is None:
            return []
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT block_id, block_type, status, created_at, metadata "
                    "FROM session_somatic_blocks WHERE session_id = ? "
                    "ORDER BY created_at ASC", (session_id,),
                ).fetchall()
            return [{
                "block_id": r["block_id"], "block_type": r["block_type"],
                "status": r["status"], "created_at": r["created_at"],
                "metadata": _loads(r["metadata"], {}),
            } for r in rows]
        except Exception as e:
            logger.warning(f"list_somatic_blocks failed: {e}")
            return []

    def remove_somatic_block(self, session_id: str, block_id: str) -> bool:
        if self._conn is None:
            return False
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "DELETE FROM session_somatic_blocks WHERE session_id = ? AND block_id = ?",
                    (session_id, block_id),
                )
            return True
        except Exception as e:
            logger.warning(f"remove_somatic_block failed: {e}")
            return False

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


# ---------------------------------------------------------------------------
# One-time migration: JSON -> SQLite (superseded by agents/migrations.py in A12)
# ---------------------------------------------------------------------------

def migrate_json_conversations_to_sqlite(
    json_store: Any, sqlite_store: SqliteConversationStore
) -> int:
    """Migrate every ``*.json`` conversation from a JSON ``ConversationStore``
    into a ``SqliteConversationStore``. Returns the number migrated.

    Idempotent: a thread that already holds messages is not re-appended.
    (Superseded by ``agents/migrations.py`` in A12, which also closes threads.)
    """
    storage_path = getattr(json_store, "storage_path", None)
    if storage_path is None or not Path(storage_path).exists():
        return 0
    n = 0
    for file_path in Path(storage_path).glob("*.json"):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            conv = Conversation.from_dict(data)
            messages = list(conv.messages)
            conv.messages = []
            existing = sqlite_store.get(conv.conversation_id)
            if existing is not None and existing.messages:
                n += 1  # already migrated
                continue
            if not sqlite_store.save(conv):
                continue
            for m in messages:
                sqlite_store.append_message(
                    conv.conversation_id, m.role, m.content,
                    origin="assistant" if m.role == "assistant" else "human",
                    metadata=m.metadata, timestamp=m.timestamp,
                )
            n += 1
        except Exception as e:
            logger.warning(f"migration skipped {file_path}: {e}")
    logger.info(f"Migrated {n} conversations from JSON to SQLite")
    return n
