# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Reserved names — names a skill may not claim.

Design §2.4: reserved = registered tool names + intake slash builtins +
persona handback names, "checked at load and at create — refused at
spec-build, the same posture as the loader's builtin-name refusal." A skill
claiming a tool's name would be reachable as `/<name>` once the slash channel
lands, and a user typing it would mean the tool, not the skill.

Skill names spell separators with hyphens while the tool registry uses
underscores, so the comparison normalizes both spellings — otherwise the
check is theater.

The tool names are collected lazily (never at import of this package: the
skills loader must not pull the tools/persona packages into every embedder)
from the schema registries the tool surface already exports.

A13-G13: the static half is not the whole set, and "tool registration is
static per process" -- which is what the process-wide cache used to rest on
-- was simply false. Home Assistant registers two tools, Frigate six, and
an MCP server publishes whatever it likes through the bridge, all of them
after this module has been imported and some after skills have already been
loaded once. So the static half stays cached (it really is static) and a
LIVE half is asked on every call: the MCP tool registry by default, plus
whatever sources the daemon registers -- its own executor, at the wiring
site. A skill named after a runtime tool is the worst kind of name trap:
the user types the name meaning the tool that turns the lights off.
"""

from __future__ import annotations

import functools
import importlib
import logging
from typing import Callable, FrozenSet, Iterable, List, Optional

logger = logging.getLogger(__name__)

#: Slash commands Halbert surfaces already claim. The dashboard composer owns
#: `/model` (dashboard/frontend/src/lib/slashCommands.ts) and the terminal
#: page owns /explain, /fix and /dryrun with single-letter aliases
#: (dashboard/frontend/src/pages/Terminal.tsx). The skill slash channel (SK-2)
#: must not let a skill shadow a command the user already knows.
RESERVED_SLASH_BUILTINS: FrozenSet[str] = frozenset({
    "model",
    "explain", "e",
    "fix", "f",
    "dryrun", "d",
})

#: The executor's unconditional core, registered inline in
#: `ToolExecutor._register_builtins` (tools/executor.py). Hand-listed because
#: the executor registers them from literals; `test_skills_reserved` pins
#: this list against a live executor so drift is caught in CI, not by a
#: production refusal — or worse, a missing one.
CORE_TOOL_NAMES: FrozenSet[str] = frozenset({
    "run_command", "read_file", "write_file", "list_directory",
    "terminal_blocks", "recall_memory",
    "new_thread", "recall_thread", "resume_thread",
    "execute_code",
})

#: Names registered only while a switch or capability is on, but claimed
#: surfaces regardless: a skill named after a tool nobody can currently see
#: is still a name trap.
CONDITIONAL_TOOL_NAMES: FrozenSet[str] = frozenset({"web_search"})

#: Schema registries (dict of tool name -> schema) and single-name constants
#: to absorb lazily. A module that fails to import costs its names, never
#: skill loading — the log says so.
_SCHEMA_REGISTRIES = (
    ("halbert_core.tools.system_info", "SYSTEM_TOOL_SCHEMAS"),
    ("halbert_core.tools.vision_tools", "VISION_TOOL_SCHEMAS"),
    ("halbert_core.tools.gpu_tools", "GPU_TOOL_SCHEMAS"),
    ("halbert_core.tools.accelerator_tools", "ACCELERATOR_TOOL_SCHEMAS"),
    ("halbert_core.persona.guest_tools", "GUEST_ONLY_TOOLS"),
)
_TOOL_NAME_CONSTANTS = (
    ("halbert_core.persona.become_tool", "BECOME_TOOL_NAME"),
    ("halbert_core.persona.guest_tools", "HANDBACK_TOOL_NAME"),
)


def normalize_skill_name(name: Optional[str]) -> str:
    """The form reserved names compare in: trimmed, lowered, underscores."""
    return (name or "").strip().lower().replace("-", "_")


def _collect_tool_names() -> FrozenSet[str]:
    names = set(CORE_TOOL_NAMES) | set(CONDITIONAL_TOOL_NAMES)
    for module, attr in _SCHEMA_REGISTRIES:
        try:
            registry = getattr(importlib.import_module(module), attr, None)
        except Exception:
            logger.debug(
                "reserved skill-name scan: %s did not import; its tool "
                "names are not reserved this process", module, exc_info=True,
            )
            continue
        if isinstance(registry, dict):
            names.update(registry)
        elif isinstance(registry, Iterable):
            names.update(registry)
    for module, attr in _TOOL_NAME_CONSTANTS:
        try:
            value = getattr(importlib.import_module(module), attr, None)
        except Exception:
            logger.debug(
                "reserved skill-name scan: %s did not import; %s is not "
                "reserved this process", module, attr, exc_info=True,
            )
            continue
        if isinstance(value, str) and value.strip():
            names.add(value.strip())
    return frozenset(names)


#: Callables returning names registered at runtime. Registered by the
#: daemon (its executor) and seeded with the MCP bridge, which needs no
#: wiring because the registry is already a process global.
_LIVE_SOURCES: List[Callable[[], Iterable[str]]] = []


def _mcp_tool_names() -> Iterable[str]:
    from ..mcp.registry import get_tool_registry

    return get_tool_registry().names()


def add_live_tool_source(source: Callable[[], Iterable[str]]) -> None:
    """Register a callable that reports currently-registered tool names.

    Idempotent on the callable object: the daemon's wiring runs once, but
    a re-entry (a test, a rebuilt agent) must not stack duplicates.
    """
    if source not in _LIVE_SOURCES:
        _LIVE_SOURCES.append(source)


def clear_live_tool_sources() -> None:
    """Drop every registered source (tests, and a deliberate rewire)."""
    _LIVE_SOURCES.clear()


def live_tool_names() -> FrozenSet[str]:
    """Names registered at runtime, right now.

    Not cached, deliberately: the cache is what the gap was. A source that
    raises costs its own names and nothing else -- refusing to load skills
    because a tool surface is unhealthy would be a worse failure than the
    name collision this guards against.
    """
    names = set()
    for source in (_mcp_tool_names, *_LIVE_SOURCES):
        try:
            reported = source()
        except Exception:
            logger.debug("reserved skill-name scan: a live tool source "
                         "failed; its names are not reserved this call",
                         exc_info=True)
            continue
        for name in reported or ():
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
    return frozenset(names)


@functools.lru_cache(maxsize=1)
def _static_reserved_names() -> FrozenSet[str]:
    """The half that really is static: hand-listed cores, slash builtins,
    and the schema registries the tool surface exports at import."""
    tools = {normalize_skill_name(n) for n in _collect_tool_names()}
    slash = {normalize_skill_name(n) for n in RESERVED_SLASH_BUILTINS}
    return frozenset(tools | slash)


def reserved_skill_names() -> FrozenSet[str]:
    """Every reserved name, normalized for comparison."""
    live = {normalize_skill_name(n) for n in live_tool_names()}
    return frozenset(_static_reserved_names() | live)


def is_reserved_skill_name(name: Optional[str]) -> bool:
    """True when *name* (or its underscore spelling) is reserved."""
    return normalize_skill_name(name) in reserved_skill_names()