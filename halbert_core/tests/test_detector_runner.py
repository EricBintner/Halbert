# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the detector runner (T7e)."""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from halbert_core.findings.store import FindingStore, Finding, FindingStatus
from halbert_core.config.being_config import BeingConfig
from halbert_core.proactive.events import ProactiveEventBus
from halbert_core.proactive.detector_runner import DetectorRunner, _EVENT_CATEGORY
from halbert_core.proactive import detector_runner as runner_mod


class FakeDetector:
    def __init__(self, findings):
        self._findings = findings

    def detect(self):
        return self._findings


class FakeGate:
    def __init__(self, allow=True):
        self.allow = allow
        self.seen = []

    def should_notify(self, event):
        self.seen.append(event)
        return (True, "") if self.allow else (False, "suppressed by fake gate")


class FakeProposalStore:
    """DetectorRunner never touches the proposal store in these tests."""


def make_finding(detector="dropin_conflicts", severity="warning",
                 title="SSH port conflict"):
    return Finding(
        id="",
        detector=detector,
        severity=severity,
        title=title,
        description="desc",
        why_now="n",
        why_care="c",
        why_so="s",
    )


def make_runner(store, gate, findings):
    runner = DetectorRunner(
        finding_store=store,
        proposal_store=FakeProposalStore(),
        being_config=BeingConfig(),
        guardrails=SimpleNamespace(safe_mode_active=False),
        gate=gate,
    )
    runner.detectors = [FakeDetector(findings)]
    return runner


@pytest.fixture
def store():
    tmp = tempfile.mktemp(suffix=".db")
    s = FindingStore(db_path=tmp)
    yield s
    if os.path.exists(tmp):
        os.unlink(tmp)


@pytest.fixture
def bus(monkeypatch):
    b = ProactiveEventBus()
    monkeypatch.setattr(runner_mod, "get_event_bus", lambda: b)
    return b


class TestDedup:
    def test_duplicate_fingerprint_not_re_added_or_republished(self, store, bus):
        gate = FakeGate()
        runner = make_runner(store, gate, [make_finding()])

        first = asyncio.run(runner.run_all())
        assert len(first) == 1
        assert store.count() == 1

        second = asyncio.run(runner.run_all())
        assert second == []
        assert store.count() == 1
        assert len(bus.get_recent()) == 1

    def test_different_title_is_not_a_duplicate(self, store, bus):
        gate = FakeGate()
        runner = make_runner(store, gate, [
            make_finding(title="conflict A"),
            make_finding(title="conflict B"),
        ])
        events = asyncio.run(runner.run_all())
        assert len(events) == 2
        assert store.count() == 2


class TestSnoozeLifecycle:
    def test_active_snooze_suppresses_re_event(self, store, bus):
        gate = FakeGate()
        runner = make_runner(store, gate, [make_finding()])
        asyncio.run(runner.run_all())

        fid = store.list_all()[0].id
        store.snooze(fid, 7)

        second = asyncio.run(runner.run_all())
        assert second == []
        assert store.count() == 1
        assert store.get(fid).status == FindingStatus.SNOOZED.value
        assert len(bus.get_recent()) == 1

    def test_expired_snooze_resurfaces(self, store, bus):
        gate = FakeGate()
        runner = make_runner(store, gate, [make_finding()])
        asyncio.run(runner.run_all())

        fid = store.list_all()[0].id
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        store.update_status(fid, FindingStatus.SNOOZED.value, snoozed_until=past)

        second = asyncio.run(runner.run_all())
        assert len(second) == 1
        # Re-surfaced the same row — no duplicate
        assert second[0].finding_id == fid
        assert store.count() == 1
        reopened = store.get(fid)
        assert reopened.status == FindingStatus.OPEN.value
        assert reopened.snoozed_until == ""

    def test_expired_snooze_tolerates_offset_plus_z_suffix(self, store, bus):
        gate = FakeGate()
        runner = make_runner(store, gate, [make_finding()])
        asyncio.run(runner.run_all())

        fid = store.list_all()[0].id
        # Some repo code produces '+00:00Z' — must still parse
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat() + "Z"
        store.update_status(fid, FindingStatus.SNOOZED.value, snoozed_until=past)

        second = asyncio.run(runner.run_all())
        assert len(second) == 1
        assert store.get(fid).status == FindingStatus.OPEN.value

    def test_active_snooze_with_z_suffix_still_suppresses(self, store, bus):
        gate = FakeGate()
        runner = make_runner(store, gate, [make_finding()])
        asyncio.run(runner.run_all())

        fid = store.list_all()[0].id
        future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        store.update_status(
            fid, FindingStatus.SNOOZED.value,
            snoozed_until=future.replace("+00:00", "Z"),
        )

        second = asyncio.run(runner.run_all())
        assert second == []
        assert store.get(fid).status == FindingStatus.SNOOZED.value

    def test_dismissed_suppresses_forever(self, store, bus):
        gate = FakeGate()
        runner = make_runner(store, gate, [make_finding()])
        asyncio.run(runner.run_all())

        fid = store.list_all()[0].id
        store.dismiss(fid, "intentional")

        second = asyncio.run(runner.run_all())
        assert second == []
        assert store.count() == 1


class TestGateFiltering:
    def test_suppressed_findings_produce_no_published_event(self, store, bus):
        gate = FakeGate(allow=False)
        runner = make_runner(store, gate, [make_finding()])

        events = asyncio.run(runner.run_all())
        assert events == []
        assert bus.get_recent() == []
        # Finding was still stored — suppression is about notification only
        assert store.count() == 1
        # But the gate was consulted
        assert len(gate.seen) == 1


