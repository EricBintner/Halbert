# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the proactive gate (T7c)."""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from halbert_core.config.being_config import BeingConfig
from halbert_core.proactive.events import ProactiveEvent
from halbert_core.proactive.gate import ProactiveGate
from halbert_core.proactive import gate as gate_mod
from halbert_core.findings.store import FindingStore, Finding, FindingStatus


def make_event(severity="warning", category="general", finding_id=None):
    return ProactiveEvent.create(
        type="finding",
        severity=severity,
        title="Test finding",
        body="body",
        category=category,
        finding_id=finding_id,
    )


def make_gate(proactivity="balanced", guardrails=None, findings=None, **kwargs):
    config = BeingConfig(proactivity=proactivity, **kwargs)
    if guardrails is None:
        guardrails = SimpleNamespace(safe_mode_active=False)
    return ProactiveGate(
        config, guardrail_enforcer=guardrails, finding_store=findings
    )


@pytest.fixture
def store():
    tmp = tempfile.mktemp(suffix=".db")
    s = FindingStore(db_path=tmp)
    yield s
    if os.path.exists(tmp):
        os.unlink(tmp)


@pytest.fixture
def finding(store):
    f = Finding(
        id="",
        detector="dropin_conflicts",
        severity="warning",
        title="SSH port conflict",
        description="desc",
        why_now="n",
        why_care="c",
        why_so="s",
    )
    fid = store.add(f)
    return fid


class _FrozenDateTime(datetime):
    """datetime subclass whose now() returns a fixed value."""

    frozen = None

    @classmethod
    def now(cls, tz=None):
        return cls.frozen


class TestDialMatrix:
    """off suppresses all; quiet -> critical only; balanced -> warning+;
    assertive -> everything."""

    @pytest.mark.parametrize("severity", ["info", "warning", "critical"])
    def test_off_suppresses_everything(self, severity):
        gate = make_gate(proactivity="off")
        allowed, reason = gate.should_notify(make_event(severity=severity))
        assert allowed is False
        assert "off" in reason

    def test_quiet_allows_critical_only(self):
        gate = make_gate(proactivity="quiet")
        assert gate.should_notify(make_event(severity="info"))[0] is False
        assert gate.should_notify(make_event(severity="warning"))[0] is False
        assert gate.should_notify(make_event(severity="critical"))[0] is True

    def test_balanced_allows_warning_and_critical(self):
        gate = make_gate(proactivity="balanced")
        assert gate.should_notify(make_event(severity="info"))[0] is False
        assert gate.should_notify(make_event(severity="warning"))[0] is True
        assert gate.should_notify(make_event(severity="critical"))[0] is True

    def test_assertive_allows_everything(self):
        gate = make_gate(proactivity="assertive")
        for severity in ("info", "warning", "critical"):
            assert gate.should_notify(make_event(severity=severity))[0] is True


class TestQuietHours:
    def test_same_day_range_suppresses_non_critical(self, monkeypatch):
        monkeypatch.setattr(gate_mod, "datetime", _FrozenDateTime)
        _FrozenDateTime.frozen = datetime(2026, 8, 24, 15, 0)
        gate = make_gate(quiet_hours={"start": "14:00", "end": "18:00"})

        allowed, reason = gate.should_notify(make_event(severity="warning"))
        assert allowed is False
        assert "quiet hours" in reason
        # Critical events still get through
        assert gate.should_notify(make_event(severity="critical"))[0] is True

    def test_outside_quiet_hours_allows(self, monkeypatch):
        monkeypatch.setattr(gate_mod, "datetime", _FrozenDateTime)
        _FrozenDateTime.frozen = datetime(2026, 8, 24, 12, 0)
        gate = make_gate(quiet_hours={"start": "14:00", "end": "18:00"})
        assert gate.should_notify(make_event(severity="warning"))[0] is True

    def test_overnight_wrap_suppresses_late_evening(self, monkeypatch):
        monkeypatch.setattr(gate_mod, "datetime", _FrozenDateTime)
        _FrozenDateTime.frozen = datetime(2026, 8, 24, 23, 30)
        gate = make_gate(quiet_hours={"start": "22:00", "end": "07:00"})
        assert gate.should_notify(make_event(severity="warning"))[0] is False

    def test_overnight_wrap_suppresses_early_morning(self, monkeypatch):
        monkeypatch.setattr(gate_mod, "datetime", _FrozenDateTime)
        _FrozenDateTime.frozen = datetime(2026, 8, 24, 6, 15)
        gate = make_gate(quiet_hours={"start": "22:00", "end": "07:00"})
        assert gate.should_notify(make_event(severity="warning"))[0] is False

    def test_overnight_wrap_allows_midday(self, monkeypatch):
        monkeypatch.setattr(gate_mod, "datetime", _FrozenDateTime)
        _FrozenDateTime.frozen = datetime(2026, 8, 24, 12, 0)
        gate = make_gate(quiet_hours={"start": "22:00", "end": "07:00"})
        assert gate.should_notify(make_event(severity="warning"))[0] is True


def make_acoustic_event(anomaly_severity, severity="warning", data="default"):
    """Acoustic anomaly finding event, as DetectorRunner publishes it (O5).

    ``data="default"`` builds the structured payload; pass None for an event
    without one.
    """
    if data == "default":
        data = {
            "sound_class": "glass_breaking",
            "confidence": 0.9,
            "area_id": "hall",
            "decibel_level": 74.0,
            "anomaly_severity": anomaly_severity,
            "source": "ambient",
            "timestamp": "2026-08-31T12:00:00+00:00",
        }
    return ProactiveEvent.create(
        type="finding",
        severity=severity,
        title="Acoustic anomaly: Glass break",
        body="Detected Glass break at 90% confidence.",
        category="acoustic",
        data=data,
    )


