# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Task B2 pins: the execute_code schema description carries Hermes's
when-to-use discipline, the PLANNING prompt names the pipeline tool, and
both disappear when the model has rejected tool schemas."""
from halbert_core.prompts import AgentPromptBuilder
from halbert_core.tools.execute_code import EXECUTE_CODE_SCHEMA


class TestSchemaGuidance:

    def test_schema_describes_when_to_use_it(self):
        desc = EXECUTE_CODE_SCHEMA["description"]
        assert "3+ tool calls" in desc
        assert "Prefer normal tool calls" in desc
        assert "return dicts" in desc  # the failure-hint discipline
        assert EXECUTE_CODE_SCHEMA["parameters"]["required"] == ["script"]


class TestPlanningPromptGuidance:

    def test_planning_prompt_mentions_the_pipeline_tool(self):
        p = AgentPromptBuilder().build_planning_prompt(query="q", context="")
        assert "execute_code" in p
        assert "halbert_tools" in p
        assert "3+" in p and "Prefer normal tool calls" in p

    def test_planning_prompt_omits_it_when_tools_are_rejected(self):
        p = AgentPromptBuilder().build_planning_prompt(
            query="q", context="", tools_supported=False)
        assert "execute_code" not in p
        assert "halbert_tools" not in p
        assert "recall_memory" not in p  # the sibling guidance goes with it