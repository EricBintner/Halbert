# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Skill parsing, discovery, registry inheritance, and matching (Phase 1).

The matcher is the routing layer the role-scoped config work lacks: without
it, `scope_for_query()` can only return None/host/knowledge_<platform>, so
the shipped `*_admin` scopes are indexed and unreachable.
"""

from __future__ import annotations

import textwrap

import pytest

from halbert_core.intake.signals import analyze_message
from halbert_core.skills import (
    Skill,
    SkillMatcher,
    SkillParseError,
    SkillRegistry,
    canonical_scope_id,
    load_skills,
    parse_skill,
)


def _skill_md(**overrides) -> str:
    """A representative SKILL.md. Built without dedent: the nested `triggers`
    block has its own indentation, which dedent would flatten into bad YAML."""
    meta = {
        "name": "storage-ops",
        "description": "Disk, filesystem, ZFS",
        "domains": "[storage]",
        "keywords": "[zfs, smart]",
        "role": "storage-ops",
        "model": "specialist",
        "priority": "high",
    }
    meta.update(overrides)
    return (
        "---\n"
        f"name: {meta['name']}\n"
        f"description: {meta['description']}\n"
        "triggers:\n"
        f"  domains: {meta['domains']}\n"
        f"  keywords: {meta['keywords']}\n"
        f"role: {meta['role']}\n"
        f"model: {meta['model']}\n"
        f"priority: {meta['priority']}\n"
        "---\n"
        "\n"
        "You are Halbert's storage operations specialist.\n"
    )


# ── Parsing ───────────────────────────────────────────────────────────

def test_parses_frontmatter_and_body():
    s = parse_skill(_skill_md())
    assert s.name == "storage-ops"
    assert s.role == "storage-ops"
    assert s.model == "specialist"
    assert s.priority == "high"
    assert s.triggers.domains == ("storage",)
    assert s.triggers.keywords == ("zfs", "smart")
    assert "storage operations specialist" in s.prompt
    assert "---" not in s.prompt


def test_a_file_with_no_frontmatter_is_all_prompt():
    s = parse_skill("Just some expertise.", name="freeform")
    assert s.name == "freeform"
    assert s.prompt == "Just some expertise."
    assert s.model == "chat"


def test_legacy_orchestrator_tier_is_rejected():
    # models.yml SLOTS are chat/specialist/vision; orchestrator is a LEGACY_KEY.
    with pytest.raises(SkillParseError, match="orchestrator"):
        parse_skill(_skill_md(model="orchestrator"))


def test_explicit_provider_model_passes_through():
    s = parse_skill(_skill_md(model="ollama:qwen3-coder"))
    assert s.model == "ollama:qwen3-coder"


def test_unclosed_frontmatter_is_an_error():
    with pytest.raises(SkillParseError, match="never closed"):
        parse_skill("---\nname: x\nstill going")


def test_bad_priority_is_an_error():
    with pytest.raises(SkillParseError, match="priority"):
        parse_skill(_skill_md(priority="urgent"))


def test_a_nameless_skill_with_no_fallback_is_an_error():
    with pytest.raises(SkillParseError, match="no name"):
        parse_skill("---\ndescription: x\n---\nbody")


def test_scope_is_normalized_to_daemon_underscores_but_role_is_not():
    # A name a skill invents has no display_name mapping to save it, so a
    # hyphenated scope would silently widen to a global union.
    s = parse_skill(
        "---\nname: x\nscope: host-storage\nrole: storage-ops\n---\nbody"
    )
    assert s.scope == "host_storage"
    assert s.role == "storage-ops"
    assert canonical_scope_id("knowledge-linux") == "knowledge_linux"
    assert canonical_scope_id(None) is None


def test_safety_block_is_parsed():
    s = parse_skill(textwrap.dedent("""\
        ---
        name: storage-ops
        safety:
          destructive_requires_approval: true
          protected_paths: ["/boot", "/dev"]
          blocked_commands: ["mkfs*"]
        ---
        body
        """))
    assert s.safety.destructive_requires_approval is True
    assert s.safety.protected_paths == ("/boot", "/dev")
    assert s.safety.blocked_commands == ("mkfs*",)
    assert not s.safety.is_empty()


# ── Loading ───────────────────────────────────────────────────────────

def test_loads_both_layouts_and_later_dirs_override(tmp_path):
    builtin = tmp_path / "builtin"
    (builtin / "storage-ops").mkdir(parents=True)
    (builtin / "storage-ops" / "SKILL.md").write_text(_skill_md())

    user = tmp_path / "user"
    user.mkdir()
    # Bare <name>.md layout, same name -> replaces the built-in outright.
    (user / "storage-ops.md").write_text(_skill_md(priority="critical"))

    skills = load_skills(dirs=[builtin, user])
    assert set(skills) == {"storage-ops"}
    assert skills["storage-ops"].priority == "critical"


def test_one_broken_skill_does_not_lose_the_others(tmp_path):
    d = tmp_path / "skills"
    d.mkdir()
    (d / "good.md").write_text(_skill_md(name="good"))
    (d / "broken.md").write_text("---\nname: broken\npriority: nonsense\n---\nx")

    skills = load_skills(dirs=[d])
    assert set(skills) == {"good"}


def test_missing_directories_are_not_an_error(tmp_path):
    assert load_skills(dirs=[tmp_path / "nope"]) == {}


# ── Registry ──────────────────────────────────────────────────────────

def test_extends_unions_lists_and_child_wins_on_scalars():
    parent = parse_skill(textwrap.dedent("""\
        ---
        name: storage-ops
        triggers:
          domains: [storage]
        priority: normal
        model: specialist
        safety:
          protected_paths: ["/boot"]
          destructive_requires_approval: true
        ---
        Parent expertise.
        """))
    child = parse_skill(textwrap.dedent("""\
        ---
        name: zfs-ops
        extends: storage-ops
        triggers:
          keywords: [zpool]
        priority: critical
        safety:
          blocked_commands: ["zpool destroy"]
        ---
        Child expertise.
        """))
    reg = SkillRegistry([parent, child])
    zfs = reg.get("zfs-ops")

    assert zfs.triggers.domains == ("storage",)      # inherited
    assert zfs.triggers.keywords == ("zpool",)       # own
    assert zfs.priority == "critical"                # child wins
    assert zfs.model == "specialist"                 # inherited
    assert zfs.safety.protected_paths == ("/boot",)  # inherited
    assert zfs.safety.blocked_commands == ("zpool destroy",)
    # A parent's approval requirement cannot be dropped by a child.
    assert zfs.safety.destructive_requires_approval is True
    assert "Parent expertise." in zfs.prompt and "Child expertise." in zfs.prompt


def test_unknown_and_cyclic_extends_degrade_instead_of_raising():
    orphan = parse_skill("---\nname: orphan\nextends: ghost\n---\nbody")
    assert SkillRegistry([orphan]).get("orphan").extends is None

    a = parse_skill("---\nname: a\nextends: b\n---\nA")
    b = parse_skill("---\nname: b\nextends: a\n---\nB")
    reg = SkillRegistry([a, b])
    assert reg.get("a") is not None and reg.get("b") is not None


def test_registry_resolves_aliases():
    s = parse_skill("---\nname: storage-ops\naliases: [disk, zfs]\n---\nbody")
    reg = SkillRegistry([s])
    assert reg.get("disk").name == "storage-ops"
    assert reg.get("zfs").name == "storage-ops"
    assert reg.get("nope") is None
    assert "disk" in reg and len(reg) == 1


# ── Matching ──────────────────────────────────────────────────────────

def _matcher(*skills, **kw):
    kw.setdefault("host_platform", "linux")
    return SkillMatcher(SkillRegistry(skills), **kw)


def test_matches_on_the_domain_intake_already_detected():
    storage = parse_skill(_skill_md())
    m = _matcher(storage)
    msg = "why is my zfs pool degraded?"
    active = m.match(msg, analyze_message(msg))
    assert [a.name for a in active] == ["storage-ops"]
    assert active[0].matched_domains == ("storage",)
    assert "zfs" in active[0].matched_keywords


def test_an_unrelated_question_activates_nothing():
    m = _matcher(parse_skill(_skill_md()))
    msg = "what time is it?"
    assert m.match(msg, analyze_message(msg)) == []


def test_a_keyword_alone_is_below_threshold():
    # Conservative activation: real topical evidence, not one stray word.
    s = parse_skill(
        "---\nname: k\ntriggers:\n  keywords: [widget]\n---\nbody"
    )
    msg = "tell me about the widget"
    assert _matcher(s).match(msg, analyze_message(msg)) == []


def test_platform_restriction_excludes_at_any_score():
    mac_only = parse_skill(textwrap.dedent("""\
        ---
        name: macbook-dev
        triggers:
          domains: [storage]
          platform: [darwin]
        ---
        body
        """))
    msg = "my disk is full"
    assert _matcher(mac_only, host_platform="linux").match(msg, analyze_message(msg)) == []
    assert _matcher(mac_only, host_platform="darwin").match(msg, analyze_message(msg))


def test_intent_restriction_filters():
    cmd_only = parse_skill(textwrap.dedent("""\
        ---
        name: c
        triggers:
          domains: [storage]
          intent: [troubleshooting]
        ---
        body
        """))
    q = "what is a filesystem?"          # intent=question
    t = "my disk is broken and failing"  # intent=troubleshooting
    assert _matcher(cmd_only).match(q, analyze_message(q)) == []
    assert _matcher(cmd_only).match(t, analyze_message(t))


def test_active_skills_are_capped_and_ordered_by_score():
    made = [
        parse_skill(
            f"---\nname: s{i}\ntriggers:\n  domains: [storage]\n---\nbody"
        )
        for i in range(5)
    ]
    msg = "my disk is full"
    active = _matcher(*made, max_active=3).match(msg, analyze_message(msg))
    assert len(active) == 3
    assert [a.score for a in active] == sorted((a.score for a in active), reverse=True)


def test_priority_breaks_score_ties():
    low = parse_skill(
        "---\nname: a-low\ntriggers:\n  domains: [storage]\npriority: low\n---\nb"
    )
    high = parse_skill(
        "---\nname: z-high\ntriggers:\n  domains: [storage]\npriority: critical\n---\nb"
    )
    msg = "my disk is full"
    active = _matcher(low, high).match(msg, analyze_message(msg))
    # Equal scores, so the more urgent skill leads despite sorting later by name.
    assert active[0].name == "z-high"


def test_explicit_invocation_overrides_matching_entirely():
    storage = parse_skill(_skill_md())
    network = parse_skill(
        "---\nname: network-ops\ntriggers:\n  domains: [network]\n---\nbody"
    )
    m = _matcher(storage, network)
    msg = "why is my zfs pool degraded?"
    active = m.match(msg, analyze_message(msg), explicit=["network-ops"])
    assert [a.name for a in active] == ["network-ops"]
    assert active[0].explicit is True


def test_explicit_invocation_accepts_an_alias_and_skips_unknown():
    s = parse_skill("---\nname: storage-ops\naliases: [disk]\n---\nbody")
    active = _matcher(s).match("anything", None, explicit=["disk", "ghost"])
    assert [a.name for a in active] == ["storage-ops"]


def test_matcher_tolerates_missing_intake():
    assert _matcher(parse_skill(_skill_md())).match("my disk is full", None) == []


def test_skill_with_no_triggers_never_auto_activates():
    s = parse_skill("---\nname: manual-only\n---\nbody")
    msg = "my disk is full and zfs is broken"
    assert _matcher(s).match(msg, analyze_message(msg)) == []
    # ...but is still reachable explicitly.
    assert _matcher(s).match(msg, None, explicit=["manual-only"])


# ── Intake wiring ─────────────────────────────────────────────────────

def _pipeline(skill_matcher=None):
    """An IntakePipeline with a stubbed complexity LLM, as test_intake_pipeline
    builds one."""
    from unittest.mock import MagicMock

    from halbert_core.intake.budget import get_context_budget
    from halbert_core.intake.complexity import ComplexityRouter
    from halbert_core.intake.pipeline import IntakePipeline

    llm = MagicMock(return_value={"response": "3"})
    router = ComplexityRouter(llm, "guide-model", "http://localhost:11434")
    return IntakePipeline(
        router, get_context_budget, {}, skill_matcher=skill_matcher
    )


def test_intake_carries_active_skills_when_a_matcher_is_wired():
    pipeline = _pipeline(_matcher(parse_skill(_skill_md())))

    intake = pipeline.analyze("why is my zfs pool degraded?")
    assert intake.active_skill_names == ["storage-ops"]

    # Explicit invocation flows through intake too.
    intake = pipeline.analyze("anything at all", explicit_skills=["storage-ops"])
    assert intake.active_skill_names == ["storage-ops"]


def test_intake_without_a_matcher_behaves_exactly_as_before():
    pipeline = _pipeline()
    intake = pipeline.analyze("why is my zfs pool degraded?")
    assert intake.active_skills == []
    assert intake.detected_domains  # the rest of intake is untouched


def test_a_failing_matcher_does_not_fail_the_turn():
    class _Exploding:
        def match(self, *a, **kw):
            raise RuntimeError("boom")

    pipeline = _pipeline(_Exploding())
    intake = pipeline.analyze("my disk is full")
    assert intake.active_skills == []
    assert intake.intent  # turn still analysed
