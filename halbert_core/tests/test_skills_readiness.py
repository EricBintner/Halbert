# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-11 Phase E: the gates a skill declares, finally consulted.

- **A13-G6**: ``requires`` is parsed and the docstring says so outright --
  "parsed, not evaluated. Evaluation is SK-4's". Nothing evaluates it, so a
  skill declaring ``bins: [zpool]`` binds its body into the prompt on a
  machine with no ZFS and tells the model to run commands that do not
  exist. The origin gates on it before a skill is eligible at all
  (`config-eval.ts:79-149`).
- **A13-G10**: an explicit ``/name`` resolves the skill and ignores every
  filter -- including the platform one the matcher applies on the scored
  path. Hermes refuses an unsupported skill even by name
  (`skills_tool.py:549-554`), and it is right to: a macOS runbook typed on
  a Linux host is not a preference, it is wrong.
- and the operator disable list that goes with it: a way to take one skill
  out of play without deleting a file someone else's pack owns.

- **A13 bug 3**: ``skill_for_path`` attributes a file to a skill by asking
  whether the skill's source PARENT is in the path's parents. For a
  bare-layout skill (``~/.config/halbert/skills/foo.md``) that parent is
  the ROOT, so every skill file in the root -- and every file under every
  sibling skill's directory -- reads back as ``foo``. Ties fell to
  insertion order.
