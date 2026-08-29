# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for AutonomyGate — the autonomy slider enforcement layer."""

import pytest
from halbert_core.integrations.home_assistant.autonomy_gate import (
    AutonomyGate,
    AutonomyDecision,
)
from halbert_core.integrations.home_assistant.ha_governance import HAGovernancePolicy


@pytest.fixture
def governance():
    return HAGovernancePolicy()


class TestAutonomyGateObserve:
    """At 'observe', nothing executes — not even safe lights."""

    def test_light_blocked_at_observe(self, governance):
        gate = AutonomyGate("observe", governance=governance)
        d = gate.evaluate("light", "light.living_room", "turn_on")
        assert not d.allowed
        assert not d.auto_execute
        assert not d.requires_proposal

    def test_climate_blocked_at_observe(self, governance):
        gate = AutonomyGate("observe", governance=governance)
        d = gate.evaluate("climate", "climate.thermostat", "set_temperature")
        assert not d.allowed

    def test_lock_blocked_at_observe(self, governance):
        gate = AutonomyGate("observe", governance=governance)
        d = gate.evaluate("lock", "lock.front_door", "unlock")
        assert not d.allowed


class TestAutonomyGateSuggest:
    """At 'suggest', everything becomes a proposal — nothing auto-executes."""

    def test_light_proposed_at_suggest(self, governance):
        gate = AutonomyGate("suggest", governance=governance)
        d = gate.evaluate("light", "light.living_room", "turn_on")
        assert d.allowed
        assert not d.auto_execute
        assert d.requires_proposal

    def test_lock_proposed_at_suggest(self, governance):
        gate = AutonomyGate("suggest", governance=governance)
        d = gate.evaluate("lock", "lock.front_door", "unlock")
        assert d.allowed
        assert not d.auto_execute
        assert d.requires_proposal


class TestAutonomyGateAct:
    """At 'act', Level 0/1 auto-execute, Level 2 becomes a proposal."""

    def test_light_auto_executes_at_act(self, governance):
        gate = AutonomyGate("act", governance=governance)
        d = gate.evaluate("light", "light.living_room", "turn_on")
        assert d.allowed
        assert d.auto_execute
        assert not d.requires_proposal
        assert d.governance_level == 0

    def test_climate_auto_executes_at_act(self, governance):
        gate = AutonomyGate("act", governance=governance)
        d = gate.evaluate("climate", "climate.thermostat", "set_temperature")
        assert d.allowed
        assert d.auto_execute
        assert not d.requires_proposal
        assert d.governance_level == 1

    def test_lock_proposed_at_act(self, governance):
        gate = AutonomyGate("act", governance=governance)
        d = gate.evaluate("lock", "lock.front_door", "unlock")
        assert d.allowed
        assert not d.auto_execute
        assert d.requires_proposal
        assert d.governance_level == 2


class TestAutonomyGateOrchestrate:
    """At 'orchestrate', Level 0/1/2 auto-execute, Level 3 forbidden."""

    def test_light_auto_executes_at_orchestrate(self, governance):
        gate = AutonomyGate("orchestrate", governance=governance)
        d = gate.evaluate("light", "light.living_room", "turn_on")
        assert d.allowed
        assert d.auto_execute
        assert d.cancel_window_seconds == 0

    def test_lock_auto_executes_with_cancel_window(self, governance):
        gate = AutonomyGate("orchestrate", governance=governance)
        d = gate.evaluate("lock", "lock.front_door", "unlock")
        assert d.allowed
        assert d.auto_execute
        assert d.cancel_window_seconds == 30
        assert d.governance_level == 2

    def test_water_valve_forbidden_at_orchestrate(self, governance):
        gate = AutonomyGate("orchestrate", governance=governance)
        d = gate.evaluate("water_valve", "valve.main", "close")
        assert not d.allowed
        assert d.governance_level == 3


class TestAutonomyGateOverrides:
    """Per-domain overrides take precedence over global level."""

    def test_lock_override_to_suggest_at_orchestrate(self, governance):
        gate = AutonomyGate(
            "orchestrate",
            autonomy_overrides={"lock": "suggest"},
            governance=governance,
        )
        d = gate.evaluate("lock", "lock.front_door", "unlock")
        assert d.allowed
        assert not d.auto_execute
        assert d.requires_proposal

    def test_climate_override_to_observe_at_act(self, governance):
        gate = AutonomyGate(
            "act",
            autonomy_overrides={"climate": "observe"},
            governance=governance,
        )
        d = gate.evaluate("climate", "climate.thermostat", "set_temperature")
        assert not d.allowed

    def test_light_override_to_orchestrate_at_observe(self, governance):
        gate = AutonomyGate(
            "observe",
            autonomy_overrides={"light": "orchestrate"},
            governance=governance,
        )
        d = gate.evaluate("light", "light.living_room", "turn_on")
        assert d.allowed
        assert d.auto_execute


class TestAutonomyGateForbidden:
    """Level 3 is always forbidden regardless of autonomy level."""

    @pytest.mark.parametrize("level", ["observe", "suggest", "act", "orchestrate"])
    def test_water_valve_always_forbidden(self, governance, level):
        gate = AutonomyGate(level, governance=governance)
        d = gate.evaluate("water_valve", "valve.main", "close")
        assert not d.allowed
        assert d.governance_level == 3

    @pytest.mark.parametrize("level", ["observe", "suggest", "act", "orchestrate"])
    def test_freezer_entity_always_forbidden(self, governance, level):
        gate = AutonomyGate(level, governance=governance)
        d = gate.evaluate("switch", "switch.freezer", "turn_off")
        assert not d.allowed
        assert d.governance_level == 3


class TestAutonomyGateUpdate:
    """Runtime level updates work."""

    def test_update_level_changes_behavior(self, governance):
        gate = AutonomyGate("observe", governance=governance)
        d1 = gate.evaluate("light", "light.living_room", "turn_on")
        assert not d1.allowed

        gate.update_level("act")
        d2 = gate.evaluate("light", "light.living_room", "turn_on")
        assert d2.allowed
        assert d2.auto_execute
