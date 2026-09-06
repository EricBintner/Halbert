# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Skill composition.

Several skills can match one turn — a question about an nginx 502 is both a
service question and a network one. The composer reduces them to the single
set of decisions a turn actually needs: one prompt, one retrieval scope, one
model tier, one budget split, one set of safety constraints.

The merge rules are not symmetric, because the things being merged are not
alike:

    prompts   concatenate      — expertise adds up
    safety    most restrictive — a constraint one skill declares binds all
    scope     highest priority — retrieval takes a single scope (v1)
    model     highest priority — one turn, one tier
    budget    max appetite     — averaging would dilute a deep specialist
    tools     intersection     — a restriction one skill declares binds all
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .parser import Skill, SkillSafety

logger = logging.getLogger(__name__)

# Budget appetite is capped so a skill cannot claim the whole window.
MAX_BUDGET_CAP = 2.0

# Categories a skill may bid for. system_identity and user_rules are absent on
# purpose: role adoption must not be able to starve the base identity prompt
# or the user's own rules.
ADJUSTABLE_CATEGORIES = (
    "retrieval", "memory", "discovery", "conversation", "observations",
)
PROTECTED_CATEGORIES = ("system_identity", "user_rules")

# Categories a skill's budget_multiplier is understood to be bidding for.
# A skill asking for depth is asking to read more, not to remember more.
APPETITE_CATEGORIES = ("retrieval", "discovery")

# More capable first — used only to break a priority tie between two skills
# asking for different tiers.
_TIER_RANK = {"specialist": 2, "chat": 1, "vision": 0}


@dataclass(frozen=True)
class ComposedSkills:
    """The single set of decisions a turn's active skills add up to."""

    skills: Tuple[Skill, ...] = ()
    prompt: str = ""
    role: Optional[str] = None
    scope: Optional[str] = None
    knowledge_scope: Optional[str] = None
    trace_expand: bool = True
    model: Optional[str] = None
    safety: SkillSafety = field(default_factory=SkillSafety)
    allowed_tools: Optional[Tuple[str, ...]] = None
    budget_appetite: Dict[str, float] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.skills

    @property
    def names(self) -> List[str]:
        return [s.name for s in self.skills]


def _ordered(skills: Sequence[Skill]) -> List[Skill]:
    """Most authoritative first: priority, then the matcher's own order.

    The matcher already sorted by score, so preserving its order as the
    tie-break keeps the better-matching skill ahead of a weaker one at the
    same priority.
    """
    indexed = sorted(enumerate(skills), key=lambda pair: (-pair[1].priority_rank, pair[0]))
    return [skill for _, skill in indexed]


#: Per-skill and total ceilings on expertise text reaching messages[0].
#:
#: merge_prompts concatenates every active skill's body unbounded, and the
#: block is sent on BOTH LLM calls of a turn, so it is paid for twice. The
#: seam sits outside ContextBudget -- nothing else would stop a long SKILL.md
#: from crowding out the conversation it is meant to inform.
#:
#: Characters, not tokens: this runs before any tokeniser is in scope, and a
#: character bound that is roughly right beats a token bound that needs a
#: model handle to compute.
MAX_SKILL_PROMPT_CHARS = 4000
MAX_TOTAL_PROMPT_CHARS = 8000

_TRUNCATION_NOTE = "\n[… truncated: skill text over the {limit}-character cap]"


def cap_prompt(text: str, *, limit: int = MAX_TOTAL_PROMPT_CHARS) -> str:
    """Bound `text`, marking the cut rather than making it silently.

    A silently truncated instruction is worse than a dropped one: the model
    acts on half a rule with no sign the other half existed.
    """
    if len(text) <= limit:
        return text
    logger.warning(
        "skill prompt text over the %d-character cap (%d); truncating",
        limit, len(text),
    )
    return text[:limit].rstrip() + _TRUNCATION_NOTE.format(limit=limit)


def merge_prompts(skills: Sequence[Skill]) -> str:
    """Concatenate expertise prompts under labelled headers.

    Headers are not decoration: with two skills active the model needs to know
    which instruction came from which role, or a storage rule reads as a
    network rule.
    """
    parts = []
    for skill in skills:
        if not skill.prompt.strip():
            continue
        body = cap_prompt(skill.prompt.strip(), limit=MAX_SKILL_PROMPT_CHARS)
        parts.append(f"[Active Skill: {skill.name}]\n{body}")
    return cap_prompt("\n\n".join(parts))


def merge_safety(skills: Sequence[Skill]) -> SkillSafety:
    """Most restrictive wins: booleans OR, lists union.

    There is no subtraction here by design. A skill cannot relax a constraint
    another active skill declared — if storage-ops protects /boot, a co-active
    service-ops cannot unprotect it.
    """
    requires_approval = False
    paths: List[str] = []
    services: List[str] = []
    commands: List[str] = []

    for skill in skills:
        requires_approval = requires_approval or skill.safety.destructive_requires_approval
        paths.extend(skill.safety.protected_paths)
        services.extend(skill.safety.protected_services)
        commands.extend(skill.safety.blocked_commands)

    def _dedup(items: List[str]) -> Tuple[str, ...]:
        seen = set()
        out = []
        for item in items:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return tuple(out)

    return SkillSafety(
        destructive_requires_approval=requires_approval,
        protected_paths=_dedup(paths),
        protected_services=_dedup(services),
        blocked_commands=_dedup(commands),
    )


