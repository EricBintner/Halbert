# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Personality prompt section generator.

Converts BeingConfig personality fields into a prompt section string
suitable for injection into the system prompt. Uses Haloysius
PersonalityProfile and the sysadmin archetypes from this package.

All Haloysius imports are lazy so the module degrades gracefully.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

_DEFAULT_TRAITS = {
    "openness": 0.5,
    "conscientiousness": 0.5,
    "extraversion": 0.5,
    "agreeableness": 0.5,
    "neuroticism": 0.5,
}


def _has_custom_traits(profile: Dict[str, float]) -> bool:
    """True if any trait differs from the 0.5 default."""
    for trait, default in _DEFAULT_TRAITS.items():
        val = profile.get(trait, 0.5)
        if abs(val - default) > 0.01:
            return True
    return False


def _format_extras(
    tone_descriptors: list,
    speech_patterns: list,
    directives: list,
) -> str:
    """Format tone, speech patterns, and directives into prompt lines."""
    lines = []
    if tone_descriptors:
        lines.append("TONE: " + ", ".join(tone_descriptors))
    if speech_patterns:
        lines.append("SPEECH PATTERNS:")
        for pattern in speech_patterns:
            lines.append(f"- {pattern}")
    if directives:
        lines.append("DIRECTIVES:")
        for directive in directives:
            lines.append(f"- {directive}")
    return "\n".join(lines) if lines else ""


def generate_personality_section(being_cfg: Any) -> str:
    """Generate a personality prompt section from BeingConfig.

    Pipeline (first match wins):
    1. custom_personality_prompt non-empty -> use directly
    2. archetype_id set -> load archetype, generate section + extras
    3. personality_profile has non-default values -> generate + extras
    4. Else -> empty string (no personality layer)

    Args:
        being_cfg: A BeingConfig instance (or duck-typed object with the
            same attributes).

    Returns:
        Prompt section string, or "" if no personality is configured.
    """
    # 1. Escape hatch
    custom = getattr(being_cfg, "custom_personality_prompt", "") or ""
    if custom.strip():
        return custom.strip()

    tone = getattr(being_cfg, "tone_descriptors", []) or []
    speech = getattr(being_cfg, "speech_patterns", []) or []
    directives = getattr(being_cfg, "directives", []) or []
    extras = _format_extras(tone, speech, directives)

    # 2. Archetype
    archetype_id = getattr(being_cfg, "archetype_id", None)
    if archetype_id:
        from .archetypes import get_archetype

        archetype = get_archetype(archetype_id)
        if archetype is not None:
            section = archetype.generate_system_prompt_section()
            if extras:
                section = section + "\n\n" + extras
            return section
        else:
            logger.warning(
                f"Unknown archetype_id '{archetype_id}', falling back to traits"
            )

    # 3. Custom Big Five traits
    profile_dict = getattr(being_cfg, "personality_profile", {}) or {}
    if _has_custom_traits(profile_dict):
        try:
            from haloysius.persona.personality import PersonalityProfile

            profile = PersonalityProfile.from_dict(profile_dict)
            section = profile.generate_prompt_section()
            if extras:
                section = section + "\n\n" + extras
            return section
        except ImportError:
            logger.warning(
                "Haloysius not available, cannot generate personality section"
            )
            if extras:
                return extras
            return ""

    # 4. Only extras (tone/directives without archetype or custom traits)
    if extras:
        return extras

    # 5. Nothing configured
    return ""
