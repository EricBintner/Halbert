# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""B2: a matched skill's expertise reaches the model.

DEFECT-1's second break, independent of the first: `ComposedSkills.prompt` is
built at `composer.py:99` and has zero consumers in the tree. Even with a
matcher wired, no skill's expertise reaches the model.

The seam is `AgentStateMachine._build_messages`, between the identity block
and the prompt -- never `PromptBuilder.build_prompt`, which is dead on the
chat path. The block is sent on both LLM calls of a turn, so it is paid for
twice, which is why it is capped here rather than left to `merge_prompts`
concatenating every active skill's body unbounded.
"""

import pytest

from halbert_core.skills.composer import merge_prompts
from halbert_core.skills.loader import BUILTIN_DIR, load_skills


@pytest.fixture
def storage_ops():
    return load_skills([BUILTIN_DIR])["storage-ops"]


class TestTheComposedBlockIsCapped:

    def test_a_body_over_the_cap_is_truncated_with_a_marker(self):
        from halbert_core.skills.composer import MAX_SKILL_PROMPT_CHARS, cap_prompt

        capped = cap_prompt("A" * (MAX_SKILL_PROMPT_CHARS * 3),
                            limit=MAX_SKILL_PROMPT_CHARS)
        assert len(capped) <= MAX_SKILL_PROMPT_CHARS + 80
        assert "truncated" in capped.lower(), (
            "silent truncation is the same defect as a silent drop"
        )

    def test_a_body_under_the_cap_is_untouched(self):
        from halbert_core.skills.composer import cap_prompt

        body = "[Active Skill: storage-ops]\nMind the zpool."
        assert cap_prompt(body) == body

    def test_many_skills_cannot_exceed_the_total_cap(self):
        from halbert_core.skills.composer import MAX_TOTAL_PROMPT_CHARS, cap_prompt

        big = "\n\n".join(f"[Active Skill: s{i}]\n" + "B" * 8000 for i in range(6))
        assert len(cap_prompt(big)) <= MAX_TOTAL_PROMPT_CHARS + 80


class TestTheBlockReachesMessagesZero:

    def _machine(self, composed_prompt):
        """A state machine stub exercising only _build_messages."""
        from halbert_core.agents.state_machine import AgentStateMachine

        m = AgentStateMachine.__new__(AgentStateMachine)
        m._identity_block = lambda modality: "I am this machine."
        m._composed_prompt_block = lambda: composed_prompt
        m._continuity_tail = lambda: ""
        m.ctx = type("C", (), {
            "conversation_history": [],
            "thread_receipt_block": "",
            "defanged_query": None,
            "user_query": "",
            "model_override": None,
            "tier_override": None,
            "intake": None,
        })()
        return m

    def test_the_skill_block_sits_between_identity_and_prompt(self, storage_ops):
        block = merge_prompts([storage_ops])
        m = self._machine(block)
        messages = m._build_messages("What pool should I scrub?")
        head = messages[0]["content"]
        assert "[Active Skill: storage-ops]" in head
        assert head.index("I am this machine.") < head.index("[Active Skill:")
        assert head.index("[Active Skill:") < head.index("What pool should I scrub?")

    def test_no_active_skill_leaves_the_message_unchanged(self):
        m = self._machine("")
        head = m._build_messages("What time is it?")[0]["content"]
        assert "[Active Skill:" not in head
        assert head == "I am this machine.\n\nWhat time is it?"


class TestEndToEndThroughRealComposition:
    """The tests above stub `_composed_prompt_block`, so they prove placement
    but not the path. This one goes through the real matcher, the real
    composer and the real seam -- the assertion the whole of B1+B2 is for.
    """

    def _machine_with_intake(self, intake):
        from halbert_core.agents.state_machine import AgentStateMachine

        m = AgentStateMachine.__new__(AgentStateMachine)
        m._identity_block = lambda modality: "I am this machine."
        m._continuity_tail = lambda: ""
        m.ctx = type("C", (), {
            "conversation_history": [], "thread_receipt_block": "",
            "defanged_query": None, "user_query": "", "model_override": None,
            "tier_override": None, "intake": intake,
        })()
        return m

    def test_a_zpool_question_carries_storage_ops_expertise_into_messages_zero(self):
        from halbert_core.intake.complexity import ComplexityLevel, ComplexityResult
        from halbert_core.intake.budget import get_context_budget
        from halbert_core.intake.pipeline import IntakePipeline
        from halbert_core.skills.loader import daemon_skill_dirs
        from halbert_core.skills.matcher import SkillMatcher
        from halbert_core.skills.registry import SkillRegistry

        class R:
            def assess(self, message, signals):
                return ComplexityResult(score=3, level=ComplexityLevel.MODERATE,
                                        reasoning="", cached=True)

        pipeline = IntakePipeline(
            complexity_router=R(), budget_fn=get_context_budget,
            model_config={"llm_config": {"chat_model": {"model": "c"}}},
            skill_matcher=SkillMatcher(SkillRegistry.from_disk(dirs=daemon_skill_dirs())),
        )
        intake = pipeline.analyze("my zpool is degraded, which disk do I replace?")
        head = self._machine_with_intake(intake)._build_messages("Answer me.")[0]["content"]
        assert "[Active Skill: storage-ops]" in head

    def test_an_unrelated_question_carries_no_skill_block(self):
        from halbert_core.intake.complexity import ComplexityLevel, ComplexityResult
        from halbert_core.intake.budget import get_context_budget
        from halbert_core.intake.pipeline import IntakePipeline
        from halbert_core.skills.loader import daemon_skill_dirs
        from halbert_core.skills.matcher import SkillMatcher
        from halbert_core.skills.registry import SkillRegistry

        class R:
            def assess(self, message, signals):
                return ComplexityResult(score=1, level=ComplexityLevel.SIMPLE,
                                        reasoning="", cached=True)

        pipeline = IntakePipeline(
            complexity_router=R(), budget_fn=get_context_budget,
            model_config={"llm_config": {"chat_model": {"model": "c"}}},
            skill_matcher=SkillMatcher(SkillRegistry.from_disk(dirs=daemon_skill_dirs())),
        )
        intake = pipeline.analyze("what time is it?")
        head = self._machine_with_intake(intake)._build_messages("Answer me.")[0]["content"]
        assert "[Active Skill:" not in head
