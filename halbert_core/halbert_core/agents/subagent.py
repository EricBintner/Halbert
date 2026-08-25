"""Subagent handles + manager (D1a).

A subagent is a scoped, reproducible unit of work (e.g. a storage auditor)
that runs in its own PTY/LLM context under a concurrency ceiling. The manager
owns the active set + a FIFO queue, enforces ``max_concurrent``, and emits
lifecycle events (spawned / at_capacity / completed / cancelled) via an
optional ``on_event`` callback — Warp's "ambient agent event" pattern (events,
not function calls) — so the SSE/proactive layer can surface them.

``agent_config_snapshot`` freezes the config onto the handle for
reproducibility. The actual subagent execution (running commands / an LLM)
lives in agents/subagents/ (D1b); the manager just manages slots + queues.

See OPUS-HANDOFF §D1a.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

logger = logging.getLogger("halbert.agents.subagent")

__all__ = ["SubagentHandle", "SubagentManager", "freeze_config"]


@dataclass
class SubagentHandle:
    """A unit of subagent work + its lifecycle state."""
    id: str
    agent_type: str
    task_goal: str
    scoped_sources: List[str] = field(default_factory=list)
    model_tier: Optional[str] = None
    pty_session_id: Optional[str] = None
    status: str = "queued"  # queued | running | completed | failed | cancelled
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result_block_id: Optional[str] = None
    agent_config_snapshot: Dict[str, Any] = field(default_factory=dict)
    parent_task_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "task_goal": self.task_goal,
            "scoped_sources": self.scoped_sources,
            "model_tier": self.model_tier,
            "pty_session_id": self.pty_session_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result_block_id": self.result_block_id,
            "parent_task_id": self.parent_task_id,
            "children": self.children,
            "error": self.error,
        }


def freeze_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Freeze a config dict onto a handle for reproducibility (deep copy)."""
    if not config:
        return {}
    try:
        return copy.deepcopy(config)
    except Exception:
        # Fall back to a shallow copy for non-deepcopyable values
        return dict(config)


