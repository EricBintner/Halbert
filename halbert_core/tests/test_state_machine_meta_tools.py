# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A9b: new_thread / recall_thread / resume_thread are handled
inline in PLANNING: no tool card, no loop increment, PLANNING re-runs once."""

import pytest

from halbert_core.agents.states import AgentState, StateContext
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.llm_client import LLMResponse, ToolCall, FunctionCall
from halbert_core.tools import ToolExecutor, ToolSafetyFramework


class _FakeStore:
    """Only list_messages: what _last_turn_id needs from the store."""

    def __init__(self, rows_by_thread):
        self.rows = rows_by_thread

    def list_messages(self, thread_id, *, limit=None):
        return list(self.rows.get(thread_id, []))


class _FakeThreadManager:
    def __init__(self, recall_results=None, resume_ok=True, store=None):
        self.calls, self.recall_results, self.resume_ok = [], recall_results or [], resume_ok
        self.store = store

    def new_thread(self, title, reason, *, from_thread_id):
        self.calls.append(("new_thread", title, reason, from_thread_id))
        return "t-new"

    def recall(self, query=None, thread_id=None, *, exclude_thread_id=None):
        self.calls.append(("recall", query, thread_id, exclude_thread_id))
        return list(self.recall_results)

    def resume_thread(self, thread_id, *, from_thread_id):
        self.calls.append(("resume_thread", thread_id, from_thread_id))
        return self.resume_ok


class _ScriptedLLM:
    def __init__(self, responses):
        self.responses, self.prompts = list(responses), []

    async def chat(self, messages, tools=None, **kwargs):
        self.prompts.append(messages[-1]["content"])
        return self.responses.pop(0) if self.responses else LLMResponse(content="answer", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        yield "answer"


def _call(name, **args):
    return LLMResponse(content="", tool_calls=[ToolCall(id="c1", function=FunctionCall(name=name, arguments=args))])


def _agent(llm):
    return AgentStateMachine(llm_client=llm, tool_executor=ToolExecutor(safety=ToolSafetyFramework()), max_loops=5)


def _planning(llm, tm, thread_id="t-open", **kw):
    agent = _agent(llm)
    agent.ctx = StateContext(session_id="s", request_id="r", user_query="now scanner share", thread_id=thread_id, **kw)
    agent.ctx.thread_manager = tm
    agent.current_state = AgentState.PLANNING
    return agent


RECALLED = {"thread_id": "t-9", "title": "Samba media share", "date": "2026-07-14",
            "receipt": "Title: Samba media share\nCommands: testparm (exit 0)",
            "matching_messages": ["added [media]"], "match_terms": ["samba", "share"]}


@pytest.mark.asyncio
async def test_new_thread_emits_thread_started_and_reenters_planning_without_loop_increment():
    tm = _FakeThreadManager()
    agent = _planning(_ScriptedLLM([_call("new_thread", title="Scanner share", reason="topic changed")]), tm,
                      thread_id="t-old", conversation_history=[{"role": "user", "content": "old"}])
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["thread_started", "state_change"]
    assert events[0].data == {"thread_id": "t-new", "title": "Scanner share", "reason": "topic changed", "previous_thread_id": "t-old"}
    assert events[1].data["state"] == "planning" and events[1].data["previous_state"] == "planning"
    assert agent.ctx.loop_count == 0
    assert agent.ctx.thread_id == "t-new" and agent.ctx.thread_switched is True
    assert agent.ctx.conversation_history == [] and "Scanner share" in agent.ctx.continuity_hint
    assert tm.calls == [("new_thread", "Scanner share", "topic changed", "t-old")]


@pytest.mark.asyncio
async def test_second_new_thread_in_a_turn_is_a_noop_that_reflects():
    tm = _FakeThreadManager()
    agent = _planning(_ScriptedLLM([_call("new_thread", title="Again", reason="r")]), tm, thread_id="t-new")
    agent.ctx.thread_switched = True
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["state_change"] and events[0].data["state"] == "reflecting"
    assert tm.calls == [] and agent.ctx.loop_count == 0


@pytest.mark.asyncio
async def test_full_turn_reenters_planning_exactly_once():
    tm = _FakeThreadManager()
    llm = _ScriptedLLM([_call("new_thread", title="Scanner share", reason="r")])
    agent = _agent(llm)
    events = [e async for e in agent.process("now scanner share", session_id="s-full", thread_id="t-old", thread_manager=tm)]
    types = [e.type for e in events]
    reentries = [e for e in events if e.type == "state_change" and e.data["state"] == "planning" and e.data["previous_state"] == "planning"]
    assert len(reentries) == 1 and types.count("thread_started") == 1
    assert "response_complete" in types and "session_ended" in types and "tool_start" not in types
    assert agent.ctx.loop_count <= 1
    assert any("Scanner share" in p for p in llm.prompts[1:])  # the second PLANNING pass saw the new hint


@pytest.mark.asyncio
async def test_store_failure_emits_thread_store_error_and_still_switches():
    tm = _FakeThreadManager()

    def boom(title, reason, *, from_thread_id):
        raise RuntimeError("db locked")

    tm.new_thread = boom
    agent = _planning(_ScriptedLLM([_call("new_thread", title="T", reason="r")]), tm, thread_id="t-old")
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["thread_store_error", "thread_started", "state_change"]
    assert "db locked" in events[0].data["message"]
    assert agent.ctx.thread_switched is True and agent.ctx.thread_id != "t-old"
    # No manager at all still switches in memory.
    agent2 = _planning(_ScriptedLLM([_call("new_thread", title="T", reason="r")]), None, thread_id="t-old")
    assert [e.type async for e in agent2._handle_planning()] == ["thread_started", "state_change"]


@pytest.mark.asyncio
async def test_recall_injects_receipt_emits_thread_recalled_and_repeat_reflects():
    tm = _FakeThreadManager(
        recall_results=[RECALLED],
        store=_FakeStore({"t-9": [{"turn_id": "turn-a"}, {"turn_id": "turn-b"}, {"turn_id": None}]}),
    )
    agent = _planning(_ScriptedLLM([_call("recall_thread", query="samba share"), _call("recall_thread", query="samba share")]), tm)
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["thread_recalled", "state_change"]
    assert events[0].data["thread_id"] == "t-9" and events[0].data["mode"] == "tool"
    assert events[0].data["match_terms"] == ["samba", "share"]
    assert events[0].data["last_turn_id"] == "turn-b"   # newest row with a turn_id
    assert tm.calls == [("recall", "samba share", None, "t-open")]
    assert agent.ctx.retrieved_context[0]["source"] == "thread" and "testparm" in agent.ctx.retrieved_context[0]["content"]
    assert agent.ctx.recalled_threads[0]["thread_id"] == "t-9"
    assert agent.ctx.loop_count == 0 and agent.ctx.thread_switched is False
    second = [e async for e in agent._handle_planning()]
    assert second[-1].data["state"] == "reflecting" and len(tm.calls) == 1


@pytest.mark.asyncio
async def test_recall_without_a_store_has_no_last_turn_id():
    tm = _FakeThreadManager(recall_results=[RECALLED])          # no .store
    agent = _planning(_ScriptedLLM([_call("recall_thread", query="samba share")]), tm)
    events = [e async for e in agent._handle_planning()]
    assert events[0].type == "thread_recalled" and events[0].data["last_turn_id"] is None
    # a recall result that already names its last turn wins over the store
    tm2 = _FakeThreadManager(recall_results=[dict(RECALLED, last_turn_id="turn-given")],
                             store=_FakeStore({"t-9": [{"turn_id": "turn-store"}]}))
    agent2 = _planning(_ScriptedLLM([_call("recall_thread", query="samba share")]), tm2)
    events2 = [e async for e in agent2._handle_planning()]
    assert events2[0].data["last_turn_id"] == "turn-given"


@pytest.mark.asyncio
async def test_recall_with_no_match_is_a_normal_observation():
    agent = _planning(_ScriptedLLM([_call("recall_thread", query="nothing")]), _FakeThreadManager(recall_results=[]))
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["state_change"] and events[0].data["state"] == "planning"
    assert any("No earlier thread matched" in o for o in agent.ctx.observations)


@pytest.mark.asyncio
async def test_resume_switches_thread_and_injects_receipt():
    tm = _FakeThreadManager(recall_results=[{"thread_id": "t-paused", "title": "NAS setup", "date": "2026-06-30",
                                             "receipt": "Title: NAS setup", "matching_messages": [], "match_terms": []}])
    agent = _planning(_ScriptedLLM([_call("resume_thread", thread_id="t-paused")]), tm)
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["thread_started", "state_change"]
    assert events[0].data == {"thread_id": "t-paused", "title": "NAS setup", "reason": "resumed", "previous_thread_id": "t-open"}
    assert ("resume_thread", "t-paused", "t-open") in tm.calls
    assert agent.ctx.thread_id == "t-paused" and agent.ctx.thread_switched is True
    assert agent.ctx.conversation_history[0]["role"] == "system" and "NAS setup" in agent.ctx.conversation_history[0]["content"]


@pytest.mark.asyncio
async def test_resume_failure_keeps_the_open_thread():
    agent = _planning(_ScriptedLLM([_call("resume_thread", thread_id="t-none")]), _FakeThreadManager(resume_ok=False))
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["state_change"]
    assert agent.ctx.thread_id == "t-open" and agent.ctx.thread_switched is False
    assert any("Could not resume" in o for o in agent.ctx.observations)
