# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: split-brain resolution when Desktop wakes and deferred tasks conflict.

Implements finding L15 and §11.3 from the federated multi-node review.

L15 — Test strategy misses split-brain cases. When the Desktop wakes, a
deferred satellite task may have completed locally (via template thoughts
or local model) and conflicts with a Desktop-side completion.

Resolution policy (§11.3 4-tier classification, to be implemented in 9.6):
- cognitive_monologue: no conflict possible (never deferred, never offloaded)
- interactive_user: Desktop-authoritative (GPU response supersedes template)
- high_value_event: last-write-wins (local action may have already executed)
- sleep_consolidation: Desktop-authoritative (batch replay overwrites local)
"""
import pytest

from halbert_core.federation.compute_router import ComputeRouter, TurnType, FallbackResult


class TestSplitBrain:
    """Verify split-brain conflict resolution."""

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires ComputeRouter.replay_deferred() implementation")
    def test_cognitive_monologue_no_conflict(self):
        """Cognitive monologue turns are never deferred, so no split-brain possible."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires replay_deferred() implementation")
    def test_interactive_user_desktop_authoritative(self):
        """When an interactive_user turn was answered locally (template) and
        the Desktop wakes with a full GPU response, the Desktop response wins."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires replay_deferred() implementation")
    def test_high_value_event_last_write_wins(self):
        """When a high_value_event was executed locally and the Desktop also
        processes it, the local execution stands (the action already happened).
        The Desktop response is logged as informational."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires replay_deferred() implementation")
    def test_sleep_consolidation_desktop_authoritative(self):
        """Sleep consolidation batch replay overwrites any local interim result."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires replay_deferred() implementation")
    def test_deferred_queue_drains_on_peer_recovery(self):
        """When the peer comes back online, the deferred queue is drained
        and all pending interactive_user/high_value_event/sleep_consolidation
        turns are replayed."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires replay_deferred() implementation")
    def test_cognitive_monologue_not_replayed_on_wake(self):
        """Cognitive monologue turns that fell back to template thoughts are NOT
        replayed when the Desktop wakes (they would flood the Desktop
        with hundreds of queued requests)."""
        pass

    def test_turn_type_enum_values(self):
        """Verify TurnType enum has the 4-tier values from §11.3."""
        assert TurnType.COGNITIVE_MONOLOGUE == "cognitive_monologue"
        assert TurnType.INTERACTIVE_USER == "interactive_user"
        assert TurnType.HIGH_VALUE_EVENT == "high_value_event"
        assert TurnType.SLEEP_CONSOLIDATION == "sleep_consolidation"

    def test_fallback_result_source_values(self):
        """Verify FallbackResult has the expected source values."""
        result = FallbackResult(source="template", reason="peer offline, SBC_LOW_POWER")
        assert result.source == "template"
        assert result.deferred is False

        result = FallbackResult(source="deferred", deferred=True, reason="queued for replay")
        assert result.source == "deferred"
        assert result.deferred is True
