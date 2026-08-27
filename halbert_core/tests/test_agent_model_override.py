# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Per-turn model and tier override on the agent request path (E-2).

The in-chat picker had no way to reach the backend: SendMessageRequest carried
no model field, and the complexity router would have overridden any choice the
user made. These cover the override reaching the adapter *as a parameter* —
never as state on the process-wide shared adapter — and bypassing the router.
"""

import pytest
from unittest.mock import patch

pytest.importorskip("fastapi")

from halbert_core.agents.states import StateContext
from halbert_core.dashboard.routes import agent as agent_routes
from halbert_core.dashboard.routes.agent import (
    SendMessageRequest,
    _resolve_turn_model,
)

GUIDE = ("guide-model", "http://localhost:11434", "ollama")
SPECIALIST = ("specialist-model", "https://api.cloud.test", "openai")
VISION = ("vision-model", "http://localhost:11434", "ollama")

TRIVIAL = "hi"
# Long, multi-clause, keyword-heavy: scores above the 0.5 legacy threshold.
COMPLEX = (
    "diagnose why the nginx service failed to restart after the certificate "
    "renewal hook ran, then analyse the systemd journal and explain the root "
    "cause step by step and recommend how to troubleshoot and optimize it"
)


@pytest.fixture
def slots(monkeypatch):
    """Install the three configured slots; returns a mutator for each."""
    state = {"guide": GUIDE, "specialist": SPECIALIST, "vision": VISION,
             "endpoints": {}}
    import halbert_core.model.client as client

    monkeypatch.setattr(client, "get_configured_model",
                        lambda: state["guide"][0] if state["guide"] else "")
    monkeypatch.setattr(client, "get_ollama_endpoint",
                        lambda: state["guide"][1] if state["guide"] else "http://localhost:11434")
    monkeypatch.setattr(client, "get_specialist_model",
                        lambda: state["specialist"] or (None, None, None))
    monkeypatch.setattr(client, "get_vision_model",
                        lambda: state["vision"] or (None, "http://localhost:11434", "ollama"))
    monkeypatch.setattr(client, "provider_for",
                        lambda url, default="ollama":
                            state["guide"][2] if state["guide"] and url == state["guide"][1] else default)
    monkeypatch.setattr(client, "resolve_endpoint_by_id",
                        lambda eid: state["endpoints"].get(eid))
    return state


class _Intake:
    def __init__(self, recommended_model):
        self.recommended_model = recommended_model


# -----------------------------------------------------------------------------
# Precedence
# -----------------------------------------------------------------------------

class TestPrecedence:

    def test_model_pin_wins_over_tier_pin(self, slots):
        turn = _resolve_turn_model(
            TRIVIAL, model_override="pinned-x", tier_override="specialist")
        assert turn.model == "pinned-x"
        assert turn.pinned is True

    def test_tier_pin_wins_over_automatic_routing(self, slots):
        turn = _resolve_turn_model(TRIVIAL, tier_override="specialist")
        assert turn.model == SPECIALIST[0]
        assert turn.tier == "specialist"
        assert turn.pinned is True

    def test_no_override_uses_automatic_routing(self, slots):
        turn = _resolve_turn_model(TRIVIAL)
        assert turn.model == GUIDE[0]
        assert turn.pinned is False


# -----------------------------------------------------------------------------
# V-04: a pin must bypass the complexity router
# -----------------------------------------------------------------------------

class TestPinBypassesRouter:

    def test_complex_query_does_not_escalate_when_a_model_is_pinned(self, slots):
        """The V-04 gate. A user who pins a local model must never find that a
        cloud specialist answered and billed them."""
        unpinned = _resolve_turn_model(COMPLEX)
        assert unpinned.model == SPECIALIST[0], "fixture must actually escalate"
        assert unpinned.escalated is True

        pinned = _resolve_turn_model(COMPLEX, model_override="local-small")
        assert pinned.model == "local-small"
        assert pinned.escalated is False

    def test_complex_query_does_not_escalate_when_the_guide_tier_is_pinned(self, slots):
        turn = _resolve_turn_model(COMPLEX, tier_override="guide")
        assert turn.model == GUIDE[0]
        assert turn.escalated is False

    def test_intake_recommendation_is_ignored_under_a_pin(self, slots):
        turn = _resolve_turn_model(
            TRIVIAL, intake_result=_Intake("specialist"),
            model_override="local-small")
        assert turn.model == "local-small"

    def test_images_do_not_force_vision_under_a_model_pin(self, slots):
        turn = _resolve_turn_model(
            TRIVIAL, images=["b64"], model_override="local-small")
        assert turn.model == "local-small"
        assert turn.tier != "vision"


# -----------------------------------------------------------------------------
# Where a pinned model lives
# -----------------------------------------------------------------------------

class TestPinnedEndpointResolution:

    def test_endpoint_id_is_authoritative(self, slots):
        slots["endpoints"]["ep-9"] = ("https://exact.test", "openai-compatible", "sk")
        turn = _resolve_turn_model(
            TRIVIAL, model_override="m", endpoint_id="ep-9")
        assert turn.endpoint == "https://exact.test"
        assert turn.provider == "openai-compatible"

    def test_pinning_the_specialist_model_by_name_finds_its_endpoint(self, slots):
        turn = _resolve_turn_model(TRIVIAL, model_override=SPECIALIST[0])
        assert turn.endpoint == SPECIALIST[1]
        assert turn.provider == SPECIALIST[2]

    def test_pinning_the_vision_model_by_name_finds_its_endpoint(self, slots):
        slots["vision"] = ("vm", "https://vision.test", "openai")
        turn = _resolve_turn_model(TRIVIAL, model_override="vm")
        assert turn.endpoint == "https://vision.test"

    def test_an_unknown_model_defaults_to_the_guide_endpoint(self, slots):
        """The common case: a second model pulled on the same local runtime."""
        turn = _resolve_turn_model(TRIVIAL, model_override="qwen-other")
        assert turn.endpoint == GUIDE[1]
        assert turn.provider == GUIDE[2]

    def test_an_unknown_endpoint_id_falls_back_to_name_matching(self, slots):
        turn = _resolve_turn_model(
            TRIVIAL, model_override=SPECIALIST[0], endpoint_id="ep-missing")
        assert turn.endpoint == SPECIALIST[1]


# -----------------------------------------------------------------------------
# Tier pins
# -----------------------------------------------------------------------------

class TestTierPins:

    def test_vision_tier_forces_the_vision_model_without_images(self, slots):
        turn = _resolve_turn_model(TRIVIAL, tier_override="vision")
        assert turn.model == VISION[0]
        assert turn.tier == "vision"

    def test_specialist_tier_falls_back_to_guide_when_unconfigured(self, slots):
        slots["specialist"] = None
        turn = _resolve_turn_model(TRIVIAL, tier_override="specialist")
        assert turn.model == GUIDE[0]
        assert turn.tier == "guide"
        assert turn.pinned is True

    def test_vision_tier_falls_back_to_guide_when_unconfigured(self, slots):
        slots["vision"] = None
        turn = _resolve_turn_model(TRIVIAL, tier_override="vision")
        assert turn.model == GUIDE[0]

    @pytest.mark.parametrize("bogus", ["auto", "", "GUIDE", "fast", None])
    def test_an_unrecognised_tier_is_treated_as_no_pin(self, slots, bogus):
        turn = _resolve_turn_model(COMPLEX, tier_override=bogus)
        assert turn.pinned is False
        assert turn.escalated is True


# -----------------------------------------------------------------------------
# Automatic routing is unchanged
# -----------------------------------------------------------------------------

class TestAutomaticRouting:

    def test_intake_recommendation_selects_the_specialist(self, slots):
        turn = _resolve_turn_model(TRIVIAL, intake_result=_Intake("specialist"))
        assert turn.model == SPECIALIST[0]
        assert turn.escalated is True

    def test_intake_guide_recommendation_stays_on_the_guide(self, slots):
        turn = _resolve_turn_model(COMPLEX, intake_result=_Intake("guide"))
        assert turn.model == GUIDE[0]

    def test_images_route_to_vision(self, slots):
        turn = _resolve_turn_model(TRIVIAL, images=["b64"])
        assert turn.tier == "vision"
        assert turn.model == VISION[0]

    def test_images_fall_through_to_text_when_no_vision_model(self, slots):
        slots["vision"] = None
        turn = _resolve_turn_model(TRIVIAL, images=["b64"])
        assert turn.tier == "guide"

    def test_legacy_complexity_routing_when_intake_is_absent(self, slots):
        assert _resolve_turn_model(TRIVIAL).tier == "guide"
        assert _resolve_turn_model(COMPLEX).tier == "specialist"

    def test_no_specialist_means_no_escalation(self, slots):
        slots["specialist"] = None
        turn = _resolve_turn_model(COMPLEX)
        assert turn.model == GUIDE[0]
        assert turn.escalated is False

    def test_the_reason_is_populated_for_the_handoff_banner(self, slots):
        assert _resolve_turn_model(COMPLEX).reason
        assert _resolve_turn_model(TRIVIAL, model_override="x").reason


class TestNoModelConfigured:

    def test_raises_a_400_the_ui_can_render(self, slots):
        from fastapi import HTTPException
        slots["guide"] = None
        with pytest.raises(HTTPException) as exc:
            _resolve_turn_model(TRIVIAL)
        assert exc.value.status_code == 400
        assert "Settings" in exc.value.detail

    def test_a_pin_still_works_with_no_guide_configured(self, slots):
        """Pinning is itself a configuration act; it must not require the
        guide slot to be filled first."""
        slots["guide"] = None
        turn = _resolve_turn_model(TRIVIAL, model_override="pinned")
        assert turn.model == "pinned"


# -----------------------------------------------------------------------------
# The request/context plumbing
# -----------------------------------------------------------------------------

class TestRequestSchema:

    def test_accepts_the_picker_fields(self):
        req = SendMessageRequest(
            message="hi", model="m", tier="specialist", endpoint_id="ep-1")
        assert (req.model, req.tier, req.endpoint_id) == ("m", "specialist", "ep-1")

    def test_fields_default_to_none_so_existing_clients_are_unaffected(self):
        req = SendMessageRequest(message="hi")
        assert req.model is None and req.tier is None and req.endpoint_id is None


class TestStateContextCarriesTheOverride:

    def test_fields_exist_and_default_to_none(self):
        ctx = StateContext(session_id="s", request_id="r", user_query="q")
        assert ctx.model_override is None
        assert ctx.tier_override is None

    def test_override_is_not_stored_on_the_shared_adapter(self):
        """One LLMClientAdapter serves every concurrent request, so a model
        stored on it would leak across sessions."""
        adapter = agent_routes.LLMClientAdapter()
        assert not hasattr(adapter, "model_override")
        assert not hasattr(adapter, "tier_override")
        assert not hasattr(adapter, "last_turn")

    @pytest.mark.parametrize("method", ["chat", "stream"])
    def test_both_adapter_methods_take_the_override_as_a_parameter(self, method):
        import inspect
        params = inspect.signature(
            getattr(agent_routes.LLMClientAdapter, method)).parameters
        assert "model_override" in params
        assert "tier_override" in params
        assert "endpoint_id" in params

    def test_mock_client_tolerates_the_new_kwargs(self):
        import inspect
        for method in ("chat", "stream"):
            sig = inspect.signature(getattr(agent_routes.MockLLMClient, method))
            assert any(p.kind is inspect.Parameter.VAR_KEYWORD
                       for p in sig.parameters.values()), method


class TestStateMachineForwarding:

    def test_process_accepts_and_stores_the_override(self):
        import inspect
        from halbert_core.agents.state_machine import AgentStateMachine
        params = inspect.signature(AgentStateMachine.process).parameters
        assert "model_override" in params
        assert "tier_override" in params

    def test_crag_evaluate_accepts_the_override(self):
        """CRAG shares the adapter; without this a pin would not stop its
        completeness check escalating to the specialist."""
        import inspect
        from halbert_core.eval.crag import CRAGEvaluator
        params = inspect.signature(CRAGEvaluator.evaluate).parameters
        assert "model_override" in params
        assert "tier_override" in params
