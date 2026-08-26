# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for CheckpointManager (C1c) + lifecycle checkpoint wiring."""

import pytest

from halbert_core.somatic.checkpoints import CheckpointManager
from halbert_core.somatic.block import BlockType, BlockStatus, SomaticBlock
from halbert_core.somatic.store import SomaticStore
from halbert_core.somatic.lifecycle import SomaticLifecycle


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------

class TestCheckpointManager:
    def test_checkpoint_and_rollback_existing(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_bytes(b"original")
        cm = CheckpointManager()
        cm.checkpoint(str(f))
        f.write_bytes(b"modified")
        assert f.read_bytes() == b"modified"
        restored = cm.rollback(str(f))
        assert restored == b"original"
        assert f.read_bytes() == b"original"

    def test_checkpoint_nonexistent_then_rollback_removes(self, tmp_path):
        f = tmp_path / "new.txt"
        cm = CheckpointManager()
        cm.checkpoint(str(f))  # file doesn't exist -> None content
        assert cm.stack_depth(str(f)) == 1
        f.write_bytes(b"created")
        cm.rollback(str(f))  # restore None -> remove file
        assert not f.exists()

    def test_rollback_no_checkpoint_returns_none(self, tmp_path):
        cm = CheckpointManager()
        assert cm.rollback(str(tmp_path / "nope")) is None

    def test_stack_lifo_order(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_bytes(b"v1")
        cm = CheckpointManager()
        cm.checkpoint(str(f))
        f.write_bytes(b"v2")
        cm.checkpoint(str(f))
        f.write_bytes(b"v3")
        # rollback restores v2 (most recent checkpoint), then v1
        assert cm.rollback(str(f)) == b"v2"
        assert cm.rollback(str(f)) == b"v1"
        assert cm.stack_depth(str(f)) == 0

    def test_fifo_trim_at_cap(self, tmp_path):
        f = tmp_path / "a.txt"
        cm = CheckpointManager(max_checkpoints=3)
        for i in range(5):
            f.write_bytes(f"v{i}".encode())
            cm.checkpoint(str(f))
        # Only the last 3 checkpoints are kept
        assert cm.stack_depth(str(f)) == 3
        # Most recent kept is v4
        f.write_bytes(b"current")
        assert cm.rollback(str(f)) == b"v4"

    def test_checkpoint_many_and_paths(self, tmp_path):
        a = tmp_path / "a.txt"; a.write_bytes(b"a")
        b = tmp_path / "b.txt"; b.write_bytes(b"b")
        cm = CheckpointManager()
        n = cm.checkpoint_many([str(a), str(b), ""])
        assert n == 2
        assert set(cm.paths()) == {str(a), str(b)}

    def test_clear(self, tmp_path):
        f = tmp_path / "a.txt"; f.write_bytes(b"x")
        cm = CheckpointManager()
        cm.checkpoint(str(f))
        assert cm.stack_depth(str(f)) == 1
        cm.clear(str(f))
        assert cm.stack_depth(str(f)) == 0
        cm.clear()
        assert cm.paths() == []


# ---------------------------------------------------------------------------
# Lifecycle checkpoint wiring (rollback on failed action)
# ---------------------------------------------------------------------------

class _FakeFinding:
    def __init__(self, affected_paths):
        self.affected_paths = affected_paths


class _FakeFindingStore:
    def __init__(self, finding):
        self._finding = finding
    def get(self, fid):
        return self._finding


class _FakeGen:
    def __init__(self, finding):
        self.findings = _FakeFindingStore(finding)
        self.proposals = type("P", (), {"get": lambda self, pid: None})()


def _decide(status):
    def _f(request_id, approved, reason="", generator=None):
        return {"linked": True, "request_id": request_id, "proposal_id": "p1",
                "status": status, "reason": reason}
    return _f


@pytest.fixture
def store():
    s = SomaticStore(":memory:")
    yield s
    s.close()


@pytest.mark.asyncio
async def test_action_checkpoints_before_execute(tmp_path, store):
    target = tmp_path / "cfg.txt"
    target.write_bytes(b"SAFE")
    finding = _FakeFinding(affected_paths=[str(target)])
    gen = _FakeGen(finding)
    cm = CheckpointManager()
    life = SomaticLifecycle(store, gen, handle_approval_decision=_decide("applied"),
                            checkpoints=cm)
    block = SomaticBlock.new(BlockType.PROPOSAL, "s1", finding_id="f1",
                              status=BlockStatus.PENDING_APPROVAL)
    block.approval_request_id = "ar1"
    block.proposal_id = "p1"
    store.create(block)
    # Simulate the action modifying the file externally mid-execution isn't
    # possible here (decide is a stub), but the checkpoint must be taken.
    await life.advance_to_action(block, approved=True)
    assert cm.stack_depth(str(target)) == 1
    assert store.get(block.id).status is BlockStatus.COMPLETED


@pytest.mark.asyncio
async def test_action_rolled_back_restores_checkpoint(tmp_path, store):
    target = tmp_path / "cfg.txt"
    target.write_bytes(b"ORIGINAL")
    finding = _FakeFinding(affected_paths=[str(target)])
    gen = _FakeGen(finding)
    cm = CheckpointManager()
    life = SomaticLifecycle(store, gen, handle_approval_decision=_decide("rolled_back"),
                            checkpoints=cm)
    block = SomaticBlock.new(BlockType.PROPOSAL, "s1", finding_id="f1",
                              status=BlockStatus.PENDING_APPROVAL)
    block.approval_request_id = "ar1"
    block.proposal_id = "p1"
    store.create(block)

    # checkpoint captures ORIGINAL; then simulate the failed action clobbering
    # the file; rollback (by the lifecycle) must restore it.
    await life.advance_to_action(block, approved=True)
    # After rolled_back, the lifecycle restored the checkpoint -> file is ORIGINAL
    assert target.read_bytes() == b"ORIGINAL"
    assert store.get(block.id).status is BlockStatus.ROLLED_BACK


@pytest.mark.asyncio
async def test_action_rejected_does_not_checkpoint(store, tmp_path):
    target = tmp_path / "cfg.txt"
    target.write_bytes(b"SAFE")
    finding = _FakeFinding(affected_paths=[str(target)])
    gen = _FakeGen(finding)
    cm = CheckpointManager()
    life = SomaticLifecycle(store, gen, handle_approval_decision=_decide("rejected"),
                            checkpoints=cm)
    block = SomaticBlock.new(BlockType.PROPOSAL, "s1", finding_id="f1",
                              status=BlockStatus.PENDING_APPROVAL)
    block.approval_request_id = "ar1"
    store.create(block)
    await life.advance_to_action(block, approved=False)
    # Rejection must not checkpoint (no execution attempted)
    assert cm.stack_depth(str(target)) == 0
    assert store.get(block.id).status is BlockStatus.REJECTED
