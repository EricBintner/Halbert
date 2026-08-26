# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Terminal event bridge (E1f).

The agent's SSE stream is produced by the state machine, but the process that
actually runs a command lives two layers down in ``tools.executor``. This
module is the seam between them: the executor *publishes* terminal lifecycle
payloads onto a per-agent-session bus, and the state machine *drains* that bus
while the tool runs, converting each payload into a ``StreamEvent`` on the
live SSE stream.

The result is that a command the agent decides to run shows up in the
conversation as a live terminal tile while it is still running, instead of a
block of text after it finished.

Design notes:

* **Zero cost when nobody is listening.** ``publish()`` is a dict lookup and a
  return when the session has no subscriber, so the executor's fast path
  (scripts, tests, CLI) is unchanged.
* **Never blocks the producer.** Queues are bounded; on overflow the oldest
  chunk is dropped. A slow or vanished consumer must never stall a running
  command.
* **The session id travels in a ContextVar.** Tool handlers take only their
  args dict, so threading an extra parameter would break every registered
  tool. ``ToolExecutor.execute()`` sets ``current_agent_session`` around the
  handler call instead; contextvars propagate into the coroutine naturally.
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.streaming.terminal_bridge")

# The agent session whose SSE stream should receive terminal events emitted by
# code running underneath it. None when a tool runs outside an agent turn.
current_agent_session: ContextVar[Optional[str]] = ContextVar(
    "halbert_current_agent_session", default=None
)

# Per-queue cap. A terminal that outruns the consumer drops its oldest chunks
# rather than growing without bound; the tile shows a resynced tail.
_QUEUE_MAXSIZE = 512


class TerminalEventBus:
    """Fan-out of terminal lifecycle payloads, keyed by agent session id."""

    def __init__(self) -> None:
        self._queues: Dict[str, List[asyncio.Queue]] = {}

    # ------------------------------------------------------------------
    # Consumer side (the state machine)
    # ------------------------------------------------------------------

    def subscribe(self, session_id: str) -> asyncio.Queue:
        """Register a consumer for ``session_id`` and return its queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._queues.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        """Remove a consumer. Safe to call twice."""
        queues = self._queues.get(session_id)
        if not queues:
            return
        try:
            queues.remove(queue)
        except ValueError:
            pass
        if not queues:
            self._queues.pop(session_id, None)

    def has_subscribers(self, session_id: Optional[str]) -> bool:
        """True when at least one consumer wants events for this session."""
        return bool(session_id) and bool(self._queues.get(session_id or ""))

    # ------------------------------------------------------------------
    # Producer side (the tool executor)
    # ------------------------------------------------------------------

    def publish(self, session_id: Optional[str], payload: Dict[str, Any]) -> None:
        """Publish a payload to every consumer of ``session_id``.

        Non-blocking and never raises: a full queue drops its oldest item.
        """
        if not session_id:
            return
        queues = self._queues.get(session_id)
        if not queues:
            return
        for queue in queues:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()  # drop oldest
                    queue.put_nowait(payload)
                except Exception:  # pragma: no cover - defensive
                    logger.debug("Dropped terminal payload for %s", session_id)


# Global singleton ----------------------------------------------------------

_bus: Optional[TerminalEventBus] = None


def get_terminal_event_bus() -> TerminalEventBus:
    """Get the process-wide TerminalEventBus (created lazily)."""
    global _bus
    if _bus is None:
        _bus = TerminalEventBus()
    return _bus


def set_terminal_event_bus(bus: Optional[TerminalEventBus]) -> None:
    """Inject/replace the global bus (for tests)."""
    global _bus
    _bus = bus


def publish_terminal_event(payload: Dict[str, Any]) -> None:
    """Publish to whichever agent session the current context belongs to."""
    get_terminal_event_bus().publish(current_agent_session.get(), payload)


def terminal_stream_wanted() -> bool:
    """True when the current context has a consumer for terminal events."""
    return get_terminal_event_bus().has_subscribers(current_agent_session.get())
