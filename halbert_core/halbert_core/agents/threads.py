# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Hidden-thread manager for the one continuous conversation (spec §4–§6).

One ``ThreadManager`` per process owns thread identity: it resolves which
thread a turn belongs to, persists the user row at turn start, appends the
assistant row at turn end, refreshes receipts, and closes paused threads
after the grace window on ``tick()``. Memory side effects (Haloysius line,
LLM summaries) are ``on_thread_closed`` hooks — no-ops in Plan A.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..intake.signals import MessageSignals
from .conversation_sqlite import SqliteConversationStore
from .receipt import build_receipt, provisional_title, refined_title
from .thread_signals import ThreadDecision, build_hint, decide, format_date

logger = logging.getLogger("halbert.agents.threads")

__all__ = ["TurnContext", "ThreadManager", "HISTORY_ROWS"]

HISTORY_ROWS = 12
SOFT_LANDING_ROWS = 6


@dataclass
class TurnContext:
    thread_id: str
    turn_id: str
    user_message_id: Optional[int]
    history: List[Dict[str, Any]]
    hint: str
    recalled: List[Dict[str, Any]]
    decision: ThreadDecision
    session_id: str = ""
    previous_thread_id: Optional[str] = None
    domains: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)


class ThreadManager:
    """Owns thread identity for every turn. Store failures never raise."""

    def __init__(self, store: SqliteConversationStore, *, now: Callable[[], float] = time.time):
        self.store = store
        self._now = now
        self.on_thread_closed: List[Callable[[Dict[str, Any]], None]] = []

    # ------------------------------------------------------------------
    # Turn boundaries
    # ------------------------------------------------------------------

    def current(self) -> Optional[Dict[str, Any]]:
        return self.store.current_open_thread()

    def begin_turn(self, query: str, signals: MessageSignals, session_id: str) -> TurnContext:
        """Resolve the thread, build history + hint, persist the user row (in_progress)."""
        now = self._now()
        open_thread = self.store.current_open_thread()
        previous_id = open_thread["thread_id"] if open_thread else None
        try:
            decision = decide(query, signals, open_thread, self.store, now)
        except Exception as e:
            logger.warning(f"thread decide failed, staying put: {e}")
            decision = ThreadDecision(
                "stay" if open_thread else "open_new", previous_id, False, None, [], []
            )

        history: List[Dict[str, Any]] = []
        if decision.action == "open_new" or open_thread is None:
            thread_id = self._open_new_thread(
                provisional_title(query), "provisional", now,
                from_thread_id=previous_id, reason="auto",
            )
            if previous_id:
                history = self._soft_landing(previous_id)
        elif decision.action == "reopen" and decision.target_thread_id:
            if self.resume_thread(decision.target_thread_id, from_thread_id=previous_id):
                thread_id = decision.target_thread_id
            else:
                thread_id = previous_id
        else:
            thread_id = previous_id
            if decision.stale:
                self.store.update_thread(thread_id, stale=True)

        thread = self.store.get_thread(thread_id) or {
            "thread_id": thread_id, "title": "", "turn_count": 0, "recalled_json": [],
        }

        recalled: List[Dict[str, Any]] = []
        strong = decision.strong
        if strong is not None and strong.status == "closed" and not self._was_retracted(thread, strong.thread_id):
            entry = self._recall_entry(strong.thread_id, strong.match_terms, now)
            if entry is not None:
                recalled.append(entry)
                self._persist_recall(thread, entry)

        if not history:
            history = self._history(thread)
        try:
            hint = build_hint(thread, decision, recalled, [], now=now)
        except Exception as e:
            logger.warning(f"hint builder failed: {e}")
            hint = ""

        turn_id = uuid.uuid4().hex
        user_message_id = self.store.append_message(
            thread_id, "user", query, origin="human", turn_id=turn_id,
            session_id=session_id, status="in_progress", timestamp=now,
        )
        return TurnContext(
            thread_id=thread_id,
            turn_id=turn_id,
            user_message_id=user_message_id,
            history=history,
            hint=hint,
            recalled=recalled,
            decision=decision,
            session_id=session_id,
            previous_thread_id=previous_id if previous_id != thread_id else None,
            domains=list(signals.detected_domains or []),
            entities=sorted(signals.entities or ()),
        )

    def end_turn(
        self,
        turn: TurnContext,
        *,
        assistant_text: str,
        blocks: list,
        terminal_session_ids: List[str],
        diff_proposals: list,
        status: str = "complete",
        thread_id_override: Optional[str] = None,
    ) -> None:
        """Finalise the turn: user row status, assistant row, thread sets, receipt."""
        now = self._now()
        thread_id = thread_id_override or turn.thread_id
        if turn.user_message_id is not None:
            fields: Dict[str, Any] = {"status": status}
            if thread_id != turn.thread_id:
                fields["thread_id"] = thread_id
            self.store.update_message(turn.user_message_id, **fields)
        if assistant_text or blocks or diff_proposals or terminal_session_ids:
            self.store.append_message(
                thread_id, "assistant", assistant_text or "", origin="assistant",
                turn_id=turn.turn_id, session_id=turn.session_id, status=status,
                blocks=list(blocks or []),
                terminal_block_ids=list(terminal_session_ids or []),
                diff_proposals=list(diff_proposals or []),
                timestamp=now,
            )
        thread = self.store.get_thread(thread_id)
        if thread is None:
            return
        domains = sorted(set(thread.get("topic_domains") or []) | set(turn.domains))
        entities = sorted(set(thread.get("entities_json") or []) | set(turn.entities))
        self.store.update_thread(
            thread_id,
            last_active=now, updated_at=now, stale=False,
            topic_domains=domains, entities_json=entities,
            turns_since_pause=int(thread.get("turns_since_pause") or 0) + 1,
        )
        self._refresh_receipt(thread_id)

    def mark_interrupted(self) -> int:
        """Boot: every ``in_progress`` row becomes ``interrupted``."""
        return self.store.mark_in_progress_interrupted()

    # ------------------------------------------------------------------
    # Thread lifecycle
    # ------------------------------------------------------------------

    def resume_thread(self, thread_id: str, *, from_thread_id: Optional[str]) -> bool:
        """Reopen a paused thread and pause ``from_thread_id``."""
        now = self._now()
        target = self.store.get_thread(thread_id)
        if target is None or target.get("status") != "paused":
            return False
        if from_thread_id and from_thread_id != thread_id:
            self._pause_thread(from_thread_id, now, successor=thread_id)
        meta = dict(target.get("metadata") or {})
        meta.pop("successor", None)
        return self.store.update_thread(
            thread_id, status="open", paused_at=None, stale=False,
            turns_since_pause=0, metadata=meta, updated_at=now,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _open_new_thread(self, title: str, title_source: str, now: float, *, from_thread_id: Optional[str], reason: str) -> str:
        new_id = uuid.uuid4().hex
        if from_thread_id:
            self._pause_thread(from_thread_id, now, successor=new_id)
        self.store.create_thread(
            new_id, title, title_source=title_source, created_at=now,
            metadata={"reason": reason, "previous_thread_id": from_thread_id},
        )
        return new_id

    def _pause_thread(self, thread_id: str, now: float, *, successor: str) -> None:
        t = self.store.get_thread(thread_id)
        if t is None or t.get("status") != "open":
            return
        meta = dict(t.get("metadata") or {})
        meta["successor"] = successor
        fields: Dict[str, Any] = {
            "status": "paused", "paused_at": now, "stale": False,
            "metadata": meta, "updated_at": now,
        }
        fields.update(self._refined_title_fields(t))
        self.store.update_thread(thread_id, **fields)
        self._refresh_receipt(thread_id)

    def _refined_title_fields(self, t: Dict[str, Any]) -> Dict[str, Any]:
        if t.get("title_source") != "provisional":
            return {}
        entities = list(t.get("entities_json") or [])
        if not entities:
            return {}
        first_user = next(
            (m["content"] for m in self.store.list_messages(t["thread_id"], limit=4) if m["role"] == "user"),
            t.get("title") or "",
        )
        return {"title": refined_title(entities, first_user), "title_source": "receipt"}

    def _refresh_receipt(self, thread_id: str) -> str:
        t = self.store.get_thread(thread_id)
        if t is None:
            return ""
        receipt = build_receipt(t, self.store.list_messages(thread_id))
        if t.get("ephemeral"):
            return receipt
        self.store.upsert_receipt(thread_id, t.get("title") or "", receipt)
        return receipt

    def _history(self, thread: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = self.store.recent_messages(thread["thread_id"], limit=HISTORY_ROWS)
        history = [{"role": r["role"], "content": r["content"]} for r in rows]
        receipt = thread.get("receipt") or ""
        if receipt and int(thread.get("message_count") or 0) > len(rows):
            history.insert(0, {"role": "system", "content": f"[Earlier in this subject: {receipt}]"})
        return history

    def _soft_landing(self, previous_id: str) -> List[Dict[str, Any]]:
        rows = self.store.recent_messages(previous_id, limit=SOFT_LANDING_ROWS)
        if not rows:
            return []
        prev = self.store.get_thread(previous_id) or {}
        note = (f'[Previous subject "{prev.get("title") or ""}", kept for one turn only; '
                "it is not the current task]")
        return [{"role": "system", "content": note}] + [
            {"role": r["role"], "content": r["content"]} for r in rows
        ]

    @staticmethod
    def _was_retracted(thread: Dict[str, Any], recalled_thread_id: str) -> bool:
        return any(
            e.get("thread_id") == recalled_thread_id and e.get("status") == "retracted"
            for e in (thread.get("recalled_json") or [])
        )

    def _recall_entry(self, thread_id: str, match_terms: List[str], now: float) -> Optional[Dict[str, Any]]:
        t = self.store.get_thread(thread_id)
        if t is None:
            return None
        return {
            "thread_id": thread_id,
            "title": t.get("title") or "",
            "date": format_date(t.get("last_active") or t.get("created_at"), now),
            "last_active": t.get("last_active"),
            "receipt": t.get("receipt") or "",
            "match_terms": list(match_terms),
            "status": "accepted",
            "at": now,
        }

    def _persist_recall(self, thread: Dict[str, Any], entry: Dict[str, Any]) -> None:
        recalled = list(thread.get("recalled_json") or [])
        if any(e.get("thread_id") == entry["thread_id"] and e.get("status") == "accepted" for e in recalled):
            return
        recalled.append({k: entry[k] for k in ("thread_id", "title", "date", "status", "at")})
        thread["recalled_json"] = recalled
        self.store.update_thread(thread["thread_id"], recalled_json=recalled)
