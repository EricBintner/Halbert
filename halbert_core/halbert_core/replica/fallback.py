# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Read-fallback — the mind stays recallable when the canonical is down.

A body with a warm replica can still answer "what do you remember" when
the canonical host is unreachable. Two rules keep the fallback honest:

- **Reads fall back, writes don't.** A stale replica can answer recall;
  it can never accept a write — a memory written to a stale copy is a
  memory the entity loses when the canonical returns and the next push
  overwrites it. Writes raise, the caller sees the canonical is down.

- **The replica is a file, not a service.** Conversation reads open a
  local ``SqliteConversationStore`` on the replica's conversations.db;
  memory reads load the replica's memories.json into a read-only facade.
  Nothing on the satellite pretends to be the canonical.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..agents.peer_conversation_store import (
    PeerConversationUnavailable,
    PeerConversationStore,
)
from .store import ReplicaStore

logger = logging.getLogger('halbert.replica.fallback')

#: PeerConversationStore methods that are safe to serve from a stale
#: replica. Everything else in PEER_CONVERSATION_METHODS is a write and
#: must raise rather than land on a copy the next push will overwrite.
#: ``get_or_open_thread`` is deliberately NOT here — it is a get-or-
#: *create*: answered from the replica it would INSERT into the stale
#: copy, and the next push would overwrite it — exactly the lost-write
#: this file exists to prevent. It raises like every other write.
READ_ONLY_METHODS = frozenset({
    "get", "list_conversations", "search",
    "get_thread", "list_threads", "current_open_thread",
    "list_messages", "recent_messages", "last_turn_id", "pending_notes",
    "list_turns", "search_receipts", "search_snippets",
    "list_somatic_blocks", "get_terminal_block", "list_terminal_blocks",
    "get_terminal_session", "list_terminal_sessions", "list_open_loops",
    "unresolved_request",
})


class FallbackConversationStore:
    """Wraps a PeerConversationStore with read-fallback to the replica.

    Every call tries the peer first. On ``PeerConversationUnavailable``
    a read-only method is answered from the replica's conversations.db
    through a plain ``SqliteConversationStore``; anything else re-raises
    — the caller learns the canonical is down instead of writing to a
    stale copy.
    """

    def __init__(
        self,
        peer_store: PeerConversationStore,
        replica: Optional[ReplicaStore] = None,
    ):
        self._peer = peer_store
        self._replica = replica or ReplicaStore()
        self._replica_sqlite = None

    # ------------------------------------------------------------------
    # Replica access
    # ------------------------------------------------------------------

    def _replica_store(self):
        """A local SqliteConversationStore opened on the replica db."""
        if self._replica_sqlite is None:
            db = self._replica.path() / "conversations.db"
            if not db.is_file():
                raise PeerConversationUnavailable(
                    "canonical down and the replica has no conversations.db")
            from ..agents.conversation_sqlite import SqliteConversationStore
            self._replica_sqlite = SqliteConversationStore(db_path=str(db))
            logger.info("Serving conversation reads from the local replica")
        return self._replica_sqlite

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _invoke(self, method: str, args: list, kwargs: Dict[str, Any]) -> Any:
        try:
            return getattr(self._peer, method)(*args, **kwargs)
        except PeerConversationUnavailable:
            if method not in READ_ONLY_METHODS:
                raise
            logger.debug(
                "canonical down — answering %s from the replica", method)
            return getattr(self._replica_store(), method)(*args, **kwargs)

    def __getattr__(self, name: str):
        """Forward store-shaped calls through _invoke; properties and
        internals are declared above so they never reach here."""
        if name.startswith("_"):
            raise AttributeError(name)

        def bound(*args, **kwargs):
            return self._invoke(name, list(args), kwargs)
        return bound

    # ------------------------------------------------------------------
    # Health — mirrors the peer store's pair
    # ------------------------------------------------------------------

    @property
    def healthy(self) -> bool:
        """True when the peer is healthy OR a replica can still answer."""
        try:
            if self._peer.healthy:
                return True
        except Exception:
            pass
        return self._replica.meta() is not None

    @property
    def connected(self) -> bool:
        try:
            return self._peer.connected
        except Exception:
            return False

    def close(self) -> None:
        if self._replica_sqlite is not None:
            try:
                self._replica_sqlite.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Memory fallback
# ---------------------------------------------------------------------------


