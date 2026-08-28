# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Watched user shell — block processing and hint generation.

When a user shell block closes (OSC 133 D marker on a 'user' kind session):
1. redact() runs on output_head and output_tail.
2. store.insert_terminal_block() records the block.
3. If watched and a thread is open: store.append_message() with
   origin='terminal', visible_in_timeline=1, terminal_block_ids=[block_id].
4. thread.last_active is updated for the gap gate (never triggers new_thread).
5. The agent sees blocks at the next turn, in the hint, capped at 8 blocks / 2 KB.

See plan-b-contracts.md section 8.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .redact import redact

logger = logging.getLogger("halbert.streaming.watched_shell")


@dataclass
class BlockRecord:
    """A closed terminal block from a user shell."""
    block_id: str
    session_id: str
    command: str
    cwd: Optional[str]
    exit_code: Optional[int]
    started_at: float
    ended_at: float
    output_head: str
    output_tail: str

    @property
    def duration(self) -> float:
        return self.ended_at - self.started_at


class WatchedShellProcessor:
    """Processes closed user-shell blocks: redact, store, and notify the thread."""

    def __init__(self, store):
        self._store = store

    def process_block_close(
        self,
        rec: BlockRecord,
        *,
        thread_id: Optional[str] = None,
        watched: bool = True,
    ) -> bool:
        """Process a closed block from a user shell.

        Returns True on success, False on store failure.
        """
        # 1. Redact
        head, head_redacted = redact(rec.output_head)
        tail, tail_redacted = redact(rec.output_tail)
        was_redacted = head_redacted or tail_redacted

        # 2. Insert terminal block
        block: Dict[str, Any] = {
            "block_id": rec.block_id,
            "session_id": rec.session_id,
            "thread_id": thread_id,
            "turn_id": None,
            "command": rec.command,
            "cwd": rec.cwd,
            "owner": "user",
            "interactive": 0,
            "remote": 0,
            "redacted": 1 if was_redacted else 0,
            "started_at": rec.started_at,
            "ended_at": rec.ended_at,
            "exit_code": rec.exit_code,
            "output_head": head,
            "output_tail": tail,
        }
        if not self._store.insert_terminal_block(block):
            logger.warning(f"Failed to insert terminal block {rec.block_id}")
            return False

        # 3. Append message if watched and thread is open
        if watched and thread_id is not None:
            content = (
                f"$ {rec.command} · exit {rec.exit_code} · "
                f"{rec.duration:.1f}s · cwd={rec.cwd}"
            )
            try:
                self._store.append_message(
                    thread_id,
                    role="system",
                    content=content,
                    origin="terminal",
                    visible_in_timeline=1,
                    terminal_block_ids=[rec.block_id],
                )
            except Exception as e:
                logger.warning(f"Failed to append terminal message: {e}")

            # 4. Update thread last_active (never triggers new_thread)
            try:
                self._store.update_thread(thread_id, updated_at=rec.ended_at)
            except Exception as e:
                logger.warning(f"Failed to update thread last_active: {e}")

        return True

    def get_recent_blocks(
        self,
        thread_id: str,
        *,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        """Get recent terminal blocks for a thread, newest-first."""
        return self._store.list_terminal_blocks(thread_id=thread_id, limit=limit)

    def build_hint_text(self, thread_id: str) -> Optional[str]:
        """Build the continuity hint text for terminal blocks.

        Returns None when there are no terminal-origin blocks.
        Capped at 8 blocks / 2 KB.
        """
        blocks = self.get_recent_blocks(thread_id, limit=8)
        if not blocks:
            return None

        n = len(blocks)
        last = blocks[0]
        last_cmd = last.get("command", "?")
        last_exit = last.get("exit_code", "?")

        hint = (
            f"[Since your last message you ran {n} command"
            f"{'s' if n != 1 else ''} in your shell "
            f"(last: {last_cmd}, exit {last_exit})]"
        )

        # Cap at 2 KB
        if len(hint) > 2048:
            hint = hint[:2048]
        return hint
