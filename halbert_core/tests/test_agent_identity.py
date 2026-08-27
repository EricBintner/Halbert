# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Layer-1 identity: Halbert is the machine, not a generic assistant.

All three voices used to open "You are Halbert, a helpful AI assistant for
Linux system administration", so a greeting came back sounding like any other
chatbot — on a host that is frequently not Linux.
"""

from unittest.mock import patch

import pytest

from halbert_core.prompts.agent_prompts import AgentPromptBuilder


VOICES = ("first_person", "the_computer", "hybrid")


@pytest.mark.parametrize("voice", VOICES)
def test_identity_is_not_a_generic_assistant(voice):
    identity = AgentPromptBuilder(voice=voice)._get_identity()
    assert "AI assistant" not in identity
    assert "Halbert" in identity


@pytest.mark.parametrize("voice", VOICES)
def test_identity_does_not_hardcode_linux(voice):
    with patch(
        "halbert_core.utils.platform.get_platform_name_friendly",
        return_value="macOS (Apple Silicon)",
    ):
        identity = AgentPromptBuilder(voice=voice)._get_identity()
    assert "macOS (Apple Silicon)" in identity
    assert "Linux" not in identity


@pytest.mark.parametrize("voice", VOICES)
def test_identity_survives_platform_detection_failure(voice):
    with patch(
        "halbert_core.utils.platform.get_platform_name_friendly",
        side_effect=OSError("no /etc/os-release"),
    ):
        identity = AgentPromptBuilder(voice=voice)._get_identity()
    # Neutral wording, no unsubstituted placeholder, and no doubled article
    # from a filler value ("this this machine").
    assert "{platform}" not in identity
    assert "You live on this machine" in identity


class TestVoicesStayDistinct:

    def test_first_person_claims_the_body(self):
        identity = AgentPromptBuilder(voice="first_person")._get_identity()
        assert "You ARE the machine" in identity
        assert "your CPU is how you think" in identity

    def test_the_computer_voice_is_not_self_contradictory(self):
        """This voice watches over the machine; it must not also be told its
        own CPU is how it thinks."""
        identity = AgentPromptBuilder(voice="the_computer")._get_identity()
        assert "third person" in identity
        assert "your CPU is how you think" not in identity
        assert "its CPU is how it thinks" in identity

    def test_hybrid_splits_subjective_and_objective(self):
        identity = AgentPromptBuilder(voice="hybrid")._get_identity()
        assert "subjective experience" in identity
        assert "objective technical facts" in identity

    def test_unknown_voice_falls_back_to_first_person(self):
        builder = AgentPromptBuilder()
        builder.voice = "nonsense"
        assert builder._get_identity() == AgentPromptBuilder(
            voice="first_person"
        )._get_identity()


class TestRespondingFallback:
    """RESPONDING has its own prompt for when the builder failed to wire.

    Rewritten (P6) from main's version, which drove
    ``handlers/responding.py``: Plan A deleted the handlers package, so the
    class it tested no longer exists and the invariant it named — a wiring
    failure must not silently change who Halbert says it is — moved onto the
    state machine's own ``_build_simple_response_prompt``, which is the path
    that is actually reached now. The assertions are main's.
    """

    def _agent(self, prompt_builder):
        from halbert_core.agents.state_machine import AgentStateMachine
        from halbert_core.agents.states import StateContext

        agent = AgentStateMachine(llm_client=None, prompt_builder=prompt_builder)
        agent.ctx = StateContext(
            session_id="s", request_id="r", user_query="what is running?"
        )
        return agent

    def test_fallback_is_not_a_generic_assistant(self):
        prompt = self._agent(None)._build_simple_response_prompt()
        assert "AI assistant" not in prompt
        assert "Halbert" in prompt
        assert prompt.index("Halbert") < prompt.index("what is running?")

    def test_builder_is_preferred_when_wired(self):
        """A wired builder means the fallback is never reached at all."""
        from unittest.mock import MagicMock

        builder = MagicMock()
        builder.build_response_prompt.return_value = "WIRED"
        agent = self._agent(builder)
        assert agent.prompts is builder
        assert agent._build_simple_response_prompt() != "WIRED"  # not this path

    def test_fallback_survives_a_broken_prompts_package(self):
        with patch(
            "halbert_core.prompts.agent_prompts.AgentPromptBuilder._get_identity",
            side_effect=RuntimeError("boom"),
        ):
            prompt = self._agent(None)._build_simple_response_prompt()
        assert "Halbert" in prompt
        assert "AI assistant" not in prompt
