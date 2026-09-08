# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Role-scoped skills: domain expertise bundled with retrieval scope,
safety constraints, model tier, and context budget."""

from .composer import (
    ComposedSkills,
    compose,
    compose_matches,
    reallocate_budget,
)
from .loader import load_skills, default_skill_dirs
from .matcher import SkillMatch, SkillMatcher, current_platform
from .parser import (
    DESCRIPTION_LIMIT,
    SKILL_ID_RE,
    Skill,
    SkillParseError,
    SkillRequirements,
    SkillSafety,
    SkillTriggers,
    canonical_scope_id,
    clamp_description,
    new_skill_id,
    parse_skill,
    parse_skill_file,
    validate_description,
)
from .registry import SkillRegistry
from .reserved import is_reserved_skill_name, reserved_skill_names
from .sidecar import (
    SkillSidecar,
    SkillSidecarError,
    load_sidecar,
    verify_sidecar_join,
)

__all__ = [
    "Skill", "SkillSafety", "SkillTriggers", "SkillRequirements",
    "SkillParseError",
    "parse_skill", "parse_skill_file", "canonical_scope_id",
    "new_skill_id", "SKILL_ID_RE",
    "validate_description", "clamp_description", "DESCRIPTION_LIMIT",
    "load_skills", "default_skill_dirs",
    "SkillRegistry",
    "SkillMatcher", "SkillMatch", "current_platform",
    "ComposedSkills", "compose", "compose_matches", "reallocate_budget",
    "is_reserved_skill_name", "reserved_skill_names",
    "SkillSidecar", "SkillSidecarError", "load_sidecar",
    "verify_sidecar_join",
]