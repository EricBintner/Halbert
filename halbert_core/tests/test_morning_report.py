# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Tests for the morning report generator (Phase 7 / T7d.1).

Covers:
- Template body includes findings, proposals, and config changes
- Summarizer output replaces the template body; fallback on error/empty
- ProactiveGate suppression (proactivity "off") → nothing published
- ConfigWatcher rolling recent-changes log feeding the report
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from halbert_core.config.being_config import BeingConfig, resolve_timezone
from halbert_core.config.watcher import ConfigWatcher
from halbert_core.findings.proposals import Proposal, ProposalStore
from halbert_core.findings.store import Finding, FindingStore
from halbert_core.proactive.morning_report import MorningReportGenerator
from halbert_core.proactive import morning_report as mr_module


class CapturingBus:
    """Fake event bus that records published events."""

    def __init__(self):
        self.events = []

    async def publish(self, event):
        self.events.append(event)


class AllowGate:
    """Fake gate that always allows publication."""

    def should_notify(self, event):
        return True, ""


class DenyGate:
    """Fake gate that suppresses everything (proactivity "off")."""

    def should_notify(self, event):
        return False, "proactivity dial is 'off' (requires severity >= 99)"


@pytest.fixture
def stores(tmp_path):
    """Real SQLite-backed stores in a temp directory."""
    finding_store = FindingStore(db_path=str(tmp_path / "findings.db"))
    proposal_store = ProposalStore(db_path=str(tmp_path / "proposals.db"))
    return finding_store, proposal_store


@pytest.fixture
def capture_bus(monkeypatch):
    """Monkeypatch the module-level get_event_bus with a capturing fake."""
    bus = CapturingBus()
    monkeypatch.setattr(mr_module, "get_event_bus", lambda: bus)
    return bus


def _make_finding(severity="warning", title="Disk nearly full"):
    return Finding(
        id="",
        detector="test_detector",
        severity=severity,
        title=title,
        description="description for " + title,
        why_now="test trigger",
        why_care="data loss risk",
        why_so="df shows 95%",
    )


def _make_proposal(action="Update fstab entry"):
    return Proposal(id="", finding_id="f-1", action=action)


def _make_generator(finding_store, proposal_store, **overrides):
    kwargs = {
        "finding_store": finding_store,
        "proposal_store": proposal_store,
        "being_config": BeingConfig(voice="first_person", proactivity="assertive"),
        "gate": AllowGate(),
    }
    kwargs.update(overrides)
    return MorningReportGenerator(**kwargs)


class TestMorningReportBody:
    def test_body_includes_findings_proposals_and_changes(
        self, stores, capture_bus
    ):
        finding_store, proposal_store = stores
        finding_store.add(_make_finding())
        proposal_store.add(_make_proposal())
        changes = [
            {"ts": datetime.now(timezone.utc).isoformat(),
             "path": "/etc/fstab",
             "kind": "text"},
        ]
        generator = _make_generator(
            finding_store,
            proposal_store,
            config_changes_provider=lambda hours: changes,
        )

        event = asyncio.run(generator.generate())

        assert len(capture_bus.events) == 1
        assert capture_bus.events[0].id == event.id
        assert "Disk nearly full" in event.body
        assert "Update fstab entry" in event.body
        assert "/etc/fstab" in event.body
        assert "## Open Findings" in event.body
        assert "## Pending Proposals" in event.body
        assert "## Config Changes" in event.body

    def test_body_without_config_changes_when_no_provider(
        self, stores, capture_bus
    ):
        finding_store, proposal_store = stores
        generator = _make_generator(finding_store, proposal_store)

        event = asyncio.run(generator.generate())

        assert "Config Changes" not in event.body
        assert "No open findings" in event.body

    def test_config_changes_provider_failure_falls_back(
        self, stores, capture_bus
    ):
        finding_store, proposal_store = stores

        def bad_provider(hours):
            raise RuntimeError("watcher exploded")

        generator = _make_generator(
            finding_store,
            proposal_store,
            config_changes_provider=bad_provider,
        )
        event = asyncio.run(generator.generate())

        assert "Config Changes" not in event.body
        assert len(capture_bus.events) == 1


class TestGate:
    def test_gate_off_publishes_nothing(self, stores, capture_bus):
        finding_store, proposal_store = stores
        finding_store.add(_make_finding())
        generator = _make_generator(
            finding_store, proposal_store, gate=DenyGate()
        )

        event = asyncio.run(generator.generate())

        assert capture_bus.events == []
        assert event.title.startswith("Morning Report")

    def test_gate_error_suppresses_publish(self, stores, capture_bus):
        class ExplodingGate:
            def should_notify(self, event):
                raise RuntimeError("half-wired gate")

        finding_store, proposal_store = stores
        generator = _make_generator(
            finding_store, proposal_store, gate=ExplodingGate()
        )

        asyncio.run(generator.generate())

        assert capture_bus.events == []


