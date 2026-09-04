# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A9a: the turn lock serialises process() calls (a queued caller
sees conversation_status=waiting first), the initial PLANNING transition is
inside the try (a dead consumer or a bad transition still cleans up), a
superseded confirmation is ended as cancelled with a "not run — superseded"
block, terminal spawn ids land on the context, somatic events carry the
thread id, prompts receive continuity/history/tools_supported, and
memory.store_interaction is gone."""

import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from halbert_core.agents.states import AgentState, StateContext, ToolCall as RecordedToolCall
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.llm_client import LLMResponse
from halbert_core.prompts.agent_prompts import AgentPromptBuilder
from halbert_core.streaming.terminal_bridge import get_terminal_event_bus
from halbert_core.tools import ToolExecutor, ToolSafetyFramework
from halbert_core.tools.executor import ExecutionResult


class _SlowLLM:
    """Answers directly, but sleeps inside chat() so two turns would
    interleave if nothing serialised them."""

    def __init__(self, log, delay=0.05):
        self.log = log
        self.delay = delay

    async def chat(self, messages, tools=None, **kwargs):
        self.log.append("chat-start")
        await asyncio.sleep(self.delay)
        self.log.append("chat-end")
        return LLMResponse(content="done", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        await asyncio.sleep(self.delay)
        yield "done"


class _RecordingLLM(_SlowLLM):
    """_SlowLLM that keeps the messages[] array every call site sent."""

    def __init__(self, delay=0):
        super().__init__([], delay=delay)
        self.seen = []

    async def chat(self, messages, tools=None, **kwargs):
        self.seen.append(messages)
        return await super().chat(messages, tools=tools, **kwargs)

    async def stream(self, messages, **kwargs):
        self.seen.append(messages)
        async for chunk in super().stream(messages, **kwargs):
            yield chunk


def _agent(llm, **kw):
    return AgentStateMachine(
        llm_client=llm, tool_executor=ToolExecutor(safety=ToolSafetyFramework()), max_loops=5, **kw,
    )


def _high_risk_llm():
    llm = AsyncMock()
    tc = MagicMock()
    tc.function.name = "run_command"
    tc.function.arguments = {"command": "systemctl restart sshd"}
    llm.chat = AsyncMock(return_value=MagicMock(content="", tool_calls=[tc], plan=None))
    return llm


class _RecordingThreadManager:
    """Only end_turn: what _supersede_paused_turn needs from a ThreadManager."""

    def __init__(self):
        self.ended = []

    def end_turn(self, turn, *, assistant_text, blocks, terminal_block_ids, diff_proposals,
                 status="complete", thread_id_override=None, block_executions=None):
        self.ended.append(dict(
            turn=turn, assistant_text=assistant_text, blocks=blocks,
            terminal_block_ids=terminal_block_ids, diff_proposals=diff_proposals,
            status=status, thread_id_override=thread_id_override,
            block_executions=block_executions,
        ))


class TestTurnLock:
    @pytest.mark.asyncio
    async def test_two_concurrent_process_calls_serialise(self):
        log = []
        agent = _agent(_SlowLLM(log))
        assert isinstance(agent.turn_lock, asyncio.Lock)
        order = []

        async def run(sid):
            async for e in agent.process("hello", session_id=sid):
                if e.type in ("session_started", "session_ended"):
                    order.append((e.type, e.session_id))

        await asyncio.wait_for(asyncio.gather(run("A"), run("B")), timeout=5)
        assert order == [
            ("session_started", "A"), ("session_ended", "A"),
            ("session_started", "B"), ("session_ended", "B"),
        ]
        # chat() never overlapped: every start is followed by its own end.
        assert log and log == ["chat-start", "chat-end"] * (len(log) // 2)
        assert not agent.turn_lock.locked()
        assert agent.current_state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_lock_released_when_turn_pauses_and_new_message_supersedes(self):
        agent = _agent(_high_risk_llm())
        async for _ in agent.process("restart sshd", session_id="first"):
            pass
        assert agent.current_state == AgentState.AWAITING_CONFIRMATION
        assert "first" in agent.active_sessions
        assert not agent.turn_lock.locked()

        # A fresh turn must not raise "Invalid transition: AWAITING_CONFIRMATION -> PLANNING".
        agent.llm = _SlowLLM([], delay=0)
        types = [e.type async for e in agent.process("something else", session_id="second")]
        assert "session_ended" in types and "error" not in types
        assert "first" not in agent.active_sessions
        assert agent.current_state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_superseded_confirmation_is_recorded_on_the_receipt(self):
        # spec §5: a staged HIGH-risk command is auto-rejected when its turn is
        # superseded and the receipt records it as "not run — superseded".
        agent = _agent(_high_risk_llm())
        async for _ in agent.process("restart sshd", session_id="first"):
            pass
        assert agent.current_state == AgentState.AWAITING_CONFIRMATION
        paused = agent.active_sessions["first"]
        tm = _RecordingThreadManager()
        paused.thread_manager = tm
        paused.turn_context = object()   # what begin_turn hands back (A9c)

        agent.llm = _SlowLLM([], delay=0)
        async for _ in agent.process("something else", session_id="second"):
            pass
        assert len(tm.ended) == 1
        end = tm.ended[0]
        assert end["status"] == "cancelled" and end["assistant_text"] == ""
        assert end["terminal_block_ids"] == [] and end["diff_proposals"] == []
        assert end["thread_id_override"] is None
        assert end["blocks"] == [{
            "tool": "run_command", "args": {"command": "systemctl restart sshd"},
            "result": "not run — superseded", "exit": None, "status": "superseded",
        }]
        assert paused.turn_context is None          # ended once, never again
        assert "first" not in agent.active_sessions

    @pytest.mark.asyncio
    async def test_second_caller_sees_waiting_status_before_the_lock(self):
        # spec §12: a second /message during a turn is queued and emits
        # conversation_status: waiting.
        agent = _agent(_SlowLLM([], delay=0.2))
        first = agent.process("one", session_id="A")
        opened = await first.__anext__()
        assert opened.type == "session_started" and agent.turn_lock.locked()

        second_events = []

        async def run_b():
            async for e in agent.process("two", session_id="B"):
                second_events.append(e)

        task = asyncio.ensure_future(run_b())
        await asyncio.sleep(0.02)
        assert second_events, "B yielded nothing while A held the lock"
        assert second_events[0].type == "conversation_status"
        assert second_events[0].session_id == "B"
        assert second_events[0].data["status"] == "waiting"
        assert len(second_events) == 1              # nothing else until A releases the lock

        async for _ in first:
            pass
        await asyncio.wait_for(task, timeout=5)
        types = [e.type for e in second_events]
        assert types[:2] == ["conversation_status", "session_started"]
        assert "session_ended" in types and "error" not in types
        assert not agent.turn_lock.locked()

    @pytest.mark.asyncio
    async def test_state_resets_to_idle_when_the_consumer_disconnects(self):
        agent = _agent(_SlowLLM([], delay=0.3))

        async def consume():
            async for _ in agent.process("hello", session_id="gone"):
                pass

        task = asyncio.ensure_future(consume())
        await asyncio.sleep(0.05)  # inside PLANNING's chat()
        assert agent.current_state == AgentState.PLANNING
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not agent.turn_lock.locked()
        assert agent.current_state == AgentState.IDLE
        assert "gone" not in agent.active_sessions

    @pytest.mark.asyncio
    async def test_process_accepts_thread_kwargs(self):
        agent = _agent(_SlowLLM([], delay=0))
        async for _ in agent.process(
            "hi", session_id="kw", thread_id="t-1",
            continuity="<continuity>x</continuity>", thread_manager=None,
        ):
            pass
        assert agent.ctx.thread_id == "t-1"
        assert agent.ctx.continuity_hint == "<continuity>x</continuity>"


class TestPromptWiring:
    @pytest.mark.asyncio
    async def test_the_hint_and_the_history_leave_the_prose_prompts(self):
        """Merge D1/E-3: rewritten from test_prompts_receive_continuity_and_history.

        The hint used to be a prose section in both builders and the history a
        "## Earlier in this conversation" block in the answer prompt. Both now
        live in the messages array — the history as real turns, the hint glued
        to the front of the final user message — so passing either to a prose
        builder as well would send it twice. ``tools_supported`` still goes to
        the builders: it selects the preamble's wording, which is still theirs.
        """
        prompts = MagicMock()
        prompts.build_planning_prompt = MagicMock(return_value="plan")
        prompts.build_response_prompt = MagicMock(return_value="respond")
        prompts._continuity_section = MagicMock(return_value=["PREAMBLE", "<continuity>hint</continuity>"])
        agent = _agent(_SlowLLM([], delay=0), prompt_builder=prompts)
        history = [{"role": "user", "content": "earlier"}]
        async for _ in agent.process(
            "now", session_id="pw", conversation_history=history,
            continuity="<continuity>hint</continuity>",
        ):
            pass
        pk = prompts.build_planning_prompt.call_args.kwargs
        assert "continuity" not in pk and "history" not in pk
        assert pk["tools_supported"] is None
        rk = prompts.build_response_prompt.call_args.kwargs
        assert "continuity" not in rk and "history" not in rk
        assert rk["tools_supported"] is None
        # The builder still owns the wording; only where it lands changed.
        prompts._continuity_section.assert_called_with(
            "<continuity>hint</continuity>", None
        )

    @pytest.mark.asyncio
    async def test_the_continuity_hint_rides_the_last_message(self):
        """Merge D1: the hint is adjacent to the question, not in messages[0].

        A10 put it at the tail of the prose because a model whose context
        window is too small drops the HEAD of what it is sent. Array position
        serves that better: messages[0] is the instructions (plus the thread
        receipt), and the head is what Ollama cuts.
        """
        llm = _RecordingLLM()
        agent = _agent(llm, prompt_builder=AgentPromptBuilder())
        async for _ in agent.process(
            "start it", session_id="tail",
            conversation_history=[
                {"role": "user", "content": "Check nginx"},
                {"role": "assistant", "content": "Nginx is stopped."},
            ],
            continuity="<continuity>hint</continuity>",
        ):
            pass
        assert llm.seen, "no LLM call was made"
        for messages in llm.seen:
            assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
            assert "<continuity>hint</continuity>" in messages[-1]["content"]
            assert messages[-1]["content"].endswith("start it")
            assert "<continuity>" not in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_prompts_receive_tools_supported_from_the_client(self):
        prompts = MagicMock()
        prompts.build_planning_prompt = MagicMock(return_value="plan")
        prompts.build_response_prompt = MagicMock(return_value="respond")
        llm = _SlowLLM([], delay=0)
        llm.tools_supported = False   # set by the client after a no-tools fallback (A9d)
        agent = _agent(llm, prompt_builder=prompts)
        async for _ in agent.process("now", session_id="ts"):
            pass
        assert prompts.build_planning_prompt.call_args.kwargs["tools_supported"] is False
        assert prompts.build_response_prompt.call_args.kwargs["tools_supported"] is False

    def test_simple_planning_prompt_carries_the_hint(self):
        agent = _agent(_SlowLLM([], delay=0))
        agent.ctx = StateContext(
            session_id="s", request_id="r", user_query="q", continuity_hint="<continuity>h</continuity>",
        )
        p = agent._build_simple_planning_prompt("ctx")
        assert p.index("<continuity>h</continuity>") < p.index("User query: q")


class TestTerminalSessionIds:
    @pytest.mark.asyncio
    async def test_spawn_payloads_are_collected_once_on_ctx(self):
        agent = _agent(_SlowLLM([], delay=0))
        agent.ctx = StateContext(session_id="term", request_id="r", user_query="ls")

        async def fake_execute(tool_name, args, session_id=None, confirmed=False, speaker_role="admin"):
            bus = get_terminal_event_bus()
            bus.publish(session_id, {"kind": "spawn", "terminal_session_id": "t-1", "command": "ls", "pid": 1})
            bus.publish(session_id, {"kind": "output", "terminal_session_id": "t-1", "data": "a\n"})
            bus.publish(session_id, {"kind": "spawn", "terminal_session_id": "t-1", "command": "ls", "pid": 1})
            bus.publish(session_id, {"kind": "complete", "terminal_session_id": "t-1", "exit_code": 0})
            return ExecutionResult(success=True, result="a")

        agent.tools.execute = fake_execute
        sink = []
        events = [e async for e in agent._run_tool_streaming("run_command", {"command": "ls"}, False, sink)]
        assert agent.ctx.terminal_block_ids == ["t-1"]
        assert [e.type for e in events].count("terminal_spawn") == 2
        assert sink[0].success is True


class TestNoMemoryStoreInteraction:
    @pytest.mark.asyncio
    async def test_store_interaction_is_never_called(self):
        memory = MagicMock()
        memory.recall = AsyncMock(return_value=[])
        memory.store_interaction = AsyncMock()
        agent = _agent(_SlowLLM([], delay=0), memory_service=memory)
        async for _ in agent.process("what is my hostname?", session_id="mem"):
            pass
        memory.store_interaction.assert_not_awaited()
        assert agent.ctx.response_chunks == ["done"]


class TestSomaticThreadId:
    @pytest.mark.asyncio
    async def test_somatic_block_event_carries_thread_id_or_session_id(self):
        # spec §8: somatic blocks are tagged with the hidden thread; the SSE
        # session_id stays per turn for routing.
        agent = _agent(_SlowLLM([], delay=0))
        block = SimpleNamespace(
            block_type="finding", id="blk-1", status="active", session_id="som",
            finding_id="f1", proposal_id=None, approval_request_id=None,
            action_id=None, reflection_id=None,
        )
        agent.ctx = StateContext(session_id="som", request_id="r", user_query="q", thread_id="t-42")
        event = await agent._emit_somatic_block(block)
        assert event.type == "somatic_block" and event.session_id == "som"
        assert event.data["thread_id"] == "t-42" and event.data["block_id"] == "blk-1"
        agent.ctx.thread_id = None
        assert (await agent._emit_somatic_block(block)).data["thread_id"] == "som"


class TestReviewFollowUps:
    """Fixes from the A9a code review: a superseded turn keeps the work it
    already did, a queued turn clears its own "waiting" badge, and the wait
    for the lock is bounded."""

    @pytest.mark.asyncio
    async def test_a_superseded_turn_keeps_the_work_it_already_did(self):
        # ThreadManager.end_turn is the only writer of the assistant row, so
        # a turn that ran `ls`, spawned a terminal and proposed a diff before
        # pausing must carry all of it onto the receipt — not just the
        # command it never ran.
        agent = _agent(_high_risk_llm())
        async for _ in agent.process("restart sshd", session_id="first"):
            pass
        assert agent.current_state == AgentState.AWAITING_CONFIRMATION
        paused = agent.active_sessions["first"]
        tm = _RecordingThreadManager()
        paused.thread_manager = tm
        paused.turn_context = object()
        paused.tool_calls.insert(0, RecordedToolCall(
            id="ran-1", name="run_command", args={"command": "ls"},
            status="success", result="Exit code 0\na",
        ))
        paused.terminal_block_ids.append("term-9")
        paused.response_chunks.append("partial ")
        paused.pending_diffs["d-1"] = {
            "file_path": "/etc/hosts", "edit_blocks": [], "status": "pending",
        }

        agent.llm = _SlowLLM([], delay=0)
        async for _ in agent.process("something else", session_id="second"):
            pass

        assert len(tm.ended) == 1
        end = tm.ended[0]
        assert end["status"] == "cancelled"
        assert end["assistant_text"] == "partial "
        assert end["terminal_block_ids"] == ["term-9"]
        assert end["diff_proposals"] == [{
            "diff_id": "d-1", "file_path": "/etc/hosts",
            "edit_blocks": [], "status": "pending",
        }]
        assert len(end["blocks"]) == 2
        ran, staged = end["blocks"]
        assert ran["tool"] == "run_command" and ran["args"] == {"command": "ls"}
        assert ran["exit"] == 0 and ran["status"] == "success" and ran["execution_id"] == "ran-1"
        assert staged == {
            "tool": "run_command", "args": {"command": "systemctl restart sshd"},
            "result": "not run — superseded", "exit": None, "status": "superseded",
        }

    @pytest.mark.asyncio
    async def test_a_queued_turn_clears_its_waiting_badge_when_it_starts(self):
        # The frontend reducer keeps the last conversation_status string, so
        # "waiting" has to be cleared as the queued turn starts working —
        # not left standing while it plans, runs commands and streams.
        agent = _agent(_SlowLLM([], delay=0.2))
        first = agent.process("one", session_id="A")
        assert (await first.__anext__()).type == "session_started"

        second_events = []

        async def run_b():
            async for e in agent.process("two", session_id="B"):
                second_events.append(e)

        task = asyncio.ensure_future(run_b())
        await asyncio.sleep(0.02)
        async for _ in first:
            pass
        await asyncio.wait_for(task, timeout=5)

        types = [e.type for e in second_events]
        assert types[:3] == ["conversation_status", "session_started", "conversation_status"]
        assert second_events[0].data["status"] == "waiting"
        assert second_events[2].data["status"] == "in_progress"
        # …and it is cleared before any work, not at the end of the turn.
        assert types.index("state_change") > 2
        assert "session_ended" in types and "error" not in types

    @pytest.mark.asyncio
    async def test_an_unqueued_turn_only_emits_its_closing_status(self):
        # The extra in_progress is for queued turns only: a turn that never
        # waited still emits nothing but the status it ends on.
        agent = _agent(_SlowLLM([], delay=0))
        events = [e async for e in agent.process("solo", session_id="solo")]
        assert [e.data["status"] for e in events if e.type == "conversation_status"] == ["success"]

    @pytest.mark.asyncio
    async def test_a_wedged_turn_surfaces_as_an_error_instead_of_hanging(self):
        # The lock is held across every yield of process(); if a release is
        # ever missed the next message must fail visibly rather than queue
        # behind a badge that never changes.
        agent = _agent(_SlowLLM([], delay=0.4))
        agent.TURN_LOCK_TIMEOUT_S = 0.05
        first = agent.process("one", session_id="A")
        assert (await first.__anext__()).type == "session_started"

        events = [e async for e in agent.process("two", session_id="B")]
        assert [e.type for e in events] == [
            "conversation_status", "conversation_status", "error", "session_ended",
        ]
        # The badge this caller set to "waiting" before blocking has to be
        # cleared by the give-up path too: the reducer keeps the last status
        # string and neither error nor session_ended touches it.
        assert [e.data["status"] for e in events[:2]] == ["waiting", "error"]
        assert events[2].data["recoverable"] is True
        assert "B" not in agent.active_sessions
        assert agent.ctx.session_id == "A"   # the running turn is untouched

        async for _ in first:
            pass
        assert not agent.turn_lock.locked()
        assert agent.current_state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_closing_an_abandoned_stream_settles_the_machine(self):
        # What routes/agent.py relies on by consuming process() under
        # contextlib.aclosing: closing the generator runs its finally, so the
        # lock is released and the machine is IDLE without waiting for the
        # event loop's async-generator finalizer.
        from contextlib import aclosing

        agent = _agent(_SlowLLM([], delay=0))
        async with aclosing(agent.process("hi", session_id="ab")) as stream:
            async for e in stream:
                if e.type == "session_started":
                    break
        assert not agent.turn_lock.locked()
        assert agent.current_state == AgentState.IDLE
        assert "ab" not in agent.active_sessions


class TestConfirmActionLock:
    """confirm_action() waits on the same lock as process(), so it needs the
    same bound: the UI aborts the paused turn's SSE and POSTs /confirm
    immediately, and that generator may still be holding the lock."""

    async def _paused(self):
        agent = _agent(_high_risk_llm())
        async for _ in agent.process("restart sshd", session_id="first"):
            pass
        assert agent.current_state == AgentState.AWAITING_CONFIRMATION
        assert not agent.turn_lock.locked()
        agent.llm = _SlowLLM([], delay=0)   # the re-plan after a rejection
        return agent, agent.active_sessions["first"].pending_confirmation["action_id"]

    @pytest.mark.asyncio
    async def test_confirm_waits_for_the_lock_and_then_runs(self):
        agent, action_id = await self._paused()
        await agent.turn_lock.acquire()     # stand in for the closing turn

        events = []

        async def confirm():
            async for e in agent.confirm_action("first", action_id, confirmed=False):
                events.append(e)

        task = asyncio.ensure_future(confirm())
        await asyncio.sleep(0.05)
        assert events == [], "confirm ran while another turn held the lock"

        agent.turn_lock.release()
        await asyncio.wait_for(task, timeout=5)
        types = [e.type for e in events]
        assert "session_ended" in types and "error" not in types
        assert not agent.turn_lock.locked()
        assert agent.current_state == AgentState.IDLE
        assert "first" not in agent.active_sessions

    @pytest.mark.asyncio
    async def test_confirm_gives_up_instead_of_hanging_forever(self):
        # Pre-A9a confirm_action took no lock at all, so a wedged turn must
        # not turn /confirm into a request that never answers and never
        # closes its stream.
        agent, action_id = await self._paused()
        agent.TURN_LOCK_TIMEOUT_S = 0.05
        await agent.turn_lock.acquire()

        events = [
            e async for e in agent.confirm_action("first", action_id, confirmed=True)
        ]
        assert [e.type for e in events] == [
            "conversation_status", "error", "session_ended",
        ]
        assert events[0].data["status"] == "error"
        assert events[1].data["recoverable"] is True
        # The paused turn is untouched: nothing ran, and the confirmation is
        # still there to retry.
        assert agent.current_state == AgentState.AWAITING_CONFIRMATION
        assert agent.active_sessions["first"].pending_confirmation["action_id"] == action_id
        assert agent.turn_lock.locked()     # still ours, never stolen
        agent.turn_lock.release()

    @pytest.mark.asyncio
    async def test_confirm_releases_the_lock_on_every_early_return(self):
        agent, action_id = await self._paused()
        for sid, aid in (("nobody", action_id), ("first", "wrong-id")):
            types = [
                e.type async for e in agent.confirm_action(sid, aid, confirmed=True)
            ]
            assert types == ["error"]
            assert not agent.turn_lock.locked()

    @pytest.mark.asyncio
    async def test_confirm_releases_the_lock_when_its_stream_is_abandoned(self):
        # routes/agent.py consumes confirm_action() under contextlib.aclosing
        # for exactly this: closing the generator must run its finally.
        from contextlib import aclosing

        agent, action_id = await self._paused()
        async with aclosing(
            agent.confirm_action("first", action_id, confirmed=False)
        ) as stream:
            async for _ in stream:
                break
        assert not agent.turn_lock.locked()

