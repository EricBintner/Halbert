# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-01 Phase C: an accepted steer is honoured, and only a live turn takes one.

Three ways the steer half told the user something untrue:

- **A07-G3** — a steer arriving after the turn was stopped, or after its
  answer had already been committed, was answered ``steer_accepted`` and
  then silently discarded. The verdict has to be the truth: refuse it, so
  the surface can send it as the next turn.
- **A07-G6** — the pending slot was replace-not-grow, so a second steer
  before the batch boundary erased the first. Both were answered
  "accepted"; only one arrived. Steers concatenate.
- **A07 bug 1** — an empty or whitespace-only arrival was accepted as a
  steer, so a stray submit joined the running turn as a blank line.

Plus **A07-G4**: the marker is an open/close pair with a prompt-side
contract, rather than a bare ``[steered]`` prefix the model has never
been told the meaning of.
"""

import asyncio

import pytest

from halbert_core.agents.llm_client import LLMResponse
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.states import AgentState, StateContext
from halbert_core.agents.steering import (
    STEER_MARKER,
    STEER_MARKER_CLOSE,
    Verdict,
    apply_steer_to_results,
)
from halbert_core.tools import ToolExecutor, ToolSafetyFramework


class _SlowLLM:
    def __init__(self, delay=0.1):
        self.delay = delay

    async def chat(self, messages, tools=None, **kwargs):
        await asyncio.sleep(self.delay)
        return LLMResponse(content="done", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        await asyncio.sleep(self.delay)
        yield "done"


def _agent(llm=None, **kw):
    return AgentStateMachine(
        llm_client=llm or _SlowLLM(),
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        max_loops=5,
        **kw,
    )


def _busy(agent, state=AgentState.EXECUTING):
    ctx = StateContext(session_id="run", request_id="r", user_query="q")
    agent.ctx = ctx
    agent.active_sessions["run"] = ctx
    agent.current_state = state
    agent._turn_lock = asyncio.Lock()
    agent._turn_lock._locked = True
    agent._turn_generation = agent.turn_activity.stamp()
    return agent


# ---------------------------------------------------------------------------
# A07-G6: steers concatenate
# ---------------------------------------------------------------------------

def test_a_second_steer_does_not_erase_the_first():
    agent = _busy(_agent())
    agent.request_steer("check the logs")
    agent.request_steer("and the camera")
    agent._drain_pending_steer()
    joined = "\n".join(agent.ctx.observations)
    assert "check the logs" in joined
    assert "and the camera" in joined


def test_the_second_steer_still_reports_that_it_joined_one():
    agent = _busy(_agent())
    assert agent.request_steer("one")["replaced"] is False
    second = agent.request_steer("two")
    assert second["accepted"] is True
    # "replaced" is the honest word for "there was already one pending" --
    # it no longer means the first one was thrown away.
    assert second["replaced"] is True


# ---------------------------------------------------------------------------
# A07 bug 1: an empty arrival is not a steer
# ---------------------------------------------------------------------------

def test_an_empty_arrival_is_refused():
    agent = _busy(_agent())
    decision, events = agent.handle_midturn_arrival("arr", "   ")
    assert decision.verb is Verdict.REFUSED
    assert decision.reason_code == "empty_arrival"
    assert agent._pending_steer == {}
    assert events[0].type == "steer_refused"


# ---------------------------------------------------------------------------
# A07-G3: a steer after stop or after commit is refused, not dropped
# ---------------------------------------------------------------------------

def test_a_steer_after_a_stop_is_refused():
    agent = _busy(_agent())
    agent.request_stop("run")
    decision, events = agent.handle_midturn_arrival("arr", "also the disk")
    assert decision.verb is Verdict.REFUSED
    assert decision.reason_code == "turn_already_stopped"
    assert agent._pending_steer == {}


def test_a_steer_after_the_answer_committed_is_refused():
    """The RESPONDING finalize stamp is the commit edge."""
    agent = _busy(_agent(), state=AgentState.RESPONDING)
    agent.turn_activity.stamp()  # the finalize stamp
    decision, events = agent.handle_midturn_arrival("arr", "also the disk")
    assert decision.verb is Verdict.REFUSED
    assert decision.reason_code == "answer_already_committed"
    assert agent._pending_steer == {}


def test_a_steer_into_a_live_turn_is_still_accepted():
    agent = _busy(_agent())
    decision, events = agent.handle_midturn_arrival("arr", "also the disk")
    assert decision.verb is Verdict.STEER
    assert events[0].type == "steer_accepted"


# ---------------------------------------------------------------------------
# A07-G4: the marker is a labelled wrapper with a prompt-side contract
# ---------------------------------------------------------------------------

def test_the_steer_marker_opens_and_closes():
    results = [{"name": "run_command", "output": "ok"}]
    out = apply_steer_to_results(results, "check the logs")
    assert STEER_MARKER in out
    assert STEER_MARKER_CLOSE in out
    assert out.index(STEER_MARKER) < out.index("check the logs")
    assert out.index("check the logs") < out.index(STEER_MARKER_CLOSE)


def test_concatenated_steers_each_get_their_own_wrapper():
    results = [{"name": "run_command", "output": "ok"}]
    apply_steer_to_results(results, "one")
    out = apply_steer_to_results(results, "two")
    assert out.count(STEER_MARKER) == 2
    assert out.count(STEER_MARKER_CLOSE) == 2


def test_the_prompt_states_what_the_marker_means():
    """The model is told what a steered block is and whose words it carries."""
    from halbert_core.prompts.agent_prompts import STEER_CONTRACT, AgentPromptBuilder

    assert "[steered]" in STEER_CONTRACT
    prompt = AgentPromptBuilder().build_planning_prompt(
        query="q",
        context="",
        observations=["ran a command\n[steered]\nand the camera\n[/steered]"],
    )
    assert STEER_CONTRACT in prompt


def test_the_contract_is_absent_when_nothing_was_steered():
    """A deterministic paragraph, not a permanent one: no marker, no note."""
    from halbert_core.prompts.agent_prompts import STEER_CONTRACT, AgentPromptBuilder

    prompt = AgentPromptBuilder().build_planning_prompt(
        query="q", context="", observations=["ran a command"],
    )
    assert STEER_CONTRACT not in prompt
