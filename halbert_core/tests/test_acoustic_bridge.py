# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Task O5: acoustic anomaly -> findings -> ProactiveEventBus -> SSE chain.

The CED-tiny tagger's anomalies already reach the coordinator as
``AcousticEventObservation`` callbacks, and ``AcousticAnomalyDetector`` already
converts them into Findings — but nothing connected the two, so an anomaly
never became a proactive event. These tests pin the repaired chain:

  1. ``attach_acoustic_bridge`` sets the coordinator's ``on_acoustic_event``.
  2. A tagged observation flows coordinator callback -> ``add_event`` ->
     ``run_acoustic`` -> FindingStore row -> gated ProactiveEvent on the bus,
     with the structured payload the frontend module needs.
  3. ``run_acoustic`` drains ONLY the acoustic detector (a scheduled sweep
     still runs the filesystem detectors; a per-event bridge run must not).
  4. Severity mapping: tagger 0-3 -> info/warning/critical on the event.
  5. Dedup: a repeat of the same anomaly is suppressed while the finding is
     open (one SSE notification, one store row).
  6. Optional-detector no-op: when the findings stack cannot be built the
     bridge drops the event with a single warning (warning-once), and never
     raises into the audio pipeline.
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from types import SimpleNamespace

import pytest

from halbert_core.audio.config import AudioConfig
from halbert_core.audio.pipeline import AcousticEventObservation, AudioPipelineCoordinator
from halbert_core.config.being_config import BeingConfig
from halbert_core.findings.store import FindingStore
from halbert_core.proactive import acoustic_bridge as bridge_mod
from halbert_core.proactive import detector_runner as runner_mod
from halbert_core.proactive.acoustic_bridge import (
    AcousticAnomalyBridge,
    attach_acoustic_bridge,
    reset_acoustic_bridge,
)
from halbert_core.proactive.detector_runner import DetectorRunner
from halbert_core.proactive.events import ProactiveEventBus


# ---------------------------------------------------------------------------
# Helpers (patterns lifted from test_detector_runner.py)
# ---------------------------------------------------------------------------

class FakeGate:
    def __init__(self, allow=True):
        self.allow = allow
        self.seen = []

    def should_notify(self, event):
        self.seen.append(event)
        return (True, "") if self.allow else (False, "suppressed by fake gate")


class FakeProposalStore:
    """DetectorRunner never touches the proposal store in these tests."""


class ExplodingDetector:
    """detect() must never be called by run_acoustic."""

    def detect(self):
        raise AssertionError("run_acoustic must not run filesystem detectors")


def make_runner(store, gate):
    return DetectorRunner(
        finding_store=store,
        proposal_store=FakeProposalStore(),
        being_config=BeingConfig(),
        guardrails=SimpleNamespace(safe_mode_active=False),
        gate=gate,
    )


def make_bridge(store, gate) -> AcousticAnomalyBridge:
    return AcousticAnomalyBridge(runner_factory=lambda: make_runner(store, gate))


def obs(**overrides) -> AcousticEventObservation:
    fields = dict(
        sound_class="smoke_alarm",
        confidence=0.93,
        area_id="kitchen",
        decibel_level=88.0,
        anomaly_severity=3,
        source="ambient",
    )
    fields.update(overrides)
    return AcousticEventObservation(**fields)


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


@pytest.fixture(autouse=True)
def _fresh_bridge_singleton():
    reset_acoustic_bridge()
    yield
    reset_acoustic_bridge()


# ---------------------------------------------------------------------------
# 1 + 2: attach + the full chain
# ---------------------------------------------------------------------------

