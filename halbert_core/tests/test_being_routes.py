# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""/api/being/events* only carry user-facing events (C2-16).

somatic_block and subagent_event are published straight to the bus by
the state machine and the subagent manager (they bypass the gate and are
already on the agent SSE stream); the bell must not render them as
generic rows whose snooze/dismiss 400.
"""
from __future__ import annotations

import asyncio

import pytest

from halbert_core.proactive.events import ProactiveEvent, ProactiveEventBus


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from halbert_core.dashboard.app import create_app

    return TestClient(create_app())


@pytest.fixture
def bus(monkeypatch):
    from halbert_core.dashboard.routes import being as being_mod

    b = ProactiveEventBus()
    monkeypatch.setattr(being_mod, "get_event_bus", lambda: b)
    return b


def _publish(bus, etype, title):
    ev = ProactiveEvent.create(type=etype, severity="info", title=title, body="b")
    asyncio.run(bus.publish(ev))
    return ev


class TestRecentEvents:
    def test_lifecycle_events_are_filtered_out(self, client, bus):
        _publish(bus, "somatic_block", "Block reflection: pending")
        finding = _publish(bus, "finding", "Loose key")
        _publish(bus, "subagent_event", "Subagent spawned: researcher")
        report = _publish(bus, "morning_report", "Morning report")

        body = client.get("/api/being/events/recent").json()
        assert [e["id"] for e in body["events"]] == [finding.id, report.id]

    def test_limit_counts_user_facing_rows(self, client, bus):
        for i in range(5):
            _publish(bus, "somatic_block", f"block {i}")
        ids = [_publish(bus, "finding", f"f{i}").id for i in range(3)]
        body = client.get("/api/being/events/recent", params={"limit": 2}).json()
        assert [e["id"] for e in body["events"]] == ids[-2:]


class TestStreamFilter:
    def test_should_stream_uses_the_user_facing_channel(self):
        from halbert_core.dashboard.routes.being import _should_stream

        assert _should_stream(ProactiveEvent.create(
            type="finding", severity="info", title="t", body="b")) is True
        assert _should_stream(ProactiveEvent.create(
            type="somatic_block", severity="info", title="t", body="b")) is False
        assert _should_stream(ProactiveEvent.create(
            type="subagent_event", severity="info", title="t", body="b")) is False
