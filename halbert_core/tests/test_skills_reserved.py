# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SK-1: reserved names — names a skill may not claim.

Design §2.4: reserved = registered tool names + intake slash builtins +
persona handback names, "checked at load and at create — refused at
spec-build, the same posture as the loader's builtin-name refusal." A skill
claiming a tool's name (hyphens and underscores compare equal, because the
skill charset spells them differently than the tool registry does) would be
reachable as `/<name>` once the slash channel lands, and a user typing it
would mean the tool, not the skill.
"""

from __future__ import annotations

import logging

from halbert_core.skills.loader import BUILTIN_DIR, load_skills
from halbert_core.skills.reserved import (
    CORE_TOOL_NAMES,
    RESERVED_SLASH_BUILTINS,
    is_reserved_skill_name,
    reserved_skill_names,
)


def _write(tmp_path, filename, content):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return tmp_path


# ── The set ────────────────────────────────────────────────────────────

def test_tool_names_are_reserved_in_both_spellings():
    # Skill names spell separators with hyphens; tools register with
    # underscores. The comparison normalizes, or the check is theater.
    assert is_reserved_skill_name("read_file")
    assert is_reserved_skill_name("read-file")
    assert is_reserved_skill_name("run-command")
    assert not is_reserved_skill_name("storage-ops")


def test_persona_handback_and_become_names_are_reserved():
    names = reserved_skill_names()
    assert "hand_back_to_halbert" in names
    assert "become_persona" in names


def test_slash_builtins_are_reserved():
    # The dashboard composer claims `/model` (frontend/src/lib/slashCommands.ts)
    # and the terminal page claims /explain /fix /dryrun with single-letter
    # aliases (frontend/src/pages/Terminal.tsx). A skill taking one of those
    # names would shadow a command the user already knows.
    assert "model" in RESERVED_SLASH_BUILTINS
    assert is_reserved_skill_name("model")
    assert is_reserved_skill_name("dryrun")


def test_capability_gated_tool_names_are_reserved_too():
    # System, vision, GPU and accelerator tools register only when their
    # registrar runs, but the names are claimed surfaces regardless: a skill
    # named after a tool nobody can currently see is still a name trap.
    names = reserved_skill_names()
    assert "get_disk_usage" in names
    assert "capture_webcam" in names


def test_the_core_tool_list_matches_a_live_executor():
    # CORE_TOOL_NAMES is hand-listed (the executor registers its builtins
    # inline), so drift is caught here in CI rather than by a production
    # refusal — or worse, a missing one.
    from halbert_core.tools.executor import ToolExecutor

    live = set(ToolExecutor().schemas)
    missing = [n for n in CORE_TOOL_NAMES if n not in live]
    assert not missing, f"stale CORE_TOOL_NAMES: {missing} not registered"


# ── Refusal at load ────────────────────────────────────────────────────

def test_a_skill_claiming_a_tool_name_is_refused_at_load(tmp_path, caplog):
    d = _write(
        tmp_path,
        "read-file.md",
        "---\nname: read-file\ndescription: d\n---\nInnocent-looking text.",
    )
    with caplog.at_level(logging.WARNING, logger="halbert_core.skills.loader"):
        skills = load_skills([d])
    assert skills == {}
    assert any("reserved" in r.message for r in caplog.records)


def test_a_skill_claiming_a_reserved_name_by_alias_is_refused(tmp_path):
    # Aliases address a skill as surely as its name does (`/disk` routes);
    # a reserved alias is the same claim with worse ergonomics.
    d = _write(
        tmp_path,
        "innocent.md",
        "---\nname: innocent\naliases: [model]\n---\nbody",
    )
    skills = load_skills([d])
    assert skills == {}


def test_an_unreserved_skill_still_loads(tmp_path):
    d = _write(
        tmp_path,
        "storage-ops-plus.md",
        "---\nname: storage-ops-plus\ndescription: d\n---\nbody",
    )
    assert "storage-ops-plus" in load_skills([d])


def test_no_bundled_skill_trips_the_reserved_check():
    # The refusal applies to every root including ours; if a bundled skill
    # ever collided with a tool name, this is where it would show.
    loaded = load_skills([BUILTIN_DIR])
    colliding = [n for n in loaded if is_reserved_skill_name(n)]
    assert colliding == []
    assert len(loaded) == 9