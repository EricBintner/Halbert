# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Skill matching.

Turns intake signals into the set of skills active for a turn. This is the
routing layer the role-scoped config work lacks: `scope_for_query()` can only
ever return None, "host", or "knowledge_<platform>", so the role scopes
(`storage_admin`, `network_admin`, `service_admin`) are indexed and
unreachable. Matching a skill is what selects one.

Matching is a cheap weighted overlap, not a model call — it runs on every
turn, so it stays in the same budget as intake/signals.py.
"""

from __future__ import annotations

import logging
import platform as _platform
import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence

from .parser import Skill
from .registry import SkillRegistry

logger = logging.getLogger(__name__)

# A domain hit is the strongest evidence: intake already decided the message
# is about storage. A keyword is narrower but noisier ("key" is a security
# keyword and an English word), so it scores lower.
DOMAIN_WEIGHT = 3
KEYWORD_WEIGHT = 2
INTENT_WEIGHT = 1
PLATFORM_WEIGHT = 1

# Conservative on purpose (design §12 Q7): a skill needs real topical
# evidence, not a platform match alone, or every skill declaring
# `platform: [darwin]` would activate on every macOS turn.
MIN_SCORE = DOMAIN_WEIGHT

# Bounds prompt injection and keeps composition tractable (design §14).
MAX_ACTIVE_SKILLS = 3

_PLATFORM_ALIASES = {
    "darwin": {"darwin", "macos", "mac", "osx"},
    "linux": {"linux"},
    "freebsd": {"freebsd", "bsd"},
}


@dataclass(frozen=True)
class SkillMatch:
    """One skill that matched, and why."""

    skill: Skill
    score: int
    matched_domains: tuple = ()
    matched_keywords: tuple = ()
    explicit: bool = False

    @property
    def name(self) -> str:
        return self.skill.name


def current_platform() -> str:
    """This host's platform, normalized.

    MessageSignals carries no platform field — the design's activation diagram
    shows one, but intake never populated it. The matcher resolves it here,
    the same way sourceprep_retrieval_backend does.
    """
    system = _platform.system().lower()
    if system == "darwin":
        return "darwin"
    if system == "linux":
        return "linux"
    if "bsd" in system:
        return "freebsd"
    return system or "unknown"


def _platform_matches(declared: Sequence[str], host: str) -> bool:
    """True when *host* satisfies a skill's declared platforms."""
    if not declared:
        return True
    accepted = _PLATFORM_ALIASES.get(host, {host})
    return any(d.lower() in accepted for d in declared)


def _keyword_hits(keywords: Sequence[str], message: str) -> tuple:
    """Whole-word keyword matches, case-insensitive."""
    if not keywords or not message:
        return ()
    lowered = message.lower()
    hits = []
    for keyword in keywords:
        # Word-boundary match so "ip" does not fire inside "description".
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            hits.append(keyword)
    return tuple(hits)


def score_skill(skill: Skill, *, domains: Iterable[str], intent: str,
                message: str, host_platform: str) -> Optional[SkillMatch]:
    """Score one skill against a turn. Returns None if it does not apply.

    Platform and intent are *filters*, not contributors on their own: a skill
    restricted to a platform we are not on cannot activate at any score.
    """
    if not _platform_matches(skill.triggers.platform, host_platform):
        return None

    if skill.triggers.intent and intent and intent.lower() not in skill.triggers.intent:
        return None

    domain_set = {d.lower() for d in domains}
    matched_domains = tuple(
        d for d in skill.triggers.domains if d.lower() in domain_set
    )
    matched_keywords = _keyword_hits(skill.triggers.keywords, message)

    score = (
        len(matched_domains) * DOMAIN_WEIGHT
        + len(matched_keywords) * KEYWORD_WEIGHT
    )
    if score == 0:
        return None

    if skill.triggers.intent and intent and intent.lower() in skill.triggers.intent:
        score += INTENT_WEIGHT
    if skill.triggers.platform:
        score += PLATFORM_WEIGHT

    return SkillMatch(
        skill=skill,
        score=score,
        matched_domains=matched_domains,
        matched_keywords=matched_keywords,
    )


class SkillMatcher:
    """Selects the skills active for a turn."""

    def __init__(self, registry: SkillRegistry, *,
                 max_active: int = MAX_ACTIVE_SKILLS,
                 min_score: int = MIN_SCORE,
                 host_platform: Optional[str] = None):
        self.registry = registry
        self.max_active = max_active
        self.min_score = min_score
        self._platform = host_platform or current_platform()

    def match(self, message: str, intake: Any = None, *,
              explicit: Optional[Sequence[str]] = None) -> List[SkillMatch]:
        """Return the active skills for this turn, strongest first.

        `intake` is a MessageIntake or MessageSignals — anything carrying
        `detected_domains` and `intent`. `explicit` names skills the user
        invoked directly, which override matching entirely: a `/storage-ops`
        turn runs storage-ops and nothing else, so the behaviour is
        predictable (design §12 Q2).
        """
        if explicit:
            return self._explicit(explicit)

        domains = list(getattr(intake, "detected_domains", ()) or ())
        intent = str(getattr(intake, "intent", "") or "")

        matches = []
        for skill in self.registry.all():
            match = score_skill(
                skill,
                domains=domains,
                intent=intent,
                message=message or "",
                host_platform=self._platform,
            )
            if match and match.score >= self.min_score:
                matches.append(match)

        # Strongest first; ties break to the higher-priority skill, then by
        # name so the ordering is stable across runs.
        matches.sort(
            key=lambda m: (-m.score, -m.skill.priority_rank, m.skill.name)
        )
        selected = matches[: self.max_active]

        if len(matches) > len(selected):
            logger.debug(
                "skill matcher: %d matched, %d activated (cap %d); dropped %s",
                len(matches), len(selected), self.max_active,
                [m.name for m in matches[self.max_active:]],
            )
        return selected

    def _explicit(self, names: Sequence[str]) -> List[SkillMatch]:
        """Resolve user-invoked skill names, ignoring triggers entirely."""
        out = []
        for name in names:
            skill = self.registry.get(name)
            if skill is None:
                logger.warning("no such skill: %r", name)
                continue
            out.append(SkillMatch(skill=skill, score=0, explicit=True))
        return out[: self.max_active]
