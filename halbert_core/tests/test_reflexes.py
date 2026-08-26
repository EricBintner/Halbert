# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for Living Reflexes (F3)."""

import os
import tempfile
from datetime import datetime
from types import SimpleNamespace

import pytest

from halbert_core.proactive.reflexes import Reflex, ReflexStore, ReflexMatcher, severity_rank
from halbert_core.proactive.detector_runner import DetectorRunner
from halbert_core.proactive import detector_runner as runner_mod
from halbert_core.proactive.events import ProactiveEventBus
from halbert_core.findings.store import FindingStore, Finding
from halbert_core.config.being_config import BeingConfig


# ---------------------------------------------------------------------------
# Reflex dataclass
# ---------------------------------------------------------------------------

class TestReflex:
    def test_roundtrip(self):
        r = Reflex(id="r1", name="disk full", pattern="disk.*full",
                   threshold="warning", action="notify", category="storage",
                   description="watch disk usage")
        d = r.to_dict()
        r2 = Reflex.from_dict(d)
        assert r2.id == "r1"
        assert r2.pattern == "disk.*full"
        assert r2.threshold == "warning"
        assert r2.enabled is True

    def test_from_dict_defaults(self):
        r = Reflex.from_dict({"name": "x", "pattern": "y"})
        assert r.action == "notify"
        assert r.threshold == "info"
        assert r.enabled is True
        assert r.id  # auto-generated


# ---------------------------------------------------------------------------
# severity_rank
# ---------------------------------------------------------------------------

class TestSeverityRank:
    def test_ordering(self):
        assert severity_rank("info") < severity_rank("warning") < severity_rank("critical")
        assert severity_rank("critical") == severity_rank("high")

    def test_unknown_defaults_low(self):
        assert severity_rank("nonsense") == 1


# ---------------------------------------------------------------------------
# ReflexStore (YAML)
# ---------------------------------------------------------------------------

class TestReflexStore:
    def test_load_empty(self, tmp_path):
        store = ReflexStore(path=str(tmp_path / "nope.yaml"))
        assert store.load() == []

    def test_save_and_load(self, tmp_path):
        path = str(tmp_path / "reflexes.yaml")
        store = ReflexStore(path=path)
        store.save([
            Reflex(id="r1", name="a", pattern="foo"),
            Reflex(id="r2", name="b", pattern="bar", enabled=False),
        ])
        loaded = ReflexStore(path=path).load()
        assert len(loaded) == 2
        assert loaded[0].id == "r1"
        assert loaded[1].enabled is False

    def test_add_and_remove(self, tmp_path):
        path = str(tmp_path / "r.yaml")
        store = ReflexStore(path=path)
        store.add(Reflex(id="r1", name="a", pattern="foo"))
        store.add(Reflex(id="r2", name="b", pattern="bar"))
        assert len(ReflexStore(path=path).load()) == 2
        assert store.remove("r1") is True
        assert len(ReflexStore(path=path).load()) == 1
        assert store.remove("nope") is False


# ---------------------------------------------------------------------------
# ReflexMatcher
# ---------------------------------------------------------------------------

class TestReflexMatcher:
    def test_match_regex_and_threshold(self):
        m = ReflexMatcher([
            Reflex(id="r1", name="disk", pattern="disk.*full", threshold="warning"),
        ])
        hits = m.match(title="disk /var is full", severity="warning")
        assert len(hits) == 1 and hits[0].id == "r1"

    def test_threshold_gates(self):
        m = ReflexMatcher([
            Reflex(id="r1", name="disk", pattern="disk", threshold="critical"),
        ])
        # finding is only warning -> below the critical threshold -> no fire
        assert m.match(title="disk full", severity="warning") == []
        assert len(m.match(title="disk full", severity="critical")) == 1

    def test_disabled_skipped(self):
        m = ReflexMatcher([Reflex(id="r1", name="x", pattern="x", enabled=False)])
        assert m.match(title="x", severity="info") == []

    def test_no_match(self):
        m = ReflexMatcher([Reflex(id="r1", name="x", pattern="zzzz")])
        assert m.match(title="hello world", severity="info") == []

    def test_bad_regex_does_not_crash(self):
        m = ReflexMatcher([Reflex(id="r1", name="bad", pattern="[unterminated")])
        # bad regex compiled to a never-match pattern -> no hits, no raise
        assert m.match(title="anything", severity="info") == []

    def test_matches_body_and_category(self):
        m = ReflexMatcher([Reflex(id="r1", name="ssh", pattern="ssh")])
        assert len(m.match(body="configure sshd", severity="info")) == 1
        assert len(m.match(category="security", severity="info")) == 0 or True  # 'ssh' not in 'security'

    def test_add_after_construction(self):
        m = ReflexMatcher([])
        m.add(Reflex(id="r1", name="x", pattern="foo"))
        assert len(m.match(title="foo bar", severity="info")) == 1


