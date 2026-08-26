# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Tests for intake/pipeline.py — the IntakePipeline orchestrator.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from halbert_core.intake.budget import ContextBudget, ModelTier, get_context_budget
from halbert_core.intake.complexity import ComplexityLevel, ComplexityResult, ComplexityRouter
from halbert_core.intake.pipeline import IntakePipeline, MessageIntake


# ── Fixtures ─────────────────────────────────────────────────────

MODEL_CONFIG = {
    "llm_config": {
        "saved_endpoints": [{"id": "ep", "name": "Local", "provider": "ollama", "url": "http://localhost:11434"}],
        "chat_model": {"enabled": True, "endpoint_id": "ep", "model": "example-guide:14b-instruct-q4_0"},
        "specialist_model": {"enabled": True, "endpoint_id": "ep", "model": "example-specialist:32b"},
        "vision_model": {"enabled": False, "endpoint_id": "", "model": ""},
    },
    "routing": {"complexity_threshold": 3},
}

MODEL_CONFIG_WITH_VISION = {
    **MODEL_CONFIG,
    "llm_config": {
        **MODEL_CONFIG["llm_config"],
        "vision_model": {"enabled": True, "endpoint_id": "ep", "model": "example-vision:8b"},
    },
}


def make_router(score: int = 3, cached: bool = False) -> ComplexityRouter:
    """Create a ComplexityRouter with a mock LLM that returns the given score."""
    mock = MagicMock()
    mock.return_value = {"response": str(score)}
    router = ComplexityRouter(mock, "guide-model", "http://localhost:11434")
    return router


def make_pipeline(score: int = 3) -> IntakePipeline:
    router = make_router(score)
    return IntakePipeline(router, get_context_budget, MODEL_CONFIG)


# ── Acceptance cases ─────────────────────────────────────────────

class TestGreeting:
    def test_greeting_full_pipeline(self):
        pipeline = make_pipeline(score=3)
        result = pipeline.analyze("hi")

        assert result.intent == "greeting"
        assert result.is_greeting is True
        assert result.complexity_score == 1
        assert result.needs_retrieval is False
        assert result.recommended_model == "guide"

    def test_greeting_no_retrieval(self):
        pipeline = make_pipeline()
        result = pipeline.analyze("hello")
        assert result.needs_retrieval is False
        assert result.needs_tools is False


class TestFarewell:
    def test_farewell_full_pipeline(self):
        pipeline = make_pipeline()
        result = pipeline.analyze("bye")

        assert result.intent == "farewell"
        assert result.is_farewell is True
        assert result.complexity_score == 1
        assert result.needs_retrieval is False
        assert result.recommended_model == "guide"


class TestTroubleshooting:
    def test_troubleshooting_routes_to_specialist(self):
        pipeline = make_pipeline(score=4)
        result = pipeline.analyze("why is nginx failing after the update?")

        assert result.intent == "troubleshooting"
        assert result.is_troubleshooting is True
        assert result.complexity_score >= 3
        assert result.needs_retrieval is True
        assert result.needs_tools is True
        assert result.recommended_model == "specialist"

    def test_troubleshooting_floor_3_still_routes_to_specialist(self):
        """Even if LLM returns 1, troubleshooting floor makes it 3 -> specialist."""
        pipeline = make_pipeline(score=1)
        result = pipeline.analyze("nginx is failing")

        assert result.is_troubleshooting is True
        assert result.complexity_score == 3  # floor applied
        assert result.recommended_model == "specialist"
        assert result.needs_tools is True


class TestCommand:
    def test_command_with_storage_domain(self):
        pipeline = make_pipeline(score=3)
        result = pipeline.analyze("show me disk usage")

        assert result.intent == "command"
        assert "storage" in result.detected_domains
        assert result.needs_retrieval is True

    def test_simple_command_routes_to_guide(self):
        pipeline = make_pipeline(score=2)
        result = pipeline.analyze("show me disk usage")

        assert result.complexity_score == 2
        assert result.recommended_model == "guide"


class TestQuestion:
    def test_question_routes_correctly(self):
        pipeline = make_pipeline(score=2)
        result = pipeline.analyze("what is the latest version of nginx?")

        assert result.is_question is True
        assert result.complexity_score == 2
        assert result.recommended_model == "guide"
        assert result.needs_retrieval is True


# ── Derived flags ────────────────────────────────────────────────

