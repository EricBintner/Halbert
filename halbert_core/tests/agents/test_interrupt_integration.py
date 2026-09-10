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


class TestStopCompletionRace:
    """B3: a stop issued as the turn completes produces "stopped" or
    "turn completed, stop declined" — never both, never a retry."""

    @pytest.mark.asyncio
    async def test_stop_at_the_finalize_edge_declines(self):
        # The exact sliver: the generator is suspended on its session_ended
        # yield. The turn has finalized (the answer committed, the finalize
        # stamp taken) but has not settled (lock held, session still
        # registered) — the interleaving a concurrent stop actually hits.
        agent = _agent(_SlowLLM(delay=0))
        events = []
        async with aclosing(agent.process("hello", session_id="edge")) as stream:
            async for e in stream:
                events.append(e)
                if e.type == "session_ended":
                    break
        types = [e.type for e in events]
        assert "response_complete" in types             # the turn delivered
        assert agent.request_stop("edge") == "turn completed, stop declined"
        assert agent.cancelled == {}                    # and never fired the flag
        assert agent.current_state == AgentState.IDLE   # the aclose settled it
        assert not agent._turn_in_flight()

    @pytest.mark.asyncio
    async def test_stop_during_response_stream_cuts_before_the_commit(self):
        agent = _agent(_SlowLLM(delay=0.05))
        events = []
        outcome = None
        async for e in agent.process("hello", session_id="midstream"):
            events.append(e)
            if e.type == "response_chunk" and outcome is None:
                outcome = agent.request_stop("midstream")
        assert outcome == "stopped"
        types = [e.type for e in events]
        assert "cancelled" in types
        assert "response_complete" not in types
        assert types.count("session_started") == 1      # never a retry
        assert agent.current_state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_the_race_lands_on_exactly_one_outcome(self):
        # A sweep across delays: wherever the stop lands, exactly one of
        # the two outcomes holds, with its matching event stream.
        for i in range(6):
            agent = _agent(_SlowLLM(delay=0.02))
            task = asyncio.ensure_future(
                _collect(agent.process("hello", session_id="race"))
            )
            await asyncio.sleep(0.02 * i)
            outcome = agent.request_stop("race")
            events = await asyncio.wait_for(task, timeout=5)
            types = [e.type for e in events]
            assert outcome in ("stopped", "turn completed, stop declined")
            if outcome == "stopped":
                assert "cancelled" in types
                assert "response_complete" not in types
            else:
                assert "response_complete" in types
                assert "cancelled" not in types
            assert types.count("session_started") == 1  # never a retry
            assert agent.current_state == AgentState.IDLE


class TestSteer:
    @pytest.mark.asyncio
    async def test_steer_applies_to_the_last_tool_result_at_the_boundary(self):
        llm = _ToolThenAnswerLLM()
        agent = _agent(llm)

        async def fake_execute(tool_name, args, session_id=None, confirmed=False,
                               speaker_role="admin"):
            # A mid-turn arrival while the tool runs (a different request
            # in production; the same task here, which changes nothing —
            # the slot is a plain cross-request surface).
            assert agent.request_steer("also check the logs")["accepted"] is True
            return ExecutionResult(success=True, result="127.0.0.1 localhost")

        agent.tools.execute = fake_execute
        await _collect(agent.process("read the hosts file", session_id="steer"))

        # The steer applied to the LAST tool result at the batch boundary,
        # inside the A07-G4 labelled wrapper.
        assert any(
            "[steered]\nalso check the logs\n[/steered]" in o
            for o in agent.ctx.observations
        )
        # And the next model call actually saw it (the planning prompt rides
        # the leading instructions, so the whole messages array is checked).
        assert any(
            "also check the logs" in str(m)
            for m in llm.seen[1:]
        )
        assert agent._pending_steer == {}

    @pytest.mark.asyncio
    async def test_steer_before_any_tool_becomes_its_own_observation(self):
        llm = _SlowLLM(delay=0.15)
        agent = _agent(llm)
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="early")))
        await asyncio.sleep(0.03)          # inside PLANNING's chat()
        assert agent.request_steer("and the camera too")["accepted"] is True
        await asyncio.wait_for(task, timeout=5)
        # No tool result existed to append to, so the steer entered the
        # observations as its own line and the model still saw it.
        assert agent.ctx.observations[0] == (
            "[steered]\nand the camera too\n[/steered]"
        )
        assert any("and the camera too" in str(m) for m in llm.seen)

    @pytest.mark.asyncio
    async def test_the_pending_steers_concatenate(self):
        """A07-G6: this used to assert the first steer was thrown away.

        The slot was replace-not-grow, so a second arrival before the
        batch boundary erased the first -- after both had been answered
        ``steer_accepted``. Every accepted steer is delivered now;
        ``replaced`` keeps its name and means "one was already pending".
        """
        agent = _agent(_SlowLLM(delay=0.15))
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="slot")))
        await asyncio.sleep(0.03)
        first = agent.request_steer("first steer")
        second = agent.request_steer("second steer")
        assert first["replaced"] is False
        assert second["replaced"] is True
        assert agent._pending_steer["slot"] == ["first steer", "second steer"]
        await asyncio.wait_for(task, timeout=5)
        joined = "\n".join(agent.ctx.observations)
        assert "second steer" in joined
        assert "first steer" in joined

    @pytest.mark.asyncio
    async def test_an_unapplied_steer_leaves_no_slot_behind(self):
        # A steer that never finds a batch boundary (the turn is stopped
        # first) leaves the slot via _settle_turn — never a stale text for
        # a later turn under the same session id.
        agent = _agent(_SlowLLM(delay=0.2))
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="late")))
        await asyncio.sleep(0.03)
        agent.request_steer("too late")
        assert agent.request_stop("late") == "stopped"
        await asyncio.wait_for(task, timeout=5)
        assert agent._pending_steer == {}


