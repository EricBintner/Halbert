# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A bounded accumulator for command output.

Every surface that runs a shell command here — the agent's block pool, the
dashboard's /exec route — ends up returning a short head and tail of what the
command printed. Both used to accumulate the whole of it first and cut it down
afterwards, so `cat` on a large file was held entirely in memory before being
thrown away (R04-F4; ~800 MB reproduced by the REV-04 review).
"""

# Ample for the 20-line head and 4 KiB tail that actually get returned,
# while capping peak retention at ~128 KiB per command.
DEFAULT_HEAD_BYTES = 64 * 1024
DEFAULT_TAIL_BYTES = 64 * 1024


class BoundedOutput:
    """Accumulate output keeping only both ends.

    Whatever falls between the head and the tail is dropped as it arrives
    rather than after the fact, and ``bytes()`` splices an elision marker in
    its place so the caller can see that output is missing rather than
    silently reading a truncated command result as a whole one.
    """

    __slots__ = ("_head", "_tail", "_dropped", "_head_cap", "_tail_cap")

    def __init__(self, head_cap: int = DEFAULT_HEAD_BYTES,
                 tail_cap: int = DEFAULT_TAIL_BYTES):
        self._head = bytearray()
        self._tail = bytearray()
        self._dropped = 0
        self._head_cap = head_cap
        self._tail_cap = tail_cap

    def extend(self, data: bytes) -> None:
        if not data:
            return
        room = self._head_cap - len(self._head)
        if room > 0:
            self._head.extend(data[:room])
            data = data[room:]
            if not data:
                return
        self._tail.extend(data)
        overflow = len(self._tail) - self._tail_cap
        if overflow > 0:
            del self._tail[:overflow]
            self._dropped += overflow

    @property
    def dropped(self) -> int:
        return self._dropped

    def __len__(self) -> int:
        return len(self._head) + len(self._tail)

    def bytes(self) -> bytes:
        if not self._dropped:
            return bytes(self._head) + bytes(self._tail)
        marker = f"\n... [{self._dropped} bytes elided] ...\n".encode()
        return bytes(self._head) + marker + bytes(self._tail)
