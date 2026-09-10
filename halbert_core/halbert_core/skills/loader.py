# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Skill discovery.

Skills are read from four locations, least specific first, so a later
definition of the same name replaces an earlier one (design
DESIGN-SKILLS-SYSTEM-2026-09-07 §1.3 collapses the two workspace spellings
into one root):

    halbert_core/skills/builtin/<name>/SKILL.md   shipped with Halbert
    ~/.config/halbert/skills/<name>/SKILL.md      the user's own
    <cwd>/.halbert/skills/<name>/SKILL.md         host-local override
    <cwd>/.claude/skills/<name>/SKILL.md          compatibility

Both `<name>/SKILL.md` and a bare `<name>.md` are accepted in every location.
A skill that fails to parse is logged and skipped rather than taking down
discovery — one malformed user file must not cost the user every built-in.

Every candidate file is read with boundary-safe rules (design §4.2): it must
resolve under the root it was declared in (a symlink escape is refused — a
skill root is a trust boundary, and a link pointing outside it is text from
somewhere else wearing the root's name), and the byte caps and strict-UTF-8
checks live in `parser.parse_skill_file`. A skill that claims a reserved
name — a tool, slash-builtin, or persona-handback name (design §2.4) — is
refused here too, the same posture as the builtin-name refusal.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .parser import Skill, SkillParseError, parse_skill_file
from .reserved import is_reserved_skill_name

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


def _skill_files(directory: Path) -> List[Path]:
    """Yield candidate skill files in *directory*, deterministically ordered.

    Each candidate must resolve under the directory it was declared in: a
    symlinked entry pointing outside the root is refused with a log line,
    because the root is the trust boundary the refusal reasons about.
    """
    if not directory.is_dir():
        return []

    try:
        root = directory.resolve()
    except OSError as e:  # pragma: no cover - unreadable root
        logger.warning("cannot resolve skill directory %s: %s", directory, e)
        return []

    found: List[Path] = []
    for entry in sorted(directory.iterdir()):
        candidate = None
        if entry.is_dir():
            for name in ("SKILL.md", "skill.md"):
                path = entry / name
                if path.is_file():
                    candidate = path
                    break
        elif entry.is_file() and entry.suffix.lower() == ".md":
            candidate = entry
        if candidate is None:
            continue
        try:
            resolved = candidate.resolve()
        except OSError as e:
            logger.warning("skipping unreadable skill %s: %s", candidate, e)
            continue
        if root not in resolved.parents:
            logger.warning(
                "refusing skill %s: it resolves to %s, outside its "
                "declaring root %s (symlink escape)",
                candidate, resolved, root,
            )
            continue
        found.append(candidate)
    return found


def skill_manifest(dirs: Optional[Iterable[Path]] = None,
                   cwd: Optional[Path] = None) -> Tuple[Tuple[str, int, int], ...]:
    """A signature per skill file: ``(path, st_mtime_ns, st_size)``, sorted.

    A13-G2. The registry is built once inside a process singleton, so an
    edited SKILL.md never reached a running daemon -- while ``read_file``,
    following the ``<location>`` the catalog printed, served the NEW body.
    The disclosure layer and the content layer described different skills.

    Hermes rebuilds exactly this manifest on every prompt build
    (``agent/prompt_builder.py:1080-1119``) and reparses only when it
    moved. Two fields, not one: mtime alone misses a rewrite inside the
    same clock tick, and size alone misses an edit that keeps the length.

    Stat failures are skipped rather than raised: a file that vanished
    between the walk and the stat is a change like any other, and the next
    call sees the tree without it.
    """
    search = list(dirs) if dirs is not None else default_skill_dirs(cwd)
    out: List[Tuple[str, int, int]] = []
    for directory in search:
        for path in _skill_files(Path(directory)):
            try:
                st = path.stat()
            except OSError:
                continue
            out.append((str(path), st.st_mtime_ns, st.st_size))
    return tuple(sorted(out))


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
        except (KeyboardInterrupt, SystemExit):
            # The operator's own Ctrl-C, and a deliberate exit. A
            # per-file guard that swallowed these would be a guard
            # against the person running the machine.
            raise
        except BaseException as e:
            # A13-G1: one bad file never costs the plane. This used to
            # catch only SkillParseError and OSError, so a file that
            # raised anything else -- a MemoryError from a YAML alias
            # bomb, a RecursionError from a self-referential anchor --
            # took the whole directory walk with it, and every skill on
            # the machine went with the one somebody dropped in a folder.
            logger.error(
                "skipping skill %s: it failed to parse in a way the parser "
                "did not anticipate (%s: %s). The other skills in %s are "
                "unaffected.",
                path, type(e).__name__, e, directory,
            )
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
            if is_reserved_skill_name(skill.name):
                # Design §2.4: reserved names are refused at load and at
                # create. A skill claiming a tool's name would be reachable
                # as `/<name>` once the slash channel lands, and a user
                # typing it would mean the tool.
                logger.warning(
                    "refusing skill %r from %s: the name is reserved "
                    "(a tool, slash-builtin, or persona-handback name)",
                    skill.name, skill.source_path,
                )
                continue
            reserved_alias = next(
                (a for a in skill.aliases if is_reserved_skill_name(a)), None
            )
            if reserved_alias is not None:
                # Aliases address a skill as surely as its name does; a
                # reserved alias is the same claim with worse ergonomics.
                logger.warning(
                    "refusing skill %r from %s: the alias %r is reserved",
                    skill.name, skill.source_path, reserved_alias,
                )
                continue
            if skill.name in resolved:
                logger.debug(
                    "skill %r from %s overrides %s",
                    skill.name, skill.source_path, resolved[skill.name].source_path,
                )
            resolved[skill.name] = skill
    return resolved