# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SK-2: the cache boundary and the stable prefix (design §2.2).

Everything above the literal CACHE_BOUNDARY marker in messages[0] —
identity, catalog, bound-skill bodies — is a pure function of versioned
inputs; everything volatile (the receipt block, folded history rows, the
turn prompt) sits below it. The stable prefix is sha256-keyed over
(prompt-template version, its component texts, a user-rules version
reserved for that future surface) and LRU-memoized, so a skill edit
invalidates exactly the cache entries that must die and no more.
"""

from __future__ import annotations

import pytest

from halbert_core.prompts.agent_prompts import (
    CACHE_BOUNDARY_MARKER,
    PROMPT_TEMPLATE_VERSION,
    build_stable_prefix,
    stable_prefix_key,
)


class TestTheStablePrefix:

    def test_it_joins_its_parts_in_order(self):
        assert build_stable_prefix("id", "catalog", "skills") == (
            "id\n\ncatalog\n\nskills"
        )

    def test_empty_parts_are_skipped(self):
        assert build_stable_prefix("id", "", "") == "id"
        assert build_stable_prefix("", "catalog", "") == "catalog"

    def test_the_key_moves_when_any_input_moves(self):
        base = stable_prefix_key("id", "cat", "sk")
        assert stable_prefix_key("id2", "cat", "sk") != base
        assert stable_prefix_key("id", "cat2", "sk") != base
        assert stable_prefix_key("id", "cat", "sk2") != base

    def test_the_key_carries_the_template_version_and_user_rules(self):
        base = stable_prefix_key("id", "cat", "sk")
        assert stable_prefix_key(
            "id", "cat", "sk", user_rules_version="v2") != base
        # A bump to the template version must move the key without any
        # other input changing — that is the whole point of it being in
        # the key.
        import halbert_core.prompts.agent_prompts as mod
        real = mod.PROMPT_TEMPLATE_VERSION
        try:
            mod.PROMPT_TEMPLATE_VERSION = real + 1
            assert stable_prefix_key("id", "cat", "sk") != base
        finally:
            mod.PROMPT_TEMPLATE_VERSION = real

    def test_the_same_inputs_hit_the_memo(self):
        first = build_stable_prefix("identity", "catalog", "skills")
        second = build_stable_prefix("identity", "catalog", "skills")
        assert first is second, "the join is memoized on its key"

    def test_the_key_is_a_sha256_hex(self):
        assert len(stable_prefix_key("a", "b", "c")) == 64
        int(stable_prefix_key("a", "b", "c"), 16)  # hex digits only

    def test_the_boundary_marker_is_a_literal_line(self):
        assert CACHE_BOUNDARY_MARKER.startswith("<!--")
        assert CACHE_BOUNDARY_MARKER.endswith("-->")

    def test_the_template_version_is_declared(self):
        assert isinstance(PROMPT_TEMPLATE_VERSION, int)


# ── The state machine seam ───────────────────────────────────────────

def _machine(intake=None, pipeline=None, identity="I am this machine.",
             skills=""):
    from halbert_core.agents.state_machine import AgentStateMachine

    m = AgentStateMachine.__new__(AgentStateMachine)
    m._identity_block = lambda modality: identity
    m._composed_prompt_block = lambda: skills
    m._continuity_tail = lambda: ""
    m.intake = pipeline
    m.ctx = type("C", (), {
        "conversation_history": [], "thread_receipt_block": "",
        "defanged_query": None, "user_query": "", "model_override": None,
        "tier_override": None, "intake": intake,
    })()
    return m


class TestTheHeadAssembly:

    def test_identity_catalog_skills_then_the_marker_then_the_prompt(self, tmp_path):
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
        m = _machine(intake=intake, pipeline=pipeline,
                     skills="[Active Skill: storage-ops]")
        head = m._build_messages("Answer me.")[0]["content"]
        assert head.startswith("I am this machine.")
        assert head.index("I am this machine.") < head.index("<available_skills>")
        assert head.index("<available_skills>") < head.index("[Active Skill:")
        assert head.index("[Active Skill:") < head.index(CACHE_BOUNDARY_MARKER)
        assert head.index(CACHE_BOUNDARY_MARKER) < head.index("Answer me.")

    def test_the_catalog_lists_the_bundled_skills(self):
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
        intake = pipeline.analyze("hello")
        head = _machine(intake=intake, pipeline=pipeline)._build_messages("q")[0]["content"]
        assert "<name>storage-ops</name>" in head
        assert "</available_skills>" in head

    def test_without_a_registry_there_is_no_catalog_but_still_a_boundary(self):
        head = _machine()._build_messages("What time is it?")[0]["content"]
        assert "<available_skills>" not in head
        assert CACHE_BOUNDARY_MARKER in head

    def test_the_marker_appears_exactly_once(self):
        head = _machine()._build_messages("q")[0]["content"]
        assert head.count(CACHE_BOUNDARY_MARKER) == 1

    def test_a_catalog_failure_never_costs_the_turn(self, monkeypatch):
        def boom(registry, **kw):
            raise RuntimeError("catalog exploded")
        monkeypatch.setattr(
            "halbert_core.skills.catalog.render_available_skills", boom)
        m = _machine()
        assert m._catalog_block() == ""
        head = m._build_messages("q")[0]["content"]
        assert "q" in head


class TestTheIntakeRegistryProperty:

    def test_intake_exposes_the_matchers_registry(self):
        from halbert_core.intake.budget import get_context_budget
        from halbert_core.intake.pipeline import IntakePipeline
        from halbert_core.skills.matcher import SkillMatcher
        from halbert_core.skills.registry import SkillRegistry

        class R:
            def assess(self, message, signals):
                from halbert_core.intake.complexity import (
                    ComplexityLevel, ComplexityResult,
                )
                return ComplexityResult(
                    score=1, level=ComplexityLevel.SIMPLE,
                    reasoning="", cached=True)

        reg = SkillRegistry([])
        pipeline = IntakePipeline(
            complexity_router=R(), budget_fn=get_context_budget,
            model_config={"llm_config": {"chat_model": {"model": "c"}}},
            skill_matcher=SkillMatcher(reg),
        )
        assert pipeline.skill_registry is reg

    def test_without_a_matcher_the_registry_is_none(self):
        from halbert_core.intake.budget import get_context_budget
        from halbert_core.intake.pipeline import IntakePipeline

        class R:
            def assess(self, message, signals):
                from halbert_core.intake.complexity import (
                    ComplexityLevel, ComplexityResult,
                )
                return ComplexityResult(
                    score=1, level=ComplexityLevel.SIMPLE,
                    reasoning="", cached=True)

        pipeline = IntakePipeline(
            complexity_router=R(), budget_fn=get_context_budget,
            model_config={"llm_config": {"chat_model": {"model": "c"}}},
        )
        assert pipeline.skill_registry is None