# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A glob's walk root is not its dirname.

os.path.dirname("/etc/**/*.conf") is the literal "/etc/**", which is never a
directory, so os.walk yields nothing and the pattern matches no files. That
killed the broadest include in the shipped Linux manifest — silently, on the
platform the config watcher actually runs on.
"""

import os

import pytest

from halbert_core.config.manifest import Manifest


class TestWalkRoot:
    @pytest.mark.parametrize("pattern,expected", [
        ("/etc/**/*.conf", "/etc"),
        ("/etc/ssh/**/*", "/etc/ssh"),
        ("/etc/systemd/*.service", "/etc/systemd"),
        ("/etc/default/*", "/etc/default"),
        ("/etc/conf.d/[a-z]*", "/etc/conf.d"),
        ("/etc/hosts", "/etc"),
    ])
    def test_it_truncates_at_the_first_metacharacter(self, pattern, expected):
        assert Manifest.walk_root(pattern) == expected

    def test_the_old_derivation_was_not_a_directory(self):
        """The bug, stated as a fact rather than a story."""
        assert os.path.dirname("/etc/**/*.conf") == "/etc/**"
        assert not os.path.isdir("/etc/**")
        assert Manifest.walk_root("/etc/**/*.conf") == "/etc"

    def test_a_user_path_is_expanded(self):
        root = Manifest.walk_root("~/.config/*.conf")
        assert not root.startswith("~")
        assert root == os.path.join(os.path.expanduser("~"), ".config")


class TestItActuallyFindsFiles:
    def test_a_recursive_include_matches(self, tmp_path):
        """End to end: the pattern shape that used to match nothing."""
        (tmp_path / "etc" / "nested").mkdir(parents=True)
        (tmp_path / "etc" / "top.conf").write_text("a\n")
        (tmp_path / "etc" / "nested" / "deep.conf").write_text("b\n")
        (tmp_path / "etc" / "ignore.txt").write_text("c\n")

        man = Manifest(include=[f"{tmp_path}/etc/**/*.conf",
                                f"{tmp_path}/etc/*.conf"], exclude=[], parsers={})
        found = set(man.iter_paths())

        assert str(tmp_path / "etc" / "top.conf") in found
        assert str(tmp_path / "etc" / "nested" / "deep.conf") in found
        assert not any(f.endswith(".txt") for f in found)

    def test_exclude_still_wins(self, tmp_path):
        (tmp_path / "etc").mkdir()
        (tmp_path / "etc" / "keep.conf").write_text("a\n")
        (tmp_path / "etc" / "secret.conf").write_text("b\n")

        man = Manifest(include=[f"{tmp_path}/etc/**/*.conf", f"{tmp_path}/etc/*.conf"],
                       exclude=[f"{tmp_path}/etc/secret.conf"], parsers={})
        found = set(man.iter_paths())

        assert str(tmp_path / "etc" / "keep.conf") in found
        assert str(tmp_path / "etc" / "secret.conf") not in found