class TestAttachAndChain:
    async def test_attach_sets_acoustic_callback(self, store, bus):
        gate = FakeGate()
        coordinator = AudioPipelineCoordinator(config=AudioConfig(enabled=True))
        assert coordinator.on_acoustic_event is None

        bridge = attach_acoustic_bridge(coordinator, bridge=make_bridge(store, gate))

        assert coordinator.on_acoustic_event is not None
        assert bridge is not None

    async def test_event_flows_to_bus_with_structured_payload(
        self, store, bus, caplog
    ):
        gate = FakeGate()
        coordinator = AudioPipelineCoordinator(config=AudioConfig(enabled=True))
        attach_acoustic_bridge(coordinator, bridge=make_bridge(store, gate))

        with caplog.at_level(logging.INFO, logger="halbert.proactive.detector_runner"):
            await coordinator.on_acoustic_event(obs())

        assert len(bus.get_recent()) == 1
        event = bus.get_recent()[0]
        # The wire type is "finding" (it links to a snoozable finding row);
        # the acoustic discriminator is the CATEGORY DetectorRunner assigns.
        assert event.type == "finding"
        assert event.category == "acoustic"
        assert event.severity == "critical"
        assert event.title == "Acoustic anomaly: Smoke detector alarm in kitchen"
        assert event.finding_id
        # Structured payload for the frontend AcousticAnomalyModule
        assert event.data == {
            "sound_class": "smoke_alarm",
            "confidence": 0.93,
            "area_id": "kitchen",
            "decibel_level": 88.0,
            "anomaly_severity": 3,
            "source": "ambient",
            "timestamp": event.data["timestamp"],
        }
        # UTC-aware ISO-8601 (the store's convention; JS Date parses it)
        assert event.data["timestamp"].endswith("+00:00")
        assert datetime.fromisoformat(event.data["timestamp"]).utcoffset() is not None
        # The finding row is stored and linked, and the transient structured
        # payload is NOT persisted (no DB column — round-trip strips it).
        stored = store.get(event.finding_id)
        assert stored.detector == "acoustic_anomaly"
        assert stored.data is None
        # The gate was consulted (quiet hours / proactivity dial apply)
        assert len(gate.seen) == 1

    async def test_moderate_anomaly_maps_to_warning(self, store, bus):
        coordinator = AudioPipelineCoordinator(config=AudioConfig(enabled=True))
        attach_acoustic_bridge(coordinator, bridge=make_bridge(store, FakeGate()))
        await coordinator.on_acoustic_event(
            obs(anomaly_severity=1, sound_class="mechanical_fan", confidence=0.7)
        )

        event = bus.get_recent()[0]
        assert event.severity == "warning"
        assert event.data["sound_class"] == "mechanical_fan"


# ---------------------------------------------------------------------------
# 3: run_acoustic drains only the acoustic detector
# ---------------------------------------------------------------------------

class TestRunAcousticScope:
    async def test_run_acoustic_skips_filesystem_detectors(self, store, bus):
        runner = make_runner(store, FakeGate())
        runner.detectors = [ExplodingDetector(), runner.acoustic_detector]
        runner.acoustic_detector.add_event(
            sound_class="glass_breaking", confidence=0.8, anomaly_severity=2,
            area_id="hall", source="ambient",
        )

        events = await runner.run_acoustic()

        assert len(events) == 1
        assert events[0].category == "acoustic"


# ---------------------------------------------------------------------------
# 4 + 5: severity mapping and dedup
# ---------------------------------------------------------------------------

class TestSeverityAndDedup:
    @pytest.mark.parametrize(
        ("severity_num", "expected"),
        [(1, "warning"), (2, "warning"), (3, "critical")],
    )
    async def test_severity_mapping(self, store, bus, severity_num, expected):
        bridge = make_bridge(store, FakeGate())
        await bridge.handle(obs(anomaly_severity=severity_num, confidence=0.9))

        assert bus.get_recent()[0].severity == expected

    async def test_non_anomaly_produces_no_event(self, store, bus):
        bridge = make_bridge(store, FakeGate())
        # severity 0 + confidence < 0.5 is skipped by the detector
        await bridge.handle(obs(anomaly_severity=0, confidence=0.3))

        assert bus.get_recent() == []
        assert store.list_all() == []

    async def test_repeat_anomaly_is_deduped_while_open(self, store, bus):
        bridge = make_bridge(store, FakeGate())
        await bridge.handle(obs())
        await bridge.handle(obs())

        assert len(bus.get_recent()) == 1
        assert len(store.list_all()) == 1


