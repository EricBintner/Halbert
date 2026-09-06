# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""B1: the matcher reaches the running daemon.

DEFECT-1 is that `IntakePipeline` is constructed with no `skill_matcher`, so
`active_skills` is always empty and every downstream consumer no-ops -- eight
written expert skills, matched by nothing.

Wiring the matcher alone changes live behaviour before any prompt exists,
because three consumers read the result: the skill's model tier picks the
specialist slot, its budget appetite reshuffles `ContextBudget`, and its role
and knowledge scope narrow SourcePrep retrieval. Those are asserted here, not
assumed, because they land the moment this does.
"""

import pytest

from halbert_core.intake.pipeline import IntakePipeline
from halbert_core.skills.loader import daemon_skill_dirs
from halbert_core.skills.matcher import SkillMatcher
from halbert_core.skills.registry import SkillRegistry


@pytest.fixture
def matcher():
    return SkillMatcher(SkillRegistry.from_disk(dirs=daemon_skill_dirs()))


class _StubRouter:
    """A fixed score, so the only thing varying between cases is the matcher.

    Score 2 on purpose: `normalised = score / 5.0` is compared against
    `routing.complexity_threshold` (0.5), so 3 or above reaches the specialist
    slot on complexity alone and the skill's own tier preference would be
    invisible behind it. At 2 the baseline is the guide slot, so the skill is
    the only thing that can move it.
    """

    def __init__(self, score=2):
        self._score = score

    def assess(self, message, signals):
        from halbert_core.intake.complexity import ComplexityLevel, ComplexityResult
        return ComplexityResult(score=self._score, level=ComplexityLevel.SIMPLE,
                                reasoning="stub", cached=True)


def _pipeline(matcher=None, score=2):
    from halbert_core.intake.budget import get_context_budget
    return IntakePipeline(
        complexity_router=_StubRouter(score),
        budget_fn=get_context_budget,
        model_config={"llm_config": {
            "chat_model": {"model": "chat-m"},
            "specialist_model": {"enabled": True, "model": "specialist-m"},
        }},
        skill_matcher=matcher,
    )


class TestTheMatcherActivatesASkill:

    def test_a_storage_question_activates_storage_ops(self, matcher):
        intake = _pipeline(matcher).analyze(
            "my zpool is degraded, which disk should I replace?"
        )
        assert "storage-ops" in [s.name for s in intake.active_skills]

    def test_without_a_matcher_nothing_activates(self):
        intake = _pipeline(None).analyze(
            "my zpool is degraded, which disk should I replace?"
        )
        assert intake.active_skills == []

    def test_an_unrelated_question_activates_nothing(self, matcher):
        intake = _pipeline(matcher).analyze("what time is it?")
        assert intake.active_skills == []


class TestTheThreeEffectsThatGoLiveWithIt:
    """Each of these is a behaviour change carried by B1 alone."""

    ZPOOL = "my zpool is degraded, which disk should I replace?"

    def test_a_skill_declaring_the_specialist_tier_routes_there(self, matcher):
        intake = _pipeline(matcher).analyze(self.ZPOOL)
        assert intake.recommended_model == "specialist", (
            "storage-ops declares model: specialist; wiring the matcher moves "
            "this turn off the chat slot"
        )

    def test_the_same_question_stays_on_guide_without_the_matcher(self):
        intake = _pipeline(None).analyze(self.ZPOOL)
        assert intake.recommended_model == "guide"

    def test_the_budget_appetite_reaches_the_composer(self, matcher):
        # storage-ops declares budget_multiplier: 1.6. The reshuffle itself
        # happens in ContextAssembler (assembler.py:257), not here -- intake's
        # own budget comes from the model name. What B1 carries is the
        # appetite reaching a non-empty ComposedSkills at all.
        from halbert_core.skills.composer import compose_matches

        intake = _pipeline(matcher).analyze(self.ZPOOL)
        composed = compose_matches(intake.active_skills)
        assert composed is not None
        assert composed.budget_appetite, (
            "the appetite is what ContextAssembler reallocates from"
        )

    def test_the_reallocation_bids_within_the_same_total(self, matcher):
        # Skills bid for a share, never a bigger window -- ContextBudget's
        # fields sum to `total`, so a multiplier that grew the total would
        # overrun the tier.
        from halbert_core.skills.composer import compose_matches, reallocate_budget

        intake = _pipeline(matcher).analyze(self.ZPOOL)
        composed = compose_matches(intake.active_skills)
        before = intake.context_budget
        after = reallocate_budget(before, composed.budget_appetite)
        assert after is not None
        assert after.total == before.total
        assert after.retrieval > before.retrieval, (
            "storage-ops bids 1.6 for retrieval depth"
        )

    def test_the_skill_role_is_carried_for_retrieval_scoping(self, matcher):
        intake = _pipeline(matcher).analyze(self.ZPOOL)
        match = [m for m in intake.active_skills if m.name == "storage-ops"][0]
        assert match.skill.role == "storage-ops", (
            "ContextAssembler scopes SourcePrep retrieval by the skill role"
        )


class TestTheRouteWiresIt:
    """The defect is a construction site, so assert on the construction site."""

    def test_the_agent_route_builds_a_matcher_from_the_daemon_dirs(self):
        import inspect
        from halbert_core.dashboard.routes import agent as route

        src = inspect.getsource(route)
        assert "SkillMatcher" in src, "routes/agent.py must construct a matcher"
        assert "daemon_skill_dirs" in src, (
            "it must use the trusted list, never default_skill_dirs, which "
            "reads Path.cwd()"
        )
        assert "skill_matcher=" in src, "and pass it to IntakePipeline"
