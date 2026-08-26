# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Halbert Prompt System v2

Structured prompt loading, building, context injection, and safety validation.
Based on Phase 39 research and Phases 40-43 implementation.
Phase 36: Agent-specific prompt building.
"""

from .loader import PromptLoader
from .builder import PromptBuilder
from .agent_prompts import AgentPromptBuilder
from .context import (
    ContextInjector,
    SystemContext,
    UserPreferences,
    RAGResult,
    RAGFormatter,
)
from .safety import (
    SafetyValidator,
    SafetyCheckResult,
    ActionLevel,
    InjectionDetector,
    CommandClassifier,
    OutputFilter,
    get_safety_validator,
)

__all__ = [
    # Loader & Builder (Phase 40)
    "PromptLoader",
    "PromptBuilder",
    # Agent Prompts (Phase 36)
    "AgentPromptBuilder",
    # Context (Phase 42)
    "ContextInjector",
    "SystemContext",
    "UserPreferences",
    # RAG (Phase 45)
    "RAGResult",
    "RAGFormatter",
    # Safety (Phase 43)
    "SafetyValidator",
    "SafetyCheckResult",
    "ActionLevel",
    "InjectionDetector",
    "CommandClassifier",
    "OutputFilter",
    "get_safety_validator",
]
