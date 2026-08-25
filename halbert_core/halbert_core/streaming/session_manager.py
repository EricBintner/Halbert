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

    def __init__(self, max_sessions: int = 2, idle_ttl_seconds: int = 60):
        self._sessions: Dict[str, PTYSession] = {}
        self._last_activity: Dict[str, float] = {}
        self._max_sessions = max_sessions
        self._idle_ttl = idle_ttl_seconds
        self._reaper_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def spawn(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        cols: int = 80,
        rows: int = 24,
    ) -> str:
        """Spawn a PTY session and return its id.

        Raises ``AtCapacityError`` if the manager is at capacity.
        """
        if len(self._sessions) >= self._max_sessions:
            raise AtCapacityError(
                f"Terminal session manager at capacity ({self._max_sessions})"
            )
        session_id = str(uuid.uuid4())
        session = PTYSession(command, cwd=cwd, env=env, cols=cols, rows=rows)
        await session.spawn()
        self._sessions[session_id] = session
        self._last_activity[session_id] = time.monotonic()
        logger.info(f"Spawned terminal session {session_id}: {command!r}")
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
            })
        return out

    def kill(self, session_id: str) -> bool:
        """Kill and remove a session. Returns True if it existed."""
        session = self._sessions.pop(session_id, None)
        self._last_activity.pop(session_id, None)
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
            last = self._last_activity.get(sid, now)
            idle = now - last
            if not session.is_alive():
                # Dead session: clean up
                logger.debug(f"Reaping dead session {sid}")
                self.kill(sid)
            elif idle > self._idle_ttl:
                logger.info(f"Reaping idle session {sid} (idle {idle:.0f}s > {self._idle_ttl}s)")
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