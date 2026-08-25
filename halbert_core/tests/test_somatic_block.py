"""Tests for SomaticBlock + SomaticStore (C1a)."""

import pytest

from halbert_core.somatic.block import BlockType, BlockStatus, SomaticBlock
from halbert_core.somatic.store import SomaticStore, get_somatic_store, set_somatic_store


# ---------------------------------------------------------------------------
# SomaticBlock
# ---------------------------------------------------------------------------

class TestSomaticBlock:
    def test_new_assigns_id(self):
        b = SomaticBlock.new(BlockType.SENSORY, session_id="s1")
        assert b.id
        assert b.block_type is BlockType.SENSORY
        assert b.status is BlockStatus.DETECTED
        assert b.session_id == "s1"

    def test_to_dict_serializes_enums(self):
        b = SomaticBlock.new(BlockType.PROPOSAL, "s1", status=BlockStatus.PROPOSED,
                             finding_id="f1")
        d = b.to_dict()
        assert d["block_type"] == "proposal"
        assert d["status"] == "proposed"
        assert d["finding_id"] == "f1"

    def test_from_dict_roundtrip(self):
        b = SomaticBlock.new(BlockType.ACTION, "s1", status=BlockStatus.EXECUTING,
                             proposal_id="p1", metadata={"k": "v"})
        d = b.to_dict()
        b2 = SomaticBlock.from_dict(d)
        assert b2.block_type is BlockType.ACTION
        assert b2.status is BlockStatus.EXECUTING
        assert b2.proposal_id == "p1"
        assert b2.metadata == {"k": "v"}


class TestBlockStatus:
    def test_terminal_statuses(self):
        terminal = BlockStatus.terminal()
        assert BlockStatus.COMPLETED in terminal
        assert BlockStatus.ROLLED_BACK in terminal
        assert BlockStatus.REJECTED in terminal
        assert BlockStatus.DETECTED not in terminal

    def test_is_terminal(self):
        assert BlockStatus.COMPLETED.is_terminal() is True
        assert BlockStatus.DETECTED.is_terminal() is False


# ---------------------------------------------------------------------------
# SomaticStore
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    s = SomaticStore(":memory:")
    yield s
    s.close()


class TestSomaticStore:
    def test_create_and_get(self, store):
        b = SomaticBlock.new(BlockType.SENSORY, "s1", finding_id="f1")
        assert store.create(b) is True
        got = store.get(b.id)
        assert got is not None
        assert got.block_type is BlockType.SENSORY
        assert got.finding_id == "f1"
        assert got.status is BlockStatus.DETECTED

    def test_get_missing_returns_none(self, store):
        assert store.get("nope") is None

    def test_create_idempotent(self, store):
        b = SomaticBlock.new(BlockType.SENSORY, "s1")
        assert store.create(b) is True
        # second create of same id is ignored (INSERT OR IGNORE)
        assert store.create(b) is True
        assert len(store.list_for_session("s1")) == 1

    def test_update_status_and_link_ids(self, store):
        b = SomaticBlock.new(BlockType.PROPOSAL, "s1", status=BlockStatus.PROPOSED)
        store.create(b)
        assert store.update_status(
            b.id, BlockStatus.PENDING_APPROVAL, approval_request_id="ar1"
        ) is True
        got = store.get(b.id)
        assert got.status is BlockStatus.PENDING_APPROVAL
        assert got.approval_request_id == "ar1"
        assert got.updated_at >= b.updated_at

    def test_update_status_ignores_unknown_link_keys(self, store):
        b = SomaticBlock.new(BlockType.ACTION, "s1")
        store.create(b)
        # 'bogus' is not an allowed link id and should be ignored
        store.update_status(b.id, BlockStatus.EXECUTING, bogus="x", action_id="a1")
        got = store.get(b.id)
        assert got.action_id == "a1"
        # bogus column was not added (no error)

    def test_list_for_session(self, store):
        for i in range(3):
            store.create(SomaticBlock.new(BlockType.SENSORY, "s1"))
        store.create(SomaticBlock.new(BlockType.SENSORY, "s2"))
        assert len(store.list_for_session("s1")) == 3
        assert len(store.list_for_session("s2")) == 1

    def test_list_by_type(self, store):
        store.create(SomaticBlock.new(BlockType.SENSORY, "s1"))
        store.create(SomaticBlock.new(BlockType.REFLECTION, "s1"))
        assert len(store.list_by_type(BlockType.SENSORY)) == 1
        assert len(store.list_by_type(BlockType.REFLECTION)) == 1

    def test_metadata_roundtrip(self, store):
        b = SomaticBlock.new(BlockType.DELIBERATION, "s1", metadata={"score": 0.8})
        store.create(b)
        got = store.get(b.id)
        assert got.metadata == {"score": 0.8}

    def test_update_status_missing_block_is_noop(self, store):
        # No crash; returns True (UPDATE affects 0 rows)
        assert store.update_status("nope", BlockStatus.COMPLETED) is True


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

def test_global_singleton():
    original = get_somatic_store()
    custom = SomaticStore(":memory:")
    set_somatic_store(custom)
    assert get_somatic_store() is custom
    set_somatic_store(original)