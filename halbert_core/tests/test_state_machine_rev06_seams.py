# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""REV-06 prompt-assembly seams.

Two regressions lived where the turn's prompt is assembled, and both are
invisible to the dashboard's happy path — which is why they shipped:

* ``R06-F2``: the response modality was resolved inside the "we have a prompt
  builder" arm but read by both arms, so every turn taken by a state machine
  built without one (Wyoming voice, any non-dashboard embedder) died with an
  UnboundLocalError in RESPONDING.
* ``R06-F1``: the defanged query was reset at the *start of RESPONDING* rather
  than at the start of the turn, so turn N+1 planned against turn N's
  question for the whole stretch between PLANNING and RESPONDING.

Both are guarded here by intent, not as a side effect of some other assertion.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from halbert_core.agents.state_machine import AgentStateMachine


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _mk_llm():
    """An LLM that plans nothing and streams one chunk."""
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=MagicMock(content="ok", tool_calls=None, plan=None)
    )

    async def _stream(messages, **kwargs):
        yield "hello"

    llm.stream = _stream
    return llm


async def _run(agent, query):
    return [e async for e in agent.process(query)]


# -----------------------------------------------------------------------------
# R06-F2 — response modality must be resolved for both prompt arms
# -----------------------------------------------------------------------------

class TestResponseModalityBoundWithoutPromptBuilder:
    """The no-prompt-builder arm reads ``response_modality`` too."""

    @pytest.mark.asyncio
    async def test_turn_completes_without_a_prompt_builder(self):
        # prompt_builder=None is the Wyoming/embedder shape. The dashboard
        # always wires one (routes/agent.py), which is why this path was dark.
        agent = AgentStateMachine(llm_client=_mk_llm(), max_loops=5)
        assert agent.prompts is None

        events = await _run(agent, "what is sshd_config")

        errors = [e for e in events if e.type == "error"]
        assert not errors, f"no-builder turn errored: {[e.data for e in errors]}"
        assert [e.data["state"] for e in events if e.type == "state_change"][-1] == "idle"

    @pytest.mark.asyncio
    async def test_simple_prompt_receives_the_resolved_modality(self):
        agent = AgentStateMachine(llm_client=_mk_llm(), max_loops=5)
        seen = []
        real = agent._build_simple_response_prompt

        def _spy(response_modality="text"):
            seen.append(response_modality)
            return real(response_modality=response_modality)

        agent._build_simple_response_prompt = _spy
        await _run(agent, "what is sshd_config")

        # Text is the floor: with no channel capability there is no speaker,
        # so the turn is a text turn.
        assert seen == ["text"]


# -----------------------------------------------------------------------------
# R06-F1 — the defanged query must not survive into the next turn
# -----------------------------------------------------------------------------

class TestDefangedQueryDoesNotLeakAcrossTurns:
    """Turn N+1 must plan against turn N+1's question."""

    @pytest.mark.asyncio
    async def test_planning_messages_carry_only_this_turns_query(self):
        agent = AgentStateMachine(llm_client=_mk_llm(), max_loops=5)

        # Stand in for the modality engine's defang step, which is what sets
        # the defanged query in production. Writing it onto the machine the
        # way the pre-fix code did keeps the test honest about the seam
        # rather than about whether the engine is importable in this venv.
        turn_one = "Set up a samba share for the media drive"
        turn_two = "What port does it listen on?"

        await _run(agent, turn_one)
        agent.ctx.defanged_query = turn_one   # as RESPONDING leaves it
        agent._defanged_query = turn_one      # the pre-fix instance attribute

        captured = []
        real_build = agent._build_messages

        def _spy(prompt, tail=None, **kwargs):
            msgs = real_build(prompt, tail=tail, **kwargs)
            captured.append(msgs)
            return msgs

        agent._build_messages = _spy
        await _run(agent, turn_two)

        assert captured, "_build_messages was never called on turn 2"
        planning = captured[0]
        last_user = [m for m in planning if m.get("role") == "user"][-1]
        assert turn_two in last_user["content"]
        assert turn_one not in last_user["content"], (
            "turn 1's question leaked into turn 2's planning prompt"
        )

    @pytest.mark.asyncio
    async def test_defanged_query_is_per_turn_state_not_machine_state(self):
        """The field must live on the context, so a new turn cannot see it."""
        agent = AgentStateMachine(llm_client=_mk_llm(), max_loops=5)
        await _run(agent, "first question")
        agent.ctx.defanged_query = "stale from the first turn"
        first_ctx = agent.ctx

        seen = []
        real_build = agent._build_messages

        def _spy(prompt, tail=None, **kwargs):
            seen.append(agent.ctx.defanged_query)
            return real_build(prompt, tail=tail, **kwargs)

        agent._build_messages = _spy
        await _run(agent, "second question")

        assert agent.ctx is not first_ctx, "process() must build a fresh context"
        assert seen, "_build_messages was never called"
        assert "stale from the first turn" not in [s for s in seen if s]
