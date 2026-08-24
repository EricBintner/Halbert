"""
Intake pipeline orchestrator.

Chains signal detection -> complexity assessment -> budget allocation
and derives routing flags (needs_retrieval, needs_tools, recommended_model).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Dict, List

from .budget import ContextBudget, get_context_budget
from .complexity import ComplexityLevel, ComplexityRouter
from .signals import MessageSignals, analyze_message

logger = logging.getLogger(__name__)


# ── Transitional web search patterns (removed when F4 lands) ─────

_WEB_SEARCH_RE = re.compile(
    r"\b(latest version|current version|newest version|cve|security advisory|"
    r"compare|vs\.|versus|difference between)\b",
    re.IGNORECASE,
)


# ── Result dataclass ─────────────────────────────────────────────

@dataclass
class MessageIntake:
    """Full intake analysis result — the output of IntakePipeline.analyze()."""

    # From signals
    intent: str
    is_question: bool
    is_greeting: bool
    is_farewell: bool
    is_troubleshooting: bool
    message_length: str
    detected_domains: List[str]
    has_error_indicators: bool
    has_code_blocks: bool
    has_file_paths: bool
    has_images: bool

    # From complexity
    complexity_score: int
    complexity_level: str
    complexity_cached: bool
    complexity_latency_ms: float

    # From budget
    model_tier: str
    context_budget: ContextBudget
    recommended_model: str  # "guide" | "specialist" | "vision"

    # Derived
    needs_retrieval: bool
    needs_tools: bool
    needs_web_search: bool  # transitional, deferred to F4


# ── Pipeline ─────────────────────────────────────────────────────

class IntakePipeline:
    """Orchestrates signal detection, complexity routing, and budget allocation."""

    def __init__(
        self,
        complexity_router: ComplexityRouter,
        budget_fn: Callable[[str], ContextBudget],
        model_config: Dict,
    ):
        """Args:
            complexity_router: the ComplexityRouter instance.
            budget_fn: callable that takes a model name and returns a ContextBudget.
                Typically `get_context_budget` from intake.budget.
            model_config: dict with keys:
                - orchestrator.model: the guide model name
                - specialist.model: the specialist model name
                - specialist.enabled: bool
                - routing.complexity_threshold: int (default 3)
        """
        self._router = complexity_router
        self._budget_fn = budget_fn
        self._model_config = model_config

    def analyze(self, message: str) -> MessageIntake:
        """Run the full intake pipeline on a message.

        Returns a MessageIntake with all fields populated.
        """
        # ── Stage 1: Signals ──────────────────────────────────────
        signals = analyze_message(message)

        # ── Stage 2: Complexity ───────────────────────────────────
        complexity = self._router.assess(message, signals)

        # ── Stage 3: Model selection + budget ─────────────────────
        threshold = self._model_config.get("routing", {}).get("complexity_threshold", 3)
        specialist_enabled = self._model_config.get("specialist", {}).get("enabled", False)
        vision_model_name = self._model_config.get("vision", {}).get("model", "")

        if signals.has_images and vision_model_name:
            # Vision takes priority — image content requires a multimodal model
            recommended_model_name = "vision"
            model_name = vision_model_name
        elif complexity.score >= threshold and specialist_enabled:
            recommended_model_name = "specialist"
            model_name = self._model_config.get("specialist", {}).get("model", "")
        else:
            recommended_model_name = "guide"
            model_name = self._model_config.get("orchestrator", {}).get("model", "")

        budget = self._budget_fn(model_name)

        # ── Stage 4: Derived flags ────────────────────────────────
        needs_retrieval = not (signals.is_greeting or signals.is_farewell)
        needs_tools = signals.is_troubleshooting and complexity.score >= threshold
        needs_web_search = bool(_WEB_SEARCH_RE.search(message))

        return MessageIntake(
            # Signals
            intent=signals.intent,
            is_question=signals.is_question,
            is_greeting=signals.is_greeting,
            is_farewell=signals.is_farewell,
            is_troubleshooting=signals.is_troubleshooting,
            message_length=signals.message_length,
            detected_domains=signals.detected_domains,
            has_error_indicators=signals.has_error_indicators,
            has_code_blocks=signals.has_code_blocks,
            has_file_paths=signals.has_file_paths,
            has_images=signals.has_images,
            # Complexity
            complexity_score=complexity.score,
            complexity_level=complexity.level.name,
            complexity_cached=complexity.cached,
            complexity_latency_ms=complexity.latency_ms,
            # Budget
            model_tier=budget.tier.value,
            context_budget=budget,
            recommended_model=recommended_model_name,
            # Derived
            needs_retrieval=needs_retrieval,
            needs_tools=needs_tools,
            needs_web_search=needs_web_search,
        )
