# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Proactive gate — decides whether a proactive event should be shown to the user.

Checks the proactivity dial, quiet hours, category overrides, guardrails,
snooze state, and dismissal state before allowing an event through.

Phase 7 / T7c.1.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from typing import Tuple

from ..config.being_config import BeingConfig
from ..autonomy.guardrails import GuardrailEnforcer
from ..findings.store import FindingStore, FindingStatus, parse_timestamp
from .events import ProactiveEvent

logger = logging.getLogger(__name__)


# Severity ranking for comparison
_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}

# Proactivity dial → minimum severity required
_PROACTIVITY_THRESHOLD = {
    "off": 99,  # nothing passes
    "quiet": 2,  # critical only
    "balanced": 1,  # warning + critical
    "assertive": 0,  # everything
}


class ProactiveGate:
    """Decides whether a proactive event should reach the user.

    Returns (should_notify, reason_if_suppressed).
    """

    def __init__(
        self,
        being_config: BeingConfig,
        guardrail_enforcer: GuardrailEnforcer | None = None,
        finding_store: FindingStore | None = None,
    ):
        self.config = being_config
        self.guardrails = guardrail_enforcer
        self.findings = finding_store

    def should_notify(self, event: ProactiveEvent) -> Tuple[bool, str]:
        """Check if an event should be shown to the user.

        Returns:
            (True, "") if the event should be shown.
            (False, reason) if the event should be suppressed.
        """
        # 1. Check proactivity dial — a per-category override wins over the
        #    global dial when one exists for this event's category.
        overrides = getattr(self.config, "category_overrides", None) or {}
        category = getattr(event, "category", None) or "general"
        dial = overrides.get(category) or self.config.proactivity
        min_severity = _PROACTIVITY_THRESHOLD.get(dial, 1)
        event_severity = _SEVERITY_ORDER.get(event.severity, 0)

        if event_severity < min_severity:
            return False, f"proactivity dial is '{dial}' (requires severity >= {min_severity})"

        # 2. Check quiet hours (suppress non-critical)
        if self.config.quiet_hours and event.severity != "critical":
            if self._in_quiet_hours():
                return False, "quiet hours active (non-critical suppressed)"

        # 3. Check guardrails (safe mode suppresses non-critical)
        if (
            self.guardrails is not None
            and self.guardrails.safe_mode_active
            and event.severity != "critical"
        ):
            return False, "safe mode active (non-critical suppressed)"

        # 4. Check snooze and dismissal for finding-linked events
        if event.finding_id and self.findings:
            finding = self.findings.get(event.finding_id)
            if finding:
                if finding.status == FindingStatus.SNOOZED.value:
                    # Suppress only while the snooze is still active —
                    # an expired snooze lets the event through again.
                    snoozed_until = parse_timestamp(finding.snoozed_until)
                    if snoozed_until and datetime.now(timezone.utc) < snoozed_until:
                        return False, f"finding snoozed until {finding.snoozed_until}"

                if finding.status == FindingStatus.DISMISSED.value:
                    return False, f"finding dismissed: {finding.dismissed_reason}"

        # 5. All checks passed
        return True, ""

    def _in_quiet_hours(self) -> bool:
        """Check if the current time is within quiet hours."""
        if not self.config.quiet_hours:
            return False

        start_str = self.config.quiet_hours.get("start")
        end_str = self.config.quiet_hours.get("end")
        if not start_str or not end_str:
            return False

        try:
            now = datetime.now().time()
            start = time.fromisoformat(start_str)
            end = time.fromisoformat(end_str)

            if start <= end:
                # Same day range (e.g., 14:00 - 18:00)
                return start <= now <= end
            else:
                # Overnight range (e.g., 22:00 - 07:00)
                return now >= start or now <= end
        except ValueError:
            logger.warning(f"Invalid quiet hours format: {self.config.quiet_hours}")
            return False
