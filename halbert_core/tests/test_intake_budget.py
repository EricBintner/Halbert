# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
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
        ("example-model:14b-instruct-q4_0", ModelTier.MEDIUM),
        ("example-model:32b", ModelTier.LARGE),
        ("example-model:8b", ModelTier.SMALL),
        ("example-model:70b", ModelTier.XLARGE),
        ("example-model:405b", ModelTier.XLARGE),
        ("example-model:3b", ModelTier.TINY),
        ("example-model:7b", ModelTier.SMALL),
        ("example-model:7b-instruct", ModelTier.SMALL),
        ("another-model:70b", ModelTier.XLARGE),
    ])
    def test_size_tags(self, model, expected):
        assert detect_model_tier(model) == expected

    def test_dash_separator(self):
        assert detect_model_tier("example-model-8b") == ModelTier.SMALL
        assert detect_model_tier("model-70b-chat") == ModelTier.XLARGE

    def test_underscore_separator(self):
        assert detect_model_tier("example_model_14b") == ModelTier.MEDIUM

    def test_moe_models(self):
        # "<experts>x<size>b" tags and an explicit "moe" token mark MoE models.
        assert detect_model_tier("example-moe:8x22b") == ModelTier.MASSIVE
        assert detect_model_tier("example-model:8x7b") == ModelTier.MASSIVE
        assert detect_model_tier("example-moe:70b") == ModelTier.MASSIVE

    def test_reasoning_model_is_sized_not_massive(self):
        # Tier detection is size-based only; a thinking model without a MoE
        # tag is sized by its parameter count.
        assert detect_model_tier("example-think:32b") == ModelTier.LARGE
        assert detect_model_tier("example-reasoner:70b") == ModelTier.XLARGE

    def test_explicit_tier_override_wins(self):
        assert detect_model_tier("example-model:8b", tier=ModelTier.MASSIVE) == ModelTier.MASSIVE
        assert detect_model_tier("example-model:8b", tier="large") == ModelTier.LARGE
        assert detect_model_tier("example-model:8b", tier="XLarge") == ModelTier.XLARGE
        # Unknown / empty override falls back to detection
        assert detect_model_tier("example-model:8b", tier="huge") == ModelTier.SMALL
        assert detect_model_tier("example-model:8b", tier="") == ModelTier.SMALL

    def test_unknown_model_falls_back_to_medium(self):
        assert detect_model_tier("some-random-model") == ModelTier.MEDIUM
        assert detect_model_tier("") == ModelTier.MEDIUM
        assert detect_model_tier("hosted-model-v4") == ModelTier.MEDIUM


# ── Budget lookup ────────────────────────────────────────────────

class TestGetContextBudget:
    def test_medium_model_budget(self):
        b = get_context_budget("example-model:14b-instruct-q4_0")
        assert b.tier == ModelTier.MEDIUM
        assert b.total == 2000

    def test_small_model_retrieval(self):
        b = get_context_budget("example-model:8b")
        assert b.tier == ModelTier.SMALL
        assert b.retrieval == 100

    def test_large_model_total(self):
        b = get_context_budget("example-model:32b")
        assert b.tier == ModelTier.LARGE
        assert b.total == 4000

    def test_xlarge_model_total(self):
        b = get_context_budget("example-model:70b")
        assert b.tier == ModelTier.XLARGE
        assert b.total == 8000

    def test_tiny_model_total(self):
        b = get_context_budget("example-model:3b")
        assert b.tier == ModelTier.TINY
        assert b.total == 400

    def test_massive_model_total(self):
        b = get_context_budget("example-moe:8x22b")
        assert b.tier == ModelTier.MASSIVE
        assert b.total == 16000

    def test_tier_override(self):
        b = get_context_budget("example-model:8b", tier="massive")
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
