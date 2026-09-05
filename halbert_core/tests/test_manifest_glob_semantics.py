# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""What the registry's globs resolve to, not what they say.

Every existing test of the config registry asserts on the *text* of the
manifest -- ``"racoon" in " ".join(registry["exclude"])`` -- which is green
whether or not the walker ever excludes racoon. It did not: ``/etc/*.conf``
reached ``/etc/racoon/racoon.conf`` because ``fnmatch``'s ``*`` crosses ``/``.
A test shaped like the document cannot see that. These are shaped like the
result.
"""

import os

import pytest

from halbert_core.config.manifest import Manifest, path_matches


@pytest.fixture
def etc(tmp_path):
    """A miniature /etc with the shapes that matter."""
    layout = [
        "etc/nfs.conf",
        "etc/hosts",
        "etc/cups/printers.conf",
        "etc/racoon/racoon.conf",
        "etc/apache2/httpd.conf",
        "etc/apache2/extra/httpd-ssl.conf",
        "etc/pam.d/sshd",
        "etc/ssh/sshd_config",
        "etc/ssh/ssh_host_rsa_key",
        "etc/ssh/sshd_config.d/100-macos.conf",
    ]
    for rel in layout:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")
    return tmp_path


def _resolved(tmp_path, include, exclude=()):
    m = Manifest(
        include=[str(tmp_path / p) for p in include],
        exclude=[str(tmp_path / p) for p in exclude],
        parsers={},
    )
    return {os.path.relpath(p, tmp_path) for p in m.iter_paths()}


class TestAStarStaysInsideOneSegment:
    def test_a_single_star_does_not_descend(self, etc):
        """The bug, stated as the thing it let in."""
        got = _resolved(etc, ["etc/*.conf"])
        assert got == {"etc/nfs.conf"}

    def test_it_does_not_reach_the_file_the_registry_excludes(self, etc):
        """``/etc/*.conf`` used to match ``/etc/racoon/racoon.conf``.

        The shipped macOS registry excludes racoon by name. The over-match
        landed on exactly the file its author had tried to keep out, and the
        exclusion could not save it -- see the walker-spelling test below.
        """
        assert "etc/racoon/racoon.conf" not in _resolved(etc, ["etc/*.conf"])

    def test_a_directory_glob_does_not_descend_either(self, etc):
        got = _resolved(etc, ["etc/apache2/*.conf"])
        assert got == {"etc/apache2/httpd.conf"}
        assert "etc/apache2/extra/httpd-ssl.conf" not in got


class TestDoubleStarSpansSegments:
    def test_it_matches_at_the_top_level_too(self, etc):
        """``/etc/**/*.conf`` could not match ``/etc/resolv.conf``.

        ``fnmatch`` requires a literal ``/`` after ``**``, so the broadest
        include in the shipped Linux registry skipped every file directly in
        ``/etc`` -- the "structurally cannot match" note in
        ``config/scopes/storage.yml``.
        """
        got = _resolved(etc, ["etc/**/*.conf"])
        assert "etc/nfs.conf" in got
        assert "etc/cups/printers.conf" in got

    def test_a_trailing_double_star_takes_everything_below(self, etc):
        assert _resolved(etc, ["etc/ssh/**"]) == {
            "etc/ssh/sshd_config",
            "etc/ssh/ssh_host_rsa_key",
            "etc/ssh/sshd_config.d/100-macos.conf",
        }


class TestExcludesStillBite:
    def test_a_key_is_excluded_from_a_directory_glob(self, etc):
        got = _resolved(etc, ["etc/ssh/*"], ["etc/ssh/*_key"])
        assert "etc/ssh/ssh_host_rsa_key" not in got
        assert "etc/ssh/sshd_config" in got

    def test_a_leading_double_star_exclude_matches_an_absolute_path(self, etc):
        """``**/*~orig`` is how the registry drops the OS's own backups.

        A leading ``**`` has to be able to eat the leading ``/``: the paths it
        is matched against are absolute.
        """
        (etc / "etc" / "hosts~orig").write_text("x\n")
        got = _resolved(etc, ["etc/*"], ["**/*~orig"])
        assert "etc/hosts~orig" not in got
        assert "etc/hosts" in got


class TestTheWalkerSpelling:
    def test_an_exclude_written_for_the_resolved_path_cannot_match(self):
        """Why the racoon exclusion was dead, stated as a property.

        ``os.walk('/etc')`` yields ``/etc/...`` however ``/etc`` resolves. On
        macOS ``/etc`` is a symlink to ``/private/etc``, so the registry's
        ``/private/etc/racoon/**`` can never match a path the walker
        produces. This is a separate bug from the glob semantics and is NOT
        fixed by them -- it is recorded here so the next reader does not
        assume the exclusion works.
        """
        walked = "/etc/racoon/racoon.conf"
        assert not path_matches(walked, "/private/etc/racoon/**")
        assert path_matches(walked, "/etc/racoon/**")