# ---------------------------------------------------------------------------
# 6: quiet hours — a severity-2 anomaly still wakes (O5 review fix 2)
# ---------------------------------------------------------------------------

class TestQuietHoursWake:
    """End-to-end: the real ProactiveGate must let a confirmed (severity-2)
    acoustic anomaly through during quiet hours. It maps to Finding severity
    "warning", which quiet hours would otherwise suppress — the exact window
    in which the urgent wake chain must fire."""

    async def test_severity_2_passes_real_gate_during_quiet_hours(
        self, store, bus, monkeypatch
    ):
        from halbert_core.proactive.gate import ProactiveGate

        monkeypatch.setattr(ProactiveGate, "_in_quiet_hours", lambda self: True)
        gate = ProactiveGate(
            BeingConfig(quiet_hours={"start": "22:00", "end": "07:00"}),
            guardrail_enforcer=SimpleNamespace(safe_mode_active=False),
            finding_store=store,
        )
        runner = DetectorRunner(
            finding_store=store,
            proposal_store=FakeProposalStore(),
            being_config=BeingConfig(quiet_hours={"start": "22:00", "end": "07:00"}),
            guardrails=SimpleNamespace(safe_mode_active=False),
            gate=gate,
        )
        bridge = AcousticAnomalyBridge(runner_factory=lambda: runner)

        published = await bridge.handle(
            obs(anomaly_severity=2, sound_class="glass_breaking")
        )

        assert len(published) == 1
        assert published[0].category == "acoustic"
        assert len(bus.get_recent()) == 1

    async def test_severity_1_acoustic_still_suppressed_in_quiet_hours(
        self, store, bus, monkeypatch
    ):
        from halbert_core.proactive.gate import ProactiveGate

        monkeypatch.setattr(ProactiveGate, "_in_quiet_hours", lambda self: True)
        gate = ProactiveGate(
            BeingConfig(quiet_hours={"start": "22:00", "end": "07:00"}),
            guardrail_enforcer=SimpleNamespace(safe_mode_active=False),
            finding_store=store,
        )
        runner = DetectorRunner(
            finding_store=store,
            proposal_store=FakeProposalStore(),
            being_config=BeingConfig(quiet_hours={"start": "22:00", "end": "07:00"}),
            guardrails=SimpleNamespace(safe_mode_active=False),
            gate=gate,
        )
        bridge = AcousticAnomalyBridge(runner_factory=lambda: runner)

        published = await bridge.handle(
            obs(anomaly_severity=1, sound_class="mechanical_fan", confidence=0.9)
        )

        # Stored (the detector ran) but suppressed by quiet hours — only
        # wake-worthy severity bypasses, not every acoustic event.
        assert published == []
        assert bus.get_recent() == []
        assert len(store.list_all()) == 1


# ---------------------------------------------------------------------------
# 7: optional-detector no-op (warning-once)
# ---------------------------------------------------------------------------

class TestOptionalNoop:
    async def test_broken_findings_stack_is_warning_once_noop(
        self, store, bus, caplog
    ):
        def _boom():
            raise RuntimeError("findings stack unavailable")

        bridge = AcousticAnomalyBridge(runner_factory=_boom)

        with caplog.at_level(logging.DEBUG, logger="halbert.proactive.acoustic_bridge"):
            result1 = await bridge.handle(obs())
            result2 = await bridge.handle(obs())

        assert result1 == []
        assert result2 == []
        assert bus.get_recent() == []
        warnings = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "findings stack unavailable" in r.message
        ]
        assert len(warnings) == 1  # second failure drops to debug, not a second warning

    async def test_handler_never_raises_into_pipeline(self, store, bus):
        def _boom():
            raise RuntimeError("boom")

        coordinator = AudioPipelineCoordinator(config=AudioConfig(enabled=True))
        attach_acoustic_bridge(coordinator, bridge=AcousticAnomalyBridge(runner_factory=_boom))

        # The coordinator's own callback guard would log this; the bridge
        # itself must already have swallowed it.
        await coordinator.on_acoustic_event(obs())
