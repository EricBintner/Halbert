# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""OpenClaw channel-health-monitor pattern: restarts budgeted per sliding
window, cooldown cycles between attempts, policy pure and table-tested —
including clock rollback (desktop machines suspend)."""
import pytest

from halbert_core.scheduler.restart_budget import RestartBudget, RestartDecision


def test_allows_first_restarts():
    rb = RestartBudget(max_per_hour=3, cooldown_cycles=1)
    assert rb.evaluate(restarts=[], now=1000) is RestartDecision.ALLOW
    assert rb.evaluate(restarts=[900], now=1000) is RestartDecision.ALLOW


def test_budget_exhausted_blocks():
    rb = RestartBudget(max_per_hour=3, cooldown_cycles=1)
    assert rb.evaluate(restarts=[300, 600, 900], now=1000) is RestartDecision.BLOCK


def test_sliding_window_recovers():
    rb = RestartBudget(max_per_hour=2, cooldown_cycles=1)
    assert rb.evaluate(restarts=[0, 60], now=3601) is RestartDecision.ALLOW  # both out of window


def test_clock_rollback_does_not_release_budget():
    rb = RestartBudget(max_per_hour=1, cooldown_cycles=1)
    assert rb.evaluate(restarts=[5000], now=1000) is RestartDecision.BLOCK  # now earlier than last restart: hold


def test_cooldown_needs_completed_cycles_since_last_restart():
    rb = RestartBudget(max_per_hour=3, cooldown_cycles=2)
    # budget is fine, but zero completed cycles since the restart at t=900
    assert rb.evaluate(restarts=[900], now=1000, cycles_since_restart=0) is RestartDecision.COOLDOWN
    assert rb.evaluate(restarts=[900], now=1000, cycles_since_restart=1) is RestartDecision.COOLDOWN
    assert rb.evaluate(restarts=[900], now=1000, cycles_since_restart=2) is RestartDecision.ALLOW


def test_budget_blocks_even_with_cycles_served():
    rb = RestartBudget(max_per_hour=1, cooldown_cycles=1)
    assert rb.evaluate(restarts=[500], now=1000, cycles_since_restart=9) is RestartDecision.BLOCK