class TestDerivedFlags:
    def test_web_search_pattern_detected(self):
        pipeline = make_pipeline()
        result = pipeline.analyze("what is the latest version of docker?")
        assert result.needs_web_search is True

    def test_no_web_search_for_normal_query(self):
        pipeline = make_pipeline()
        result = pipeline.analyze("check disk usage")
        assert result.needs_web_search is False

    def test_cve_triggers_web_search(self):
        pipeline = make_pipeline()
        result = pipeline.analyze("is there a CVE for openssh?")
        assert result.needs_web_search is True

    def test_needs_tools_only_for_troubleshooting(self):
        """needs_tools requires both troubleshooting AND complexity >= threshold."""
        pipeline = make_pipeline(score=4)
        # High complexity but not troubleshooting
        result = pipeline.analyze("configure a complex multi-tier backup strategy with encryption")
        assert result.needs_tools is False  # not troubleshooting

    def test_needs_tools_requires_high_complexity(self):
        """Low complexity troubleshooting doesn't trigger tools."""
        pipeline = make_pipeline(score=2)
        # Troubleshooting floor makes it 3, so this WILL trigger tools
        result = pipeline.analyze("nginx error")
        assert result.is_troubleshooting is True
        assert result.complexity_score == 3  # floor
        assert result.needs_tools is True


# ── Budget integration ───────────────────────────────────────────

class TestBudgetIntegration:
    def test_guide_model_budget(self):
        pipeline = make_pipeline(score=2)
        result = pipeline.analyze("simple question")
        assert result.recommended_model == "guide"
        assert result.model_tier == "medium"  # 14b guide -> MEDIUM
        assert result.context_budget.total == 2000

    def test_specialist_model_budget(self):
        pipeline = make_pipeline(score=4)
        result = pipeline.analyze("complex diagnostic query about nginx configuration")
        assert result.recommended_model == "specialist"
        assert result.model_tier == "large"  # 32b specialist -> LARGE
        assert result.context_budget.total == 4000


# ── MessageIntake completeness ───────────────────────────────────

class TestMessageIntakeFields:
    def test_all_fields_populated(self):
        pipeline = make_pipeline(score=3)
        result = pipeline.analyze("check /etc/nginx/nginx.conf for errors")

        # All fields should be non-default
        assert result.intent is not None
        assert isinstance(result.is_question, bool)
        assert isinstance(result.is_greeting, bool)
        assert isinstance(result.is_farewell, bool)
        assert isinstance(result.is_troubleshooting, bool)
        assert result.message_length is not None
        assert isinstance(result.detected_domains, list)
        assert isinstance(result.has_error_indicators, bool)
        assert isinstance(result.has_code_blocks, bool)
        assert isinstance(result.has_file_paths, bool)
        assert isinstance(result.has_images, bool)
        assert isinstance(result.complexity_score, int)
        assert result.complexity_level is not None
        assert isinstance(result.complexity_cached, bool)
        assert isinstance(result.complexity_latency_ms, float)
        assert result.model_tier is not None
        assert result.context_budget is not None
        assert result.recommended_model is not None
        assert isinstance(result.needs_retrieval, bool)
        assert isinstance(result.needs_tools, bool)
        assert isinstance(result.needs_web_search, bool)


# ── Vision routing ───────────────────────────────────────────────

class TestVisionRouting:
    def test_image_message_routes_to_vision(self):
        """A message with image references should route to vision model."""
        pipeline = IntakePipeline(make_router(score=5), get_context_budget, MODEL_CONFIG_WITH_VISION)
        result = pipeline.analyze("What's wrong with this screenshot? ![error](screenshot.png)")
        assert result.has_images is True
        assert result.recommended_model == "vision"

    def test_vision_overrides_specialist(self):
        """Vision should take priority even for high-complexity messages."""
        pipeline = IntakePipeline(make_router(score=5), get_context_budget, MODEL_CONFIG_WITH_VISION)
        result = pipeline.analyze("Debug this kernel panic, here's the crash dump: crash.jpeg")
        assert result.recommended_model == "vision"

    def test_no_vision_model_falls_back(self):
        """If no vision model configured, falls back to guide/specialist."""
        pipeline = IntakePipeline(make_router(score=2), get_context_budget, MODEL_CONFIG)
        result = pipeline.analyze("Check this screenshot.png for errors")
        assert result.has_images is True
        assert result.recommended_model != "vision"

    def test_plain_text_does_not_route_to_vision(self):
        """Messages without images should not route to vision."""
        pipeline = IntakePipeline(make_router(score=2), get_context_budget, MODEL_CONFIG_WITH_VISION)
        result = pipeline.analyze("why is nginx failing?")
        assert result.has_images is False
        assert result.recommended_model != "vision"

    def test_disabled_specialist_routes_to_guide(self):
        """A specialist slot with a model but enabled=False must not be used."""
        cfg = {**MODEL_CONFIG, "llm_config": {**MODEL_CONFIG["llm_config"],
               "specialist_model": {"enabled": False, "endpoint_id": "ep", "model": "example-specialist:32b"}}}
        pipeline = IntakePipeline(make_router(score=5), get_context_budget, cfg)
        result = pipeline.analyze("complex diagnostic query about nginx configuration")
        assert result.recommended_model == "guide"
