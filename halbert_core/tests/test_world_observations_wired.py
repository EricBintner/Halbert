# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A4 has to reach an actual prompt, not just be able to.

The A4 commit added `world_observations` to `assemble()` and to
`build_response_prompt()`, added `as_prompt_line()`, and tested all three --
and no production caller passed the argument, so not one ledger row ever
reached a model. That is DEFECT-3's shape exactly: complete, tested, and
constructed by nothing. These tests assert the wiring, not the capability.
"""

import time

import pytest

from halbert_core.continuity.timeline import TimelineEvent, TimelineStore


@pytest.fixture
def store(tmp_path):
    s = TimelineStore(db_path=str(tmp_path / "t.db"))
    s.record(TimelineEvent(timestamp=time.time(), event_type="ha_state_change",
                           source="ha", entity_id="lock.front_door",
                           severity="warning", title="Front door was unlocked"))
    s.record(TimelineEvent(timestamp=time.time(), event_type="frigate_event",
                           source="frigate", entity_id="driveway:van",
                           title="Detected car at driveway"))
    return s


class TestTheStateMachineProducesWorldRows:

    def _machine(self, store, monkeypatch):
        from halbert_core.agents.state_machine import AgentStateMachine
        import halbert_core.integrations.cognition_wiring as cw

        monkeypatch.setattr(cw, "get_timeline_store", lambda: store)
        return AgentStateMachine.__new__(AgentStateMachine)

    def test_it_returns_cited_rows(self, store, monkeypatch):
        rows = self._machine(store, monkeypatch)._world_observations()
        assert rows
        assert all(r.startswith("[t") for r in rows)
        assert any("Front door was unlocked" in r for r in rows)

    def test_no_ledger_is_not_fatal(self, monkeypatch):
        import halbert_core.integrations.cognition_wiring as cw
        from halbert_core.agents.state_machine import AgentStateMachine

        monkeypatch.setattr(cw, "get_timeline_store", lambda: None)
        assert AgentStateMachine.__new__(AgentStateMachine)._world_observations() == []

    def test_a_broken_ledger_is_not_fatal(self, monkeypatch):
        import halbert_core.integrations.cognition_wiring as cw
        from halbert_core.agents.state_machine import AgentStateMachine

        class _Broken:
            def query(self, **k):
                raise RuntimeError("disk gone")

        monkeypatch.setattr(cw, "get_timeline_store", lambda: _Broken())
        assert AgentStateMachine.__new__(AgentStateMachine)._world_observations() == []

    def test_it_is_bounded(self, tmp_path, monkeypatch):
        import halbert_core.integrations.cognition_wiring as cw
        from halbert_core.agents.state_machine import AgentStateMachine

        s = TimelineStore(db_path=str(tmp_path / "many.db"))
        for i in range(200):
            s.record(TimelineEvent(timestamp=time.time(), event_type="x",
                                   source="s", entity_id=f"e{i}", title=f"row {i}"))
        monkeypatch.setattr(cw, "get_timeline_store", lambda: s)
        rows = AgentStateMachine.__new__(AgentStateMachine)._world_observations()
        assert 0 < len(rows) <= 20, "an idle day is thousands of rows"


class TestBothCallSitesPassThem:
    """Asserted on the source, because the alternative is standing up the
    whole turn machinery to prove one keyword argument is present.
    """

    def test_planning_passes_world_observations(self):
        import inspect
        from halbert_core.agents import state_machine

        src = inspect.getsource(state_machine.AgentStateMachine)
        assert "world_observations=self._world_observations()" in src, (
            "assemble() accepts the rows and PLANNING never sends any"
        )

    def test_both_render_points_are_fed(self):
        import inspect
        from halbert_core.agents import state_machine

        src = inspect.getsource(state_machine.AgentStateMachine)
        assert src.count("world_observations=self._world_observations()") >= 2, (
            "the block is sent on both LLM calls of a turn; grounding seen "
            "once is grounding half-used"
        )


class TestTheBlockSaysEachThingOnce:
    """A person arriving writes two rows -- the state change and the occupancy
    event -- and branch 1 gave them the same title. Rendered as-is the Eyes
    block reads "Sarah arrived home / Sarah arrived home", which a model can
    only take as two arrivals. Grounding that invents a repetition is worse
    than grounding that is missing.
    """

    def test_two_rows_describing_one_fact_render_once(self, tmp_path, monkeypatch):
        import halbert_core.integrations.cognition_wiring as cw
        from halbert_core.agents.state_machine import AgentStateMachine

        s = TimelineStore(db_path=str(tmp_path / "t.db"))
        now = time.time()
        s.record(TimelineEvent(timestamp=now, event_type="ha_state_change",
                               source="ha", entity_id="person.sarah",
                               title="Sarah arrived home"))
        s.record(TimelineEvent(timestamp=now, event_type="occupancy_change",
                               source="ha", entity_id="person.sarah",
                               title="Sarah arrived home"))
        monkeypatch.setattr(cw, "get_timeline_store", lambda: s)
        rows = AgentStateMachine.__new__(AgentStateMachine)._world_observations()
        assert len([r for r in rows if "Sarah arrived home" in r]) == 1

    def test_the_same_thing_happening_twice_still_shows_twice(self, tmp_path, monkeypatch):
        # Dedup must not eat a real recurrence: two arrivals an hour apart are
        # two facts, and collapsing them would hide exactly what the ledger is
        # for.
        import halbert_core.integrations.cognition_wiring as cw
        from halbert_core.agents.state_machine import AgentStateMachine

        s = TimelineStore(db_path=str(tmp_path / "t.db"))
        now = time.time()
        for offset in (0, -3600):
            s.record(TimelineEvent(timestamp=now + offset,
                                   event_type="occupancy_change", source="ha",
                                   entity_id="person.sarah",
                                   title="Sarah arrived home"))
        monkeypatch.setattr(cw, "get_timeline_store", lambda: s)
        rows = AgentStateMachine.__new__(AgentStateMachine)._world_observations()
        assert len([r for r in rows if "Sarah arrived home" in r]) == 2


class TestTheGroundingIsStableWithinATurn:
    """PLANNING and RESPONDING both call this, so an event landing between
    them would give the model different grounding in the two halves of one
    turn -- it would plan against a world that had changed by the time it
    answered, with no way to notice.
    """

    def test_the_second_call_in_a_turn_matches_the_first(self, tmp_path, monkeypatch):
        import halbert_core.integrations.cognition_wiring as cw
        from halbert_core.agents.state_machine import AgentStateMachine

        s = TimelineStore(db_path=str(tmp_path / "t.db"))
        s.record(TimelineEvent(timestamp=time.time(), event_type="x",
                               source="s", entity_id="a", title="first thing"))
        monkeypatch.setattr(cw, "get_timeline_store", lambda: s)

        m = AgentStateMachine.__new__(AgentStateMachine)
        planning = m._world_observations()

        # An event lands mid-turn, as one will.
        s.record(TimelineEvent(timestamp=time.time(), event_type="x",
                               source="s", entity_id="b", title="second thing"))

        assert m._world_observations() == planning

    def test_a_new_turn_sees_the_new_event(self, tmp_path, monkeypatch):
        import halbert_core.integrations.cognition_wiring as cw
        from halbert_core.agents.state_machine import AgentStateMachine

        s = TimelineStore(db_path=str(tmp_path / "t.db"))
        s.record(TimelineEvent(timestamp=time.time(), event_type="x",
                               source="s", entity_id="a", title="first thing"))
        monkeypatch.setattr(cw, "get_timeline_store", lambda: s)

        m = AgentStateMachine.__new__(AgentStateMachine)
        m._world_observations()
        s.record(TimelineEvent(timestamp=time.time(), event_type="x",
                               source="s", entity_id="b", title="second thing"))
        m._reset_world_observations()
        assert any("second thing" in r for r in m._world_observations())