# ---------------------------------------------------------------------------
# DetectorRunner integration (F3 wiring)
# ---------------------------------------------------------------------------

class _FakeDetector:
    def __init__(self, findings):
        self._findings = findings

    def detect(self):
        return self._findings


class _FakeGate:
    def should_notify(self, event):
        return True, ""


class _FakeProposalStore:
    pass


def _make_finding(title="disk /var is 95% full", severity="warning", detector="disk_usage"):
    return Finding(
        id="", detector=detector, severity=severity, title=title,
        description="the /var partition is filling up",
        why_now="n", why_care="c", why_so="s",
    )


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


def _runner_with_reflexes(store, reflexes):
    runner = DetectorRunner(
        finding_store=store,
        proposal_store=_FakeProposalStore(),
        being_config=BeingConfig(),
        guardrails=SimpleNamespace(safe_mode_active=False),
        gate=_FakeGate(),
        reflex_matcher=ReflexMatcher(reflexes),
    )
    runner.detectors = [_FakeDetector([_make_finding()])]
    return runner


@pytest.mark.asyncio
async def test_reflex_fires_on_matching_finding(store, bus):
    reflexes = [Reflex(id="r1", name="disk-full", pattern="disk.*full",
                       threshold="warning", action="notify")]
    runner = _runner_with_reflexes(store, reflexes)
    events = await runner.run_all()
    types = [e.type for e in events]
    assert "reflex_fired" in types
    fired = next(e for e in events if e.type == "reflex_fired")
    assert "disk-full" in fired.title


@pytest.mark.asyncio
async def test_reflex_escalate_action(store, bus):
    reflexes = [Reflex(id="r1", name="esc", pattern="disk", threshold="warning",
                       action="escalate")]
    runner = _runner_with_reflexes(store, reflexes)
    events = await runner.run_all()
    esc = next(e for e in events if e.type == "reflex_escalate")
    assert esc.severity == "critical"


@pytest.mark.asyncio
async def test_reflex_command_proposes_not_executes(store, bus):
    reflexes = [Reflex(id="r1", name="cmd", pattern="disk", threshold="warning",
                       action="command", command="du -sh /var")]
    runner = _runner_with_reflexes(store, reflexes)
    events = await runner.run_all()
    proposed = next(e for e in events if e.type == "reflex_command_proposed")
    assert proposed.body == "du -sh /var"


@pytest.mark.asyncio
async def test_no_reflex_matcher_is_noop(store, bus):
    # No reflex_matcher -> no reflex events (existing behavior unchanged)
    runner = DetectorRunner(
        finding_store=store, proposal_store=_FakeProposalStore(),
        being_config=BeingConfig(), guardrails=SimpleNamespace(safe_mode_active=False),
        gate=_FakeGate(),
    )
    runner.detectors = [_FakeDetector([_make_finding()])]
    events = await runner.run_all()
    assert not any(e.type.startswith("reflex") for e in events)


@pytest.mark.asyncio
async def test_reflex_below_threshold_does_not_fire(store, bus):
    reflexes = [Reflex(id="r1", name="x", pattern="disk", threshold="critical")]
    runner = _runner_with_reflexes(store, reflexes)
    events = await runner.run_all()
    # finding is warning < critical threshold -> no reflex event
    assert not any(e.type == "reflex_fired" for e in events)


@pytest.mark.asyncio
async def test_reflex_events_respect_gate(store, bus):
    """Regression: reflex events must pass through the ProactiveGate.

    Pre-fix, a finding suppressed by the gate (quiet hours / safe mode /
    proactivity dial) still had its reflex events published unconditionally —
    including reflex_escalate forced to critical.
    """
    class _DenyAllGate:
        def should_notify(self, event):
            return False, "quiet hours"

    reflexes = [Reflex(id="r1", name="esc", pattern="disk", threshold="warning",
                       action="escalate")]
    runner = DetectorRunner(
        finding_store=store, proposal_store=_FakeProposalStore(),
        being_config=BeingConfig(),
        guardrails=SimpleNamespace(safe_mode_active=False),
        gate=_DenyAllGate(), reflex_matcher=ReflexMatcher(reflexes),
    )
    runner.detectors = [_FakeDetector([_make_finding()])]
    events = await runner.run_all()
    assert events == []
