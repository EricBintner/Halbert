# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert's presence curve (presence spec v2 §14): the engine's shape,
Halbert's copy, top budget 8, closes_after 5, and no social affect at any
level (pass 3 P-2)."""

import pytest

engine = pytest.importorskip("haloysius.attunement.types")

from halbert_core.attunement.curve import halbert_curve  # noqa: E402

C = engine.ImpulseClass


def test_curve_is_valid_and_owned_by_halbert():
    curve = halbert_curve()
    assert curve.owner == "halbert"
    assert [r.level for r in curve.rungs] == [0, 1, 3, 4, 6, 8, 10]


def test_no_social_affect_at_any_level():
    for r in halbert_curve().rungs:
        assert C.AFFECT_SOCIAL not in r.admits


def test_level_three_is_the_default_and_admits_the_morning():
    r = halbert_curve().rung_at(3)
    assert r.admits == {C.LIFE_SAFETY, C.CRITICAL, C.WARNING, C.SCHEDULED, C.RECURRENCE}


def test_copy_is_first_person_and_every_rung_says_why():
    for r in halbert_curve().rungs:
        assert r.says.startswith("I") and r.why


def test_top_rung_relaxes_the_engine_default():
    top = halbert_curve().rung_at(10)
    assert top.budget_per_day == 8 and top.closes_after == 5


def test_halbert_curve_is_cached():
    assert halbert_curve() is halbert_curve()
