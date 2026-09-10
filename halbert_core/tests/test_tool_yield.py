# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A07-G8: the yield primitive.

A steer typed while a long foreground command runs used to sit in the
pending slot until the command exited — five minutes for a backup, longer
for a build — with nothing telling the steward the words had not been read
yet. The origin's answer is three bits, not two: *kill* ends the command,
*steer* waits for the batch boundary, and *yield* hands the live process to
the background registry so the boundary arrives now.

Halbert already owns the background registry: a pool session whose block is
open is never reaped and never re-acquired, so a yielded block keeps its own
shell and finishes there. What was missing was the bit that says to stop
waiting for it.
"""

import asyncio
import time

import pytest

from halbert_core.streaming.session_manager import TerminalSessionManager
from halbert_core.streaming.agent_pool import TerminalPool
from halbert_core.tools import yield_signal


def _make_manager_with_pool(cap=3, max_sessions=8):
    m = TerminalSessionManager(
        max_sessions=max_sessions,
        kind_caps={"user": 3, "agent-pool": cap, "oneshot": 2},
    )
    pool = TerminalPool(m, cap=cap)
    return m, pool


# ---------------------------------------------------------------------------
# The signal itself
# ---------------------------------------------------------------------------

class TestYieldSignal:
    """One bit per session, and it only exists while a tool is running.

    The flag must not outlive the execution it was raised against. A steer
    that arrives between two tool calls has a boundary of its own coming;
    if the request leaked, the *next* tool would detach on arrival — a
    command abandoned for a steer that was already delivered.
    """

    def setup_method(self):
        yield_signal.reset()

    def teardown_method(self):
        yield_signal.reset()

    def test_no_execution_means_nothing_to_yield(self):
        assert yield_signal.request("s1") is False
        assert yield_signal.pending("s1") is False
        assert yield_signal.consume("s1") is False

    def test_request_during_an_execution_is_taken(self):
        token = yield_signal.begin("s1")
        assert yield_signal.request("s1") is True
        assert yield_signal.pending("s1") is True
        yield_signal.end("s1", token)

    def test_consume_is_read_and_clear(self):
        token = yield_signal.begin("s1")
        yield_signal.request("s1")
        assert yield_signal.consume("s1") is True
        assert yield_signal.consume("s1") is False
        yield_signal.end("s1", token)

    def test_an_unconsumed_request_does_not_outlive_its_execution(self):
        token = yield_signal.begin("s1")
        yield_signal.request("s1")
        yield_signal.end("s1", token)
        assert yield_signal.pending("s1") is False
        # And the next tool starts clean.
        token2 = yield_signal.begin("s1")
        assert yield_signal.consume("s1") is False
        yield_signal.end("s1", token2)

    def test_a_stale_end_does_not_clear_a_live_request(self):
        stale = yield_signal.begin("s1")
        yield_signal.end("s1", stale)
        live = yield_signal.begin("s1")
        yield_signal.request("s1")
        yield_signal.end("s1", stale)
        assert yield_signal.pending("s1") is True
        yield_signal.end("s1", live)

    def test_sessions_do_not_share_the_bit(self):
        t1 = yield_signal.begin("s1")
        t2 = yield_signal.begin("s2")
        yield_signal.request("s1")
        assert yield_signal.pending("s2") is False
        yield_signal.end("s1", t1)
        yield_signal.end("s2", t2)

    def test_a_session_with_no_id_is_not_a_session(self):
        # current_agent_session defaults to None outside a turn; a yield
        # request keyed on None would be a global flag every tool reads.
        assert yield_signal.begin(None) is None
        assert yield_signal.request(None) is False
        assert yield_signal.consume(None) is False


# ---------------------------------------------------------------------------
# The consumption point: a block that detaches instead of finishing
# ---------------------------------------------------------------------------

class TestPoolYield:
    """``run_block`` stops waiting, and the command keeps running.

    Nothing is killed and nothing is orphaned: the shell stays in the
    manager with its block open, so the reaper skips it and ``acquire``
    will not hand it to another command.
    """

    @pytest.mark.asyncio
    async def test_a_block_that_is_not_yielded_is_unchanged(self):
        m, pool = _make_manager_with_pool(cap=3)
        try:
            result = await pool.run_block(
                "echo hello", timeout=10.0, should_yield=lambda: False
            )
            assert result is not None
            assert result["exit_code"] == 0
            assert result.get("yielded") is False
            assert m._block_open.get(result["session_id"]) is False
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_yield_returns_before_the_command_does(self):
        m, pool = _make_manager_with_pool(cap=3)
        try:
            started = time.monotonic()
            flag = {"on": False}

            async def raise_it():
                await asyncio.sleep(0.3)
                flag["on"] = True

            asyncio.ensure_future(raise_it())
            result = await pool.run_block(
                "sleep 6", timeout=30.0, should_yield=lambda: flag["on"]
            )
            elapsed = time.monotonic() - started
            assert result is not None
            assert result["yielded"] is True
            # No exit code, because it has not exited.
            assert result["exit_code"] is None
            assert elapsed < 4.0, f"waited {elapsed:.1f}s for a yield"
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_a_yielded_block_keeps_its_shell(self):
        m, pool = _make_manager_with_pool(cap=3)
        try:
            flag = {"on": True}
            result = await pool.run_block(
                "sleep 6", timeout=30.0, should_yield=lambda: flag["on"]
            )
            sid = result["session_id"]
            # Alive, and still marked busy — which is what keeps the reaper
            # off it and keeps acquire() from handing the same shell to the
            # next command while this one is still running in it.
            assert m.get(sid) is not None
            assert m.get(sid).is_alive()
            assert m._block_open.get(sid) is True
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_a_yielded_block_finishes_in_the_background(self):
        m, pool = _make_manager_with_pool(cap=3)
        try:
            closed = []
            flag = {"on": True}
            result = await pool.run_block(
                "sleep 0.6; echo done",
                timeout=30.0,
                should_yield=lambda: flag["on"],
                on_close=closed.append,
            )
            sid = result["session_id"]
            assert result["yielded"] is True

            for _ in range(80):
                if closed:
                    break
                await asyncio.sleep(0.1)

            assert closed, "the yielded block never closed"
            final = closed[0]
            assert final["exit_code"] == 0
            assert final["block_id"] == result["block_id"]
            assert "done" in (final["output_head"] + final["output_tail"])
            # The slot comes back only when the command is actually over.
            assert m._block_open.get(sid) is False
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_a_yielded_block_cannot_hold_a_slot_forever(self):
        """R04-F3 again, by another door.

        A yielded block is exempt from the foreground timeout by design.
        Without a ceiling of its own, three `tail -f`s would take a cap-3
        pool down for the life of the process.
        """
        m, pool = _make_manager_with_pool(cap=3)
        try:
            closed = []
            result = await pool.run_block(
                "sleep 30",
                timeout=30.0,
                should_yield=lambda: True,
                on_close=closed.append,
                yielded_max_seconds=1.0,
            )
            sid = result["session_id"]
            for _ in range(80):
                if closed:
                    break
                await asyncio.sleep(0.1)
            assert closed, "the ceiling never fired"
            assert m._block_open.get(sid) is False
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_queue_eof_is_not_a_deadline(self):
        """EOF on the fanout queue ends the drain with no D marker.

        That is not a timeout, and the ETX-then-kill ladder must not run on
        it. Before the yield poll existed the drain sat inside one
        ``wait_for`` that returned straight out on EOF and left the shell
        alone; a poll loop that cannot tell "the drain ended" from "the
        deadline expired" would evict a pool session every time a fanout
        closed — a new behaviour smuggled in by a refactor.
        """
        m, pool = _make_manager_with_pool(cap=3)
        try:
            sid, session = await pool.acquire()
            m.set_block_open(sid, False)  # undo; run_block acquires its own

            async def eof_attach(maxsize=0):
                q = asyncio.Queue()
                q.put_nowait(("__replay__", b""))
                q.put_nowait(None)
                return q

            session.attach = eof_attach
            result = await pool.run_block(
                "echo hi", timeout=30.0, should_yield=lambda: False
            )
            assert result is not None
            assert result["yielded"] is False
            assert result["exit_code"] == -1  # no D marker ever arrived
            assert m.get(result["session_id"]) is not None, "EOF killed the shell"
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_the_yielded_result_carries_what_it_has_so_far(self):
        m, pool = _make_manager_with_pool(cap=3)
        try:
            flag = {"on": False}

            async def raise_it():
                await asyncio.sleep(0.8)
                flag["on"] = True

            asyncio.ensure_future(raise_it())
            result = await pool.run_block(
                "echo first; sleep 6",
                timeout=30.0,
                should_yield=lambda: flag["on"],
            )
            assert result["yielded"] is True
            assert "first" in (result["output_head"] + result["output_tail"])
        finally:
            await pool.shutdown()


# ---------------------------------------------------------------------------
# What the model is told
# ---------------------------------------------------------------------------

class TestYieldedResultText:
    def test_a_yielded_block_says_it_is_still_running(self):
        from halbert_core.tools.executor import ToolExecutor

        text = ToolExecutor._format_block_result({
            "yielded": True,
            "exit_code": None,
            "session_id": "term-9",
            "block_id": "blk-3",
            "output_head": "compiling...",
            "output_tail": "compiling...",
        })
        assert "still running" in text.lower()
        assert "term-9" in text
        assert "compiling..." in text
        # Never an exit code it does not have.
        assert "Exit code" not in text

    def test_a_finished_block_is_worded_as_before(self):
        from halbert_core.tools.executor import ToolExecutor

        text = ToolExecutor._format_block_result({
            "yielded": False,
            "exit_code": 0,
            "output_head": "hello",
            "output_tail": "hello",
        })
        assert text == "hello"


# ---------------------------------------------------------------------------
# The seam: a steer raises the bit for the tool that is running
# ---------------------------------------------------------------------------

class TestSteerRequestsAYield:
    def setup_method(self):
        yield_signal.reset()

    def teardown_method(self):
        yield_signal.reset()

    def _machine(self):
        from halbert_core.agents.state_machine import AgentStateMachine
        sm = AgentStateMachine.__new__(AgentStateMachine)
        sm._pending_steer = {}
        return sm

    def test_a_steer_with_a_tool_running_asks_it_to_yield(self):
        sm = self._machine()

        class Ctx:
            session_id = "s1"
        sm.ctx = Ctx()
        sm._turn_in_flight = lambda: True

        token = yield_signal.begin("s1")
        try:
            out = sm.request_steer("also rotate the logs")
            assert out["accepted"] is True
            assert out["yield_requested"] is True
            assert yield_signal.pending("s1") is True
        finally:
            yield_signal.end("s1", token)

    def test_a_steer_between_tools_asks_nothing(self):
        sm = self._machine()

        class Ctx:
            session_id = "s1"
        sm.ctx = Ctx()
        sm._turn_in_flight = lambda: True

        out = sm.request_steer("also rotate the logs")
        assert out["accepted"] is True
        assert out["yield_requested"] is False
        assert yield_signal.pending("s1") is False


class TestTheAcceptedEventSaysSo:
    """The half of A07-G8 that belongs to the surface.

    The finding is not only "the steer waited": it is that nothing told the
    steward it was waiting. The event that already carries ``replaced`` and
    ``demoted`` is where "a running command was let go so I could read this"
    belongs — backend-only until a consumer renders it, the same way
    ``stop_declined`` landed.
    """

    def setup_method(self):
        yield_signal.reset()

    def teardown_method(self):
        yield_signal.reset()

    def _busy_agent(self):
        from halbert_core.agents.llm_client import LLMResponse
        from halbert_core.agents.state_machine import AgentStateMachine
        from halbert_core.agents.states import AgentState, StateContext
        from halbert_core.tools import ToolExecutor, ToolSafetyFramework

        class _SlowLLM:
            async def chat(self, messages, tools=None, **kwargs):
                await asyncio.sleep(0.1)
                return LLMResponse(content="done", tool_calls=[], plan=[])

            async def stream(self, messages, **kwargs):
                await asyncio.sleep(0.1)
                yield "done"

        agent = AgentStateMachine(
            llm_client=_SlowLLM(),
            tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
            max_loops=5,
        )
        ctx = StateContext(session_id="run", request_id="r", user_query="q")
        agent.ctx = ctx
        agent.active_sessions["run"] = ctx
        agent.current_state = AgentState.EXECUTING
        agent._turn_lock = asyncio.Lock()
        agent._turn_lock._locked = True
        agent._turn_generation = agent.turn_activity.stamp()
        return agent

    def test_a_steer_over_a_running_command_is_marked_yielded(self):
        agent = self._busy_agent()
        token = yield_signal.begin("run")
        try:
            _decision, events = agent.handle_midturn_arrival("arr", "also the disk")
            assert events[0].type == "steer_accepted"
            assert events[0].data["yielded"] is True
        finally:
            yield_signal.end("run", token)

    def test_a_steer_with_nothing_running_is_not(self):
        agent = self._busy_agent()
        _decision, events = agent.handle_midturn_arrival("arr", "also the disk")
        assert events[0].type == "steer_accepted"
        assert events[0].data["yielded"] is False
