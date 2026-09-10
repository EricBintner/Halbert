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
from .parser import (Skill, SkillRequirements, SkillSafety,
                     SkillTriggers, derived_skill_id, new_skill_id)

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


def _merge_requires(parent, child):
    """Union two ``requires`` clauses; either side may be None."""
    if parent is None:
        return child
    if child is None:
        return parent
    return SkillRequirements(
        bins=_merge_tuples(parent.bins, child.bins),
        any_bins=_merge_tuples(parent.any_bins, child.any_bins),
        env=_merge_tuples(parent.env, child.env),
        os=_merge_tuples(parent.os, child.os),
        config=_merge_tuples(parent.config, child.config),
    )


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

    declared = set(skill.declared or ())

    def pick(attr: str):
        """Child wins when it DECLARED the field, or set it off the default.

        A13 bug 9: the declared half was missing, so "left at the default"
        and "deliberately set to the default" were the same thing to the
        merge -- and a child could not escape a parent's
        ``priority: critical`` by writing ``priority: normal``. The parser
        records which keys the file actually carried; this reads that
        rather than trying to infer intent from a value.
        """
        child_value = getattr(skill, attr)
        if attr in declared or child_value != getattr(defaults, attr):
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
        # A13 bug 9, second half: this used to REPLACE. Every other
        # restriction in this merge unions in the most-restrictive
        # direction -- a parent's protected path cannot be dropped by a
        # child -- and `requires` is a restriction: a child that declared
        # its own `bins` shed the parent's, then inherited a body that
        # assumes both.
        requires=_merge_requires(parent.requires, skill.requires),
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
    if skill.source_path is not None:
        # A13-G8: derived from the file, so the id means the same skill
        # after a restart. A fresh random ULID per load made every skill a
        # new row in the telemetry table every time the daemon came up,
        # and the table's whole question is "which skills does the model
        # actually consult?".
        return dataclasses.replace(
            skill, id=derived_skill_id(skill.source_path))
    # Nothing durable to key on -- an in-memory skill is process-local by
    # construction, and the id still has to be well-formed.
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
        every read passes through. Exact matches win over containment.

        A13 bug 3: containment applies only to a DIRECTORY-layout skill --
        one whose source file is named ``SKILL.md``. A bare-layout skill
        (``~/.config/halbert/skills/foo.md``) has the shared ROOT as its
        parent, so asking whether that parent is in a path's parents
        attributed every skill file in the root, and every file under every
        sibling skill's directory, to whichever bare skill the dict
        happened to yield first. It owns its own file and nothing else.

        Among directory-layout skills the DEEPEST containing directory
        wins, so a skill nested inside a pack's tree claims its own
        references rather than losing them to the pack; name breaks a tie
        at equal depth, so the answer is deterministic.
        """
        import os

        if not self._skills:
            return None
        try:
            probe = Path(os.path.expanduser(str(path))).resolve()
        except (OSError, RuntimeError):
            return None
        best: Optional[Skill] = None
        best_depth = -1
        for skill in sorted(self._skills.values(), key=lambda s: s.name):
            src = skill.source_path
            if src is None:
                continue
            try:
                resolved = Path(src).resolve()
            except (OSError, RuntimeError):
                continue
            if probe == resolved:
                return skill
            if resolved.name.lower() != "skill.md":
                continue
            parent = resolved.parent
            if parent in probe.parents:
                depth = len(parent.parts)
                if depth > best_depth:
                    best, best_depth = skill, depth
        return best

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
