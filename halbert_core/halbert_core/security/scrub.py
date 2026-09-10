# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The one scrub seam every user-visible string passes through.

A05-G4 and R-05 Phase E. This function existed twice: as
``AgentStateMachine._echo_guard_egress`` and as
``turn_event_tee._scrub_text``, the second carrying a comment saying it
"mirrors" the first "so the tee does not import the state machine to
reach a staticmethod". Two copies of a security seam drift, and the one
that drifts is the one nobody is looking at. It lives here now, where
neither module has to reach into the other.

What it does, in order:

1. Ask the echo guard whether this text reproduces material Halbert
   deliberately injected (an acknowledged config egress, a file the
   owner asked to be read aloud). A match means the model echoed context
   it should have paraphrased.
2. On a match, log ONE structured line carrying a hash of the matched
   material and never the material.
3. Redact through the guard, then through the exact-value registry.
4. If the text was flagged and nothing changed, SUPPRESS it. A guard
   that says "this contains a secret" and a redactor that removes
   nothing is not permission to send.

**Fail closed.** The previous seams were "non-fatal by construction": any
failure inside the guard returned the text RAW, on the reasoning that a
guard failure must never cost the user their answer. But a scrub that
cannot run is not evidence that there was nothing to scrub, and the one
case where the machinery breaks is the case where nobody is watching.
A failure yields a deterministic notice instead -- the user learns
something happened, which is what an empty string does not tell them.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger("halbert.security.scrub")

#: What a surface shows when the scrub itself could not run. Deterministic
#: shipped text: an explanation of a refusal that is itself generated is
#: an unfalsifiable explanation.
SCRUB_FAILED_NOTICE = (
    "[withheld: I could not check this text for material that should not "
    "leave the machine, so I am not sending it.]"
)


def scrub_for_egress(
    text: str,
    *,
    surface: str,
    session_id: str = "",
    request_id: str = "",
    guard=None,
    registry=None,
) -> str:
    """Scrub one string on its way to a person, a log, or another process.

    ``surface`` names where it is going ("reply", "tee", "tool_display",
    "spoken_tail", "audit_rollup", "error", "confirmation") and appears
    in the warning, so a flagged echo is attributable to the seam it
    tried to leave by.

    ``guard`` and ``registry`` are injection points for tests; production
    passes neither and gets the process-global pair.
    """
    if not text:
        return text
    try:
        if guard is None:
            from .echo_guard import get_global_echo_guard
            guard = get_global_echo_guard()
        if registry is None:
            from ..ingestion.redaction_registry import get_global_registry
            registry = get_global_registry()

        matched = guard.find_match(text)
        if matched is None:
            # Not an echo -- but the registry still gets its pass: a
            # value can reach a surface without ever having been
            # injected as context.
            return registry.redact_text(text)

        redacted = registry.redact_text(guard.redact(text))
        changed = redacted != text
        logger.warning(
            json.dumps({
                "event": "echo_guard_flagged",
                "surface": surface,
                "session_id": session_id or None,
                "request_id": request_id or None,
                "match_sha256": hashlib.sha256(
                    matched.encode("utf-8")).hexdigest(),
                "matched_chars": len(matched),
                "payload_chars": len(text),
                # A05 bug 1: the truth, not a constant. This said
                # `redacted: true` unconditionally while the redaction
                # was a no-op on partial echoes.
                "redacted": changed,
                "suppressed": not changed,
            })
        )
        if not changed:
            # Flagged and unchanged: the guard says this contains
            # injected material and nothing removed it. That is not
            # permission to send.
            return ""
        return redacted
    except Exception as e:
        logger.error(
            "scrub seam failed for surface=%s (%s); withholding the text "
            "rather than sending it unchecked", surface, e,
        )
        return SCRUB_FAILED_NOTICE
