# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Halbert intake pipeline — message analysis before the cognitive tick.

Public API:
    from halbert_core.intake import (
        IntakePipeline, MessageIntake,
        MessageSignals, analyze_message,
        ModelTier, ContextBudget, detect_model_tier, get_context_budget,
        ComplexityLevel, ComplexityResult, ComplexityRouter,
    )
"""

from .signals import MessageSignals, analyze_message
from .budget import (
    ModelTier,
    ContextBudget,
    CONTEXT_BUDGETS,
    detect_model_tier,
    get_context_budget,
)
from .complexity import ComplexityLevel, ComplexityResult, ComplexityRouter
from .pipeline import MessageIntake, IntakePipeline

__all__ = [
    # Signals
    "MessageSignals",
    "analyze_message",
    # Budget
    "ModelTier",
    "ContextBudget",
    "CONTEXT_BUDGETS",
    "detect_model_tier",
    "get_context_budget",
    # Complexity
    "ComplexityLevel",
    "ComplexityResult",
    "ComplexityRouter",
    # Pipeline
    "MessageIntake",
    "IntakePipeline",
]
