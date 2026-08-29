# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for HomeCognitiveLoop — the autonomous perception-reason-action tick."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from halbert_core.home.cognitive_loop import HomeCognitiveLoop, CognitiveTickResult
from halbert_core.integrations.home_assistant.autonomy_gate import AutonomyGate
from halbert_core.integrations.home_assistant.ha_governance import HAGovernancePolicy


@pytest.fixture
def gate():
    return AutonomyGate("observe", governance=HAGovernancePolicy())


@pytest.fixture
def ha_client():
    client = MagicMock()
    client.get_states = AsyncMock(return_value=[{"entity_id": "light.living_room", "state": "on"}])
    client.call_service = AsyncMock(return_value={})
    return client


@pytest.fixture
def ha_event_mapper():
    mapper = MagicMock()
    mapper._pending_events = [{"entity_id": "light.living_room", "domain": "light"}]
    mapper.populate_cognition = MagicMock()
    return mapper


@pytest.fixture
def cognition():
    cog = MagicMock()
    return cog


@pytest.fixture
def cognition_tick():
    tick = MagicMock(return_value=MagicMock(thought=None))
    return tick


class TestCognitiveLoopTick:
    """Test the single-tick behavior."""

    def test_tick_returns_result(self, gate, ha_client, ha_event_mapper, cognition, cognition_tick):
        loop = HomeCognitiveLoop(
            autonomy_gate=gate,
            ha_client=ha_client,
            ha_event_mapper=ha_event_mapper,
            cognition=cognition,
            cognition_tick=cognition_tick,
        )
        result = loop.tick()
        assert isinstance(result, CognitiveTickResult)
        assert result.error is None
        assert "ha_entities" in result.perceived

    def test_tick_flushes_events_to_cognition(self, gate, ha_event_mapper, cognition):
        loop = HomeCognitiveLoop(
            autonomy_gate=gate,
            ha_event_mapper=ha_event_mapper,
            cognition=cognition,
        )
        loop.tick()
        ha_event_mapper.populate_cognition.assert_called_once_with(cognition)

    def test_tick_runs_cognition_tick(self, gate, cognition, cognition_tick):
        loop = HomeCognitiveLoop(
            autonomy_gate=gate,
            cognition=cognition,
            cognition_tick=cognition_tick,
        )
        result = loop.tick()
        assert result.cognition_ticked is True

    def test_tick_without_cognition_does_not_crash(self, gate):
        loop = HomeCognitiveLoop(autonomy_gate=gate)
        result = loop.tick()
        assert result.cognition_ticked is False
        assert result.error is None

    def test_tick_with_no_ha_client_does_not_crash(self, gate):
        loop = HomeCognitiveLoop(autonomy_gate=gate)
        result = loop.tick()
        assert result.perceived["ha_entities"] == []


class TestCognitiveLoopAutonomy:
    """Test that the loop respects the autonomy gate."""

    def test_observe_blocks_all_actions(self, gate, ha_client):
        loop = HomeCognitiveLoop(
            autonomy_gate=gate,
            ha_client=ha_client,
        )
        # Inject a desired action manually
        loop._decide = lambda perceived: [
            {"domain": "light", "entity_id": "light.living_room", "service": "turn_off"}
        ]
        result = loop.tick()
        assert len(result.actions_blocked) == 1
        assert len(result.actions_executed) == 0
        assert len(result.actions_proposed) == 0

    def test_act_executes_level_0_actions(self, ha_client):
        gate = AutonomyGate("act", governance=HAGovernancePolicy())
        loop = HomeCognitiveLoop(
            autonomy_gate=gate,
            ha_client=ha_client,
        )
        loop._decide = lambda perceived: [
            {"domain": "light", "entity_id": "light.living_room", "service": "turn_off"}
        ]
        result = loop.tick()
        assert len(result.actions_executed) == 1
        assert len(result.actions_blocked) == 0

    def test_act_proposes_level_2_actions(self, ha_client):
        gate = AutonomyGate("act", governance=HAGovernancePolicy())
        loop = HomeCognitiveLoop(
            autonomy_gate=gate,
            ha_client=ha_client,
        )
        loop._decide = lambda perceived: [
            {"domain": "lock", "entity_id": "lock.front_door", "service": "unlock"}
        ]
        result = loop.tick()
        assert len(result.actions_proposed) == 1
        assert len(result.actions_executed) == 0

    def test_orchestrate_executes_level_2_with_cancel_window(self, ha_client):
        gate = AutonomyGate("orchestrate", governance=HAGovernancePolicy())
        loop = HomeCognitiveLoop(
            autonomy_gate=gate,
            ha_client=ha_client,
        )
        loop._decide = lambda perceived: [
            {"domain": "lock", "entity_id": "lock.front_door", "service": "unlock"}
        ]
        result = loop.tick()
        assert len(result.actions_executed) == 1
        # Check the decision had a cancel window
        executed = result.actions_executed[0]
        assert executed["decision"]["cancel_window_seconds"] == 30

    def test_level_3_always_blocked(self, ha_client):
        gate = AutonomyGate("orchestrate", governance=HAGovernancePolicy())
        loop = HomeCognitiveLoop(
            autonomy_gate=gate,
            ha_client=ha_client,
        )
        loop._decide = lambda perceived: [
            {"domain": "water_valve", "entity_id": "valve.main", "service": "close"}
        ]
        result = loop.tick()
        assert len(result.actions_blocked) == 1
        assert len(result.actions_executed) == 0


class TestCognitiveLoopStatus:
    """Test the status property."""

    def test_status_before_any_tick(self, gate):
        loop = HomeCognitiveLoop(autonomy_gate=gate)
        status = loop.status
        assert status["running"] is False
        assert status["tick_count"] == 0
        assert status["last_tick"] is None
        assert status["autonomy_level"] == "observe"

    def test_status_after_tick(self, gate, ha_client):
        loop = HomeCognitiveLoop(autonomy_gate=gate, ha_client=ha_client)
        loop.tick()
        status = loop.status
        assert status["tick_count"] == 1
        assert status["last_tick"] is not None
        assert status["last_tick"]["error"] is None


class TestCognitiveLoopStartStop:
    """Test start/stop behavior."""

    def test_start_and_stop(self, gate):
        loop = HomeCognitiveLoop(autonomy_gate=gate, interval_seconds=1)
        loop.start()
        assert loop.status["running"] is True
        loop.stop()
        assert loop.status["running"] is False

    def test_double_start_warns(self, gate):
        loop = HomeCognitiveLoop(autonomy_gate=gate, interval_seconds=60)
        loop.start()
        loop.start()  # should not crash, just warn
        loop.stop()