class TestSummarizer:
    def test_summarizer_text_used_when_provided(self, stores, capture_bus):
        finding_store, proposal_store = stores
        generator = _make_generator(
            finding_store,
            proposal_store,
            summarizer=lambda text: "CUSTOM SUMMARY",
        )

        event = asyncio.run(generator.generate())

        assert event.body == "CUSTOM SUMMARY"

    def test_template_fallback_on_summarizer_exception(
        self, stores, capture_bus
    ):
        def bad_summarizer(text):
            raise RuntimeError("LLM unavailable")

        finding_store, proposal_store = stores
        generator = _make_generator(
            finding_store, proposal_store, summarizer=bad_summarizer
        )

        event = asyncio.run(generator.generate())

        assert "morning review" in event.body

    def test_template_fallback_on_empty_summary(self, stores, capture_bus):
        finding_store, proposal_store = stores
        generator = _make_generator(
            finding_store, proposal_store, summarizer=lambda text: "  "
        )

        event = asyncio.run(generator.generate())

        assert "morning review" in event.body

    def test_template_body_intact_without_summarizer(self, stores, capture_bus):
        finding_store, proposal_store = stores
        generator = _make_generator(finding_store, proposal_store)

        event = asyncio.run(generator.generate())

        # Voice-aware intro for first_person voice
        assert event.body.startswith("I've completed my morning review.")


class TestConfigWatcherRecentChanges:
    def _watcher(self, **kwargs):
        kwargs.setdefault("manifest_path", "/nonexistent/config-registry.yml")
        kwargs.setdefault("on_snapshot", lambda rows: None)
        return ConfigWatcher(**kwargs)

    def _snapshot(self, path="/etc/a.conf", hash_="h1", kind="ini"):
        ts = datetime.now(timezone.utc).isoformat()
        return [{"ts": ts, "path": path, "hash": hash_, "kind": kind}]

    def test_change_recorded_when_hash_changes(self):
        watcher = self._watcher()
        watcher._handle_change(self._snapshot(hash_="h1"))  # baseline
        watcher._handle_change(self._snapshot(hash_="h1"))  # no change
        watcher._handle_change(self._snapshot(hash_="h2"))  # change

        changes = watcher.get_recent_changes(within_hours=24)

        assert len(changes) == 1
        assert changes[0]["path"] == "/etc/a.conf"
        assert changes[0]["kind"] == "ini"
        assert changes[0]["ts"]

    def test_baseline_snapshot_records_nothing(self):
        watcher = self._watcher()
        watcher._handle_change(self._snapshot())

        assert watcher.get_recent_changes(within_hours=24) == []

    def test_deleted_file_recorded(self):
        watcher = self._watcher()
        watcher._handle_change(self._snapshot())
        watcher._handle_change([])  # file gone

        changes = watcher.get_recent_changes(within_hours=24)

        assert len(changes) == 1
        assert changes[0]["kind"] == "deleted"
        assert changes[0]["path"] == "/etc/a.conf"

    def test_old_entries_filtered_by_window(self):
        watcher = self._watcher()
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        watcher._changes.append(
            {"ts": old_ts, "path": "/etc/old.conf", "kind": "ini"}
        )

        assert watcher.get_recent_changes(within_hours=24) == []
        assert len(watcher.get_recent_changes(within_hours=72)) == 1

    def test_composed_callbacks_all_invoked(self):
        calls = []
        cb_a = lambda rows: calls.append("a")
        cb_b = lambda rows: calls.append("b")
        exploding = lambda rows: (_ for _ in ()).throw(RuntimeError("boom"))

        watcher = self._watcher(
            on_change=cb_a,
            change_callbacks=[exploding, cb_b],
        )
        watcher._handle_change(self._snapshot())

        assert calls == ["a", "b"]


# ── Timezone resolution ──────────────────────────────────────────

class TestTimezoneResolution:
    def test_explicit_iana_name(self):
        assert resolve_timezone("America/Chicago") == "America/Chicago"

    def test_utc(self):
        assert resolve_timezone("UTC") == "UTC"

    def test_local_returns_valid_tz(self):
        """'local' should resolve to a valid IANA timezone (not empty)."""
        tz = resolve_timezone("local")
        assert isinstance(tz, str)
        assert len(tz) > 0

    def test_being_config_has_timezone_field(self):
        cfg = BeingConfig()
        assert hasattr(cfg, "timezone")
        assert cfg.timezone == "local"

    def test_being_config_from_dict_with_timezone(self):
        cfg = BeingConfig.from_dict({"timezone": "Europe/Berlin"})
        assert cfg.timezone == "Europe/Berlin"

    def test_being_config_from_dict_without_timezone(self):
        cfg = BeingConfig.from_dict({})
        assert cfg.timezone == "local"
