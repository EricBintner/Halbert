# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: compute broker concurrency and priority preemption.

Implements finding H6 / L15 from the federated multi-node review.

H6 — 1:N is over-scoped for a first phase. The broker is scaffolded for
the full 1:N design but defaults to max_concurrent=1 for Phase 9.2a.
Phase 9.8 (2b) increases max_concurrent and enables preemption.

This test verifies:
1. The broker initializes with the correct concurrency limit.
2. Priority ordering is correct (P1 > P2 > P3).
3. get_stats() returns the expected monitoring data.
4. Preemption is disabled by default (Phase 9.2a).
"""
import pytest

from halbert_core.federation.compute_broker import (
    ComputeBroker, ComputePriority, ComputeRequest,
)


class TestComputeBroker:
    """Verify compute broker configuration and priority ordering."""

    def test_default_max_concurrent_is_1(self):
        """Phase 9.2a: broker defaults to max_concurrent=1 (pass-through)."""
        broker = ComputeBroker()
        assert broker.max_concurrent == 1

    def test_preemption_disabled_by_default(self):
        """Phase 9.2a: preemption is disabled."""
        broker = ComputeBroker()
        assert broker.enable_preemption is False

    def test_phase_2b_config(self):
        """Phase 9.8: broker can be configured for N concurrency + preemption."""
        broker = ComputeBroker(max_concurrent=4, enable_preemption=True)
        assert broker.max_concurrent == 4
        assert broker.enable_preemption is True

    def test_priority_ordering(self):
        """ComputeRequest objects sort by priority (lower = higher priority)."""
        req1 = ComputeRequest(priority=ComputePriority.LOCAL_INTERACTIVE)
        req2 = ComputeRequest(priority=ComputePriority.REMOTE_INTERACTIVE)
        req3 = ComputeRequest(priority=ComputePriority.BACKGROUND_BATCH)
        # Sort order: req1 < req2 < req3 (P1 first)
        sorted_reqs = sorted([req3, req1, req2])
        assert sorted_reqs[0] is req1
        assert sorted_reqs[1] is req2
        assert sorted_reqs[2] is req3

    def test_fifo_within_same_priority(self):
        """Requests with the same priority are FIFO (ordered by timestamp)."""
        req_a = ComputeRequest(priority=ComputePriority.BACKGROUND_BATCH, timestamp=100.0)
        req_b = ComputeRequest(priority=ComputePriority.BACKGROUND_BATCH, timestamp=200.0)
        assert req_a < req_b  # earlier timestamp sorts first

    def test_priority_values(self):
        """Verify priority enum values match the handoff spec."""
        assert ComputePriority.LOCAL_INTERACTIVE == 1
        assert ComputePriority.REMOTE_INTERACTIVE == 2
        assert ComputePriority.BACKGROUND_BATCH == 3

    def test_get_stats_returns_config(self):
        """get_stats() returns the broker's configuration."""
        broker = ComputeBroker(max_concurrent=2, enable_preemption=True)
        stats = broker.get_stats()
        assert stats["max_concurrent"] == 2
        assert stats["preemption_enabled"] is True
        assert "queue_depth" in stats
        assert "running" in stats

    @pytest.mark.skip(reason="TODO(federation-9.8) — requires async broker loop implementation")
    def test_concurrent_requests_respect_semaphore(self):
        """With max_concurrent=1, only one request runs at a time."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.8) — requires preemption implementation")
    def test_p1_preempts_p3(self):
        """A Priority 1 request preempts a running Priority 3 request."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.8) — requires preemption implementation")
    def test_p1_does_not_preempt_p2(self):
        """A Priority 1 request does NOT preempt a running Priority 2 request."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.8) — requires async implementation")
    def test_10_satellite_concurrent_load(self):
        """10-satellite concurrent load test with priority preemption.

        This is the full Phase 9.8 load test from the handoff §6.
        """
        pass
