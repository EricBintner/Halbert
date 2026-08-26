# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Tool-calling bridge: model client → LLMClientAdapter → state machine.

Before this bridge existed the adapter accepted a ``tools`` argument and threw
it away, so ``LLMResponse.tool_calls`` was always None. PLANNING routes on
``tool_calls``, which meant EXECUTING, READING and AWAITING_CONFIRMATION —
and with them the whole approval flow — were unreachable from the API.
"""

import pytest
import requests
from unittest.mock import MagicMock, patch

from halbert_core.model.client import _normalise_tool_calls, call_llm_chat


TOOL_SCHEMAS = [{
    "type": "function",
    "function": {
        "name": "run_command",
        "description": "Execute a shell command",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
}]


def _response(payload, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


# -----------------------------------------------------------------------------
# Normalisation
# -----------------------------------------------------------------------------

class TestNormaliseToolCalls:

    def test_ollama_shape_keeps_decoded_arguments(self):
        calls = _normalise_tool_calls([
            {"function": {"name": "run_command", "arguments": {"command": "uptime"}}}
        ])
        assert calls == [
            {"id": "call_0", "name": "run_command", "arguments": {"command": "uptime"}}
        ]

    def test_openai_shape_decodes_json_string_arguments(self):
        calls = _normalise_tool_calls([{
            "id": "call_abc",
            "type": "function",
            "function": {"name": "read_file", "arguments": '{"path": "/etc/hosts"}'},
        }])
        assert calls == [
            {"id": "call_abc", "name": "read_file", "arguments": {"path": "/etc/hosts"}}
        ]

    def test_unparseable_arguments_degrade_to_empty_dict(self):
        # A truncated tool call should still name the tool rather than crash
        # the turn — the executor reports the missing argument itself.
        calls = _normalise_tool_calls([
            {"function": {"name": "run_command", "arguments": '{"command": "upti'}}
        ])
        assert calls == [{"id": "call_0", "name": "run_command", "arguments": {}}]

    def test_non_dict_arguments_degrade_to_empty_dict(self):
        calls = _normalise_tool_calls([
            {"function": {"name": "run_command", "arguments": ["uptime"]}}
        ])
        assert calls[0]["arguments"] == {}

    def test_nameless_and_malformed_entries_are_dropped(self):
        calls = _normalise_tool_calls([
            {"function": {"arguments": {}}},
            "not-a-dict",
            {"function": {"name": "run_command", "arguments": {}}},
        ])
        assert [c["name"] for c in calls] == ["run_command"]

    def test_empty_and_none_are_empty(self):
        assert _normalise_tool_calls(None) == []
        assert _normalise_tool_calls([]) == []


# -----------------------------------------------------------------------------
# call_llm_chat wire format
# -----------------------------------------------------------------------------

class TestCallLLMChatTools:

    def test_ollama_sends_tools_and_returns_tool_calls(self):
        payload = {"message": {
            "content": "",
            "tool_calls": [
                {"function": {"name": "run_command", "arguments": {"command": "uptime"}}}
            ],
        }}
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response(payload)) as post:
            result = call_llm_chat(
                endpoint="http://localhost:11434",
                model="example-model:latest",
                messages=[{"role": "user", "content": "how long up?"}],
                tools=TOOL_SCHEMAS,
            )

        sent = post.call_args.kwargs["json"]
        assert sent["tools"] == TOOL_SCHEMAS
        # Ollama only reports tool_calls on a non-streamed response.
        assert sent["stream"] is False
        assert result["tool_calls"][0]["name"] == "run_command"

    def test_openai_sends_tools_and_returns_tool_calls(self):
        payload = {"choices": [{"message": {
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "function": {"name": "read_file", "arguments": '{"path": "/etc/hosts"}'},
            }],
        }}]}
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response(payload)) as post:
            result = call_llm_chat(
                endpoint="https://api.example.test",
                model="example-hosted-model",
                messages=[{"role": "user", "content": "read hosts"}],
                provider="openai",
                tools=TOOL_SCHEMAS,
            )

        assert post.call_args.kwargs["json"]["tools"] == TOOL_SCHEMAS
        assert result["tool_calls"][0]["arguments"] == {"path": "/etc/hosts"}
        # A null content alongside tool calls must not blow up .strip().
        assert result["content"] == ""

    def test_no_tools_argument_sends_no_tools_key(self):
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response({"message": {"content": "hi"}})) as post:
            result = call_llm_chat(
                endpoint="http://localhost:11434",
                model="example-model:latest",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert "tools" not in post.call_args.kwargs["json"]
        assert result["tool_calls"] == []

    def test_model_rejecting_tools_is_retried_without_them(self):
        """Most local models have no tool support; Ollama 400s rather than
        ignoring the field. Answering without tools beats losing the turn."""
        err = requests.HTTPError()
        err.response = MagicMock(status_code=400)
        bad = _response({}, status=400)
        bad.raise_for_status.side_effect = err
        good = _response({"message": {"content": "no tools here"}})

        with patch("halbert_core.model.client.requests.post",
                   side_effect=[bad, good]) as post:
            result = call_llm_chat(
                endpoint="http://localhost:11434",
                model="tiny",
                messages=[{"role": "user", "content": "hi"}],
                tools=TOOL_SCHEMAS,
            )

        assert post.call_count == 2
        assert "tools" in post.call_args_list[0].kwargs["json"]
        assert "tools" not in post.call_args_list[1].kwargs["json"]
        assert result["content"] == "no tools here"

    def test_server_errors_are_not_swallowed_by_the_retry(self):
        err = requests.HTTPError()
        err.response = MagicMock(status_code=500)
        bad = _response({}, status=500)
        bad.raise_for_status.side_effect = err

        with patch("halbert_core.model.client.requests.post", return_value=bad):
            with pytest.raises(requests.HTTPError):
                call_llm_chat(
                    endpoint="http://localhost:11434",
                    model="example-model:latest",
                    messages=[{"role": "user", "content": "hi"}],
                    tools=TOOL_SCHEMAS,
                )


# -----------------------------------------------------------------------------
# Adapter → state-machine shape
# -----------------------------------------------------------------------------

fastapi = pytest.importorskip("fastapi")


class TestLLMClientAdapterTools:

    @pytest.fixture
    def adapter(self):
        from halbert_core.dashboard.routes.agent import LLMClientAdapter
        return LLMClientAdapter()

    @pytest.mark.asyncio
    async def test_tools_reach_the_model_client(self, adapter):
        with patch("halbert_core.model.client.call_llm_chat") as chat:
            chat.return_value = {"content": "ok", "tool_calls": []}
            await adapter.chat(
                [{"role": "user", "content": "hi"}], tools=TOOL_SCHEMAS
            )
        assert chat.call_args.kwargs["tools"] == TOOL_SCHEMAS

    @pytest.mark.asyncio
    async def test_tool_calls_come_back_in_state_machine_shape(self, adapter):
        """PLANNING reads tool_call.function.name / .function.arguments."""
        with patch("halbert_core.model.client.call_llm_chat") as chat:
            chat.return_value = {
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "name": "run_command",
                     "arguments": {"command": "uptime"}}
                ],
            }
            response = await adapter.chat(
                [{"role": "user", "content": "how long up?"}], tools=TOOL_SCHEMAS
            )

        assert len(response.tool_calls) == 1
        call = response.tool_calls[0]
        assert call.id == "call_1"
        assert call.function.name == "run_command"
        assert call.function.arguments == {"command": "uptime"}

    @pytest.mark.asyncio
    async def test_no_tool_calls_is_none_not_empty_list(self, adapter):
        with patch("halbert_core.model.client.call_llm_chat") as chat:
            chat.return_value = {"content": "just talking", "tool_calls": []}
            response = await adapter.chat([{"role": "user", "content": "hi"}])
        assert response.tool_calls is None
        assert response.content == "just talking"


class TestPlanningRoutesOnAdaptedToolCalls:
    """The end the bridge exists for: a tool call from the wire has to move
    the state machine into EXECUTING / READING / SEARCHING."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name,expected_state", [
        ("run_command", "executing"),
        ("read_file", "reading"),
        ("web_search", "searching"),
    ])
    async def test_wire_tool_call_routes_to_state(self, tool_name, expected_state):
        from halbert_core.agents import AgentState, AgentStateMachine
        from halbert_core.dashboard.routes.agent import _as_tool_calls
        from halbert_core.tools import ToolExecutor, ToolSafetyFramework
        from unittest.mock import AsyncMock

        llm = AsyncMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            content="",
            tool_calls=_as_tool_calls([
                {"id": "c1", "name": tool_name, "arguments": {}}
            ]),
            plan=None,
        ))

        agent = AgentStateMachine(
            llm_client=llm,
            tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
            max_loops=5,
        )
        agent.ctx = _bare_context()
        agent.current_state = AgentState.PLANNING

        states = [
            e.data["state"]
            async for e in agent._handle_planning()
            if e.type == "state_change"
        ]
        assert expected_state in states


