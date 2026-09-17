# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert's presence curve (presence spec v2 §14): the engine's shape,
Halbert's copy, top budget 8, closes_after 5, and no social affect at any
level (pass 3 P-2)."""

import re

import pytest

from halbert_core.attunement.curve import halbert_curve

engine = pytest.importorskip("haloysius.attunement.types")

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
        assert re.search(r"\bI('ll| )", r.says) and r.why   # the person, not the letter


def test_top_rung_relaxes_the_engine_default():
    top = halbert_curve().rung_at(10)
    assert top.budget_per_day == 8 and top.closes_after == 5


def test_halbert_curve_is_cached():
    assert halbert_curve() is halbert_curve()


def test_admission_channel_and_patience_agree_with_the_engine_vectors():
    """The shape is the engine's, rung for rung; only budget, closes_after and
    the copy are Halbert's to change. The engine's own 136 vectors say so."""
    from haloysius.attunement.conformance import check_presence
    from haloysius.attunement.presence import resolve_presence
    from halbert_core.attunement.context import halbert_config
    failures = check_presence(
        lambda level, ov: resolve_presence(level, halbert_curve(), halbert_config().attachment, ov))
    assert not failures, "\n".join(failures)
