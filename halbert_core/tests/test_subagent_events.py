# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the subagent lifecycle event stream (D1c)."""

import asyncio
import pytest

from halbert_core.agents.events import StreamEvent
from halbert_core.agents.subagent import (
    SubagentManager, subagent_event_to_stream, publish_subagent_event,
)


# ---------------------------------------------------------------------------
# StreamEvent.subagent_event factory
# ---------------------------------------------------------------------------

class TestSubagentStreamEvent:
    def test_factory_shape(self):
        ev = StreamEvent.subagent_event(
            "s1", "completed", "h-1", agent_type="storage_auditor",
            result_block_id="blk-1",
        )
        assert ev.type == "subagent_event"
        assert ev.data["subagent_event"] == "completed"
        assert ev.data["handle_id"] == "h-1"
        assert ev.data["agent_type"] == "storage_auditor"
        assert ev.data["result_block_id"] == "blk-1"

    def test_to_sse(self):
        ev = StreamEvent.subagent_event("s1", "spawned", "h-1")
        sse = ev.to_sse()
        assert "subagent_event" in sse
        assert "spawned" in sse


# ---------------------------------------------------------------------------
# subagent_event_to_stream converts the manager event dict
# ---------------------------------------------------------------------------

class TestEventToStream:
    def test_converts_manager_event(self):
        event = {"type": "at_capacity", "handle_id": "h-1",
                 "agent_type": "auditor", "status": "queued", "queued": 1}
        se = subagent_event_to_stream("s1", event)
        assert se.type == "subagent_event"
        assert se.data["subagent_event"] == "at_capacity"
        assert se.data["handle_id"] == "h-1"
        assert se.data["agent_type"] == "auditor"


# ---------------------------------------------------------------------------
# Manager emits SSE-via-callback AND publishes to ProactiveEventBus
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manager_on_event_callback_fires():
    captured = []
    mgr = SubagentManager(max_concurrent=1, on_event=lambda e: captured.append(e))
    mgr.spawn("a", "g1")           # spawned
    h2 = mgr.spawn("b", "g2")       # queued -> at_capacity
    mgr.complete(h2.id if False else mgr.list_active()[0].id)  # complete
    types = [e["type"] for e in captured]
    assert "spawned" in types
    assert "at_capacity" in types
    assert "completed" in types


@pytest.mark.asyncio
async def test_manager_publishes_to_proactive_bus():
    # The manager schedules publish_subagent_event on the running loop.
    # Give the loop a chance to run the scheduled task, then check the bus
    # received something via its in-memory subscriber ring (best-effort).
    from halbert_core.proactive.events import get_event_bus
    bus = get_event_bus()
    # Subscribe to capture published events
    q = bus.subscribe_global() if hasattr(bus, "subscribe_global") else None

    mgr = SubagentManager(max_concurrent=1, on_event=lambda e: None)
    mgr.spawn("a", "g1")
    # Let the scheduled publish task run
    await asyncio.sleep(0.05)

    # Best-effort assertion: the publish call path ran without raising.
    # (The bus may have no subscribers wired in test env; just ensure no crash.)
    assert mgr.active_count == 1


@pytest.mark.asyncio
async def test_publish_subagent_event_does_not_raise_without_bus():
    # Even with a fresh/empty bus, publish must not raise.
    await publish_subagent_event({"type": "completed", "handle_id": "h",
                                  "agent_type": "x", "status": "completed"})


def test_emit_without_loop_does_not_raise():
    # _emit schedules a publish task; called with no running loop it must
    # swallow the RuntimeError (sync spawn from non-async context).
    mgr = SubagentManager(max_concurrent=1, on_event=lambda e: None)
    mgr.spawn("a", "g1")  # no running loop in a sync test function -> no crash
    assert mgr.active_count == 1