class TestMidturnArrivals:
    """B2's never-silently-dropped invariant: every arrival while busy
    yields a verdict the requester can observe."""

    @pytest.mark.asyncio
    async def test_text_while_busy_steers_with_an_observable_event(self):
        agent = _agent(_SlowLLM(delay=0.15))
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="busy")))
        await asyncio.sleep(0.03)

        decision, events = agent.handle_midturn_arrival("arr-1", "also check the logs")
        assert decision.verb is Verdict.STEER
        assert [e.type for e in events] == ["steer_accepted"]
        assert events[0].data["replaced"] is False
        assert agent._pending_steer["busy"] == ["also check the logs"]

        await asyncio.wait_for(task, timeout=5)
        assert any(
            "[steered]\nalso check the logs\n[/steered]" in o
            for o in agent.ctx.observations
        )

    @pytest.mark.asyncio
    async def test_stop_while_busy_stops_with_existing_event_vocabulary(self):
        agent = _agent(_SlowLLM(delay=0.15))
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="busy")))
        await asyncio.sleep(0.03)

        decision, events = agent.handle_midturn_arrival("arr-1", "/stop")
        assert decision.verb is Verdict.STOP
        assert [e.type for e in events] == ["cancelled", "session_ended"]
        assert agent.cancelled["busy"] is True

        events_main = await asyncio.wait_for(task, timeout=5)
        assert "cancelled" in [e.type for e in events_main]

    @pytest.mark.asyncio
    async def test_guidance_during_a_tool_batch_steers_and_the_turn_completes(self):
        """Never kill a tool to deliver *guidance*: plain text steers.

        R-01 Phase B (A07-G2): this used to send "/stop" and assert the
        stop demoted to a steer. The demotion rule is about guidance --
        transcribed onto the stop verb it left the algebra unable to stop
        a running command, which is what a stop is for. The rule itself
        stands, pinned here on the text it was always about; the stop
        half is pinned in tests/agents/test_stop_semantics.py.
        """
        llm = _ToolThenAnswerLLM()
        agent = _agent(llm)
        seen = {}

        async def fake_execute(tool_name, args, session_id=None, confirmed=False,
                               speaker_role="admin"):
            decision, events = agent.handle_midturn_arrival(
                "arr", "actually, check the logs instead"
            )
            seen["decision"] = decision
            seen["events"] = events
            return ExecutionResult(success=True, result="ok")

        agent.tools.execute = fake_execute
        await _collect(agent.process("read the hosts file", session_id="demote"))

        decision = seen["decision"]
        assert decision.verb is Verdict.STEER
        assert seen["events"][0].type == "steer_accepted"
        # The text rode the steer into the last tool result, and the tool
        # was never killed: the turn ran to its answer.
        assert any(
            "[steered]\nactually, check the logs instead\n[/steered]" in o
            for o in agent.ctx.observations
        )
        assert agent.current_state == AgentState.IDLE

    def test_arrival_when_idle_is_an_ordinary_turn(self):
        agent = _agent(_SlowLLM(delay=0))
        decision, events = agent.handle_midturn_arrival("s", "hello")
        assert decision.verb is Verdict.NORMAL_TURN
        assert events is None
        assert agent._pending_steer == {}