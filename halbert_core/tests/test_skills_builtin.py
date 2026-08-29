# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The six built-in skills, and the routing they produce (Phase 3)."""

from __future__ import annotations

import pytest

from halbert_core.intake.signals import analyze_message
from halbert_core.skills import SkillMatcher, SkillRegistry
from halbert_core.skills.composer import compose_matches
from halbert_core.skills.loader import BUILTIN_DIR, load_skills

EXPECTED = {
    "storage-ops", "service-ops", "network-ops",
    "security-ops", "config-ops", "discovery-ops",
    "home-ops", "frigate-ops",
}


@pytest.fixture(scope="module")
def builtins():
    return load_skills(dirs=[BUILTIN_DIR])


@pytest.fixture
def matcher(builtins):
    return SkillMatcher(SkillRegistry(builtins.values()), host_platform="linux")


def _route(matcher, message):
    matches = matcher.match(message, analyze_message(message))
    return [m.name for m in matches], compose_matches(matches)


# ── The set itself ────────────────────────────────────────────────────

def test_all_six_builtins_parse(builtins):
    assert set(builtins) == EXPECTED


def test_every_builtin_declares_a_role_and_a_prompt(builtins):
    for name, skill in builtins.items():
        assert skill.role, f"{name} has no role to resolve against a scope"
        assert len(skill.prompt) > 200, f"{name} has no substantive expertise"
        assert skill.description, f"{name} has no description"


def test_roles_are_unique_because_the_daemon_requires_it(builtins):
    # SourcePrep enforces one assigned_to_role per project, so two skills
    # cannot share a role.
    roles = [s.role for s in builtins.values()]
    assert len(roles) == len(set(roles))


def test_builtin_tiers_are_current_slot_names(builtins):
    for name, skill in builtins.items():
        assert skill.model in ("chat", "specialist", "vision"), name


# ── Routing ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("message,expected_lead", [
    ("why is my zfs pool degraded?", "storage-ops"),
    ("my disk is full and I can't figure out why", "storage-ops"),
    ("nginx keeps returning 502 after the cert renewal", "service-ops"),
    ("dns isn't resolving on this machine", "network-ops"),
    ("what's my sshd_config PermitRootLogin set to?", "security-ops"),
    ("what do I have installed on here?", "discovery-ops"),
])
def test_representative_questions_reach_the_right_specialist(
    matcher, message, expected_lead
):
    names, _ = _route(matcher, message)
    assert names and names[0] == expected_lead, f"{message} -> {names}"


def test_a_greeting_activates_nothing(matcher):
    names, composed = _route(matcher, "hello there")
    assert names == [] and composed.is_empty


def test_storage_question_routes_to_the_storage_role_and_a_specialist(matcher):
    _, composed = _route(matcher, "why is my zfs pool degraded?")
    assert composed.role == "storage-ops"
    assert composed.model == "specialist"
    # Deep analysis asked for more retrieval than the default.
    assert composed.budget_appetite.get("retrieval", 1.0) > 1.0


def test_security_outranks_config_on_an_sshd_question(matcher):
    # Both fire on "sshd_config"; security-ops is critical priority and leads,
    # so its safety constraints and tier govern the turn.
    names, composed = _route(matcher, "what's my sshd_config PermitRootLogin set to?")
    assert set(names) >= {"security-ops", "config-ops"}
    assert names[0] == "security-ops"
    assert "/etc/ssh" in composed.safety.protected_paths


def test_discovery_does_not_activate_on_specific_domain_questions(matcher):
    # An inventory skill claiming every domain would spend a slot on every
    # turn; it is keyword-driven instead.
    for message in ("why is my zfs pool degraded?", "dns isn't resolving on this machine"):
        names, _ = _route(matcher, message)
        assert "discovery-ops" not in names, message


# ── Boundary matching ─────────────────────────────────────────────────

def test_underscored_identifiers_are_detected():
    # "_" is a word character, so \bconfig\b misses "sshd_config" — exactly
    # the identifier the keyword exists to catch.
    assert "config" in analyze_message("what's in sshd_config?").detected_domains
    assert "security" in analyze_message("check sshd_config").detected_domains
    assert "service" in analyze_message("look at nginx.conf").detected_domains


def test_a_keyword_still_does_not_match_inside_a_longer_word():
    # Letters must still bound, or "ssh" fires on "sshd" and every near-miss.
    assert "security" not in analyze_message("the sshsomething thing").detected_domains
    assert "network" not in analyze_message("a description of things").detected_domains


def test_safety_of_the_composed_builtins_is_most_restrictive(matcher):
    _, composed = _route(matcher, "why is my zfs pool degraded?")
    assert composed.safety.destructive_requires_approval is True
    assert any("mkfs" in c for c in composed.safety.blocked_commands)


# ── Role provisioning through setup ───────────────────────────────────

def test_setup_sends_assigned_to_role_when_the_template_declares_it():
    """A template role must reach the daemon, or every skill declaring it
    silently falls back to the parent scope."""
    from halbert_core.integrations.sourceprep_setup import SourcePrepSetup

    calls = []

    class _Setup(SourcePrepSetup):
        def __init__(self):  # bypass the real client wiring
            pass

        def _list_scopes(self, pid):
            return []

        def _call(self, method, path, body=None):
            calls.append((method, path, body))
            return {"id": "storage_admin", "pipeline_profile": "system_config"}

    _Setup()._reconcile_scopes("p", [{
        "id": "storage_admin",
        "paths": ["host/etc/fstab"],
        "pipeline_profile": "system_config",
        "assigned_to_role": "storage-ops",
    }])

    created = [b for m, p, b in calls if m == "POST" and p.endswith("/scopes")]
    assert created and created[0]["assigned_to_role"] == "storage-ops"


def test_setup_warns_when_a_role_does_not_persist():
    from halbert_core.integrations.sourceprep_setup import SourcePrepSetup

    class _Setup(SourcePrepSetup):
        def __init__(self):
            pass

        def _list_scopes(self, pid):
            # Daemon accepted the create but dropped the role.
            return [{"display_name": "storage_admin", "id": "storage_admin",
                     "assigned_to_role": None, "paths": ["host/etc/fstab"]}]

        def _call(self, method, path, body=None):
            return {"id": "storage_admin"}

    outcomes = _Setup()._reconcile_scopes("p", [{
        "id": "storage_admin",
        "paths": ["host/etc/fstab"],
        "assigned_to_role": "storage-ops",
    }])
    assert "_role_warning" in outcomes
