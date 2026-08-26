"""Async PTY session (B1a).

Real pseudo-terminal I/O via ``os.openpty()`` + ``aiofiles``. This is the
hardest single component in the sovereign-host plan: raw master/slave fd
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
from typing import AsyncIterator, Optional

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
    ):
        self._command = command
        self._cwd = cwd
        self._env = env
        self._cols = cols
        self._rows = rows
        self._buffer_bytes = buffer_bytes

        self._master_fd: Optional[int] = None
        self._slave_fd: Optional[int] = None
        self._pid: Optional[int] = None

        # Bounded scrollback (keep the most recent ``buffer_bytes`` of output)
        self._buffer = bytearray()
        self._exited = False
        self._exit_code: Optional[int] = None

        # Queues of in-flight read_chunk() generators, so kill() can push the
        # EOF sentinel and wake consumers suspended at ``queue.get()``.
        self._read_queues: set = set()

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
    # Lifecycle
    # ------------------------------------------------------------------

    async def spawn(self) -> int:
        """Open the PTY, fork the child, and execute the command.

        Returns the child PID (also the session id).
        """
        self._master_fd, self._slave_fd = os.openpty()
        self._set_winsize(self._cols, self._rows)

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

        Uses the event loop's reader (kqueue on macOS, epoll on Linux) via
        ``loop.add_reader`` rather than ``aiofiles``. ``aiofiles`` runs reads
        in a thread executor, and a blocked PTY read does NOT unblock when the
        master fd is closed — which hangs the event loop on shutdown. The
        selector-based approach unregisters cleanly on fd close.

        Yields until the child exits and the master returns EOF, then reaps
        the child and records the exit code. Safe to iterate once per spawn.
        """
        if self._master_fd is None:
            return
        loop = asyncio.get_event_loop()
        queue: "asyncio.Queue[Optional[bytes]]" = asyncio.Queue()
        self._read_queues.add(queue)
        eof = False

        def _on_readable() -> None:
            nonlocal eof
            if self._exited:
                return
            try:
                data = os.read(self._master_fd, 4096)
            except OSError:
                # Master closed / error -> treat as EOF
                data = b""
            if not data:
                eof = True
                loop.remove_reader(self._master_fd)
                queue.put_nowait(None)
            else:
                self._append_buffer(data)
                queue.put_nowait(data)

        loop.add_reader(self._master_fd, _on_readable)
        try:
            while not eof:
                item = await queue.get()
                if item is None:
                    break
                yield item
            # Normal EOF: the child has closed the slave, so a blocking reap is
            # safe and fast. This runs only on the natural-completion path.
            self._reap(blocking=True)
        finally:
            self._read_queues.discard(queue)
            # None after a concurrent kill() already removed the reader and
            # closed the fd — remove_reader would fail (and could target a
            # reused fd number), so skip it in that case.
            if self._master_fd is not None:
                loop.remove_reader(self._master_fd)
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