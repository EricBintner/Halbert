# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-01 Phase B: one stop verb, and it actually stops things.

Four defects in the interrupt algebra's stop half (OSS solidity pass):

- **A07-G2** — an explicit ``/stop`` while a tool ran was demoted to a
  steer. The demotion rule is "never kill a tool to deliver *guidance*";
  the packet transcribed it onto the stop verb, so the one verb the
  algebra names "stop" could not stop the one thing users want stopped.
- **A07-G2 (second half)** — the tool wait loop never polled
  ``self.cancelled``, so even a stop that fired left the subprocess
  running to completion.
- **A07-G13 + A07 bug 2** — the dashboard's stop button POSTed
  ``/cancel``, which raises the flag with no generation claim, while a
  typed ``/stop`` claimed the generation: two verbs, two semantics, and
  a paused turn tore down under one and not the other.
- **A07-G5 / A07-G9** — a stop could not abort an in-flight model
  request, and a turn queued on the turn lock could not be stopped at
  all.
"""

import asyncio

import pytest

from halbert_core.agents.llm_client import LLMResponse
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.states import AgentState
from halbert_core.agents.steering import Verdict, decide_midturn
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


async def _collect(stream):
    return [e async for e in stream]


# ---------------------------------------------------------------------------
# A07-G2: Rule 1 is unconditional
# ---------------------------------------------------------------------------

def test_stop_is_not_demoted_while_a_tool_batch_runs():
    """The demotion rule protects *guidance*, not the stop verb."""
    decision = decide_midturn(
        turn_active=True,
        is_command=True,
        text="/stop",
        tool_batch_in_flight=True,
    )
    assert decision.verb is Verdict.STOP


def test_plain_text_still_steers_while_a_tool_batch_runs():
    """Rule 3 is untouched: text never kills a tool."""
    decision = decide_midturn(
        turn_active=True,
        is_command=False,
        text="also check the logs",
        tool_batch_in_flight=True,
    )
    assert decision.verb is Verdict.STEER


# ---------------------------------------------------------------------------
# A07-G2: the stop reaches the running tool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_stop_cancels_the_running_tool_task():
    """``request_stop`` must cancel the tool task, not just flag the turn.

    The wait loop used to block on ``{task, getter}`` with no timeout, so
    a stop raised the flag and then waited for the command it was meant
    to stop.
    """
    agent = _agent()
    started = asyncio.Event()
    cancelled = {"seen": False}

    async def _forever(*a, **kw):
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled["seen"] = True
            raise

    agent.tools.execute = _forever
    agent.ctx = None

    async def _drive():
        from halbert_core.agents.states import StateContext
        agent.ctx = StateContext(session_id="s", request_id="r", user_query="q")
        agent.active_sessions["s"] = agent.ctx
        agent._turn_lock = asyncio.Lock()
        await agent._turn_lock.acquire()
        agent._turn_generation = agent.turn_activity.stamp()
        sink = []
        return [
            e async for e in agent._run_tool_streaming(
                "run_command", {"command": "sleep 30"}, True, sink
            )
        ]

    task = asyncio.ensure_future(_drive())
    await asyncio.wait_for(started.wait(), timeout=5)
    assert agent.request_stop("s") == "stopped"
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)
    assert cancelled["seen"], "the tool task must be cancelled by the stop"


# ---------------------------------------------------------------------------
# A07-G13 + A07 bug 2: one stop semantics
# ---------------------------------------------------------------------------

def test_cancel_session_goes_through_the_generation_claim():
    """``/cancel`` and ``/stop`` are one verb.

    ``cancel_session`` raised the flag unconditionally; ``request_stop``
    claims the running turn's generation so a stop that loses the race to
    a finishing turn declines. Two paths meant the dashboard button and a
    typed ``/stop`` disagreed about what a stop is.
    """
    agent = _agent()
    from halbert_core.agents.states import StateContext

    ctx = StateContext(session_id="s", request_id="r", user_query="q")
    agent.ctx = ctx
    agent.active_sessions["s"] = ctx
    agent._turn_lock = asyncio.Lock()
    agent._turn_lock._locked = True
    agent._turn_generation = agent.turn_activity.stamp()

    claims = []
    real_claim = agent.turn_activity.claim

    def _record(generation, fn):
        claims.append(generation)
        return real_claim(generation, fn)

    agent.turn_activity.claim = _record
    assert agent.cancel_session("s") is True
    assert claims, "cancel_session must go through the generation claim"


def test_cancel_session_on_an_unknown_session_is_still_false():
    """The /cancel route's 404 contract survives the delegation."""
    assert _agent().cancel_session("nope") is False


def test_a_paused_turn_tears_down_under_either_verb():
    """A07 bug 2: the paused rule was asymmetric between the two verbs."""
    from halbert_core.agents.states import StateContext

    for verb in ("cancel", "stop"):
        agent = _agent()
        ctx = StateContext(session_id="s", request_id="r", user_query="q")
        agent.ctx = ctx
        agent.active_sessions["s"] = ctx
        agent.current_state = AgentState.AWAITING_CONFIRMATION
        agent._turn_lock = asyncio.Lock()
        agent._turn_lock._locked = True
        agent._turn_generation = agent.turn_activity.stamp()

        if verb == "cancel":
            agent.cancel_session("s")
        else:
            agent.request_stop("s")

        assert "s" not in agent.active_sessions, verb
        assert agent.current_state is AgentState.IDLE, verb


# ---------------------------------------------------------------------------
# A07-G5: a stop aborts the in-flight model request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_stop_aborts_the_in_flight_model_request():
    """A model call that would take a minute does not hold the stop."""
    seen = {"cancelled": False}

    class _WedgedLLM:
        async def chat(self, messages, tools=None, **kwargs):
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                seen["cancelled"] = True
                raise
            return LLMResponse(content="done", tool_calls=[], plan=[])

        async def stream(self, messages, **kwargs):
            await asyncio.sleep(30)
            yield "done"

    agent = _agent(llm=_WedgedLLM())
    task = asyncio.ensure_future(_collect(agent.process("hello", session_id="s")))
    await asyncio.sleep(0.15)
    agent.request_stop("s")
    events = await asyncio.wait_for(task, timeout=5)
    assert "cancelled" in [e.type for e in events]
    assert seen["cancelled"], "the model call itself must be cancelled"


# ---------------------------------------------------------------------------
# A07-G9: a queued turn can be stopped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_queued_turn_can_be_stopped_before_it_starts():
    """A turn waiting on the turn lock is stoppable.

    It never entered ``active_sessions``, so ``request_stop`` declined
    and the queued turn ran anyway once the lock freed — the user's stop
    produced a turn.
    """
    agent = _agent(llm=_SlowLLM(delay=0.4))
    first = asyncio.ensure_future(_collect(agent.process("one", session_id="a")))
    await asyncio.sleep(0.05)
    second = asyncio.ensure_future(_collect(agent.process("two", session_id="b")))
    await asyncio.sleep(0.05)

    assert agent.request_stop("b") == "stopped"
    second_events = await asyncio.wait_for(second, timeout=10)
    await asyncio.wait_for(first, timeout=10)

    types = [e.type for e in second_events]
    assert "cancelled" in types, types
    assert "session_ended" not in types[types.index("cancelled") + 1:]