def _bare_context():
    from halbert_core.agents.states import StateContext
    return StateContext(
        session_id="sess-tools",
        request_id="req-tools",
        user_query="do the thing",
        conversation_history=[],
        max_loops=5,
    )


# -----------------------------------------------------------------------------
# Tool results must reach the next PLANNING pass
# -----------------------------------------------------------------------------

class TestToolResultsFeedBack:
    """The first live turn through the bridge ran `uptime` four times: the
    observation said only "Executed run_command: success", so the model never
    saw the output and kept re-asking until max_loops cut the turn off."""

    def test_observation_carries_the_output(self):
        from halbert_core.agents.state_machine import _format_tool_observation

        obs = _format_tool_observation(
            "run_command", {"command": "uptime"}, "22:50 up 1 day, load 0.5"
        )
        assert "uptime" in obs
        assert "22:50 up 1 day" in obs

    def test_long_output_is_truncated_with_a_marker(self):
        from halbert_core.agents.state_machine import (
            _format_tool_observation, _TOOL_RESULT_CHARS,
        )

        obs = _format_tool_observation("read_file", {"path": "/x"}, "y" * 10_000)
        assert len(obs) < _TOOL_RESULT_CHARS + 200
        assert "truncated" in obs
        assert "10000 chars total" in obs

    def test_empty_output_is_stated_not_silently_blank(self):
        from halbert_core.agents.state_machine import _format_tool_observation

        obs = _format_tool_observation("run_command", {"command": "true"}, "")
        assert "no output" in obs

    def test_none_result_does_not_render_as_the_string_None(self):
        from halbert_core.agents.state_machine import _format_tool_observation

        obs = _format_tool_observation("run_command", {"command": "true"}, None)
        assert "no output" in obs


