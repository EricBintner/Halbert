# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the personality builder: BeingConfig fields, archetypes, prompt generation."""

import pytest
import sys
from pathlib import Path

# Ensure halbert_core is importable
halbert_core_path = Path(__file__).parent.parent
if str(halbert_core_path) not in sys.path:
    sys.path.insert(0, str(halbert_core_path))


class TestBeingConfigPersonality:
    """Test personality fields on BeingConfig."""

    def test_default_personality_is_neutral(self):
        from halbert_core.config.being_config import BeingConfig
        cfg = BeingConfig()
        assert cfg.personality_profile == {
            "openness": 0.5, "conscientiousness": 0.5,
            "extraversion": 0.5, "agreeableness": 0.5, "neuroticism": 0.5,
        }
        assert cfg.archetype_id is None
        assert cfg.tone_descriptors == []
        assert cfg.speech_patterns == []
        assert cfg.directives == []
        assert cfg.custom_personality_prompt == ""

    def test_validate_rejects_out_of_range_traits(self):
        from halbert_core.config.being_config import BeingConfig
        cfg = BeingConfig()
        cfg.personality_profile["openness"] = 1.5
        with pytest.raises(ValueError, match="must be 0.0-1.0"):
            cfg.validate()

    def test_validate_rejects_unknown_trait(self):
        from halbert_core.config.being_config import BeingConfig
        cfg = BeingConfig()
        cfg.personality_profile["unknown_trait"] = 0.5
        with pytest.raises(ValueError, match="Unknown personality trait"):
            cfg.validate()

    def test_validate_accepts_boundary_values(self):
        from halbert_core.config.being_config import BeingConfig
        cfg = BeingConfig()
        cfg.personality_profile["openness"] = 0.0
        cfg.personality_profile["neuroticism"] = 1.0
        cfg.validate()  # should not raise

    def test_from_dict_picks_up_personality_fields(self):
        from halbert_core.config.being_config import BeingConfig
        data = {
            "voice": "the_computer",
            "personality_profile": {
                "openness": 0.8, "conscientiousness": 0.9,
                "extraversion": 0.3, "agreeableness": 0.6, "neuroticism": 0.2,
            },
            "archetype_id": "sentinel",
            "tone_descriptors": ["calm", "precise"],
        }
        cfg = BeingConfig.from_dict(data)
        assert cfg.archetype_id == "sentinel"
        assert cfg.tone_descriptors == ["calm", "precise"]
        assert cfg.personality_profile["openness"] == 0.8

    def test_to_dict_includes_personality(self):
        from halbert_core.config.being_config import BeingConfig
        cfg = BeingConfig()
        cfg.archetype_id = "mentor"
        d = cfg.to_dict()
        assert "personality_profile" in d
        assert "archetype_id" in d
        assert d["archetype_id"] == "mentor"


class TestPersonalityPromptGenerator:
    """Test generate_personality_section pipeline."""

    def test_empty_config_returns_empty(self):
        from halbert_core.config.being_config import BeingConfig
        from halbert_core.persona.personality_prompt import generate_personality_section
        cfg = BeingConfig()
        assert generate_personality_section(cfg) == ""

    def test_custom_prompt_escape_hatch(self):
        from halbert_core.config.being_config import BeingConfig
        from halbert_core.persona.personality_prompt import generate_personality_section
        cfg = BeingConfig()
        cfg.custom_personality_prompt = "You are a grumpy sysadmin."
        result = generate_personality_section(cfg)
        assert result == "You are a grumpy sysadmin."

    def test_extras_only(self):
        from halbert_core.config.being_config import BeingConfig
        from halbert_core.persona.personality_prompt import generate_personality_section
        cfg = BeingConfig()
        cfg.tone_descriptors = ["calm", "precise"]
        cfg.directives = ["Always show the command before running it."]
        result = generate_personality_section(cfg)
        assert "TONE: calm, precise" in result
        assert "Always show the command before running it." in result

    def test_archetype_only_without_haloysius(self):
        """If Haloysius is not installed, archetype lookup returns empty or extras only."""
        from halbert_core.config.being_config import BeingConfig
        from halbert_core.persona.personality_prompt import generate_personality_section
        cfg = BeingConfig()
        cfg.archetype_id = "sentinel"
        # This will either work (Haloysius installed) or gracefully degrade
        result = generate_personality_section(cfg)
        # Should not raise; either has content or is empty
        assert isinstance(result, str)

    def test_custom_traits_without_haloysius(self):
        """Custom traits should not crash if Haloysius is unavailable."""
        from halbert_core.config.being_config import BeingConfig
        from halbert_core.persona.personality_prompt import generate_personality_section
        cfg = BeingConfig()
        cfg.personality_profile["openness"] = 0.9
        result = generate_personality_section(cfg)
        assert isinstance(result, str)


class TestAgentPromptBuilderPersonality:
    """Test personality injection in AgentPromptBuilder."""

    def test_no_being_cfg_returns_empty_personality(self):
        from halbert_core.prompts.agent_prompts import AgentPromptBuilder
        builder = AgentPromptBuilder()
        assert builder._generate_personality() == ""

    def test_reload_personality_does_not_crash(self):
        from halbert_core.prompts.agent_prompts import AgentPromptBuilder
        builder = AgentPromptBuilder()
        # Should not raise even if being.yml doesn't exist
        builder.reload_personality()

    def test_fallback_path_includes_personality(self):
        """When base_builder is None, personality should appear between identity and capabilities."""
        from halbert_core.prompts.agent_prompts import AgentPromptBuilder
        from halbert_core.config.being_config import BeingConfig

        cfg = BeingConfig()
        cfg.custom_personality_prompt = "TEST_PERSONALITY_MARKER"
        builder = AgentPromptBuilder(being_cfg=cfg)
        prompt = builder.build_system_prompt()
        assert "TEST_PERSONALITY_MARKER" in prompt
        # Personality should come after identity, before capabilities
        identity_pos = prompt.index("You are Halbert")
        personality_pos = prompt.index("TEST_PERSONALITY_MARKER")
        capabilities_pos = prompt.index("## Capabilities")
        assert identity_pos < personality_pos < capabilities_pos


class TestPromptBuilderPersonality:
    """Test personality_section parameter in PromptBuilder."""

    def test_personality_section_appears_in_prompt(self):
        from halbert_core.prompts.builder import PromptBuilder
        from halbert_core.prompts.loader import PromptLoader
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        if not prompts_dir.exists():
            pytest.skip("prompts dir not found")
        loader = PromptLoader(prompts_dir)
        builder = PromptBuilder(loader)

        prompt_without = builder.build_prompt(tier="specialist")
        prompt_with = builder.build_prompt(
            tier="specialist",
            personality_section="TEST_PERSONALITY_CONTENT",
        )

        assert "TEST_PERSONALITY_CONTENT" not in prompt_without
        assert "TEST_PERSONALITY_CONTENT" in prompt_with
        assert "<personality>" in prompt_with
        assert "</personality>" in prompt_with
