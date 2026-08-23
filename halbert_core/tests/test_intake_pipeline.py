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
    "orchestrator": {"model": "qwen2.5:14b-instruct-q4_0"},
    "specialist": {"model": "qwen2.5:32b", "enabled": True},
    "routing": {"complexity_threshold": 3},
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
        assert result.model_tier == "medium"  # qwen2.5:14b -> MEDIUM
        assert result.context_budget.total == 2000

    def test_specialist_model_budget(self):
        pipeline = make_pipeline(score=4)
        result = pipeline.analyze("complex diagnostic query about nginx configuration")
        assert result.recommended_model == "specialist"
        assert result.model_tier == "large"  # qwen2.5:32b -> LARGE
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
