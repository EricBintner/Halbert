# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Scriptable-Apps Prompt Context (A4)

Turns the A3 scriptable-apps discovery results into a concise system-prompt
block so the agent knows which apps are scriptable on this machine and what
commands they support — it no longer has to guess. Consumed by
``AgentPromptBuilder.build_system_prompt`` (both the delegated PromptBuilder
path and the hardcoded fallback path).

Where the data comes from
-------------------------
The stored discovery results only. ``DiscoveryEngine`` keeps discoveries in
memory (populated by scan runs, surfaced through ``get_by_type``); this
injector reads them via the ``get_engine()`` singleton — the same
lazy-singleton pattern ``context/extra_adapters.py`` uses — and NEVER
triggers a scan. The A3 scanner runs in ~0.1s but it is a filesystem walk
over /Applications; putting it on the per-turn prompt path would change the
cost calculus, so A4's decision is: read-only, no scan, no caching layer on
top (the engine's in-memory store already serves repeated reads). When no
scan has run yet there is nothing to inject and the block is empty — that is
the correct answer, not an error.

Bounded strategy (the plan's prompt-bloat risk)
-----------------------------------------------
The block is bounded three ways:

1. ``MAX_APPS`` (8): only the most scriptable apps are listed, ranked by
   command count descending (then name, for determinism). Dropped apps are
   summarized as "(+N more scriptable apps omitted for brevity)".
2. ``MAX_COMMANDS_SHOWN`` (6): each app shows at most 6 command names,
   sampled from the scanner's already-capped ``data["commands"]`` list, with
   the true remainder computed from ``data["command_count"]`` — the scanner
   caps its list at 25 but reports the full count, so "+N more" is honest
   even for large dictionaries. (The scanner's ``chat_context`` samples only
   5 commands by design; it is deliberately NOT used here.)
3. ``MAX_BLOCK_CHARS`` (2048): a hard cap on the whole block, enforced by
   dropping lines from the end if the first two bounds were somehow not
   enough.

Gating (fail closed, mirroring A1's tool registration)
------------------------------------------------------
The block is injected only when all of these hold, checked on every call:

1. Platform is macOS — the tools are not registered elsewhere.
2. ``CAP_APPLESCRIPT`` capability is on (preset / being.yml decision) —
   the plan's required gate.
3. The applescript config switch (``applescript_config.yml`` ``enabled:``,
   re-read every call, never cached — same as A1) is on. Capability-on but
   config-off leaves the tools registered yet refusing every execution, so
   advertising scriptable apps in that state would offer a tool that
   refuses; the cheap file read keeps the prompt honest.

Safety phrasing (A2): the block is factual — which apps are scriptable, use
``run_applescript``. It does not coach around confirmations or describe the
tools as unrestricted; the tool schemas and the HIGH-default risk
classifier own usage and gating.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.prompts.applescript")

#: Maximum number of apps listed individually; the rest are summarized.
MAX_APPS = 8

#: Maximum command names shown per app; the remainder comes from
#: ``data["command_count"]`` as a "+N more" marker.
MAX_COMMANDS_SHOWN = 6

#: Hard cap on the entire injected block.
MAX_BLOCK_CHARS = 2048


class AppleScriptContextInjector:
    """
    Format the latest scriptable-apps discovery results for prompt injection.

    Follows the ``ContextInjector`` pattern: optional engine in the
    constructor (``get_engine()`` singleton fallback), a single formatting
    entry point returning a prompt block — empty string whenever nothing
    should be injected (gate closed, no scan yet, no scriptable apps).
    """

    def __init__(self, discovery_engine: Optional[Any] = None):
        """
        Args:
            discovery_engine: Optional DiscoveryEngine-like object exposing
                ``get_by_type``. Defaults to the ``get_engine()`` singleton,
                resolved lazily on first use.
        """
        self.discovery_engine = discovery_engine

    # ─────────────────────────────────────────────────────────────────────
    # Entry point
    # ─────────────────────────────────────────────────────────────────────

    def get_context(self) -> str:
        """
        Build the scriptable-apps prompt block.

        Returns:
            ``<applescript_context>`` XML block, or "" when any gate is
            closed or there is nothing to report.
        """
        if not self._gates_open():
            return ""
        apps = self._scriptable_apps()
        if not apps:
            return ""
        return self._format(apps)

    # ─────────────────────────────────────────────────────────────────────
    # Gates (fail closed — mirrors register_applescript_tools)
    # ─────────────────────────────────────────────────────────────────────

    def _gates_open(self) -> bool:
        """macOS + CAP_APPLESCRIPT + applescript config enabled."""
        import platform
        if platform.system() != "Darwin":
            return False

        try:
            from ..capabilities import CAP_APPLESCRIPT, has_capability
            if not has_capability(CAP_APPLESCRIPT):
                return False
        except Exception as e:
            logger.debug("CAP_APPLESCRIPT lookup failed, context stays off: %s", e)
            return False

        try:
            from ..config import applescript_config
            if not applescript_config.is_applescript_enabled():
                return False
        except Exception as e:
            logger.debug("Applescript config check failed, context stays off: %s", e)
            return False

        return True

    # ─────────────────────────────────────────────────────────────────────
    # Discovery retrieval (read-only — never triggers a scan)
    # ─────────────────────────────────────────────────────────────────────

    def _engine(self) -> Optional[Any]:
        if self.discovery_engine is not None:
            return self.discovery_engine
        try:
            from ..discovery.engine import get_engine
            return get_engine()
        except Exception as e:
            logger.debug("Discovery engine unavailable: %s", e)
            return None

    def _scriptable_apps(self) -> List[Dict[str, Any]]:
        """
        Extract per-app summaries from the engine's stored APP discoveries.

        Built from each Discovery's ``data`` (the scanner's full, capped
        command list plus the true ``command_count``), never from
        ``chat_context`` which samples only 5 commands by design.
        """
        engine = self._engine()
        if engine is None:
            return []
        try:
            from ..discovery.schema import DiscoveryType
            discoveries = engine.get_by_type(DiscoveryType.APP)
        except Exception as e:
            logger.debug("Failed to read scriptable-app discoveries: %s", e)
            return []

        apps: List[Dict[str, Any]] = []
        seen_names: set = set()
        for d in discoveries:
            data = getattr(d, "data", None) or {}
            name = data.get("app_name") or getattr(d, "name", None)
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            commands = list(data.get("commands") or [])
            command_count = data.get("command_count")
            if not isinstance(command_count, int) or command_count < 0:
                command_count = len(commands)
            apps.append({
                "name": name,
                "commands": commands,
                "command_count": command_count,
                "classes": data.get("classes"),
            })

        # Rank by scriptable surface (command count), then name for a
        # deterministic order across rebuilds.
        apps.sort(key=lambda a: (-a["command_count"], a["name"]))
        return apps

    # ─────────────────────────────────────────────────────────────────────
    # Formatting
    # ─────────────────────────────────────────────────────────────────────

    def _format(self, apps: List[Dict[str, Any]]) -> str:
        """Render the bounded ``<applescript_context>`` block."""
        shown = apps[:MAX_APPS]
        hidden = len(apps) - len(shown)

        lines = [
            "<applescript_context>",
            "You can control scriptable apps on this Mac with the "
            "run_applescript tool (it is safety-gated: risky scripts may "
            "ask for confirmation). Apps found scriptable on this machine:",
        ]
        for app in shown:
            lines.append(f"- {self._app_line(app)}")
        if hidden > 0:
            plural = "s" if hidden != 1 else ""
            lines.append(
                f"(+{hidden} more scriptable app{plural} omitted for brevity)"
            )
        lines.append("</applescript_context>")

        return self._enforce_cap("\n".join(lines))

    @staticmethod
    def _app_line(app: Dict[str, Any]) -> str:
        """One bullet: ``Name (N commands: a, b, ... +M more)``."""
        name = app["name"]
        commands: List[str] = app["commands"]
        count = app["command_count"]
        classes = app.get("classes")

        if not commands:
            classes_part = f", {classes} classes" if isinstance(classes, int) else ""
            return f"{name} (no commands{classes_part})"

        shown = commands[:MAX_COMMANDS_SHOWN]
        more = count - len(shown)
        marker = f" (+{more} more)" if more > 0 else ""
        return f"{name} ({count} commands: {', '.join(shown)}{marker})"

    @staticmethod
    def _enforce_cap(block: str) -> str:
        """Last-resort bound: drop whole lines until the block fits."""
        if len(block) <= MAX_BLOCK_CHARS:
            return block

        note = "...(scriptable-app list truncated)"
        out: List[str] = []
        size = len(note) + 1
        for line in block.split("\n"):
            if size + len(line) + 1 > MAX_BLOCK_CHARS:
                break
            out.append(line)
            size += len(line) + 1
        # The closing tag is the first casualty of a cap this deep — drop
        # it rather than emit a lie about completeness.
        if out and out[-1] == "</applescript_context>":
            out.pop()
        out.append(note)
        logger.warning(
            "Scriptable-apps context exceeded %d chars (%d); truncated",
            MAX_BLOCK_CHARS, len(block),
        )
        return "\n".join(out)