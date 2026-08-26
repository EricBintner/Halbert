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
            if name not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    def _ensure_schema(self) -> None:
        try:
            with self._lock:
                cur = self._conn.cursor()
                # PRAGMAs first: they must run outside any transaction.
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=5000")
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
                    else:
                        cur.execute(
                            "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
                            "conversation_id UNINDEXED, content, "
                            "tokenize='porter unicode61')"
                        )
                    cur.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS receipts_fts USING fts5("
                        "thread_id UNINDEXED, title, receipt, "
                        "tokenize='porter unicode61')"
                    )
                    self._fts_ok = True
                except sqlite3.OperationalError as e:
                    logger.warning(f"FTS5 unavailable, falling back to LIKE: {e}")
                    self._fts_ok = False
                if version < SCHEMA_VERSION:
                    cur.execute("DELETE FROM schema_version")
                    cur.execute(
                        "INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,)
                    )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"SqliteConversationStore schema failed: {e}")

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
                         updated_at = excluded.updated_at,
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
        if self._fts_ok and terms:
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
        failed; nothing is left behind on failure.
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
                if self._fts_ok:
                    self._conn.execute(
                        "INSERT INTO messages_fts(rowid, conversation_id, content) "
                        "VALUES (?, ?, ?)",
                        (message_id, thread_id, text),
                    )
                self._conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, thread_id)
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
                cur = self._conn.execute(
                    f"UPDATE messages SET {', '.join(sets)} WHERE id = ?", params
                )
                if cur.rowcount == 0:
                    return False
                if reindex and self._fts_ok:
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
