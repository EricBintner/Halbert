# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
SKILL.md parsing.

A Halbert skill is a markdown file with a YAML frontmatter block: the
frontmatter declares how the skill activates and what it constrains, and the
body is the expertise prompt injected when it does.

The format is byte-compatible with Claude Code's Agent Skills at the core
(`name`, `description`, `allowed-tools`, `license`, `metadata` — unknown
top-level keys are tolerated, which is what loads third-party packs), and
carries Halbert's own extensions under a single namespaced `halbert:`
mapping, so a future upstream field can never collide with ours (design
DESIGN-SKILLS-SYSTEM-2026-09-07 §1.2). Flat Halbert keys remain readable for
one cycle through a compat reader that warns and rewrites nothing.

This module only reads them; the matcher decides when a skill applies and
the composer decides what several active skills add up to.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml  # type: ignore

logger = logging.getLogger(__name__)

# Tiers name the slots in models.yml (llm_config.SLOTS), not models and not
# the legacy orchestrator/specialist/vision triple. The Determination rule
# (design §4.3) is enforced here: a skill may route to a *slot*, never name
# or recommend a model — the old "provider:model" passthrough is retired,
# and the compat reader downgrades legacy values to the chat tier with a
# warning rather than honoring them. Note the intake pipeline calls the
# chat slot "guide" in MessageIntake.recommended_model; mapping happens at
# that boundary, not here.
TIERS = ("chat", "specialist", "vision")

PRIORITIES = ("low", "normal", "high", "critical")

# CD-11: the flavour layer is Lenses. An `ops` skill carries expertise,
# triggers, retrieval role and safety; a `lens` carries voice and nothing
# else (CD-3 — selection is arithmetic and lens-independent), and is chosen
# by `active_lens`, never by the matcher (CD-2).
KINDS = ("ops", "lens")

# Agent-authored lifecycle (design §5.5). Operator and bundled files carry
# no marker and load as trusted; `draft` is what the create tool (SK-6)
# stamps, and only the verification runner (SK-7) promotes.
STATES = ("draft", "trusted", "archived")

# Scored by the matcher; also the order used to break priority ties.
PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2, "critical": 3}

_FRONTMATTER_FENCE = "---"

# A skill name is the CC-compatible surface: lowercase alphanumerics and
# hyphens, 1–64 chars, starting alphanumeric (design §1.2). Underscores are
# deliberately excluded — the tool namespace spells its names with them, and
# the reserved-name check compares the two after normalizing.
SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# A stable skill id: `sk_` + a 26-character Crockford-base32 ULID (48-bit
# millisecond stamp, 80 random bits). Identity, not display data — the
# frontmatter `id` is the join key to the provenance sidecar (§5.4), and a
# rename must never change it nor a move forfeit it.
SKILL_ID_RE = re.compile(r"^sk_[0-9A-HJKMNP-TV-Z]{26}$")

# The 60-char description discipline (§1.2): the description is the routing
# surface, so it is short by hard create-time rejection, not by lint. The
# create tool is SK-6's; the number both ends enforce lives here.
DESCRIPTION_LIMIT = 60

#: Boundary-safe read caps (design §4.2). Characters here are bytes of
#: encoded content, not tokens: this runs before any tokeniser is in scope.
MAX_SKILL_FILE_BYTES = 128 * 1024       # one SKILL.md, hard cap
MAX_FRONTMATTER_BYTES = 8 * 1024        # the fenced frontmatter block
MAX_REQUIRES_ENTRY_CHARS = 256         # one requires clause entry

#: The keys accepted inside the `halbert:` namespace. Tolerance ends here
#: (design §1.2): unknown *top-level* keys are what loads third-party packs,
#: but a key inside our namespace that is not ours is squatting.
HALBERT_KEYS = frozenset({
    "id", "kind", "triggers", "safety", "role", "scope", "knowledge_scope",
    "trace_expand", "tier", "priority", "budget_multiplier", "subagent",
    "max_turns", "extends", "aliases", "requires", "state",
})

