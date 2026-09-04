# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""``recall_memory`` — answer "why is X the way it is" from the change ledger.

Until now this name was routed to a generic search and the result annotated
"not implemented", because a model told that recall succeeded and returned
nothing concludes that nothing is remembered and tells the user so — a claim
the turn has no basis for.

The rule that replaces that annotation has to appear in two places, and does:
in the schema description, which the model reads before calling, and in the
returned string, which is what reaches ``ctx.observations`` and is therefore
the only thing present when the answer is actually composed. A rule stated
only in the schema is absent at the moment it matters.

Everything here is deterministic. No model, no ranking, no search.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..continuity.provenance import FILE_CONTENT_PREDICATE
from ..continuity.recall import (
    LedgerUnavailable,
    matching_subjects,
    predicates_for,
    recall_state,
    recorded_subjects,
)
from ..continuity.state_store import UNRECORDED

logger = logging.getLogger("halbert.tools.recall_memory")

__all__ = ["RECALL_MEMORY_SCHEMA", "recall_memory"]

#: Keep well inside ``_TOOL_RESULT_CHARS`` (2000), so the truncation eats
#: nothing — a cut landing just after "reason:" leaves a dangling half-reason
#: in the prompt, which is the exact shape the provenance rule forbids.
_MAX_HISTORY = 8

RECALL_MEMORY_SCHEMA = {
    "name": "recall_memory",
    "description": (
        "Answer why a file, service or machine fact is the way it is, from the "
        "change ledger: its current value, what it was before, who changed it, "
        "when, and the reason recorded at the time. "
        "If it answers that there is no record, that means nothing was recorded "
        "for it — it does NOT mean nothing changed. Say so in those terms; never "
        "report an empty answer as evidence that the thing is unchanged, and "
        "never supply a reason of your own for a change the ledger did not record."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string",
                     "description": "A file, e.g. /etc/ssh/sshd_config"},
            "subject": {"type": "string",
                        "description": "An explicit subject, e.g. service:sshd, "
                                       "disk:nvme0n1, system, user, thread:<id>"},
            "predicate": {"type": "string",
                          "description": f"Defaults to {FILE_CONTENT_PREDICATE} "
                                         "(a file's content). Others include "
                                         "service_status, disk_health, cpu_load, "
                                         "mode_octal."},
            "query": {"type": "string",
                      "description": "Free text, when you do not know the exact "
                                     "subject. Lists matching subjects to choose "
                                     "from; it does not guess one."},
            "history": {"type": "boolean",
                        "description": "Include earlier values, newest first."},
        },
        "required": [],
    },
}

#: Said on every abstain path, in these words. The distinction it draws is
#: the entire point of the tool: a model that reads an empty answer as
#: "unchanged" will tell someone their config is untouched when the truth is
#: that nobody wrote down what happened to it.
_RIDER = "this does not mean nothing changed."

_ABSTAIN = (
    "No record for {subject} ({predicate}) in the change ledger. "
    "Nothing was recorded here — " + _RIDER
)

_EMPTY_LEDGER = (
    "The change ledger is empty — nothing has been recorded yet. " + _RIDER
)


def _unavailable(err: object) -> str:
    return (f"The change ledger could not be read: {err}. "
            f"This is a failure to look, not an absence of records — no "
            f"conclusion about what changed can be drawn from it.")


def _more(shown: list, total: int) -> str:
    """Say when a list is partial, rather than letting it read as complete."""
    return f" (showing {len(shown)} of {total})" if total > len(shown) else ""


def _when(ts: Optional[float]) -> str:
    if ts is None:
        return "now"
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(ts)


def _value(predicate: str, obj: str) -> str:
    """Digests are abbreviated; every other predicate's value is printed whole."""
    if predicate == FILE_CONTENT_PREDICATE and len(obj) == 64:
        return f"{obj[:12]}…"
    return obj


#: A single reason may not eat the whole observation budget. Cut with an
#: explicit marker rather than letting _format_tool_observation truncate at
#: 2000 chars, which can land mid-word -- and a reason that stops mid-sentence
#: reads as though that is all that was said.
_MAX_REASON_CHARS = 240


