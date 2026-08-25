"""SomaticStore — SQLite persistence for SomaticBlocks (C1a).

Best-effort, thread-safe (single connection + write lock), mirroring the
OutcomeStore pattern. CRUD: create / get / update_status / list_for_session /
list_by_type. The block's ``metadata`` dict is JSON-encoded in a TEXT column.

The store does NOT own the Finding/Proposal/ApprovalRequest models — those
stay in findings/ and approval/. SomaticBlock rows only hold their ids.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .block import BlockStatus, BlockType, SomaticBlock

logger = logging.getLogger("halbert.somatic.store")

_DEFAULT_DB = str(Path.home() / ".halbert" / "somatic_blocks.db")


class SomaticStore:
    """SQLite-backed store for SomaticBlocks (best-effort, never raises)."""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        try:
            if self._db_path != ":memory:":
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                self._db_path, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._ensure_schema()
        except Exception as e:
            logger.debug(f"SomaticStore init failed (non-fatal): {e}")
            self._conn = None

    def _ensure_schema(self) -> None:
        try:
            with self._lock:
                cur = self._conn.cursor()
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS somatic_blocks (
                        id                  TEXT PRIMARY KEY,
                        block_type          TEXT NOT NULL,
                        status              TEXT NOT NULL,
                        session_id          TEXT NOT NULL,
                        finding_id          TEXT,
                        proposal_id         TEXT,
                        approval_request_id TEXT,
                        action_id           TEXT,
                        reflection_id       TEXT,
                        created_at          REAL NOT NULL,
                        updated_at          REAL NOT NULL,
                        metadata            TEXT NOT NULL DEFAULT '{}'
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_somatic_session "
                    "ON somatic_blocks(session_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_somatic_type "
                    "ON somatic_blocks(block_type)"
                )
                self._conn.commit()
        except Exception as e:
            logger.debug(f"SomaticStore schema failed (non-fatal): {e}")

    # ------------------------------------------------------------------
    # Row <-> SomaticBlock
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_block(row: sqlite3.Row) -> SomaticBlock:
        meta = {}
        try:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
        except (json.JSONDecodeError, TypeError):
            meta = {}
        return SomaticBlock(
            id=row["id"],
            block_type=BlockType(row["block_type"]),
            status=BlockStatus(row["status"]),
            session_id=row["session_id"],
            finding_id=row["finding_id"],
            proposal_id=row["proposal_id"],
            approval_request_id=row["approval_request_id"],
            action_id=row["action_id"],
            reflection_id=row["reflection_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=meta,
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, block: SomaticBlock) -> bool:
        """Insert a new block. Returns False if it already exists / on error."""
        if self._conn is None:
            return False
        try:
            with self._lock:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO somatic_blocks
                        (id, block_type, status, session_id, finding_id,
                         proposal_id, approval_request_id, action_id,
                         reflection_id, created_at, updated_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        block.id, block.block_type.value, block.status.value,
                        block.session_id, block.finding_id, block.proposal_id,
                        block.approval_request_id, block.action_id,
                        block.reflection_id, block.created_at, block.updated_at,
                        json.dumps(block.metadata or {}),
                    ),
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.debug(f"SomaticStore create failed (non-fatal): {e}")
            return False

    def get(self, block_id: str) -> Optional[SomaticBlock]:
        if self._conn is None:
            return None
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT * FROM somatic_blocks WHERE id = ?", (block_id,)
                )
                row = cur.fetchone()
            return self._row_to_block(row) if row else None
        except Exception as e:
            logger.debug(f"SomaticStore get failed (non-fatal): {e}")
            return None

    def save(self, block: SomaticBlock) -> bool:
        """Upsert a full block (INSERT OR REPLACE), including metadata.

        Use this when the in-memory block's metadata has changed; use
        ``update_status`` for a lighter status/link-id-only update.
        """
        if self._conn is None:
            return False
        try:
            with self._lock:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO somatic_blocks
                        (id, block_type, status, session_id, finding_id,
                         proposal_id, approval_request_id, action_id,
                         reflection_id, created_at, updated_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        block.id, block.block_type.value, block.status.value,
                        block.session_id, block.finding_id, block.proposal_id,
                        block.approval_request_id, block.action_id,
                        block.reflection_id, block.created_at, block.updated_at,
                        json.dumps(block.metadata or {}),
                    ),
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.debug(f"SomaticStore save failed (non-fatal): {e}")
            return False

    def update_status(
        self, block_id: str, status: BlockStatus, **link_ids: Optional[str]
    ) -> bool:
        """Update a block's status and optionally set linked ids.

        ``link_ids`` may include finding_id / proposal_id /
        approval_request_id / action_id / reflection_id. Only non-None values
        are written. ``updated_at`` is refreshed.
        """
        if self._conn is None:
            return False
        allowed = {
            "finding_id", "proposal_id", "approval_request_id",
            "action_id", "reflection_id",
        }
        sets = ["status = ?", "updated_at = ?"]
        params: List[Any] = [status.value, time.time()]
        for key, value in link_ids.items():
            if key in allowed and value is not None:
                sets.append(f"{key} = ?")
                params.append(value)
        params.append(block_id)
        try:
            with self._lock:
                self._conn.execute(
                    f"UPDATE somatic_blocks SET {', '.join(sets)} WHERE id = ?",
                    tuple(params),
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.debug(f"SomaticStore update_status failed (non-fatal): {e}")
            return False

    def list_for_session(self, session_id: str) -> List[SomaticBlock]:
        if self._conn is None:
            return []
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT * FROM somatic_blocks WHERE session_id = ? "
                    "ORDER BY created_at ASC",
                    (session_id,),
                )
                rows = cur.fetchall()
            return [self._row_to_block(r) for r in rows]
        except Exception as e:
            logger.debug(f"SomaticStore list_for_session failed: {e}")
            return []

    def list_by_type(self, block_type: BlockType) -> List[SomaticBlock]:
        if self._conn is None:
            return []
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT * FROM somatic_blocks WHERE block_type = ? "
                    "ORDER BY created_at ASC",
                    (block_type.value,),
                )
                rows = cur.fetchall()
            return [self._row_to_block(r) for r in rows]
        except Exception as e:
            logger.debug(f"SomaticStore list_by_type failed: {e}")
            return []

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


# Global singleton ----------------------------------------------------------

_store: Optional[SomaticStore] = None
_store_lock = threading.Lock()


def get_somatic_store() -> SomaticStore:
    """Get the global SomaticStore (created lazily)."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = SomaticStore()
    return _store


def set_somatic_store(store: Optional[SomaticStore]) -> None:
    """Inject/replace the global store (for tests)."""
    global _store
    _store = store