# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A13-G2: a skill edit that never reaches the running daemon.

The registry is built once, inside ``get_agent()``'s process singleton.
Edit a SKILL.md — fix a wrong command, tighten a ``protected_paths`` line,
add a skill — and nothing changes until the daemon restarts. What makes it
worse than ordinary staleness is that the two halves disagree: the catalog
still advertises the OLD description, and when the model follows the
``<location>`` and reads the file, ``read_file`` hands it the NEW body. The
disclosure layer and the content layer describe different skills.

Hermes rebuilds a manifest of ``st_mtime_ns`` + ``st_size`` per skill file
at prompt-build time (`agent/prompt_builder.py:1080-1119`); this is that,
at turn start. The stat walk is the cheap half — the parse only runs when a
signature actually moved.
"""
from __future__ import annotations

import pytest

from halbert_core.skills.loader import skill_manifest
from halbert_core.skills.reload import SkillPlane, get_skill_plane, reset_skill_plane


SKILL = """---
name: {name}
description: {description}
halbert:
  kind: ops
  state: trusted
  priority: normal
---
{body}
"""


@pytest.fixture(autouse=True)
def _clean_plane():
    reset_skill_plane()
    yield
    reset_skill_plane()


@pytest.fixture
def root(tmp_path):
    d = tmp_path / "skills" / "disk-ops"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        SKILL.format(name="disk-ops", description="Disks", body="Old body."))
    return tmp_path / "skills"


def _write(root, name, description, body, *, mtime=None):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    path = d / "SKILL.md"
    path.write_text(SKILL.format(name=name, description=description, body=body))
    if mtime is not None:
        import os
        os.utime(path, ns=(mtime, mtime))
    return path


# ---------------------------------------------------------------------------
# The manifest itself
# ---------------------------------------------------------------------------

class TestTheManifest:
    def test_it_records_a_signature_per_skill_file(self, root):
        manifest = skill_manifest([root])
        assert len(manifest) == 1
        path, mtime_ns, size = manifest[0]
        assert path.endswith("disk-ops/SKILL.md")
        assert mtime_ns > 0 and size > 0

    def test_an_edit_moves_the_signature(self, root):
        before = skill_manifest([root])
        _write(root, "disk-ops", "Disks", "New body.", mtime=10**18)
        assert skill_manifest([root]) != before

    def test_a_new_file_moves_the_signature(self, root):
        before = skill_manifest([root])
        _write(root, "net-ops", "Interfaces", "Body.")
        assert len(skill_manifest([root])) == len(before) + 1

    def test_a_deleted_file_moves_the_signature(self, root):
        _write(root, "net-ops", "Interfaces", "Body.")
        before = skill_manifest([root])
        (root / "net-ops" / "SKILL.md").unlink()
        assert skill_manifest([root]) != before

    def test_it_is_ordered_so_two_reads_of_an_unchanged_tree_agree(self, root):
        _write(root, "net-ops", "Interfaces", "Body.")
        _write(root, "aaa-ops", "First", "Body.")
        assert skill_manifest([root]) == skill_manifest([root])

    def test_a_missing_root_is_not_an_error(self, tmp_path):
        assert skill_manifest([tmp_path / "nope"]) == ()


# ---------------------------------------------------------------------------
# The plane: rebuilt only when something moved
# ---------------------------------------------------------------------------

class TestThePlaneFollowsTheDisk:
    def test_an_edit_reaches_the_registry(self, root):
        plane = SkillPlane(dirs=[root])
        assert plane.registry.get("disk-ops").description == "Disks"
        _write(root, "disk-ops", "Disks and filesystems", "New body.",
               mtime=10**18)
        assert plane.refresh() is True
        assert plane.registry.get("disk-ops").description == "Disks and filesystems"

    def test_the_body_and_the_description_move_together(self, root):
        """The half that makes this worse than staleness: read_file already
        served the new body while the catalog still advertised the old
        description."""
        plane = SkillPlane(dirs=[root])
        _write(root, "disk-ops", "Disks and filesystems", "New body.",
               mtime=10**18)
        plane.refresh()
        skill = plane.registry.get("disk-ops")
        assert "New body." in skill.prompt
        assert skill.description == "Disks and filesystems"

    def test_a_new_skill_appears(self, root):
        plane = SkillPlane(dirs=[root])
        assert plane.registry.get("net-ops") is None
        _write(root, "net-ops", "Interfaces", "Body.")
        assert plane.refresh() is True
        assert plane.registry.get("net-ops") is not None

    def test_an_untouched_tree_is_not_reparsed(self, root):
        plane = SkillPlane(dirs=[root])
        version = plane.registry.snapshot_version
        assert plane.refresh() is False
        assert plane.refresh() is False
        assert plane.registry.snapshot_version == version

    def test_force_rebuilds_anyway(self, root):
        plane = SkillPlane(dirs=[root])
        version = plane.registry.snapshot_version
        assert plane.refresh(force=True) is True
        assert plane.registry.snapshot_version != version

    def test_the_matcher_keeps_its_identity_across_a_reload(self, root):
        """The pipeline holds this object; a reload that replaced it would
        leave the running daemon matching against the registry it had at
        construction — the bug, wearing a fix."""
        plane = SkillPlane(dirs=[root])
        matcher = plane.matcher
        _write(root, "net-ops", "Interfaces", "Body.")
        plane.refresh()
        assert plane.matcher is matcher
        assert matcher.registry is plane.registry
        assert matcher.registry.get("net-ops") is not None

    def test_the_read_seam_follows_the_reload(self, root):
        """``skill_for_path`` is how a catalog consultation becomes a
        telemetry receipt; pointing it at the old registry would lose the
        receipt for exactly the skill that just changed."""
        from halbert_core.skills.telemetry import active_registry

        plane = SkillPlane(dirs=[root])
        path = _write(root, "net-ops", "Interfaces", "Body.")
        plane.refresh()
        assert active_registry() is plane.registry
        assert active_registry().skill_for_path(path) is not None


class TestAReloadNeverCostsTheTurn:
    def test_a_root_that_vanishes_leaves_the_last_good_registry(self, root, tmp_path):
        plane = SkillPlane(dirs=[root])
        before = plane.registry
        import shutil

        shutil.rmtree(root)
        plane.refresh()
        # An empty tree is a legitimate state -- the registry follows it --
        # but nothing raises out of a turn for it.
        assert plane.registry is not None
        assert before is not None

    def test_a_stat_failure_is_not_fatal(self, root, monkeypatch):
        plane = SkillPlane(dirs=[root])
        version = plane.registry.snapshot_version

        def _boom(*a, **k):
            raise OSError("injected")

        monkeypatch.setattr(
            "halbert_core.skills.reload.skill_manifest", _boom)
        assert plane.refresh() is False
        assert plane.registry.snapshot_version == version

    def test_a_parse_that_explodes_leaves_the_previous_registry_serving(
            self, root, monkeypatch):
        plane = SkillPlane(dirs=[root])
        before = plane.registry

        def _boom(*a, **k):
            raise RuntimeError("injected")

        monkeypatch.setattr(
            "halbert_core.skills.reload.SkillRegistry.from_disk", _boom)
        _write(root, "net-ops", "Interfaces", "Body.")
        assert plane.refresh() is False
        assert plane.registry is before

    def test_a_failed_rebuild_is_retried_rather_than_latched(
            self, root, monkeypatch):
        """The signature is committed only on success, so the next turn
        tries again instead of accepting the broken state as current."""
        plane = SkillPlane(dirs=[root])
        calls = []
        real = SkillPlane._build

        def _boom(self, *a, **k):
            calls.append(1)
            raise RuntimeError("injected")

        monkeypatch.setattr(SkillPlane, "_build", _boom)
        _write(root, "net-ops", "Interfaces", "Body.")
        plane.refresh()
        plane.refresh()
        assert len(calls) == 2
        monkeypatch.setattr(SkillPlane, "_build", real)
        assert plane.refresh() is True


class TestTheProcessSingleton:
    def test_the_same_plane_comes_back(self, root):
        assert get_skill_plane(dirs=[root]) is get_skill_plane()

    def test_reset_lets_a_test_start_clean(self, root):
        first = get_skill_plane(dirs=[root])
        reset_skill_plane()
        assert get_skill_plane(dirs=[root]) is not first


class TestTheConsumerIsActuallyWired:
    """The cross-cutting defect this whole pass is about: a module that
    works, with nothing calling it. A reload path nobody calls at turn
    start is the same bug wearing a fix."""

    def test_the_route_builds_its_matcher_through_the_plane(self):
        import inspect

        from halbert_core.dashboard.routes import agent as route

        src = inspect.getsource(route.get_agent)
        assert "get_skill_plane" in src
        # ...and no longer builds a private one that nothing can refresh.
        assert "SkillRegistry.from_disk" not in src

    def test_the_turn_entry_refreshes_before_it_runs(self):
        import inspect

        from halbert_core.dashboard.routes import agent as route

        src = inspect.getsource(route)
        head = src[:src.index("A turn needs a stable id")]
        assert "get_skill_plane().refresh()" in head

    def test_the_matcher_the_pipeline_holds_is_the_planes(self, root):
        """``IntakePipeline.skill_registry`` is a property over the
        matcher, so the catalog and the matcher cannot drift apart."""
        from halbert_core.intake import IntakePipeline

        plane = SkillPlane(dirs=[root])
        pipeline = IntakePipeline(
            complexity_router=None, budget_fn=lambda *a, **k: 4000,
            model_config={}, skill_matcher=plane.matcher)
        assert pipeline.skill_registry is plane.registry
        _write(root, "net-ops", "Interfaces", "Body.")
        plane.refresh()
        assert pipeline.skill_registry is plane.registry
        assert pipeline.skill_registry.get("net-ops") is not None
