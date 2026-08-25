"""Tests for ConversationStatus wiring into the state machine + SSE (A2c)."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from halbert_core.agents.states import (
    AgentState, StateContext, ConversationStatus,
)
from halbert_core.agents.events import StreamEvent
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.llm_client import LLMResponse
from halbert_core.tools import ToolSafetyFramework, ToolExecutor
from halbert_core.context import ContextAssembler, TokenCounter
from halbert_core.prompts import AgentPromptBuilder


# ---------------------------------------------------------------------------
# Minimal mocks
# ---------------------------------------------------------------------------

class _MockRAG:
    async def search(self, query, limit=5):
        return [{"content": "doc", "source": "docs"}]


class _MockMemory:
    async def recall(self, query, limit=5):
        return []

    async def store_interaction(self, **kw):
        return None


class _MockDiscovery:
    async def search(self, query, limit=5):
        return []


class _MockLLM:
    """LLM that responds directly without tool calls."""

    def __init__(self, content="The answer is 42."):
        self._content = content

    async def chat(self, messages, tools=None, **kwargs):
        return LLMResponse(content=self._content, tool_calls=None, plan=None)

    async def stream(self, messages, **kwargs):
        for word in self._content.split():
            yield word + " "


def _build_agent():
    return AgentStateMachine(
        llm_client=_MockLLM(),
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        context_assembler=ContextAssembler(
            rag_service=_MockRAG(),
            memory_service=_MockMemory(),
            discovery_service=_MockDiscovery(),
            token_counter=TokenCounter(),
        ),
        prompt_builder=AgentPromptBuilder(),
        max_loops=5,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_success_emits_conversation_status_event():
    agent = _build_agent()
    events = []
    async for event in agent.process("What is 21 * 2?"):
        events.append(event)

    conv_events = [e for e in events if e.type == "conversation_status"]
    statuses = [e.data.get("status") for e in conv_events]
    # The run completes successfully -> a conversation_status success event
    assert "success" in statuses
    assert agent.ctx.conversation_status.current() == ConversationStatus.SUCCESS
    assert agent.ctx.conversation_status.is_terminal()


@pytest.mark.asyncio
async def test_conversation_status_event_is_serializable():
    agent = _build_agent()
    events = []
    async for event in agent.process("hello"):
        events.append(event)

    conv = next(e for e in events if e.type == "conversation_status")
    sse = conv.to_sse()
    assert "conversation_status" in sse
    assert "status" in sse


@pytest.mark.asyncio
async def test_initial_status_is_in_progress_then_transitions():
    agent = _build_agent()
    events = []
    async for event in agent.process("hello"):
        events.append(event)

    conv_events = [e for e in events if e.type == "conversation_status"]
    assert len(conv_events) >= 1
    # First conversation_status event reflects a transition from IN_PROGRESS
    assert conv_events[0].data.get("status") in {
        s.value for s in ConversationStatus
    }


def test_cancel_session_sets_cancelled():
    agent = AgentStateMachine(llm_client=None)
    ctx = StateContext(session_id="s1", request_id="r1", user_query="q")
    agent.active_sessions["s1"] = ctx
    assert agent.cancel_session("s1") is True
    assert ctx.conversation_status.current() == ConversationStatus.CANCELLED
    assert ctx.conversation_status.is_terminal()


def test_cancel_unknown_session_returns_false():
    agent = AgentStateMachine(llm_client=None)
    assert agent.cancel_session("nope") is False


def test_set_conversation_status_helper_emits_event():
    agent = AgentStateMachine(llm_client=None)
    agent.ctx = StateContext(session_id="s1", request_id="r1", user_query="q")
    event = agent._set_conversation_status(ConversationStatus.BLOCKED,
                                           blocked_action={"action_id": "a1"})
    assert event.type == "conversation_status"
    assert event.data["status"] == "blocked"
    assert event.data["blocked_action"] == {"action_id": "a1"}
    assert agent.ctx.conversation_status.current() == ConversationStatus.BLOCKED


@pytest.mark.asyncio
async def test_terminal_error_on_responding_failure():
    """A failure during RESPONDING ends with terminal ERROR status."""
    class _BrokenStreamLLM:
        async def chat(self, messages, tools=None, **kwargs):
            return LLMResponse(content="ok", tool_calls=None, plan=None)

        async def stream(self, messages, **kwargs):
            raise RuntimeError("stream exploded")
            yield  # make it a generator

    agent = AgentStateMachine(
        llm_client=_BrokenStreamLLM(),
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        context_assembler=ContextAssembler(
            rag_service=_MockRAG(), memory_service=_MockMemory(),
            discovery_service=_MockDiscovery(), token_counter=TokenCounter(),
        ),
        prompt_builder=AgentPromptBuilder(),
        max_loops=5,
    )
    events = []
    async for event in agent.process("hello"):
        events.append(event)

    conv_events = [e for e in events if e.type == "conversation_status"]
    statuses = [e.data.get("status") for e in conv_events]
    assert "error" in statuses
    assert agent.ctx.conversation_status.current() == ConversationStatus.ERROR