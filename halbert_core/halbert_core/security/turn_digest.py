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
import re
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


#: How many per-effect lines a digest renders before it says "and N
#: more" (A05-G8). A turn that wrote forty files spoke forty lines --
#: which is not accountability, it is noise a person stops hearing.
MAX_DIGEST_LINES = 12

#: The statuses an effect can carry (A05-G9). The digest recorded only
#: SUCCESSES, and ``run_command`` returning a non-zero exit code IS a
#: success at the executor's seam -- so "I restarted sshd" was spoken
#: for a command that failed.
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_STARTED = "started"
DIGEST_STATUSES = (STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED, STATUS_STARTED)


def status_for_result(success: bool, result: Any) -> str:
    """The digest status for one tool result (A05-G9 + bug 6).

    ``ExecutionResult.success`` means "the tool ran without raising",
    which for ``run_command`` is true of a command that ran and returned
    1. The executor's own result string opens with "Exit code N" in that
    case, so the exit code is readable without asking the executor to
    parse tool-specific output (the packet's STOP condition).
    """
    if not success:
        return STATUS_FAILED
    text = result if isinstance(result, str) else ""
    match = re.match(r"Exit code (-?\d+)", text)
    if match and int(match.group(1)) != 0:
        return STATUS_FAILED
    return STATUS_DONE


class TurnDigest:
    """Per-turn list of write-plane effects, redacted by shape."""

    def __init__(self) -> None:
        self._effects: List[Tuple[str, str, str]] = []

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        tool: str,
        target: str = "",
        raw_args: Any = None,
        status: str = STATUS_DONE,
    ) -> None:
        """Record one write-plane effect and what became of it.

        ``raw_args`` is accepted and deliberately dropped: callers hold
        the real arguments (the executor does) and the signature makes
        the non-negotiable visible — no raw argument text ever enters
        the digest, so no future edit can "just log the command" into a
        string that gets spoken and rendered.

        ``status`` is A05-G9: only successes used to be recorded, so a
        turn that tried and failed reported nothing, and a command that
        returned non-zero reported success.
        """
        del raw_args  # never stored, never summarized
        cleaned = self._redact(target)
        if status not in DIGEST_STATUSES:
            status = STATUS_DONE
        self._effects.append((str(tool or "?"), cleaned, status))

    @staticmethod
    def _redact(target: Any) -> str:
        """Redact and truncate a target. Never raises; never returns None."""
        # A05-G10: a binary payload rendered as its own length in
        # characters of noise -- spoken aloud, and written to the audit
        # rollup. It is a fact about a payload, not the payload.
        if isinstance(target, (bytes, bytearray, memoryview)):
            return f"<{len(bytes(target))} bytes of binary>"
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
        statuses: Dict[str, int] = {}
        for tool, _target, status in self._effects:
            counts[tool] = counts.get(tool, 0) + 1
            statuses[status] = statuses.get(status, 0) + 1
        n = len(self._effects)
        head = "{} effect{}: {}".format(
            n,
            "" if n == 1 else "s",
            ", ".join(f"{tool} ×{count}" for tool, count in counts.items()),
        )
        # A05-G9: what became of them, on the line a person hears first.
        outcomes = ", ".join(
            f"{count} {status}" for status, count in sorted(statuses.items())
            if status != STATUS_DONE
        )
        if outcomes:
            head = f"{head} ({outcomes})"
        lines = [head]
        # A05-G8: bounded. Forty lines is not accountability, it is noise
        # a person stops hearing -- and the count line above already
        # carries the total, so nothing is hidden by the cap.
        shown = self._effects[:MAX_DIGEST_LINES]
        for tool, target, status in shown:
            suffix = "" if status == STATUS_DONE else f" [{status}]"
            lines.append(
                f"{tool}: {target}{suffix}" if target else f"{tool}{suffix}")
        remaining = n - len(shown)
        if remaining > 0:
            lines.append(f"and {remaining} more")
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


def record_effect(
    tool_name: str,
    args: Optional[Dict[str, Any]],
    status: str = STATUS_DONE,
) -> None:
    """Record a write-plane effect into the current turn's digest.

    A05-G9: this recorded successes only, so a turn that TRIED and
    failed reported nothing at all — and the tail said "no side effects"
    for a turn that had just been refused halfway through a restart.
    ``status`` is what became of it.

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
            status=status,
        )
    except Exception as e:
        logger.debug(f"turn digest record failed (non-fatal): {e}")


def _scrubbed_summary(digest: Optional[TurnDigest]) -> Optional[str]:
    """The digest's summary, through the one egress seam (A05 bug 7).

    The digest redacts its TARGETS by shape, which is not the same as
    passing the finished line through the seam every other user-visible
    string goes through: the tail was spoken and written to the audit
    rollup without ever meeting the echo guard or the exact-value
    registry.
    """
    if digest is None or digest.is_empty():
        return None
    from .scrub import scrub_for_egress

    return scrub_for_egress(digest.summary(), surface="turn_digest") or None


def spoken_tail(digest: Optional[TurnDigest], modality: Optional[str]) -> Optional[str]:
    """The digest line to speak at the end of a turn, or None.

    Voice turns only: the tail is accountability for what a spoken
    command did, spoken back while the user can still hear it. Text
    turns keep their effects in the audit chain and the receipt —
    appending a spoken tail to a typed turn is noise.
    """
    if (modality or "text") != "voice":
        return None
    return _scrubbed_summary(digest)


def audit_rollup(digest: Optional[TurnDigest]) -> Optional[str]:
    """The digest line written to the hash-chained audit log.

    The SAME string the tail speaks, scrubbed the same way: scrubbing
    one and not the other would put the raw value in the log instead of
    in the room, which is not an improvement.
    """
    return _scrubbed_summary(digest)