class ReplicaReadOnly(Exception):
    """A write was attempted against the read-only replica memory facade."""


class ReplicaMemoryStore:
    """Read-only memory facade over the replica's memories.json.

    Answers the read surface PersonaMemoryStore callers use — ``get``,
    ``search``, ``get_recent``, ``list_memories``, ``get_by_type``,
    ``get_emotional``, ``get_stats`` — by rebuilding ``PersonaMemory``
    objects from the snapshot file. ``search`` is keyword-overlap
    scoring, deliberately: loading the embedder stack to serve a stale
    copy is the wrong trade; degraded recall beats no recall.

    Every write method raises ``ReplicaReadOnly``.
    """

    #: Public PersonaMemoryStore methods that are writes — bound here to
    #: raise, so a caller gets a clean error instead of an AttributeError
    #: or a silently dropped fact.
    _WRITE_METHODS = (
        "smart_add", "teach", "learn_fact", "update_preference",
        "strengthen", "confirm_memory", "correct_memory", "delete",
        "decay_unused", "add_keywords", "auto_extract_keywords",
    )

    def __init__(self, memories_path: Path):
        self._path = Path(memories_path)
        self._memories: List[Any] = []
        self._load()
        for name in self._WRITE_METHODS:
            setattr(self, name, self._read_only(name))

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text())
            from haloysius.memory_v2.types import PersonaMemory
            self._memories = [
                PersonaMemory.from_dict(m)
                for m in data.get("memories", [])
            ]
        except Exception as e:
            logger.warning("Replica memories unreadable: %s", e)
            self._memories = []

    def _read_only(self, name: str):
        def raise_it(*args, **kwargs):
            raise ReplicaReadOnly(
                f"{name}: the replica is read-only — memory writes need "
                f"the canonical host")
        return raise_it

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, memory_id: str) -> Optional[Any]:
        return next((m for m in self._memories if m.id == memory_id), None)

    def list_memories(self, include_deleted: bool = False) -> List[Any]:
        if include_deleted:
            return list(self._memories)
        return [m for m in self._memories
                if not getattr(m, "deleted", False)]

    def get_recent(self, k: int = 10) -> List[Any]:
        return sorted(
            self.list_memories(),
            key=lambda m: getattr(m, "created_at", "") or "",
            reverse=True,
        )[:k]

    def get_by_type(self, memory_type) -> List[Any]:
        return [m for m in self.list_memories()
                if getattr(m, "memory_type", None) == memory_type]

    def get_emotional(self, min_intensity: float = 0.5) -> List[Any]:
        return [m for m in self.list_memories()
                if getattr(m, "emotional_intensity", 0) >= min_intensity]

    def search(self, query: str, k: int = 5, memory_type=None) -> List[Any]:
        """Keyword-overlap recall — degraded on purpose, documented above."""
        terms = {t.lower() for t in query.split() if len(t) > 2}
        if not terms:
            return self.get_recent(k)

        def score(m) -> int:
            text = " ".join(str(getattr(m, f, "") or "")
                            for f in ("content", "summary", "context",
                                      "keywords")).lower()
            return sum(1 for t in terms if t in text)

        pool = self.list_memories()
        if memory_type is not None:
            pool = [m for m in pool
                    if getattr(m, "memory_type", None) == memory_type]
        return sorted(pool, key=score, reverse=True)[:k]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_memories": len(self.list_memories()),
            "replica": True,
            "source": str(self._path),
        }


def probe_canonical_reachable(
    peer_url: str,
    bearer_token: str,
    timeout: float = 3.0,
    http_get=None,
) -> bool:
    """One-shot reachability check — GET the peer's health endpoint.

    Distinct from PeerLivenessProbe: that is the long-lived 3-strike
    monitor the status surfaces read. This is the single question
    ``_create_memory_store`` asks once, at store-construction time,
    before it decides which backend to build.

    ``peer_url`` may be a base URL (``http://host:8000``) or the memory
    path from being.yml (``http://host:8000/api/memory``) — the health
    endpoint lives on the origin, so the path is dropped.
    """
    if http_get is None:
        import requests
        http_get = requests.get
    from urllib.parse import urlsplit
    parts = urlsplit(peer_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    try:
        resp = http_get(
            f"{origin}/api/conversations/health",
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=timeout,
        )
        return resp.status_code == 200
    except Exception:
        return False
