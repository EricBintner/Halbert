# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A8: the <continuity> hint and the thread history sit at the tail
of the PLANNING prompt and immediately before the query in RESPONDING."""

from halbert_core.prompts import AgentPromptBuilder

HINT = '<continuity>\nThread: "Scanner share" · 2 turns · last active 3 minutes ago.\n</continuity>'


class TestPlanningPrompt:
    def test_continuity_sits_immediately_before_current_task(self):
        p = AgentPromptBuilder().build_planning_prompt(query="add a share", context="ctx", plan=[], continuity=HINT)
        assert p.index(HINT) < p.index("## Current Task")
        between = p[p.index(HINT) + len(HINT):p.index("## Current Task")]
        assert between.strip() == ""
        assert p.rstrip().endswith("User request: add a share")

    def test_voice_preamble_precedes_hint(self):
        p = AgentPromptBuilder(voice="first_person").build_planning_prompt(query="q", context="", continuity=HINT)
        pre = AgentPromptBuilder.CONTINUITY_PREAMBLE["first_person"]
        assert pre in p and p.index(pre) < p.index(HINT)
        assert "recall_thread" in pre and "new_thread" in pre
        p2 = AgentPromptBuilder(voice="the_computer").build_planning_prompt(query="q", context="", continuity=HINT)
        assert AgentPromptBuilder.CONTINUITY_PREAMBLE["the_computer"] in p2 and pre not in p2

    def test_preamble_drops_the_tool_instruction_when_tools_are_rejected(self):
        # spec §7: "The instruction to call tools is omitted when the model has
        # rejected tool schemas" — the client reports that as tools_supported=False.
        b = AgentPromptBuilder(voice="first_person")
        p = b.build_planning_prompt(query="q", context="", continuity=HINT, tools_supported=False)
        no_tools = AgentPromptBuilder.CONTINUITY_PREAMBLE_NO_TOOLS["first_person"]
        assert no_tools in p and HINT in p and p.index(no_tools) < p.index(HINT)
        assert "recall_thread" not in p and "new_thread" not in p
        assert "one continuous conversation" in no_tools
        # None (unknown) and True keep the full preamble
        for supported in (None, True):
            p2 = b.build_planning_prompt(query="q", context="", continuity=HINT, tools_supported=supported)
            assert AgentPromptBuilder.CONTINUITY_PREAMBLE["first_person"] in p2
        r = b.build_response_prompt(query="q", context=[], observations=[], continuity=HINT, tools_supported=False)
        assert no_tools in r and "recall_thread" not in r
        for voice in ("first_person", "the_computer", "hybrid"):
            assert "recall_thread" not in AgentPromptBuilder.CONTINUITY_PREAMBLE_NO_TOOLS[voice]
            assert "new_thread" not in AgentPromptBuilder.CONTINUITY_PREAMBLE_NO_TOOLS[voice]
        p3 = AgentPromptBuilder(voice="the_computer").build_planning_prompt(
            query="q", context="", continuity=HINT, tools_supported=False
        )
        assert AgentPromptBuilder.CONTINUITY_PREAMBLE_NO_TOOLS["the_computer"] in p3 and no_tools not in p3

    def test_no_continuity_means_no_preamble_and_sections_precede_task(self):
        p = AgentPromptBuilder().build_planning_prompt(
            query="q", context="THE CONTEXT", observations=["saw x"],
            plan=[{"step": "look", "status": "completed"}],
        )
        assert "<continuity>" not in p and "recall_thread" not in p
        assert p.index("## Available Context") < p.index("## Current Task")
        assert p.index("## Previous Observations") < p.index("## Current Task")
        assert p.index("## Instructions") < p.index("## Current Task")
        assert "- saw x" in p and "1. ● look" in p


class TestResponsePrompt:
    def test_history_then_continuity_then_query(self):
        history = [
            {"role": "user", "content": "we set up samba last week"},
            {"role": "assistant", "content": "Yes, [media] at /srv/media."},
        ]
        p = AgentPromptBuilder().build_response_prompt(
            query="add scanner", context=[], observations=[], history=history, continuity=HINT,
        )
        assert p.index("## Earlier in this conversation") < p.index(HINT) < p.index("## Task")
        assert "**user**: we set up samba last week" in p
        assert "**assistant**: Yes, [media] at /srv/media." in p
        assert p.index("**user**") < p.index("**assistant**")

    def test_history_lines_are_one_line_capped_and_flattened(self):
        from halbert_core.agents.blocks import TextBlock
        p = AgentPromptBuilder().build_response_prompt(
            query="q", context=[], observations=[],
            history=[
                {"role": "user", "content": "x" * 2000},
                {"role": "assistant", "content": [TextBlock(text="flattened text")]},
                {"role": "system", "content": "[Earlier in this subject: Title: Samba]"},
                {"role": "user", "content": "line one\n\nline two"},
            ],
        )
        line = next(l for l in p.splitlines() if l.startswith("**user**: x"))
        assert len(line) == len("**user**: ") + 500 + 1 and line.endswith("…")
        assert "**assistant**: flattened text" in p
        assert "**system**: [Earlier in this subject: Title: Samba]" in p
        assert "**user**: line one line two" in p

    def test_no_history_no_continuity_unchanged_head(self):
        p = AgentPromptBuilder().build_response_prompt(query="q", context=[], observations=[])
        assert p.startswith("## Task\nAnswer this question: q")
        assert "## Earlier in this conversation" not in p and "<continuity>" not in p