#: Flat Halbert keys the compat reader still accepts (one cycle), mapped to
#: their namespaced spelling where it differs. The loader warns and rewrites
#: nothing — old files keep working through this reader until the cycle ends.
_FLAT_TO_HALBERT = {
    "kind": "kind", "triggers": "triggers", "safety": "safety",
    "role": "role", "scope": "scope", "knowledge_scope": "knowledge_scope",
    "trace_expand": "trace_expand", "model": "tier", "tier": "tier",
    "priority": "priority", "budget_multiplier": "budget_multiplier",
    "subagent": "subagent", "max_turns": "max_turns", "extends": "extends",
    "aliases": "aliases", "state": "state", "platform": "triggers",
}


class SkillParseError(ValueError):
    """A SKILL.md file could not be read as a skill."""


# ── Stable ids ─────────────────────────────────────────────────────────

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_id_lock = threading.Lock()
_id_last: list = [0, -1]  # [ms, randomness seen] — monotonic within a stamp


def new_skill_id() -> str:
    """Stamp a fresh stable skill id (`sk_` + ULID).

    Monotonic: two stamps taken in the same millisecond differ by more than
    a random re-roll (the randomness is incremented, the ULID discipline),
    so lexicographic order never goes backwards within a process even if the
    wall clock does. The id is identity (§5.4): stamped once at creation,
    never recomputed, never inferred from location or name.
    """
    with _id_lock:
        ms = time.time_ns() // 1_000_000
        rnd = int.from_bytes(os.urandom(10), "big")
        last_ms, last_rnd = _id_last
        if ms < last_ms or (ms == last_ms and rnd <= last_rnd):
            # Clock went backwards or collided within the millisecond:
            # bump the randomness inside the last good millisecond.
            ms = last_ms
            rnd = last_rnd + 1
            if rnd >= 1 << 80:  # overflow: step to the next millisecond
                ms += 1
                rnd = 0
        _id_last[0], _id_last[1] = ms, rnd
    raw = (ms << 80) | rnd
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[raw & 31])
        raw >>= 5
    return "sk_" + "".join(reversed(chars))


def validate_description(description: str) -> Optional[str]:
    """The create-time hard rejection for over-budget descriptions.

    Returns None when the description is within the limit, otherwise the
    refusal reason. Hard rejection, not lint (§1.2): the create tool (SK-6)
    errors on this; ingested ecosystem packs we do not control are clamped
    with a visible marker instead (see `clamp_description`).
    """
    text = (description or "").strip()
    if len(text) <= DESCRIPTION_LIMIT:
        return None
    return (
        f"description is {len(text)} characters; the limit is "
        f"{DESCRIPTION_LIMIT} (hard create-time rejection, not lint)"
    )