def merge_allowed_tools(skills: Sequence[Skill]) -> Optional[Tuple[str, ...]]:
    """Intersect tool allowlists. None anywhere means "inherits all".

    A skill that does not restrict tools is not asserting that everything is
    permitted, so it does not widen a co-active skill's restriction — it
    simply contributes no restriction of its own.
    """
    restricted = [s.allowed_tools for s in skills if s.allowed_tools is not None]
    if not restricted:
        return None

    allowed = set(restricted[0])
    for other in restricted[1:]:
        allowed &= set(other)
    if not allowed:
        logger.warning(
            "composed skills %s have no tools in common; all tools denied",
            [s.name for s in skills],
        )
    return tuple(sorted(allowed))


def merge_model(skills: Sequence[Skill]) -> Optional[str]:
    """The most authoritative skill's tier, ties broken to the more capable."""
    if not skills:
        return None
    top = max(s.priority_rank for s in skills)
    contenders = [s for s in skills if s.priority_rank == top]
    return max(
        contenders, key=lambda s: _TIER_RANK.get(s.model, 3)  # explicit ids win
    ).model


def merge_budget_appetite(skills: Sequence[Skill]) -> Dict[str, float]:
    """Max appetite per category, capped.

    Deliberately not a mean. If storage-ops asks for 1.8 to read deeply and an
    incidental service-ops asks for 1.0, averaging to 1.4 dilutes exactly the
    skill that needed the depth.
    """
    if not skills:
        return {}
    appetite = min(max(s.budget_multiplier for s in skills), MAX_BUDGET_CAP)
    if appetite <= 1.0:
        return {}
    return {category: appetite for category in APPETITE_CATEGORIES}


def compose(skills: Sequence[Skill]) -> ComposedSkills:
    """Reduce the turn's active skills to one set of decisions."""
    if not skills:
        return ComposedSkills()

    ordered = _ordered(skills)
    lead = ordered[0]

    # v1 takes a single scope: the SourcePrep context endpoint's `scope` is a
    # single string, so a union of two skills' scopes is not expressible.
    # Falling to the most authoritative skill's is the honest reduction.
    role = next((s.role for s in ordered if s.role), None)
    scope = next((s.scope for s in ordered if s.scope), None)
    knowledge_scope = next((s.knowledge_scope for s in ordered if s.knowledge_scope), None)

    if len({s.scope for s in ordered if s.scope}) > 1:
        logger.debug(
            "composed skills declare multiple scopes; using %r from %r",
            scope, lead.name,
        )

    return ComposedSkills(
        skills=tuple(ordered),
        prompt=merge_prompts(ordered),
        role=role,
        scope=scope,
        knowledge_scope=knowledge_scope,
        trace_expand=any(s.trace_expand for s in ordered),
        model=merge_model(ordered),
        safety=merge_safety(ordered),
        allowed_tools=merge_allowed_tools(ordered),
        budget_appetite=merge_budget_appetite(ordered),
    )


def compose_matches(matches: Sequence[Any]) -> ComposedSkills:
    """Compose from SkillMatch objects, as the matcher returns them."""
    return compose([m.skill for m in matches if getattr(m, "skill", None)])


# ── Budget ────────────────────────────────────────────────────────────

def reallocate_budget(context_budget: Any, appetite: Dict[str, float]) -> Any:
    """Shift tokens toward the categories the active skills bid for.

    ContextBudget holds absolute token counts that sum to `total`, so a skill
    cannot simply multiply its retrieval budget — that would overrun the
    tier's context window. Instead the adjustable categories are re-weighted
    against each other and renormalized back to the same total, leaving
    `total` and the protected categories untouched.

    Returns the budget unchanged when no skill bid for anything.
    """
    if not appetite or context_budget is None:
        return context_budget

    try:
        adjustable = {
            name: int(getattr(context_budget, name))
            for name in ADJUSTABLE_CATEGORIES
            if hasattr(context_budget, name)
        }
    except (TypeError, ValueError):  # pragma: no cover - defensive
        logger.debug("budget reallocation skipped: unreadable budget", exc_info=True)
        return context_budget

    pool = sum(adjustable.values())
    if pool <= 0:
        return context_budget

    weighted = {
        name: value * float(appetite.get(name, 1.0))
        for name, value in adjustable.items()
    }
    weighted_total = sum(weighted.values())
    if weighted_total <= 0:  # pragma: no cover - defensive
        return context_budget

    # Renormalize so the adjustable categories still sum to the same pool.
    scaled = {
        name: int(value * pool / weighted_total) for name, value in weighted.items()
    }

    # Integer division loses a few tokens; give the remainder to the category
    # with the strongest appetite so the invariant holds exactly.
    drift = pool - sum(scaled.values())
    if drift:
        target = max(scaled, key=lambda n: (appetite.get(n, 1.0), scaled[n]))
        scaled[target] += drift

    try:
        return dataclasses.replace(context_budget, **scaled)
    except TypeError:  # pragma: no cover - non-dataclass budget
        logger.debug("budget reallocation skipped: not a dataclass", exc_info=True)
        return context_budget
