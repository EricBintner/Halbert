# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Per-file checkpoint stack for undo-before-action (C1c).

Before SomaticLifecycle executes a proposal's changes, CheckpointManager saves
the current content of every affected file. If execution fails and rolls
back, the most recent checkpoint per file can be restored — a coarse-grained,
in-memory undo that complements (does not replace) WriteConfig's own
backup/rollback.

Each path has a bounded LIFO stack (default 50); the oldest checkpoint is
dropped when the cap is exceeded (FIFO trim). Non-existent files are recorded
as ``None`` so rollback can restore the pre-action "file did not exist" state.

Pattern stolen from OCC's CheckpointManager. See OPUS-HANDOFF §C1c.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("halbert.somatic.checkpoints")


class CheckpointManager:
    """Per-file stack of byte-content checkpoints (in-memory, bounded)."""

    def __init__(self, max_checkpoints: int = 50):
        self._stacks: Dict[str, List[Optional[bytes]]] = {}
        self._max = max_checkpoints

    def checkpoint(self, path: str) -> None:
        """Save the current content of ``path`` (None if it doesn't exist)."""
        p = str(path)
        try:
            if Path(p).exists():
                with open(p, "rb") as f:
                    content: Optional[bytes] = f.read()
            else:
                content = None
        except OSError as e:
            logger.warning(f"checkpoint read failed for {p}: {e}")
            content = None
        stack = self._stacks.setdefault(p, [])
        stack.append(content)
        if len(stack) > self._max:
            # Drop the oldest (FIFO trim) — keep the most recent N
            del stack[: len(stack) - self._max]

    def checkpoint_many(self, paths: List[str]) -> int:
        """Checkpoint several paths; returns the number checkpointed."""
        n = 0
        for p in paths:
            if p:
                self.checkpoint(p)
                n += 1
        return n

    def rollback(self, path: str) -> Optional[bytes]:
        """Pop and restore the most recent checkpoint for ``path``.

        Returns the restored content, or None if there was no checkpoint (in
        which case nothing is written). Restoring ``None`` content removes the
        file (it didn't exist when checkpointed).
        """
        p = str(path)
        stack = self._stacks.get(p)
        if not stack:
            return None
        content = stack.pop()
        try:
            if content is None:
                if Path(p).exists():
                    Path(p).unlink()
            else:
                with open(p, "wb") as f:
                    f.write(content)
        except OSError as e:
            logger.warning(f"rollback write failed for {p}: {e}")
        if not stack:
            self._stacks.pop(p, None)
        return content

    def rollback_many(self, paths: List[str]) -> int:
        """Roll back several paths (most recent checkpoint each). Returns count."""
        n = 0
        for p in paths:
            if self.rollback(p) is not None:
                n += 1
        return n

    def stack_depth(self, path: str) -> int:
        """Number of checkpoints held for ``path``."""
        return len(self._stacks.get(str(path), []))

    def paths(self) -> List[str]:
        """All paths with at least one checkpoint."""
        return [p for p, s in self._stacks.items() if s]

    def clear(self, path: Optional[str] = None) -> None:
        """Clear checkpoints for one path, or all paths if None."""
        if path is None:
            self._stacks.clear()
        else:
            self._stacks.pop(str(path), None)
