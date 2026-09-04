# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""E1f: terminal lifecycle from the tool executor to the agent's SSE stream.

Covers the three seams that make a command Halbert runs visible while it is
still running: the event factories, the bus between executor and state
machine, and the executor's streaming _run_command.
"""

import asyncio
import os

import pytest

from halbert_core.agents.events import StreamEvent
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.states import AgentState, StateContext, ToolCall
from halbert_core.streaming.terminal_bridge import (
    TerminalEventBus,
    current_agent_session,
    get_terminal_event_bus,
    publish_terminal_event,
    set_terminal_event_bus,
    set_terminal_pool_enabled,
    terminal_stream_wanted,
)
from halbert_core.tools.executor import ToolExecutor


@pytest.fixture(autouse=True)
def fresh_bus():
    """Every test gets its own bus; the singleton is restored afterwards.

    The pool is pinned off because this file tests the *subprocess* path of
    ``_run_command`` -- the one that streams `output` payloads over the bus.
    The pool path streams over a PTY WebSocket instead and emits spawn and
    complete only, so a leaked ``_pool_enabled`` from another test file turns
    every assertion here into a mystery about missing output.
    """
    set_terminal_event_bus(TerminalEventBus())
    set_terminal_pool_enabled(False)
    yield
    set_terminal_event_bus(None)
    set_terminal_pool_enabled(False)


# -----------------------------------------------------------------------------
# Event factories
# -----------------------------------------------------------------------------

class TestTerminalEvents:

    def test_spawn_carries_attach_mode_and_identity(self):
        event = StreamEvent.terminal_spawn(
            "sess-1", "term-1", command="ls -la", pid=4242,
            sandboxed=True, cwd="/tmp", attach="ws",
        )
        payload = event.to_dict()
        assert payload["type"] == "terminal_spawn"
        assert payload["session_id"] == "sess-1"
        assert payload["terminal_session_id"] == "term-1"
        assert payload["command"] == "ls -la"
        assert payload["pid"] == 4242
        assert payload["sandboxed"] is True
        assert payload["cwd"] == "/tmp"
        assert payload["attach"] == "ws"

    def test_spawn_defaults_to_sse_attachment(self):
        event = StreamEvent.terminal_spawn("s", "t", command="pwd", pid=1)
        assert event.to_dict()["attach"] == "sse"

    def test_output_and_complete(self):
        out = StreamEvent.terminal_output("s", "t", "hello\r\n").to_dict()
        assert out["type"] == "terminal_output"
        assert out["data"] == "hello\r\n"

        done = StreamEvent.terminal_complete("s", "t", 3).to_dict()
        assert done["type"] == "terminal_complete"
        assert done["exit_code"] == 3

    def test_events_serialize_as_sse(self):
        line = StreamEvent.terminal_output("s", "t", "x").to_sse()
        assert line.startswith("data: ")
        assert line.endswith("\n\n")


# -----------------------------------------------------------------------------
# The bus
# -----------------------------------------------------------------------------

class TestTerminalEventBus:

    async def test_publish_without_subscriber_is_a_noop(self):
        bus = get_terminal_event_bus()
        assert bus.has_subscribers("nobody") is False
        bus.publish("nobody", {"kind": "output", "data": "x"})  # must not raise

    async def test_subscriber_receives_payloads(self):
        bus = get_terminal_event_bus()
        queue = bus.subscribe("sess")
        bus.publish("sess", {"kind": "spawn"})
        assert (await queue.get())["kind"] == "spawn"

    async def test_unsubscribe_stops_delivery(self):
        bus = get_terminal_event_bus()
        queue = bus.subscribe("sess")
        bus.unsubscribe("sess", queue)
        bus.publish("sess", {"kind": "output"})
        assert queue.empty()
        assert bus.has_subscribers("sess") is False

    async def test_unsubscribe_is_idempotent(self):
        bus = get_terminal_event_bus()
        queue = bus.subscribe("sess")
        bus.unsubscribe("sess", queue)
        bus.unsubscribe("sess", queue)  # must not raise

    async def test_full_queue_drops_oldest_rather_than_blocking(self):
        bus = get_terminal_event_bus()
        queue = bus.subscribe("sess")
        total = queue.maxsize + 10
        for i in range(total):
            bus.publish("sess", {"kind": "output", "data": i})
        # Producer never blocked, and the newest chunk survived.
        assert queue.qsize() == queue.maxsize
        drained = [queue.get_nowait()["data"] for _ in range(queue.qsize())]
        assert drained[-1] == total - 1

    async def test_context_var_targets_the_current_session(self):
        bus = get_terminal_event_bus()
        queue = bus.subscribe("sess-a")
        token = current_agent_session.set("sess-a")
        try:
            assert terminal_stream_wanted() is True
            publish_terminal_event({"kind": "spawn"})
        finally:
            current_agent_session.reset(token)
        assert queue.get_nowait()["kind"] == "spawn"
        assert terminal_stream_wanted() is False


# -----------------------------------------------------------------------------
# Executor: streaming run_command
# -----------------------------------------------------------------------------

class TestRunCommandStreaming:

    async def test_returns_output_and_publishes_lifecycle(self):
        bus = get_terminal_event_bus()
        queue = bus.subscribe("sess")
        executor = ToolExecutor()

        result = await executor.execute(
            "run_command", {"command": "echo streamed"}, session_id="sess"
        )
        assert result.success is True
        assert "streamed" in result.result

        payloads = []
        while not queue.empty():
            payloads.append(queue.get_nowait())

        kinds = [p["kind"] for p in payloads]
        assert kinds[0] == "spawn"
        assert kinds[-1] == "complete"
        assert "output" in kinds

        spawn = payloads[0]
        assert spawn["command"] == "echo streamed"
        assert spawn["attach"] == "sse"
        assert spawn["pid"] > 0
        assert payloads[-1]["exit_code"] == 0

        terminal_id = spawn["terminal_session_id"]
        assert all(p["terminal_session_id"] == terminal_id for p in payloads)
        streamed = "".join(p["data"] for p in payloads if p["kind"] == "output")
        assert "streamed" in streamed

    async def test_publishes_nothing_when_nobody_is_listening(self):
        executor = ToolExecutor()
        result = await executor.execute(
            "run_command", {"command": "echo quiet"}, session_id="unwatched"
        )
        assert result.success is True
        assert "quiet" in result.result
        assert get_terminal_event_bus().has_subscribers("unwatched") is False

    async def test_stderr_is_streamed_and_reported(self):
        bus = get_terminal_event_bus()
        queue = bus.subscribe("sess")
        executor = ToolExecutor()

        result = await executor.execute(
            "run_command",
            {"command": "echo problem >&2; exit 7"},
            session_id="sess",
        )
        assert result.success is True  # the tool ran; the command failed
        assert "Exit code 7" in result.result
        assert "problem" in result.result

        payloads = []
        while not queue.empty():
            payloads.append(queue.get_nowait())
        assert payloads[-1]["exit_code"] == 7
        streamed = "".join(p["data"] for p in payloads if p["kind"] == "output")
        assert "problem" in streamed

    async def test_timeout_kills_the_child_and_closes_the_terminal(self):
        bus = get_terminal_event_bus()
        queue = bus.subscribe("sess")
        executor = ToolExecutor()

        result = await executor.execute(
            "run_command", {"command": "sleep 5", "timeout": 1}, session_id="sess"
        )
        assert result.success is False
        assert "timed out" in (result.error or "").lower()

        payloads = []
        while not queue.empty():
            payloads.append(queue.get_nowait())
        assert payloads[0]["kind"] == "spawn"
        assert payloads[-1]["kind"] == "complete"

    async def test_timeout_covers_a_child_that_closes_its_pipes_and_keeps_running(self):
        """EOF on the pipes is not the same event as the child exiting.

        A command that closes its std fds reaches EOF immediately; if only the
        drain were timed, it would outlive its timeout entirely.
        """
        bus = get_terminal_event_bus()
        bus.subscribe("sess")
        executor = ToolExecutor()

        started = asyncio.get_event_loop().time()
        result = await executor.execute(
            "run_command",
            {"command": "exec 1>&- 2>&-; sleep 30", "timeout": 1},
            session_id="sess",
        )
        elapsed = asyncio.get_event_loop().time() - started

        assert result.success is False
        assert "timed out" in (result.error or "").lower()
        assert elapsed < 10, f"timeout did not bound process exit (took {elapsed:.1f}s)"

    async def test_session_context_is_restored_after_execute(self):
        executor = ToolExecutor()
        await executor.execute("run_command", {"command": "true"}, session_id="sess")
        assert current_agent_session.get() is None


# -----------------------------------------------------------------------------
# State machine: relaying terminal events onto the live SSE stream
# -----------------------------------------------------------------------------

def _machine() -> AgentStateMachine:
    machine = AgentStateMachine(llm_client=None, tool_executor=ToolExecutor())
    machine.ctx = StateContext(
        session_id="sess", request_id="req-1", user_query="run something"
    )
    return machine


class TestStateMachineTerminalRelay:

    async def test_run_tool_streaming_yields_events_and_returns_result(self):
        machine = _machine()
        sink = []
        events = [
            e async for e in machine._run_tool_streaming(
                "run_command", {"command": "echo relayed"}, False, sink
            )
        ]

        types = [e.type for e in events]
        assert types[0] == "terminal_spawn"
        assert types[-1] == "terminal_complete"
        assert "terminal_output" in types
        assert all(e.session_id == "sess" for e in events)

        assert len(sink) == 1
        assert "relayed" in sink[0].result

    async def test_bus_subscription_is_released_afterwards(self):
        machine = _machine()
        sink = []
        async for _ in machine._run_tool_streaming(
            "run_command", {"command": "true"}, False, sink
        ):
            pass
        assert get_terminal_event_bus().has_subscribers("sess") is False

    async def test_non_terminal_tools_relay_nothing(self):
        machine = _machine()
        sink = []
        events = [
            e async for e in machine._run_tool_streaming(
                "read_file", {"path": "/definitely/not/here"}, False, sink
            )
        ]
        assert events == []
        assert len(sink) == 1
        assert sink[0].success is False

    async def test_executing_state_emits_terminal_events_in_order(self):
        machine = _machine()
        machine.current_state = AgentState.EXECUTING
        machine.ctx.tool_calls.append(
            ToolCall(id="exec-1", name="run_command", args={"command": "echo inline"})
        )

        events = [e async for e in machine._handle_executing()]
        types = [e.type for e in events]

        assert types.index("tool_start") < types.index("terminal_spawn")
        assert types.index("terminal_spawn") < types.index("terminal_complete")
        assert types.index("terminal_complete") < types.index("tool_complete")
        assert types[-1] == "state_change"
        # The model still sees the output as an observation.
        assert any("inline" in obs for obs in machine.ctx.observations)

    async def test_relay_survives_a_tool_that_publishes_nothing(self):
        """A tool with no terminal output must not stall the generator."""
        machine = _machine()
        sink = []
        await asyncio.wait_for(
            _drain(machine._run_tool_streaming("read_file", {"path": "/nope"}, False, sink)),
            timeout=5,
        )
        assert len(sink) == 1


    async def test_closing_the_stream_mid_command_releases_everything(self):
        """An SSE client that disconnects mid-command must not leak."""
        machine = _machine()
        sink = []
        agen = machine._run_tool_streaming(
            "run_command", {"command": "sleep 30"}, False, sink
        )

        first = await agen.__anext__()
        assert first.type == "terminal_spawn"
        pid = first.to_dict()["pid"]

        await agen.aclose()

        assert get_terminal_event_bus().has_subscribers("sess") is False
        # The child must not outlive the turn that started it.
        await asyncio.sleep(0.3)
        with pytest.raises(OSError):
            os.kill(pid, 0)

    async def test_two_turns_do_not_see_each_others_terminals(self):
        """Concurrent sessions each drain only their own bus queue."""
        one = _machine()
        two = _machine()
        two.ctx.session_id = "other"

        sink_one, sink_two = [], []
        events_one, events_two = [], []

        async def collect(machine, command, sink, out):
            async for event in machine._run_tool_streaming(
                "run_command", {"command": command}, False, sink
            ):
                out.append(event)

        await asyncio.gather(
            collect(one, "echo alpha", sink_one, events_one),
            collect(two, "echo beta", sink_two, events_two),
        )

        assert {e.session_id for e in events_one} == {"sess"}
        assert {e.session_id for e in events_two} == {"other"}

        text_one = "".join(
            e.to_dict()["data"] for e in events_one if e.type == "terminal_output"
        )
        text_two = "".join(
            e.to_dict()["data"] for e in events_two if e.type == "terminal_output"
        )
        assert "alpha" in text_one and "beta" not in text_one
        assert "beta" in text_two and "alpha" not in text_two


async def _drain(agen):
    async for _ in agen:
        pass
