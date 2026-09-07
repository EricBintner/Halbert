# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Restart budget policy for crash-loop guards (packet 03 A2).

OpenClaw's channel-health-monitor pattern, kept pure and table-tested:
restarts are budgeted per sliding window, a cooldown of completed cycles
must elapse between attempts, and — because desktop machines suspend and
their clocks roll back — a ``now`` earlier than the last restart holds the
budget closed instead of releasing it (a rollback must never make the
budget look fresher than it is).

Pure policy: the caller owns the restart ledger and the cycle telemetry.
"""
from __future__ import annotations

from enum import Enum


class RestartDecision(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    COOLDOWN = "cooldown"  # budget is fine, but not enough cycles since the last restart


class RestartBudget:
    """Budget restart attempts per sliding window.

    ``max_per_hour`` restarts within ``window_s`` block further attempts.
    ``cooldown_cycles`` completed job cycles must have elapsed since the
    last restart before another is allowed — pass the observed count as
    ``cycles_since_restart``; callers without cycle telemetry simply omit
    it and get window + rollback protection only.
    """

    def __init__(
        self,
        max_per_hour: int = 5,
        cooldown_cycles: int = 1,
        window_s: float = 3600.0,
    ):
        self.max_per_hour = max_per_hour
        self.cooldown_cycles = cooldown_cycles
        self.window_s = window_s

    def evaluate(self, restarts, now: float, cycles_since_restart: int = None) -> RestartDecision:
        if not restarts:
            return RestartDecision.ALLOW
        last = max(restarts)
        if now < last:
            # Clock rolled back (suspend, NTP step, manual change): hold.
            # Releasing here is how a crash-loop re-arms itself.
            return RestartDecision.BLOCK
        recent = [t for t in restarts if now - t <= self.window_s]
        if len(recent) >= self.max_per_hour:
            return RestartDecision.BLOCK
        if cycles_since_restart is not None and cycles_since_restart < self.cooldown_cycles:
            return RestartDecision.COOLDOWN
        return RestartDecision.ALLOW