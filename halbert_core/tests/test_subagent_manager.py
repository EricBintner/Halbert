# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for SubagentManager (D1a)."""

import pytest

from halbert_core.agents.subagent import SubagentManager, SubagentHandle, freeze_config


@pytest.fixture
def events():
    """Returns (manager_factory, captured_events_list)."""
    captured = []

    def on_event(ev):
        captured.append(ev)

    def make(max_concurrent=2):
        return SubagentManager(max_concurrent=max_concurrent, on_event=on_event), captured

    return make


# ---------------------------------------------------------------------------
# freeze_config
# ---------------------------------------------------------------------------

class TestFreezeConfig:
    def test_deep_copy(self):
        cfg = {"model": "x", "nested": {"a": 1}}
        snap = freeze_config(cfg)
        snap["nested"]["a"] = 99
        assert cfg["nested"]["a"] == 1  # original untouched

    def test_none_empty(self):
        assert freeze_config(None) == {}
        assert freeze_config({}) == {}


# ---------------------------------------------------------------------------
# Spawn / capacity / queue
# ---------------------------------------------------------------------------

class TestSpawnAndCapacity:
    def test_spawn_admits_when_slot_free(self, events):
        mgr, evs = events()
        h = mgr.spawn("storage_auditor", "check disks")
        assert h.status == "running"
        assert mgr.active_count == 1
        assert any(e["type"] == "spawned" for e in evs)

    def test_spawn_queues_at_capacity(self, events):
        mgr, evs = events(max_concurrent=2)
        mgr.spawn("a", "g1")
        mgr.spawn("b", "g2")
        h3 = mgr.spawn("c", "g3")  # over capacity -> queued
        assert h3.status == "queued"
        assert mgr.queued_count == 1
        assert mgr.active_count == 2
        assert any(e["type"] == "at_capacity" for e in evs)

    def test_freeze_config_on_handle(self, events):
        mgr, _ = events()
        h = mgr.spawn("a", "g", agent_config={"model": "example-model:latest", "temp": 0.7})
        assert h.agent_config_snapshot == {"model": "example-model:latest", "temp": 0.7}

    def test_handle_has_id_and_metadata(self, events):
        mgr, _ = events()
        h = mgr.spawn("a", "g", scoped_sources=["/etc"], model_tier="specialist",
                       parent_task_id="parent-1")
        assert h.id
        assert h.scoped_sources == ["/etc"]
        assert h.model_tier == "specialist"
        assert h.parent_task_id == "parent-1"


# ---------------------------------------------------------------------------
# Complete / promote
# ---------------------------------------------------------------------------

class TestCompleteAndPromotion:
    def test_complete_frees_slot_and_promotes(self, events):
        mgr, evs = events(max_concurrent=1)
        h1 = mgr.spawn("a", "g1")  # running
        h2 = mgr.spawn("b", "g2")  # queued (capacity 1)
        assert h2.status == "queued"

        assert mgr.complete(h1.id, result_block_id="blk-1") is True
        assert h1.status == "completed"
        assert h1.result_block_id == "blk-1"
        # h2 promoted to running
        assert mgr.get(h2.id).status == "running"
        assert mgr.active_count == 1
        assert any(e["type"] == "completed" for e in evs)

    def test_complete_failed(self, events):
        mgr, evs = events()
        h = mgr.spawn("a", "g")
        mgr.complete(h.id, error="boom")
        assert h.status == "failed"
        assert h.error == "boom"
        assert any(e["type"] == "failed" for e in evs)

    def test_complete_unknown_returns_false(self, events):
        mgr, _ = events()
        assert mgr.complete("nope") is False

    def test_complete_with_error_promotes_next(self, events):
        mgr, _ = events(max_concurrent=1)
        h1 = mgr.spawn("a", "g1")
        h2 = mgr.spawn("b", "g2")
        mgr.complete(h1.id, error="x")
        assert mgr.get(h2.id).status == "running"


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

class TestCancel:
    def test_cancel_running_promotes_next(self, events):
        mgr, _ = events(max_concurrent=1)
        h1 = mgr.spawn("a", "g1")
        h2 = mgr.spawn("b", "g2")
        assert mgr.cancel(h1.id) is True
        assert h1.status == "cancelled"
        assert mgr.get(h2.id).status == "running"

    def test_cancel_queued(self, events):
        mgr, _ = events(max_concurrent=1)
        mgr.spawn("a", "g1")
        h2 = mgr.spawn("b", "g2")
        assert mgr.cancel(h2.id) is True
        assert h2.status == "cancelled"
        assert mgr.queued_count == 0

    def test_cancel_unknown_returns_false(self, events):
        mgr, _ = events()
        assert mgr.cancel("nope") is False


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

class TestReads:
    def test_list_active_and_queued(self, events):
        mgr, _ = events(max_concurrent=1)
        h1 = mgr.spawn("a", "g1")
        h2 = mgr.spawn("b", "g2")
        active = mgr.list_active()
        queued = mgr.list_queued()
        assert len(active) == 1 and active[0].id == h1.id
        assert len(queued) == 1 and queued[0].id == h2.id

    def test_get_active_and_queued(self, events):
        mgr, _ = events(max_concurrent=1)
        h1 = mgr.spawn("a", "g1")
        h2 = mgr.spawn("b", "g2")
        assert mgr.get(h1.id).id == h1.id
        assert mgr.get(h2.id).id == h2.id
        assert mgr.get("nope") is None

    def test_to_dict(self, events):
        mgr, _ = events()
        h = mgr.spawn("a", "g")
        d = h.to_dict()
        assert d["agent_type"] == "a"
        assert d["status"] == "running"
        assert "id" in d