class TestAcousticLifeSafetyBypass:
    """O5: a CONFIRMED acoustic anomaly (tagger anomaly_severity >= 2) is
    life-safety for quiet hours. It maps to Finding severity "warning",
    which quiet hours would otherwise suppress — exactly the window in which
    the urgent wake chain must fire. (The engine's LIFE_SAFETY_EVENT_TYPES
    keys on sound classes, not the "acoustic" category, so it cannot make
    this call — the structured payload's severity is authoritative.)"""

    def _quiet_gate(self, monkeypatch):
        # 15:00 inside the 14:00-18:00 quiet window (the _FrozenDateTime
        # pattern from TestQuietHours).
        monkeypatch.setattr(gate_mod, "datetime", _FrozenDateTime)
        _FrozenDateTime.frozen = datetime(2026, 8, 24, 15, 0)
        return make_gate(quiet_hours={"start": "14:00", "end": "18:00"})

    def test_severity_2_bypasses_quiet_hours(self, monkeypatch):
        gate = self._quiet_gate(monkeypatch)
        allowed, reason = gate.should_notify(make_acoustic_event(2))
        assert allowed is True
        assert reason == ""

    def test_severity_1_acoustic_still_suppressed_in_quiet_hours(self, monkeypatch):
        gate = self._quiet_gate(monkeypatch)
        allowed, reason = gate.should_notify(make_acoustic_event(1))
        assert allowed is False
        assert "quiet hours" in reason

    def test_bypass_requires_the_structured_payload(self, monkeypatch):
        gate = self._quiet_gate(monkeypatch)
        # category alone (old events / a publisher without data) must not
        # trust a missing severity
        allowed, _ = gate.should_notify(make_acoustic_event(2, data=None))
        assert allowed is False

    def test_bypass_does_not_leak_to_other_categories(self, monkeypatch):
        gate = self._quiet_gate(monkeypatch)
        event = ProactiveEvent.create(
            type="finding", severity="warning", title="t", body="b",
            category="security",
            data={"anomaly_severity": 3, "sound_class": "smoke_alarm"},
        )
        assert gate.should_notify(event)[0] is False


class TestCategoryOverrides:
    def test_override_beats_stricter_global_dial(self):
        gate = make_gate(
            proactivity="off",
            category_overrides={"security": "assertive"},
        )
        # security override lifts the global "off" for this category
        event = make_event(severity="info", category="security")
        assert gate.should_notify(event)[0] is True
        # unmatched categories still follow the global dial
        event = make_event(severity="critical", category="general")
        assert gate.should_notify(event)[0] is False

    def test_override_beats_looser_global_dial(self):
        gate = make_gate(
            proactivity="assertive",
            category_overrides={"storage": "quiet"},
        )
        # storage override tightens: warning suppressed, critical allowed
        assert gate.should_notify(
            make_event(severity="warning", category="storage")
        )[0] is False
        assert gate.should_notify(
            make_event(severity="critical", category="storage")
        )[0] is True
        # other categories still assertive
        assert gate.should_notify(
            make_event(severity="info", category="config")
        )[0] is True

    def test_none_category_overrides_falls_back_to_global(self):
        gate = make_gate(proactivity="quiet")
        gate.config.category_overrides = None  # tolerate None from YAML
        assert gate.should_notify(make_event(severity="warning"))[0] is False
        assert gate.should_notify(make_event(severity="critical"))[0] is True


class TestSafeMode:
    def test_safe_mode_suppresses_non_critical(self):
        guardrails = SimpleNamespace(safe_mode_active=True)
        gate = make_gate(guardrails=guardrails)
        allowed, reason = gate.should_notify(make_event(severity="warning"))
        assert allowed is False
        assert "safe mode" in reason

    def test_safe_mode_allows_critical(self):
        guardrails = SimpleNamespace(safe_mode_active=True)
        gate = make_gate(guardrails=guardrails)
        assert gate.should_notify(make_event(severity="critical"))[0] is True

    def test_no_guardrail_enforcer_is_allowed(self):
        gate = make_gate()
        gate.guardrails = None
        assert gate.should_notify(make_event(severity="warning"))[0] is True


class TestFindingState:
    def test_active_snooze_suppresses(self, store, finding):
        store.snooze(finding, 7)
        gate = make_gate(findings=store)
        allowed, reason = gate.should_notify(
            make_event(severity="warning", finding_id=finding)
        )
        assert allowed is False
        assert "snoozed" in reason

    def test_expired_snooze_allows(self, store, finding):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        store.update_status(
            finding, FindingStatus.SNOOZED.value, snoozed_until=past
        )
        gate = make_gate(findings=store)
        assert gate.should_notify(
            make_event(severity="warning", finding_id=finding)
        )[0] is True

    def test_expired_snooze_tolerates_offset_plus_z_suffix(self, store, finding):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat() + "Z"
        store.update_status(
            finding, FindingStatus.SNOOZED.value, snoozed_until=past
        )
        gate = make_gate(findings=store)
        assert gate.should_notify(
            make_event(severity="warning", finding_id=finding)
        )[0] is True

    def test_dismissed_suppresses(self, store, finding):
        store.dismiss(finding, "intentional")
        gate = make_gate(findings=store)
        allowed, reason = gate.should_notify(
            make_event(severity="warning", finding_id=finding)
        )
        assert allowed is False
        assert "dismissed" in reason
