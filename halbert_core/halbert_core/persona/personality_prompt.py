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
    include_voice_presentation: bool = True,
    being_cfg: Any = None,
) -> str:
    """Format tone, speech patterns, and directives into prompt lines.

    Phase 2.5: ``VOICE PRESENTATION`` is only included for text turns.
    For voice turns, the engine's ``ModalityAwarePromptBuilder`` handles
    voice identity via ``PersonaVoiceProfile`` — injecting it into the
    text prompt is redundant and can confuse the model.
    """
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
    # Voice presentation guidance — only for text turns. The engine's
    # PersonaVoiceProfile handles voice identity for voice turns.
    if include_voice_presentation and being_cfg is not None:
        vp = getattr(being_cfg, "voice_presentation", "not_defined") or "not_defined"
        if vp in ("male", "female"):
            lines.append(f"VOICE PRESENTATION: {vp}")
    return "\n".join(lines) if lines else ""


def generate_personality_section(being_cfg: Any, response_modality: str = "text") -> str:
    """Generate a personality prompt section from BeingConfig.

    Pipeline (first match wins):
    1. custom_personality_prompt non-empty -> use directly
    2. archetype_id set -> load archetype, generate section + extras
    3. personality_profile has non-default values -> generate + extras
    4. Else -> empty string (no personality layer)

    Phase 2.5: ``response_modality`` controls whether voice-presentation
    guidance is included. For voice turns, the engine's
    ``ModalityAwarePromptBuilder`` handles voice identity via
    ``PersonaVoiceProfile``, so the text prompt doesn't need it.

    Args:
        being_cfg: A BeingConfig instance (or duck-typed object with the
            same attributes).
        response_modality: "text" or "voice" — controls whether
            voice-presentation guidance is included in the prompt.

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
    # Phase 2.5: skip VOICE PRESENTATION for voice turns — the engine
    # handles voice identity via PersonaVoiceProfile.
    include_vp = response_modality != "voice"
    extras = _format_extras(tone, speech, directives, include_vp, being_cfg)

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
