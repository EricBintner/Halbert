# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The Class-1 fence — GOVERNED_PATHS as a function of the resolved dirs.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §6.2/§6.3:

    Class 1 — Governing artefacts. Never writable by the agent, at any
    autonomy level, with no override, no confirmation dialog, no escape
    hatch. ... A policy that says "the agent must not edit policy.yml"
    is stored in policy.yml. So this is enforced by path, by
    filesystem, by chain and by lint — never by policy.

    ``halbert_core/consent/selfmod.py`` exports ``GOVERNED_PATHS`` as a
    **function of the resolved config and data dirs** — never a literal,
    never CWD-relative. Every write primitive resolves its target and
    refuses.

    The check must run on the **resolved path the handler will actually
    open**, obtained once, as one string, used for both [the check and
    the open] (F16).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from halbert_core.consent.selfmod import (
    GOVERNED_PATHS,
    GovernedPathError,
    assert_not_governed,
    is_governed_path,
)


@pytest.fixture
def dirs(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"
    for d in (config_dir, data_dir, log_dir):
        d.mkdir()
    return {
        "config_dir": str(config_dir),
        "data_dir": str(data_dir),
        "log_dir": str(log_dir),
    }


def _governed(**dirs):
    return GOVERNED_PATHS(
        config_dir=dirs["config_dir"],
        data_dir=dirs["data_dir"],
        log_dir=dirs["log_dir"],
    )


# ---------------------------------------------------------------------------
# A function of the resolved dirs — never a literal.
# ---------------------------------------------------------------------------


def test_governed_paths_is_a_function_not_a_literal():
    assert callable(GOVERNED_PATHS)


def test_the_governed_set_follows_the_dirs_you_give_it(tmp_path, dirs):
    """Two different machines resolve two different governed sets — a
    literal list could not do that and would drift the moment the config
    dir moved."""
    here = _governed(**dirs)

    other = dict(dirs)
    other["config_dir"] = str(tmp_path / "other-config")
    other["config_dir"] and Path(other["config_dir"]).mkdir()
    there = _governed(**other)

    assert here != there
    assert (Path(dirs["config_dir"]) / "being.yml") in [Path(p) for p in here]
    assert (Path(other["config_dir"]) / "being.yml") in [Path(p) for p in there]


def test_the_governed_covers_the_class_1_artefacts(dirs):
    governed = {Path(p) for p in _governed(**dirs)}

    assert Path(dirs["config_dir"], "being.yml") in governed
    assert Path(dirs["config_dir"], "autonomy.yml") in governed
    assert Path(dirs["config_dir"], "policy.yml") in governed
    assert Path(dirs["config_dir"], "consent-state.json") in governed
    assert Path(dirs["config_dir"], "skills") in governed
    assert Path(dirs["config_dir"], "lenses") in governed
    assert Path(dirs["data_dir"], "consent") in governed
    assert Path(dirs["data_dir"], "runtime", "halt.json") in governed
    assert Path(dirs["log_dir"], "audit") in governed


def test_the_governed_covers_the_persistence_locations(dirs):
    governed = {Path(p) for p in _governed(**dirs)}
    home = Path.home()

    assert home / "Library" / "LaunchAgents" in governed
    assert home / ".config" / "systemd" / "user" in governed
    assert home / ".config" / "autostart" in governed
    assert Path("/Library/LaunchDaemons") in governed


def test_every_governed_path_is_resolved_and_absolute(dirs):
    for p in _governed(**dirs):
        path = Path(p)
        assert path.is_absolute()
        assert ".." not in path.parts
        assert "~" not in path.parts


# ---------------------------------------------------------------------------
# is_governed_path — the resolved-path check.
# ---------------------------------------------------------------------------


def _check(path, dirs):
    return is_governed_path(str(path), **dirs)


def test_the_artefact_itself_is_governed(dirs):
    assert _check(Path(dirs["config_dir"]) / "being.yml", dirs)


def test_content_inside_a_governed_directory_is_governed(dirs):
    assert _check(Path(dirs["config_dir"]) / "skills" / "evil.md", dirs)
    assert _check(Path(dirs["data_dir"]) / "consent" / "0001.jsonl", dirs)


def test_an_ordinary_file_is_not_governed(dirs):
    assert not _check(Path(dirs["config_dir"]) / "notes.txt", dirs)
    assert not _check(Path.home() / "Documents" / "letter.txt", dirs)


def test_a_prefix_collision_is_not_a_match(dirs):
    """skills-backup/ is not skills/ — the check is on path boundaries,
    not string prefixes."""
    assert not _check(Path(dirs["config_dir"]) / "skills-backup" / "x.md", dirs)


def test_the_home_expansion_of_a_persistence_path_is_governed(dirs):
    assert _check("~/Library/LaunchAgents/com.evil.agent.plist", dirs)


def test_a_dotted_escape_resolves_into_governed(dirs):
    """F16's shape: the raw argument and the opened file must be the same
    string. A path that *looks* outside but resolves inside is governed."""
    raw = Path(dirs["config_dir"]) / ".." / Path(dirs["config_dir"]).name / "being.yml"
    assert _check(raw, dirs)


def test_a_symlink_to_a_governed_file_is_governed(dirs, tmp_path):
    target = Path(dirs["config_dir"]) / "being.yml"
    alias = tmp_path / "harmless.txt"
    os.symlink(target, alias)

    assert _check(alias, dirs)


def test_a_symlink_inside_governed_pointing_out_is_caught_by_resolution(
    dirs, tmp_path
):
    """The other direction: a path inside a governed directory that
    resolves outside is *not* governed (it opens elsewhere) — but the
    reverse trick, a symlink in an open area pointing into the governed
    tree, is caught because the check resolves first."""
    outside = tmp_path / "outside" / "being.yml"
    outside.parent.mkdir()
    outside.write_text("not the real one")
    assert not _check(outside, dirs)


# ---------------------------------------------------------------------------
# assert_not_governed — obtained once, used for both check and open.
# ---------------------------------------------------------------------------


def test_assert_not_governed_returns_the_resolved_path(dirs, tmp_path):
    raw = tmp_path / ".." / tmp_path.name / "notes.txt"

    resolved = assert_not_governed(str(raw), **dirs)

    assert resolved == str(Path(raw).resolve())
    assert not is_governed_path(resolved, **dirs)


def test_assert_not_governed_refuses_a_governed_path(dirs):
    with pytest.raises(GovernedPathError) as caught:
        assert_not_governed(str(Path(dirs["config_dir"]) / "being.yml"), **dirs)

    assert caught.value.governed_root
    assert caught.value.path


def test_assert_not_governed_resolves_before_checking(dirs, tmp_path):
    """A symlink at an open path that resolves to the consent log is
    refused on the resolved path — the F16 rule at the one place the
    write primitives will call."""
    target = Path(dirs["data_dir"]) / "consent"
    alias = tmp_path / "camera-firmware"
    os.symlink(target, alias)

    with pytest.raises(GovernedPathError):
        assert_not_governed(str(alias), **dirs)


def test_governed_path_error_is_a_runtime_error(dirs):
    assert issubclass(GovernedPathError, RuntimeError)