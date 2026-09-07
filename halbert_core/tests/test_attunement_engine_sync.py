# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Are Halbert's mirrors still in sync with the engine's contract?

``halbert_core.attunement`` declares local copies of four engine enums and of
the ``SituationSignals`` field set, so the adapter is testable and importable
with ``haloysius.attunement`` absent. Local copies drift. This repo already
carries a repo-wide vocabulary guard test *because* two screens drifted while
sixteen local tests stayed green, so the mirrors are checked against the real
types rather than against a second copy of the author's belief.

Every test here skips while the engine package is unbuilt and starts asserting
the moment it lands — which is the point: the sync check answers itself.
"""

import dataclasses

import pytest

from halbert_core.attunement import sensor as hb_sensor
from halbert_core.attunement import subject as hb_subject
from halbert_core.attunement import surfaces as hb_surfaces
from halbert_core.attunement.store import AttunementStore

engine_types = pytest.importorskip(
    "haloysius.attunement.types",
    reason="haloysius.attunement not built yet (spec revision 2, phase A in flight)",
)


def _values(enum_cls):
    return {m.value for m in enum_cls}


def test_channel_class_values_match():
    assert _values(hb_surfaces.ChannelClass) == _values(engine_types.ChannelClass)


def test_subject_confidence_values_match():
    assert _values(hb_subject.SubjectConfidence) == _values(
        engine_types.SubjectConfidence
    )


def test_activity_values_match():
    """A local Activity member the engine does not have would be sent and
    silently ignored; one the engine has and we lack is a row we cannot feed."""
    assert _values(hb_sensor.Activity) == _values(engine_types.Activity)


def test_signal_provenance_values_match():
    assert _values(hb_sensor.SignalProvenance) == _values(
        engine_types.SignalProvenance
    )


def test_our_signal_fields_are_a_subset_of_the_engine_contract():
    """Extra local fields would raise on construction."""
    engine_fields = {f.name for f in dataclasses.fields(engine_types.SituationSignals)}
    ours = {f.name for f in dataclasses.fields(hb_sensor.SituationSnapshot)}
    assert ours <= engine_fields, f"fields the engine does not accept: {ours - engine_fields}"


def test_a_snapshot_converts_to_the_engine_type():
    snapshot = hb_sensor.build_signals(idle_seconds=45)
    signals = snapshot.to_engine()
    assert signals is not None
    assert signals.activity == engine_types.Activity.IDLE.value or \
           signals.activity == engine_types.Activity.IDLE


def test_the_store_satisfies_the_engine_protocol():
    """A-HB-2: Halbert injects its own store. If it does not structurally
    satisfy the Protocol, the injection silently falls back to the file
    store and the multi-body problem comes back."""
    ledger = pytest.importorskip("haloysius.attunement.ledger")
    store = AttunementStore(db_path=":memory:")
    assert isinstance(store, ledger.StandingRequestStore)


def test_unfed_rows_are_named_so_the_gap_is_visible():
    """Documents what Halbert does not yet supply, so the list is a decision
    rather than an oversight. Update it as the sensor grows."""
    engine_fields = {f.name for f in dataclasses.fields(engine_types.SituationSignals)}
    ours = {f.name for f in dataclasses.fields(hb_sensor.SituationSnapshot)}
    known_gaps = {
        # Comes from a parsed directive via the ledger, not from a sensor.
        "user_stated_busy_until",
        # A-BM-5's reading-time term. BrightestMinds-shaped: it models a
        # person reading a long reply, which is not a Halbert situation.
        "last_persona_reply_words",
        "time_since_last_persona_turn_s",
    }
    assert engine_fields - ours == known_gaps


def test_our_freshness_default_matches_the_engine_field_default():
    """§4.5 of the plan: assert against the engine's numbers, never copy them.
    ``sensor.DEFAULT_FRESHNESS_S`` is the fallback we send when no per-signal
    horizon applies; if the engine moves its default and we do not, every
    unfused signal silently ages at a different rate on the two sides."""
    field = next(
        f for f in dataclasses.fields(engine_types.SituationSignals)
        if f.name == "freshness_horizon_s"
    )
    assert hb_sensor.DEFAULT_FRESHNESS_S == field.default


def test_our_retention_default_matches_the_engine_config():
    """The store trims outcomes on its own schedule; drifting from
    ``AttunementConfig.outcome_retention_days`` would mean the engine
    believing it has 90 days of evidence that we deleted."""
    from halbert_core.attunement.store import DEFAULT_RETENTION_DAYS

    assert DEFAULT_RETENTION_DAYS == engine_types.AttunementConfig().outcome_retention_days


def test_the_policy_constants_are_importable_as_a_table():
    """Assumption 8 / Halbert non-blocking #11: consumers assert against the
    engine's constants rather than duplicating them. This is the access path
    working, so a future receptivity assertion has somewhere to point."""
    from haloysius.attunement.testing import constants

    table = constants()
    assert table, "the engine exports no constants table"
