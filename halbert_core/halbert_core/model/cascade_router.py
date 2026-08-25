"""MetaHarnessRouter — cost-cascade model router with outcome-based self-tuning (C2a).

Iterates the model ladder cheapest-first (guide -> specialist -> vision) and
returns the first model whose predicted success clears a quality bar. The
prediction blends a tier-based *prior* with recorded outcome *evidence*:

    w = clamp(attempts / (attempts + min_samples), 0, evidence_weight_cap)
    predict = (1 - w) * prior + w * evidence

The blending formula prevents overfitting to a few early samples: with little
evidence the prior dominates; as evidence accumulates it takes over, capped so
the prior is never fully ignored. The router is **opt-in** (default OFF); when
disabled, ``tier_router`` keeps its existing heuristic path so behavior is
byte-identical to before.

Pattern stolen from OCC's MetaHarnessRouter. See OPUS-HANDOFF §C2a.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from .capabilities import ModelDefinition
from .outcome_store import OutcomeStore

logger = logging.getLogger("halbert.model.cascade_router")

# Technical/domain keywords that raise complexity
_TECH_KEYWORDS = [
    "regex", "error", "stack", "trace", "traceback", "debug", "diagnose",
    "config", "configure", "systemd", "journal", "network", "firewall",
    "routing", "kernel", "module", "driver", "partition", "filesystem",
    "lvm", "zfs", "permissions", "ownership", "certificate", "ssl", "ssh",
    "diagnose", "analyze", "optimize", "migrate", "refactor",
]


class MetaHarnessRouter:
    """Cost-cascade model router with outcome-based self-tuning (opt-in)."""

    def __init__(
        self,
        tier_router: "object",
        outcome_store: OutcomeStore,
        min_samples: int = 3,
        evidence_weight_cap: float = 0.9,
        quality_bar: float = 0.7,
    ):
        self._tier_router = tier_router
        self._outcomes = outcome_store
        self._min_samples = min_samples
        self._cap = evidence_weight_cap
        self._quality_bar = quality_bar
        self._enabled = False  # Opt-in, default OFF

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def enable(self) -> None:
        self._enabled = True
        logger.info("MetaHarnessRouter enabled")

    def disable(self) -> None:
        self._enabled = False

    def is_enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    # Complexity estimation (bag-of-words heuristic, 0=trivial, 1=hard)
    # ------------------------------------------------------------------

    def estimate_complexity(self, text: str) -> float:
        """Rough bag-of-words complexity score in [0, 1]."""
        if not text:
            return 0.0
        score = 0.0
        n = len(text)
        # Length signal
        if n > 200:
            score += 0.15
        if n > 1000:
            score += 0.2
        if n > 4000:
            score += 0.15
        # Technical keywords
        lower = text.lower()
        hits = sum(1 for kw in _TECH_KEYWORDS if kw in lower)
        score += min(hits * 0.08, 0.4)
        # Code presence
        if "```" in text:
            score += 0.2
        if re.search(r"\b(def |function |class |import |from |SELECT |JOIN )\b", text):
            score += 0.15
        # Multi-step / multi-question
        if lower.count("?") >= 2:
            score += 0.1
        if any(w in lower for w in ("step by step", "first", "then", "finally", "multi-step")):
            score += 0.1
        return min(max(score, 0.0), 1.0)

    # ------------------------------------------------------------------
    # Prediction (blend prior + evidence)
    # ------------------------------------------------------------------

    def predict(self, model_id: str, complexity: float) -> float:
        """Blend the tier-based prior with recorded success-rate evidence."""
        stats = self._outcomes.stats_for(model_id)
        attempts = stats.get("attempts", 0)
        prior = self._prior(model_id, complexity)
        if attempts < self._min_samples:
            return prior
        w = min(attempts / (attempts + self._min_samples), self._cap)
        evidence = stats.get("success_rate", 0.0)
        return (1 - w) * prior + w * evidence

    def _prior(self, model_id: str, complexity: float) -> float:
        """Tier-based prior success probability for a model at a complexity.

        Guide models are strong on easy tasks and weak on hard ones;
        specialist is stable across the range; vision is best on hard tasks.
        """
        tier = self._tier_of(model_id)
        if tier == "guide":
            prior = 0.85 - 0.6 * complexity
        elif tier == "specialist":
            prior = 0.75 - 0.1 * complexity
        elif tier == "vision":
            prior = 0.55 + 0.3 * complexity
        else:
            prior = 0.6
        return min(max(prior, 0.0), 1.0)

    def _tier_of(self, model_id: str) -> str:
        """Which tier a model id belongs to (guide/specialist/vision/other)."""
        try:
            cfg = self._tier_router.config
        except Exception:
            return "other"
        if getattr(cfg.guide, "primary", None) == model_id:
            return "guide"
        if getattr(cfg.specialist, "primary", None) == model_id:
            return "specialist"
        if getattr(cfg.vision, "primary", None) == model_id:
            return "vision"
        return "other"

    # ------------------------------------------------------------------
    # Ladder + routing
    # ------------------------------------------------------------------

    def _ladder(self) -> List[ModelDefinition]:
        """The model ladder cheapest-first: guide -> specialist -> vision."""
        models: List[ModelDefinition] = []
        try:
            cfg = self._tier_router.config
            for tier_cfg in (cfg.guide, cfg.specialist, cfg.vision):
                primary = getattr(tier_cfg, "primary", None)
                if primary and primary in cfg.models:
                    models.append(cfg.models[primary])
        except Exception as e:
            logger.debug(f"ladder build failed: {e}")
        return models

    def route(self, task_text: str) -> Optional[ModelDefinition]:
        """Iterate the ladder cheapest-first; return the first model whose
        predicted success clears the quality bar. Falls back to the most
        capable model (last in the ladder). Returns None if the ladder is empty.
        """
        ladder = self._ladder()
        if not ladder:
            return None
        complexity = self.estimate_complexity(task_text)
        for model in ladder:
            if self.predict(model.model_id, complexity) >= self._quality_bar:
                return model
        return ladder[-1]  # fallback to most capable

    def escalate(self, failed_model_id: str) -> Optional[ModelDefinition]:
        """Step up one tier after a failure at ``failed_model_id``."""
        ladder = self._ladder()
        for i, model in enumerate(ladder):
            if model.model_id == failed_model_id and i + 1 < len(ladder):
                return ladder[i + 1]
        return None  # already at the top (or unknown) -> no escalation