class TestCategories:
    @pytest.mark.parametrize("detector,expected", [
        ("dropin_conflicts", "config"),
        ("fstab_phantom", "storage"),
        ("permissions_hygiene", "security"),
        ("some_new_detector", "general"),
    ])
    def test_detector_maps_to_category(self, store, bus, detector, expected):
        gate = FakeGate()
        runner = make_runner(
            store, gate, [make_finding(detector=detector, title=f"{detector} issue")]
        )
        events = asyncio.run(runner.run_all())
        assert events[0].category == expected
        assert _EVENT_CATEGORY.get(detector, "general") == expected

    def test_event_carries_finding_id(self, store, bus):
        gate = FakeGate()
        runner = make_runner(store, gate, [make_finding()])
        events = asyncio.run(runner.run_all())
        assert events[0].finding_id == store.list_all()[0].id


class TestSyncWrapper:
    def test_run_all_sync_without_running_loop(self, store, bus):
        gate = FakeGate()
        runner = make_runner(store, gate, [make_finding()])
        events = runner.run_all_sync()
        assert len(events) == 1
        assert bus.get_recent()[0].title == "SSH port conflict"


class TestWhysOnTheEvent:
    """C2-02: the finding event carries the four whys and affected paths."""

    def test_event_carries_whys_and_paths(self, store, bus):
        finding = make_finding()
        finding.why_trust = ["/etc/ssh/sshd_config:5"]
        finding.affected_paths = ["/etc/ssh/sshd_config"]
        runner = make_runner(store, FakeGate(), [finding])
        events = asyncio.run(runner.run_all())
        ev = events[0]
        assert ev.why == {
            "now": "n", "care": "c", "so": "s",
            "trust": ["/etc/ssh/sshd_config:5"],
        }
        assert ev.affected_paths == ["/etc/ssh/sshd_config"]
        # ...and they survive the wire format the SSE route emits.
        d = ev.to_dict()
        assert d["why"]["care"] == "c"
        assert d["affected_paths"] == ["/etc/ssh/sshd_config"]

    def test_resurfaced_finding_keeps_its_proposal_id(self, store, bus):
        finding = make_finding()
        fid = store.add(finding)
        store.link_proposal(fid, "prop-1")
        store.update_status(fid, FindingStatus.RESOLVED.value)
        runner = make_runner(store, FakeGate(), [make_finding()])
        events = asyncio.run(runner.run_all())
        assert events[0].finding_id == fid
        assert events[0].proposal_id == "prop-1"


class FakeGenerator:
    def __init__(self, proposal_id="prop-auto", fail=False):
        self.proposal_id = proposal_id
        self.fail = fail
        self.calls = []

    def generate_for_finding(self, finding_id):
        self.calls.append(finding_id)
        if self.fail:
            raise RuntimeError("boom")
        return self.proposal_id


def _ssh_key(tmp_path):
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir(exist_ok=True)
    key = ssh_dir / "id_rsa"
    key.write_text("key\n")
    key.chmod(0o644)
    return str(key)


def _executable_finding(tmp_path):
    f = make_finding(detector="permissions_hygiene", title="Loose key mode")
    f.affected_paths = [_ssh_key(tmp_path)]
    return f


class TestProposeAtDetection:
    """J3-7: a NEW finding with an executable fix gets its proposal on the
    sweep; manual-review findings and re-surfaced ones do not."""

    def _runner(self, store, findings, generator):
        runner = make_runner(store, FakeGate(), findings)
        runner.proposal_generator = generator
        return runner

    def test_executable_finding_is_proposed_and_event_links_it(self, store, bus, tmp_path):
        gen = FakeGenerator()
        runner = self._runner(store, [_executable_finding(tmp_path)], gen)
        events = asyncio.run(runner.run_all())
        fid = store.list_all()[0].id
        assert gen.calls == [fid]
        assert events[0].proposal_id == "prop-auto"

    def test_manual_review_finding_gets_no_proposal(self, store, bus):
        gen = FakeGenerator()
        dropin = make_finding(detector="dropin_conflicts")
        dropin.affected_paths = ["/etc/ssh/sshd_config.d/10.conf"]
        fstab = make_finding(detector="fstab_phantom", title="Phantom mount")
        fstab.affected_paths = ["/etc/fstab"]
        runner = self._runner(store, [dropin, fstab], gen)
        events = asyncio.run(runner.run_all())
        assert gen.calls == []
        assert [e.proposal_id for e in events] == [None, None]

    def test_resurfaced_finding_is_not_reproposed(self, store, bus, tmp_path):
        first = _executable_finding(tmp_path)
        fid = store.add(first)
        store.link_proposal(fid, "prop-old")
        store.update_status(fid, FindingStatus.RESOLVED.value)
        gen = FakeGenerator()
        runner = self._runner(store, [_executable_finding(tmp_path)], gen)
        events = asyncio.run(runner.run_all())
        assert gen.calls == []
        assert events[0].proposal_id == "prop-old"

    def test_generator_failure_is_not_fatal(self, store, bus, tmp_path):
        gen = FakeGenerator(fail=True)
        runner = self._runner(store, [_executable_finding(tmp_path)], gen)
        events = asyncio.run(runner.run_all())
        assert len(events) == 1
        assert events[0].proposal_id is None
        assert store.count("open") == 1

    def test_injected_generator_is_used_over_the_default(self, store, bus, tmp_path):
        gen = FakeGenerator(proposal_id="prop-injected")
        runner = DetectorRunner(
            finding_store=store,
            proposal_store=FakeProposalStore(),
            being_config=BeingConfig(),
            guardrails=SimpleNamespace(safe_mode_active=False),
            gate=FakeGate(),
            proposal_generator=gen,
        )
        runner.detectors = [FakeDetector([_executable_finding(tmp_path)])]
        events = asyncio.run(runner.run_all())
        assert events[0].proposal_id == "prop-injected"
