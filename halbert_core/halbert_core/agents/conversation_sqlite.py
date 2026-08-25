"""SQLite + FTS5 conversation store (F1).

A drop-in alternative to the JSON-backed ``ConversationStore`` with the same
public API (get/create/get_or_create/save/delete/list_conversations/search),
backed by SQLite. ``search`` uses an FTS5 full-text index over message
content + a LIKE fallback over titles, so it is O(log n) instead of the JSON
store's linear scan over files.

Also provides a ``session_somatic_blocks`` table linking sessions to somatic
blocks (C1), with add/list/remove helpers.

``migrate_json_conversations_to_sqlite`` is the one-time migration that
loads every ``*.json`` conversation from a ``ConversationStore`` and saves it
into a ``SqliteConversationStore``.

The JSON ``ConversationStore`` is kept intact as a fallback; the dashboard can
adopt the SQLite store when ready. See OPUS-HANDOFF §F1.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .conversation import Conversation, Message

logger = logging.getLogger("halbert.agents.conversation_sqlite")

_DEFAULT_DB = str(Path.home() / ".halbert" / "conversations.db")


class SqliteConversationStore:
    """SQLite-backed conversation store with FTS5 search (F1).

    Same API as ``ConversationStore``. Thread-safe (single connection +
    write lock). Best-effort: methods log and degrade rather than raise on
    DB errors, matching the JSON store's leniency.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._fts_ok = False
        try:
            if self._db_path != ":memory:":
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                self._db_path, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._ensure_schema()
        except Exception as e:
            logger.debug(f"SqliteConversationStore init failed (non-fatal): {e}")
            self._conn = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        try:
            with self._lock:
                cur = self._conn.cursor()
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
                # FTS5 full-text index over message content. Standalone table
                # (conversation_id unindexed) so save() can bulk-replace rows.
                try:
                    cur.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts "
                        "USING fts5(conversation_id UNINDEXED, content)"
                    )
                    self._fts_ok = True
                except sqlite3.OperationalError as e:
                    logger.debug(f"FTS5 unavailable, falling back to LIKE: {e}")
                    self._fts_ok = False
                self._conn.commit()
        except Exception as e:
            logger.debug(f"SqliteConversationStore schema failed: {e}")

    # ------------------------------------------------------------------
    # CRUD (same API as ConversationStore)
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
            logger.debug(f"sqlite get failed: {e}")
            return None
        conv = Conversation(
            conversation_id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata"] or "{}"),
        )
        conv.messages = [
            Message(
                role=m["role"],
                content=m["content"],
                timestamp=m["timestamp"],
                metadata=json.loads(m["metadata"] or "{}"),
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

    def save(self, conversation: Conversation) -> None:
        """Upsert a conversation and replace its messages + FTS rows."""
        if self._conn is None:
            return
        cid = conversation.conversation_id
        meta = json.dumps(conversation.metadata or {})
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT OR REPLACE INTO conversations
                       (id, user_id, title, created_at, updated_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (cid, conversation.user_id, conversation.title,
                     conversation.created_at, conversation.updated_at, meta),
                )
                # Replace messages
                self._conn.execute(
                    "DELETE FROM messages WHERE conversation_id = ?", (cid,)
                )
                for m in conversation.messages:
                    self._conn.execute(
                        """INSERT INTO messages
                           (conversation_id, role, content, timestamp, metadata)
                           VALUES (?, ?, ?, ?, ?)""",
                        (cid, m.role, m.content, m.timestamp,
                         json.dumps(m.metadata or {})),
                    )
                # Replace FTS rows
                if self._fts_ok:
                    self._conn.execute(
                        "DELETE FROM messages_fts WHERE conversation_id = ?", (cid,)
                    )
                    for m in conversation.messages:
                        self._conn.execute(
                            "INSERT INTO messages_fts(conversation_id, content) "
                            "VALUES (?, ?)",
                            (cid, m.content),
                        )
                self._conn.commit()
        except Exception as e:
            logger.debug(f"sqlite save failed: {e}")

    def delete(self, conversation_id: str) -> bool:
        if self._conn is None:
            return False
        try:
            with self._lock:
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
                self._conn.commit()
            return True
        except Exception as e:
            logger.debug(f"sqlite delete failed: {e}")
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
            logger.debug(f"sqlite list_conversations failed: {e}")
            return []

    def search(
        self, query: str, user_id: Optional[str] = None, limit: int = 20
    ) -> List[str]:
        """Full-text search over message content (+ title LIKE). Returns conversation ids."""
        if self._conn is None or not query:
            return []
        results: List[str] = []
        try:
            with self._lock:
                if self._fts_ok:
                    # FTS5 MATCH on message content
                    rows = self._conn.execute(
                        """SELECT DISTINCT m.conversation_id
                           FROM messages_fts m
                           JOIN conversations c ON c.id = m.conversation_id
                           WHERE messages_fts MATCH ? AND (? IS NULL OR c.user_id = ?)
                           LIMIT ?""",
                        (query, user_id, user_id, limit),
                    ).fetchall()
                    results = [r[0] for r in rows]
                # Always also LIKE-match titles (cheap, catches FTS misses)
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
            logger.debug(f"sqlite search failed: {e}")
        return results[:limit]

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
            with self._lock:
                self._conn.execute(
                    """INSERT OR REPLACE INTO session_somatic_blocks
                       (id, session_id, block_id, block_type, status, created_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (f"{session_id}:{block_id}", session_id, block_id, block_type,
                     status, time.time(), json.dumps(metadata or {})),
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.debug(f"add_somatic_block failed: {e}")
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
            out = []
            for r in rows:
                try:
                    meta = json.loads(r["metadata"] or "{}")
                except Exception:
                    meta = {}
                out.append({
                    "block_id": r["block_id"], "block_type": r["block_type"],
                    "status": r["status"], "created_at": r["created_at"],
                    "metadata": meta,
                })
            return out
        except Exception as e:
            logger.debug(f"list_somatic_blocks failed: {e}")
            return []

    def remove_somatic_block(self, session_id: str, block_id: str) -> bool:
        if self._conn is None:
            return False
        try:
            with self._lock:
                self._conn.execute(
                    "DELETE FROM session_somatic_blocks WHERE session_id = ? AND block_id = ?",
                    (session_id, block_id),
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.debug(f"remove_somatic_block failed: {e}")
            return False

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


# ---------------------------------------------------------------------------
# One-time migration: JSON -> SQLite
# ---------------------------------------------------------------------------

def migrate_json_conversations_to_sqlite(
    json_store: Any, sqlite_store: SqliteConversationStore
) -> int:
    """Migrate every ``*.json`` conversation from a JSON ``ConversationStore``
    into a ``SqliteConversationStore``. Returns the number migrated.

    Idempotent: re-saving a conversation that already exists overwrites it.
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
            sqlite_store.save(conv)
            n += 1
        except Exception as e:
            logger.warning(f"migration skipped {file_path}: {e}")
    logger.info(f"Migrated {n} conversations from JSON to SQLite")
    return n