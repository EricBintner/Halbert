# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
SKILL.md parsing.

A Halbert skill is a markdown file with a YAML frontmatter block: the
frontmatter declares how the skill activates and what it constrains, and the
body is the expertise prompt injected when it does.

Unlike a Claude Code skill, where the prompt *is* the skill, here the prompt
is one of five components — prompt, retrieval scope, safety, model tier, and
context budget. This module only reads them; the matcher decides when a skill
applies and the composer decides what several active skills add up to.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml  # type: ignore

logger = logging.getLogger(__name__)

# Model tiers name the slots in models.yml (llm_config.SLOTS), not the legacy
# orchestrator/specialist/vision triple. Note the intake pipeline calls the
# chat slot "guide" in MessageIntake.recommended_model; mapping happens at that
# boundary, not here.
MODEL_TIERS = ("chat", "specialist", "vision")

PRIORITIES = ("low", "normal", "high", "critical")

# CD-11: the flavour layer is Lenses. An `ops` skill carries expertise,
# triggers, retrieval role and safety; a `lens` carries voice and nothing
# else (CD-3 — selection is arithmetic and lens-independent), and is chosen
# by `active_lens`, never by the matcher (CD-2).
KINDS = ("ops", "lens")

# Scored by the matcher; also the order used to break priority ties.
PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2, "critical": 3}

_FRONTMATTER_FENCE = "---"


class SkillParseError(ValueError):
    """A SKILL.md file could not be read as a skill."""


def canonical_scope_id(name: Optional[str]) -> Optional[str]:
    """Normalize a skill-declared scope id to the daemon's convention.

    Scope ids on the daemon use underscores (`knowledge_linux`,
    `storage_admin`). The project template writes hyphens, but those are
    display names the daemon maps to underscored ids for us — a name a *skill*
    invents has no such mapping, and an unrecognized scope silently widens the
    query to a global union. So normalize what skills declare.

    Roles are deliberately not normalized: they are skill-facing names and
    hyphenated by convention (`storage-ops`).
    """
    if not name:
        return None
    return name.strip().replace("-", "_")


def _as_tuple(value: Any) -> Tuple[str, ...]:
    """Coerce a scalar-or-list frontmatter field to a tuple of strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    return (str(value),)


@dataclass(frozen=True)
class SkillTriggers:
    """What makes a skill activate. Empty tuple means "does not restrict"."""

    domains: Tuple[str, ...] = ()
    keywords: Tuple[str, ...] = ()
    platform: Tuple[str, ...] = ()
    intent: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillSafety:
    """Declarative constraints, compiled into ToolSafetyFramework downstream.

    These are rules, not enforcement: Halbert already gates every tool call
    through ToolExecutor -> ToolSafetyFramework -> ApprovalEngine, and skill
    safety contributes to that chain rather than adding a parallel one.
    """

    destructive_requires_approval: bool = False
    protected_paths: Tuple[str, ...] = ()
    protected_services: Tuple[str, ...] = ()
    blocked_commands: Tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not (
            self.destructive_requires_approval
            or self.protected_paths
            or self.protected_services
            or self.blocked_commands
        )


@dataclass(frozen=True)
class Skill:
    """One parsed SKILL.md."""

    name: str
    description: str = ""
    aliases: Tuple[str, ...] = ()
    triggers: SkillTriggers = field(default_factory=SkillTriggers)

    # Retrieval. `role` is the preferred bridge: the skill names itself and
    # the scope carrying that role is resolved from the daemon's scope list,
    # so scope ids and skill names stay decoupled. `scope` is the fallback for
    # targeting a scope that has no role assigned.
    role: Optional[str] = None
    scope: Optional[str] = None
    knowledge_scope: Optional[str] = None
    trace_expand: bool = True

    model: str = "chat"
    priority: str = "normal"
    budget_multiplier: float = 1.0

    safety: SkillSafety = field(default_factory=SkillSafety)
    allowed_tools: Optional[Tuple[str, ...]] = None  # None = inherit all
    subagent: bool = False
    max_turns: int = 10

    prompt: str = ""
    source_path: Optional[Path] = None
    extends: Optional[str] = None
    kind: str = "ops"  # ops | lens (KINDS)

    @property
    def priority_rank(self) -> int:
        return PRIORITY_RANK.get(self.priority, 1)


def split_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Split a SKILL.md into its frontmatter mapping and its body.

    A file with no frontmatter fence is all body — that is not an error, it is
    a prompt-only skill whose name comes from its filename.
    """
    stripped = text.lstrip("﻿")
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return {}, stripped.strip()

    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONTMATTER_FENCE:
            raw = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:]).strip()
            try:
                meta = yaml.safe_load(raw) or {}
            except yaml.YAMLError as e:
                raise SkillParseError(f"invalid YAML frontmatter: {e}") from e
            if not isinstance(meta, dict):
                raise SkillParseError("frontmatter must be a mapping")
            return meta, body

    raise SkillParseError("frontmatter opened with --- but never closed")


