# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Activity generations: a cross-thread cancel that loses the race to a
finishing turn must DECLINE, not double-fire (Hermes require_generation)."""
from halbert_core.agents.turn_activity import TurnActivity


def test_fresh_claim_publishes():
    act = TurnActivity()
    gen = act.stamp()
    assert act.claim(gen, lambda: "published") == "published"


def test_stale_claim_declines():
    act = TurnActivity()
    old = act.stamp()
    act.stamp()  # the turn moved on
    fired = []
    assert act.claim(old, lambda: fired.append(1)) is None
    assert fired == []


def test_claim_is_single_shot_under_lock():
    act = TurnActivity()
    gen = act.stamp()
    results = [act.claim(gen, lambda: "x") for _ in range(2)]
    assert results.count("x") == 1