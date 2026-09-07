# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SEC-3 (F7/F171): a persona name cannot become a path.

``memory_dir = f"personas/{persona}"`` was joined to the memory root and handed
to ``shutil.rmtree``. A persona of ``../..`` deleted whatever sat above the
memory root.

The tests that matter here are the ones that build a real directory tree and
assert it survives — asserting only that a ValueError is raised would still pass
if the deletion happened first.
"""
from __future__ import annotations

import pytest

from halbert_core.persona.memory_purge import MemoryPurge, _PERSONA_NAME


@pytest.fixture
def purge(tmp_path):
    root = tmp_path / "memory"
    (root / "personas" / "friend").mkdir(parents=True)
    (root / "personas" / "friend" / "notes.jsonl").write_text('{"a": 1}\n')
    (root / "core").mkdir()
    (root / "core" / "precious.jsonl").write_text('{"keep": true}\n')
    # The thing an escape would reach.
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "important.txt").write_text("do not delete me")
    return MemoryPurge(memory_root=root), tmp_path


class TestTraversalIsRefused:
    @pytest.mark.parametrize("payload", [
        "../..",
        "../../outside",
        "..",
        "friend/../../outside",
        "./friend",
        "/etc",
        "friend/sub",
        "",
        ".",
        "-rf",
    ])
    def test_a_name_that_expresses_a_path_is_refused(self, purge, payload):
        mp, tmp_path = purge
        with pytest.raises(ValueError):
            mp.preview_purge(payload)

    def test_the_files_outside_the_root_actually_survive(self, purge):
        """The assertion that matters: nothing was deleted on the way to the raise."""
        mp, tmp_path = purge
        for payload in ("../..", "../../outside", "friend/../../outside"):
            with pytest.raises(ValueError):
                mp.execute_purge(payload, user="test", export_before=False)

        assert (tmp_path / "outside" / "important.txt").exists()
        assert (tmp_path / "outside" / "important.txt").read_text() == "do not delete me"
        assert (tmp_path / "memory" / "core" / "precious.jsonl").exists()

    def test_a_symlink_out_of_the_root_is_refused(self, purge):
        """The name rule alone would pass this; the containment check is what stops it."""
        mp, tmp_path = purge
        (tmp_path / "memory" / "personas" / "escape").symlink_to(tmp_path / "outside")

        with pytest.raises(ValueError, match="outside the persona memory root"):
            mp.execute_purge("escape", user="test", export_before=False)

        assert (tmp_path / "outside" / "important.txt").exists()


class TestOrdinaryUseStillWorks:
    def test_a_real_persona_previews(self, purge):
        mp, _ = purge
        confirmation = mp.preview_purge("friend")
        assert confirmation.persona == "friend"
        assert confirmation.estimated_entries == 1

    def test_a_real_persona_purges_and_leaves_core_alone(self, purge):
        mp, tmp_path = purge
        mp.execute_purge("friend", user="test", export_before=False)

        assert not (tmp_path / "memory" / "personas" / "friend" / "notes.jsonl").exists()
        assert (tmp_path / "memory" / "personas" / "friend").is_dir()  # recreated
        assert (tmp_path / "memory" / "core" / "precious.jsonl").exists()

    def test_protected_directories_are_still_protected(self, purge):
        mp, _ = purge
        for name in ("core", "runtime", "shared", "it_admin"):
            with pytest.raises(ValueError):
                mp.preview_purge(name)

    @pytest.mark.parametrize("name", ["friend", "custom", "work_2", "a-b-c", "x"])
    def test_ordinary_names_are_accepted_by_the_pattern(self, name):
        assert _PERSONA_NAME.match(name)
