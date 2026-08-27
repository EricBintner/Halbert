# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Composition, budget reallocation, safety compilation, and scope routing
for co-active skills (Phase 2)."""

from __future__ import annotations

import asyncio

import pytest

from halbert_core.intake.budget import get_context_budget
from halbert_core.skills.composer import (
    ADJUSTABLE_CATEGORIES,
    MAX_BUDGET_CAP,
    compose,
    merge_allowed_tools,
    reallocate_budget,
)
from halbert_core.skills.parser import parse_skill
from halbert_core.tools.safety import RiskLevel, ToolSafetyFramework


def _skill(name, **fields):
    lines = ["---", f"name: {name}"]
    for key, value in fields.items():
        if key == "body":
            continue
        lines.append(f"{key}: {value}")
    lines += ["---", fields.get("body", f"{name} expertise.")]
    return parse_skill("\n".join(lines))


# ── Prompt merging ────────────────────────────────────────────────────

def test_prompts_concatenate_under_labelled_headers():
    c = compose([_skill("storage-ops"), _skill("service-ops")])
    assert "[Active Skill: storage-ops]" in c.prompt
    assert "[Active Skill: service-ops]" in c.prompt
    assert c.prompt.index("storage-ops") < c.prompt.index("service-ops")


def test_a_prompt_less_skill_contributes_no_header():
    c = compose([_skill("quiet", body=""), _skill("loud")])
    assert "[Active Skill: quiet]" not in c.prompt
    assert "[Active Skill: loud]" in c.prompt


def test_composing_nothing_is_empty_not_an_error():
    c = compose([])
    assert c.is_empty and c.prompt == "" and c.model is None


# ── Ordering, scope, model ────────────────────────────────────────────

def test_priority_decides_the_lead_skill():
    low = _skill("a-normal", priority="normal", scope="host", model="chat")
    high = _skill("z-critical", priority="critical", scope="host_security",
                  model="specialist")
    c = compose([low, high])
    assert c.names[0] == "z-critical"
    assert c.scope == "host_security"
    assert c.model == "specialist"


def test_scope_falls_to_the_lead_because_retrieval_takes_only_one():
    # SourcePrep's context endpoint takes a single scope string; a union of
    # two skills' scopes is not expressible, so v1 picks one.
    c = compose([
        _skill("lead", priority="high", scope="storage_admin"),
        _skill("other", priority="normal", scope="network_admin"),
    ])
    assert c.scope == "storage_admin"


def test_role_is_preferred_and_survives_composition():
    c = compose([_skill("storage-ops", role="storage-ops", priority="high")])
    assert c.role == "storage-ops"


def test_equal_priority_breaks_to_the_more_capable_tier():
    c = compose([
        _skill("a", priority="high", model="chat"),
        _skill("b", priority="high", model="specialist"),
    ])
    assert c.model == "specialist"


# ── Safety ────────────────────────────────────────────────────────────

def test_safety_is_most_restrictive_and_cannot_be_relaxed():
    strict = parse_skill(
        "---\nname: storage-ops\nsafety:\n"
        "  destructive_requires_approval: true\n"
        '  protected_paths: ["/boot"]\n'
        '  blocked_commands: ["mkfs*"]\n---\nbody'
    )
    loose = parse_skill(
        "---\nname: service-ops\nsafety:\n"
        "  destructive_requires_approval: false\n"
        '  protected_paths: ["/etc/systemd/"]\n---\nbody'
    )
    c = compose([strict, loose])
    # false cannot cancel true
    assert c.safety.destructive_requires_approval is True
    assert set(c.safety.protected_paths) == {"/boot", "/etc/systemd/"}
    assert c.safety.blocked_commands == ("mkfs*",)


def test_allowed_tools_intersect_and_no_restriction_does_not_widen():
    a = parse_skill('---\nname: a\nallowed_tools: [exec, read]\n---\nb')
    b = parse_skill('---\nname: b\nallowed_tools: [read, write]\n---\nb')
    unrestricted = _skill("c")
    assert merge_allowed_tools([a, b]) == ("read",)
    # A skill that does not restrict tools contributes no restriction.
    assert merge_allowed_tools([a, unrestricted]) == ("exec", "read")
    assert merge_allowed_tools([unrestricted]) is None


# ── Budget ────────────────────────────────────────────────────────────

def test_appetite_takes_the_max_not_the_mean():
    # Averaging 1.8 with an incidental 1.0 would dilute the deep specialist.
    c = compose([
        _skill("deep", budget_multiplier=1.8),
        _skill("incidental", budget_multiplier=1.0),
    ])
    assert c.budget_appetite["retrieval"] == pytest.approx(1.8)


def test_appetite_is_capped():
    c = compose([_skill("greedy", budget_multiplier=9.0)])
    assert c.budget_appetite["retrieval"] == MAX_BUDGET_CAP


def test_no_appetite_when_nobody_bids_above_one():
    assert compose([_skill("plain")]).budget_appetite == {}


def test_reallocation_preserves_the_sum_to_total_invariant():
    base = get_context_budget("example-specialist:32b")
    before = sum(getattr(base, c) for c in ADJUSTABLE_CATEGORIES)

    after = reallocate_budget(base, {"retrieval": 1.8, "discovery": 1.8})

    assert sum(getattr(after, c) for c in ADJUSTABLE_CATEGORIES) == before
    assert after.total == base.total
    # Retrieval genuinely deepened, and it came from the other categories.
    assert after.retrieval > base.retrieval


def test_reallocation_never_touches_the_protected_categories():
    base = get_context_budget("example-specialist:32b")
    after = reallocate_budget(base, {"retrieval": 2.0})
    assert after.system_identity == base.system_identity
    assert after.user_rules == base.user_rules


def test_reallocation_is_a_noop_without_appetite():
    base = get_context_budget("example-specialist:32b")
    assert reallocate_budget(base, {}) is base
    assert reallocate_budget(None, {"retrieval": 2.0}) is None


# ── Safety compilation into the existing framework ────────────────────

def test_blocked_command_from_a_skill_is_critical_and_denied():
    fw = ToolSafetyFramework()
    fw.set_skill_safety(compose([parse_skill(
        '---\nname: zfs-ops\nsafety:\n  blocked_commands: ["zpool destroy*"]\n---\nb'
    )]).safety)

    result = fw.classify("run_command", {"command": "zpool destroy tank"})
    assert result.risk_level is RiskLevel.CRITICAL
    assert result.allowed is False
    assert "zfs-ops" or "Blocked" in result.reason


def test_protected_path_from_a_skill_requires_confirmation():
    fw = ToolSafetyFramework()
    fw.set_skill_safety(compose([parse_skill(
        "---\nname: storage-ops\nsafety:\n"
        "  destructive_requires_approval: true\n"
        '  protected_paths: ["/boot"]\n---\nb'
    )]).safety)

    result = fw.classify("write_file", {"path": "/boot/grub/grub.cfg"})
    assert result.requires_confirmation is True
    assert result.risk_level is RiskLevel.HIGH


def test_a_skill_cannot_make_a_built_in_critical_command_safe():
    fw = ToolSafetyFramework()
    baseline = fw.classify("run_command", {"command": "rm -rf /"})
    fw.set_skill_safety(compose([_skill("permissive")]).safety)
    after = fw.classify("run_command", {"command": "rm -rf /"})
    # Skills only tighten; the built-in classification still stands.
    assert after.risk_level == baseline.risk_level
    assert after.allowed == baseline.allowed


def test_clearing_skill_safety_restores_baseline():
    fw = ToolSafetyFramework()
    fw.set_skill_safety(compose([parse_skill(
        '---\nname: x\nsafety:\n  blocked_commands: ["ls*"]\n---\nb'
    )]).safety)
    assert fw.classify("run_command", {"command": "ls /tmp"}).allowed is False

    fw.set_skill_safety(None)
    assert fw.classify("run_command", {"command": "ls /tmp"}).allowed is True


# ── Scope routing through the adapter ─────────────────────────────────

class _Backend:
    def __init__(self, roles=None):
        self._roles = roles or {}
        self.calls = []

    def resolve_role(self, role):
        return self._roles.get(role)

    def search(self, query, k=5, figure_id=None):
        self.calls.append(figure_id)
        return [{"text": "t", "source_path": "p", "score": 1.0}]


def _adapter(backend):
    from halbert_core.context.adapters import SourcePrepAdapter
    return SourcePrepAdapter(backend=backend)


def test_a_skill_role_reaches_the_role_scope():
    # The whole point: scope_for_query() can never return storage_admin.
    backend = _Backend(roles={"storage-ops": "storage_admin"})
    asyncio.run(_adapter(backend).search("why is my pool degraded", role="storage-ops"))
    assert backend.calls == ["storage_admin"]


def test_an_unassigned_role_falls_back_to_the_heuristic():
    backend = _Backend(roles={})
    asyncio.run(_adapter(backend).search("what's my sshd_config set to?", role="storage-ops"))
    # Not None, and not the role — the host-cue heuristic took over.
    assert backend.calls == ["host"]


def test_an_explicit_skill_scope_overrides_the_heuristic():
    backend = _Backend()
    asyncio.run(_adapter(backend).search("anything at all", scope="network_admin"))
    assert backend.calls == ["network_admin"]


# ── End to end through ContextAssembler ───────────────────────────────

class _ScopedRetrieval:
    """A retrieval source that records the scope it was asked for."""

    def __init__(self):
        self.scopes = []
        self.roles = []

    async def search(self, query, limit=5, *, scope=None, role=None):
        self.scopes.append(scope)
        self.roles.append(role)
        return [{"content": "pool is degraded", "source": "host/etc/zfs", "score": 1.0}]


class _UnscopedRetrieval:
    """An older source that takes no scope keywords at all."""

    def __init__(self):
        self.calls = 0

    async def search(self, query, limit=5):
        self.calls += 1
        return [{"content": "x", "source": "s", "score": 1.0}]


def _assembler(retrieval):
    from halbert_core.context.assembler import ContextAssembler
    return ContextAssembler(retrieval_service=retrieval)


def _intake(message="why is my zfs pool degraded?"):
    from unittest.mock import MagicMock

    from halbert_core.intake.complexity import ComplexityRouter
    from halbert_core.intake.pipeline import IntakePipeline

    router = ComplexityRouter(MagicMock(return_value={"response": "3"}),
                              "guide-model", "http://localhost:11434")
    return IntakePipeline(router, get_context_budget, {}).analyze(message)


def test_assemble_routes_retrieval_through_the_active_skill_role():
    retrieval = _ScopedRetrieval()
    composed = compose([_skill("storage-ops", role="storage-ops", priority="high")])

    asyncio.run(_assembler(retrieval).assemble(
        "why is my zfs pool degraded?", intake=_intake(), active_skills=composed
    ))
    assert retrieval.roles == ["storage-ops"]


def test_assemble_accepts_raw_matcher_output_too():
    from halbert_core.skills import SkillMatcher, SkillRegistry

    retrieval = _ScopedRetrieval()
    skill = _skill("storage-ops", role="storage-ops")
    matcher = SkillMatcher(SkillRegistry([parse_skill(
        "---\nname: storage-ops\nrole: storage-ops\n"
        "triggers:\n  domains: [storage]\n---\nbody"
    )]), host_platform="linux")
    matches = matcher.match("why is my zfs pool degraded?", _intake())
    assert matches  # sanity: the matcher fired

    asyncio.run(_assembler(retrieval).assemble(
        "why is my zfs pool degraded?", intake=_intake(), active_skills=matches
    ))
    assert retrieval.roles == ["storage-ops"]


def test_assemble_falls_back_when_the_source_takes_no_scope():
    # An older retrieval source must not lose retrieval just because a skill
    # is active.
    retrieval = _UnscopedRetrieval()
    composed = compose([_skill("storage-ops", role="storage-ops")])
    result = asyncio.run(_assembler(retrieval).assemble(
        "why is my zfs pool degraded?", intake=_intake(), active_skills=composed
    ))
    assert retrieval.calls == 1
    assert result is not None


def test_assemble_without_skills_is_unchanged():
    retrieval = _ScopedRetrieval()
    asyncio.run(_assembler(retrieval).assemble(
        "why is my zfs pool degraded?", intake=_intake()
    ))
    assert retrieval.roles == [None] and retrieval.scopes == [None]


# ── Model tier from active skills ─────────────────────────────────────

_MODELS = {
    "llm_config": {
        "chat_model": {"enabled": True, "endpoint_id": "ep", "model": "guide:14b"},
        "specialist_model": {"enabled": True, "endpoint_id": "ep", "model": "deep:32b"},
        "vision_model": {"enabled": False, "endpoint_id": "", "model": ""},
    },
    "routing": {"complexity_threshold": 3},
}

_NO_SPECIALIST = {
    "llm_config": {
        **_MODELS["llm_config"],
        "specialist_model": {"enabled": False, "endpoint_id": "", "model": ""},
    },
    "routing": {"complexity_threshold": 3},
}


def _tier_pipeline(skill_md, config=_MODELS, score=1):
    from unittest.mock import MagicMock

    from halbert_core.intake.complexity import ComplexityRouter
    from halbert_core.intake.pipeline import IntakePipeline
    from halbert_core.skills import SkillMatcher, SkillRegistry

    matcher = SkillMatcher(
        SkillRegistry([parse_skill(skill_md)]), host_platform="linux"
    )
    router = ComplexityRouter(MagicMock(return_value={"response": str(score)}),
                              "guide-model", "http://localhost:11434")
    return IntakePipeline(router, get_context_budget, config, skill_matcher=matcher)


_STORAGE_SPECIALIST = (
    "---\nname: storage-ops\nmodel: specialist\n"
    "triggers:\n  domains: [storage]\n---\nbody"
)


def test_an_active_skill_can_pull_a_simple_query_to_the_specialist():
    # Complexity 1 is well under the threshold; the skill is what escalates.
    intake = _tier_pipeline(_STORAGE_SPECIALIST).analyze("my disk is full")
    assert intake.active_skill_names == ["storage-ops"]
    assert intake.recommended_model == "specialist"


def test_a_skill_cannot_route_to_a_slot_the_user_never_configured():
    intake = _tier_pipeline(
        _STORAGE_SPECIALIST, config=_NO_SPECIALIST
    ).analyze("my disk is full")
    assert intake.recommended_model == "guide"


def test_a_chat_tier_skill_does_not_block_complexity_escalation_for_others():
    # The skill asks for chat and gets it, even though complexity is high.
    intake = _tier_pipeline(
        "---\nname: quick\nmodel: chat\ntriggers:\n  domains: [storage]\n---\nb",
        score=5,
    ).analyze("my disk is full")
    assert intake.recommended_model == "guide"


def test_no_active_skill_leaves_routing_exactly_as_it_was():
    from unittest.mock import MagicMock

    from halbert_core.intake.complexity import ComplexityRouter
    from halbert_core.intake.pipeline import IntakePipeline

    # A networking question: the storage skill must not activate, so routing
    # has to land wherever a matcher-less pipeline would have put it.
    message = "the connection keeps refusing on port 443"

    with_skills = _tier_pipeline(_STORAGE_SPECIALIST, score=5).analyze(message)
    router = ComplexityRouter(MagicMock(return_value={"response": "5"}),
                              "guide-model", "http://localhost:11434")
    without = IntakePipeline(router, get_context_budget, _MODELS).analyze(message)

    assert with_skills.active_skills == []
    assert with_skills.recommended_model == without.recommended_model
