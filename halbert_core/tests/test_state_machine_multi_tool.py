# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SP-3: a response carrying several tool calls dispatches them all.

Pre-fix, ``_handle_planning`` read ``response.tool_calls[0]`` and silently
dropped the rest — a local model emitting two calls in one turn lost the
second with nothing reflected to the model. The fix stages every
executor/read/search call as a pending :class:`ToolCall` and drains them one
per loop via ``_next_pending_tool_call`` (first unsettled), so all run in
order. Thread-meta calls are still handled inline one at a time.
"""

import pytest

from halbert_core.agents.states import AgentState, StateContext
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.llm_client import LLMResponse, ToolCall, FunctionCall
from halbert_core.tools import ToolExecutor, ToolSafetyFramework


class _ScriptedLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.arrays = []

    async def chat(self, messages, tools=None, **kwargs):
        self.arrays.append([dict(m) for m in messages])
        return self.responses.pop(0) if self.responses else LLMResponse(
            content="answer", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        yield "answer"


def _multi(*calls):
    """An LLMResponse whose tool_calls list holds several calls."""
    return LLMResponse(
        content="",
        tool_calls=[
            ToolCall(id=f"c{i}", function=FunctionCall(name=name, arguments=args))
            for i, (name, args) in enumerate(calls)
        ],
    )


def _agent(llm):
    return AgentStateMachine(
        llm_client=llm,
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        max_loops=5,
    )


def _planning(llm, **kw):
    agent = _agent(llm)
    agent.ctx = StateContext(session_id="s", request_id="r", user_query="q", **kw)
    agent.current_state = AgentState.PLANNING
    return agent


@pytest.mark.asyncio
async def test_two_tool_calls_in_one_response_are_both_staged():
    """The data-loss case: two executor calls in one response. Both must be
    staged as pending ToolCalls — none dropped — and the route targets the
    first."""
    llm = _ScriptedLLM([_multi(
        ("list_directory", {"path": "/tmp"}),
        ("read_file", {"path": "/tmp/x"}),
    )])
    agent = _planning(llm)
    events = [e async for e in agent._handle_planning()]

    names = [tc.name for tc in agent.ctx.tool_calls]
    assert names == ["list_directory", "read_file"], (
        f"both calls must be staged, got {names}")
    # All staged calls start pending; the handlers drain them in order.
    assert all(tc.status == "pending" for tc in agent.ctx.tool_calls)
    # Routed toward the first call's state (list_directory -> EXECUTING).
    assert events[-1].data["state"] == "executing"


@pytest.mark.asyncio
async def test_next_pending_drains_in_order():
    """As each staged call settles, the next pending one is selected."""
    llm = _ScriptedLLM([_multi(
        ("list_directory", {"path": "/a"}),
        ("read_file", {"path": "/b"}),
        ("read_config", {"path": "/c"}),
    )])
    agent = _planning(llm)
    [e async for e in agent._handle_planning()]

    assert agent._next_pending_tool_call().name == "list_directory"
    agent.ctx.tool_calls[0].status = "success"
    assert agent._next_pending_tool_call().name == "read_file"
    agent.ctx.tool_calls[1].status = "success"
    assert agent._next_pending_tool_call().name == "read_config"
    agent.ctx.tool_calls[2].status = "error"
    assert agent._next_pending_tool_call() is None


@pytest.mark.asyncio
async def test_duplicate_call_is_skipped_not_restaged():
    """A call identical to one that already settled this turn is skipped with
    an observation, not re-staged (the already-called guard survives)."""
    llm = _ScriptedLLM([_multi(
        ("read_file", {"path": "/tmp/x"}),
        ("read_file", {"path": "/tmp/x"}),
    )])
    agent = _planning(llm)
    # Simulate the first read_file already settled this turn.
    prior = agent.ctx  # noqa: F841
    from halbert_core.agents.states import ToolCall as _TC
    settled = _TC(id="p0", name="read_file", args={"path": "/tmp/x"})
    settled.status = "success"
    agent.ctx.add_tool_call(settled)

    [e async for e in agent._handle_planning()]
    # No NEW pending call staged for the duplicate; an observation notes it.
    pending = [tc for tc in agent.ctx.tool_calls if tc.status == "pending"]
    assert pending == [], f"duplicate must not be re-staged: {pending}"
    assert any("Already ran" in o for o in agent.ctx.observations)


@pytest.mark.asyncio
async def test_meta_tool_first_stays_inline_executor_calls_ride_next_loop():
    """A response whose FIRST call is a thread-meta tool is handled inline
    exactly as before; executor calls in the same response are not staged by
    the meta path (they ride the next PLANNING re-entry)."""
    tm_response = _multi(
        ("new_thread", {"title": "T", "reason": "r"}),
        ("read_file", {"path": "/tmp/x"}),
    )
    llm = _ScriptedLLM([tm_response])

    class _TM:
        store = None

        def new_thread(self, title, reason, *, from_thread_id):
            return "t-new"

        def recall(self, **kw):
            return []

        def resume_thread(self, tid, *, from_thread_id):
            return True

    agent = _planning(llm, thread_id="t-old",
                      conversation_history=[{"role": "user", "content": "old"}])
    agent.ctx.thread_manager = _TM()
    events = [e async for e in agent._handle_planning()]
    # Meta path: thread_started + re-enter PLANNING; read_file not staged.
    assert "thread_started" in [e.type for e in events]
    assert all(tc.name != "read_file" for tc in agent.ctx.tool_calls)
