# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Skill discovery.

Skills are read from four locations, least specific first, so a later
definition of the same name replaces an earlier one:

    halbert_core/skills/builtin/<name>/SKILL.md   shipped with Halbert
    ~/.config/halbert/skills/<name>/SKILL.md      the user's own
    <cwd>/.halbert/skills/<name>/SKILL.md         host-local override
    <cwd>/.claude/skills/<name>/SKILL.md          compatibility

Both `<name>/SKILL.md` and a bare `<name>.md` are accepted in every location.
A skill that fails to parse is logged and skipped rather than taking down
discovery — one malformed user file must not cost the user every built-in.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .parser import Skill, SkillParseError, parse_skill_file

logger = logging.getLogger(__name__)

BUILTIN_DIR = Path(__file__).parent / "builtin"


def default_skill_dirs(cwd: Optional[Path] = None) -> List[Path]:
    """The four search locations, in precedence order (last wins)."""
    root = Path(cwd) if cwd else Path.cwd()
    return [
        BUILTIN_DIR,
        Path.home() / ".config" / "halbert" / "skills",
        root / ".halbert" / "skills",
        root / ".claude" / "skills",
    ]


def daemon_skill_dirs() -> List[Path]:
    """The locations the running daemon may take instructions from.

    Skill text reaches the model as its own directive (lenses invariant 8), so
    only operator-owned locations may supply it. ``default_skill_dirs`` reads
    ``Path.cwd()``, which for the ``halbert`` console script is whatever shell
    the user happened to start it from and for a debug or HALBERT_REPO_ROOT
    Tauri build is the repo itself -- verified to load ``.claude/skills`` from
    the repo, and twelve unrelated Claude Code skills from ``$HOME``.

    ``default_skill_dirs`` keeps the four-location chain for CLI and test
    callers that genuinely want a project-local skill. The daemon uses this.
    """
    return [BUILTIN_DIR, Path.home() / ".config" / "halbert" / "skills"]


def _builtin_names() -> set:
    return {s.name for s in load_skills_from_dir(BUILTIN_DIR)}


def _skill_files(directory: Path) -> Iterable[Path]:
    """Yield candidate skill files in *directory*, deterministically ordered."""
    if not directory.is_dir():
        return []

    found: List[Path] = []
    for entry in sorted(directory.iterdir()):
        if entry.is_dir():
            for candidate in ("SKILL.md", "skill.md"):
                path = entry / candidate
                if path.is_file():
                    found.append(path)
                    break
        elif entry.is_file() and entry.suffix.lower() == ".md":
            found.append(entry)
    return found


def load_skills_from_dir(directory: Path) -> List[Skill]:
    """Parse every skill in one directory, skipping the ones that don't."""
    skills: List[Skill] = []
    for path in _skill_files(directory):
        try:
            skills.append(parse_skill_file(path))
        except SkillParseError as e:
            logger.warning("skipping unparseable skill: %s", e)
        except OSError as e:
            logger.warning("skipping unreadable skill %s: %s", path, e)
    return skills


def load_skills(dirs: Optional[Iterable[Path]] = None,
                cwd: Optional[Path] = None) -> Dict[str, Skill]:
    """Load all skills, resolving same-name overrides by precedence.

    Returns a mapping of skill name to Skill. A user skill named `storage-ops`
    replaces the built-in of that name outright — it does not merge with it.
    """
    search = list(dirs) if dirs is not None else default_skill_dirs(cwd)

    resolved: Dict[str, Skill] = {}
    builtin_names = _builtin_names() if BUILTIN_DIR in [Path(d) for d in search] else set()

    for directory in search:
        is_builtin_dir = Path(directory) == BUILTIN_DIR
        for skill in load_skills_from_dir(Path(directory)):
            if not is_builtin_dir and skill.name in builtin_names:
                # A same-named file replaced the builtin outright, taking its
                # declared protected_paths with it -- so a file dropped in the
                # user directory could quietly disarm storage-ops. Refused
                # rather than merged: merging two safety declarations has no
                # obviously correct answer, and the name is the thing the
                # matcher and /skill address.
                logger.warning(
                    "refusing skill %r from %s: the name is a built-in and "
                    "overriding it would drop its declared safety",
                    skill.name, skill.source_path,
                )
                continue
            if skill.name in resolved:
                logger.debug(
                    "skill %r from %s overrides %s",
                    skill.name, skill.source_path, resolved[skill.name].source_path,
                )
            resolved[skill.name] = skill
    return resolved
