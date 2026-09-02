# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the findings store (T5b.3)."""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from halbert_core.findings.store import FindingStore, Finding, FindingStatus


@pytest.fixture
def store():
    """Create a temporary FindingStore."""
    tmp = tempfile.mktemp(suffix=".db")
    s = FindingStore(db_path=tmp)
    yield s
    if os.path.exists(tmp):
        os.unlink(tmp)


@pytest.fixture
def sample_finding():
    return Finding(
        id="",
        detector="dropin_conflicts",
        severity="warning",
        title="SSH port conflict",
        description="sshd_config and drop-in both set Port",
        why_now="detected during scan",
        why_care="service may not bind expected port",
        why_so="base sets Port=22, drop-in sets Port=2222",
        why_trust=["/etc/ssh/sshd_config:5", "/etc/ssh/sshd_config.d/100.conf:1"],
        affected_paths=["/etc/ssh/sshd_config", "/etc/ssh/sshd_config.d/100.conf"],
        affected_services=["sshd"],
    )


class TestFindingCRUD:
    def test_add_generates_id_and_timestamp(self, store, sample_finding):
        fid = store.add(sample_finding)
        assert fid != ""
        assert sample_finding.id == fid
        assert sample_finding.created_at != ""

    def test_get_returns_finding(self, store, sample_finding):
        fid = store.add(sample_finding)
        got = store.get(fid)
        assert got is not None
        assert got.title == "SSH port conflict"
        assert got.why_trust == ["/etc/ssh/sshd_config:5", "/etc/ssh/sshd_config.d/100.conf:1"]
        assert got.affected_paths == ["/etc/ssh/sshd_config", "/etc/ssh/sshd_config.d/100.conf"]

    def test_get_nonexistent_returns_none(self, store):
        assert store.get("nonexistent-id") is None

    def test_list_open(self, store, sample_finding):
        store.add(sample_finding)
        store.add(Finding(
            id="", detector="test", severity="info",
            title="Another", description="d",
            why_now="n", why_care="c", why_so="s",
        ))
        opens = store.list_open()
        assert len(opens) == 2

    def test_list_by_severity(self, store, sample_finding):
        store.add(sample_finding)  # warning
        store.add(Finding(
            id="", detector="test", severity="critical",
            title="Critical", description="d",
            why_now="n", why_care="c", why_so="s",
        ))
        warnings = store.list_by_severity("warning")
        criticals = store.list_by_severity("critical")
        assert len(warnings) == 1
        assert len(criticals) == 1
        assert criticals[0].title == "Critical"

    def test_list_by_detector(self, store, sample_finding):
        store.add(sample_finding)
        results = store.list_by_detector("dropin_conflicts")
        assert len(results) == 1
        assert results[0].detector == "dropin_conflicts"

    def test_delete(self, store, sample_finding):
        fid = store.add(sample_finding)
        assert store.delete(fid) is True
        assert store.get(fid) is None
        assert store.delete(fid) is False

    def test_count(self, store, sample_finding):
        assert store.count() == 0
        store.add(sample_finding)
        assert store.count() == 1
        assert store.count(status="open") == 1
        assert store.count(status="resolved") == 0


class TestFindingSnooze:
    def test_snooze_sets_future_date(self, store, sample_finding):
        fid = store.add(sample_finding)
        assert store.snooze(fid, 7) is True

        got = store.get(fid)
        assert got.status == "snoozed"
        assert got.snoozed_until != ""

        # Verify the date is roughly 7 days from now
        snoozed_dt = datetime.fromisoformat(got.snoozed_until)
        now = datetime.now(timezone.utc)
        delta = snoozed_dt - now
        assert 6 <= delta.days <= 8  # allow slight timing variance

    def test_snooze_nonexistent_returns_false(self, store):
        assert store.snooze("nonexistent", 7) is False


class TestFindingDismiss:
    def test_dismiss_records_reason(self, store, sample_finding):
        fid = store.add(sample_finding)
        assert store.dismiss(fid, "intentional override") is True

        got = store.get(fid)
        assert got.status == "dismissed"
        assert got.dismissed_reason == "intentional override"

    def test_dismiss_nonexistent_returns_false(self, store):
        assert store.dismiss("nonexistent", "reason") is False


class TestFindingUpdateStatus:
    def test_resolve_sets_resolved_at(self, store, sample_finding):
        fid = store.add(sample_finding)
        assert store.update_status(fid, FindingStatus.RESOLVED.value) is True

        got = store.get(fid)
        assert got.status == "resolved"
        assert got.resolved_at != ""

    def test_link_proposal(self, store, sample_finding):
        fid = store.add(sample_finding)
        assert store.link_proposal(fid, "proposal-123") is True

        got = store.get(fid)
        assert got.proposal_id == "proposal-123"
        assert got.status == "open"  # still open


class TestFindingSerialization:
    def test_to_dict_and_from_dict_roundtrip(self, sample_finding):
        d = sample_finding.to_dict()
        restored = Finding.from_dict(d)
        assert restored.title == sample_finding.title
        assert restored.why_trust == sample_finding.why_trust
        assert restored.affected_paths == sample_finding.affected_paths


class TestListFindings:
    """list_findings(status, limit) — the one reader the route, the MCP
    tool and the page share (C2-05 / MCP-01)."""

    def _seed(self, store, sample_finding):
        open_id = store.add(sample_finding)
        snoozed = Finding.from_dict({**sample_finding.to_dict(), "id": "",
                                     "title": "snoozed one", "created_at": ""})
        snoozed_id = store.add(snoozed)
        store.snooze(snoozed_id, days=3)
        dismissed = Finding.from_dict({**sample_finding.to_dict(), "id": "",
                                       "title": "dismissed one", "created_at": ""})
        dismissed_id = store.add(dismissed)
        store.dismiss(dismissed_id, "not a problem")
        return open_id, snoozed_id, dismissed_id

    def test_default_returns_every_status(self, store, sample_finding):
        ids = self._seed(store, sample_finding)
        got = {f.id for f in store.list_findings()}
        assert got == set(ids)

    def test_all_is_the_same_as_no_filter(self, store, sample_finding):
        self._seed(store, sample_finding)
        assert [f.id for f in store.list_findings("all")] == [
            f.id for f in store.list_findings(None)
        ]

    def test_open_only(self, store, sample_finding):
        open_id, _, _ = self._seed(store, sample_finding)
        assert [f.id for f in store.list_findings("open")] == [open_id]

    def test_snoozed_and_dismissed(self, store, sample_finding):
        _, snoozed_id, dismissed_id = self._seed(store, sample_finding)
        assert [f.id for f in store.list_findings("snoozed")] == [snoozed_id]
        assert [f.id for f in store.list_findings("dismissed")] == [dismissed_id]

    def test_limit_applies(self, store, sample_finding):
        self._seed(store, sample_finding)
        assert len(store.list_findings(limit=2)) == 2
        assert len(store.list_findings("open", limit=0)) == 0

    def test_unknown_status_is_rejected(self, store):
        with pytest.raises(ValueError):
            store.list_findings("bogus")

    def test_rows_carry_the_four_whys(self, store, sample_finding):
        store.add(sample_finding)
        f = store.list_findings("open")[0]
        assert (f.why_now, f.why_care, f.why_so) == (
            "detected during scan",
            "service may not bind expected port",
            "base sets Port=22, drop-in sets Port=2222",
        )
        assert f.why_trust == sample_finding.why_trust
