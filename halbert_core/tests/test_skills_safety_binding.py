# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""B3: a skill's declared safety actually binds.

DEFECT-1's third break: `ToolSafetyFramework.set_skill_safety()` is called
only from tests, so declared skill safety never binds in production. With B2
landed, `storage-ops` now tells the model about ZFS operations in depth while
its own `protected_paths` and `destructive_requires_approval` do nothing --
which is the pairing the plan warned against.

Two pre-existing defects in the classifier itself are fixed here, both
measured before the fix:

- `rm grub.cfg` with `cwd=/boot` classified MEDIUM with no confirmation,
  while `cd /boot && rm grub.cfg` was HIGH. Same operation; the classifier
  only ever read `command` and `path`. This is the channel 44fc501e closed
  for the base classifier, still open on the skill one.
- `man mkfs` classified CRITICAL and was blocked outright, because the
  substring fallback matched `mkfs` anywhere in the string.
"""

import pytest

from halbert_core.skills.composer import compose
from halbert_core.skills.loader import BUILTIN_DIR, load_skills
from halbert_core.tools.safety import RiskLevel, ToolSafetyFramework


@pytest.fixture
def framework():
    f = ToolSafetyFramework()
    f.set_skill_safety(compose([load_skills([BUILTIN_DIR])["storage-ops"]]).safety)
    return f


class TestTheCwdChannel:

    def test_cwd_into_a_protected_path_requires_confirmation(self, framework):
        r = framework.classify("run_command", {"command": "rm grub.cfg", "cwd": "/boot"})
        assert r.requires_confirmation
        assert r.risk_level == RiskLevel.HIGH

    def test_the_inline_form_is_still_caught(self, framework):
        r = framework.classify("run_command", {"command": "cd /boot && rm grub.cfg"})
        assert r.requires_confirmation

    def test_an_unprotected_cwd_is_not_elevated(self, framework):
        r = framework.classify("run_command", {"command": "ls", "cwd": "/tmp"})
        assert not r.requires_confirmation


class TestTheSubstringFallbackIsAnchored:

    @pytest.mark.parametrize("command", [
        "man mkfs",
        "echo mkfs is dangerous",
        "grep mkfs /var/log/syslog",
    ])
    def test_merely_naming_a_blocked_command_is_not_blocked(self, framework, command):
        r = framework.classify("run_command", {"command": command})
        assert r.allowed, f"{command!r} only mentions the command; it does not run it"

    @pytest.mark.parametrize("command", [
        "man mkfs",
        "which mkfs.ext4",
        "echo mkfs is dangerous",
        "grep mkfs /var/log/syslog",
    ])
    def test_the_skill_pass_itself_declines_all_of_these(self, framework, command):
        """Asserted against `_check_skill_safety` directly, not the whole
        classifier, because the *base* classifier blocks `which mkfs.ext4`
        on its own `mkfs\.` regex -- the same unanchored matching, one level
        down, with a far wider blast radius to change. That is recorded as a
        separate finding; B3 owns the skill pass, and the skill pass is what
        this asserts.
        """
        assert framework._check_skill_safety("run_command", {"command": command}) is None

    @pytest.mark.parametrize("command", [
        "mkfs.ext4 /dev/sda1",
        "sudo mkfs.ext4 /dev/sda1",
        "/sbin/mkfs.ext4 /dev/sda1",
        "zpool destroy tank",
        "sudo zpool destroy tank",
    ])
    def test_actually_running_it_is_still_blocked(self, framework, command):
        r = framework.classify("run_command", {"command": command})
        assert not r.allowed
        assert r.risk_level == RiskLevel.CRITICAL

    def test_a_blocked_command_later_in_a_chain_is_still_caught(self, framework):
        r = framework.classify("run_command",
                               {"command": "cd /tmp && mkfs.ext4 /dev/sda1"})
        assert not r.allowed


class TestSafetyOnlyEverRaisesRisk:
    """Lenses invariant 6: skills compose upward only."""

    def test_clearing_returns_the_baseline(self, framework):
        blocked = framework.classify("run_command", {"command": "zpool destroy tank"})
        assert not blocked.allowed
        framework.set_skill_safety(None)
        after = framework.classify("run_command", {"command": "zpool destroy tank"})
        assert after.allowed, "the next turn must not inherit this turn's skill"

    def test_a_skill_cannot_lower_a_baseline_classification(self, framework):
        # rm -rf / is CRITICAL from the base classifier; no skill declares it,
        # so the skill pass must not be able to hand it back as safe.
        r = framework.classify("run_command", {"command": "rm -rf /"})
        assert r.risk_level == RiskLevel.CRITICAL


class TestThePerTurnLifecycle:
    """`set_skill_safety` is a bare attribute assignment whose own docstring
    says skills are per-turn -- and nothing cleared it. A skill left installed
    would classify the next turn, on a framework shared for the process.
    """

    def _machine(self, matches):
        from halbert_core.agents.state_machine import AgentStateMachine

        m = AgentStateMachine.__new__(AgentStateMachine)
        m.tools = type("T", (), {"safety": ToolSafetyFramework()})()
        m.ctx = type("C", (), {"intake": type("I", (), {"active_skills": matches})()})()
        return m

    def _storage_match(self):
        from halbert_core.skills.matcher import SkillMatch

        return [SkillMatch(skill=load_skills([BUILTIN_DIR])["storage-ops"], score=9)]

    def test_installing_binds_the_skills_rules(self):
        m = self._machine(self._storage_match())
        assert m.tools.safety.classify(
            "run_command", {"command": "zpool destroy tank"}).allowed
        m._install_skill_safety()
        assert not m.tools.safety.classify(
            "run_command", {"command": "zpool destroy tank"}).allowed

    def test_clearing_returns_to_baseline(self):
        m = self._machine(self._storage_match())
        m._install_skill_safety()
        m._clear_skill_safety()
        assert m.tools.safety.classify(
            "run_command", {"command": "zpool destroy tank"}).allowed, (
            "the next turn inherited this turn's skill"
        )

    def test_a_turn_with_no_skills_clears_any_stale_rules(self):
        m = self._machine(self._storage_match())
        m._install_skill_safety()
        m.ctx.intake.active_skills = []
        m._install_skill_safety()
        assert m.tools.safety.classify(
            "run_command", {"command": "zpool destroy tank"}).allowed

    def test_it_binds_the_executors_framework_not_a_new_one(self):
        m = self._machine(self._storage_match())
        before = m.tools.safety
        m._install_skill_safety()
        assert m.tools.safety is before, (
            "RoleGate wraps this instance; a different one enforces nothing"
        )

    def test_installing_never_raises(self):
        m = self._machine(self._storage_match())
        m.ctx.intake = None
        m._install_skill_safety()   # must not raise
        m.tools = None
        m._install_skill_safety()
        m._clear_skill_safety()
