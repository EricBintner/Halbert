# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Deterministic compaction: the T3 v0 rotation writer (A16-G1, FD-3).

``compact_boundaries`` shipped with a schema, an index and no writer.
The typed tree columns were added and never populated, so a long thread
grew until its history was truncated by whatever budget it hit -- and the
part that fell off was the part that had scrolled away, which is exactly
the part a person expects the machine to remember.

FD-3's ruling is a deterministic v0 NOW, with the LLM summary deferred to
the R5 harness gate. So there is no model here, and there will not be one
by accident: the summary is assembled from the turns themselves, keeping
the strings a later question is actually asked with -- the exact command
that was run, the file that was touched, the error text that came back.

A generated summary of a shell session is a paraphrase of the one thing
you cannot paraphrase: "it failed with permission denied on
/etc/nginx/nginx.conf" is the fact, and "there was a permissions problem"
is not the same sentence. So the writer extracts rather than composes.

The guards (A16-G6) are the origin's, and each answers a way a rotation
loop eats itself:

* **cooldown** -- a rotation that just ran does not run again on the next
  turn, however big the thread still looks;
* **merge-max** -- a generation-N summary is folded into N+1 at most so
  many times, so the oldest material is not re-summarised forever;
* **futility** -- a rotation that would not actually shrink anything does
  not happen (A16-G10's no-progress guard);
* **empty** -- a rotation with nothing to say writes no row (A16-G10);
* **clock jump** -- a cooldown measured across a system clock change is
  not a cooldown, so a backwards jump does not license an immediate
  re-rotation.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("halbert.continuity.rotation")

#: The soonest a thread may rotate again (A16-G6). A thread that just
#: compacted has not accumulated anything worth compacting.
COOLDOWN_SECONDS = 300.0

#: How many times a generation may be folded forward. Past this the
#: oldest material stays where it is: re-summarising a summary is how a
#: record turns into a rumour.
MAX_GENERATION = 5

#: A rotation must remove at least this fraction of what it covered, or
#: it is not worth the row it would write (A16-G10's no-progress guard).
MIN_PROGRESS_RATIO = 0.25

#: A clock that moved more than this between two readings is a clock
#: change, not elapsed time.
CLOCK_JUMP_SECONDS = 3600.0

#: How many of each kind of fact a summary keeps. Bounded so a rotation
#: cannot produce something larger than what it replaced.
MAX_FACTS_PER_KIND = 12

_COMMAND_RE = re.compile(r"(?:^|\n)\s*\$\s?(.+)")
_EXIT_RE = re.compile(r"Exit code (-?\d+)")
_PATH_RE = re.compile(r"(?<![\w/])(/[\w.\-/]{3,})")
_ERROR_RE = re.compile(
    r"(?im)^.*\b(error|failed|denied|refused|not found|traceback)\b.*$")


@dataclass(frozen=True)
class RotationRefusal:
    """Why a rotation did not happen. A refusal is a fact, not a silence."""

    reason: str
    detail: str = ""


@dataclass(frozen=True)
class RotationPlan:
    """What one rotation would write."""

    thread_id: str
    generation: int
    summary: str
    covered_message_ids: Tuple[int, ...]
    preserved_message_ids: Tuple[int, ...]
    coverage_end_id: int
    pre_chars: int
    post_chars: int
    trigger: str = "budget"
    trigger_detail: str = ""


def _facts(messages: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
    """The strings a later question is actually asked with.

    Extraction, never composition: a paraphrase of a command is not a
    command, and "there was a permissions problem" is not the sentence
    someone will search for.
    """
    commands: List[str] = []
    paths: List[str] = []
    errors: List[str] = []
    exits: List[str] = []
    for message in messages:
        text = str(message.get("content") or "")
        if not text:
            continue
        for match in _COMMAND_RE.finditer(text):
            line = match.group(1).strip()
            if line and line not in commands:
                commands.append(line)
        for match in _EXIT_RE.finditer(text):
            code = match.group(1)
            if code != "0":
                note = f"exit {code}"
                if note not in exits:
                    exits.append(note)
        for match in _PATH_RE.finditer(text):
            path = match.group(1)
            if path not in paths:
                paths.append(path)
        for match in _ERROR_RE.finditer(text):
            line = match.group(0).strip()
            if line and line not in errors:
                errors.append(line[:200])
    return {
        "commands": commands[:MAX_FACTS_PER_KIND],
        "paths": paths[:MAX_FACTS_PER_KIND],
        "errors": errors[:MAX_FACTS_PER_KIND],
        "exits": exits[:MAX_FACTS_PER_KIND],
    }


def build_summary(messages: Sequence[Dict[str, Any]], generation: int) -> str:
    """The deterministic summary text for one rotation. No model."""
    facts = _facts(messages)
    if not any(facts.values()):
        return ""
    lines = [
        f"[compacted generation {generation}: {len(messages)} earlier "
        f"turns, kept verbatim below]"
    ]
    for label, key in (
        ("Commands run", "commands"),
        ("Files and paths", "paths"),
        ("Errors", "errors"),
        ("Exit codes", "exits"),
    ):
        items = facts[key]
        if not items:
            continue
        lines.append(f"{label}:")
        lines.extend(f"  - {item}" for item in items)
    return "\n".join(lines)


def plan_rotation(
    thread_id: str,
    messages: Sequence[Dict[str, Any]],
    *,
    generation: int = 1,
    keep_recent: int = 10,
    last_rotated_at: Optional[float] = None,
    now: Optional[float] = None,
    trigger: str = "budget",
):
    """A ``RotationPlan``, or a ``RotationRefusal`` saying why not.

    Every guard returns a refusal with a reason rather than ``None``: a
    rotation that quietly does not happen is indistinguishable from one
    that happened and lost everything.
    """
    current = now if now is not None else time.time()
    if generation > MAX_GENERATION:
        return RotationRefusal(
            "merge_max",
            f"generation {generation} is past the {MAX_GENERATION} fold "
            f"limit; re-summarising a summary is how a record becomes a "
            f"rumour",
        )
    if last_rotated_at:
        elapsed = current - float(last_rotated_at)
        if elapsed < 0 or elapsed > CLOCK_JUMP_SECONDS:
            # A16-G6: a cooldown measured across a clock change is not a
            # cooldown. Refuse this round rather than treat the jump as
            # licence to rotate immediately.
            return RotationRefusal(
                "clock_jump",
                f"the clock moved {elapsed:.0f}s between rotations; waiting "
                f"for a reading that means something",
            )
        if elapsed < COOLDOWN_SECONDS:
            return RotationRefusal(
                "cooldown",
                f"last rotation was {elapsed:.0f}s ago (cooldown "
                f"{COOLDOWN_SECONDS:.0f}s)",
            )

    ordered = list(messages)
    if len(ordered) <= keep_recent:
        return RotationRefusal(
            "nothing_to_rotate",
            f"{len(ordered)} messages, keeping the most recent {keep_recent}",
        )
    covered = ordered[:-keep_recent] if keep_recent else ordered
    preserved = ordered[-keep_recent:] if keep_recent else []
    summary = build_summary(covered, generation)
    if not summary:
        # A16-G10: a rotation with nothing to say writes no row. An
        # empty summary that replaced real turns would be a deletion
        # wearing a compaction's name.
        return RotationRefusal(
            "empty_summary",
            "the covered turns carried no command, path, error or exit code",
        )

    pre_chars = sum(len(str(m.get("content") or "")) for m in covered)
    post_chars = len(summary)
    if pre_chars <= 0 or (pre_chars - post_chars) / pre_chars < MIN_PROGRESS_RATIO:
        # A16-G10: a rotation that does not shrink anything is churn --
        # it rewrites history and buys nothing.
        return RotationRefusal(
            "no_progress",
            f"the summary is {post_chars} characters against {pre_chars} "
            f"covered; below the {MIN_PROGRESS_RATIO:.0%} floor",
        )

    covered_ids = tuple(
        int(m["id"]) for m in covered if isinstance(m.get("id"), int))
    preserved_ids = tuple(
        int(m["id"]) for m in preserved if isinstance(m.get("id"), int))
    return RotationPlan(
        thread_id=thread_id,
        generation=generation,
        summary=summary,
        covered_message_ids=covered_ids,
        preserved_message_ids=preserved_ids,
        coverage_end_id=covered_ids[-1] if covered_ids else 0,
        pre_chars=pre_chars,
        post_chars=post_chars,
        trigger=trigger,
        trigger_detail=f"generation {generation}",
    )
