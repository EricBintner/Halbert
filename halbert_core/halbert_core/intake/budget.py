# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Model-tier detection and context budget allocation.

Maps model names to hardware tiers and provides per-tier token budgets
for context assembly. No VRAM detection, no GPU queries, no external deps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Union


class ModelTier(Enum):
    TINY = "tiny"        # 1-3B
    SMALL = "small"      # 4-8B
    MEDIUM = "medium"    # 9-20B
    LARGE = "large"      # 21-40B
    XLARGE = "xlarge"    # 40B+
    MASSIVE = "massive"  # MoE 262K+


@dataclass(frozen=True)
class ContextBudget:
    """Token budget allocation for a model tier."""
    tier: ModelTier
    total: int
    system_identity: int
    user_rules: int
    retrieval: int
    memory: int
    discovery: int
    conversation: int
    observations: int


# ── Budget table (v1) ────────────────────────────────────────────
# Reconciled: no self_knowledge, rag renamed to retrieval.
# Fields sum to total for every tier.
# Audited deviation from the plan (§T1b.1): the plan table's per-category
# columns do not sum to their tier totals for small/medium/large/xlarge/
# massive (e.g. medium sums to 1700 vs total 2000). This implementation
# scales the conversation bucket so the sum-to-total invariant holds for
# every tier; tier totals and non-conversation values are unchanged.

CONTEXT_BUDGETS: Dict[ModelTier, ContextBudget] = {
    ModelTier.TINY: ContextBudget(
        tier=ModelTier.TINY, total=400,
        system_identity=50, user_rules=50, retrieval=50,
        memory=25, discovery=50, conversation=100, observations=75,
    ),
    ModelTier.SMALL: ContextBudget(
        tier=ModelTier.SMALL, total=800,
        system_identity=75, user_rules=75, retrieval=100,
        memory=75, discovery=75, conversation=300, observations=100,
    ),
    # Plan A (spec §7): the conversation bucket holds six raw turns (12 rows
    # of ~100 tokens) at MEDIUM and LARGE. Tier totals are unchanged; the
    # other buckets pay for it. The thread receipt lives inside this bucket
    # too (context/assembler.py renders it in its own slot).
    ModelTier.MEDIUM: ContextBudget(
        tier=ModelTier.MEDIUM, total=2000,
        system_identity=75, user_rules=50, retrieval=100,
        memory=50, discovery=50, conversation=1600, observations=75,
    ),
    ModelTier.LARGE: ContextBudget(
        tier=ModelTier.LARGE, total=4000,
        system_identity=125, user_rules=100, retrieval=400,
        memory=275, discovery=250, conversation=2400, observations=450,
    ),
    ModelTier.XLARGE: ContextBudget(
        tier=ModelTier.XLARGE, total=8000,
        system_identity=200, user_rules=200, retrieval=1200,
        memory=900, discovery=800, conversation=3600, observations=1100,
    ),
    ModelTier.MASSIVE: ContextBudget(
        tier=ModelTier.MASSIVE, total=16000,
        system_identity=400, user_rules=400, retrieval=2400,
        memory=1800, discovery=1600, conversation=7200, observations=2200,
    ),
}


# ── Model name parsing ───────────────────────────────────────────

# Match patterns like ":14b", "-14b", ":14b-instruct", "_14b"
_SIZE_RE = re.compile(r"[:\-_](\d+(?:\.\d+)?)b\b", re.IGNORECASE)
# Mixture-of-experts: an explicit "moe" token or an "<experts>x<size>b" tag
# such as "8x22b". Generic only -- never keyed on vendor or model names.
_MOE_RE = re.compile(r"\bmoe\b|\b\d+x\d+(?:\.\d+)?b\b", re.IGNORECASE)


def _coerce_tier(tier: Union[ModelTier, str, None]) -> Optional[ModelTier]:
    """Accept a ModelTier or its string value (e.g. from models.yml ``tier:``)."""
    if tier is None or tier == "":
        return None
    if isinstance(tier, ModelTier):
        return tier
    try:
        return ModelTier(str(tier).strip().lower())
    except ValueError:
        return None


def detect_model_tier(
    model_name: str,
    tier: Union[ModelTier, str, None] = None,
) -> ModelTier:
    """Return the hardware tier for a model.

    An explicit ``tier`` override (a ModelTier or its value, e.g. a
    models.yml ``tier: large``) wins. Otherwise the name is parsed for
    generic size hints only:

    Examples:
        <name>:14b-instruct-q4_0 -> MEDIUM
        <name>:32b               -> LARGE
        <name>:8b                -> SMALL
        <name>:70b               -> XLARGE
        <name>:8x22b (MoE)       -> MASSIVE

    Fallback: MEDIUM (safe default).
    """
    override = _coerce_tier(tier)
    if override is not None:
        return override

    if not model_name:
        return ModelTier.MEDIUM

    # MoE / very large models
    if _MOE_RE.search(model_name):
        return ModelTier.MASSIVE

    match = _SIZE_RE.search(model_name)
    if not match:
        return ModelTier.MEDIUM

    size = float(match.group(1))

    if size <= 3:
        return ModelTier.TINY
    elif size <= 8:
        return ModelTier.SMALL
    elif size <= 20:
        return ModelTier.MEDIUM
    elif size <= 40:
        return ModelTier.LARGE
    else:
        return ModelTier.XLARGE


def get_context_budget(
    model_name: str,
    tier: Union[ModelTier, str, None] = None,
) -> ContextBudget:
    """Detect the model tier (or honour an explicit ``tier``) and return its budget."""
    return CONTEXT_BUDGETS[detect_model_tier(model_name, tier)]
