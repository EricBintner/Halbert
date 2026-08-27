# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A9c: process() calls ThreadManager.begin_turn after taking the
lock, seeds the context from the TurnContext, emits turn_persisted (and
thread_recalled for auto recalls), and calls end_turn in its finally."""

import asyncio
import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

from halbert_core.agents.states import AgentState, StateContext
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.llm_client import LLMResponse, ToolCall, FunctionCall
from halbert_core.streaming.terminal_bridge import get_terminal_event_bus
from halbert_core.tools import ToolExecutor, ToolSafetyFramework
from halbert_core.tools.executor import ExecutionResult


@dataclass
class _Turn:
    thread_id: str
    turn_id: str
    user_message_id: Optional[int]
    history: List[Dict[str, Any]]
    hint: str
    recalled: List[Dict[str, Any]] = field(default_factory=list)
    decision: Any = None


class _FakeThreadManager:
    def __init__(self, hint="", history=None, recalled=None, fail_begin=False):
        self.hint, self.history, self.recalled, self.fail_begin = hint, history or [], recalled or [], fail_begin
        self.begun, self.ended = [], []

    def begin_turn(self, query, signals, session_id):
        if self.fail_begin:
            raise RuntimeError("db locked")
        self.begun.append((query, signals, session_id))
        return _Turn("t-open", f"turn-{len(self.begun)}", 1, list(self.history), self.hint, list(self.recalled))

    def end_turn(self, turn, *, assistant_text, blocks, terminal_session_ids, diff_proposals, status="complete", thread_id_override=None):
        self.ended.append(dict(turn=turn, assistant_text=assistant_text, blocks=blocks, terminal_session_ids=terminal_session_ids,
                               diff_proposals=diff_proposals, status=status, thread_id_override=thread_id_override))

    def new_thread(self, title, reason, *, from_thread_id):
        return "t-new"

    def recall(self, query=None, thread_id=None, *, exclude_thread_id=None):
        return []

    def resume_thread(self, thread_id, *, from_thread_id):
        return False


class _LLM:
    def __init__(self, responses=None, delay=0.0):
        self.responses, self.delay = list(responses or []), delay

    async def chat(self, messages, tools=None, **kwargs):
        await asyncio.sleep(self.delay)
        return self.responses.pop(0) if self.responses else LLMResponse(content="answer", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        await asyncio.sleep(self.delay)
        yield "the "
        yield "answer"


def _agent(llm):
    return AgentStateMachine(llm_client=llm, tool_executor=ToolExecutor(safety=ToolSafetyFramework()), max_loops=5)


def _tool(name, **args):
    return LLMResponse(content="", tool_calls=[ToolCall(id="c1", function=FunctionCall(name=name, arguments=args))])


@pytest.mark.asyncio
async def test_context_seeded_turn_persisted_and_auto_recall():
    tm = _FakeThreadManager(
        hint='<continuity>Thread: "Scanner share"</continuity>',
        history=[{"role": "user", "content": "earlier"}],
        recalled=[{"thread_id": "t-9", "title": "Samba media share", "date": "2026-07-14",
                   "receipt": "Title: Samba media share", "match_terms": ["samba"],
                   "last_turn_id": "turn-old"}],
    )
    agent = _agent(_LLM())
    events = [e async for e in agent.process("add a share", session_id="s1", thread_manager=tm)]
    types = [e.type for e in events]
    assert types.index("session_started") < types.index("thread_recalled") < types.index("turn_persisted") < types.index("state_change")
    assert next(e for e in events if e.type == "turn_persisted").data == {"thread_id": "t-open", "turn_id": "turn-1"}
    rec = next(e for e in events if e.type == "thread_recalled").data
    assert rec["thread_id"] == "t-9" and rec["mode"] == "auto"
    assert rec["last_turn_id"] == "turn-old"
    assert tm.begun[0][0] == "add a share" and tm.begun[0][2] == "s1"
    assert tm.begun[0][1].detected_domains is not None   # a MessageSignals
    assert agent.ctx.thread_id == "t-open" and agent.ctx.continuity_hint.startswith("<continuity>")
    assert agent.ctx.conversation_history == [{"role": "user", "content": "earlier"}]
    assert agent.ctx.retrieved_context[0]["source"] == "thread"
    assert agent.ctx.recalled_threads[0]["thread_id"] == "t-9"


@pytest.mark.asyncio
async def test_begin_turn_failure_or_no_manager_still_answers():
    tm = _FakeThreadManager(fail_begin=True)
    types = [e.type async for e in _agent(_LLM()).process("hello", session_id="s3", thread_manager=tm)]
    assert "thread_store_error" in types and "turn_persisted" not in types
    assert "response_complete" in types and tm.ended == []
    types = [e.type async for e in _agent(_LLM()).process("hello", session_id="s4")]
    assert "turn_persisted" not in types and "thread_store_error" not in types and "response_complete" in types


@pytest.mark.asyncio
async def test_end_turn_receives_text_blocks_terminals_status():
    tm = _FakeThreadManager()
    agent = _agent(_LLM([_tool("run_command", command="uptime")]))

    async def fake_execute(tool_name, args, session_id=None, confirmed=False):
        get_terminal_event_bus().publish(session_id, {"kind": "spawn", "terminal_session_id": "term-7", "command": "uptime", "pid": 3})
        get_terminal_event_bus().publish(session_id, {"kind": "complete", "terminal_session_id": "term-7", "exit_code": 0})
        return ExecutionResult(success=True, result="22:50 up 1 day")

    agent.tools.execute = fake_execute
    async for _ in agent.process("how long up?", session_id="s5", thread_manager=tm):
        pass
    assert len(tm.ended) == 1
    end = tm.ended[0]
    assert end["turn"].turn_id == "turn-1" and end["assistant_text"] == "the answer"
    assert end["status"] == "complete" and end["thread_id_override"] is None
    assert end["terminal_session_ids"] == ["term-7"] and end["diff_proposals"] == []
    block = end["blocks"][0]
    assert block["tool"] == "run_command" and block["args"] == {"command": "uptime"}
    assert block["result"] == "22:50 up 1 day" and block["exit"] == 0


@pytest.mark.asyncio
async def test_thread_switch_passes_override_and_drops_meta_blocks():
    tm = _FakeThreadManager()
    agent = _agent(_LLM([_tool("new_thread", title="New", reason="r")]))
    async for _ in agent.process("new subject", session_id="s6", thread_manager=tm):
        pass
    assert tm.ended[0]["thread_id_override"] == "t-new" and tm.ended[0]["blocks"] == []


@pytest.mark.asyncio
async def test_cancelled_and_interrupted_statuses():
    tm = _FakeThreadManager()
    agent = _agent(_LLM(delay=0.3))

    async def consume_and_cancel():
        async for e in agent.process("slow", session_id="s7", thread_manager=tm):
            if e.type == "state_change" and e.data["state"] == "planning":
                agent.cancel_session("s7")

    await asyncio.wait_for(consume_and_cancel(), timeout=5)
    assert tm.ended[0]["status"] == "cancelled"

    async def consume():
        async for _ in agent.process("slow", session_id="s8", thread_manager=tm):
            pass

    task = asyncio.ensure_future(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert tm.ended[1]["status"] == "interrupted" and tm.ended[1]["assistant_text"] == ""


@pytest.mark.asyncio
async def test_paused_turn_ends_only_after_confirmation():
    tm = _FakeThreadManager()
    llm = AsyncMock()
    tc = MagicMock()
    tc.function.name = "run_command"
    tc.function.arguments = {"command": "systemctl restart sshd"}
    calls = {"n": 0}

    async def _chat(*a, **k):
        calls["n"] += 1
        return MagicMock(content="", tool_calls=[tc] if calls["n"] == 1 else [], plan=None)

    async def _stream(messages, **kwargs):
        yield "restarted"

    llm.chat, llm.stream = AsyncMock(side_effect=_chat), _stream
    agent = _agent(llm)
    events = [e async for e in agent.process("restart sshd", session_id="s9", thread_manager=tm)]
    assert agent.current_state == AgentState.AWAITING_CONFIRMATION and tm.ended == []
    confirm = next(e for e in events if e.type == "tool_confirmation_required")
    agent.tools.execute = AsyncMock(return_value=ExecutionResult(success=True, result="restarted"))
    async for _ in agent.confirm_action("s9", confirm.data["execution_id"], True):
        pass
    assert len(tm.ended) == 1
    assert tm.ended[0]["status"] == "complete" and tm.ended[0]["assistant_text"] == "restarted"


@pytest.mark.asyncio
async def test_stream_abandoned_during_begin_turn_still_ends_the_turn():
    """A consumer that goes away while _begin_turn is still yielding.

    _begin_turn() runs before the try whose finally ends the turn, so the
    stop button / a client disconnect landing on that yield (aclose() ->
    GeneratorExit) used to leave the user row in_progress with no assistant
    row and no receipt. process()'s outer finally has to end it.
    """
    tm = _FakeThreadManager()
    agent = _agent(_LLM(delay=0.3))
    gen = agent.process("add a share", session_id="s10", thread_manager=tm)
    seen = []
    async for e in gen:
        seen.append(e.type)
        if e.type == "turn_persisted":
            break
    await gen.aclose()

    assert seen[-1] == "turn_persisted" and len(tm.begun) == 1
    assert len(tm.ended) == 1
    assert tm.ended[0]["turn"].turn_id == "turn-1"
    assert tm.ended[0]["status"] == "interrupted"
    assert tm.ended[0]["assistant_text"] == "" and tm.ended[0]["blocks"] == []
    assert not agent.turn_lock.locked()
    assert agent.current_state == AgentState.IDLE


@pytest.mark.asyncio
async def test_queued_turn_abandoned_before_planning_is_not_persisted_as_complete():
    """A queued turn dropped on its own in_progress event is interrupted.

    The queued caller's ``conversation_status: in_progress`` is the one
    statement inside process()'s inner try that runs *before* the PLANNING
    transition, so the machine is still IDLE there. Reading IDLE as "ran to
    the end" wrote that empty turn to the store as ``complete`` — a row no
    longer ``in_progress``, which boot's ``mark_interrupted()`` can never
    heal.
    """
    tm = _FakeThreadManager()
    agent = _agent(_LLM(delay=0.5))

    async def first():
        async for _ in agent.process("first", session_id="q1", thread_manager=tm):
            pass

    task = asyncio.ensure_future(first())
    await asyncio.sleep(0.05)          # the first turn now holds the turn lock
    gen = agent.process("second", session_id="q2", thread_manager=tm)
    seen = []
    async for e in gen:
        seen.append((e.type, e.data.get("status")))
        if e.type == "conversation_status" and e.data.get("status") == "in_progress":
            break
    await gen.aclose()
    await asyncio.wait_for(task, timeout=10)

    # The second turn really did queue (otherwise this proves nothing).
    assert ("conversation_status", "waiting") in seen
    assert seen[-1] == ("conversation_status", "in_progress")
    assert [e["turn"].turn_id for e in tm.ended] == ["turn-1", "turn-2"]
    assert tm.ended[0]["status"] == "complete" and tm.ended[0]["assistant_text"] == "the answer"
    assert tm.ended[1]["status"] == "interrupted" and tm.ended[1]["assistant_text"] == ""
    assert not agent.turn_lock.locked()
    assert agent.current_state == AgentState.IDLE


def _confirming_agent():
    """An agent whose first plan stages a HIGH-risk command, then answers."""
    llm = AsyncMock()
    tc = MagicMock()
    tc.function.name = "run_command"
    tc.function.arguments = {"command": "systemctl restart sshd"}
    calls = {"n": 0}

    async def _chat(*a, **k):
        calls["n"] += 1
        return MagicMock(content="", tool_calls=[tc] if calls["n"] == 1 else [], plan=None)

    async def _stream(messages, **kwargs):
        yield "restarted"

    llm.chat, llm.stream = AsyncMock(side_effect=_chat), _stream
    return _agent(llm)


@pytest.mark.asyncio
async def test_cancelling_a_paused_turn_ends_it():
    """cancel_session() on a turn paused at AWAITING_CONFIRMATION.

    The paused turn's SSE stream has already closed, so no finally will run
    for it again: dropping the session without ending the turn left the user
    row in_progress forever (confirm_action is never called, and
    _supersede_paused_turn can no longer find the session on the next
    message). The staged action never ran, so it is recorded as not run.
    """
    tm = _FakeThreadManager()
    agent = _confirming_agent()
    async for _ in agent.process("restart sshd", session_id="c1", thread_manager=tm):
        pass
    assert agent.current_state == AgentState.AWAITING_CONFIRMATION and tm.ended == []

    assert agent.cancel_session("c1") is True
    assert len(tm.ended) == 1
    end = tm.ended[0]
    assert end["turn"].turn_id == "turn-1" and end["status"] == "cancelled"
    staged = end["blocks"][-1]
    assert staged["tool"] == "run_command"
    assert staged["args"] == {"command": "systemctl restart sshd"}
    assert staged["result"] == "not run — superseded" and staged["exit"] is None
    assert agent.current_state == AgentState.IDLE
    assert not agent.turn_lock.locked()

    # The next turn is a normal one, and the cancelled turn is not written twice.
    async for _ in agent.process("thanks", session_id="c2", thread_manager=tm):
        pass
    assert [e["turn"].turn_id for e in tm.ended] == ["turn-1", "turn-2"]
    assert tm.ended[1]["status"] == "complete"


@pytest.mark.asyncio
async def test_cancelling_a_live_turn_leaves_the_write_to_the_finally():
    """cancel_session() must not end a turn that is still running.

    A live turn is ended by process()'s finally, with the text, blocks and
    terminal ids it finished with. cancel_session only asks the drive loop
    to stop, and the handler that is running keeps going for a moment
    afterwards — writing the turn from cancel_session would persist a
    truncated record and make the finally's own end_turn a no-op.
    """
    tm = _FakeThreadManager()
    agent = _agent(_LLM(delay=0.05))
    async for e in agent.process("slow", session_id="c3", thread_manager=tm):
        if e.type == "state_change" and e.data["state"] == "planning":
            agent.cancel_session("c3")
            assert tm.ended == []      # the running turn still owns its write
    assert [end["status"] for end in tm.ended] == ["cancelled"]


@pytest.mark.asyncio
async def test_cancelling_a_session_no_turn_is_answering_settles_it():
    """Stop on a session with no turn in flight has to settle it here.

    The flag alone is enough while a turn is running: ``_drive`` polls it and
    ``process()``'s finally does the teardown with what the turn really
    finished with (above). But when nothing is running, no finally will ever
    run for that session again — so raising the flag and stopping there left
    the entry in ``active_sessions``, which is what ``/api/agent/sessions``
    and ``/health`` report as a live turn, and left its persisted user row
    ``in_progress`` until some later message happened to supersede it. A
    turn paused on a confirmation is only the best-known case of this; the
    rule is the same for any session nothing is answering.
    """
    tm = _FakeThreadManager()
    agent = _agent(_LLM())
    # The state a stranded session leaves behind: registered, its turn
    # persisted and still open, and no live generator to end it.
    turn = tm.begin_turn("uptime?", None, "s-stray")
    ctx = StateContext(session_id="s-stray", request_id="r", user_query="uptime?")
    ctx.thread_manager = tm
    ctx.turn_context = turn
    ctx.response_chunks.append("half an ")
    agent.active_sessions["s-stray"] = ctx
    agent.current_state = AgentState.PLANNING

    assert agent.cancel_session("s-stray") is True
    assert agent.cancelled["s-stray"] is True
    assert "s-stray" not in agent.active_sessions, "a stopped session still looks live"
    assert agent.current_state == AgentState.IDLE
    # Ended once, as cancelled, keeping what it had already said.
    assert [e["status"] for e in tm.ended] == ["cancelled"]
    assert tm.ended[0]["assistant_text"] == "half an "

    # The next turn is a normal one and the stopped turn is not written twice.
    async for _ in agent.process("thanks", session_id="s-next", thread_manager=tm):
        pass
    assert [e["status"] for e in tm.ended] == ["cancelled", "complete"]


@pytest.mark.asyncio
async def test_cancelling_a_running_turn_leaves_the_session_to_its_own_cleanup():
    """The other side of that rule, and the force-reset that must not return.

    While a turn is in flight the stop button may only raise the flag.
    Evicting the session and resetting the machine to IDLE from here — what
    the route used to do — does not stop anything: the handler that is
    running keeps streaming its answer while the next transition fights the
    state it was reset to, and the turn's own finally then finds nothing
    left to write.
    """
    tm = _FakeThreadManager()
    agent = _agent(_LLM(delay=0.05))
    at_the_stop = []
    async for e in agent.process("slow", session_id="c4", thread_manager=tm):
        if e.type == "state_change" and e.data["state"] == "planning":
            agent.cancel_session("c4")
            at_the_stop.append(("c4" in agent.active_sessions, agent.current_state))

    assert at_the_stop, "the turn never reached planning"
    registered, state = at_the_stop[0]
    assert registered is True, "the running turn's session was evicted under it"
    assert state != AgentState.IDLE, "the machine was force-reset under a running turn"
    # Its own cleanup then settles it, once, with what it really finished with.
    assert "c4" not in agent.active_sessions and agent.current_state == AgentState.IDLE
    assert [e["status"] for e in tm.ended] == ["cancelled"]
