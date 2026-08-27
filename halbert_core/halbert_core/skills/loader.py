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
    for directory in search:
        for skill in load_skills_from_dir(Path(directory)):
            if skill.name in resolved:
                logger.debug(
                    "skill %r from %s overrides %s",
                    skill.name, skill.source_path, resolved[skill.name].source_path,
                )
            resolved[skill.name] = skill
    return resolved
