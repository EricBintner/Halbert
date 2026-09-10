# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-11 Phase C: the catalog says what to do with itself, and stays bounded.

- **A13-G3** (the audit's "cheapest high-leverage" row): the block listed
  nine skills and never said what a skill is for. Track B — progressive
  disclosure — works only if the model already guesses the convention:
  scan the list, read the one that matches, obey it. OpenClaw states that
  above the block in so many words (`system-prompt.ts:255-275`); Halbert
  shipped the list alone and hoped.
- **A13-G4**: a description is bounded at parse (4096) and clamped by the
  ladder only once the block is already over budget. Under budget, rung 0
  renders every description in full — so one ingested pack entry with a
  4000-character description IS the catalog, and the eight skills that
  actually run this machine get pushed off it.
- **A13 bug 7**: the truncation notice tells the operator to audit with
  ``halbert skills list``. There is no such command — no CLI module, no
  dashboard route. The one line whose entire job is honesty was the line
  that was not true.
"""
from __future__ import annotations

import logging

import pytest

from halbert_core.skills.catalog import (
    CATALOG_BUDGET_CHARS,
    MAX_RENDERED_DESCRIPTION_CHARS,
    SKILLS_GUIDANCE,
    catalog_block_only,
    descriptions_over_limit,
    render_available_skills,
)
from halbert_core.skills.parser import DESCRIPTION_LIMIT, parse_skill
from halbert_core.skills.registry import SkillRegistry


def _skill(name, description="", *, source=None, priority="normal"):
    meta = (f"name: {name}\ndescription: {description}\n"
            f"halbert:\n  kind: ops\n  state: trusted\n"
            f"  priority: {priority}\n")
    return parse_skill(f"---\n{meta}---\nExpertise.", source_path=source)


def _with_paths(tmp_path, count, *, description="Runbook text"):
    out = []
    for i in range(count):
        d = tmp_path / f"skill-{i:02d}"
        d.mkdir(exist_ok=True)
        (d / "SKILL.md").write_text("body")
        out.append(_skill(f"skill-{i:02d}", description,
                          source=d / "SKILL.md"))
    return out


# ---------------------------------------------------------------------------
# A13-G3 — the consultation instruction
# ---------------------------------------------------------------------------

class TestTheCatalogSaysWhatToDoWithItself:
    def test_the_guidance_rides_above_the_block(self, tmp_path):
        catalog = render_available_skills(_registry := SkillRegistry(
            _with_paths(tmp_path, 2)))
        assert catalog.startswith(SKILLS_GUIDANCE)
        assert "<available_skills>" in catalog

    def test_the_guidance_names_the_read_tool_and_forbids_invented_paths(self):
        assert "read_file" in SKILLS_GUIDANCE
        assert "<location>" in SKILLS_GUIDANCE
        # The failure mode that costs a turn: a plausible path that is not
        # in the block.
        assert "invent" in SKILLS_GUIDANCE.lower()

    def test_the_guidance_covers_none_and_several(self):
        low = SKILLS_GUIDANCE.lower()
        assert "most specific" in low
        assert "none" in low

    def test_an_empty_catalog_carries_no_guidance_either(self):
        """Instructions for a list that is not there are noise in every
        prompt on a host with no skills."""
        assert render_available_skills(SkillRegistry([])) == ""

    def test_the_ecosystem_block_is_still_byte_for_byte_the_pack_shape(self, tmp_path):
        """The ingest contract: a pack that works elsewhere works here.

        The guidance is Halbert's own framing and sits OUTSIDE the block —
        exactly where the origin puts it — so the element itself is
        unchanged.
        """
        d = tmp_path / "zfs-snapshot-rollback"
        d.mkdir()
        src = d / "SKILL.md"
        src.write_text("body")
        reg = SkillRegistry([
            _skill("zfs-snapshot-rollback",
                   "Roll back a ZFS dataset to a named snapshot safely",
                   source=src)])
        assert catalog_block_only(render_available_skills(reg)) == (
            "<available_skills>\n"
            "<skill>\n"
            "<name>zfs-snapshot-rollback</name>\n"
            "<description>Roll back a ZFS dataset to a named snapshot safely</description>\n"
            f"<location>{src}</location>\n"
            "</skill>\n"
            "</available_skills>"
        )

    def test_the_guidance_survives_every_rung_of_the_ladder(self, tmp_path):
        """It is the identity floor's neighbour: a catalog nobody was told
        how to use is the defect this row is about, at any budget."""
        reg = SkillRegistry(_with_paths(tmp_path, 6, description="D" * 100))
        for budget in (300, 200, 120, 40):
            assert render_available_skills(reg, budget=budget).startswith(
                SKILLS_GUIDANCE)

    def test_the_guidance_is_paid_for_out_of_the_budget(self, tmp_path):
        """Not an unmeasured extra bolted on after the ladder decided it
        had fitted — that is how a budget stops meaning anything."""
        reg = SkillRegistry(_with_paths(tmp_path, 8, description="D" * 200))
        for budget in (600, 900, 1500):
            assert len(render_available_skills(reg, budget=budget)) <= budget


# ---------------------------------------------------------------------------
# A13-G4 — one entry cannot be the catalog
# ---------------------------------------------------------------------------

class TestNoOneEntryOwnsTheCatalog:
    def test_a_huge_description_is_clamped_even_when_it_would_fit(self, tmp_path):
        """Rung 0 is where this bites: under budget the ladder never runs,
        so a 4000-char description used to render in full."""
        d = tmp_path / "greedy"
        d.mkdir()
        (d / "SKILL.md").write_text("body")
        reg = SkillRegistry([
            _skill("greedy", "G" * 3000, source=d / "SKILL.md")])
        catalog = render_available_skills(reg)
        assert "G" * 3000 not in catalog
        assert len(catalog) < 3000

    def test_the_clamp_is_visible(self, tmp_path):
        d = tmp_path / "greedy"
        d.mkdir()
        (d / "SKILL.md").write_text("body")
        reg = SkillRegistry([
            _skill("greedy", "G" * 3000, source=d / "SKILL.md")])
        assert "…" in render_available_skills(reg)

    def test_a_greedy_entry_no_longer_crowds_the_others_out(self, tmp_path):
        """The consequence the bound exists for: the skills that actually
        run this machine stay listed."""
        skills = _with_paths(tmp_path, 8, description="Runbook text")
        d = tmp_path / "greedy"
        d.mkdir()
        (d / "SKILL.md").write_text("body")
        skills.append(_skill("greedy", "G" * 3500, source=d / "SKILL.md"))
        catalog = render_available_skills(SkillRegistry(skills))
        assert catalog.count("<skill>") == 9
        assert "truncated" not in catalog

    def test_the_render_ceiling_sits_between_the_two_bounds_that_exist(self):
        """Above every description Halbert ships, below the parse ceiling.

        A ceiling at the 60-char create limit would silently truncate
        founder-authored copy in the prompt; a ceiling at the 4096-char
        parse bound is the defect. It is a bound on one entry's share of a
        shared budget, not a rewrite of anyone's words.
        """
        from halbert_core.skills.parser import MAX_PARSED_DESCRIPTION_CHARS

        assert DESCRIPTION_LIMIT < MAX_RENDERED_DESCRIPTION_CHARS
        assert MAX_RENDERED_DESCRIPTION_CHARS < MAX_PARSED_DESCRIPTION_CHARS
        assert MAX_RENDERED_DESCRIPTION_CHARS * 8 < CATALOG_BUDGET_CHARS

    def test_nothing_shipped_is_touched_by_the_ceiling(self):
        from halbert_core.skills.loader import daemon_skill_dirs

        reg = SkillRegistry.from_disk(dirs=daemon_skill_dirs())
        for skill in reg.all():
            assert len(skill.description or "") <= MAX_RENDERED_DESCRIPTION_CHARS


# ---------------------------------------------------------------------------
# A13 bug 8 / FD-20 — the sweep, as a lint rather than an edit
# ---------------------------------------------------------------------------

class TestTheBundledDescriptionSweep:
    #: Empty, and that is the point. FD-20 was answered on 2026-09-10:
    #: all six over-limit descriptions were rewritten (founder-approved,
    #: not mechanically trimmed -- `config-ops` could not reach 60 by
    #: removing words alone and needed "Configuration" -> "Config").
    #: The set can only shrink, so an empty one is the end state and a
    #: new over-limit description now fails outright.
    KNOWN_OVER_LIMIT = set()

    def test_no_bundled_skill_joins_the_over_limit_set(self):
        from halbert_core.skills.loader import daemon_skill_dirs

        reg = SkillRegistry.from_disk(dirs=daemon_skill_dirs())
        over = {name for name, _ in descriptions_over_limit(reg)}
        assert over <= self.KNOWN_OVER_LIMIT, (
            f"new over-{DESCRIPTION_LIMIT}-char descriptions: "
            f"{sorted(over - self.KNOWN_OVER_LIMIT)}"
        )

    def test_the_lint_reports_the_measured_length(self, tmp_path):
        d = tmp_path / "wordy"
        d.mkdir()
        (d / "SKILL.md").write_text("body")
        reg = SkillRegistry([
            _skill("wordy", "W" * 90, source=d / "SKILL.md")])
        assert descriptions_over_limit(reg) == [("wordy", 90)]

    def test_a_description_inside_the_limit_is_not_reported(self, tmp_path):
        d = tmp_path / "terse"
        d.mkdir()
        (d / "SKILL.md").write_text("body")
        reg = SkillRegistry([_skill("terse", "Short", source=d / "SKILL.md")])
        assert descriptions_over_limit(reg) == []


# ---------------------------------------------------------------------------
# A13 bug 7 — the one line whose job is honesty
# ---------------------------------------------------------------------------

class TestTheNoticeIsTrue:
    def test_the_notice_no_longer_names_a_command_that_does_not_exist(self, tmp_path):
        reg = SkillRegistry(_with_paths(tmp_path, 5, description="D" * 100))
        catalog = render_available_skills(reg, budget=400)
        assert "truncated" in catalog
        assert "halbert skills list" not in catalog

    def test_a_truncated_render_tells_the_operator_somewhere_real(
            self, tmp_path, caplog):
        """Rung 5 promised an operator surface. There is no CLI and no
        route, so the surface is the daemon log — and the log carries the
        thing the notice cannot afford to: every skill and its location."""
        reg = SkillRegistry(_with_paths(tmp_path, 5, description="D" * 100))
        with caplog.at_level(logging.WARNING):
            render_available_skills(reg, budget=400)
        joined = "\n".join(r.getMessage() for r in caplog.records)
        assert "skill-00" in joined and "skill-04" in joined
        assert "SKILL.md" in joined

    def test_a_render_that_fits_says_nothing_to_anyone(self, tmp_path, caplog):
        """The notice is the block's only XML comment, so its absence is
        the check — not a substring search for the word, which a skill
        installed under a path containing it would answer."""
        reg = SkillRegistry(_with_paths(tmp_path, 3))
        with caplog.at_level(logging.WARNING):
            catalog = render_available_skills(reg)
        assert "<!--" not in catalog
        assert not [r for r in caplog.records if "catalog" in r.getMessage()]
