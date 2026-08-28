# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Agent terminal pool — PTY-backed bash sessions for agent run_command.

The pool owns 'agent-pool' kind sessions in the TerminalSessionManager.
executor._run_command asks the pool for a session that is not busy
(no open block) and not interactive; spawns one up to the cap; falls
back to the subprocess path at cap or when the session is interactive.

See plan-b-contracts.md section 6.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Dict, Optional, Tuple

from .pty import PTYSession
from .session_manager import TerminalSessionManager, AtCapacityError
from .shell_integration import OSCParser, BlockBoundary
from .redact import redact

logger = logging.getLogger("halbert.streaming.agent_pool")

_POOL_SHELL = "bash --norc --noprofile"


class TerminalPool:
    """Pool of PTY-backed bash sessions for agent run_command."""

    def __init__(self, manager: TerminalSessionManager, *, cap: int = 3):
        self._manager = manager
        self._cap = cap
        self._sessions: Dict[str, PTYSession] = {}

    async def acquire(self) -> Optional[Tuple[str, PTYSession]]:
        """Return an idle, non-interactive pool session, or spawn one.

        Returns None when at cap and all sessions are busy/interactive
        (caller falls back to subprocess).
        """
        # Look for an existing idle session
        for sid, session in self._sessions.items():
            if not self._manager._block_open.get(sid, False) and session.is_alive():
                self._manager.set_block_open(sid, True)
                return (sid, session)

        # Try to spawn a new one
        if len(self._sessions) >= self._cap:
            return None

        try:
            sid = await self._manager.spawn(
                _POOL_SHELL,
                kind="agent-pool",
                watched=False,
            )
        except AtCapacityError:
            return None

        session = self._manager.get(sid)
        if session is None:
            return None

        self._sessions[sid] = session
        self._manager.set_block_open(sid, True)
        return (sid, session)

    async def run_block(
        self,
        command: str,
        *,
        cwd: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Optional[Dict]:
        """Run a single command as a block in a pool session.

        Returns a dict with block_id, session_id, exit_code, output_head,
        output_tail, duration. Returns None if no session could be acquired.
        """
        acquired = await self.acquire()
        if acquired is None:
            return None
        sid, session = acquired
        block_id = str(uuid.uuid4())
        started_at = time.monotonic()

        # Build the block command with OSC 133 markers.
        # The command runs in a subshell so `exit` doesn't kill the pool shell.
        cwd_prefix = f"cd {cwd} && " if cwd else ""
        block_cmd = (
            f"printf '\\x1b]133;C;id={block_id}\\x07';"
            f"({cwd_prefix}{command});"
            f"printf '\\x1b]133;D;%d;id={block_id}\\x07' \"$?\"\n"
        )

        # Attach a fanout queue to read output
        q = await session.attach()
        # Skip the replay item
        replay = await asyncio.wait_for(q.get(), timeout=5.0)

        # Set up OSC parser to detect block boundaries
        parser = OSCParser()
        block_output = bytearray()
        exit_code: Optional[int] = None
        block_closed = False

        # Write the command
        await session.write_stdin(block_cmd)

        try:
            async def wait_for_block():
                nonlocal exit_code, block_closed
                while not block_closed:
                    try:
                        item = await asyncio.wait_for(q.get(), timeout=timeout)
                    except asyncio.TimeoutError:
                        break
                    if item is None:
                        break
                    if isinstance(item, tuple):
                        continue  # replay
                    out = parser.feed(item)
                    block_output.extend(out.block_bytes)
                    for b in out.boundaries:
                        if b.kind == "D" and b.block_id == block_id:
                            exit_code = b.exit_code
                            block_closed = True
                            break

            await asyncio.wait_for(wait_for_block(), timeout=timeout + 2.0)
        except asyncio.TimeoutError:
            # Command timed out — send Ctrl-C
            try:
                await session.write_stdin("\x03")
                # Grace-wait 2s for D marker
                try:
                    async def grace_wait():
                        nonlocal exit_code, block_closed
                        deadline = time.monotonic() + 2.0
                        while not block_closed and time.monotonic() < deadline:
                            try:
                                item = await asyncio.wait_for(q.get(), timeout=deadline - time.monotonic())
                            except asyncio.TimeoutError:
                                break
                            if item is None:
                                break
                            if isinstance(item, tuple):
                                continue
                            out = parser.feed(item)
                            block_output.extend(out.block_bytes)
                            for b in out.boundaries:
                                if b.kind == "D" and b.block_id == block_id:
                                    exit_code = b.exit_code
                                    block_closed = True
                                    break
                    await grace_wait()
                except Exception:
                    pass
            except Exception:
                pass
            if not block_closed:
                # Kill and evict
                self._manager.kill(sid)
                self._evict(sid)
                exit_code = -1
        finally:
            session.detach(q)

        duration = time.monotonic() - started_at

        # Build output head (first 20 lines) and tail (last 4 KiB)
        output_bytes = bytes(block_output)
        output_text = output_bytes.decode("utf-8", errors="replace")
        lines = output_text.split("\n")
        head = "\n".join(lines[:20])
        tail = output_text[-4096:] if len(output_text) > 4096 else output_text

        # Redact
        head, head_redacted = redact(head)
        tail, tail_redacted = redact(tail)

        # Release the session
        self._manager.set_block_open(sid, False)

        return {
            "block_id": block_id,
            "session_id": sid,
            "exit_code": exit_code if exit_code is not None else -1,
            "output_head": head,
            "output_tail": tail,
            "duration": duration,
            "redacted": head_redacted or tail_redacted,
        }

    def release(self, session_id: str) -> None:
        """Mark a session as no longer busy (block closed). Does not kill."""
        if session_id in self._sessions:
            self._manager.set_block_open(session_id, False)

    def _evict(self, session_id: str) -> None:
        """Remove a session from the pool's tracking (called on kill/evict)."""
        self._sessions.pop(session_id, None)

    async def shutdown(self) -> None:
        """Kill all pool sessions."""
        for sid in list(self._sessions.keys()):
            self._manager.kill(sid)
        self._sessions.clear()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_pool: Optional[TerminalPool] = None


def get_terminal_pool() -> TerminalPool:
    """Get the global TerminalPool (created lazily)."""
    global _pool
    if _pool is None:
        from .session_manager import get_terminal_manager
        _pool = TerminalPool(get_terminal_manager(), cap=3)
    return _pool


def set_terminal_pool(pool: Optional[TerminalPool]) -> None:
    """Inject/replace the global pool (for tests)."""
    global _pool
    _pool = pool
