# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Terminal session manager (B1b).

Singleton that owns all live ``PTYSession`` instances, enforces a concurrent
session cap, and reaps idle/dead sessions via a background task. Callers ask
the manager to spawn a command and get back an opaque session id; the manager
tracks last-activity time so the reaper can kill sessions idle past the TTL.

``AtCapacityError`` is a non-blocking signal — callers should queue or retry,
not crash. See OPUS-HANDOFF §B1b.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

_DEFAULT_KIND_CAPS = {"user": 3, "agent-pool": 3, "oneshot": 2}
_DEFAULT_KIND_TTLS = {"user": 1800, "agent-pool": 900, "oneshot": 60}

from .pty import PTYSession

logger = logging.getLogger("halbert.streaming.session_manager")

# Reaper defaults
_REAP_INTERVAL_SECONDS = 10.0


class AtCapacityError(Exception):
    """Raised when the session manager is at its max_sessions cap.

    Non-blocking: callers should queue the request or retry rather than treat
    this as a fatal error.
    """
    pass


class TerminalSessionManager:
    """Manages all active PTY sessions (singleton-style)."""

    def __init__(
        self,
        max_sessions: int = 8,
        idle_ttl_seconds: int = 60,
        kind_caps: Optional[Dict[str, int]] = None,
        kind_ttls: Optional[Dict[str, int]] = None,
    ):
        self._sessions: Dict[str, PTYSession] = {}
        self._last_activity: Dict[str, float] = {}
        self._max_sessions = max_sessions
        self._idle_ttl = idle_ttl_seconds
        self._reaper_task: Optional[asyncio.Task] = None
        # Plan B: per-kind metadata
        self._kinds: Dict[str, str] = {}
        self._watched: Dict[str, bool] = {}
        self._attach_counts: Dict[str, int] = {}
        self._block_open: Dict[str, bool] = {}
        self._parser_states: Dict[str, Dict] = {}  # Plan B: B9 — OSC parser state
        self._kind_caps = kind_caps if kind_caps is not None else dict(_DEFAULT_KIND_CAPS)
        self._kind_ttls = kind_ttls if kind_ttls is not None else dict(_DEFAULT_KIND_TTLS)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def spawn(
        self,
        command: str,
        *,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        cols: int = 80,
        rows: int = 24,
        kind: str = "oneshot",
        watched: bool = True,
        echo: bool = True,
    ) -> str:
        """Spawn a PTY session and return its id.

        Raises ``AtCapacityError`` if the manager is at the total cap or
        the per-kind cap.
        """
        if len(self._sessions) >= self._max_sessions:
            raise AtCapacityError(
                f"Terminal session manager at capacity ({self._max_sessions})"
            )
        # Per-kind cap
        kind_count = sum(1 for k in self._kinds.values() if k == kind)
        kind_cap = self._kind_caps.get(kind, self._max_sessions)
        if kind_count >= kind_cap:
            raise AtCapacityError(
                f"Terminal session kind '{kind}' at capacity ({kind_cap})"
            )
        session_id = str(uuid.uuid4())
        session = PTYSession(command, cwd=cwd, env=env, cols=cols, rows=rows, echo=echo)
        await session.spawn()
        self._sessions[session_id] = session
        self._last_activity[session_id] = time.monotonic()
        self._kinds[session_id] = kind
        self._watched[session_id] = watched
        self._attach_counts[session_id] = 0
        self._block_open[session_id] = False
        logger.info(f"Spawned terminal session {session_id} (kind={kind}): {command!r}")
        return session_id

    def get(self, session_id: str) -> Optional[PTYSession]:
        """Return the PTYSession for ``session_id``, or None."""
        return self._sessions.get(session_id)

    def touch(self, session_id: str) -> None:
        """Mark a session as just-active (resets its idle timer)."""
        if session_id in self._sessions:
            self._last_activity[session_id] = time.monotonic()

    def list_active(self) -> List[Dict[str, Any]]:
        """Snapshot of all sessions for /sessions endpoints."""
        now = time.monotonic()
        out = []
        for sid, session in self._sessions.items():
            out.append({
                "session_id": sid,
                "pid": session.pid,
                "alive": session.is_alive(),
                "exit_code": session.exit_code,
                "idle_seconds": round(now - self._last_activity.get(sid, now), 1),
                "buffer_bytes": len(session.get_buffer()),
                "kind": self._kinds.get(sid, "oneshot"),
                "owner": "user" if self._kinds.get(sid) == "user" else "agent",
                "watched": self._watched.get(sid, True),
                "block_open": self._block_open.get(sid, False),
                "attach_count": self._attach_counts.get(sid, 0),
            })
        return out

    def attach_client(self, session_id: str) -> None:
        """Increment the ws client count (prevents user-shell reaping)."""
        if session_id in self._attach_counts:
            self._attach_counts[session_id] += 1

    def detach_client(self, session_id: str) -> None:
        """Decrement the ws client count (never goes negative)."""
        if session_id in self._attach_counts:
            self._attach_counts[session_id] = max(0, self._attach_counts[session_id] - 1)

    def set_block_open(self, session_id: str, is_open: bool) -> None:
        """Mark a session as having an open block (prevents agent-pool reaping)."""
        if session_id in self._block_open:
            self._block_open[session_id] = is_open

    # ------------------------------------------------------------------
    # Parser state for stage endpoint (Plan B: B9)
    # ------------------------------------------------------------------

    def is_at_prompt(self, session_id: str) -> bool:
        """True when the session's shell is at an empty prompt.

        The OSC parser for user-kind sessions tracks the last boundary.
        A prompt is when: last boundary was A or B, no C open, and no
        bytes typed since B. When no parser state is tracked, returns
        False (conservative — don't stage into an unknown state).
        """
        state = self._parser_states.get(session_id)
        if state is None:
            return False
        return state.get("at_prompt", False)

    def update_parser_state(self, session_id: str, *, at_prompt: bool) -> None:
        """Update the parser state for a session (called by the reader loop)."""
        if session_id in self._sessions:
            self._parser_states[session_id] = {"at_prompt": at_prompt}

    def kill(self, session_id: str) -> bool:
        """Kill and remove a session. Returns True if it existed."""
        session = self._sessions.pop(session_id, None)
        self._last_activity.pop(session_id, None)
        self._kinds.pop(session_id, None)
        self._watched.pop(session_id, None)
        self._attach_counts.pop(session_id, None)
        self._block_open.pop(session_id, None)
        self._parser_states.pop(session_id, None)
        if session is None:
            return False
        try:
            session.kill()
        except Exception as e:
            logger.warning(f"Error killing session {session_id}: {e}")
        logger.info(f"Killed terminal session {session_id}")
        return True

    @property
    def count(self) -> int:
        return len(self._sessions)

    # ------------------------------------------------------------------
    # Idle reaper
    # ------------------------------------------------------------------

    def start_reaper(self) -> None:
        """Start the background idle-session reaper (idempotent)."""
        if self._reaper_task is not None and not self._reaper_task.done():
            return
        self._reaper_task = asyncio.create_task(self._reaper_loop())
        logger.info("Terminal session reaper started")

    def stop_reaper(self) -> None:
        """Stop the reaper (idempotent). Cancels the background task."""
        if self._reaper_task is None:
            return
        self._reaper_task.cancel()
        self._reaper_task = None
        logger.info("Terminal session reaper stopped")

    async def _reaper_loop(self) -> None:
        """Every ``_REAP_INTERVAL_SECONDS``: kill idle/dead sessions."""
        try:
            while True:
                await asyncio.sleep(_REAP_INTERVAL_SECONDS)
                self._reap_once()
        except asyncio.CancelledError:
            return

    def _reap_once(self) -> None:
        now = time.monotonic()
        # Snapshot ids to avoid mutating during iteration
        for sid in list(self._sessions.keys()):
            session = self._sessions.get(sid)
            if session is None:
                continue
            if not session.is_alive():
                # Dead session: clean up regardless of kind
                logger.debug(f"Reaping dead session {sid}")
                self.kill(sid)
                continue
            last = self._last_activity.get(sid, now)
            # Stdout counts as activity too: PTYSession stamps last_output_at
            # on every chunk, so a session streaming output with no stdin
            # (watching a long build) is never reaped mid-stream.
            last = max(last, getattr(session, "last_output_at", 0.0) or 0.0)
            idle = now - last
            kind = self._kinds.get(sid, "oneshot")
            ttl = self._kind_ttls.get(kind, self._idle_ttl)
            # Per-kind reaping rules (Plan B: B5):
            # - user sessions with attached clients are never reaped
            # - agent-pool sessions with open blocks are never reaped
            if kind == "user" and self._attach_counts.get(sid, 0) > 0:
                continue
            if kind == "agent-pool" and self._block_open.get(sid, False):
                continue
            if idle > ttl:
                logger.info(f"Reaping idle session {sid} (kind={kind}, idle {idle:.0f}s > {ttl}s)")
                self.kill(sid)

    async def shutdown(self) -> None:
        """Stop the reaper and kill all sessions (clean shutdown)."""
        self.stop_reaper()
        for sid in list(self._sessions.keys()):
            self.kill(sid)


# Global singleton ----------------------------------------------------------

_manager: Optional[TerminalSessionManager] = None


def get_terminal_manager() -> TerminalSessionManager:
    """Get the global TerminalSessionManager (created lazily)."""
    global _manager
    if _manager is None:
        _manager = TerminalSessionManager()
    return _manager


def set_terminal_manager(manager: Optional[TerminalSessionManager]) -> None:
    """Inject/replace the global manager (for tests)."""
    global _manager
    _manager = manager
