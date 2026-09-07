# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Turn activity generations: race-safe cancellation claims.

Pattern lifted from Hermes ``agent/interrupt_control.py`` (require_generation):
a mid-turn cancel is issued cross-thread, so it can lose the race to a turn
that is finishing anyway. The abort carries the activity generation it
observed; at the final mutation edge the abort executes only if the
generation still matches — an abort that arrives late *declines* instead of
double-firing on a turn that already completed.

The object is pure mechanics: it owns a lock and a monotonic generation
counter and nothing else. The state machine (Packet 07 Phase B) supplies
the stamps at turn start / finalize and passes ``claim`` the abort closure.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional


class TurnActivity:
    """A monotonically increasing generation counter with single-shot claims.

    ``stamp()`` advances the generation and returns the current value: call
    it whenever the turn's activity "moves on" (turn starts, a tool batch
    boundary passes, the turn finalizes). ``claim(gen, fn)`` runs ``fn``
    under the lock iff ``gen`` is still the current generation and has not
    been claimed — exactly once, else returns ``None``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0
        self._claimed = False

    def stamp(self) -> int:
        """Advance to a fresh generation and return the current one.

        Any outstanding claims for older generations become stale, and the
        single-shot claim of the *current* generation is reset: a new
        generation is a new, unclaimed activity.
        """
        with self._lock:
            self._generation += 1
            self._claimed = False
            return self._generation

    @property
    def generation(self) -> int:
        """The current generation (read under lock)."""
        with self._lock:
            return self._generation

    def claim(self, generation: int, fn: Callable[[], Any]) -> Optional[Any]:
        """Execute ``fn`` under the lock iff ``generation`` is current, once.

        Returns ``fn()``'s result on a fresh claim; ``None`` when the claim
        is stale (the turn moved on) or already consumed (single-shot).
        """
        with self._lock:
            if generation != self._generation or self._claimed:
                return None
            self._claimed = True
            return fn()