class TestRepeatedToolCallGuard:

    def _agent(self):
        from halbert_core.agents import AgentStateMachine
        from halbert_core.tools import ToolExecutor, ToolSafetyFramework
        from unittest.mock import AsyncMock

        llm = AsyncMock()
        agent = AgentStateMachine(
            llm_client=llm,
            tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
            max_loops=5,
        )
        agent.ctx = _bare_context()
        return agent

    def test_settled_identical_call_is_recognised(self):
        from halbert_core.agents.states import ToolCall

        agent = self._agent()
        agent.ctx.add_tool_call(ToolCall(
            id="a", name="run_command", args={"command": "uptime"}, status="success"
        ))
        assert agent._already_called("run_command", {"command": "uptime"})

    def test_different_arguments_are_not_a_repeat(self):
        from halbert_core.agents.states import ToolCall

        agent = self._agent()
        agent.ctx.add_tool_call(ToolCall(
            id="a", name="run_command", args={"command": "uptime"}, status="success"
        ))
        assert not agent._already_called("run_command", {"command": "df -h"})

    def test_a_pending_call_does_not_match_itself(self):
        from halbert_core.agents.states import ToolCall

        agent = self._agent()
        agent.ctx.add_tool_call(ToolCall(
            id="a", name="run_command", args={"command": "uptime"}, status="pending"
        ))
        assert not agent._already_called("run_command", {"command": "uptime"})

    @pytest.mark.asyncio
    async def test_planning_reflects_instead_of_re_executing(self):
        from halbert_core.agents import AgentState
        from halbert_core.agents.states import ToolCall
        from halbert_core.dashboard.routes.agent import _as_tool_calls
        from unittest.mock import AsyncMock

        agent = self._agent()
        agent.current_state = AgentState.PLANNING
        agent.ctx.add_tool_call(ToolCall(
            id="a", name="run_command", args={"command": "uptime"}, status="success"
        ))
        agent.llm.chat = AsyncMock(return_value=MagicMock(
            content="",
            tool_calls=_as_tool_calls([
                {"id": "b", "name": "run_command", "arguments": {"command": "uptime"}}
            ]),
            plan=None,
        ))

        states = [
            e.data["state"]
            async for e in agent._handle_planning()
            if e.type == "state_change"
        ]

        assert states == ["reflecting"]
        # No second record for the same call.
        assert len(agent.ctx.tool_calls) == 1
