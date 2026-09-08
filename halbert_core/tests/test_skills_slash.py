# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SK-2: the slash channel in intake (design §2.4).

A `/<name>` at the head of a message addresses a skill: intake parses the
leading tokens and routes them to the matcher's explicit path, which
overrides trigger matching entirely. Reserved names — the client-side
slash commands SK-1 encoded, and the tool names — never route to a skill:
a user typing `/model` means the command, and the refusal at load already
guarantees no skill ever claimed that name. The dashboard's slash
affordance is D-1's question; the intake-level channel lands regardless.
"""

from __future__ import annotations

import pytest

from halbert_core.intake.pipeline import IntakePipeline, parse_slash_skills


def _router(score=1):
    from halbert_core.intake.complexity import ComplexityLevel, ComplexityResult

    class R:
        def assess(self, message, signals):
            return ComplexityResult(score=score, level=ComplexityLevel.SIMPLE,
                                    reasoning="", cached=True)
    return R()


def _pipeline(matcher):
    from halbert_core.intake.budget import get_context_budget
    return IntakePipeline(
        complexity_router=_router(),
        budget_fn=get_context_budget,
        model_config={"llm_config": {"chat_model": {"model": "c"}}},
        skill_matcher=matcher,
    )


def _matcher():
    from halbert_core.skills.loader import daemon_skill_dirs
    from halbert_core.skills.matcher import SkillMatcher
    from halbert_core.skills.registry import SkillRegistry
    return SkillMatcher(SkillRegistry.from_disk(dirs=daemon_skill_dirs()))


class TestParsing:

    def test_a_leading_slash_token_names_a_skill(self):
        assert parse_slash_skills("/storage-ops check my pool") == ["storage-ops"]

    def test_the_message_can_be_only_the_invocation(self):
        assert parse_slash_skills("/storage-ops") == ["storage-ops"]

    def test_several_leading_tokens_all_route(self):
        assert parse_slash_skills("/storage-ops /network-ops why") == [
            "storage-ops", "network-ops"]

    def test_leading_whitespace_is_fine(self):
        assert parse_slash_skills("  /storage-ops  hi") == ["storage-ops"]

    def test_a_slash_mid_message_is_not_a_channel(self):
        assert parse_slash_skills("check /etc/hosts for me") == []
        assert parse_slash_skills("look at /storage-ops") == []

    def test_a_path_shaped_token_is_not_a_skill_name(self):
        assert parse_slash_skills("/etc/hosts check") == []

    def test_the_run_ends_at_the_first_non_token(self):
        assert parse_slash_skills("hi /storage-ops") == []

    @pytest.mark.parametrize("reserved", [
        "/model", "/explain", "/fix", "/dryrun", "/read_file",
    ])
    def test_reserved_names_never_route_to_a_skill(self, reserved):
        """SK-1 refused these names at load; the channel refuses them at
        parse, so the reserved set cannot drift into a skill route."""
        assert parse_slash_skills(f"{reserved} and then some") == []

    def test_an_unknown_skill_still_parses(self):
        """Resolution is the matcher's job: it warns on a name no skill
        answers to, and the turn proceeds. The parser only decides what
        the user addressed."""
        assert parse_slash_skills("/no-such-skill help") == ["no-such-skill"]

    def test_uppercase_is_not_the_channel(self):
        assert parse_slash_skills("/Storage-Ops help") == []


class TestRoutingThroughTheMatcher:

    def test_a_slash_invocation_activates_the_skill_explicitly(self):
        intake = _pipeline(_matcher()).analyze("/storage-ops check the pool")
        assert "storage-ops" in intake.active_skill_names
        assert all(m.explicit for m in intake.active_skills)

    def test_a_slash_invocation_overrides_trigger_matching(self):
        """`/storage-ops` runs storage-ops and nothing else (design §12
        Q2), even when the words would have matched several skills."""
        intake = _pipeline(_matcher()).analyze("/storage-ops nginx is down")
        assert intake.active_skill_names == ["storage-ops"]

    def test_a_plain_message_still_matches_by_trigger(self):
        intake = _pipeline(_matcher()).analyze("my zpool is degraded")
        assert "storage-ops" in intake.active_skill_names
        assert not any(m.explicit for m in intake.active_skills)

    def test_the_explicit_parameter_still_works_alongside(self):
        matcher = _matcher()
        intake = _pipeline(matcher).analyze(
            "/storage-ops check the pool",
            explicit_skills=["network-ops"],
        )
        assert "network-ops" in intake.active_skill_names
        assert "storage-ops" in intake.active_skill_names

    def test_a_reserved_command_message_is_just_a_message(self):
        intake = _pipeline(_matcher()).analyze("/model which slot is pinned")
        assert intake.active_skills == []

    def test_without_a_matcher_a_slash_message_still_analyzes(self):
        intake = _pipeline(None).analyze("/storage-ops check the pool")
        assert intake.active_skills == []
        assert intake.intent  # the pipeline ran to completion

    def test_a_slash_invocation_still_records_an_explicit_receipt(
            self, monkeypatch):
        """The activation seam stamps `explicit` for a slash invocation —
        the event the design's row names, not just trigger matches."""
        rows = []
        monkeypatch.setattr(
            "halbert_core.skills.telemetry.record_skill_event",
            lambda skill_id, event, **kw: rows.append((skill_id, event))
            or True)
        matcher = _matcher()
        intake = _pipeline(matcher).analyze("/storage-ops check the pool")
        from halbert_core.agents.state_machine import AgentStateMachine

        m = AgentStateMachine.__new__(AgentStateMachine)
        m.ctx = type("C", (), {
            "intake": intake, "session_id": "s", "request_id": "r"})()
        m._record_skill_activation()
        assert [(i, e) for i, e in rows] == [
            (matcher.registry.get("storage-ops").id, "explicit")]