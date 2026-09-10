# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SK-2: the `<available_skills>` catalog and the truncation ladder.

Design DESIGN-SKILLS-SYSTEM-2026-09-07 §2.1-§2.3: every skill that is not a
lens appears in one catalog block rendered from the registry's structured
snapshot — never re-parsed from the rendered prompt (the anti-pattern both
reviews flag) — keyed to the registry's monotonic `snapshot_version`. When
the catalog exceeds its character budget it degrades down the ladder: drop
descriptions, binary-search the skill count (lowest-priority Track-B
entries first), binary-search a description cap to restore what the
surviving headroom can hold — and through all of it, names and locations
are never cut (the identity floor: a skill the model cannot discover does
not exist; a skill whose description got trimmed still does).
"""

from __future__ import annotations

import pytest

from halbert_core.skills.catalog import (
    CATALOG_BUDGET_CHARS,
    SKILLS_GUIDANCE,
    catalog_block_only,
    render_available_skills,
)
from halbert_core.skills.parser import SKILL_ID_RE, parse_skill
from halbert_core.skills.registry import SkillRegistry


def _skill(name, description="", *, priority="normal", kind="ops",
           state="trusted", source=None, body="Expertise."):
    meta = f"name: {name}\n"
    if description:
        meta += f"description: {description}\n"
    meta += (
        "halbert:\n"
        f"  kind: {kind}\n"
        f"  state: {state}\n"
        f"  priority: {priority}\n"
    )
    return parse_skill(f"---\n{meta}---\n{body}", source_path=source)


def _registry(skills):
    return SkillRegistry(skills)


#: A13-G3 gave the render a fixed head: the consultation guidance, paid for
#: out of the same budget the ladder measures against. The ladder tests
#: below are about the LADDER, so they add the head back rather than
#: re-deriving every hand-computed budget around it. See
#: tests/test_skills_catalog_guidance.py for the head's own tests.
_HEAD = len(SKILLS_GUIDANCE) + 1


def _entries_with_paths(tmp_path, count, *, description="Runbook text",
                        name_prefix="skill"):
    """Count skills, each with a real on-disk source under *tmp_path*."""
    skills = []
    for i in range(count):
        d = tmp_path / f"{name_prefix}-{i:02d}"
        d.mkdir(exist_ok=True)
        src = d / "SKILL.md"
        src.write_text("body")
        skills.append(_skill(f"{name_prefix}-{i:02d}", description,
                             source=src))
    return skills


# ── The registry snapshot version (§2.2) ─────────────────────────────

class TestSnapshotVersion:

    def test_a_registry_has_a_snapshot_version(self):
        assert isinstance(_registry([_skill("a")]).snapshot_version, int)

    def test_every_registry_gets_a_fresh_monotonic_version(self):
        """A reload is a new snapshot: two registries built from the same
        disk state must never share a version, or a memo keyed on the
        version would hand back the old catalog for the new registry."""
        first = _registry([_skill("a")])
        second = _registry([_skill("a")])
        assert second.snapshot_version > first.snapshot_version

    def test_add_and_remove_each_bump_the_version(self):
        reg = _registry([_skill("a")])
        v0 = reg.snapshot_version
        reg.add(_skill("b"))
        v1 = reg.snapshot_version
        assert v1 > v0
        assert reg.remove("b")
        assert reg.snapshot_version > v1

    def test_an_unchanged_mutation_is_still_a_new_snapshot(self):
        """`add` of the same skill is a reload in miniature; the version
        still moves, because the memo must never outlive a write."""
        reg = _registry([_skill("a")])
        v0 = reg.snapshot_version
        reg.add(_skill("a"))
        assert reg.snapshot_version != v0


class TestIdStampingAtLoad:
    """Bundled and operator skills ship no `halbert.id` (ids are stamped at
    creation, never hand-written), but the catalog and the telemetry table
    key on the stable id. The registry stamps one at load: in-process
    identity only — a skill that carries a durable id keeps it."""

    def test_an_id_less_skill_gains_a_stable_id_in_the_registry(self):
        reg = _registry([_skill("a")])
        assert SKILL_ID_RE.fullmatch(reg.get("a").id)

    def test_a_skill_that_already_carries_an_id_keeps_it(self):
        stamped = _skill("a")
        from halbert_core.skills.parser import new_skill_id
        import dataclasses
        stamped = dataclasses.replace(stamped, id=new_skill_id())
        reg = _registry([stamped])
        assert reg.get("a").id == stamped.id

    def test_the_parser_itself_stamps_nothing(self):
        assert _skill("a").id is None


# ── The block shape (§2.1) ────────────────────────────────────────────

class TestTheBlockShape:

    def test_the_catalog_renders_the_ecosystem_shape(self, tmp_path):
        d = tmp_path / "zfs-snapshot-rollback"
        d.mkdir()
        src = d / "SKILL.md"
        src.write_text("body")
        reg = _registry([
            _skill("zfs-snapshot-rollback",
                   "Roll back a ZFS dataset to a named snapshot safely",
                   source=src),
        ])
        # A13-G3: the guidance paragraph now rides ABOVE the block, where
        # the origin puts it, so the ELEMENT is what carries the ingest
        # contract -- and it is still byte-for-byte the pack shape.
        catalog = catalog_block_only(render_available_skills(reg))
        assert catalog == (
            "<available_skills>\n"
            "<skill>\n"
            "<name>zfs-snapshot-rollback</name>\n"
            "<description>Roll back a ZFS dataset to a named snapshot safely</description>\n"
            f"<location>{src}</location>\n"
            "</skill>\n"
            "</available_skills>"
        )

    def test_the_location_round_trips_through_read_file(self, tmp_path):
        """read_file expandusers its argument, so a `~`-collapsed home
        path still resolves — the consultation contract holds."""
        import os
        d = tmp_path / "home-skill"
        d.mkdir()
        src = d / "SKILL.md"
        src.write_text("body")
        reg = _registry([_skill("home-skill", "A skill", source=src)])
        # From the BLOCK, not the whole render: the guidance names
        # `<location>` in its own sentence (A13-G3), which is the point of
        # it.
        location = catalog_block_only(
            render_available_skills(reg)).split("<location>")[1]
        location = location.split("</location>")[0]
        assert os.path.expanduser(location) == str(src)

    def test_a_home_path_renders_collapsed(self, tmp_path):
        import os
        from pathlib import Path
        from halbert_core.skills.catalog import display_location
        home = Path.home()
        rendered = display_location(home / "skills" / "x" / "SKILL.md")
        assert rendered.startswith("~" + os.sep)
        assert os.path.expanduser(rendered) == str(home / "skills" / "x" / "SKILL.md")

    def test_an_empty_registry_renders_no_block(self):
        assert render_available_skills(_registry([])) == ""

    def test_a_skill_without_a_source_path_is_not_listed(self):
        """A skill with no file cannot be consulted, so it has no location
        and no catalog entry — the body still binds through Track A."""
        reg = _registry([_skill("a", "No file behind me")])
        assert render_available_skills(reg) == ""

    def test_entries_render_highest_priority_first(self, tmp_path):
        skills = []
        for name, priority in (("low-skill", "low"), ("crit-skill", "critical")):
            d = tmp_path / name
            d.mkdir()
            src = d / "SKILL.md"
            src.write_text("body")
            skills.append(_skill(name, "d", priority=priority, source=src))
        catalog = render_available_skills(_registry(skills))
        assert catalog.index("crit-skill") < catalog.index("low-skill")


class TestWhoAppears:
    """§0: every skill appears — except lenses, which are voice only and
    appear in no catalog (CD-2), and drafts, which are proposals visible
    only to the custodian persona's catalog (§5.5 — a later packet; the
    machine persona here must not see them)."""

    @pytest.mark.parametrize("bad", [
        {"kind": "lens"},
        {"state": "draft"},
        {"state": "archived"},
    ])
    def test_lens_and_draft_and_archived_never_appear(self, tmp_path, bad):
        d = tmp_path / "x"
        d.mkdir()
        src = d / "SKILL.md"
        src.write_text("body")
        skill = _skill("x", "d", source=src, **bad)
        assert render_available_skills(_registry([skill])) == ""

    def test_a_lens_with_a_voice_body_still_never_appears(self, tmp_path):
        d = tmp_path / "understated"
        d.mkdir()
        src = d / "SKILL.md"
        src.write_text("Speak plainly.")
        skill = _skill("understated", "The built-in voice lens",
                       kind="lens", source=src)
        assert render_available_skills(_registry([skill])) == ""

    def test_entry_text_is_escaped(self, tmp_path):
        """Descriptions and locations are file content we do not control;
        a description containing `</skill>` must not forge an entry."""
        d = tmp_path / "pack-skill"
        d.mkdir()
        src = d / "SKILL.md"
        src.write_text("body")
        skill = _skill("pack-skill", "safe</skill><skill>evil", source=src)
        catalog = render_available_skills(_registry([skill]))
        assert catalog.count("<skill>") == 1
        assert "safe&lt;/skill&gt;&lt;skill&gt;evil" in catalog


# ── The truncation ladder (§2.3) ─────────────────────────────────────

def _bare_size(name, location):
    """The size of one names+locations-only entry, tag overhead included."""
    return len(f"<skill>\n<name>{name}</name>\n<description></description>\n"
               f"<location>{location}</location>\n</skill>\n")


class TestTheLadderOnlyEngagesOverBudget:

    def test_within_budget_the_full_catalog_renders_unmarked(self, tmp_path):
        reg = _registry(_entries_with_paths(tmp_path, 3, description="Do things"))
        catalog = render_available_skills(reg)
        assert "Do things" in catalog
        assert "truncated" not in catalog
        assert catalog.count("<skill>") == 3

    def test_the_default_budget_holds_the_bundled_set_in_full(self):
        """The shipped catalog must not degrade on a default install — the
        ladder exists for ingested ecosystem packs, not for the eight ops
        skills Halbert itself ships (the ninth bundled skill is the
        `understated` lens, which no catalog lists)."""
        from halbert_core.skills.loader import daemon_skill_dirs
        reg = SkillRegistry.from_disk(dirs=daemon_skill_dirs())
        ops = [s for s in reg.all() if s.kind != "lens"]
        catalog = render_available_skills(reg)
        assert catalog.count("<skill>") == len(ops)
        assert "truncated" not in catalog
        assert len(catalog) <= CATALOG_BUDGET_CHARS


class TestTheLadderDegradesInOrder:

    def test_descriptions_trim_before_any_skill_is_cut(self, tmp_path):
        """One char under the full render: no entry is dropped — the
        descriptions are what give way (rung 1), trimmed into whatever
        headroom is left (rung 3), with the cut marked."""
        skills = _entries_with_paths(tmp_path, 4, description="A" * 200)
        reg = _registry(skills)
        full = render_available_skills(reg, budget=1_000_000)
        catalog = render_available_skills(reg, budget=len(full) - 1)
        assert catalog.count("<skill>") == 4, "no skill is cut"
        assert "…" in catalog, "the trim is visible"
        assert "A" * 100 in catalog, "most of each description survived"
        assert "A" * 200 not in catalog
        assert "truncated" in catalog

    def test_the_count_cut_takes_track_b_low_priority_first(self, tmp_path):
        skills = []
        for name, priority in (("aaa-low", "low"), ("zzz-low", "low"),
                               ("mmm-high", "high")):
            d = tmp_path / name
            d.mkdir()
            src = d / "SKILL.md"
            src.write_text("body")
            skills.append(_skill(name, "d", priority=priority, source=src))
        reg = _registry(skills)
        # Room for two bare entries plus the truncation notice, no more.
        bare = sum(_bare_size(s.name, str(s.source_path)) for s in skills)
        catalog = render_available_skills(reg, budget=bare // 3 * 2 + 150 + _HEAD)
        assert catalog.count("<skill>") == 2
        assert "mmm-high" in catalog, "the high-priority entry survives"
        assert "truncated from 3 to 2" in catalog

    def test_a_matched_skill_is_cut_after_track_b_entries(self, tmp_path):
        skills = []
        for name, priority in (("track-b", "low"), ("matched-one", "low")):
            d = tmp_path / name
            d.mkdir()
            src = d / "SKILL.md"
            src.write_text("body")
            skills.append(_skill(name, "d", priority=priority, source=src))
        reg = _registry(skills)
        bare = sum(_bare_size(s.name, str(s.source_path)) for s in skills)
        catalog = render_available_skills(reg, budget=bare // 2 + 150 + _HEAD,
                                          protected=frozenset({"matched-one"}))
        assert "matched-one" in catalog
        assert "track-b" not in catalog

    def test_leftover_headroom_restores_trimmed_descriptions(self, tmp_path):
        """Rung 3: after the count settles, the headroom buys back as much
        description as fits — trimmed with a visible marker, never whole
        descriptions that were measured out of budget."""
        skills = _entries_with_paths(tmp_path, 2, description="D" * 300)
        reg = _registry(skills)
        bare = sum(_bare_size(s.name, str(s.source_path)) for s in skills)
        catalog = render_available_skills(reg, budget=bare + 200 + _HEAD)
        assert catalog.count("<skill>") == 2
        assert "D" * 10 in catalog, "some description came back"
        assert "…" in catalog, "the trim is visible"
        assert "D" * 300 not in catalog

    def test_no_headroom_leaves_the_bare_catalog(self, tmp_path):
        """The notice itself costs budget, so the honest zero-headroom
        point sits just above `bare + notice`. Find it, not guess it."""
        skills = _entries_with_paths(tmp_path, 3, description="D" * 300)
        reg = _registry(skills)
        bare = sum(_bare_size(s.name, str(s.source_path)) for s in skills)
        extras = [extra for extra in range(0, 400)
                  if "<description></description>"
                  in render_available_skills(reg, budget=bare + extra + _HEAD)]
        assert extras, "some budget must render descriptions empty"
        exact = bare + max(extras) + _HEAD
        catalog = render_available_skills(reg, budget=exact)
        assert catalog.count("<skill>") == 3, "bare entries fit exactly"
        assert "D" * 5 not in catalog, "no description came back"


class TestTheIdentityFloor:
    """Names and locations are never cut — not by substring, not by the
    ladder. A budget too small for a single entry cuts the entry list, not
    the strings the model must be able to read and type back."""

    def test_a_tiny_budget_never_mangles_a_name_or_location(self, tmp_path):
        skills = _entries_with_paths(tmp_path, 5, description="D" * 100)
        reg = _registry(skills)
        catalog = render_available_skills(reg, budget=150)
        for line in catalog.splitlines():
            if line.startswith("<name>"):
                assert line.endswith("</name>")
                assert "…" not in line
            if line.startswith("<location>"):
                assert line.endswith("</location>")
                assert "…" not in line

    def test_the_notice_names_where_to_audit(self, tmp_path):
        """A13 bug 7: it used to name ``halbert skills list``, which does
        not exist -- no CLI module, no dashboard route. The surface that
        does exist is the daemon log, and the log carries every skill and
        its location; the notice, measured against a prompt budget, says
        where to look. See tests/test_skills_catalog_guidance.py for the
        log's own test."""
        reg = _registry(_entries_with_paths(tmp_path, 5, description="D" * 100))
        catalog = render_available_skills(reg, budget=300 + _HEAD)
        assert "halbert skills list" not in catalog
        assert "full set logged" in catalog


