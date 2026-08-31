# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P4c: Template degraded marker tests.

Verifies that FallbackResult.degraded is set correctly and that
degraded_marker() / apply_degraded_marker() produce the right indicators.
"""

import pytest

from halbert_core.federation.compute_router import (
    FallbackResult,
    TurnType,
    ComputeRouter,
    is_degraded_response,
    apply_degraded_marker,
    DEGRADED_MARKER_PREFIX,
)


class TestDegradedFlag:
    def test_peer_result_not_degraded(self):
        result = FallbackResult(source="peer", model_id="m")
        assert result.degraded is False
        assert result.degraded_marker() is None

    def test_local_model_not_degraded(self):
        result = FallbackResult(source="local_model", model_id="m")
        assert result.degraded is False
        assert result.degraded_marker() is None

    def test_template_is_degraded(self):
        result = FallbackResult(source="template", degraded=True)
        assert result.degraded is True
        marker = result.degraded_marker()
        assert marker is not None
        assert "no thinking power" in marker
        assert "template" in marker

    def test_heuristic_is_degraded(self):
        result = FallbackResult(source="heuristic", degraded=True)
        marker = result.degraded_marker()
        assert marker is not None
        assert "heuristic" in marker

    def test_deferred_is_degraded(self):
        result = FallbackResult(source="deferred", degraded=True)
        marker = result.degraded_marker()
        assert marker is not None
        assert "deferred" in marker


class TestApplyDegradedMarker:
    def test_prepends_marker_for_degraded(self):
        result = FallbackResult(source="template", degraded=True)
        text = "I think the service is running."
        marked = apply_degraded_marker(text, result)
        assert marked.startswith("[no thinking power")
        assert text in marked

    def test_noop_for_non_degraded(self):
        result = FallbackResult(source="peer", degraded=False)
        text = "Real AI response."
        marked = apply_degraded_marker(text, result)
        assert marked == text

    def test_no_double_apply(self):
        result = FallbackResult(source="template", degraded=True)
        text = "[no thinking power — template response] Already marked."
        marked = apply_degraded_marker(text, result)
        assert marked == text  # unchanged

    def test_empty_text_with_degraded(self):
        result = FallbackResult(source="template", degraded=True)
        marked = apply_degraded_marker("", result)
        assert "[no thinking power" in marked


class TestIsDegradedResponse:
    def test_detects_marker(self):
        assert is_degraded_response("[no thinking power — template] hello") is True

    def test_no_marker(self):
        assert is_degraded_response("Real AI response.") is False

    def test_empty_string(self):
        assert is_degraded_response("") is False


class TestRouterSetsDegraded:
    """Verify the router's _template_fallback sets degraded=True."""

    def test_template_fallback_sets_degraded(self):
        router = ComputeRouter(
            peer_endpoint=None, hardware_profile="sbc_low_power",
        )
        result = router._template_fallback(
            [{"role": "user", "content": "hi"}], "m",
            TurnType.INTERACTIVE_USER, None,
        )
        assert result.degraded is True
        assert result.degraded_marker() is not None

    def test_cognitive_monologue_template_degraded(self):
        router = ComputeRouter(
            peer_endpoint=None, hardware_profile="sbc_low_power",
        )
        result = router._template_fallback(
            [{"role": "user", "content": "tick"}], "m",
            TurnType.COGNITIVE_MONOLOGUE, None,
        )
        assert result.degraded is True
        assert result.source == "template"

    def test_heuristic_fallback_degraded(self):
        router = ComputeRouter(
            peer_endpoint=None, hardware_profile="sbc_low_power",
        )
        result = router._template_fallback(
            [{"role": "user", "content": "alert"}], "m",
            TurnType.HIGH_VALUE_EVENT, None,
        )
        assert result.degraded is True
        assert result.source == "heuristic"
