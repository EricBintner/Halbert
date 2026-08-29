# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: split-brain resolution when Desktop wakes and deferred tasks conflict.

Implements finding L15 from the federated multi-node review.

L15 — Test strategy misses split-brain cases. When the Desktop wakes, a
deferred satellite task may have completed locally (via template thoughts
or local model) and conflicts with a Desktop-side completion.

Resolution policy (to be implemented in federation-9.6):
- For monologue turns: no conflict possible (monologue is never deferred)
- For user turns: Desktop-authoritative (the Desktop's GPU response
  supersedes the satellite's local/template response)
- For automation turns: last-write-wins (the satellite's local action
  may have already been executed; the Desktop's response is informational)
"""
import pytest

from halbert_core.federation.compute_router import ComputeRouter, TurnType, FallbackResult


class TestSplitBrain:
    """Verify split-brain conflict resolution."""

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires ComputeRouter.replay_deferred() implementation")
    def test_monologue_no_conflict(self):
        """Monologue turns are never deferred, so no split-brain possible."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires replay_deferred() implementation")
    def test_user_turn_desktop_authoritative(self):
        """When a user turn was answered locally (template) and the Desktop
        wakes with a full GPU response, the Desktop response wins."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires replay_deferred() implementation")
    def test_automation_turn_last_write_wins(self):
        """When an automation turn was executed locally and the Desktop
        also processes it, the local execution stands (the action already
        happened). The Desktop response is logged as informational."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires replay_deferred() implementation")
    def test_deferred_queue_drains_on_peer_recovery(self):
        """When the peer comes back online, the deferred queue is drained
        and all pending user/automation turns are replayed."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires replay_deferred() implementation")
    def test_monologue_turns_not_replayed_on_wake(self):
        """Monologue turns that fell back to template thoughts are NOT
        replayed when the Desktop wakes (they would flood the Desktop
        with hundreds of queued requests)."""
        pass

    def test_turn_type_enum_values(self):
        """Verify TurnType enum has the expected values."""
        assert TurnType.MONOLOGUE == "monologue"
        assert TurnType.USER == "user"
        assert TurnType.AUTOMATION == "automation"

    def test_fallback_result_source_values(self):
        """Verify FallbackResult has the expected source values."""
        result = FallbackResult(source="template", reason="peer offline, SBC_LOW_POWER")
        assert result.source == "template"
        assert result.deferred is False

        result = FallbackResult(source="deferred", deferred=True, reason="queued for replay")
        assert result.source == "deferred"
        assert result.deferred is True
