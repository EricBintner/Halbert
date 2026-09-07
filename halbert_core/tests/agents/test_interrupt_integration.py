# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Packet 07 Phase B: the interrupt algebra in the live state machine.

B1 — a TurnActivity threaded through the running turn: process() stamps on
start, RESPONDING finalize stamps at the answer-commit edge, and a stop
claims the start generation so a stop that loses the race to a finishing
turn declines instead of double-firing.

B2 — mid-turn arrivals route through decide_midturn: plain text steers into
the single replace-not-grow pending slot and applies at the next batch
boundary; "/stop" during a tool batch demotes to steer (yield, never kill).

B3 — the generation-claim race: a stop issued as the turn completes
produces "stopped" or "turn completed, stop declined", never both, never a
retry.
"""

import asyncio
from contextlib import aclosing
from types import SimpleNamespace

import pytest

from halbert_core.agents.llm_client import LLMResponse
from halbert_core.agents.steering import Verdict
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.states import AgentState
from halbert_core.tools import ToolExecutor, ToolSafetyFramework
from halbert_core.tools.executor import ExecutionResult


class _SlowLLM:
    """Answers directly, but sleeps inside chat()/stream() so a concurrent
    request can arrive mid-turn, exactly like the dashboard's second POST."""

    def __init__(self, delay=0.05):
        self.delay = delay
        self.seen = []

    async def chat(self, messages, tools=None, **kwargs):
        self.seen.append(messages)
        await asyncio.sleep(self.delay)
        return LLMResponse(content="done", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        self.seen.append(messages)
        for chunk in ("an", "swer"):
            await asyncio.sleep(self.delay)
            yield chunk


class _ToolThenAnswerLLM:
    """chat #1 asks for read_file; every later chat answers directly."""

    def __init__(self):
        self.calls = 0
        self.seen = []

    async def chat(self, messages, tools=None, **kwargs):
        self.seen.append(messages)
        self.calls += 1
        if self.calls == 1:
            tc = SimpleNamespace(
                function=SimpleNamespace(
                    name="read_file", arguments={"path": "/etc/hosts"}
                )
            )
            return LLMResponse(content="", tool_calls=[tc], plan=[])
        return LLMResponse(content="done", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        self.seen.append(messages)
        yield "done"


def _agent(llm, **kw):
    return AgentStateMachine(
        llm_client=llm,
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        max_loops=5,
        **kw,
    )


async def _collect(stream):
    return [e async for e in stream]


class TestGenerationStamps:
    @pytest.mark.asyncio
    async def test_process_stamps_on_start_and_responding_finalize(self):
        agent = _agent(_SlowLLM(delay=0))
        before = agent.turn_activity.generation
        await _collect(agent.process("hello", session_id="stamp"))
        # Exactly two: the start stamp in process() and the finalize stamp
        # at the answer-commit edge in RESPONDING.
        assert agent.turn_activity.generation == before + 2

    @pytest.mark.asyncio
    async def test_a_cancelled_turn_never_reaches_the_finalize_stamp(self):
        agent = _agent(_SlowLLM(delay=0.2))
        before = agent.turn_activity.generation
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="cut")))
        await asyncio.sleep(0.05)
        assert agent.request_stop("cut") == "stopped"
        await asyncio.wait_for(task, timeout=5)
        # Only the start stamp: the stream was cut before the answer
        # committed, so no finalize edge ever passed.
        assert agent.turn_activity.generation == before + 1


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_midturn_claims_and_cuts_the_stream(self):
        agent = _agent(_SlowLLM(delay=0.2))
        task = asyncio.ensure_future(_collect(agent.process("long answer", session_id="stopme")))
        await asyncio.sleep(0.05)
        assert agent._turn_in_flight()
        assert agent.request_stop("stopme") == "stopped"
        events = await asyncio.wait_for(task, timeout=5)
        types = [e.type for e in events]
        assert types.count("session_started") == 1      # never a retry
        assert "cancelled" in types
        assert "response_complete" not in types         # never both
        assert agent.current_state == AgentState.IDLE
        assert "stopme" not in agent.active_sessions
        assert agent.cancelled.get("stopme") is None     # the finally settled it

    @pytest.mark.asyncio
    async def test_stop_after_the_turn_settled_declines(self):
        agent = _agent(_SlowLLM(delay=0))
        await _collect(agent.process("hello", session_id="done"))
        assert agent.request_stop("done") == "turn completed, stop declined"
        assert agent.cancelled == {}

    @pytest.mark.asyncio
    async def test_a_second_stop_while_stopping_is_idempotent(self):
        agent = _agent(_SlowLLM(delay=0.2))
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="twice")))
        await asyncio.sleep(0.05)
        assert agent.request_stop("twice") == "stopped"
        # The claim is single-shot, but the turn IS stopping: the second
        # stop observes the flag the first one raised and says so.
        assert agent.request_stop("twice") == "stopped"
        await asyncio.wait_for(task, timeout=5)
        assert agent.cancelled == {}

    @pytest.mark.asyncio
    async def test_stop_on_a_paused_confirmation_tears_it_down(self):
        # A paused turn's stream is already closed; nothing races, so the
        # stop takes cancel_session's teardown path (no claim needed).
        from unittest.mock import AsyncMock, MagicMock

        llm = AsyncMock()
        tc = MagicMock()
        tc.function.name = "run_command"
        tc.function.arguments = {"command": "systemctl restart sshd"}
        llm.chat = AsyncMock(return_value=MagicMock(content="", tool_calls=[tc], plan=None))
        agent = _agent(llm)
        await _collect(agent.process("restart sshd", session_id="paused"))
        assert agent.current_state == AgentState.AWAITING_CONFIRMATION
        assert agent.request_stop("paused") == "stopped"
        assert "paused" not in agent.active_sessions
        assert agent.current_state == AgentState.IDLE