"""
from __future__ import annotations

import sys

import pytest

from halbert_core.skills.parser import parse_skill
from halbert_core.skills.readiness import (
    Readiness,
    disabled_skill_names,
    evaluate_readiness,
    reset_skills_config_cache,
)
from halbert_core.skills.registry import SkillRegistry


def _skill(name="disk-ops", *, requires=None, source=None, platform=None):
    meta = [f"name: {name}", "description: d", "halbert:", "  kind: ops",
            "  state: trusted"]
    if requires:
        meta.append("  requires:")
        for key, value in requires.items():
            meta.append(f"    {key}: {list(value)}")
    if platform:
        meta.append("  triggers:")
        meta.append(f"    platform: {list(platform)}")
    return parse_skill("---\n" + "\n".join(meta) + "\n---\nBody.",
                       source_path=source)


@pytest.fixture(autouse=True)
def _clean_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    reset_skills_config_cache()
    yield
    reset_skills_config_cache()


# ---------------------------------------------------------------------------
# A13-G6 — requires, evaluated
# ---------------------------------------------------------------------------

class TestRequiresIsEvaluated:
    def test_a_skill_with_no_requires_is_ready(self):
        assert evaluate_readiness(_skill()) is Readiness.READY

    def test_a_missing_binary_makes_it_unavailable(self):
        skill = _skill(requires={"bins": ["definitely-not-a-real-binary"]})
        assert evaluate_readiness(skill) is Readiness.MISSING

    def test_a_present_binary_is_ready(self):
        skill = _skill(requires={"bins": ["sh"]})
        assert evaluate_readiness(skill) is Readiness.READY

    def test_bins_is_all_of(self):
        skill = _skill(requires={"bins": ["sh", "definitely-not-a-real-binary"]})
        assert evaluate_readiness(skill) is Readiness.MISSING

    def test_any_bins_is_any_of(self):
        skill = _skill(
            requires={"anyBins": ["definitely-not-a-real-binary", "sh"]})
        assert evaluate_readiness(skill) is Readiness.READY

    def test_any_bins_with_none_present_is_missing(self):
        skill = _skill(requires={"anyBins": ["nope-a", "nope-b"]})
        assert evaluate_readiness(skill) is Readiness.MISSING

    def test_env_is_presence_never_value(self, monkeypatch):
        skill = _skill(requires={"env": ["HALBERT_TEST_TOKEN"]})
        assert evaluate_readiness(skill) is Readiness.MISSING
        monkeypatch.setenv("HALBERT_TEST_TOKEN", "")
        assert evaluate_readiness(skill) is Readiness.READY, (
            "presence, not truthiness -- the value is never read")

    def test_the_os_gate_is_unsupported_not_missing(self):
        """A different answer because it is a different fact: a missing
        binary can be installed; a macOS runbook on Linux cannot."""
        other = "linux" if sys.platform == "darwin" else "darwin"
        assert evaluate_readiness(
            _skill(requires={"os": [other]})) is Readiness.UNSUPPORTED

    def test_this_host_passes_its_own_os_gate(self):
        from halbert_core.skills.matcher import current_platform

        assert evaluate_readiness(
            _skill(requires={"os": [current_platform()]})) is Readiness.READY

    def test_the_os_gate_is_checked_before_the_rest(self):
        """The origin's order (`config-eval.ts:126-149`): an unsupported
        skill reports UNSUPPORTED even when a binary is missing too, so the
        operator is told the thing they cannot fix."""
        other = "linux" if sys.platform == "darwin" else "darwin"
        skill = _skill(requires={"os": [other], "bins": ["nope"]})
        assert evaluate_readiness(skill) is Readiness.UNSUPPORTED

    def test_a_capability_key_is_consulted(self):
        skill = _skill(requires={"config": ["CAP_DEFINITELY_NOT_A_CAPABILITY"]})
        assert evaluate_readiness(skill) is Readiness.MISSING

    def test_the_triggers_platform_gate_still_applies(self):
        other = "linux" if sys.platform == "darwin" else "darwin"
        assert evaluate_readiness(
            _skill(platform=[other])) is Readiness.UNSUPPORTED


# ---------------------------------------------------------------------------
# A13-G10 — the operator disable list, and /name that respects the gates
# ---------------------------------------------------------------------------

class TestTheDisableList:
    def _config(self, tmp_path, text):
        path = tmp_path / "data" / "skills_config.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        reset_skills_config_cache()
        return path

    def test_nothing_is_disabled_without_a_config(self):
        assert disabled_skill_names() == frozenset()

    def test_a_named_skill_is_disabled(self, tmp_path):
        self._config(tmp_path, "disabled:\n  - frigate-ops\n")
        assert "frigate-ops" in disabled_skill_names()
        assert evaluate_readiness(_skill("frigate-ops")) is Readiness.DISABLED

    def test_a_platform_scoped_disable(self, tmp_path):
        from halbert_core.skills.matcher import current_platform

        self._config(
            tmp_path,
            f"disabled_by_platform:\n  {current_platform()}:\n    - home-ops\n")
        assert evaluate_readiness(_skill("home-ops")) is Readiness.DISABLED
        assert evaluate_readiness(_skill("disk-ops")) is Readiness.READY

    def test_another_platforms_disable_does_not_apply_here(self, tmp_path):
        other = "linux" if sys.platform == "darwin" else "darwin"
        self._config(tmp_path,
                     f"disabled_by_platform:\n  {other}:\n    - home-ops\n")
        assert evaluate_readiness(_skill("home-ops")) is Readiness.READY

    def test_a_malformed_config_disables_nothing_and_does_not_raise(self, tmp_path):
        self._config(tmp_path, "disabled: not-a-list\n[[[")
        assert disabled_skill_names() == frozenset()

    def test_the_config_is_reread_when_it_changes(self, tmp_path):
        self._config(tmp_path, "disabled: []\n")
        assert disabled_skill_names() == frozenset()
        import os
        path = self._config(tmp_path, "disabled:\n  - frigate-ops\n")
        os.utime(path, ns=(10 ** 18, 10 ** 18))
        assert "frigate-ops" in disabled_skill_names()


class TestTheMatcherHonoursReadiness:
    def _matcher(self, skills):
        """``min_score=1``: a keyword-only trigger scores 2 against a
        production floor of 3, so a default matcher answers [] for these
        fixtures whatever the gate does."""
        from halbert_core.skills.matcher import SkillMatcher

        return SkillMatcher(SkillRegistry(skills), min_score=1)

    def test_an_explicit_name_no_longer_bypasses_the_platform_gate(self):
        other = "linux" if sys.platform == "darwin" else "darwin"
        matcher = self._matcher([_skill("mac-ops", platform=[other])])
        assert matcher.match("", explicit=["mac-ops"]) == []

    def test_an_explicit_name_respects_the_disable_list(self, tmp_path):
        path = tmp_path / "data" / "skills_config.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("disabled:\n  - disk-ops\n")
        reset_skills_config_cache()
        matcher = self._matcher([_skill("disk-ops")])
        assert matcher.match("", explicit=["disk-ops"]) == []

    def test_an_explicit_name_still_works_for_a_ready_skill(self):
        matcher = self._matcher([_skill("disk-ops")])
        assert [m.name for m in matcher.match("", explicit=["disk-ops"])] == ["disk-ops"]

    def test_a_missing_requirement_keeps_a_skill_out_of_the_scored_path(self):
        def _zfs(bins):
            return parse_skill(
                "---\nname: zfs-ops\ndescription: d\nhalbert:\n  kind: ops\n"
                f"  state: trusted\n  requires:\n    bins: {bins}\n"
                "  triggers:\n    keywords: ['zpool']\n---\nBody.")

        # Present: it matches, so the fixture is known to be matchable...
        assert [m.name for m in
                self._matcher([_zfs(["sh"])]).match("check zpool status")] == ["zfs-ops"]
        # ...and absent, the gate is what removes it.
        assert self._matcher(
            [_zfs(["definitely-not-real"])]).match("check zpool status") == []


# ---------------------------------------------------------------------------
# A13 bug 3 — a bare-layout skill does not own the whole root
# ---------------------------------------------------------------------------

class TestSkillForPath:
    def _bare(self, root, name):
        path = root / f"{name}.md"
        path.write_text("body")
        return _skill(name, source=path)

    def test_a_bare_skill_owns_only_its_own_file(self, tmp_path):
        root = tmp_path / "skills"
        root.mkdir()
        registry = SkillRegistry([self._bare(root, "aaa"),
                                  self._bare(root, "zzz")])
        assert registry.skill_for_path(root / "aaa.md").name == "aaa"
        assert registry.skill_for_path(root / "zzz.md").name == "zzz"

    def test_a_bare_skill_does_not_claim_a_sibling(self, tmp_path):
        root = tmp_path / "skills"
        root.mkdir()
        (root / "notes.txt").write_text("not a skill")
        registry = SkillRegistry([self._bare(root, "aaa")])
        assert registry.skill_for_path(root / "notes.txt") is None

    def test_a_directory_skill_still_owns_its_references(self, tmp_path):
        d = tmp_path / "skills" / "disk-ops"
        (d / "references").mkdir(parents=True)
        src = d / "SKILL.md"
        src.write_text("body")
        ref = d / "references" / "zfs.md"
        ref.write_text("body")
        registry = SkillRegistry([_skill("disk-ops", source=src)])
        assert registry.skill_for_path(ref).name == "disk-ops"

    def test_the_deepest_containing_skill_wins(self, tmp_path):
        """Two skills, one nested inside the other's tree: the answer is
        the one whose directory actually holds the file, not whichever
        happened to be inserted first."""
        outer = tmp_path / "pack"
        inner = outer / "nested"
        inner.mkdir(parents=True)
        (outer / "SKILL.md").write_text("body")
        (inner / "SKILL.md").write_text("body")
        probe = inner / "references.md"
        probe.write_text("body")
        registry = SkillRegistry([
            _skill("zzz-outer", source=outer / "SKILL.md"),
            _skill("aaa-inner", source=inner / "SKILL.md"),
        ])
        assert registry.skill_for_path(probe).name == "aaa-inner"

    def test_an_exact_hit_still_wins_over_containment(self, tmp_path):
        d = tmp_path / "skills" / "disk-ops"
        d.mkdir(parents=True)
        src = d / "SKILL.md"
        src.write_text("body")
        registry = SkillRegistry([_skill("disk-ops", source=src)])
        assert registry.skill_for_path(src).name == "disk-ops"

    def test_a_file_under_no_skill_is_nobodys(self, tmp_path):
        d = tmp_path / "skills" / "disk-ops"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("body")
        elsewhere = tmp_path / "etc" / "samba" / "smb.conf"
        elsewhere.parent.mkdir(parents=True)
        elsewhere.write_text("x")
        registry = SkillRegistry([_skill("disk-ops", source=d / "SKILL.md")])
        assert registry.skill_for_path(elsewhere) is None


# ---------------------------------------------------------------------------
# A13 bug 4 — a receipt for a read that happened
# ---------------------------------------------------------------------------

class TestTheReadReceiptFollowsTheRead:
    """``record_skill_read`` was called ABOVE the existence, type and size
    checks, so a read that raised minted a receipt for a consultation that
    never happened -- and the curator's whole question is which skills the
    model actually consulted. A typo'd ``<location>``, a deleted skill
    directory and an over-cap reference file each recorded one."""

    def _read(self, path):
        import asyncio

        from halbert_core.tools import ToolExecutor, ToolSafetyFramework

        executor = ToolExecutor(safety=ToolSafetyFramework())
        return asyncio.run(executor._read_file({"path": str(path)}))

    def test_a_missing_file_records_nothing(self, tmp_path, monkeypatch):
        seen = []
        monkeypatch.setattr(
            "halbert_core.skills.telemetry.record_skill_read", seen.append)
        with pytest.raises(FileNotFoundError):
            self._read(tmp_path / "nope.md")
        assert seen == []

    def test_a_directory_records_nothing(self, tmp_path, monkeypatch):
        seen = []
        monkeypatch.setattr(
            "halbert_core.skills.telemetry.record_skill_read", seen.append)
        with pytest.raises(ValueError):
            self._read(tmp_path)
        assert seen == []

    def test_an_over_cap_file_records_nothing(self, tmp_path, monkeypatch):
        seen = []
        monkeypatch.setattr(
            "halbert_core.skills.telemetry.record_skill_read", seen.append)
        big = tmp_path / "big.md"
        big.write_text("x" * (1024 * 1024 + 1))
        with pytest.raises(ValueError):
            self._read(big)
        assert seen == []

    def test_a_read_that_succeeds_still_records(self, tmp_path, monkeypatch):
        seen = []
        monkeypatch.setattr(
            "halbert_core.skills.telemetry.record_skill_read", seen.append)
        good = tmp_path / "SKILL.md"
        good.write_text("body")
        assert self._read(good) == "body"
        assert seen == [str(good)]
