# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Intake pipeline orchestrator.

Chains signal detection -> complexity assessment -> budget allocation
and derives routing flags (needs_retrieval, needs_tools, recommended_model).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

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

    # From the skill matcher, when one is wired in. Holds SkillMatch objects,
    # typed loosely so intake stays independent of the skills package.
    active_skills: List[Any] = field(default_factory=list)

    @property
    def active_skill_names(self) -> List[str]:
        return [getattr(m, "name", "") for m in self.active_skills]


# ── Pipeline ─────────────────────────────────────────────────────

class IntakePipeline:
    """Orchestrates signal detection, complexity routing, and budget allocation."""

    def __init__(
        self,
        complexity_router: ComplexityRouter,
        budget_fn: Callable[[str], ContextBudget],
        model_config: Dict,
        skill_matcher: Any = None,
    ):
        """Args:
            complexity_router: the ComplexityRouter instance.
            budget_fn: callable that takes a model name and returns a ContextBudget.
                Typically `get_context_budget` from intake.budget.
            model_config: the whole models.yml dict (post-migration, from
                model.llm_config.load_file()). Reads:
                - llm_config.chat_model.model
                - llm_config.specialist_model.{enabled,model}
                - llm_config.vision_model.{enabled,model}
                - routing.complexity_threshold: int (default 3)
            skill_matcher: optional skills.SkillMatcher. When present, the
                skills active for the turn are matched from the signals and
                carried on MessageIntake. Left None, intake behaves exactly
                as before — skills are additive, not a new requirement.
        """
        self._router = complexity_router
        self._budget_fn = budget_fn
        self._model_config = model_config
        self._skill_matcher = skill_matcher

    def analyze(self, message: str, *,
                explicit_skills: Optional[Sequence[str]] = None) -> MessageIntake:
        """Run the full intake pipeline on a message.

        Returns a MessageIntake with all fields populated.

        `explicit_skills` are skills the user invoked by name (`/storage-ops`),
        which override trigger matching for the turn.
        """
        # ── Stage 1: Signals ──────────────────────────────────────
        signals = analyze_message(message)

        # ── Stage 2: Complexity ───────────────────────────────────
        complexity = self._router.assess(message, signals)

        # ── Stage 3: Model selection + budget ─────────────────────
        llm = self._model_config.get("llm_config") or {}
        chat = llm.get("chat_model") or {}
        specialist = llm.get("specialist_model") or {}
        vision = llm.get("vision_model") or {}
        threshold = self._model_config.get("routing", {}).get("complexity_threshold", 3)
        specialist_enabled = bool(specialist.get("enabled")) and bool(specialist.get("model"))
        vision_model_name = vision.get("model", "") if vision.get("enabled") else ""

        if signals.has_images and vision_model_name:
            # Vision takes priority — image content requires a multimodal model
            recommended_model_name = "vision"
            model_name = vision_model_name
        elif complexity.score >= threshold and specialist_enabled:
            recommended_model_name = "specialist"
            model_name = specialist.get("model", "")
        else:
            recommended_model_name = "guide"
            model_name = chat.get("model", "")

        budget = self._budget_fn(model_name)

        # ── Stage 4: Derived flags ────────────────────────────────
        needs_retrieval = not (signals.is_greeting or signals.is_farewell)
        needs_tools = signals.is_troubleshooting and complexity.score >= threshold
        needs_web_search = bool(_WEB_SEARCH_RE.search(message))

        # ── Stage 5: Skills ───────────────────────────────────────
        # Matching never fails a turn: a broken skill file or matcher costs
        # the turn its role scope and expertise prompt, not its answer.
        active_skills: List[Any] = []
        if self._skill_matcher is not None:
            try:
                active_skills = list(
                    self._skill_matcher.match(
                        message, signals, explicit=explicit_skills
                    )
                )
            except Exception:  # pragma: no cover - defensive
                logger.warning("skill matching failed; continuing", exc_info=True)

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
            active_skills=active_skills,
        )
