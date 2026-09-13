# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""ResilientPeerConversationStore — peer store + local cache + write queue.

Multi-node Task 3 (dispatch §3): ``PeerConversationStore`` is a thin HTTP
proxy — when the canonical host is asleep or the LAN is down, every call
fails and the satellite's agent loop stalls. This wrapper keeps the same
public interface as ``SqliteConversationStore``/``PeerConversationStore``
and adds:

* a **write-through local mirror** (a real ``SqliteConversationStore`` at
  a cache path) — every successful peer write is applied locally too, so
  offline reads serve a complete copy of everything this node has
  written, and reads of key surfaces (threads, messages, terminal and
  somatic blocks, open loops, receipts) are mirrored best-effort;
* a **durable staging queue** (``staged_invocation`` in the same DB) —
  writes that hit ``PeerConversationUnavailable`` are applied locally
  and recorded in order for replay;
* an **ordered flush loop** — a daemon thread replays staged calls FIFO
  on reconnect, rewriting locally-minted ids to peer-assigned ones via
  ``local_peer_id_map``.

Ordering and idempotency are the semantics that matter: ``create_thread``
must land before its ``append_message``; an ``update_message`` written
against a locally-minted id must reach the peer as that peer's id; and
``redact_message`` is never staged — a redaction that has not run at the
canonical host has not run, so it surfaces ``PeerConversationUnavailable``
to the caller rather than pretending to be queued work.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from .conversation import Conversation
from .conversation_sqlite import RedactionFailed, SqliteConversationStore
from .peer_conversation_store import (
    PEER_CONVERSATION_METHODS,
    PeerConversationStore,
    PeerConversationUnavailable,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Method classification (dispatch §3.3/§3.4)
# ---------------------------------------------------------------------------

#: Reads — safe to serve from the local mirror when the peer is down.
_READ_METHODS = frozenset({
    "get", "list_conversations", "search",
    "get_thread", "list_threads", "current_open_thread",
    "unresolved_request",
    "list_messages", "recent_messages", "last_turn_id", "pending_notes",
    "list_turns", "search_receipts", "search_snippets",
    "list_somatic_blocks",
    "get_terminal_block", "list_terminal_blocks",
    "get_terminal_session", "list_terminal_sessions",
    "list_open_loops",
})

#: Writes whose first positional argument is a generated integer id.
#: ``redact_message`` also takes one but is never staged nor applied
#: locally — see the module docstring.
_INT_ID_ARG_ENTITY = {
    "update_message": "message",
    "close_open_loop": "open_loop",
}

#: Writes whose RESULT is a server-minted integer id — recorded in
#: ``local_peer_id_map`` so dependent writes can be rewritten on flush.
_INT_ID_RESULT_ENTITY = {
    "append_message": "message",
    "add_open_loop": "open_loop",
}

_FLUSH_INTERVAL_S = 5.0
_FLUSH_MAX_ATTEMPTS = 5
_BACKOFF_BASE_S = 2.0
_BACKOFF_CAP_S = 300.0


class _FlushNotReady(Exception):
    """A staged call references a local id whose peer id is not known yet."""


class ResilientPeerConversationStore:
    """``PeerConversationStore`` + local mirror + durable write queue."""

    def __init__(
        self,
        peer: PeerConversationStore,
        cache_path: str,
        *,
        flush_interval: float = _FLUSH_INTERVAL_S,
        autostart_flush: bool = True,
    ):
        self.peer = peer
        self.local = SqliteConversationStore(cache_path)
        self._flush_interval = flush_interval
        self._flush_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._ensure_staging_tables()
        self._flusher: Optional[threading.Thread] = None
        if autostart_flush:
            self.start_flush_loop()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_staging_tables(self) -> None:
        conn = self.local._conn
        if conn is None:
            return
        with self.local._lock, conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS staged_invocation (
                       id              INTEGER PRIMARY KEY AUTOINCREMENT,
                       enqueued_at     REAL NOT NULL,
                       method          TEXT NOT NULL,
                       args_json       TEXT NOT NULL DEFAULT '[]',
                       kwargs_json     TEXT NOT NULL DEFAULT '{}',
                       local_result_id INTEGER,
                       attempts        INTEGER NOT NULL DEFAULT 0,
                       next_retry_at   REAL NOT NULL DEFAULT 0,
                       last_error      TEXT,
                       dead_lettered_at REAL
                   )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS local_peer_id_map (
                       local_id    INTEGER NOT NULL,
                       entity_type TEXT NOT NULL,
                       peer_id     INTEGER,
                       resolved_at REAL,
                       PRIMARY KEY (local_id, entity_type)
                   )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_local_peer_id_map_peer "
                "ON local_peer_id_map (entity_type, peer_id)"
            )

    def start_flush_loop(self) -> None:
        """Start the daemon flusher (idempotent)."""
        if self._flusher is not None:
            return
        self._flusher = threading.Thread(
            target=self._flush_loop,
            name="peer-conversation-flush",
            daemon=True,
        )
        self._flusher.start()

    def close(self) -> None:
        """Stop the flusher and close the local mirror."""
        self._stop_event.set()
        if self._flusher is not None:
            self._flusher.join(timeout=10)
            self._flusher = None
        try:
            self.local.close()
        except Exception:
            pass
        try:
            self.peer.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Store surface
    # ------------------------------------------------------------------

    @property
    def healthy(self) -> bool:
        return bool(self.peer.healthy)

    @property
    def connected(self) -> bool:
        return bool(self.peer.connected)

    @property
    def db_path(self) -> str:
        return self.local.db_path

    @property
    def peer_url(self) -> str:
        return self.peer.peer_url

    def __getattr__(self, name: str):
        # Dispatch every wire method through the resilience policy. Defined
        # attributes above take precedence; anything outside the allowlist
        # stays a normal AttributeError.
        if name not in PEER_CONVERSATION_METHODS:
            raise AttributeError(name)
        if name in _READ_METHODS:
            def read(*args, **kwargs):
                return self._read(name, *args, **kwargs)
            return read
        if name == "redact_message":
            return self._redact_message
        def write(*args, **kwargs):
            return self._write(name, *args, **kwargs)
        return write

    # ------------------------------------------------------------------
    # Reads — peer first, mirror best-effort, local fallback
    # ------------------------------------------------------------------

    def _read(self, method: str, *args, **kwargs) -> Any:
        try:
            result = getattr(self.peer, method)(*args, **kwargs)
        except PeerConversationUnavailable:
            return getattr(self.local, method)(*args, **kwargs)
        try:
            self._mirror_read(method, args, result)
        except Exception as e:
            # The read succeeded; a mirror failure just leaves the cache
            # stale — log and move on (dispatch §3.3 step 2).
            logger.debug("read mirror %s failed (non-fatal): %s", method, e)
        return result

    def _mirror_read(self, method: str, args, result: Any) -> None:
        if result is None:
            return
        if method == "get":
            self.local.save(result)
        elif method == "list_conversations":
            for conv in result or []:
                if isinstance(conv, Conversation):
                    self.local.save(conv)
                elif isinstance(conv, dict):
                    self.local.save(Conversation.from_dict(conv))
        elif method in ("get_thread", "current_open_thread"):
            self._mirror_thread_dict(result)
        elif method == "list_threads":
            for t in result or []:
                self._mirror_thread_dict(t)
        elif method in ("list_messages", "recent_messages"):
            thread_id = args[0] if args else None
            if thread_id:
                self._mirror_message_dicts(thread_id, result or [])
        elif method in ("get_terminal_block",):
            self._mirror_terminal_block(result)
        elif method == "list_terminal_blocks":
            for b in result or []:
                self._mirror_terminal_block(b)
        elif method in ("get_terminal_session",):
            self._mirror_terminal_session(result)
        elif method == "list_terminal_sessions":
            for s in result or []:
                self._mirror_terminal_session(s)
        elif method == "list_open_loops":
            for loop in result or []:
                self._mirror_open_loop(loop)
        elif method == "list_somatic_blocks":
            session_id = args[0] if args else None
            for b in result or []:
                self.local.add_somatic_block(
                    session_id, b.get("block_id", ""),
                    b.get("block_type", ""), b.get("status", ""),
                    b.get("metadata") or {},
                )
        # Derived/search surfaces (unresolved_request, last_turn_id,
        # pending_notes, list_turns, search*) read mirrored rows — there
        # is nothing to copy for them.

    def _mirror_thread_dict(self, d: Dict[str, Any]) -> None:
        if not isinstance(d, dict):
            return
        tid = d.get("thread_id") or d.get("id")
        if not tid:
            return
        if self.local.get_thread(tid) is None:
            self.local.create_thread(
                tid, d.get("title") or "",
                status=d.get("status") or "open",
                title_source=d.get("title_source") or "provisional",
                created_at=d.get("created_at"),
                parent_thread_id=d.get("parent_thread_id"),
                metadata=d.get("metadata") or {},
            )
        else:
            fields = {
                k: d[k]
                for k in ("title", "status", "title_source", "metadata")
                if k in d
            }
            if fields:
                self.local.update_thread(tid, **fields)

    def _ensure_local_thread(self, thread_id: str) -> None:
        """append_message refuses a thread_id the mirror does not know —
        create the shell row so mirrored messages land."""
        if self.local.get_thread(thread_id) is None:
            self.local.create_thread(thread_id, "", status="open")

    def _mirror_message_dicts(self, thread_id: str, msgs: List[Dict[str, Any]]) -> None:
        for m in msgs:
            if not isinstance(m, dict):
                continue
            peer_id = m.get("message_id")
            if peer_id is not None and self._local_id_for(int(peer_id), "message") is not None:
                continue  # already mirrored (or written through)
            self._ensure_local_thread(thread_id)
            local_id = self.local.append_message(
                thread_id,
                m.get("role", "assistant"),
                m.get("content"),
                origin=m.get("origin") or "human",
                turn_id=m.get("turn_id"),
                session_id=m.get("session_id"),
                status=m.get("status") or "complete",
                blocks=m.get("blocks"),
                terminal_block_ids=m.get("terminal_block_ids"),
                diff_proposals=m.get("diff_proposals"),
                metadata=m.get("metadata"),
                timestamp=m.get("timestamp"),
                visible_in_timeline=bool(m.get("visible_in_timeline", True)),
            )
            if local_id is not None and peer_id is not None:
                self._record_id_map(int(local_id), "message", int(peer_id))

    def _mirror_terminal_block(self, b: Dict[str, Any]) -> None:
        if isinstance(b, dict) and b.get("block_id"):
            self.local.insert_terminal_block(b)

    def _mirror_terminal_session(self, s: Dict[str, Any]) -> None:
        if isinstance(s, dict) and s.get("session_id"):
            self.local.insert_terminal_session(s)

    def _mirror_open_loop(self, loop: Dict[str, Any]) -> None:
        if not isinstance(loop, dict):
            return
        peer_id = loop.get("id")
        if peer_id is None or self._local_id_for(int(peer_id), "open_loop") is not None:
            return
        local_id = self.local.add_open_loop(
            loop.get("thread_id", ""), loop.get("text", ""),
            domain=loop.get("domain"), source=loop.get("source"),
            created_at=loop.get("created_at"),
        )
        if local_id is not None:
            self._record_id_map(int(local_id), "open_loop", int(peer_id))
            if loop.get("closed_at"):
                self.local.close_open_loop(int(local_id), closed_at=loop["closed_at"])

    # ------------------------------------------------------------------
    # Writes — peer first, write-through locally; stage on failure
    # ------------------------------------------------------------------

    def _write(self, method: str, *args, **kwargs) -> Any:
        try:
            result = getattr(self.peer, method)(*args, **kwargs)
        except PeerConversationUnavailable:
            local_result = self._apply_local(method, args, kwargs)
            self._stage(method, args, kwargs, local_result)
            return local_result
        self._mirror_write(method, args, kwargs, result)
        return result

    def _redact_message(self, message_id: int) -> Optional[str]:
        """Never staged: a redaction that has not run at the canonical
        host has not run — surface the outage, don't queue the intent."""
        result = self.peer.redact_message(message_id)  # raises Unavailable
        # Keep the mirror honest: redact the local copy too.
        try:
            local_id = self._local_id_for(message_id, "message")
            if local_id is not None:
                self.local.redact_message(local_id)
        except Exception as e:
            logger.debug("local redact mirror failed (non-fatal): %s", e)
        return result

    def _mirror_write(self, method: str, args, kwargs, peer_result: Any) -> None:
        """Write-through: apply the same call locally so the mirror stays
        a complete copy of this node's writes."""
        try:
            l_args, l_kwargs = self._peer_to_local_ids(method, list(args), dict(kwargs))
            local_result = getattr(self.local, method)(*l_args, **l_kwargs)
            entity = _INT_ID_RESULT_ENTITY.get(method)
            if entity is not None and isinstance(local_result, int) and isinstance(peer_result, int):
                self._record_id_map(local_result, entity, peer_result)
        except Exception as e:
            logger.warning("local mirror of %s failed (non-fatal): %s", method, e)

    def _apply_local(self, method: str, args, kwargs) -> Any:
        l_args, l_kwargs = self._peer_to_local_ids(method, list(args), dict(kwargs))
        return getattr(self.local, method)(*l_args, **l_kwargs)

    def _peer_to_local_ids(self, method: str, args: list, kwargs: dict):
        """Translate a generated id argument from peer space to local.

        ``update_message(peer_id)`` made while online names the peer's id;
        the local mirror tracks it under its own. When the caller passes
        an id the map does not know, it is either already-local (offline-
        minted) or refers to a row the mirror never saw — pass it through
        either way; the local apply is best-effort.
        """
        entity = _INT_ID_ARG_ENTITY.get(method)
        if entity and args and isinstance(args[0], int):
            local_id = self._local_id_for(args[0], entity)
            if local_id is not None:
                args[0] = local_id
        return args, kwargs

    # ------------------------------------------------------------------
    # Staging queue
    # ------------------------------------------------------------------

    def _stage(self, method: str, args, kwargs, local_result: Any) -> None:
        conn = self.local._conn
        if conn is None:
            logger.warning("no cache DB — staged write for %s is lost", method)
            return
        local_result_id = local_result if isinstance(local_result, int) else None
        entity = _INT_ID_RESULT_ENTITY.get(method)
        try:
            with self.local._lock, conn:
                conn.execute(
                    "INSERT INTO staged_invocation "
                    "(enqueued_at, method, args_json, kwargs_json, local_result_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (time.time(), method, json.dumps(list(args)),
                     json.dumps(kwargs), local_result_id),
                )
                if entity is not None and local_result_id is not None:
                    conn.execute(
                        "INSERT OR IGNORE INTO local_peer_id_map "
                        "(local_id, entity_type, peer_id) VALUES (?, ?, NULL)",
                        (local_result_id, entity),
                    )
        except Exception as e:
            logger.warning("staging %s failed — the write stays local only: %s", method, e)

    def _record_id_map(self, local_id: int, entity: str, peer_id: int) -> None:
        conn = self.local._conn
        if conn is None:
            return
        try:
            with self.local._lock, conn:
                conn.execute(
                    "INSERT OR REPLACE INTO local_peer_id_map "
                    "(local_id, entity_type, peer_id, resolved_at) "
                    "VALUES (?, ?, ?, ?)",
                    (local_id, entity, peer_id, time.time()),
                )
        except Exception as e:
            logger.debug("id map write failed (non-fatal): %s", e)

    def _local_id_for(self, peer_id: int, entity: str) -> Optional[int]:
        conn = self.local._conn
        if conn is None:
            return None
        with self.local._lock:
            row = conn.execute(
                "SELECT local_id FROM local_peer_id_map "
                "WHERE entity_type = ? AND peer_id = ?",
                (entity, peer_id),
            ).fetchone()
        return int(row["local_id"]) if row else None

    def _peer_id_for(self, local_id: int, entity: str) -> Optional[int]:
        conn = self.local._conn
        if conn is None:
            return None
        with self.local._lock:
            row = conn.execute(
                "SELECT peer_id FROM local_peer_id_map "
                "WHERE local_id = ? AND entity_type = ?",
                (local_id, entity),
            ).fetchone()
        return (int(row["peer_id"]) if row and row["peer_id"] is not None else None)

    def staged_count(self) -> int:
        conn = self.local._conn
        if conn is None:
            return 0
        with self.local._lock:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM staged_invocation "
                "WHERE dead_lettered_at IS NULL"
            ).fetchone()
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------------
    # Flush
    # ------------------------------------------------------------------

    def _flush_loop(self) -> None:
        while not self._stop_event.wait(self._flush_interval):
            if self.staged_count() == 0:
                continue
            try:
                self.flush_pending()
            except Exception as e:
                logger.warning("flush pass failed: %s", e)

    def flush_pending(self) -> int:
        """Replay staged writes FIFO. Returns the count flushed this pass.

        Synchronous and idempotent — the daemon thread calls it on a
        timer, tests and a reconnect hook call it directly.
        """
        flushed = 0
        with self._flush_lock:
            while True:
                row = self._next_staged()
                if row is None:
                    return flushed
                try:
                    args, kwargs = self._decode_invocation(row)
                    args, kwargs = self._rewrite_local_ids(row["method"], args, kwargs)
                except _FlushNotReady:
                    # The write that mints this id is still queued ahead or
                    # was dead-lettered — retry shortly, then dead-letter
                    # on the same budget as transport failures.
                    if int(row["attempts"]) + 1 >= _FLUSH_MAX_ATTEMPTS:
                        self._dead_letter(row, "peer id never resolved")
                    else:
                        self._retry_with_backoff(row, "peer id not resolved yet")
                    continue
                except Exception as e:
                    self._dead_letter(row, f"undecodable invocation: {e}")
                    continue
                try:
                    result = getattr(self.peer, row["method"])(*args, **kwargs)
                except PeerConversationUnavailable:
                    return flushed  # still down — stop, keep order
                except RedactionFailed:
                    self._dead_letter(row, "RedactionFailed")
                    continue
                except Exception as e:
                    if int(row["attempts"]) + 1 >= _FLUSH_MAX_ATTEMPTS:
                        self._dead_letter(row, f"attempts exhausted: {e}")
                    else:
                        self._retry_with_backoff(row, str(e))
                    continue
                self._capture_peer_ids(row, result)
                self._delete_staged(row["id"])
                flushed += 1

    def _next_staged(self) -> Optional[Dict[str, Any]]:
        conn = self.local._conn
        if conn is None:
            return None
        with self.local._lock:
            row = conn.execute(
                "SELECT * FROM staged_invocation "
                "WHERE dead_lettered_at IS NULL AND next_retry_at <= ? "
                "ORDER BY id LIMIT 1",
                (time.time(),),
            ).fetchone()
        return dict(row) if row else None

    def _decode_invocation(self, row: Dict[str, Any]):
        return json.loads(row["args_json"] or "[]"), json.loads(row["kwargs_json"] or "{}")

    def _rewrite_local_ids(self, method: str, args: list, kwargs: dict):
        """Local-minted ids become their peer ids at replay time."""
        entity = _INT_ID_ARG_ENTITY.get(method)
        if entity and args and isinstance(args[0], int):
            conn = self.local._conn
            mapped = None
            if conn is not None:
                with self.local._lock:
                    r = conn.execute(
                        "SELECT peer_id FROM local_peer_id_map "
                        "WHERE local_id = ? AND entity_type = ?",
                        (args[0], entity),
                    ).fetchone()
                mapped = r  # row presence says "this id was locally minted"
            if mapped is not None:
                if mapped["peer_id"] is None:
                    raise _FlushNotReady
                args[0] = int(mapped["peer_id"])
            # Not in the map: the arg is already a peer id — pass through.
        return args, kwargs

    def _capture_peer_ids(self, row: Dict[str, Any], result: Any) -> None:
        """Record the peer-assigned id for a replayed id-minting write."""
        local_id = row.get("local_result_id")
        entity = _INT_ID_RESULT_ENTITY.get(row["method"])
        if local_id is None or entity is None or not isinstance(result, int):
            return
        conn = self.local._conn
        if conn is None:
            return
        try:
            with self.local._lock, conn:
                conn.execute(
                    "UPDATE local_peer_id_map SET peer_id = ?, resolved_at = ? "
                    "WHERE local_id = ? AND entity_type = ?",
                    (int(result), time.time(), local_id, entity),
                )
        except Exception as e:
            logger.debug("peer id capture failed (non-fatal): %s", e)

    def _delete_staged(self, row_id: int) -> None:
        conn = self.local._conn
        if conn is None:
            return
        with self.local._lock, conn:
            conn.execute("DELETE FROM staged_invocation WHERE id = ?", (row_id,))

    def _retry_with_backoff(self, row: Dict[str, Any], error: str) -> None:
        conn = self.local._conn
        if conn is None:
            return
        attempts = int(row["attempts"]) + 1
        delay = min(_BACKOFF_BASE_S * (2 ** attempts), _BACKOFF_CAP_S)
        with self.local._lock, conn:
            conn.execute(
                "UPDATE staged_invocation SET attempts = ?, next_retry_at = ?, "
                "last_error = ? WHERE id = ?",
                (attempts, time.time() + delay, error[:500], row["id"]),
            )

    def _dead_letter(self, row: Dict[str, Any], reason: str) -> None:
        """Mark a staged call unflushed-able; it stays in the table for
        inspection but out of the FIFO — a poisoned row must not block
        every write behind it forever."""
        logger.warning(
            "dead-lettering staged %s (id=%s): %s", row["method"], row["id"], reason)
        conn = self.local._conn
        if conn is None:
            return
        with self.local._lock, conn:
            conn.execute(
                "UPDATE staged_invocation SET dead_lettered_at = ?, last_error = ? "
                "WHERE id = ?",
                (time.time(), reason[:500], row["id"]),
            )
