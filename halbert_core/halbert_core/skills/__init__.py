# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Role-scoped skills: domain expertise bundled with retrieval scope,
safety constraints, model tier, and context budget."""

from .loader import load_skills, default_skill_dirs
from .matcher import SkillMatch, SkillMatcher, current_platform
from .parser import (
    Skill,
    SkillParseError,
    SkillSafety,
    SkillTriggers,
    canonical_scope_id,
    parse_skill,
    parse_skill_file,
)
from .registry import SkillRegistry

__all__ = [
    "Skill", "SkillSafety", "SkillTriggers", "SkillParseError",
    "parse_skill", "parse_skill_file", "canonical_scope_id",
    "load_skills", "default_skill_dirs",
    "SkillRegistry",
    "SkillMatcher", "SkillMatch", "current_platform",
]
