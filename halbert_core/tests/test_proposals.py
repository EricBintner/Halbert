# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the proposals store (T5b.3)."""

import os
import tempfile

import pytest

from halbert_core.findings.store import FindingStore, Finding
from halbert_core.findings.proposals import (
    ProposalStore,
    Proposal,
    ProposalStatus,
)


@pytest.fixture
def db_path():
    tmp = tempfile.mktemp(suffix=".db")
    yield tmp
    if os.path.exists(tmp):
        os.unlink(tmp)


@pytest.fixture
def fstore(db_path):
    return FindingStore(db_path=db_path)


@pytest.fixture
def pstore(db_path):
    return ProposalStore(db_path=db_path)


@pytest.fixture
def finding_id(fstore):
    f = Finding(
        id="",
        detector="test",
        severity="warning",
        title="Test finding",
        description="desc",
        why_now="now",
        why_care="care",
        why_so="so",
    )
    return fstore.add(f)


@pytest.fixture
def sample_proposal(finding_id):
    return Proposal(
        id="",
        finding_id=finding_id,
        action="Remove conflicting drop-in",
        changes=[
            {
                "path": "/etc/ssh/sshd_config.d/100.conf",
                "key": "Port",
                "old_value": "2222",
                "new_value": None,
            }
        ],
        dry_run_result={"preview": "would remove Port=2222"},
        blast_radius=["sshd.service"],
    )


class TestProposalCRUD:
    def test_add_generates_id_and_timestamp(self, pstore, sample_proposal):
        pid = pstore.add(sample_proposal)
        assert pid != ""
        assert sample_proposal.id == pid
        assert sample_proposal.created_at != ""

    def test_get_returns_proposal(self, pstore, sample_proposal):
        pid = pstore.add(sample_proposal)
        got = pstore.get(pid)
        assert got is not None
        assert got.action == "Remove conflicting drop-in"
        assert got.changes[0]["path"] == "/etc/ssh/sshd_config.d/100.conf"
        assert got.blast_radius == ["sshd.service"]
        assert got.dry_run_result == {"preview": "would remove Port=2222"}

    def test_get_nonexistent_returns_none(self, pstore):
        assert pstore.get("nonexistent") is None

    def test_list_pending(self, pstore, sample_proposal):
        pstore.add(sample_proposal)
        pending = pstore.list_pending()
        assert len(pending) == 1
        assert pending[0].status == "pending"

    def test_list_for_finding(self, pstore, sample_proposal, finding_id):
        pstore.add(sample_proposal)
        results = pstore.list_for_finding(finding_id)
        assert len(results) == 1
        assert results[0].finding_id == finding_id

    def test_list_all(self, pstore, sample_proposal):
        pstore.add(sample_proposal)
        all_props = pstore.list_all()
        assert len(all_props) == 1

    def test_delete(self, pstore, sample_proposal):
        pid = pstore.add(sample_proposal)
        assert pstore.delete(pid) is True
        assert pstore.get(pid) is None


class TestProposalStatusTransitions:
    def test_approve_sets_approved_at(self, pstore, sample_proposal):
        pid = pstore.add(sample_proposal)
        assert pstore.approve(pid, approval_request_id="apr-123") is True

        got = pstore.get(pid)
        assert got.status == "approved"
        assert got.approved_at != ""
        assert got.approval_request_id == "apr-123"

    def test_reject_records_reason(self, pstore, sample_proposal):
        pid = pstore.add(sample_proposal)
        assert pstore.reject(pid, "too risky") is True

        got = pstore.get(pid)
        assert got.status == "rejected"
        assert got.rejection_reason == "too risky"

    def test_mark_applied_sets_applied_at(self, pstore, sample_proposal):
        pid = pstore.add(sample_proposal)
        pstore.approve(pid)
        assert pstore.mark_applied(pid) is True

        got = pstore.get(pid)
        assert got.status == "applied"
        assert got.applied_at != ""

    def test_mark_rolled_back_sets_rolled_back_at(self, pstore, sample_proposal):
        pid = pstore.add(sample_proposal)
        pstore.approve(pid)
        assert pstore.mark_rolled_back(pid) is True

        got = pstore.get(pid)
        assert got.status == "rolled_back"
        assert got.rolled_back_at != ""


class TestProposalFindingLinkage:
    def test_multiple_proposals_for_one_finding(self, pstore, sample_proposal, finding_id):
        pstore.add(sample_proposal)
        p2 = Proposal(
            id="",
            finding_id=finding_id,
            action="Different fix approach",
        )
        pstore.add(p2)
        results = pstore.list_for_finding(finding_id)
        assert len(results) == 2


class TestProposalSerialization:
    def test_to_dict_and_from_dict_roundtrip(self, sample_proposal):
        d = sample_proposal.to_dict()
        restored = Proposal.from_dict(d)
        assert restored.action == sample_proposal.action
        assert restored.changes == sample_proposal.changes
        assert restored.blast_radius == sample_proposal.blast_radius
