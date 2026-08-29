# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for visual intent detection, intake routing, and PLANNING auto-capture."""
import pytest

from halbert_core.intake.signals import analyze_message, _VISUAL_INTENT_RE


class TestVisualIntentRegex:
    """Unit tests for the _VISUAL_INTENT_RE pattern."""

    @pytest.mark.parametrize("msg", [
        "what is on my screen",
        "what's on my screen",
        "whats on my screen",
        "look at this error dialog",
        "look at my screen",
        "look at the display",
        "look at this popup",
        "what do you see",
        "see this error message",
        "see the dialog",
        "the error dialog says connection refused",
        "the popup says disk full",
        "what does my screen show",
        "what does the screen say",
        "what's on my display",
        "what is on the display",
    ])
    def test_matches(self, msg):
        assert _VISUAL_INTENT_RE.search(msg), f"Should match: {msg!r}"

    @pytest.mark.parametrize("msg", [
        "screening process",
        "screenshot tool config",
        "the screen protector is on",
        "help me fix my wifi",
        "check the logs",
        "what time is it",
        "how do I configure the firewall",
        "the screen is too bright",  # not asking to look AT it
    ])
    def test_no_match(self, msg):
        assert not _VISUAL_INTENT_RE.search(msg), f"Should NOT match: {msg!r}"


class TestVisualIntentSignal:
    """Tests that analyze_message populates has_vision_request."""

    def test_visual_intent_sets_flag(self):
        s = analyze_message("what's on my screen?")
        assert s.has_vision_request is True

    def test_no_visual_intent_no_flag(self):
        s = analyze_message("help me configure the firewall")
        assert s.has_vision_request is False

    def test_image_attachment_does_not_set_vision_request(self):
        """has_images and has_vision_request are independent signals."""
        s = analyze_message("![screenshot](screenshot.png)")
        assert s.has_images is True
        assert s.has_vision_request is False

    def test_visual_intent_with_image(self):
        """Both can be true at once."""
        s = analyze_message("what's on my screen ![img](data:image/png;base64,abc)")
        assert s.has_images is True
        assert s.has_vision_request is True


class TestIntakeVisionRequestRouting:
    """Tests that the intake pipeline routes vision_request to the vision model."""

    def _make_pipeline(self, vision_enabled=True):
        """Build a minimal IntakePipeline with mocked complexity router."""
        from halbert_core.intake.pipeline import IntakePipeline
        from halbert_core.intake.complexity import ComplexityResult, ComplexityLevel

        class MockRouter:
            def assess(self, message, signals):
                return ComplexityResult(
                    score=1,
                    level=ComplexityLevel.SIMPLE,
                    cached=False,
                    latency_ms=0.0,
                )

        model_config = {
            "llm_config": {
                "chat_model": {"model": "guide-model"},
                "specialist_model": {"enabled": False, "model": ""},
                "vision_model": {
                    "enabled": vision_enabled,
                    "model": "vision-model" if vision_enabled else "",
                },
            },
            "routing": {"complexity_threshold": 3},
        }

        from halbert_core.intake.budget import ContextBudget, ModelTier
        def budget_fn(model_name):
            return ContextBudget(
                tier=ModelTier.MEDIUM, total=2000,
                system_identity=200, user_rules=200, retrieval=400,
                memory=200, discovery=200, conversation=400, observations=400,
            )

        return IntakePipeline(
            complexity_router=MockRouter(),
            budget_fn=budget_fn,
            model_config=model_config,
        )

    def test_vision_request_routes_to_vision(self):
        pipeline = self._make_pipeline(vision_enabled=True)
        intake = pipeline.analyze("what's on my screen?")
        assert intake.has_vision_request is True
        assert intake.recommended_model == "vision"

    def test_no_vision_request_routes_to_guide(self):
        pipeline = self._make_pipeline(vision_enabled=True)
        intake = pipeline.analyze("help me configure the firewall")
        assert intake.has_vision_request is False
        assert intake.recommended_model == "guide"

    def test_vision_request_no_vision_model_routes_to_guide(self):
        """If no vision model is configured, falls back to guide."""
        pipeline = self._make_pipeline(vision_enabled=False)
        intake = pipeline.analyze("what's on my screen?")
        assert intake.has_vision_request is True
        assert intake.recommended_model == "guide"
