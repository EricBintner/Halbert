# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""PeerConversationStore — the one conversation, served by another body.

In singular entity mode a workstation's ``ThreadManager`` does not own a
local SQLite file: the canonical thread database lives on the HA server, and
every node runs its own ``ThreadManager`` against that one database over the
peer HTTP link (implementation plan P3a,
``.handoff/IMPL-PLAN-SINGULAR-ENTITY-TASKS-2026-08-31.md``). This class is
the workstation-side half: a drop-in stand-in for
``SqliteConversationStore`` whose every public method is one HTTP call.

Wire contract (the P3b server half — ``dashboard/routes/conversations.py`` —
must answer exactly this; ``tests/test_peer_conversation_store.py`` contains
an executable reference implementation backed by the real store):

- ``POST {peer_url}/api/conversations/invoke`` with JSON body
  ``{"method": <name>, "args": [...], "kwargs": {...}}`` and bearer auth.
  The server allowlists ``method`` against ``PEER_CONVERSATION_METHODS``,
  calls the same-named method on its local ``SqliteConversationStore``, and
  answers ``200 {"value": <the method's return value>}`` — including
  ``null``/``false``/``[]``, which are ordinary answers here, not errors.
- ``GET {peer_url}/api/conversations/health`` →
  ``{"healthy": bool, "connected": bool}`` (the store's two properties).
- ``Conversation``-carrying methods — ``get``/``create``/``get_or_create``
  return, and ``save`` accepts, ``Conversation.to_dict()`` at the wire; both
  sides rebuild the dataclass with ``from_dict()``.
- A redaction that did not land is the one failure the store reports by
  raising: the server answers ``500 {"error": {"type": "RedactionFailed",
  "message": ...}}`` and the proxy re-raises ``RedactionFailed`` so the
  privacy promise survives the network hop.
- 401 (bad bearer token) and any other non-200 raise
  ``PeerConversationUnavailable`` locally, as do connection errors and
  timeouts.

Semantics relative to ``SqliteConversationStore``: return values and
failure modes are the store's own (falsy on a failed write, ``None`` on a
missing row), except that *transport* failure — unreachable peer, rejected
token — raises ``PeerConversationUnavailable`` instead of quietly returning
an empty result, because "the peer is down" must stay distinguishable from
"there are no threads". ``ThreadManager`` is written "store failures never
raise"; the P3c wiring that injects this store is where unavailability is
caught and degraded, not here.

No ``mcp_response()`` redaction is applied on either side: this is internal
communication between two bodies of one entity (the same rule the memory
peer link follows), unlike ``peer_tool_proxy.py`` whose responses cross the
entity boundary and are redacted at the peer's egress.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .conversation import Conversation
from .conversation_sqlite import RedactionFailed

logger = logging.getLogger("halbert.agents.peer_conversation_store")

#: Every ``SqliteConversationStore`` public method the peer link may invoke.
#: The server's dispatch endpoint allowlists against this same set, and
#: ``tests/test_peer_conversation_store.py`` pins it in parity with both
#: classes' public interfaces, so the three cannot drift apart silently.
#: ``close`` is deliberately absent: the proxy has no connection to close,
#: so it is a local no-op, never a wire call.
PEER_CONVERSATION_METHODS = frozenset({
    "get", "create", "get_or_create", "save", "delete",
    "list_conversations", "search",
    "append_message", "update_message", "mark_in_progress_interrupted",
    "redact_message",
    "create_thread", "update_thread", "get_thread", "list_threads",
    "current_open_thread",
    "list_messages", "recent_messages", "last_turn_id", "pending_notes",
    "list_turns",
    "upsert_receipt", "search_receipts", "search_snippets",
    "merge_thread",
    "add_somatic_block", "list_somatic_blocks", "remove_somatic_block",
    "insert_terminal_block", "update_terminal_block", "get_terminal_block",
    "list_terminal_blocks",
    "insert_terminal_session", "update_terminal_session",
    "get_terminal_session", "list_terminal_sessions",
    "add_open_loop", "list_open_loops", "close_open_loop",
    "migrate_terminal_block_ids_to_blocks",
})


class PeerConversationUnavailable(Exception):
    """The canonical conversation store is unreachable over the peer link.

    Raised on connection errors, timeouts, a rejected bearer token, or any
    non-200 the peer could not be talked out of. Distinct from the store's
    ordinary falsy "write failed / row missing" answers so a caller can tell
    "the peer is down" (retry, degrade, queue) from "there is no such row".
    """


class PeerConversationStore:
    """HTTP proxy of the HA server's ``SqliteConversationStore``.

    A drop-in store for ``ThreadManager``: same public method names,
    signatures, and return shapes as ``SqliteConversationStore`` — every
    method below mirrors its counterpart there, in declaration order.

    Usage::

        store = PeerConversationStore(
            peer_url="http://ha-server.lan:8000",
            bearer_token="...",
        )
        mgr = ThreadManager(store)
    """

    def __init__(
        self,
        peer_url: str,
        bearer_token: str = "",
        timeout: float = 15.0,
    ):
        """
        Args:
            peer_url: The HA server's base URL (e.g. ``http://ha-server.lan:8000``).
            bearer_token: Peer bearer token (same token family as the compute
                and MCP peer links).
            timeout: Per-request HTTP timeout. Reads of one thread page stay
                well under this; it exists so a wedged server cannot pin the
                cognition tick forever.
        """
        self.peer_url = peer_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    @property
    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def _invoke(self, method: str, args: list, kwargs: Dict[str, Any]) -> Any:
        """One wire call. Returns the server-side method's return value.

        Raises ``RedactionFailed`` when the server reports one (the store's
        one deliberate raise), ``PeerConversationUnavailable`` on transport
        failure or any other non-200.
        """
        if method not in PEER_CONVERSATION_METHODS:
            # Client-side twin of the server's allowlist: a typo'd or
            # unapproved name never leaves this machine.
            raise PeerConversationUnavailable(
                f"method {method!r} is not allowed on the peer conversation link"
            )
        import requests

        url = f"{self.peer_url}/api/conversations/invoke"
        body = {"method": method, "args": args, "kwargs": kwargs}
        try:
            resp = requests.post(url, json=body, headers=self._headers,
                                 timeout=self.timeout)
        except requests.ConnectionError as e:
            raise PeerConversationUnavailable(
                f"Cannot reach peer conversation store at {url}: {e}"
            ) from e
        except requests.Timeout as e:
            raise PeerConversationUnavailable(
                f"Peer conversation store timed out at {url}: {e}"
            ) from e

        if resp.status_code == 401:
            raise PeerConversationUnavailable(
                f"Peer conversation store rejected bearer token (401) at {url}"
            )
        if resp.status_code >= 400:
            payload = {}
            try:
                payload = resp.json()
            except Exception:
                pass
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict) and error.get("type") == "RedactionFailed":
                raise RedactionFailed(error.get("message") or "peer redaction failed")
            raise PeerConversationUnavailable(
                f"Peer conversation store returned {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        try:
            payload = resp.json()
        except Exception as e:
            raise PeerConversationUnavailable(
                f"Peer conversation store returned invalid JSON: {e}"
            ) from e
        return payload.get("value")

    def _health(self) -> Dict[str, bool]:
        """The peer's ``healthy``/``connected`` flags, all-False when down."""
        import requests

        url = f"{self.peer_url}/api/conversations/health"
        try:
            resp = requests.get(url, headers=self._headers, timeout=self.timeout)
            if resp.status_code != 200:
                return {"healthy": False, "connected": False}
            flags = resp.json()
            return {"healthy": bool(flags.get("healthy")),
                    "connected": bool(flags.get("connected"))}
        except Exception as e:
            logger.warning(f"peer conversation health probe failed: {e}")
            return {"healthy": False, "connected": False}

    def _conversation(self, value: Any) -> Optional[Conversation]:
        return Conversation.from_dict(value) if value is not None else None

    # ------------------------------------------------------------------
    # Health (SqliteConversationStore property parity)
    # ------------------------------------------------------------------

    @property
    def healthy(self) -> bool:
        """The peer store's own ``healthy`` flag; False when unreachable."""
        return self._health()["healthy"]

    @property
    def connected(self) -> bool:
        """The peer store's own ``connected`` flag; False when unreachable."""
        return self._health()["connected"]

    # ------------------------------------------------------------------
    # Legacy CRUD (Conversation dataclass shape)
    # ------------------------------------------------------------------

    def get(self, conversation_id: str) -> Optional[Conversation]:
        return self._conversation(self._invoke("get", [conversation_id], {}))

    def create(self, conversation_id: str, user_id: Optional[str] = None) -> Conversation:
        return self._conversation(self._invoke(
            "create", [conversation_id], {"user_id": user_id}))

    def get_or_create(self, conversation_id: str, user_id: Optional[str] = None) -> Conversation:
        return self._conversation(self._invoke(
            "get_or_create", [conversation_id], {"user_id": user_id}))

    def save(self, conversation: Conversation) -> bool:
        # The wire carries Conversation.to_dict(); the server rebuilds it.
        return self._invoke("save", [conversation.to_dict()], {})

    def delete(self, conversation_id: str) -> bool:
        return self._invoke("delete", [conversation_id], {})

    def list_conversations(
        self, user_id: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        return self._invoke("list_conversations", [],
                            {"user_id": user_id, "limit": limit, "offset": offset})

    def search(
        self, query: str, user_id: Optional[str] = None, limit: int = 20
    ) -> List[str]:
        return self._invoke("search", [query],
                            {"user_id": user_id, "limit": limit})

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
        return self._invoke("append_message", [thread_id, role, content], {
            "origin": origin, "turn_id": turn_id, "session_id": session_id,
            "status": status, "blocks": blocks,
            "terminal_block_ids": terminal_block_ids,
            "diff_proposals": diff_proposals, "metadata": metadata,
            "timestamp": timestamp,
            "visible_in_timeline": visible_in_timeline,
        })

    def update_message(self, message_id: int, **fields: Any) -> bool:
        return self._invoke("update_message", [message_id], dict(fields))

    def mark_in_progress_interrupted(self) -> int:
        return self._invoke("mark_in_progress_interrupted", [], {})

    # ------------------------------------------------------------------
    # Forget / redact
    # ------------------------------------------------------------------

    REDACTED = "[redacted by admin]"

    def redact_message(self, message_id: int) -> Optional[str]:
        """Raises ``RedactionFailed`` through the wire when the peer's
        redaction did not land — the store's one deliberate raise, preserved
        end to end so a failed privacy action is never mistaken for a 404."""
        return self._invoke("redact_message", [message_id], {})

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
        return self._invoke("create_thread", [thread_id, title], {
            "status": status, "title_source": title_source,
            "created_at": created_at, "parent_thread_id": parent_thread_id,
            "metadata": metadata,
        })

    def update_thread(self, thread_id: str, **fields: Any) -> bool:
        return self._invoke("update_thread", [thread_id], dict(fields))

    def get_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        return self._invoke("get_thread", [thread_id], {})

    def list_threads(
        self, status: Optional[Any] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        return self._invoke("list_threads", [status], {"limit": limit})

    def current_open_thread(self) -> Optional[Dict[str, Any]]:
        return self._invoke("current_open_thread", [], {})

    # ------------------------------------------------------------------
    # Message readers
    # ------------------------------------------------------------------

    def list_messages(self, thread_id: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        return self._invoke("list_messages", [thread_id], {"limit": limit})

    def recent_messages(self, thread_id: str, limit: int = 12) -> List[Dict[str, Any]]:
        return self._invoke("recent_messages", [thread_id], {"limit": limit})

    def last_turn_id(self, thread_id: str) -> Optional[str]:
        return self._invoke("last_turn_id", [thread_id], {})

    def pending_notes(self, thread_id: str, *, limit: int = 8) -> List[str]:
        return self._invoke("pending_notes", [thread_id], {"limit": limit})

    def list_turns(
        self,
        *,
        before_turn_id: Optional[str] = None,
        around_turn_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return self._invoke("list_turns", [], {
            "before_turn_id": before_turn_id,
            "around_turn_id": around_turn_id, "limit": limit,
        })

    # ------------------------------------------------------------------
    # Receipts
    # ------------------------------------------------------------------

    def upsert_receipt(self, thread_id: str, title: str, receipt: str) -> bool:
        return self._invoke("upsert_receipt", [thread_id, title, receipt], {})

    def search_receipts(
        self, query: str, *, exclude_thread_id: Optional[str] = None,
        limit: int = 5, domains: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        return self._invoke("search_receipts", [query], {
            "exclude_thread_id": exclude_thread_id, "limit": limit,
            "domains": domains,
        })

    def search_snippets(self, thread_id: str, query: str, limit: int = 5) -> List[str]:
        return self._invoke("search_snippets", [thread_id, query], {"limit": limit})

    # ------------------------------------------------------------------
    # Merge-back
    # ------------------------------------------------------------------

    def merge_thread(
        self, src_thread_id: str, dst_thread_id: str, *, now: Optional[float] = None
    ) -> Optional[int]:
        return self._invoke("merge_thread", [src_thread_id, dst_thread_id],
                            {"now": now})

    # ------------------------------------------------------------------
    # session_somatic_blocks
    # ------------------------------------------------------------------

    def add_somatic_block(
        self, session_id: str, block_id: str, block_type: str = "",
        status: str = "", metadata: Optional[Dict] = None,
    ) -> bool:
        return self._invoke("add_somatic_block",
                            [session_id, block_id, block_type, status],
                            {"metadata": metadata})

    def list_somatic_blocks(self, session_id: str) -> List[Dict[str, Any]]:
        return self._invoke("list_somatic_blocks", [session_id], {})

    def remove_somatic_block(self, session_id: str, block_id: str) -> bool:
        return self._invoke("remove_somatic_block", [session_id, block_id], {})

    # ------------------------------------------------------------------
    # terminal_blocks
    # ------------------------------------------------------------------

    def insert_terminal_block(self, block: Dict[str, Any]) -> bool:
        return self._invoke("insert_terminal_block", [block], {})

    def update_terminal_block(self, block_id: str, **fields: Any) -> bool:
        return self._invoke("update_terminal_block", [block_id], dict(fields))

    def get_terminal_block(self, block_id: str) -> Optional[Dict[str, Any]]:
        return self._invoke("get_terminal_block", [block_id], {})

    def list_terminal_blocks(
        self,
        *,
        session_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return self._invoke("list_terminal_blocks", [], {
            "session_id": session_id, "thread_id": thread_id,
            "turn_id": turn_id, "limit": limit,
        })

    # ------------------------------------------------------------------
    # terminal_sessions
    # ------------------------------------------------------------------

    def insert_terminal_session(self, session: Dict[str, Any]) -> bool:
        return self._invoke("insert_terminal_session", [session], {})

    def update_terminal_session(self, session_id: str, **fields: Any) -> bool:
        return self._invoke("update_terminal_session", [session_id], dict(fields))

    def get_terminal_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._invoke("get_terminal_session", [session_id], {})

    def list_terminal_sessions(
        self,
        *,
        kind: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return self._invoke("list_terminal_sessions", [],
                            {"kind": kind, "limit": limit})

    # ------------------------------------------------------------------
    # open_loops
    # ------------------------------------------------------------------

    def add_open_loop(
        self,
        thread_id: str,
        text: str,
        *,
        domain: Optional[str] = None,
        source: Optional[str] = None,
        created_at: Optional[float] = None,
    ) -> Optional[int]:
        return self._invoke("add_open_loop", [thread_id, text], {
            "domain": domain, "source": source, "created_at": created_at,
        })

    def list_open_loops(
        self,
        thread_id: str,
        *,
        open_only: bool = True,
    ) -> List[Dict[str, Any]]:
        return self._invoke("list_open_loops", [thread_id],
                            {"open_only": open_only})

    def close_open_loop(self, loop_id: int, *, closed_at: Optional[float] = None) -> bool:
        return self._invoke("close_open_loop", [loop_id], {"closed_at": closed_at})

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def migrate_terminal_block_ids_to_blocks(self) -> int:
        return self._invoke("migrate_terminal_block_ids_to_blocks", [], {})

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """No-op: there is no local connection to close. Exists so callers
        written against ``SqliteConversationStore.close()`` keep working."""