# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SEC-9: the gate judges every entity the call actually touches.

Home Assistant takes its target from ``data["entity_id"]`` as readily as from a
separate argument. The gate read only the argument and the caller's ``data`` was
then merged on top, so the entity-level forbidden list — the only entity-level
check in the whole policy — was one dict key away from being decorative.
"""
from __future__ import annotations

import pytest

from halbert_core.integrations.home_assistant.autonomy_gate import (
    AutonomyGate,
    effective_entity_ids,
)
from halbert_core.integrations.home_assistant.ha_governance import HAGovernancePolicy


class TestEffectiveEntityIds:
    def test_argument_alone(self):
        assert effective_entity_ids("light.kitchen") == ["light.kitchen"]

    def test_data_alone(self):
        assert effective_entity_ids("", {"entity_id": "lock.front"}) == ["lock.front"]

    def test_union_of_both(self):
        assert effective_entity_ids(
            "light.kitchen", {"entity_id": "switch.life_support"}
        ) == ["light.kitchen", "switch.life_support"]

    def test_lists_are_flattened(self):
        """HA accepts a list of entity ids as readily as a string."""
        assert effective_entity_ids(
            ["light.a", "light.b"], {"entity_id": ["light.b", "lock.front"]}
        ) == ["light.a", "light.b", "lock.front"]

    def test_modern_target_spelling(self):
        assert effective_entity_ids(
            "", {"target": {"entity_id": "lock.front"}}
        ) == ["lock.front"]

    def test_ignores_junk(self):
        assert effective_entity_ids(None, {"entity_id": None, "brightness": 255}) == []
        assert effective_entity_ids("   ", {}) == []


class TestGateJudgesTheWholePayload:
    @pytest.fixture
    def gate(self):
        # `orchestrate` is the most permissive level, so anything that refuses
        # here refuses everywhere.
        return AutonomyGate(autonomy_level="orchestrate", governance=HAGovernancePolicy())

    def test_a_forbidden_entity_hidden_in_data_is_caught(self, gate):
        """The exploit, exactly as it was reachable.

        `switch.lamp` is a Level 0 switch; `switch.life_support` is on the
        forbidden entity list. Judged on the argument alone this was allowed and
        auto-executed against life support.
        """
        benign = gate.evaluate_call("switch", "switch.lamp", "turn_off")
        assert benign.allowed is True

        smuggled = gate.evaluate_call(
            "switch", "switch.lamp", "turn_off", {"entity_id": "switch.life_support"}
        )
        assert smuggled.allowed is False
        assert smuggled.governance_level == 3

    def test_the_old_path_would_have_allowed_it(self, gate):
        """Pin the difference, so nobody 'simplifies' evaluate_call back to evaluate."""
        old = gate.evaluate("switch", "switch.lamp", "turn_off")
        assert old.allowed is True  # what the caller used to ask

    def test_most_restrictive_target_wins(self, gate):
        d = gate.evaluate_call(
            "light", "light.kitchen", "turn_on", {"entity_id": ["light.hall", "switch.medical"]}
        )
        assert d.allowed is False

    def test_a_call_with_no_entity_is_still_judged_on_its_domain(self, gate):
        """`shell_command` needs no target to be arbitrary code execution."""
        d = gate.evaluate_call("shell_command", "", "run", {})
        assert d.allowed is False
        assert d.governance_level == 3

    def test_an_ordinary_call_is_unaffected(self, gate):
        d = gate.evaluate_call("light", "light.kitchen", "turn_on", {"brightness": 200})
        assert d.allowed is True
        assert d.auto_execute is True


class TestUnresolvableTargets:
    """Ways a call names a target the gate cannot check.

    The first version of this fix read `entity_id` and `target.entity_id` and
    stopped there. Home Assistant's `cv.make_entity_service_schema` merges
    device_id, area_id, floor_id and label_id into *every* entity service schema,
    and `ha_client` POSTs `data` verbatim as the service body — so the gate was
    judging a field the call would not act on.
    """

    @pytest.fixture
    def gate(self):
        return AutonomyGate(autonomy_level="orchestrate", governance=HAGovernancePolicy())

    def test_entity_match_all_is_refused(self, gate):
        """`entity_id: "all"` is HA's ENTITY_MATCH_ALL — every entity of the platform.

        It starts with none of the forbidden entity prefixes, so it walked past
        them: `switch.turn_off` with `{"entity_id": "all"}` at `act` autonomy
        turned off every switch in the house, including switch.life_support.
        """
        d = gate.evaluate_call("switch", "", "turn_off", {"entity_id": "all"})
        assert d.allowed is False
        assert d.auto_execute is False

    @pytest.mark.parametrize("key", ["device_id", "area_id", "floor_id", "label_id"])
    def test_registry_selectors_are_refused(self, gate, key):
        d = gate.evaluate_call("switch", "", "turn_off", {key: "abc123"})
        assert d.allowed is False, f"{key} should not be waved through"
        assert d.auto_execute is False

    @pytest.mark.parametrize("key", ["device_id", "area_id"])
    def test_registry_selectors_inside_target_are_refused(self, gate, key):
        d = gate.evaluate_call("switch", "", "turn_off", {"target": {key: "abc123"}})
        assert d.allowed is False
        assert d.auto_execute is False

    def test_case_does_not_defeat_the_forbidden_list(self, gate):
        """HA matches entity ids case-insensitively; the gate did not."""
        d = gate.evaluate_call("switch", "Switch.Life_Support", "turn_off")
        assert d.allowed is False

    def test_a_named_entity_still_works(self, gate):
        """The refusal must not swallow the ordinary case."""
        d = gate.evaluate_call("light", "light.kitchen", "turn_on", {"brightness": 200})
        assert d.allowed is True
        assert d.auto_execute is True

    def test_an_empty_selector_is_not_treated_as_present(self, gate):
        """`{"area_id": ""}` names nothing and must not refuse a valid call."""
        d = gate.evaluate_call("light", "light.kitchen", "turn_on", {"area_id": ""})
        assert d.allowed is True
