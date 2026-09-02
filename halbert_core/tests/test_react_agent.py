# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""ReAct loop: tool results must reach the model paired with their own call.

``R06-O1``. Building the ``role: "tool"`` messages by searching backwards
through every step for the last OBSERVATION with a matching ``tool_name``
meant that a model calling the same tool twice in one response — two
``read_file`` calls on different paths — got the *second* result attached to
both messages, and never saw the first at all. The steps are produced one
per tool call, in order, so they pair by position.
"""

import json
from unittest import mock

import pytest

from halbert_core.agents.react_agent import ReActAgent, ThinkingStepType


def _tool_call(name, **args):
    return {"function": {"name": name, "arguments": args}}


def _agent(execute_tool_fn, check_auth_fn=None):
    return ReActAgent(
        model="test-model",
        endpoint="http://localhost:0",
        tools=[],
        execute_tool_fn=execute_tool_fn,
        check_auth_fn=check_auth_fn,
        max_iterations=2,
    )


def _llm_script(*responses):
    """Feed _call_llm_with_tools a fixed sequence of assistant messages."""
    it = iter(responses)

    def _next(messages):
        return next(it)

    return _next


class TestToolResultsPairWithTheirCalls:

    def test_the_same_tool_called_twice_gets_two_different_results(self):
        seen = []

        def execute(name, args):
            seen.append(args["path"])
            return {"content": f"contents of {args['path']}"}

        agent = _agent(execute)
        captured = {}

        def _call(messages):
            if "turn2" not in captured:
                captured["turn2"] = True
                return {"message": {
                    "content": "",
                    "tool_calls": [
                        _tool_call("read_file", path="/etc/hosts"),
                        _tool_call("read_file", path="/etc/fstab"),
                    ],
                }}
            captured["messages"] = list(messages)
            return {"message": {"content": "done", "tool_calls": []}}

        with mock.patch.object(agent, "_call_llm_with_tools", side_effect=_call):
            agent.run("read both files", "You are a test agent.")

        assert seen == ["/etc/hosts", "/etc/fstab"]

        tool_msgs = [m for m in captured["messages"] if m["role"] == "tool"]
        assert len(tool_msgs) == 2
        bodies = [json.loads(m["content"]) for m in tool_msgs]
        assert bodies[0]["content"] == "contents of /etc/hosts"
        assert bodies[1]["content"] == "contents of /etc/fstab", (
            "the second call's result was attached to both messages"
        )

    def test_a_blocked_call_keeps_the_others_aligned(self):
        """A denied tool still produces one observation, so the calls after
        it must not shift onto the wrong results."""

        def execute(name, args):
            return {"content": f"ran {name}"}

        def check_auth(name, args):
            return {"allowed": name != "rm"}

        agent = _agent(execute, check_auth_fn=check_auth)
        captured = {}
        first = {"done": False}

        def _call(messages):
            if not first["done"]:
                first["done"] = True
                return {"message": {
                    "content": "",
                    "tool_calls": [
                        _tool_call("rm", path="/tmp/x"),
                        _tool_call("read_file", path="/etc/hosts"),
                    ],
                }}
            captured["messages"] = list(messages)
            return {"message": {"content": "done", "tool_calls": []}}

        with mock.patch.object(agent, "_call_llm_with_tools", side_effect=_call):
            result = agent.run("delete then read", "You are a test agent.")

        tool_msgs = [m for m in captured["messages"] if m["role"] == "tool"]
        assert len(tool_msgs) == 2
        blocked, read = (json.loads(m["content"]) for m in tool_msgs)
        assert "error" in blocked
        assert read["content"] == "ran read_file"

        observations = [
            s for s in result.thinking_steps
            if s.type is ThinkingStepType.OBSERVATION
        ]
        assert [o.tool_name for o in observations] == ["rm", "read_file"]

    def test_a_failing_tool_still_pairs_with_its_own_call(self):
        def execute(name, args):
            if args["path"] == "/etc/shadow":
                raise PermissionError("denied")
            return {"content": "ok"}

        agent = _agent(execute)
        captured = {}
        first = {"done": False}

        def _call(messages):
            if not first["done"]:
                first["done"] = True
                return {"message": {
                    "content": "",
                    "tool_calls": [
                        _tool_call("read_file", path="/etc/shadow"),
                        _tool_call("read_file", path="/etc/hosts"),
                    ],
                }}
            captured["messages"] = list(messages)
            return {"message": {"content": "done", "tool_calls": []}}

        with mock.patch.object(agent, "_call_llm_with_tools", side_effect=_call):
            agent.run("read both", "You are a test agent.")

        bodies = [
            json.loads(m["content"])
            for m in captured["messages"] if m["role"] == "tool"
        ]
        assert "denied" in bodies[0]["error"]
        assert bodies[1]["content"] == "ok"
