"""
Tests for intake/budget.py — model tier detection and context budgets.
"""

from __future__ import annotations

import pytest

from halbert_core.intake.budget import (
    CONTEXT_BUDGETS,
    ContextBudget,
    ModelTier,
    detect_model_tier,
    get_context_budget,
)


# ── Tier detection ───────────────────────────────────────────────

class TestDetectModelTier:
    @pytest.mark.parametrize("model, expected", [
        ("qwen2.5:14b-instruct-q4_0", ModelTier.MEDIUM),
        ("qwen2.5:32b", ModelTier.LARGE),
        ("llama3.1:8b", ModelTier.SMALL),
        ("llama3.1:70b", ModelTier.XLARGE),
        ("llama3.1:405b", ModelTier.XLARGE),
        ("phi3:3b", ModelTier.TINY),
        ("qwen2.5:3b", ModelTier.TINY),
        ("mistral:7b", ModelTier.SMALL),
        ("qwen2.5:7b-instruct", ModelTier.SMALL),
        ("llama3.3:70b", ModelTier.XLARGE),
    ])
    def test_known_models(self, model, expected):
        assert detect_model_tier(model) == expected

    def test_dash_separator(self):
        assert detect_model_tier("llama-3.1-8b") == ModelTier.SMALL
        assert detect_model_tier("model-70b-chat") == ModelTier.XLARGE

    def test_underscore_separator(self):
        assert detect_model_tier("qwen2.5_14b") == ModelTier.MEDIUM

    def test_moe_models(self):
        assert detect_model_tier("mixtral:8x22b") == ModelTier.MASSIVE
        assert detect_model_tier("deepseek-r1:70b") == ModelTier.MASSIVE
        assert detect_model_tier("qwq:32b") == ModelTier.MASSIVE

    def test_unknown_model_falls_back_to_medium(self):
        assert detect_model_tier("some-random-model") == ModelTier.MEDIUM
        assert detect_model_tier("") == ModelTier.MEDIUM
        assert detect_model_tier("gpt-4") == ModelTier.MEDIUM


# ── Budget lookup ────────────────────────────────────────────────

class TestGetContextBudget:
    def test_medium_model_budget(self):
        b = get_context_budget("qwen2.5:14b-instruct-q4_0")
        assert b.tier == ModelTier.MEDIUM
        assert b.total == 2000

    def test_small_model_retrieval(self):
        b = get_context_budget("llama3.1:8b")
        assert b.tier == ModelTier.SMALL
        assert b.retrieval == 100

    def test_large_model_total(self):
        b = get_context_budget("qwen2.5:32b")
        assert b.tier == ModelTier.LARGE
        assert b.total == 4000

    def test_xlarge_model_total(self):
        b = get_context_budget("llama3.1:70b")
        assert b.tier == ModelTier.XLARGE
        assert b.total == 8000

    def test_tiny_model_total(self):
        b = get_context_budget("phi3:3b")
        assert b.tier == ModelTier.TINY
        assert b.total == 400

    def test_massive_model_total(self):
        b = get_context_budget("mixtral:8x22b")
        assert b.tier == ModelTier.MASSIVE
        assert b.total == 16000


# ── Budget integrity ─────────────────────────────────────────────

class TestBudgetIntegrity:
    @pytest.mark.parametrize("tier", list(ModelTier))
    def test_fields_sum_to_total(self, tier):
        b = CONTEXT_BUDGETS[tier]
        allocated = (
            b.system_identity + b.user_rules + b.retrieval
            + b.memory + b.discovery + b.conversation + b.observations
        )
        assert allocated == b.total, (
            f"{tier.value}: fields sum to {allocated}, total is {b.total}"
        )

    @pytest.mark.parametrize("tier", list(ModelTier))
    def test_all_budgets_present(self, tier):
        assert tier in CONTEXT_BUDGETS
        assert isinstance(CONTEXT_BUDGETS[tier], ContextBudget)

    @pytest.mark.parametrize("tier", list(ModelTier))
    def test_all_fields_positive(self, tier):
        b = CONTEXT_BUDGETS[tier]
        for field_name in ("system_identity", "user_rules", "retrieval",
                           "memory", "discovery", "conversation", "observations"):
            assert getattr(b, field_name) > 0, f"{tier.value}.{field_name} is not positive"
