# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-01 Phase D: a wedged turn is eventually freed (A07-G10).

``TURN_LOCK_TIMEOUT_S`` bounds how long a *waiter* queues; nothing ever
bounded the *holder*. A turn wedged on an un-returning await held the
turn lock for the life of the process, and every later message queued
behind a badge that never changed -- recoverable only by restarting.

The fix is the stamp the origin's watchdog is built on: ``ctx.last_activity``,
touched at handler entry, at each tool start and completion, and on each
stream chunk, plus one sampler that watches it. The sampler is bound to
the generation it observed, so it can only ever end the turn it was
watching -- the same single-shot claim a stop uses.

A turn parked on a confirmation is not stalled: a human may take a
quarter of an hour to answer, and waiting is not wedging.
"""

import asyncio

import pytest

from halbert_core.agents.llm_client import LLMResponse
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.states import AgentState
from halbert_core.tools import ToolExecutor, ToolSafetyFramework


class _WedgedLLM:
    """Never returns: the shape of a provider client that hung."""

    async def chat(self, messages, tools=None, **kwargs):
        await asyncio.sleep(3600)
        return LLMResponse(content="never", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        await asyncio.sleep(3600)
        yield "never"


class _FastLLM:
    async def chat(self, messages, tools=None, **kwargs):
        return LLMResponse(content="done", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
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


@pytest.mark.asyncio
async def test_a_wedged_turn_is_ended_by_the_watchdog():
    agent = _agent(_WedgedLLM())
    agent.TURN_STALL_SECONDS = 0.2
    agent.STALL_POLL_SECONDS = 0.05

    events = await asyncio.wait_for(
        _collect(agent.process("hello", session_id="wedged")), timeout=10
    )
    assert "cancelled" in [e.type for e in events]
    # And the lock is free again: a later turn is not queued forever.
    assert not agent.turn_lock.locked()


@pytest.mark.asyncio
async def test_a_live_turn_is_never_ended_by_the_watchdog():
    """Activity is what keeps the turn alive, and a normal turn has it."""
    agent = _agent(_FastLLM())
    agent.TURN_STALL_SECONDS = 0.2
    agent.STALL_POLL_SECONDS = 0.05
    events = await asyncio.wait_for(
        _collect(agent.process("hello", session_id="alive")), timeout=10
    )
    types = [e.type for e in events]
    assert "cancelled" not in types
    assert "session_ended" in types


@pytest.mark.asyncio
async def test_a_turn_paused_on_a_confirmation_is_not_stalled():
    """Waiting for a human is not wedging (OC15-M3's rule, applied here)."""
    from unittest.mock import AsyncMock, MagicMock

    llm = AsyncMock()
    tc = MagicMock()
    tc.function.name = "run_command"
    tc.function.arguments = {"command": "systemctl restart sshd"}
    llm.chat = AsyncMock(
        return_value=MagicMock(content="", tool_calls=[tc], plan=None)
    )
    agent = _agent(llm)
    agent.TURN_STALL_SECONDS = 0.1
    agent.STALL_POLL_SECONDS = 0.02

    await _collect(agent.process("restart sshd", session_id="paused"))
    assert agent.current_state == AgentState.AWAITING_CONFIRMATION
    await asyncio.sleep(0.3)
    # Still there to confirm: the watchdog did not tear down a turn that
    # is waiting on a person.
    assert "paused" in agent.active_sessions


@pytest.mark.asyncio
async def test_the_stamp_moves_as_the_turn_works():
    agent = _agent(_FastLLM())
    seen = []

    real = agent._touch_activity

    def _record(note):
        seen.append(note)
        return real(note)

    agent._touch_activity = _record
    await _collect(agent.process("hello", session_id="stamped"))
    assert seen, "the turn must stamp its own liveness"
    assert any("responding" in n or "planning" in n for n in seen), seen


@pytest.mark.asyncio
async def test_the_watchdog_declines_on_a_turn_that_moved_on():
    """The sampler is bound to the generation it observed.

    A sampler that woke late must not end a *different* turn running
    under the same session id -- the same single-shot claim rule a stop
    obeys.
    """
    agent = _agent(_FastLLM())
    fired = []
    generation = agent.turn_activity.stamp()
    agent.turn_activity.stamp()  # the turn moved on
    assert agent.turn_activity.claim(generation, lambda: fired.append(1)) is None
    assert fired == []