class SubagentManager:
    """Manages active subagents + a FIFO queue under a concurrency ceiling."""

    def __init__(
        self,
        pty_manager: Any = None,
        somatic_store: Any = None,
        max_concurrent: int = 2,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self._pty = pty_manager
        self._somatic = somatic_store
        self._max = max_concurrent
        self._active: Dict[str, SubagentHandle] = {}
        self._queue: Deque[SubagentHandle] = deque()
        self._on_event = on_event

    # ------------------------------------------------------------------
    # Event helper
    # ------------------------------------------------------------------

    def _emit(self, event_type: str, handle: SubagentHandle, **extra: Any) -> None:
        event = {
            "type": event_type,
            "handle_id": handle.id,
            "agent_type": handle.agent_type,
            "status": handle.status,
            **extra,
        }
        if self._on_event is not None:
            try:
                self._on_event(event)
            except Exception as e:
                logger.debug(f"subagent on_event callback failed: {e}")
        # Also publish to the proactive channel (best-effort; no-op if no loop)
        try:
            asyncio.get_running_loop().create_task(publish_subagent_event(event))
        except RuntimeError:
            pass
        except Exception as e:
            logger.debug(f"subagent proactive schedule failed: {e}")

    # ------------------------------------------------------------------
    # Spawn / complete / cancel
    # ------------------------------------------------------------------

    def spawn(
        self,
        agent_type: str,
        task_goal: str,
        scoped_sources: Optional[List[str]] = None,
        model_tier: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        agent_config: Optional[Dict[str, Any]] = None,
    ) -> SubagentHandle:
        """Create a handle and admit it if a slot is free; else queue it.

        Non-blocking: a queued handle returns immediately with status
        ``queued`` and an ``at_capacity`` event is emitted.
        """
        handle = SubagentHandle(
            id=str(uuid.uuid4()),
            agent_type=agent_type,
            task_goal=task_goal,
            scoped_sources=list(scoped_sources or []),
            model_tier=model_tier,
            parent_task_id=parent_task_id,
            status="queued",
            agent_config_snapshot=freeze_config(agent_config),
        )

        if len(self._active) < self._max:
            self._admit(handle)
        else:
            self._queue.append(handle)
            self._emit("at_capacity", handle, queued=len(self._queue))
            logger.info(f"Subagent queued (at capacity): {handle.id}")

        return handle

    def _admit(self, handle: SubagentHandle) -> None:
        """Move a handle into the active set as running."""
        handle.status = "running"
        handle.started_at = handle.started_at or time.time()
        self._active[handle.id] = handle
        self._emit("spawned", handle)

    def _promote_next(self) -> Optional[SubagentHandle]:
        """Admit the next queued handle if a slot is free."""
        if len(self._active) >= self._max:
            return None
        if not self._queue:
            return None
        handle = self._queue.popleft()
        self._admit(handle)
        return handle

    def complete(
        self, handle_id: str, result_block_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Mark a running handle complete/failed and promote the next queued."""
        handle = self._active.pop(handle_id, None)
        if handle is None:
            # Maybe it was cancelled from the queue
            return False
        handle.completed_at = time.time()
        if error:
            handle.status = "failed"
            handle.error = error
            self._emit("failed", handle)
        else:
            handle.status = "completed"
            handle.result_block_id = result_block_id
            self._emit("completed", handle, result_block_id=result_block_id)
        self._promote_next()
        return True

    def cancel(self, handle_id: str) -> bool:
        """Cancel a handle (active or queued). Promotes next if a slot frees."""
        # Active?
        handle = self._active.pop(handle_id, None)
        if handle is not None:
            handle.status = "cancelled"
            handle.completed_at = time.time()
            self._emit("cancelled", handle)
            self._promote_next()
            return True
        # Queued?
        for i, h in enumerate(self._queue):
            if h.id == handle_id:
                del self._queue[i]
                h.status = "cancelled"
                self._emit("cancelled", h)
                return True
        return False

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, handle_id: str) -> Optional[SubagentHandle]:
        if handle_id in self._active:
            return self._active[handle_id]
        for h in self._queue:
            if h.id == handle_id:
                return h
        return None

    def list_active(self) -> List[SubagentHandle]:
        return list(self._active.values())

    def list_queued(self) -> List[SubagentHandle]:
        return list(self._queue)

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def queued_count(self) -> int:
        return len(self._queue)


# ---------------------------------------------------------------------------
# Lifecycle event stream (D1c)
# ---------------------------------------------------------------------------

def subagent_event_to_stream(session_id: str, event: Dict[str, Any]) -> "Any":
    """Convert a SubagentManager event dict to a StreamEvent for SSE.

    The manager emits plain dicts via ``on_event``; call this to turn one into
    a ``StreamEvent.subagent_event`` for the SSE channel.
    """
    from .events import StreamEvent
    return StreamEvent.subagent_event(
        session_id=session_id,
        event_type=event.get("type", "state_changed"),
        handle_id=event.get("handle_id", ""),
        agent_type=event.get("agent_type"),
        status=event.get("status"),
    )


async def publish_subagent_event(event: Dict[str, Any]) -> None:
    """Publish a subagent lifecycle event to the ProactiveEventBus (D1c).

    Best-effort: never raises (a missing/bus-less environment just skips).
    """
    try:
        from ..proactive.events import ProactiveEvent, get_event_bus
        event_type = event.get("type", "state_changed")
        agent_type = event.get("agent_type", "subagent")
        pe = ProactiveEvent.create(
            type="subagent_event",
            severity="info" if event_type != "failed" else "warning",
            title=f"Subagent {event_type}: {agent_type}",
            body=f"handle={event.get('handle_id')} status={event.get('status')}",
        )
        await get_event_bus().publish(pe)
    except Exception as e:
        logger.debug(f"subagent proactive publish failed (non-fatal): {e}")