def _clip(text: str, limit: int = _MAX_REASON_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "… (truncated)"


def _reason(row: Dict[str, Any]) -> str:
    """Never blank, never the bare token.

    An absent field is the one a model fills in, and a bare "unrecorded"
    invites paraphrase into something plausible.
    """
    reason = (row.get("reason") or "").strip()
    if not reason or reason == UNRECORDED:
        return "reason: not recorded (none was captured at the time)"
    return f"reason: {_clip(reason)}"


def _render_row(predicate: str, row: Dict[str, Any], label: str) -> List[str]:
    return [
        f"{label}: {_value(predicate, row.get('object', ''))}"
        f"  (since {_when(row.get('valid_from'))})",
        f"  changed by: {row.get('actor') or 'unknown'}"
        f"  via {row.get('source') or 'unknown'}"
        + (f"  [request {row['request_id']}]" if row.get("request_id") else ""),
        f"  {_reason(row)}",
    ]


def _render(result: Dict[str, Any]) -> str:
    subject, predicate = result["subject"], result["predicate"]
    if not result["found"]:
        return _ABSTAIN.format(subject=subject, predicate=predicate)

    lines = [f"Change ledger — {subject} ({predicate})"]
    current, superseded = result.get("current"), result.get("superseded")
    if current:
        lines += _render_row(predicate, current, "now")
    else:
        lines.append("now: no open value (it was invalidated)")
    if superseded:
        lines.append("")
        lines += _render_row(predicate, superseded, "before that")

    history = result.get("history") or []
    # Identify a row by fields to_dict actually emits. Comparing on "id"
    # silently matched None to None for every row, so history rendered
    # nothing at all while the parameter looked supported.
    def _key(row):
        return (row.get("valid_from"), row.get("object"), row.get("request_id"))

    extra = [h for h in history if not current or _key(h) != _key(current)]
    if extra:
        lines.append("")
        lines.append("earlier values, newest first:")
        for row in extra[:_MAX_HISTORY]:
            lines.append(
                f"  {_when(row.get('valid_from'))}: "
                f"{_value(predicate, row.get('object', ''))} "
                f"({row.get('actor') or 'unknown'}) — {_reason(row)[8:]}"
            )
    return "\n".join(lines)


def _choose_from(candidates: List[Any], subject_only: bool = False) -> str:
    listed = "\n".join(
        f"  - {c}" if subject_only else f"  - {c[0]} ({c[1]})"
        for c in candidates
    )
    return listed


async def recall_memory(args: Dict[str, Any]) -> str:
    """Deterministic dispatch. Never falls through to a search."""
    path = (args.get("path") or "").strip()
    subject = (args.get("subject") or "").strip()
    predicate = (args.get("predicate") or FILE_CONTENT_PREDICATE).strip()
    query = (args.get("query") or "").strip()
    history = bool(args.get("history"))

    try:
        if path or subject:
            result = recall_state(
                subject=subject or None, path=path or None,
                predicate=predicate, include_history=history,
                history_limit=_MAX_HISTORY,
            )
            if result["found"]:
                return _render(result)
            # The subject may be real and the predicate wrong. Abstaining
            # outright on a subject the ledger plainly knows is a lie by
            # omission, so name what it does hold.
            held = predicates_for(result["subject"])
            if held:
                return (
                    f"No {predicate} recorded for {result['subject']}, but the "
                    f"change ledger does hold: {', '.join(held)}. "
                    f"Ask again with one of those as the predicate. "
                    f"Nothing was recorded under {predicate} — {_RIDER}"
                )
            return _render(result)

        if query:
            matches = matching_subjects(query)
            if matches:
                return (
                    f"The change ledger holds these subjects matching "
                    f"'{query}':\n{_choose_from(matches)}\n"
                    f"Ask again with one of them as the subject."
                )
            known, total = recorded_subjects()
            if not known:
                return _EMPTY_LEDGER
            return (
                f"Nothing in the change ledger matches '{query}' — {_RIDER} "
                f"It currently holds{_more(known, total)}:\n"
                f"{_choose_from(known, subject_only=True)}"
            )

        known, total = recorded_subjects()
        if not known:
            return _EMPTY_LEDGER
        return (f"The change ledger holds these subjects{_more(known, total)}:\n"
                f"{_choose_from(known, subject_only=True)}\n"
                "Ask again with one of them as the subject, or a path.")

    except LedgerUnavailable as e:
        # Never an empty success: "I could not look" is not "there is nothing".
        return _unavailable(e)
    except Exception as e:
        # Backstop. Anything that reaches here is still a failure to look,
        # and must not reach the model as an empty answer -- which is what
        # an uncaught exception out of a tool handler eventually becomes.
        logger.warning(f"recall_memory failed unexpectedly: {e}")
        return _unavailable(e)
