"""Tests for D1d: subagent wiring into the state machine."""

import asyncio
import pytest

from halbert_core.agents.states import (
    AgentState, StateContext, ConversationStatus,
)
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.subagent import SubagentManager


@pytest.fixture
def manager():
    return SubagentManager(max_concurrent=2, on_event=lambda e: None)


def _agent(manager):
    agent = AgentStateMachine(llm_client=None, subagent_manager=manager)
    agent.ctx = StateContext(session_id="s1", request_id="r1", user_query="q")
    return agent


@pytest.mark.asyncio
async def test_spawn_subagent_sets_waiting_for_events(manager):
    agent = _agent(manager)
    events = []
    async for e in agent.spawn_subagent("storage_auditor", "check disks",
                                        ["/dev/sda"]):
        events.append(e)

    # Conversation status moved to WAITING_FOR_EVENTS
    assert agent.ctx.conversation_status.current() is ConversationStatus.WAITING_FOR_EVENTS
    handle_id = agent.ctx.current_subagent_handle_id
    assert handle_id is not None
    assert manager.get(handle_id).agent_type == "storage_auditor"

    # Events: a conversation_status (waiting) + a subagent_event (spawned)
    cs = [e for e in events if e.type == "conversation_status"]
    sa = [e for e in events if e.type == "subagent_event"]
    assert len(cs) == 1 and cs[0].data["status"] == "waiting_for_events"
    assert len(sa) == 1 and sa[0].data["subagent_event"] == "spawned"


@pytest.mark.asyncio
async def test_await_subagent_completion_resumes_in_progress(manager):
    agent = _agent(manager)
    # Spawn
    async for _ in agent.spawn_subagent("a", "g"):
        pass
    handle_id = agent.ctx.current_subagent_handle_id
    assert agent.ctx.conversation_status.current() is ConversationStatus.WAITING_FOR_EVENTS

    # Complete the subagent from a concurrent task while we await
    async def complete_later():
        await asyncio.sleep(0.1)
        manager.complete(handle_id, result_block_id="blk-1")

    asyncio.create_task(complete_later())

    events = []
    async for e in agent.await_subagent_completion(timeout=5.0):
        events.append(e)

    # Conversation resumed to IN_PROGRESS
    assert agent.ctx.conversation_status.current() is ConversationStatus.IN_PROGRESS
    assert agent.ctx.current_subagent_handle_id is None
    # A subagent completion event was emitted
    sa = [e for e in events if e.type == "subagent_event"]
    assert len(sa) == 1
    assert sa[0].data["subagent_event"] == "completed"
    assert sa[0].data["result_block_id"] == "blk-1"


@pytest.mark.asyncio
async def test_await_subagent_timeout_still_resumes(manager):
    agent = _agent(manager)
    async for _ in agent.spawn_subagent("a", "g"):
        pass
    # Do NOT complete it -> await times out but still resumes to IN_PROGRESS
    events = []
    async for e in agent.await_subagent_completion(timeout=0.3):
        events.append(e)
    assert agent.ctx.conversation_status.current() is ConversationStatus.IN_PROGRESS
    assert agent.ctx.current_subagent_handle_id is None


@pytest.mark.asyncio
async def test_no_subagent_manager_is_noop():
    agent = AgentStateMachine(llm_client=None)  # no subagent_manager
    agent.ctx = StateContext(session_id="s1", request_id="r1", user_query="q")
    events = []
    async for e in agent.spawn_subagent("a", "g"):
        events.append(e)
    assert events == []  # no-op
    assert agent.ctx.conversation_status.current() is ConversationStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_await_without_pending_handle_is_noop(manager):
    agent = _agent(manager)
    # No spawn first -> current_subagent_handle_id is None
    events = []
    async for e in agent.await_subagent_completion(timeout=0.2):
        events.append(e)
    assert events == []