def clamp_description(description: str,
                      limit: int = DESCRIPTION_LIMIT) -> str:
    """Clamp a description to *limit* chars with a visible `…` marker.

    For ecosystem packs whose text we do not control (§1.2): the file is
    never edited on disk, so the marker is what makes the cut auditable.
    """
    text = (description or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


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
class SkillRequirements:
    """What a skill needs the host to have, parsed — not evaluated.

    Evaluation is SK-4's (capability gating against the live host); SK-1
    owns only the schema: `bins` all-of, `anyBins` any-of (the distinction
    is the design's own, §3), `env` variable *names* — values are never
    read, logged, or copied — `os` platforms, and `config` names of
    capabilities.py capability keys.
    """

    bins: Tuple[str, ...] = ()
    any_bins: Tuple[str, ...] = ()
    env: Tuple[str, ...] = ()
    os: Tuple[str, ...] = ()
    config: Tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not (self.bins or self.any_bins or self.env
                    or self.os or self.config)


#: requires-clause spellings in frontmatter -> dataclass fields.
REQUIRES_KEYS = {
    "bins": "bins",
    "anyBins": "any_bins",
    "env": "env",
    "os": "os",
    "config": "config",
}


def _parse_requires(raw: Any) -> Optional[SkillRequirements]:
    """Parse the `requires` schema, refusing anything that is not it."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SkillParseError(
            f"requires must be a mapping, not {type(raw).__name__}"
        )
    unknown = sorted(set(raw) - set(REQUIRES_KEYS))
    if unknown:
        raise SkillParseError(
            f"requires key(s) {unknown} not one of {sorted(REQUIRES_KEYS)}"
        )
    values: Dict[str, Tuple[str, ...]] = {}
    for key, name in REQUIRES_KEYS.items():
        if key not in raw:
            continue
        entries = raw[key]
        if not isinstance(entries, (list, tuple)):
            entries = (entries,)
        checked = []
        for entry in entries:
            if not isinstance(entry, str) or not entry.strip():
                raise SkillParseError(
                    f"requires.{key} entries must be non-empty strings"
                )
            if len(entry) > MAX_REQUIRES_ENTRY_CHARS:
                raise SkillParseError(
                    f"requires.{key} entry over the "
                    f"{MAX_REQUIRES_ENTRY_CHARS}-character cap"
                )
            checked.append(entry.strip())
        values[name] = tuple(checked)
    return SkillRequirements(**values)


@dataclass(frozen=True)
class Skill:
    """One parsed SKILL.md."""

    name: str
    description: str = ""
    aliases: Tuple[str, ...] = ()
    triggers: SkillTriggers = field(default_factory=SkillTriggers)

    # Identity and lifecycle (design §5.4–5.5). The id is the join key to the
    # provenance sidecar; absent means not yet stamped (operator files).
    # Neither is ever inherited through `extends`.
    id: Optional[str] = None
    state: str = "trusted"
    requires: Optional[SkillRequirements] = None

    # Retrieval. `role` is the preferred bridge: the skill names itself and
    # the scope carrying that role is resolved from the daemon's scope list,
    # so scope ids and skill names stay decoupled. `scope` is the fallback for
    # targeting a scope that has no role assigned.
    role: Optional[str] = None
    scope: Optional[str] = None
    knowledge_scope: Optional[str] = None
    trace_expand: bool = True

    tier: str = "chat"
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


class _Compat:
    """The one-cycle compat reader over `halbert:` + flat frontmatter.

    Namespaced keys win; flat keys still read, and the reader records which
    flat keys it consumed (to warn) and which it shadowed (to say the
    namespace won). It rewrites nothing on disk — old files keep working
    through this reader until the cycle ends (design §1.2).
    """

    def __init__(self, meta: Dict[str, Any]):
        halbert_raw = meta.get("halbert")
        if halbert_raw is None:
            halbert_raw = {}
        if not isinstance(halbert_raw, dict):
            raise SkillParseError("halbert must be a mapping")
        unknown = sorted(set(halbert_raw) - HALBERT_KEYS)
        if unknown:
            raise SkillParseError(
                f"halbert key(s) {unknown} not one of {sorted(HALBERT_KEYS)} "
                "(tolerance ends at our own extension schema)"
            )
        self._halbert: Dict[str, Any] = halbert_raw
        self._meta = meta
        self.flat_used: list = []
        self.shadowed: list = []

    def get(self, key: str, default: Any = None, *,
            flat: Optional[str] = None) -> Any:
        """The value for logical *key*: namespaced first, then flat."""
        flat_key = flat if flat is not None else key
        h_value = self._halbert.get(key)
        f_value = self._meta.get(flat_key)
        if h_value is not None:
            if f_value is not None and flat_key in _FLAT_TO_HALBERT:
                self.shadowed.append(flat_key)
            return h_value
        if f_value is not None and flat_key in _FLAT_TO_HALBERT:
            self.flat_used.append(flat_key)
            return f_value
        return default

    def warn(self) -> None:
        """Emit the one-cycle warnings once per parse."""
        if self.flat_used:
            logger.warning(
                "flat frontmatter key(s) %s are readable for one more "
                "cycle; declare them under `halbert:` (the loader rewrites "
                "nothing)",
                sorted(set(self.flat_used)),
            )
        if self.shadowed:
            logger.warning(
                "the `halbert:` block overrides the flat key(s) %s; "
                "the namespaced value wins",
                sorted(set(self.shadowed)),
            )


def split_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Split a SKILL.md into its frontmatter mapping and its body.

    A file with no frontmatter fence is all body — that is not an error, it is
    a prompt-only skill whose name comes from its filename. The fenced block
    is hard-capped (design §4.2): a frontmatter is routing metadata, not a
    place to hide a novel.
    """
    stripped = text.lstrip("﻿")
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return {}, stripped.strip()

    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONTMATTER_FENCE:
            raw = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:]).strip()
            if len(raw.encode("utf-8")) > MAX_FRONTMATTER_BYTES:
                raise SkillParseError(
                    f"frontmatter block is over the "
                    f"{MAX_FRONTMATTER_BYTES // 1024} KiB cap"
                )
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
    if not SKILL_NAME_RE.fullmatch(skill_name):
        raise SkillParseError(
            f"name {skill_name!r} must match {SKILL_NAME_RE.pattern} "
            "(the CC-compatible rule: lowercase alphanumerics and hyphens)"
        )

    reader = _Compat(meta)

    triggers_raw = reader.get("triggers") or {}
    if not isinstance(triggers_raw, dict):
        raise SkillParseError("triggers must be a mapping")
    # `platform` is accepted at the top level too — the design's own examples
    # write it both ways.
    platform = _as_tuple(
        triggers_raw.get("platform") or meta.get("platform")
    )

    triggers = SkillTriggers(
        domains=_as_tuple(triggers_raw.get("domains")),
        keywords=tuple(k.lower() for k in _as_tuple(triggers_raw.get("keywords"))),
        platform=tuple(p.lower() for p in platform),
        intent=tuple(i.lower() for i in _as_tuple(triggers_raw.get("intent"))),
    )

    safety_raw = reader.get("safety") or {}
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

    # The tier is a models.yml slot, never a model. The compat reader
    # downgrades legacy "provider:model" passthrough values (retired by the
    # Determination rule, §4.3) instead of honoring them; inside our own
    # namespace the three slot names are all that exist.
    tier_raw = reader.get("tier", flat="model")
    tier = str(tier_raw).strip() if tier_raw is not None else "chat"
    if ":" in tier:
        if "tier" in reader._halbert and reader._halbert["tier"] is not None:
            raise SkillParseError(
                f"tier {tier!r} is not one of {TIERS} — the "
                "provider:model passthrough is retired (a skill routes to "
                "a slot; it never names a model)"
            )
        logger.warning(
            "model %r names a model id; the provider:model passthrough is "
            "retired (Determination) — downgrading to the 'chat' tier",
            tier,
        )
        tier = "chat"
    elif tier not in TIERS:
        raise SkillParseError(
            f"tier {tier!r} is not one of {TIERS} "
            "(use 'chat', not the legacy 'orchestrator')"
        )

    priority = str(reader.get("priority") or "normal").strip().lower()
    if priority not in PRIORITIES:
        raise SkillParseError(f"priority {priority!r} is not one of {PRIORITIES}")

    try:
        multiplier = float(reader.get("budget_multiplier", 1.0))
    except (TypeError, ValueError) as e:
        raise SkillParseError(f"budget_multiplier must be a number: {e}") from e

    # CC writes `allowed-tools` with a hyphen (§1.2: "accepted as CC writes
    # it"); the Halbert spelling maps onto the same tuple. CC writes the
    # value as a comma-separated scalar (`allowed-tools: Read, Bash`) as
    # often as a list, so a scalar splits on commas.
    allowed = meta.get("allowed_tools")
    if allowed is None:
        allowed = meta.get("allowed-tools")
    if isinstance(allowed, str):
        allowed = [entry for entry in allowed.split(",")]
    allowed_tools = _as_tuple(allowed) if allowed is not None else None

    kind = str(reader.get("kind") or "ops").strip().lower()
    if kind not in KINDS:
        raise SkillParseError(f"kind {kind!r} is not one of {KINDS}")
    if kind == "lens":
        # A lens is voice only. Anything that could score, scope, route or
        # bind is refused at the boundary rather than silently ignored, so a
        # user file cannot smuggle an ops skill in under a lens's trust.
        carries = []
        if any((triggers.domains, triggers.keywords, triggers.platform, triggers.intent)):
            carries.append("triggers")
        if (reader.get("role") or reader.get("scope")
                or reader.get("knowledge_scope")):
            carries.append("role/scope")
        if safety_raw:
            carries.append("safety")
        if allowed_tools is not None:
            carries.append("allowed_tools")
        if tier_raw is not None or reader.get("subagent"):
            carries.append("tier/subagent")
        if carries:
            raise SkillParseError(
                f"a lens is voice only; {skill_name!r} declares {', '.join(carries)}"
            )

    skill_id = reader.get("id")
    if skill_id is not None:
        skill_id = str(skill_id).strip()
        if not SKILL_ID_RE.fullmatch(skill_id):
            raise SkillParseError(
                f"id {skill_id!r} is not a stable skill id (sk_ + ULID); "
                "ids are stamped at creation, never hand-written"
            )

    state = str(reader.get("state") or "trusted").strip().lower()
    if state not in STATES:
        raise SkillParseError(f"state {state!r} is not one of {STATES}")

    requires = _parse_requires(reader.get("requires"))

    reader.warn()

    return Skill(
        name=skill_name,
        description=str(meta.get("description") or "").strip(),
        aliases=_as_tuple(reader.get("aliases")),
        id=skill_id,
        state=state,
        requires=requires,
        triggers=triggers,
        role=(str(reader.get("role")).strip() if reader.get("role") else None),
        scope=canonical_scope_id(reader.get("scope")),
        knowledge_scope=canonical_scope_id(reader.get("knowledge_scope")),
        trace_expand=bool(reader.get("trace_expand", True)),
        tier=tier,
        priority=priority,
        budget_multiplier=multiplier,
        safety=safety,
        allowed_tools=allowed_tools,
        subagent=bool(reader.get("subagent", False)),
        max_turns=int(reader.get("max_turns", 10)),
        prompt=body,
        source_path=source_path,
        extends=(str(reader.get("extends")).strip()
                  if reader.get("extends") else None),
        kind=kind,
    )


def parse_skill_file(path: Path) -> Skill:
    """Parse a SKILL.md (or <name>.md) from disk, with boundary-safe reads.

    The design's §4.2 rules for reading untrusted skill files live here: a
    hard byte cap, strict UTF-8, and no NUL bytes — a file that fails any of
    them is refused, not best-effort decoded. Realpath confinement under the
    declaring root is the loader's half of the rule (a symlink escape must be
    refused where the root is known, not here).

    The fallback name is the containing directory for `<name>/SKILL.md`, and
    the filename stem otherwise — matching both layouts the design allows.
    """
    raw = Path(path).read_bytes()
    if len(raw) > MAX_SKILL_FILE_BYTES:
        raise SkillParseError(
            f"{path}: file is over the {MAX_SKILL_FILE_BYTES // 1024} KiB "
            f"cap ({len(raw)} bytes)"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SkillParseError(f"{path}: not strict UTF-8: {e}") from e
    if "\x00" in text:
        raise SkillParseError(f"{path}: NUL byte refused")

    fallback = path.parent.name if path.stem.upper() == "SKILL" else path.stem
    try:
        return parse_skill(text, name=fallback, source_path=Path(path))
    except SkillParseError as e:
        raise SkillParseError(f"{path}: {e}") from e