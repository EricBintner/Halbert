# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The shipped prompt text speaks as the machine, not as an assistant.

Alignment audit 2026-09-02, T1-01: ``config/prompts/v2/base/identity.xml``
opened "Expert Linux/macOS system administrator assistant" / "the sentient
consciousness of this system", ``safety.xml`` ruled "You are a system
administrator assistant", and ``PromptManager.BASE_SAFETY_PROMPT`` (mirrored
in ``config/prompts/base-safety.txt``) said "the sentient consciousness of
this Linux system" on every host, macOS included. The marketing copy says
"I am not an assistant"; the prompt now agrees with it.
"""

from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / "config" / "prompts"

BANNED = ("assistant", "sentient")


class TestShippedPromptText:

    @pytest.mark.parametrize("relpath", [
        "v2/base/identity.xml",
        "v2/base/safety.xml",
        "base-safety.txt",
    ])
    def test_no_assistant_or_sentient(self, relpath):
        text = (PROMPTS_DIR / relpath).read_text().lower()
        for word in BANNED:
            assert word not in text, f"{relpath} still says '{word}'"

    def test_identity_xml_speaks_as_the_machine(self):
        text = (PROMPTS_DIR / "v2/base/identity.xml").read_text()
        assert "<role>This machine, speaking as itself</role>" in text
        assert "speaking as yourself" in text
        assert "never compromise yourself" in text

    def test_safety_xml_role_rule(self):
        text = (PROMPTS_DIR / "v2/base/safety.xml").read_text()
        assert (
            "<rule>You are this machine, speaking as yourself; "
            "you administer yourself and never compromise yourself</rule>"
        ) in text

    def test_prompt_manager_base_is_platform_aware(self, tmp_path):
        from halbert_core.model.prompt_manager import PromptManager

        with patch(
            "halbert_core.utils.platform.get_platform_name_friendly",
            return_value="macOS (Apple Silicon)",
        ):
            manager = PromptManager(config_dir=tmp_path)
        base = manager.base_safety
        assert "macOS (Apple Silicon)" in base
        assert "Linux" not in base
        assert "{platform}" not in base
        for word in BANNED:
            assert word not in base.lower()
        assert manager.validate_prompt(manager.build_prompt())

    def test_prompt_manager_base_survives_platform_failure(self, tmp_path):
        from halbert_core.model.prompt_manager import PromptManager

        with patch(
            "halbert_core.utils.platform.get_platform_name_friendly",
            side_effect=OSError("no os-release"),
        ):
            manager = PromptManager(config_dir=tmp_path)
        assert manager.base_safety.startswith("I am Halbert. I am this machine")

    def test_prompt_manager_default_config_writes_the_rendered_text(self, tmp_path):
        from halbert_core.model.prompt_manager import PromptManager

        manager = PromptManager(config_dir=tmp_path)
        manager.create_default_config()
        written = (tmp_path / "prompts" / "base-safety.txt").read_text()
        assert "{platform}" not in written
        for word in BANNED:
            assert word not in written.lower()
