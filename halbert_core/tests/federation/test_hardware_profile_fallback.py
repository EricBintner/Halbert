# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: hardware-profile-aware fallback uses template thoughts on SBC_LOW_POWER.

Implements finding H7 / L15 from the federated multi-node review.

H7 — On SBC_LOW_POWER (≤4GB RAM), a local 3B model will OOM. The fallback
chain must NOT attempt to load a micro-model on these devices. Instead,
it falls back to template thoughts (HALBERT_LLM_THOUGHTS=0).

This test verifies that ComputeRouter._hardware_supports_local_model()
returns False for SBC_LOW_POWER and True for higher profiles.
"""
import pytest

from halbert_core.federation.compute_router import ComputeRouter, TurnType


class TestHardwareProfileFallback:
    """Verify hardware-profile-aware fallback logic."""

    def _make_router(self, profile: str) -> ComputeRouter:
        """Create a ComputeRouter with a given hardware profile."""
        return ComputeRouter(
            peer_endpoint="http://desktop.lan:8000",
            peer_token="test-token",
            hardware_profile=profile,
        )

    def test_sbc_low_power_cannot_run_local_model(self):
        """SBC_LOW_POWER (≤4GB) cannot run a local model (OOM risk)."""
        router = self._make_router("sbc_low_power")
        assert router._hardware_supports_local_model() is False

    def test_entry_8gb_can_run_local_model(self):
        """ENTRY_8GB (4-8GB) can run a 3B Q4 model."""
        router = self._make_router("entry_8gb")
        assert router._hardware_supports_local_model() is True

    def test_laptop_16gb_can_run_local_model(self):
        """LAPTOP_16GB can run a 7B-8B model."""
        router = self._make_router("laptop_16gb")
        assert router._hardware_supports_local_model() is True

    def test_workstation_32gb_can_run_local_model(self):
        """WORKSTATION_32GB can run a local model."""
        router = self._make_router("workstation_32gb")
        assert router._hardware_supports_local_model() is True

    def test_unknown_profile_cannot_run_local_model(self):
        """UNKNOWN profile is conservative — cannot run local model."""
        router = self._make_router("unknown")
        assert router._hardware_supports_local_model() is False

    def test_monologue_turn_is_never_deferred(self):
        """Cognitive monologue turns (advance_turn) are never deferred (H8, §11.3)."""
        router = self._make_router("sbc_low_power")
        assert router._should_defer(TurnType.COGNITIVE_MONOLOGUE) is False

    def test_monologue_turn_is_never_offloaded(self):
        """Cognitive monologue turns are never offloaded to the peer (§11.3)."""
        router = self._make_router("sbc_low_power")
        assert router._should_offload(TurnType.COGNITIVE_MONOLOGUE) is False

    def test_interactive_user_is_deferred(self):
        """Interactive user turns are deferred to the replay queue."""
        router = self._make_router("sbc_low_power")
        assert router._should_defer(TurnType.INTERACTIVE_USER) is True

    def test_interactive_user_is_offloaded(self):
        """Interactive user turns are eligible for peer offload."""
        router = self._make_router("sbc_low_power")
        assert router._should_offload(TurnType.INTERACTIVE_USER) is True

    def test_high_value_event_is_deferred(self):
        """High-value event turns (Frigate/security) are deferred."""
        router = self._make_router("sbc_low_power")
        assert router._should_defer(TurnType.HIGH_VALUE_EVENT) is True

    def test_high_value_event_is_offloaded(self):
        """High-value event turns are eligible for peer offload."""
        router = self._make_router("sbc_low_power")
        assert router._should_offload(TurnType.HIGH_VALUE_EVENT) is True

    def test_sleep_consolidation_is_deferred(self):
        """Sleep consolidation turns are deferred (batch replay when Desktop idle)."""
        router = self._make_router("sbc_low_power")
        assert router._should_defer(TurnType.SLEEP_CONSOLIDATION) is True

    def test_sleep_consolidation_is_offloaded(self):
        """Sleep consolidation turns are eligible for peer offload."""
        router = self._make_router("sbc_low_power")
        assert router._should_offload(TurnType.SLEEP_CONSOLIDATION) is True

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires ComputeRouter.route() implementation")
    def test_sbc_low_power_falls_back_to_template_not_micro_model(self):
        """On SBC_LOW_POWER with peer offline, fallback is template thoughts.

        This test verifies the full fallback chain:
        1. Peer is offline (health probe fails)
        2. Hardware profile is SBC_LOW_POWER → cannot run local model
        3. Fallback is template thoughts (not a micro-model that would OOM)
        4. For cognitive_monologue: template, no deferral
        5. For interactive_user: template as interim, deferred to queue
        """
        pass

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires ComputeRouter.route() implementation")
    def test_entry_8gb_falls_back_to_local_model(self):
        """On ENTRY_8GB with peer offline, fallback is a 3B local model.

        This test verifies:
        1. Peer is offline
        2. Hardware profile is ENTRY_8GB → can run local model
        3. Fallback is the local 3B model (not template thoughts)
        """
        pass

    def test_failure_threshold_is_3(self):
        """§11.6: The peer health failure threshold is 3 consecutive failures."""
        router = self._make_router("sbc_low_power")
        assert router._failure_threshold == 3

    def test_consecutive_failures_starts_at_zero(self):
        """The consecutive failure counter starts at 0."""
        router = self._make_router("sbc_low_power")
        assert router._consecutive_failures == 0

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires _probe_peer_health() implementation")
    def test_single_failure_does_not_transition_to_offline(self):
        """§11.6: A single probe failure does NOT mark the peer offline.

        The peer stays online until 3 consecutive failures.
        """
        pass

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires _probe_peer_health() implementation")
    def test_three_consecutive_failures_transition_to_offline(self):
        """§11.6: 3 consecutive failures transition the peer to OFFLINE."""
        pass

    @pytest.mark.skip(reason="TODO(federation-9.6) — requires _probe_peer_health() implementation")
    def test_success_resets_failure_counter(self):
        """§11.6: A single successful probe resets the failure counter to 0."""
        pass