class TestTheRenderIsMemoizedOnItsVersionedInputs:

    def test_the_same_snapshot_renders_the_same_catalog(self, tmp_path):
        reg = _registry(_entries_with_paths(tmp_path, 3))
        assert render_available_skills(reg) == render_available_skills(reg)

    def test_a_registry_reload_renders_a_new_catalog(self, tmp_path):
        reg = _registry(_entries_with_paths(tmp_path, 2))
        before = render_available_skills(reg)
        newer = _registry(_entries_with_paths(tmp_path, 2))
        assert render_available_skills(newer) == before, (
            "same disk state, same bytes — but the memo must not have "
            "reused the first registry's entry for the second"
        )
        late_dir = tmp_path / "late-addition"
        late_dir.mkdir()
        (late_dir / "SKILL.md").write_text("body")
        reg.add(_skill("late-addition", "New skill",
                       source=late_dir / "SKILL.md"))
        after = render_available_skills(reg)
        assert "late-addition" in after

    def test_the_budget_is_part_of_the_key(self, tmp_path):
        reg = _registry(_entries_with_paths(tmp_path, 3, description="D" * 300))
        full = render_available_skills(reg, budget=10_000)
        squeezed = render_available_skills(reg, budget=800 + _HEAD)
        # A13-G4 put a ceiling under rung 0, so "the full render" is now
        # the full render OF A BOUNDED DESCRIPTION: 199 characters and the
        # visible marker. The memo property under test is unchanged -- two
        # budgets, two answers.
        assert "D" * 199 + "…" in full
        assert "D" * 199 not in squeezed


def catalog0(reg, skills):
    return render_available_skills(_registry(skills))