def parse_skill(text: str, *, name: Optional[str] = None,
                source_path: Optional[Path] = None) -> Skill:
    """Parse SKILL.md content into a Skill.

    `name` is the fallback identity (the containing directory or filename)
    used when the frontmatter does not declare one.
    """
    meta, body = split_frontmatter(text)

    skill_name = str(meta.get("name") or name or "").strip()
    if not skill_name:
        raise SkillParseError("skill has no name, and no fallback was given")

    triggers_raw = meta.get("triggers") or {}
    if not isinstance(triggers_raw, dict):
        raise SkillParseError("triggers must be a mapping")

    # `platform` is accepted at the top level too — the design's own examples
    # write it both ways.
    platform = _as_tuple(triggers_raw.get("platform") or meta.get("platform"))

    triggers = SkillTriggers(
        domains=_as_tuple(triggers_raw.get("domains")),
        keywords=tuple(k.lower() for k in _as_tuple(triggers_raw.get("keywords"))),
        platform=tuple(p.lower() for p in platform),
        intent=tuple(i.lower() for i in _as_tuple(triggers_raw.get("intent"))),
    )

    safety_raw = meta.get("safety") or {}
    if not isinstance(safety_raw, dict):
        raise SkillParseError("safety must be a mapping")
    safety = SkillSafety(
        destructive_requires_approval=bool(
            safety_raw.get("destructive_requires_approval", False)
        ),
        protected_paths=_as_tuple(safety_raw.get("protected_paths")),
        protected_services=_as_tuple(safety_raw.get("protected_services")),
        blocked_commands=_as_tuple(safety_raw.get("blocked_commands")),
    )

    model = str(meta.get("model") or "chat").strip()
    # An explicit "provider:model" string is passed through untouched; only
    # bare tier names are validated, so a typo'd tier is caught but a real
    # model id still works.
    if ":" not in model and model not in MODEL_TIERS:
        raise SkillParseError(
            f"model {model!r} is not one of {MODEL_TIERS} "
            "(use 'chat', not the legacy 'orchestrator')"
        )

    priority = str(meta.get("priority") or "normal").strip().lower()
    if priority not in PRIORITIES:
        raise SkillParseError(f"priority {priority!r} is not one of {PRIORITIES}")

    try:
        multiplier = float(meta.get("budget_multiplier", 1.0))
    except (TypeError, ValueError) as e:
        raise SkillParseError(f"budget_multiplier must be a number: {e}") from e

    allowed = meta.get("allowed_tools")
    allowed_tools = _as_tuple(allowed) if allowed is not None else None

    kind = str(meta.get("kind") or "ops").strip().lower()
    if kind not in KINDS:
        raise SkillParseError(f"kind {kind!r} is not one of {KINDS}")
    if kind == "lens":
        # A lens is voice only. Anything that could score, scope, route or
        # bind is refused at the boundary rather than silently ignored, so a
        # user file cannot smuggle an ops skill in under a lens's trust.
        carries = []
        if any((triggers.domains, triggers.keywords, triggers.platform, triggers.intent)):
            carries.append("triggers")
        if meta.get("role") or meta.get("scope") or meta.get("knowledge_scope"):
            carries.append("role/scope")
        if safety_raw:
            carries.append("safety")
        if allowed_tools is not None:
            carries.append("allowed_tools")
        if meta.get("model") or meta.get("subagent"):
            carries.append("model/subagent")
        if carries:
            raise SkillParseError(
                f"a lens is voice only; {skill_name!r} declares {', '.join(carries)}"
            )

    return Skill(
        name=skill_name,
        description=str(meta.get("description") or "").strip(),
        aliases=_as_tuple(meta.get("aliases")),
        triggers=triggers,
        role=(str(meta.get("role")).strip() if meta.get("role") else None),
        scope=canonical_scope_id(meta.get("scope")),
        knowledge_scope=canonical_scope_id(meta.get("knowledge_scope")),
        trace_expand=bool(meta.get("trace_expand", True)),
        model=model,
        priority=priority,
        budget_multiplier=multiplier,
        safety=safety,
        allowed_tools=allowed_tools,
        subagent=bool(meta.get("subagent", False)),
        max_turns=int(meta.get("max_turns", 10)),
        prompt=body,
        source_path=source_path,
        extends=(str(meta.get("extends")).strip() if meta.get("extends") else None),
        kind=kind,
    )


def parse_skill_file(path: Path) -> Skill:
    """Parse a SKILL.md (or <name>.md) from disk.

    The fallback name is the containing directory for `<name>/SKILL.md`, and
    the filename stem otherwise — matching both layouts the design allows.
    """
    text = path.read_text(encoding="utf-8")
    fallback = path.parent.name if path.stem.upper() == "SKILL" else path.stem
    try:
        return parse_skill(text, name=fallback, source_path=path)
    except SkillParseError as e:
        raise SkillParseError(f"{path}: {e}") from e
