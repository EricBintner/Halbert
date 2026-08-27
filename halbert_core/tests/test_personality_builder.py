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


class TestArchetypeBlending:
    """Test archetype blending (Phase 2)."""

    def test_blend_same_archetype_returns_that_archetype(self):
        from halbert_core.persona.archetypes import blend_archetypes, is_available
        if not is_available():
            pytest.skip("Haloysius not available")
        result = blend_archetypes("sentinel", "sentinel", 0.5)
        # Blending identical archetypes should yield the same profile
        assert abs(result["openness"] - 0.40) < 0.01

    def test_blend_ratio_1_is_all_a(self):
        from halbert_core.persona.archetypes import blend_archetypes, is_available
        if not is_available():
            pytest.skip("Haloysius not available")
        result = blend_archetypes("sentinel", "comedian", 1.0)
        # ratio=1.0 means all sentinel
        assert abs(result["openness"] - 0.40) < 0.01
        assert abs(result["extraversion"] - 0.30) < 0.01

    def test_blend_ratio_0_is_all_b(self):
        from halbert_core.persona.archetypes import blend_archetypes, is_available
        if not is_available():
            pytest.skip("Haloysius not available")
        result = blend_archetypes("sentinel", "comedian", 0.0)
        # ratio=0.0 means all comedian
        assert abs(result["openness"] - 0.65) < 0.01
        assert abs(result["extraversion"] - 0.75) < 0.01

    def test_blend_50_50_is_average(self):
        from halbert_core.persona.archetypes import blend_archetypes, is_available
        if not is_available():
            pytest.skip("Haloysius not available")
        result = blend_archetypes("sentinel", "comedian", 0.5)
        # 50/50 should be the average
        expected_openness = (0.40 + 0.65) / 2
        assert abs(result["openness"] - expected_openness) < 0.01

    def test_blend_invalid_archetype_raises(self):
        from halbert_core.persona.archetypes import blend_archetypes, is_available
        if not is_available():
            pytest.skip("Haloysius not available")
        with pytest.raises(ValueError, match="Unknown archetype ID"):
            blend_archetypes("sentinel", "nonexistent", 0.5)

    def test_blend_invalid_ratio_raises(self):
        from halbert_core.persona.archetypes import blend_archetypes, is_available
        if not is_available():
            pytest.skip("Haloysius not available")
        with pytest.raises(ValueError, match="Ratio must be"):
            blend_archetypes("sentinel", "comedian", 1.5)

    def test_blend_returns_all_five_traits(self):
        from halbert_core.persona.archetypes import blend_archetypes, is_available
        if not is_available():
            pytest.skip("Haloysius not available")
        result = blend_archetypes("mentor", "surgeon", 0.7)
        assert set(result.keys()) == {
            "openness", "conscientiousness", "extraversion",
            "agreeableness", "neuroticism",
        }
        for v in result.values():
            assert 0.0 <= v <= 1.0


class TestPromptManagerCustomMode:
    """Test PromptManager CUSTOM mode loads personality from BeingConfig."""

    def test_custom_mode_generates_from_personality(self, tmp_path):
        from halbert_core.model.prompt_manager import PromptManager, PromptMode
        from halbert_core.config.being_config import BeingConfig, save_being_config

        # Set up a being.yml with personality in tmp_path
        cfg = BeingConfig()
        cfg.custom_personality_prompt = "TEST_CUSTOM_PERSONA_MARKER"
        save_being_config(cfg, str(tmp_path / "being.yml"))

        # Point PromptManager at tmp_path as config dir
        pm = PromptManager(config_dir=tmp_path)
        prompt = pm.build_prompt(mode=PromptMode.CUSTOM)

        # The custom persona layer should be generated from BeingConfig
        assert "TEST_CUSTOM_PERSONA_MARKER" in prompt

    def test_custom_mode_falls_back_to_placeholder_when_no_personality(self, tmp_path):
        from halbert_core.model.prompt_manager import PromptManager, PromptMode
        from halbert_core.config.being_config import BeingConfig, save_being_config

        # Empty personality config
        cfg = BeingConfig()
        save_being_config(cfg, str(tmp_path / "being.yml"))

        pm = PromptManager(config_dir=tmp_path)
        prompt = pm.build_prompt(mode=PromptMode.CUSTOM)

        # Should still have base safety + mode layer, just no custom personality
        assert "SAFETY RULES" in prompt
        assert "Custom" in prompt

    def test_custom_txt_file_overrides_generated_personality(self, tmp_path):
        from halbert_core.model.prompt_manager import PromptManager, PromptMode
        from halbert_core.config.being_config import BeingConfig, save_being_config

        # Set up being.yml with personality
        cfg = BeingConfig()
        cfg.custom_personality_prompt = "FROM_BEING_CONFIG"
        save_being_config(cfg, str(tmp_path / "being.yml"))

        # Create custom.txt that should take precedence
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "custom.txt").write_text("FROM_CUSTOM_TXT_FILE")

        pm = PromptManager(config_dir=tmp_path)
        prompt = pm.build_prompt(mode=PromptMode.CUSTOM)

        # File-based layer should win over generated
        assert "FROM_CUSTOM_TXT_FILE" in prompt
        assert "FROM_BEING_CONFIG" not in prompt


