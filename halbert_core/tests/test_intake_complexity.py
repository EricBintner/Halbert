"""
Tests for intake/complexity.py — LLM-based complexity router.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from halbert_core.intake.complexity import (
    ComplexityLevel,
    ComplexityResult,
    ComplexityRouter,
)
from halbert_core.intake.signals import MessageSignals


def make_signals(**kwargs) -> MessageSignals:
    """Create MessageSignals with defaults overridden by kwargs."""
    defaults = dict(
        intent="informational",
        is_question=False,
        is_greeting=False,
        is_farewell=False,
        is_troubleshooting=False,
        message_length="normal",
        detected_domains=[],
        has_error_indicators=False,
        has_code_blocks=False,
        has_file_paths=False,
    )
    defaults.update(kwargs)
    return MessageSignals(**defaults)


def mock_llm_returns(value: str):
    """Create a mock LLM caller that returns a fixed response string."""
    mock = MagicMock()
    mock.return_value = {"response": value}
    return mock


def mock_llm_raises(exc: Exception):
    """Create a mock LLM caller that raises an exception."""
    mock = MagicMock()
    mock.side_effect = exc
    return mock


# ── LLM-based scoring ────────────────────────────────────────────

class TestLLMScoring:
    def test_returns_3(self):
        router = ComplexityRouter(mock_llm_returns("3"), "guide-model", "http://localhost:11434")
        result = router.assess("configure nginx", make_signals())
        assert result.score == 3
        assert result.level == ComplexityLevel.MODERATE
        assert result.cached is False

    def test_returns_5(self):
        router = ComplexityRouter(mock_llm_returns("5"), "guide-model", "http://localhost:11434")
        result = router.assess("complex query", make_signals())
        assert result.score == 5
        assert result.level == ComplexityLevel.VERY_COMPLEX

    def test_returns_1(self):
        router = ComplexityRouter(mock_llm_returns("1"), "guide-model", "http://localhost:11434")
        result = router.assess("simple query", make_signals())
        assert result.score == 1
        assert result.level == ComplexityLevel.TRIVIAL

    def test_returns_4(self):
        router = ComplexityRouter(mock_llm_returns("4"), "guide-model", "http://localhost:11434")
        result = router.assess("complex query", make_signals())
        assert result.score == 4
        assert result.level == ComplexityLevel.COMPLEX


# ── Fallback behavior ────────────────────────────────────────────

class TestFallback:
    def test_garbage_response_fallback(self):
        router = ComplexityRouter(mock_llm_returns("garbage"), "guide-model", "http://localhost:11434")
        result = router.assess("some query", make_signals())
        assert result.score == 3
        assert result.level == ComplexityLevel.MODERATE

    def test_timeout_fallback(self):
        router = ComplexityRouter(mock_llm_raises(TimeoutError()), "guide-model", "http://localhost:11434")
        result = router.assess("some query", make_signals())
        assert result.score == 3
        assert result.level == ComplexityLevel.MODERATE

    def test_generic_exception_fallback(self):
        router = ComplexityRouter(mock_llm_raises(RuntimeError("oops")), "guide-model", "http://localhost:11434")
        result = router.assess("some query", make_signals())
        assert result.score == 3


# ── Fast paths ───────────────────────────────────────────────────

class TestFastPaths:
    def test_greeting_no_llm_call(self):
        mock = mock_llm_returns("3")
        router = ComplexityRouter(mock, "guide-model", "http://localhost:11434")
        result = router.assess("hi", make_signals(is_greeting=True))
        assert result.score == 1
        assert result.cached is True
        assert result.latency_ms < 1.0
        mock.assert_not_called()

    def test_farewell_no_llm_call(self):
        mock = mock_llm_returns("3")
        router = ComplexityRouter(mock, "guide-model", "http://localhost:11434")
        result = router.assess("bye", make_signals(is_farewell=True))
        assert result.score == 1
        assert result.cached is True
        mock.assert_not_called()


# ── Troubleshooting floor ────────────────────────────────────────

class TestTroubleshootingFloor:
    def test_floor_applied_when_llm_returns_low(self):
        mock = mock_llm_returns("1")
        router = ComplexityRouter(mock, "guide-model", "http://localhost:11434")
        result = router.assess("nginx is failing", make_signals(is_troubleshooting=True))
        assert result.score == 3
        assert result.level == ComplexityLevel.MODERATE

    def test_no_floor_when_llm_returns_high(self):
        mock = mock_llm_returns("4")
        router = ComplexityRouter(mock, "guide-model", "http://localhost:11434")
        result = router.assess("nginx is failing", make_signals(is_troubleshooting=True))
        assert result.score == 4

    def test_floor_exactly_3(self):
        mock = mock_llm_returns("2")
        router = ComplexityRouter(mock, "guide-model", "http://localhost:11434")
        result = router.assess("system broken", make_signals(is_troubleshooting=True))
        assert result.score == 3


# ── Caching ──────────────────────────────────────────────────────

class TestCaching:
    def test_repeated_message_is_cache_hit(self):
        mock = mock_llm_returns("4")
        router = ComplexityRouter(mock, "guide-model", "http://localhost:11434")
        msg = "check disk usage and memory"
        signals = make_signals()

        first = router.assess(msg, signals)
        assert first.cached is False

        second = router.assess(msg, signals)
        assert second.cached is True
        assert second.score == first.score
        assert second.latency_ms < 1.0

        # LLM should only be called once
        assert mock.call_count == 1

    def test_different_messages_not_cached(self):
        mock = mock_llm_returns("3")
        router = ComplexityRouter(mock, "guide-model", "http://localhost:11434")
        router.assess("first message", make_signals())
        router.assess("second message", make_signals())
        assert mock.call_count == 2


# ── Stats ────────────────────────────────────────────────────────

class TestStats:
    def test_stats_accumulate(self):
        mock = mock_llm_returns("3")
        router = ComplexityRouter(mock, "guide-model", "http://localhost:11434")
        router.assess("query 1", make_signals())
        router.assess("query 2", make_signals())
        router.assess("query 1", make_signals())  # cache hit

        stats = router.get_stats()
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 2
        assert stats["cache_size"] == 2
        assert "avg_latency_ms" in stats
        assert "score_distribution" in stats
        assert stats["score_distribution"][3] == 2

    def test_stats_after_greeting(self):
        mock = mock_llm_returns("3")
        router = ComplexityRouter(mock, "guide-model", "http://localhost:11434")
        router.assess("hi", make_signals(is_greeting=True))

        stats = router.get_stats()
        # Greeting fast path doesn't count as cache hit or miss
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0
        assert stats["score_distribution"][1] == 1
