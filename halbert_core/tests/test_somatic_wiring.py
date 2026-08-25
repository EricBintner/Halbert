"""Tests for somatic state-machine wiring (C1d)."""

import pytest

from halbert_core.agents.states import AgentState, StateContext
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.events import StreamEvent
from halbert_core.somatic.block import BlockType, BlockStatus, SomaticBlock
from halbert_core.somatic.store import SomaticStore


class _FakeLifecycle:
    def __init__(self):
        self.reflection_calls = []

    async def advance_to_reflection(self, block, tick_output=None):
        self.reflection_calls.append(block.id)
        block.status = BlockStatus.COMPLETED


@pytest.fixture
def store():
    s = SomaticStore(":memory:")
    yield s
    s.close()


def _agent_with_somatic(store, life):
    agent = AgentStateMachine(
        llm_client=None,
        somatic_lifecycle=life,
        somatic_store=store,
    )
    agent.ctx = StateContext(session_id="s1", request_id="r1", user_query="q")
    agent.current_state = AgentState.REFLECTING
    return agent


@pytest.mark.asyncio
async def test_reflecting_advances_active_somatic_block(store):
    life = _FakeLifecycle()
    agent = _agent_with_somatic(store, life)
    block = SomaticBlock.new(BlockType.ACTION, "s1", status=BlockStatus.EXECUTING)
    store.create(block)
    agent.ctx.current_somatic_block_id = block.id

    events = []
    async for e in agent._handle_reflecting():
        events.append(e)

    # Lifecycle was called for this block
    assert life.reflection_calls == [block.id]
    # A somatic_block SSE event was emitted with the new status
    somatic = [e for e in events if e.type == "somatic_block"]
    assert len(somatic) == 1
    assert somatic[0].data["block_id"] == block.id
    assert somatic[0].data["status"] == "completed"
    # Store reflects the persisted status
    assert store.get(block.id).status is BlockStatus.COMPLETED


@pytest.mark.asyncio
async def test_reflecting_no_somatic_lifecycle_is_noop(store):
    # No somatic lifecycle wired -> no somatic_block event
    agent = AgentStateMachine(llm_client=None)  # no somatic
    agent.ctx = StateContext(session_id="s1", request_id="r1", user_query="q")
    agent.current_state = AgentState.REFLECTING
    events = []
    async for e in agent._handle_reflecting():
        events.append(e)
    assert not any(e.type == "somatic_block" for e in events)


@pytest.mark.asyncio
async def test_reflecting_missing_block_id_skipped(store):
    life = _FakeLifecycle()
    agent = _agent_with_somatic(store, life)
    agent.ctx.current_somatic_block_id = "does-not-exist"
    events = []
    async for e in agent._handle_reflecting():
        events.append(e)
    assert life.reflection_calls == []
    assert not any(e.type == "somatic_block" for e in events)


@pytest.mark.asyncio
async def test_emit_somatic_block_builds_event_and_publishes(store):
    life = _FakeLifecycle()
    agent = _agent_with_somatic(store, life)
    block = SomaticBlock.new(BlockType.PROPOSAL, "s1", status=BlockStatus.PENDING_APPROVAL,
                             finding_id="f1", proposal_id="p1")
    event = await agent._emit_somatic_block(block)
    assert event.type == "somatic_block"
    assert event.data["block_type"] == "proposal"
    assert event.data["status"] == "pending_approval"
    assert event.data["finding_id"] == "f1"
    assert event.data["proposal_id"] == "p1"
    assert event.data["block_id"] == block.id


@pytest.mark.asyncio
async def test_state_context_carries_somatic_block_id():
    ctx = StateContext(session_id="s", request_id="r", user_query="q")
    assert ctx.current_somatic_block_id is None
    ctx.current_somatic_block_id = "blk-1"
    assert ctx.current_somatic_block_id == "blk-1"