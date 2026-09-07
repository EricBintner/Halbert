# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Deterministic echo guard: second layer over the redaction choke point.

Lifted from OpenClaw src/gateway/boot-echo-guard.ts: rolling-window chunk
match of recently injected sensitive material against outbound deliveries.
Catches the model reproducing a long verbatim chunk even after paraphrasing
around markers. Pure detection — the wiring layer decides suppression vs.
warn (Halbert's posture is warn-and-redact; see the seam in
``agents.state_machine`` and the injection site in ``config.queries``).

What "recently injected sensitive material" means here
-------------------------------------------------------
The acknowledged-egress path (``config.queries.get_config_value`` after
tier + acknowledgment + TTL) is the only place Halbert deliberately hands a
secret out. That same site feeds this guard (``note_injected``), so the
guard's window set contains exactly the material whose re-appearance in an
outbound reply means the model echoed context it should have paraphrased.

Scope
-----
The injection site has no session identity — a config query is not tied to
one conversation — so the scope is the process, which is also the correct
sharing scope for a single-user assistant. The ``session`` parameter is
the extension point for the day it does; today ``clear_session`` clears
the process scope and every scan sees every injection.

Cost
-----
``note_injected`` stores one ``window``-sized chunk per overlapping window
of the normalized text (a 200-char value at the default window is ~121
chunks). The store is bounded FIFO (``max_chunks``) so a long-lived
process cannot accumulate without limit; re-noted chunks refresh their
recency rather than duplicating.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Optional

# The default window matches OpenClaw's 80-char contiguous chunk rule: long
# enough that ordinary prose never matches, short enough that a verbatim
# echo of a secret (or of the sentence it arrived in) is caught whole.
DEFAULT_WINDOW = 80


class EchoGuard:
    """Rolling-window chunk detector over recently injected material."""

    def __init__(
        self,
        window: int = DEFAULT_WINDOW,
        threshold: int = DEFAULT_WINDOW,
        max_chunks: int = 16384,
    ):
        # ``threshold`` is reserved: scan_outbound flags any single window
        # >= ``window`` chars; if telemetry ever shows false positives, the
        # minimum flagged-chunk count is the knob to add. The parameter
        # stays so call sites do not churn when it lands.
        self._window = window
        self._threshold = threshold
        self._chunks: "OrderedDict[str, None]" = OrderedDict()
        self._max_chunks = max_chunks

    @staticmethod
    def _normalize(text: str) -> str:
        """Collapse all whitespace runs to single spaces.

        The injected material and the outbound reply may differ in line
        wrapping alone; a chunk match should not depend on it.
        """
        return " ".join(text.split())

    def _windows(self, norm: str):
        # range covers every full window; a text shorter than the window
        # contributes its whole self as a single chunk (and a scan of text
        # shorter than the window compares whole-to-whole the same way).
        for i in range(0, max(1, len(norm) - self._window + 1)):
            yield norm[i:i + self._window]

    def note_injected(self, text: str, session: str = "default") -> None:
        """Record sensitive material whose echo in outbound text is a leak.

        ``session`` is accepted for forward compatibility (see the module
        docstring's Scope note) and currently names the process scope.
        """
        norm = self._normalize(text)
        if not norm:
            return
        for chunk in self._windows(norm):
            if chunk in self._chunks:
                self._chunks.move_to_end(chunk)
            else:
                self._chunks[chunk] = None
                if len(self._chunks) > self._max_chunks:
                    self._chunks.popitem(last=False)

    def find_match(self, text: str, session: str = "default") -> Optional[str]:
        """The first injected window reproduced verbatim in ``text``, or None.

        Returns the matched material itself — for the wiring layer to hash
        into its structured warning. It must never be logged raw.
        """
        norm = self._normalize(text)
        for window in self._windows(norm):
            if window in self._chunks:
                return window
        return None

    def scan_outbound(self, text: str, session: str = "default") -> bool:
        """True when ``text`` reproduces a long verbatim chunk of injected
        material."""
        return self.find_match(text) is not None

    def clear_session(self, session: str = "default") -> None:
        """Forget all injected material (process scope today — see the
        module docstring's Scope note)."""
        self._chunks.clear()

    def __len__(self) -> int:
        return len(self._chunks)


_GLOBAL: Optional[EchoGuard] = None


def get_global_echo_guard() -> EchoGuard:
    """Process-global guard; the injection site and the outbound seam are in
    different subsystems and must see the same window set."""
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = EchoGuard()
    return _GLOBAL