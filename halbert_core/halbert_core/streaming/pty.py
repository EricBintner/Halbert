# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Async PTY session (B1a).

Real pseudo-terminal I/O via ``os.openpty()`` + ``aiofiles``. This is the
hardest single component in the streaming-terminal plan: raw master/slave fd
management, async reads from the master, stdin writes, SIGWINCH resize, and
child reaping — with no ``subprocess`` anywhere.

The session owns a bounded scrollback buffer (default 1 MiB) so the frontend
can render history on attach without holding unbounded output.

Unix-only (``os.fork``): macOS + Linux for v1. Windows is post-v1.

See OPUS-HANDOFF §B1a.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import signal
import struct
import termios
import time
from typing import AsyncIterator, Optional, Set

logger = logging.getLogger("halbert.streaming.pty")

_DEFAULT_BUFFER_BYTES = 1024 * 1024  # 1 MiB scrollback


class PTYSession:
    """Async PTY session using ``os.openpty()`` + ``aiofiles``.

    Lifecycle:
        session = PTYSession("echo hello")
        pid = await session.spawn()
        async for chunk in session.read_chunk():
            ...  # bytes of stdout
        # child has exited; session.exit_code is set
        session.kill()  # cleanup (idempotent)
    """

    def __init__(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        cols: int = 80,
        rows: int = 24,
        buffer_bytes: int = _DEFAULT_BUFFER_BYTES,
        echo: bool = True,
    ):
        self._command = command
        self._cwd = cwd
        self._env = env
        self._cols = cols
        self._rows = rows
        self._buffer_bytes = buffer_bytes
        self._echo = echo

        self._master_fd: Optional[int] = None
        self._slave_fd: Optional[int] = None
        self._pid: Optional[int] = None

        # Bounded scrollback (keep the most recent ``buffer_bytes`` of output)
        self._buffer = bytearray()
        self._exited = False
        self._exit_code: Optional[int] = None

        # Monotonic timestamp of the last stdout chunk. The session manager's
        # idle reaper treats recent output as activity, so a session streaming
        # output with no stdin (watching a long build) is not reaped mid-stream.
        self.last_output_at: float = 0.0

        # Queues of in-flight read_chunk() generators, so kill() can push the
        # EOF sentinel and wake consumers suspended at ``queue.get()``.
        self._read_queues: set = set()

        # Fan-out: single reader task + per-consumer queues (Plan B: B4).
        # The reader task reads the master fd once and pushes chunks to every
        # attached queue. This replaces the per-caller add_reader that starved
        # when a second consumer attached to the same fd.
        self._reader_task: Optional[asyncio.Task] = None
        self._fanout_queues: Set["asyncio.Queue"] = set()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def pid(self) -> Optional[int]:
        return self._pid

    @property
    def exit_code(self) -> Optional[int]:
        return self._exit_code

    def is_alive(self) -> bool:
        """Whether the child is still running.

        Does a non-blocking ``waitpid`` poll so a child that exited since the
        last check is reaped and reported as not-alive (rather than relying on
        a cached flag that may be stale after an abandoned read_chunk).
        """
        if self._exited:
            return False
        self._reap(blocking=False)
        return not self._exited

    def get_buffer(self) -> bytes:
        """Return the full scrollback buffer contents."""
        return bytes(self._buffer)

    # ------------------------------------------------------------------
    # Fan-out reader (Plan B: B4)
    # ------------------------------------------------------------------

    async def attach(self, maxsize: int = 0) -> "asyncio.Queue":
        """Subscribe to this session's output stream.

        Returns a queue that receives every future chunk. The first item
        is ``("__replay__", self.get_buffer())`` so a newly-attached xterm
        can render history without a separate fetch.

        Starts the single reader task if it is not already running.
        """
        # If the child has already exited, drain any remaining data from the
        # master fd before replaying so late attachers see the full output.
        if self._exited and self._master_fd is not None:
            self._drain_master()
        q: "asyncio.Queue" = asyncio.Queue(maxsize=maxsize)
        # Replay first
        q.put_nowait(("__replay__", self.get_buffer()))
        self._fanout_queues.add(q)
        if self._reader_task is None or self._reader_task.done():
            if self._master_fd is not None and not self._exited:
                self._reader_task = asyncio.create_task(self._reader_loop())
            elif self._exited:
                # Child already exited — push EOF immediately
                q.put_nowait(None)
        return q

    def detach(self, queue: "asyncio.Queue") -> None:
        """Unsubscribe a consumer queue. Non-blocking."""
        self._fanout_queues.discard(queue)

    async def _reader_loop(self) -> None:
        """Single reader task: reads master fd and fans out to all queues."""
        if self._master_fd is None:
            return
        loop = asyncio.get_event_loop()

        def _on_readable() -> None:
            if self._exited:
                return
            try:
                data = os.read(self._master_fd, 4096)
            except OSError:
                data = b""
            if not data:
                # EOF
                loop.remove_reader(self._master_fd)
                self._push_to_all(None)
                self._reap(blocking=True)
            else:
                self._append_buffer(data)
                self.last_output_at = time.monotonic()
                self._push_to_all(data)

        loop.add_reader(self._master_fd, _on_readable)
        try:
            # Keep the task alive until cancelled or EOF
            while not self._exited:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            if self._master_fd is not None:
                try:
                    loop.remove_reader(self._master_fd)
                except (RuntimeError, ValueError):
                    pass

    def _push_to_all(self, item) -> None:
        """Push an item to every fanout queue, dropping on overflow."""
        for q in list(self._fanout_queues):
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                # Queue is full (bounded) — drop the chunk for this consumer.
                # The scrollback buffer still has it; the consumer can re-attach
                # and replay. Never block the reader on one slow consumer.
                pass

    def _drain_master(self) -> None:
        """Non-blocking drain of any remaining data on the master fd."""
        if self._master_fd is None:
            return
        try:
            fcntl.fcntl(self._master_fd, fcntl.F_SETFL, os.O_NONBLOCK)
        except OSError:
            pass
        while True:
            try:
                data = os.read(self._master_fd, 4096)
            except OSError:
                break
            if not data:
                break
            self._append_buffer(data)
            self.last_output_at = time.monotonic()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def spawn(self) -> int:
        """Open the PTY, fork the child, and execute the command.

        Returns the child PID (also the session id).
        """
        self._master_fd, self._slave_fd = os.openpty()
        self._set_winsize(self._cols, self._rows)

        # Clear ECHO on the slave fd before forking (pool sessions).
        # The line discipline echo duplicates every stdin write as stdout,
        # which corrupts block output for agent-pool sessions.
        if not self._echo and self._slave_fd is not None:
            try:
                attrs = termios.tcgetattr(self._slave_fd)
                # ECHO is bit 3 (0x8) in c_lflag
                attrs[3] = attrs[3] & ~termios.ECHO
                termios.tcsetattr(self._slave_fd, termios.TCSANOW, attrs)
            except OSError:
                pass

        pid = os.fork()
        if pid == 0:
            # --- Child ---
            try:
                os.setsid()
                # Attach the slave PTY to stdin/stdout/stderr
                os.dup2(self._slave_fd, 0)
                os.dup2(self._slave_fd, 1)
                os.dup2(self._slave_fd, 2)
                # Acquire the PTY as controlling terminal: dup2 of a
                # parent-opened fd never triggers the session-leader ctty
                # acquisition path, and without a ctty /dev/tty (sudo
                # passwords, job control) is broken.
                if hasattr(termios, "TIOCSCTTY"):
                    try:
                        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
                    except OSError:
                        pass
                if self._master_fd is not None:
                    os.close(self._master_fd)
                if self._slave_fd is not None:
                    os.close(self._slave_fd)
                if self._cwd:
                    os.chdir(self._cwd)
                child_env = dict(os.environ)
                if self._env:
                    child_env.update(self._env)
                # Ensure the PTY is the controlling terminal
                os.execvpe("/bin/sh", ["/bin/sh", "-c", self._command], child_env)
            except Exception:  # pragma: no cover - child process
                os._exit(127)
        else:
            # --- Parent ---
            os.close(self._slave_fd)
            self._slave_fd = None
            self._pid = pid
            logger.info(f"PTY spawned pid={pid} cmd={self._command!r}")
            return pid

    async def read_chunk(self) -> AsyncIterator[bytes]:
        """Async generator yielding stdout chunks from the master fd.

        Backward-compatible wrapper around the fan-out reader (Plan B: B4).
        Creates a queue via ``attach()``, yields chunks, and detaches in
        ``finally``. The first item (``__replay__``) is skipped so callers
        that already consumed the buffer don't get a duplicate.
        """
        if self._master_fd is None:
            return
        queue = await self.attach()
        self._read_queues.add(queue)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, tuple) and item[0] == "__replay__":
                    # Skip replay for backward compat — callers that used
                    # read_chunk before B4 never got a replay item.
                    continue
                yield item
            # Normal EOF: the child has closed the slave, so a blocking reap is
            # safe and fast. This runs only on the natural-completion path.
            if not self._exited:
                self._reap(blocking=True)
        finally:
            self._read_queues.discard(queue)
            self.detach(queue)
            # Cleanup/abandon path (aclose while still running): never block.
            self._reap(blocking=False)

    async def write_stdin(self, data: str) -> None:
        """Write to the child's stdin (the master fd)."""
        if self._master_fd is None:
            raise OSError("PTY session has no master fd")
        os.write(self._master_fd, data.encode())

    def resize(self, cols: int, rows: int) -> None:
        """Send a new window size to the PTY (SIGWINCH-equivalent)."""
        self._cols = cols
        self._rows = rows
        if self._master_fd is not None:
            self._set_winsize(cols, rows)

    def kill(self) -> None:
        """Terminate the child and close the master fd. Idempotent."""
        was_alive = not self._exited
        # Cancel the reader task first (Plan B: B4).
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
        # Remove the async reader first so the event loop can shut down
        # cleanly even if a read_chunk generator was abandoned mid-iteration
        # (the generator's `finally` only runs on close/GC, which can be too
        # late during loop teardown). Safe to call from sync context.
        if self._master_fd is not None:
            try:
                asyncio.get_running_loop().remove_reader(self._master_fd)
            except (RuntimeError, ValueError):
                # No running loop (e.g. cleanup after loop close) — nothing to remove
                pass
        # Wake any in-flight read_chunk() consumer suspended at queue.get():
        # with the reader removed the EOF sentinel would otherwise never
        # arrive, leaving the consumer task frozen forever.
        for q in list(self._read_queues):
            try:
                q.put_nowait(None)
            except Exception:
                pass
        # Push EOF to every fanout queue (Plan B: B4).
        self._push_to_all(None)
        if was_alive and self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGTERM)
            except OSError:
                pass
            # Bounded, non-blocking reap: give SIGTERM a moment, then SIGKILL.
            time.sleep(0.05)
            self._reap(blocking=False)
            if not self._exited:
                try:
                    os.kill(self._pid, signal.SIGKILL)
                except OSError:
                    pass
                time.sleep(0.02)
                self._reap(blocking=False)
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None
        self._exited = True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _set_winsize(self, cols: int, rows: int) -> None:
        if self._master_fd is None:
            return
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

    def _append_buffer(self, data: bytes) -> None:
        """Append output to the bounded scrollback, trimming the oldest."""
        self._buffer.extend(data)
        if len(self._buffer) > self._buffer_bytes:
            # Keep only the most recent ``buffer_bytes``
            del self._buffer[: len(self._buffer) - self._buffer_bytes]

    def _reap(self, blocking: bool = True) -> None:
        """Reap the child, recording its exit code.

        ``blocking=True`` (default) waits for the child — only safe after a
        real EOF, when the child has already closed the slave. ``blocking=False``
        uses ``WNOHANG`` so an abandoned read_chunk generator (aclose while the
        child is still running) never blocks the event loop.
        """
        if self._pid is None:
            return
        flags = 0 if blocking else os.WNOHANG
        try:
            pid, status = os.waitpid(self._pid, flags)
        except OSError:
            # Already reaped (e.g. double-call)
            if self._exit_code is None:
                self._exit_code = -1
            self._exited = True
            return
        if pid == 0:
            # Non-blocking poll and child still running -> leave it
            return
        if os.WIFEXITED(status):
            self._exit_code = os.WEXITSTATUS(status)
        elif os.WIFSIGNALED(status):
            self._exit_code = -os.WTERMSIG(status)
        else:
            self._exit_code = -1
        self._exited = True