class TestPhase3CharacterFields:
    """Test Phase 3 Character card fields on BeingConfig."""

    def test_default_character_fields(self):
        from halbert_core.config.being_config import BeingConfig
        cfg = BeingConfig()
        assert cfg.name == ""
        assert cfg.voice_presentation == "not_defined"
        assert cfg.model is None

    def test_validate_rejects_invalid_voice_presentation(self):
        from halbert_core.config.being_config import BeingConfig
        cfg = BeingConfig()
        cfg.voice_presentation = "invalid"
        with pytest.raises(ValueError, match="Invalid voice_presentation"):
            cfg.validate()

    def test_validate_accepts_valid_voice_presentations(self):
        from halbert_core.config.being_config import BeingConfig
        for vp in ("not_defined", "male", "female"):
            cfg = BeingConfig()
            cfg.voice_presentation = vp
            cfg.validate()

    def test_from_dict_picks_up_character_fields(self):
        from halbert_core.config.being_config import BeingConfig
        cfg = BeingConfig.from_dict({
            "name": "Halbert",
            "voice_presentation": "male",
            "model": "llama3:8b",
        })
        assert cfg.name == "Halbert"
        assert cfg.voice_presentation == "male"
        assert cfg.model == "llama3:8b"

    def test_to_dict_includes_character_fields(self):
        from halbert_core.config.being_config import BeingConfig
        cfg = BeingConfig()
        cfg.name = "TestBot"
        d = cfg.to_dict()
        assert "name" in d
        assert d["name"] == "TestBot"
        assert "voice_presentation" in d
        assert "model" in d


class TestCommunicationStyles:
    """Test the 5 communication-style archetypes."""

    def test_list_communication_styles_returns_five(self):
        from halbert_core.persona.archetypes import list_communication_styles, is_available
        if not is_available():
            pytest.skip("Haloysius not available")
        styles = list_communication_styles()
        assert len(styles) == 5
        ids = {s["id"] for s in styles}
        assert ids == {"concise", "balanced", "detailed", "analytical", "casual"}

    def test_communication_styles_have_profiles(self):
        from halbert_core.persona.archetypes import list_communication_styles, is_available
        if not is_available():
            pytest.skip("Haloysius not available")
        styles = list_communication_styles()
        for s in styles:
            assert "profile" in s
            assert set(s["profile"].keys()) == {
                "openness", "conscientiousness", "extraversion",
                "agreeableness", "neuroticism",
            }

    def test_get_archetype_finds_communication_style(self):
        from halbert_core.persona.archetypes import get_archetype, is_available
        if not is_available():
            pytest.skip("Haloysius not available")
        archetype = get_archetype("concise")
        assert archetype is not None
        assert archetype.id == "concise"
        assert archetype.name == "Concise"

    def test_blend_communication_styles(self):
        from halbert_core.persona.archetypes import blend_archetypes, is_available
        if not is_available():
            pytest.skip("Haloysius not available")
        result = blend_archetypes("concise", "casual", 0.5)
        assert set(result.keys()) == {
            "openness", "conscientiousness", "extraversion",
            "agreeableness", "neuroticism",
        }


class TestVoicePresentationInPrompt:
    """Test that voice_presentation injects into personality prompt."""

    def test_male_presentation_appears_in_extras(self):
        from halbert_core.config.being_config import BeingConfig
        from halbert_core.persona.personality_prompt import generate_personality_section
        cfg = BeingConfig()
        cfg.voice_presentation = "male"
        cfg.tone_descriptors = ["calm"]
        result = generate_personality_section(cfg)
        assert "VOICE PRESENTATION: male" in result

    def test_not_defined_does_not_appear(self):
        from halbert_core.config.being_config import BeingConfig
        from halbert_core.persona.personality_prompt import generate_personality_section
        cfg = BeingConfig()
        cfg.voice_presentation = "not_defined"
        cfg.tone_descriptors = ["calm"]
        result = generate_personality_section(cfg)
        assert "VOICE PRESENTATION" not in result

    def test_custom_prompt_overrides_voice_presentation(self):
        from halbert_core.config.being_config import BeingConfig
        from halbert_core.persona.personality_prompt import generate_personality_section
        cfg = BeingConfig()
        cfg.voice_presentation = "female"
        cfg.custom_personality_prompt = "Just be yourself."
        result = generate_personality_section(cfg)
        assert result == "Just be yourself."
        assert "VOICE PRESENTATION" not in result
