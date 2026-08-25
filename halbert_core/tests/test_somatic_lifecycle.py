"""Tests for SomaticLifecycle (C1b) — wraps existing modules, doesn't replace."""

import pytest

from halbert_core.somatic.block import BlockType, BlockStatus, SomaticBlock
from halbert_core.somatic.store import SomaticStore
from halbert_core.somatic.lifecycle import SomaticLifecycle


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeProposal:
    def __init__(self, proposal_id, approval_request_id="ar-1"):
        self.id = proposal_id
        self.approval_request_id = approval_request_id
        self.status = "pending"


class _FakeProposalStore:
    def __init__(self, proposal):
        self._proposal = proposal

    def get(self, pid):
        return self._proposal if pid == self._proposal.id else None


class _FakeGenerator:
    """Stands in for ProposalGenerator."""

    def __init__(self, proposal_id="p-1", approval_request_id="ar-1"):
        self.proposals = _FakeProposalStore(
            _FakeProposal(proposal_id, approval_request_id)
        )
        self.generate_calls = []
        self._proposal_id = proposal_id

    def generate_for_finding(self, finding_id):
        self.generate_calls.append(finding_id)
        return self._proposal_id  # or None to simulate no-fix


def _fake_decide_factory(result_status, proposal_id="p-1"):
    """Returns a handle_approval_decision callable yielding a fixed result."""
    def _decide(request_id, approved, reason="", generator=None):
        return {
            "linked": True,
            "request_id": request_id,
            "proposal_id": proposal_id,
            "status": result_status,
            "reason": reason,
            "execution": {"ok": result_status == "applied"},
        }
    return _decide


@pytest.fixture
def store():
    s = SomaticStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def block(store):
    b = SomaticBlock.new(BlockType.SENSORY, session_id="s1", finding_id="f-1")
    store.create(b)
    return b


# ---------------------------------------------------------------------------
# Sensory / deliberation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_advance_to_sensory_records_finding(store, block):
    life = SomaticLifecycle(store, _FakeGenerator(), handle_approval_decision=lambda *a, **k: {})
    await life.advance_to_sensory(block, finding_id="f-1",
                                  detector_output={"temp": 90})
    got = store.get(block.id)
    assert got.status is BlockStatus.DETECTED
    assert got.finding_id == "f-1"
    assert "detector_output" in got.metadata


@pytest.mark.asyncio
async def test_advance_to_deliberation(store, block):
    life = SomaticLifecycle(store, _FakeGenerator(), handle_approval_decision=lambda *a, **k: {})
    await life.advance_to_deliberation(block, cognitive_tick_output="thinking")
    got = store.get(block.id)
    assert got.status is BlockStatus.DELIBERATING
    assert got.metadata.get("deliberation") == "thinking"


# ---------------------------------------------------------------------------
# Proposal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_advance_to_proposal_links_ids(store, block):
    gen = _FakeGenerator(proposal_id="p-9", approval_request_id="ar-9")
    life = SomaticLifecycle(store, gen, handle_approval_decision=lambda *a, **k: {})
    await life.advance_to_proposal(block)
    got = store.get(block.id)
    assert got.status is BlockStatus.PENDING_APPROVAL
    assert got.proposal_id == "p-9"
    assert got.approval_request_id == "ar-9"
    assert gen.generate_calls == ["f-1"]


@pytest.mark.asyncio
async def test_advance_to_proposal_no_fix_rejects(store, block):
    gen = _FakeGenerator()
    gen._proposal_id = None  # no fix available
    life = SomaticLifecycle(store, gen, handle_approval_decision=lambda *a, **k: {})
    await life.advance_to_proposal(block)
    got = store.get(block.id)
    assert got.status is BlockStatus.REJECTED
    assert got.proposal_id is None


@pytest.mark.asyncio
async def test_advance_to_proposal_requires_finding(store):
    b = SomaticBlock.new(BlockType.SENSORY, "s1")  # no finding_id
    store.create(b)
    life = SomaticLifecycle(store, _FakeGenerator(), handle_approval_decision=lambda *a, **k: {})
    with pytest.raises(ValueError):
        await life.advance_to_proposal(b)


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_advance_to_action_approved_completes(store, block):
    gen = _FakeGenerator()
    decide = _fake_decide_factory("applied", "p-1")
    life = SomaticLifecycle(store, gen, handle_approval_decision=decide)
    # block must have an approval_request_id
    block.approval_request_id = "ar-1"
    store.update_status(block.id, block.status, approval_request_id="ar-1")

    await life.advance_to_action(block, approved=True, reason="looks good")
    got = store.get(block.id)
    assert got.status is BlockStatus.COMPLETED
    assert got.action_id == "p-1"
    assert got.metadata.get("execution", {}).get("proposal_id") == "p-1"


@pytest.mark.asyncio
async def test_advance_to_action_rejected(store, block):
    gen = _FakeGenerator()
    decide = _fake_decide_factory("rejected", "p-1")
    life = SomaticLifecycle(store, gen, handle_approval_decision=decide)
    block.approval_request_id = "ar-1"

    await life.advance_to_action(block, approved=False, reason="too risky")
    got = store.get(block.id)
    assert got.status is BlockStatus.REJECTED


@pytest.mark.asyncio
async def test_advance_to_action_rolled_back_on_failure(store, block):
    gen = _FakeGenerator()
    decide = _fake_decide_factory("rolled_back", "p-1")
    life = SomaticLifecycle(store, gen, handle_approval_decision=decide)
    block.approval_request_id = "ar-1"

    await life.advance_to_action(block, approved=True, reason="go")
    got = store.get(block.id)
    assert got.status is BlockStatus.ROLLED_BACK


@pytest.mark.asyncio
async def test_advance_to_action_requires_approval_request(store, block):
    life = SomaticLifecycle(store, _FakeGenerator(), handle_approval_decision=lambda *a, **k: {})
    block.approval_request_id = None
    with pytest.raises(ValueError):
        await life.advance_to_action(block, approved=True)


# ---------------------------------------------------------------------------
# Reflection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_advance_to_reflection_completes(store, block):
    life = SomaticLifecycle(store, _FakeGenerator(), handle_approval_decision=lambda *a, **k: {})
    block.status = BlockStatus.EXECUTING
    store.update_status(block.id, block.status)
    await life.advance_to_reflection(block, tick_output="lesson learned")
    got = store.get(block.id)
    assert got.status is BlockStatus.COMPLETED
    assert got.metadata.get("reflection") == "lesson learned"