# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The suppression log, and shadow mode (A-HB-25; plan O1 and §4.6).

``the-being.md`` §2 ratifies that nothing appears to the user without a why.
It has a shadow the product cannot answer: **why did I *not* hear about
this?** After attunement, eleven mechanisms can eat a proactive event — the
dial, a category override, quiet hours, safe mode, a snooze, a dismissal, a
withdrawal, a limit floor, a deferred topic, low receptivity, an unreleased
hold — every one of them silent by construction. A warning lost to an
interaction of two is indistinguishable from a warning never generated.

This module lands *before* the engine, recording the legacy gate's own
decisions against stable keys. That is useful on its own: it makes "what
haven't you told me?" answerable today. When ``decide()`` arrives, the same
rows carry the engine's opinion beside the legacy one and the file becomes
shadow mode — decide, log, act on nothing, and read the disagreement over
real days before a single user-visible behaviour changes.

Nothing here may raise into its caller. A suppression log that crashes the
thing it observes is worse than no log.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from .surfaces import ChannelClass

logger = logging.getLogger("halbert.attunement.shadow")

#: Legacy prose from ``ProactiveGate.should_notify`` → stable reason key.
#: The gate's contract is ``(bool, str)`` and is called from several places,
#: so rather than change it we classify what it already says. Keys follow the
#: engine's ``namespace:value[:detail]`` convention so the two logs can be
#: read together.
_REASON_PATTERNS = (
    (re.compile(r"proactivity dial is '(\w+)'"), lambda m: f"dial:{m.group(1)}"),
    (re.compile(r"quiet hours active"), lambda m: "quiet_hours"),
    (re.compile(r"safe mode active"), lambda m: "incident:safe_mode"),
    (re.compile(r"finding snoozed"), lambda m: "standing:defer_topic:snoozed"),
    (re.compile(r"finding dismissed"), lambda m: "standing:defer_topic:dismissed"),
)


def reason_key_for(reason: str) -> str:
    """Map the gate's prose to a stable key.

    An unrecognised reason is keyed as ``unmapped:<slug>`` rather than
    dropped — a suppression nobody can name is exactly the failure this log
    exists to expose, so it must be visible rather than silent.
    """
    if not reason:
        return ""
    for pattern, build in _REASON_PATTERNS:
        match = pattern.search(reason)
        if match:
            return build(match)
    slug = re.sub(r"[^a-z0-9]+", "_", reason.lower()).strip("_")[:40]
    logger.debug("attunement: unmapped suppression reason %r", reason)
    return f"unmapped:{slug}"


class SuppressionRecorder:
    """Writes one row per proactive decision, allowed or suppressed."""

    def __init__(self, store: Any = None, *, persona_id: str = "halbert",
                 subject_id: str = "primary"):
        self.store = store
        self.persona_id = persona_id
        self.subject_id = subject_id

    def record(
        self,
        event: Any,
        *,
        allowed: bool,
        reason: str,
        channel_class: ChannelClass = ChannelClass.PUSH,
    ) -> Optional[str]:
        """Record one decision. Returns the attempt id, or None.

        Never raises: every failure is logged and swallowed.
        """
        if self.store is None:
            return None
        try:
            attempt_id = str(uuid.uuid4())
            key = reason_key_for("" if allowed else reason)
            entry: Dict[str, Any] = {
                "attempt_id": attempt_id,
                "persona_id": self.persona_id,
                "subject_id": self.subject_id,
                "source": getattr(event, "type", "") or "",
                "severity": getattr(event, "severity", "") or "",
                "channel_class": channel_class.value,
                "outcome": "speak" if allowed else "silent",
                "reasons": [key] if key else [],
                "margin": 0.0,
                "context_key": getattr(event, "finding_id", None),
            }
            self.store.record_outcome_raw(entry)
            return attempt_id
        except Exception as exc:
            logger.warning("attunement: could not record decision: %s", exc)
            return None

    def recent_suppressions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """The rows behind "what haven't you told me?"."""
        if self.store is None:
            return []
        try:
            rows = self.store.list_outcomes_raw(
                self.persona_id, subject_id=self.subject_id, limit=limit * 4
            )
        except Exception as exc:
            logger.warning("attunement: could not read suppressions: %s", exc)
            return []
        return [r for r in rows if r.get("outcome") != "speak"][:limit]
