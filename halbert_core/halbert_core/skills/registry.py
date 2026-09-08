# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
In-memory skill registry.

Holds the loaded skills, resolves names and aliases, and flattens `extends`
inheritance so the matcher and composer only ever see fully-resolved skills.

Every mutation and every construction is a new *snapshot*: a process-wide
monotonic counter hands each one a `snapshot_version` that no other
registry state ever holds again. The catalog renderer (skills SK-2) keys
its memo on it (design §2.2), so a reload invalidates exactly the renders
that must die and — because the counter never repeats — a memo entry can
never outlive the registry state it was rendered from.
"""

from __future__ import annotations

import dataclasses
import itertools
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .loader import load_skills
from .parser import Skill, SkillSafety, SkillTriggers, new_skill_id

logger = logging.getLogger(__name__)

#: Snapshot versions, never reset within a process. `itertools.count` hands
#: out each value exactly once, so a fresh registry built from unchanged
#: disk still gets a version no memo has ever seen — that is the point: a
#: reload is a new snapshot even when nothing changed on disk.
_snapshot_versions = itertools.count(1)


def _merge_tuples(parent: tuple, child: tuple) -> tuple:
    """Union, preserving order and dropping duplicates (parent first)."""
    seen = set()
    out = []
    for item in (*parent, *child):
        if item not in seen:
            seen.add(item)
            out.append(item)
    return tuple(out)


def resolve_extends(skill: Skill, by_name: Dict[str, Skill],
                    _seen: Optional[frozenset] = None) -> Skill:
    """Flatten `extends` into *skill*.

    List fields union with the parent's; scalar fields keep the child's value
    when it differs from the dataclass default. Safety unions in the
    most-restrictive direction, matching how the composer treats co-active
    skills: a parent's protected path cannot be dropped by a child.

    An unknown or cyclic parent is logged and ignored — a broken `extends`
    degrades the skill to its own definition rather than removing it.
    """
    if not skill.extends:
        return skill

    seen = _seen or frozenset()
    if skill.name in seen:
        logger.warning("skill %r has a cyclic extends chain; ignoring", skill.name)
        return dataclasses.replace(skill, extends=None)

    parent = by_name.get(skill.extends)
    if parent is None:
        logger.warning(
            "skill %r extends unknown skill %r; ignoring", skill.name, skill.extends
        )
        return dataclasses.replace(skill, extends=None)

    parent = resolve_extends(parent, by_name, seen | {skill.name})
    defaults = Skill(name="_")

    def pick(attr: str):
        """Child wins unless it left the field at its default."""
        child_value = getattr(skill, attr)
        if child_value != getattr(defaults, attr):
            return child_value
        return getattr(parent, attr)

    merged_triggers = SkillTriggers(
        domains=_merge_tuples(parent.triggers.domains, skill.triggers.domains),
        keywords=_merge_tuples(parent.triggers.keywords, skill.triggers.keywords),
        platform=_merge_tuples(parent.triggers.platform, skill.triggers.platform),
        intent=_merge_tuples(parent.triggers.intent, skill.triggers.intent),
    )

    merged_safety = SkillSafety(
        destructive_requires_approval=(
            parent.safety.destructive_requires_approval
            or skill.safety.destructive_requires_approval
        ),
        protected_paths=_merge_tuples(
            parent.safety.protected_paths, skill.safety.protected_paths
        ),
        protected_services=_merge_tuples(
            parent.safety.protected_services, skill.safety.protected_services
        ),
        blocked_commands=_merge_tuples(
            parent.safety.blocked_commands, skill.safety.blocked_commands
        ),
    )

    prompt = "\n\n".join(p for p in (parent.prompt, skill.prompt) if p)

    return dataclasses.replace(
        skill,
        triggers=merged_triggers,
        safety=merged_safety,
        aliases=_merge_tuples(parent.aliases, skill.aliases),
        role=pick("role"),
        scope=pick("scope"),
        knowledge_scope=pick("knowledge_scope"),
        trace_expand=pick("trace_expand"),
        tier=pick("tier"),
        priority=pick("priority"),
        budget_multiplier=pick("budget_multiplier"),
        allowed_tools=pick("allowed_tools"),
        subagent=pick("subagent"),
        max_turns=pick("max_turns"),
        kind=pick("kind"),
        requires=pick("requires"),
        # Identity and lifecycle are never inherited: an id is identity, not
        # a capability (design §5.4 — a rename or a move must not smuggle or
        # forfeit provenance), and lifecycle is per-skill (§5.5).
        id=skill.id,
        state=skill.state,
        prompt=prompt,
        extends=None,
    )


def _stamp(skill: Skill) -> Skill:
    """A skill with a stable id, stamped here when it shipped without one.

    Bundled and operator files carry no `halbert.id` — ids are stamped at
    creation, never hand-written (§5.4), and neither was "created" through
    the authoring tool. But the catalog and the telemetry table key on the
    id (never the name — the two-sources-of-truth trap), so the registry
    stamps one at load: in-process identity only. A skill that carries a
    durable id keeps it; SK-6's create path writes those onto the file.
    """
    if skill.id is not None:
        return skill
    return dataclasses.replace(skill, id=new_skill_id())


class SkillRegistry:
    """The loaded skills, addressable by name or alias."""

    def __init__(self, skills: Optional[Iterable[Skill]] = None):
        self._skills: Dict[str, Skill] = {}
        self._snapshot_version = next(_snapshot_versions)
        for skill in skills or ():
            self._skills[skill.name] = _stamp(skill)
        self._flatten()

    @classmethod
    def from_disk(cls, dirs: Optional[Iterable[Path]] = None,
                  cwd: Optional[Path] = None) -> "SkillRegistry":
        return cls(load_skills(dirs=dirs, cwd=cwd).values())

    @property
    def snapshot_version(self) -> int:
        """The version of this registry's state; never reused (§2.2)."""
        return self._snapshot_version

    def _flatten(self) -> None:
        source = dict(self._skills)
        self._skills = {
            name: resolve_extends(skill, source) for name, skill in source.items()
        }
        self._aliases: Dict[str, str] = {}
        for skill in self._skills.values():
            for alias in skill.aliases:
                if alias in self._skills:
                    logger.warning(
                        "alias %r of skill %r collides with a skill name; ignoring",
                        alias, skill.name,
                    )
                    continue
                self._aliases.setdefault(alias, skill.name)

    def add(self, skill: Skill) -> None:
        self._skills[skill.name] = _stamp(skill)
        self._snapshot_version = next(_snapshot_versions)
        self._flatten()

    def remove(self, name: str) -> bool:
        if name in self._skills:
            del self._skills[name]
            self._snapshot_version = next(_snapshot_versions)
            self._flatten()
            return True
        return False

    def skill_for_path(self, path) -> Optional[Skill]:
        """The skill a file belongs to, or None when it is not skill text.

        A hit is the skill's own SKILL.md or any file under the skill's
        directory (its `references/` and `scripts/` — design §6, seam 1).
        The executor's read_file consults this before dispatch so a catalog
        consultation becomes a telemetry receipt at the one choke point
        every read passes through. Exact SKILL.md matches win over directory
        containment; ties resolve by name so the answer is deterministic.
        """
        import os

        if not self._skills:
            return None
        try:
            probe = Path(os.path.expanduser(str(path))).resolve()
        except (OSError, RuntimeError):
            return None
        exact: Optional[Skill] = None
        containing: Optional[Skill] = None
        for skill in self._skills.values():
            src = skill.source_path
            if src is None:
                continue
            try:
                resolved = Path(src).resolve()
            except (OSError, RuntimeError):
                continue
            if probe == resolved:
                exact = skill
                break
            if resolved.parent in probe.parents and containing is None:
                containing = skill
        return exact or containing

    def get(self, name: str) -> Optional[Skill]:
        """Look up by name, then by alias."""
        if not name:
            return None
        key = name.strip()
        if key in self._skills:
            return self._skills[key]
        aliased = self._aliases.get(key)
        return self._skills.get(aliased) if aliased else None

    def all(self) -> List[Skill]:
        return sorted(self._skills.values(), key=lambda s: s.name)

    def names(self) -> List[str]:
        return sorted(self._skills)

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self.get(name) is not None
