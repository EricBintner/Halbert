# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Packet 04 B1: turn-scoped mutation digest.

OpenClaw records every voice call durably with a digest of the tool
effects that happened during it — evidence for "what did you just do to
my files?". Halbert's write-plane tools already write the hash-chained
audit log (``obs.audit``); this module is the *turn-scoped rollup*: one
per-turn object a voice reply can speak and the audit log can carry,
assembled from what the tool executor did during the turn.

Redaction is the whole point of the shape: the digest holds
``(tool, redacted_target)`` pairs ONLY. Raw tool arguments never enter
it — a ``write_file`` call's ``contents`` is the loudest payload on any
turn, and this text is spoken aloud and shown on the subtitle ribbon.
Targets pass through the same ``redact_text()`` the rest of the egress
paths use, then truncate: a name is enough to ask about, the content is
in the audit chain already.

The digest reaches the executor through a ContextVar set by
``AgentStateMachine.process()`` — the same pattern as
``current_agent_session`` in the terminal bridge. Tool calls run in
tasks spawned inside the turn (``asyncio.ensure_future`` copies the
context at creation), so a write-plane success anywhere in the turn
records into the turn's digest without threading a parameter through
every registered handler. Nothing bound (executor used outside a turn,
or a caller that never set one) is a no-op — the digest is a
reportability feature, never a gate.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("halbert.security.turn_digest")

# How much of a redacted target the digest keeps. A target is a name to
# ask about afterwards ("the write to /etc/hosts"), not content.
_MAX_TARGET_CHARS = 120

# Where each write-plane tool's "what did it touch" lives in its args.
# run_command is handled separately (argv head only).
_TARGET_KEYS: Dict[str, str] = {
    "write_file": "path",
    "write_config": "path",
    "schedule_cron": "name",
    "terminal_blocks": "session_id",
}

# The current turn's digest, or None outside a turn.
current_turn_digest: ContextVar[Optional["TurnDigest"]] = ContextVar(
    "halbert_current_turn_digest", default=None
)


class TurnDigest:
    """Per-turn list of successful write-plane effects, redacted by shape."""

    def __init__(self) -> None:
        self._effects: List[Tuple[str, str]] = []

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        tool: str,
        target: str = "",
        raw_args: Any = None,
    ) -> None:
        """Record one successful write-plane effect.

        ``raw_args`` is accepted and deliberately dropped: callers hold
        the real arguments (the executor does) and the signature makes
        the non-negotiable visible — no raw argument text ever enters
        the digest, so no future edit can "just log the command" into a
        string that gets spoken and rendered.
        """
        del raw_args  # never stored, never summarized
        cleaned = self._redact(target)
        self._effects.append((str(tool or "?"), cleaned))

    @staticmethod
    def _redact(target: Any) -> str:
        """Redact and truncate a target. Never raises; never returns None."""
        try:
            from ..ingestion.redaction import redact_text

            cleaned = redact_text(str(target or ""))
        except Exception as e:  # redaction is a choke point, not a gate
            logger.debug(f"turn digest target redaction failed: {e}")
            cleaned = str(target or "")
        return cleaned[:_MAX_TARGET_CHARS]

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._effects)

    def is_empty(self) -> bool:
        return not self._effects

    def summary(self) -> str:
        """One count line, then one redacted line per effect.

        ``2 effects: write_file ×1, run_command ×1`` followed by the
        per-effect targets — the shape a voice reply can speak at the
        end of a turn ("two effects: one write to /etc/hosts...").
        """
        if not self._effects:
            return "no side effects"
        counts: Dict[str, int] = {}
        for tool, _target in self._effects:
            counts[tool] = counts.get(tool, 0) + 1
        n = len(self._effects)
        head = "{} effect{}: {}".format(
            n,
            "" if n == 1 else "s",
            ", ".join(f"{tool} ×{count}" for tool, count in counts.items()),
        )
        lines = [head]
        for tool, target in self._effects:
            lines.append(f"{tool}: {target}" if target else tool)
        return "\n".join(lines)


# ----------------------------------------------------------------------
# Executor-side helpers
# ----------------------------------------------------------------------

def target_for_tool(tool_name: str, args: Optional[Dict[str, Any]]) -> str:
    """The short 'what did it touch' for a write-plane tool's arguments.

    Commands reduce to the argv head only — the program name says what
    ran without carrying whatever it was told. Other tools name the
    object they touched. Missing args are empty, never an error.
    """
    args = args or {}
    if tool_name == "run_command":
        command = str(args.get("command") or "")
        first_line = command.splitlines()[0] if command else ""
        words = first_line.split()
        return words[0] if words else ""
    key = _TARGET_KEYS.get(tool_name)
    if not key:
        return ""
    value = args.get(key)
    return str(value) if value is not None else ""


def record_effect(tool_name: str, args: Optional[Dict[str, Any]]) -> None:
    """Record a successful write-plane effect into the current turn's digest.

    No-op when no turn digest is bound. Never raises: the digest is a
    reportability feature and must not turn a successful tool into a
    failed one.
    """
    digest = current_turn_digest.get()
    if digest is None:
        return
    try:
        digest.record(
            tool=tool_name,
            target=target_for_tool(tool_name, args),
            raw_args=args,
        )
    except Exception as e:
        logger.debug(f"turn digest record failed (non-fatal): {e}")


def spoken_tail(digest: Optional[TurnDigest], modality: Optional[str]) -> Optional[str]:
    """The digest line to speak at the end of a turn, or None.

    Voice turns only: the tail is accountability for what a spoken
    command did, spoken back while the user can still hear it. Text
    turns keep their effects in the audit chain and the receipt —
    appending a spoken tail to a typed turn is noise.
    """
    if digest is None or (modality or "text") != "voice":
        return None
    if digest.is_empty():
        return None
    return digest.summary()