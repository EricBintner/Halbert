# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A3: state goes to the state ledger, events go to the event ledger.

`StateStore.record_state` deduplicates — `if cur["object"] == obj: return None`.
That is correct and wanted for *state* ("the door is unlocked" is one fact, not
one per report) and fatal for *events* (three sightings of the same van must
count three). So the split is not a tidiness preference; putting an event in
the state store destroys the recurrence the whole ledger exists to support,
and the plan's own warning — do not defeat the dedup by embedding a timestamp
in the object value — is the shortcut this asserts against.

Motion is the interesting case: "motion detected" is a moment, not a
condition, so it stays event-only. A door being open is a condition.
"""

import time

import pytest

from halbert_core.continuity.freshness import AnswerSource, decide, is_re_observable
from halbert_core.continuity.state_store import StateStore
from halbert_core.integrations.home_assistant.ha_event_mapper import (
    HAEventMapper,
    state_triple,
)


def _event(domain, new, old="", entity=None, device_class=""):
    return {
        "entity_id": entity or f"{domain}.thing",
        "domain": domain,
        "old_state": old,
        "new_state": new,
        "attributes": {"friendly_name": "Thing", "device_class": device_class},
        "timestamp": 1000.0,
    }


class TestWhichObservationsAreState:

    @pytest.mark.parametrize("event, predicate, obj", [
        (_event("lock", "unlocked", "locked"), "lock_state", "unlocked"),
        (_event("lock", "locked", "unlocked"), "lock_state", "locked"),
        (_event("alarm_control_panel", "armed_away", "disarmed"), "alarm_state", "armed_away"),
        (_event("alarm_control_panel", "triggered", "armed_away"), "alarm_state", "triggered"),
        (_event("person", "home", "not_home"), "presence", "home"),
        (_event("device_tracker", "not_home", "home"), "presence", "not_home"),
        (_event("climate", "heat", "off"), "climate_state", "heat"),
        (_event("light", "on", "off"), "power_state", "on"),
        (_event("switch", "off", "on"), "power_state", "off"),
        (_event("binary_sensor", "on", "off", device_class="door"), "door_state", "open"),
        (_event("binary_sensor", "off", "on", device_class="door"), "door_state", "closed"),
        (_event("binary_sensor", "on", "off", device_class="moisture"), "moisture_state", "wet"),
    ])
    def test_state_shaped_observations_produce_a_triple(self, event, predicate, obj):
        assert state_triple(event) == (predicate, obj)

    @pytest.mark.parametrize("event, why", [
        (_event("binary_sensor", "on", "off", device_class="motion"),
         "motion detected is a moment, not a condition"),
        (_event("sensor", "21.5", "21.4"),
         "a telemetry reading is not one of the states we model"),
        ({}, "an empty event asserts nothing"),
    ])
    def test_event_shaped_observations_produce_none(self, event, why):
        assert state_triple(event) is None, why

    def test_it_is_pure_and_total(self):
        # Same rule as the describer beside it: HA sends null states.
        assert state_triple({"domain": "lock", "new_state": None}) is None


class TestTheTripleReachesTheLedger:

    @pytest.fixture
    def ledger(self, tmp_path):
        return StateStore(db_path=str(tmp_path / "state.db"))

    def test_a_lock_transition_records_a_triple(self, ledger):
        HAEventMapper(ledger=ledger).add_event(
            _event("lock", "unlocked", "locked", entity="lock.front_door"))
        rows = ledger.current_state("lock.front_door", "lock_state", strict=True)
        assert len(rows) == 1
        assert rows[0].object == "unlocked"

    def test_the_reason_names_itself_and_is_not_generated(self, ledger):
        HAEventMapper(ledger=ledger).add_event(
            _event("lock", "unlocked", "locked", entity="lock.front_door"))
        why = ledger.why("lock.front_door", "lock_state")
        assert "locked" in str(why) and "unlocked" in str(why), (
            "the reason must say what actually happened, not be invented"
        )

    def test_repeating_the_same_state_does_not_pile_up(self, ledger):
        m = HAEventMapper(ledger=ledger)
        for _ in range(3):
            m.add_event(_event("lock", "unlocked", "locked", entity="lock.front_door"))
        assert len(ledger.state_history("lock.front_door", "lock_state")) == 1, (
            "dedup is the feature that makes StateStore right for state"
        )

    def test_an_event_shaped_observation_writes_no_triple(self, ledger):
        HAEventMapper(ledger=ledger).add_event(
            _event("binary_sensor", "on", "off",
                   entity="binary_sensor.hall", device_class="motion"))
        assert ledger.current_state("binary_sensor.hall", strict=True) == [], (
            "motion is a moment; nothing about it is a standing condition"
        )

    def test_a_missing_ledger_is_not_fatal(self):
        HAEventMapper(ledger=None).add_event(_event("lock", "unlocked", "locked"))


class TestFreshnessTreatsThemAsReObservable:
    """A stale lock reading must send the answering path to look, not remember."""

    @pytest.mark.parametrize("predicate", [
        "lock_state", "alarm_state", "presence",
        "door_state", "power_state", "climate_state", "moisture_state",
    ])
    def test_each_predicate_is_re_observable(self, predicate):
        assert is_re_observable(predicate)

    def test_a_stale_lock_row_returns_probe(self, tmp_path):
        ledger = StateStore(db_path=str(tmp_path / "s.db"))
        HAEventMapper(ledger=ledger).add_event(
            _event("lock", "unlocked", "locked", entity="lock.front_door"))
        d = decide("lock.front_door", "lock_state", store=ledger, fresh_seconds=-1)
        assert d.source is AnswerSource.PROBE
        assert d.must_look

    def test_a_fresh_lock_row_answers_from_the_ledger(self, tmp_path):
        ledger = StateStore(db_path=str(tmp_path / "s.db"))
        HAEventMapper(ledger=ledger).add_event(
            _event("lock", "unlocked", "locked", entity="lock.front_door"))
        d = decide("lock.front_door", "lock_state", store=ledger, fresh_seconds=3600)
        assert d.source is AnswerSource.LEDGER
        assert d.value == "unlocked"


class TestTheTwoLedgersStayInTheirLanes:

    def test_a_state_transition_still_writes_its_event_row(self, tmp_path):
        # A2's contract is unchanged: every HA event gets one ha_state_change
        # row. A3 adds a triple; it does not take the row away.
        from halbert_core.continuity.timeline import TimelineStore

        timeline = TimelineStore(db_path=str(tmp_path / "t.db"))
        ledger = StateStore(db_path=str(tmp_path / "s.db"))
        HAEventMapper(timeline=timeline, ledger=ledger).add_event(
            _event("lock", "unlocked", "locked", entity="lock.front_door"))
        assert len(timeline.query(event_type="ha_state_change")) == 1
        assert ledger.current_state("lock.front_door", "lock_state", strict=True)


class TestTheProductionMapperGetsALedger:
    """The routing is worth nothing if the shipped mapper has no ledger.

    This is exactly how DEFECT-3 happened: TimelineStore was complete, tested,
    and constructed by nothing.
    """

    def test_the_wiring_injects_a_state_ledger(self, monkeypatch):
        import halbert_core.integrations.cognition_wiring as cw

        captured = {}

        class _Mapper:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(cw, "_ha_event_mapper", None, raising=False)
        monkeypatch.setattr(
            "halbert_core.integrations.home_assistant.ha_event_mapper.HAEventMapper",
            _Mapper,
        )
        cw.get_ha_event_mapper()
        assert "ledger" in captured, (
            "the mapper classifies state and has nowhere to put it"
        )
