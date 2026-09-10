# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-11 Phase E, second half: the CC flags, colon-rich descriptions,
`extends`, and one rule written down.

- **A13-G9**: ``disable-model-invocation`` and ``user-invocable`` are the
  two flags an ingested pack uses to say "this is a slash command, not
  something to volunteer" and "this is machinery, do not offer it to a
  person". Halbert tolerated them as unknown top-level keys and offered
  every skill to both.
- **A13-G11**: a description with a colon in it (``Frigate NVR: camera
  streams``) is a YAML parse error, and the whole skill vanished over a
  punctuation mark in prose. The origin recovers that ONE line and only
  that one line (`frontmatter.ts:83-126`).
- **A13 bug 9**: ``extends`` cannot say "use the default" — the merge reads
  a child's default-valued field as "unset" and takes the parent's — and it
  REPLACES ``requires`` where every other restriction unions.
- **A13-G12**: the prompt-cache boundary is a recorded string, never a
  marker searched for in text. No consumer splits on it today; the rule is
  written down and pinned so none starts.
"""
from __future__ import annotations

import pytest

from halbert_core.skills.parser import SkillParseError, parse_skill
from halbert_core.skills.registry import SkillRegistry


def _parse(meta_lines, body="Body."):
    return parse_skill("---\n" + "\n".join(meta_lines) + "\n---\n" + body)


# ---------------------------------------------------------------------------
# A13-G9 — the two invocation flags
# ---------------------------------------------------------------------------

class TestInvocationFlags:
    def test_both_default_to_open(self):
        skill = _parse(["name: disk-ops", "description: d"])
        assert skill.model_invocable is True
        assert skill.user_invocable is True

    def test_disable_model_invocation_is_read(self):
        skill = _parse(["name: disk-ops", "description: d",
                        "disable-model-invocation: true"])
        assert skill.model_invocable is False
        assert skill.user_invocable is True

    def test_user_invocable_false_is_read(self):
        skill = _parse(["name: disk-ops", "description: d",
                        "user-invocable: false"])
        assert skill.user_invocable is False
        assert skill.model_invocable is True

    def test_the_underscore_spelling_reads_too(self):
        skill = _parse(["name: disk-ops", "description: d",
                        "disable_model_invocation: true"])
        assert skill.model_invocable is False

    def test_a_non_boolean_is_refused_rather_than_guessed(self):
        with pytest.raises(SkillParseError):
            _parse(["name: disk-ops", "description: d",
                    "user-invocable: maybe"])


class TestTheFlagsAreHonoured:
    def _registry(self, skills):
        return SkillRegistry(skills)

    def _matcher(self, skills):
        """``min_score=1`` on purpose: a keyword-only trigger scores 2 and
        the production floor is 3, so a matcher at the default would
        return [] for every skill here and these tests would pass without
        testing anything."""
        from halbert_core.skills.matcher import SkillMatcher

        return SkillMatcher(self._registry(skills), min_score=1)

    def _listed(self, tmp_path, skill):
        from halbert_core.skills.catalog import render_available_skills

        return render_available_skills(self._registry([skill]))

    def test_a_model_disabled_skill_is_not_in_the_catalog(self, tmp_path):
        src = tmp_path / "d" / "SKILL.md"
        src.parent.mkdir()
        src.write_text("body")
        skill = parse_skill(
            "---\nname: disk-ops\ndescription: d\n"
            "disable-model-invocation: true\n---\nBody.", source_path=src)
        assert "disk-ops" not in self._listed(tmp_path, skill)

    def test_a_model_disabled_skill_is_not_matched(self):
        skill = _parse(["name: disk-ops", "description: d",
                        "disable-model-invocation: true",
                        "halbert:", "  triggers:", "    keywords: ['zpool']"])
        assert self._matcher([skill]).match("check zpool status") == []

    def test_but_the_user_can_still_invoke_it_by_name(self):
        """That is the whole point of the flag: a slash command, not
        something the model volunteers."""
        skill = _parse(["name: disk-ops", "description: d",
                        "disable-model-invocation: true"])
        assert [m.name for m in
                self._matcher([skill]).match("", explicit=["disk-ops"])] == ["disk-ops"]

    def test_a_user_disabled_skill_refuses_an_explicit_name(self):
        skill = _parse(["name: internal-ops", "description: d",
                        "user-invocable: false"])
        assert self._matcher([skill]).match("", explicit=["internal-ops"]) == []

    def test_but_the_model_may_still_match_it(self):
        skill = _parse(["name: internal-ops", "description: d",
                        "user-invocable: false",
                        "halbert:", "  triggers:", "    keywords: ['zpool']"])
        assert [m.name for m in
                self._matcher([skill]).match("check zpool status")] == ["internal-ops"]


# ---------------------------------------------------------------------------
# A13-G11 — one line recovered, and only one
# ---------------------------------------------------------------------------

class TestColonRichDescriptions:
    def test_a_colon_in_a_description_no_longer_loses_the_skill(self):
        skill = _parse(["name: frigate-ops",
                        "description: Frigate NVR: camera streams and MQTT"])
        assert skill.description == "Frigate NVR: camera streams and MQTT"

    def test_the_rest_of_the_frontmatter_survives_the_recovery(self):
        skill = _parse(["name: frigate-ops",
                        "description: Frigate NVR: cameras",
                        "halbert:", "  kind: ops", "  priority: high"])
        assert skill.priority == "high"
        assert skill.kind == "ops"

    def test_only_description_is_recovered(self):
        """The origin recovers the freeform text field and nothing else: a
        broken ``triggers`` block is a broken routing rule, and guessing at
        one is how a skill activates on the wrong turn."""
        with pytest.raises(SkillParseError):
            _parse(["name: x", "description: d",
                    "halbert:", "  role: storage: ops"])

    def test_a_quoted_description_is_untouched(self):
        skill = _parse(["name: x", 'description: "Already: quoted"'])
        assert skill.description == "Already: quoted"

    def test_a_block_scalar_description_is_not_rewritten(self):
        skill = _parse(["name: x", "description: |", "  Line one.",
                        "  Line two."])
        assert "Line one." in skill.description

    def test_frontmatter_that_is_broken_some_other_way_still_refuses(self):
        with pytest.raises(SkillParseError):
            _parse(["name: x", "description: d", "\tbad: indentation: here"])


# ---------------------------------------------------------------------------
# A13 bug 9 — extends
# ---------------------------------------------------------------------------

class TestExtends:
    def _pair(self, child_lines, parent_lines):
        parent = _parse(["name: base", "description: d"] + parent_lines)
        child = _parse(["name: child", "description: d",
                        "halbert:", "  extends: base"] + child_lines)
        return SkillRegistry([parent, child]).get("child")

    def test_a_child_inherits_what_it_does_not_declare(self):
        child = self._pair([], ["halbert:", "  priority: high"])
        assert child.priority == "high"

    def test_a_child_can_declare_the_default_back(self):
        """The bug: the merge read a child's default-valued field as
        "unset" and handed back the parent's, so a skill could inherit a
        `priority: critical` it explicitly wrote `normal` to escape."""
        parent = _parse(["name: base", "description: d",
                         "halbert:", "  priority: critical"])
        child = _parse(["name: child", "description: d",
                        "halbert:", "  extends: base", "  priority: normal"])
        assert SkillRegistry([parent, child]).get("child").priority == "normal"

    def test_requires_unions_rather_than_replacing(self):
        """Every other restriction in this merge unions in the
        most-restrictive direction -- a parent's protected path cannot be
        dropped by a child. ``requires`` was the one that replaced, so a
        child could shed the parent's ``bins`` clause by declaring its own,
        and inherit a body that assumes both."""
        parent = _parse(["name: base", "description: d",
                         "halbert:", "  requires:", "    bins: ['zpool']"])
        child = _parse(["name: child", "description: d",
                        "halbert:", "  extends: base",
                        "  requires:", "    bins: ['smbd']"])
        merged = SkillRegistry([parent, child]).get("child")
        assert set(merged.requires.bins) == {"zpool", "smbd"}

    def test_a_child_with_no_requires_inherits_the_parents(self):
        parent = _parse(["name: base", "description: d",
                         "halbert:", "  requires:", "    bins: ['zpool']"])
        child = _parse(["name: child", "description: d",
                        "halbert:", "  extends: base"])
        merged = SkillRegistry([parent, child]).get("child")
        assert set(merged.requires.bins) == {"zpool"}

    def test_the_os_clause_unions_too(self):
        parent = _parse(["name: base", "description: d",
                         "halbert:", "  requires:", "    os: ['linux']"])
        child = _parse(["name: child", "description: d",
                        "halbert:", "  extends: base",
                        "  requires:", "    os: ['darwin']"])
        merged = SkillRegistry([parent, child]).get("child")
        assert set(merged.requires.os) == {"linux", "darwin"}


# ---------------------------------------------------------------------------
# A13-G12 — the rule, written down
# ---------------------------------------------------------------------------

def test_nothing_splits_the_prompt_on_the_cache_boundary_marker():
    """The boundary is a length recorded at construction, never a marker
    searched for in text (Hermes ``skill_commands.py:60-73``: "single
    construction site guarantees the prefix is a byte-prefix"). A consumer
    that split a rendered prompt on the marker would be forgeable by any
    skill body that contained it -- and this is the one repo-wide rule the
    audit could only ask for as prevention, because no such consumer
    exists yet.
    """
    import pathlib
    import re

    from halbert_core.prompts.agent_prompts import CACHE_BOUNDARY_MARKER

    root = pathlib.Path(__file__).resolve().parents[1] / "halbert_core"
    offenders = []
    call = re.compile(
        r"\.(?:split|rsplit|partition|rpartition|index|find)\s*\(\s*"
        r"(?:CACHE_BOUNDARY_MARKER|[\"']" + re.escape(CACHE_BOUNDARY_MARKER)
        + r"[\"'])")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if call.search(text):
            offenders.append(str(path.relative_to(root)))
    assert offenders == [], (
        "these split a prompt on the cache-boundary marker; the boundary is "
        f"a recorded length, not a delimiter: {offenders}")
