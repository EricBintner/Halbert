# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The identity leads ``messages[0]`` on every turn.

Alignment audit 2026-09-02, C1-01: ``AgentPromptBuilder.build_system_prompt``
held the per-voice identity but had no caller, so neither the PLANNING nor
the RESPONDING message ever told the model who it was — only the receipt and
continuity machinery reached it. C1-03 / W1-03 / W4-06: ``body_name`` and
``purpose`` reached config and the UI but never the prompt. C1-04: the voice
setting was live only in the continuity preamble, which renders only when a
hint exists. T1-01: the shipped XML prompt still called Halbert an
"assistant" and a "sentient consciousness".

These tests construct the state machine the way ``routes/agent.py::get_agent``
does — an ``AgentPromptBuilder`` over a ``BeingConfig`` — drive one real turn,
and read the arrays the LLM was actually sent.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from halbert_core.agents.llm_client import LLMResponse
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.states import StateContext
from halbert_core.config.being_config import BeingConfig
from halbert_core.prompts.agent_prompts import AgentPromptBuilder


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / "config" / "prompts"


class _RecordingLLM:
    """Answers directly (no tool calls) and keeps every messages[] array.

    One turn is exactly two calls: PLANNING via ``chat`` and RESPONDING via
    ``stream``, in that order.
    """

    tools_supported = None

    def __init__(self):
        self.seen = []

    async def chat(self, messages, tools=None, **kwargs):
        self.seen.append([dict(m) for m in messages])
        return LLMResponse(content="answer", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        self.seen.append([dict(m) for m in messages])
        yield "answer"


def _cfg(**overrides) -> BeingConfig:
    cfg = BeingConfig(
        name="Titan", voice="the_computer", body_name="desk", purpose="home NAS",
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _builder(cfg) -> AgentPromptBuilder:
    """The shape ``get_agent`` builds: voice from the config, config in hand."""
    voice = cfg.voice if cfg is not None else "first_person"
    return AgentPromptBuilder(
        base_builder=None, context_injector=None, voice=voice, being_cfg=cfg,
    )


def _agent(llm, cfg, **kw) -> AgentStateMachine:
    return AgentStateMachine(
        llm_client=llm, prompt_builder=_builder(cfg), max_loops=2, **kw,
    )


async def _turn(agent, query="what is running?"):
    async for _ in agent.process(query, session_id="identity"):
        pass


def _planning_and_responding(llm):
    assert len(llm.seen) == 2, [len(a) for a in llm.seen]
    planning, responding = llm.seen
    assert planning[0]["role"] == "system"
    assert responding[0]["role"] == "system"
    return planning[0]["content"], responding[0]["content"]


# ---------------------------------------------------------------------------
# The block itself
# ---------------------------------------------------------------------------

class TestBuildIdentityBlock:

    def test_leads_with_the_voice_identity(self):
        block = _builder(_cfg()).build_identity_block()
        assert block.startswith("You are Titan.")
        assert "third person" in block
        assert "its CPU is how it thinks" in block

    def test_first_person_is_i_form(self):
        block = _builder(_cfg(voice="first_person")).build_identity_block()
        assert block.startswith("You are Titan.")
        assert 'You speak in first person: "I", "my", "me". You ARE the machine.' in block
        assert "You are currently at your desk body" in block

    def test_body_line_names_body_and_hostname(self):
        with patch("platform.node", return_value="titan-01"):
            block = _builder(_cfg()).build_identity_block()
        assert "desk body (titan-01)" in block

    def test_the_computer_body_line_is_third_person(self):
        with patch("platform.node", return_value="titan-01"):
            block = _builder(_cfg()).build_identity_block()
        assert "This machine is the desk body (titan-01)." in block
        assert "your desk body" not in block

    def test_body_line_survives_an_empty_hostname(self):
        with patch("platform.node", return_value=""):
            block = _builder(_cfg(voice="first_person")).build_identity_block()
        assert "You are currently at your desk body." in block
        assert "()" not in block

    def test_purpose_line(self):
        block = _builder(_cfg()).build_identity_block()
        assert "This machine's purpose: home NAS." in block

    def test_purpose_trailing_period_is_not_doubled(self):
        block = _builder(_cfg(purpose="home NAS.")).build_identity_block()
        assert "home NAS." in block
        assert "home NAS.." not in block

    def test_no_body_no_purpose_no_lines(self):
        block = _builder(_cfg(body_name="", purpose="")).build_identity_block()
        assert "currently at" not in block
        assert "This machine is the" not in block
        assert "purpose" not in block

    def test_no_config_is_the_bare_identity(self):
        builder = AgentPromptBuilder()
        assert builder.build_identity_block() == builder._get_identity()
        assert builder.build_identity_block().startswith("You are Halbert.")

    def test_singular_mode_names_the_canonical_host(self):
        cfg = _cfg(
            voice="first_person",
            canonical_memory_url="http://n150.lan:8001/api/memory",
            persona_id_override="halbert",
        )
        block = _builder(cfg).build_identity_block()
        assert "n150.lan" in block
        assert "more than one body" in block

    def test_singular_mode_the_computer_is_third_person(self):
        cfg = _cfg(
            canonical_memory_url="http://n150.lan:8001/api/memory",
            persona_id_override="halbert",
        )
        block = _builder(cfg).build_identity_block()
        assert "n150.lan" in block
        assert "your memory" not in block

    def test_singular_mode_without_a_body_name_still_has_a_subject(self):
        cfg = _cfg(
            body_name="",
            canonical_memory_url="http://n150.lan:8001/api/memory",
            persona_id_override="halbert",
        )
        block = _builder(cfg).build_identity_block()
        assert "This machine is one body of a single entity" in block
        assert "n150.lan" in block

    def test_independent_mode_has_no_canonical_line(self):
        block = _builder(_cfg()).build_identity_block()
        assert "canonical" not in block
        assert "more than one body" not in block

    def test_personality_sits_between_identity_and_body(self):
        cfg = _cfg(custom_personality_prompt="Dry, terse, never chirpy.")
        block = _builder(cfg).build_identity_block()
        assert block.index("You are Titan.") < block.index("Dry, terse, never chirpy.")
        assert block.index("Dry, terse, never chirpy.") < block.index("desk body")

    def test_stays_short(self):
        # A few hundred characters of who/where/why, not a second prompt.
        block = _builder(_cfg()).build_identity_block()
        assert len(block) < 1200, len(block)

    def test_purpose_is_one_line_and_capped(self):
        cfg = _cfg(purpose="a\n\nvery " + ("long " * 200))
        block = _builder(cfg).build_identity_block()
        line = next(l for l in block.splitlines() if l.startswith("This machine's purpose"))
        assert "\n" not in line
        assert len(line) < 300
        assert not line.endswith("…."), line


# ---------------------------------------------------------------------------
# The block leads messages[0] on both LLM calls of a turn
# ---------------------------------------------------------------------------

class TestIdentityLeadsEveryTurn:

    @pytest.mark.asyncio
    async def test_the_computer_leads_planning_and_responding(self):
        llm = _RecordingLLM()
        with patch("platform.node", return_value="titan-01"):
            await _turn(_agent(llm, _cfg()))
        planning, responding = _planning_and_responding(llm)
        for content in (planning, responding):
            assert content.startswith("You are Titan."), content[:120]
            assert "third person" in content
            assert "desk body (titan-01)" in content
            assert "This machine's purpose: home NAS." in content
        # Ahead of the planning / response prose, not behind it.
        assert planning.index("Titan") < planning.index("## Current Task")
        assert responding.index("Titan") < responding.index("Answer this question")

    @pytest.mark.asyncio
    async def test_first_person_leads_both(self):
        llm = _RecordingLLM()
        await _turn(_agent(llm, _cfg(voice="first_person")))
        planning, responding = _planning_and_responding(llm)
        for content in (planning, responding):
            assert content.startswith("You are Titan.")
            assert "You ARE the machine" in content
            assert "You are currently at your desk body" in content

    def test_identity_precedes_prompt_and_receipt_block(self):
        agent = _agent(_RecordingLLM(), _cfg())
        agent.ctx = StateContext(
            session_id="s", request_id="r", user_query="continue",
            thread_receipt_block="## Earlier in this subject\nTitle: Samba",
        )
        content = agent._build_messages("INSTRUCTIONS")[0]["content"]
        assert content.startswith("You are Titan.")
        assert content.index("Titan") < content.index("INSTRUCTIONS")
        assert content.index("INSTRUCTIONS") < content.index("Earlier in this subject")

    def test_no_builder_keeps_the_instructions_as_is(self):
        """The Wyoming/embedder shape: prompt_builder=None. RESPONDING's own
        fallback already leads with ``_fallback_identity``; nothing is
        prepended here so that path is not doubled."""
        agent = AgentStateMachine(llm_client=_RecordingLLM(), max_loops=2)
        agent.ctx = StateContext(session_id="s", request_id="r", user_query="q")
        assert agent._build_messages("INSTRUCTIONS")[0]["content"] == "INSTRUCTIONS"

    def test_a_builder_without_the_hook_is_tolerated(self):
        """A test double or an out-of-tree builder that does not render an
        identity block must not break the turn."""
        prompts = MagicMock()
        agent = AgentStateMachine(
            llm_client=_RecordingLLM(), prompt_builder=prompts, max_loops=2,
        )
        agent.ctx = StateContext(session_id="s", request_id="r", user_query="q")
        assert agent._build_messages("INSTRUCTIONS")[0]["content"] == "INSTRUCTIONS"

    def test_a_failing_block_does_not_end_the_turn(self):
        agent = _agent(_RecordingLLM(), _cfg())
        agent.ctx = StateContext(session_id="s", request_id="r", user_query="q")
        with patch.object(
            AgentPromptBuilder, "build_identity_block", side_effect=RuntimeError("boom"),
        ):
            content = agent._build_messages("INSTRUCTIONS")[0]["content"]
        assert content == "INSTRUCTIONS"

    @pytest.mark.asyncio
    async def test_voice_change_is_live_on_the_next_turn(self):
        """C1-04: the settings and persona routes hot-reload through
        ``agent.prompt_builder``; the state machine keeps the builder as
        ``self.prompts``, so that name must resolve to the same object."""
        llm = _RecordingLLM()
        agent = _agent(llm, _cfg())
        assert agent.prompt_builder is agent.prompts

        with patch(
            "halbert_core.config.being_config.load_being_config",
            return_value=_cfg(voice="first_person"),
        ):
            agent.prompt_builder.reload_personality()
        await _turn(agent)
        planning, responding = _planning_and_responding(llm)
        for content in (planning, responding):
            assert "You ARE the machine" in content
            assert "third person" not in content
