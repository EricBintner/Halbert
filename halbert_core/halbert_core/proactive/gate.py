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

        Phase 2.5: the quiet-hours check delegates to the engine's
        ``should_speak_proactively()`` when the modality engine is
        available, which applies the ``QuietHoursPolicy`` with
        life-safety bypass (B2). Falls back to the local quiet-hours
        check when the engine is not installed.
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

        # 2. Check quiet hours — delegate to the engine's
        #    should_speak_proactively() when available (applies
        #    QuietHoursPolicy with life-safety bypass B2). Fall back to
        #    the local check when the engine is not installed. Confirmed
        #    acoustic anomalies (O5) are life-safety too and bypass like
        #    "critical" — see _is_wake_worthy_acoustic().
        if event.severity != "critical" and not self._is_wake_worthy_acoustic(event):
            quiet_active = self._check_quiet_hours_engine(event)
            if quiet_active is not None:
                # Engine returned a definitive answer.
                if not quiet_active:
                    return False, "quiet hours active (non-critical suppressed)"
            elif self.config.quiet_hours and self._in_quiet_hours():
                # Fallback: local quiet-hours check.
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

    def _is_wake_worthy_acoustic(self, event: ProactiveEvent) -> bool:
        """True for a confirmed acoustic anomaly: tagger severity >= 2 (O5).

        The Voice Mode wake chain treats these as life-safety — a confirmed
        anomaly (glass break, intrusion) at 3am is exactly when it matters —
        so they bypass quiet hours exactly like the engine's B2 life-safety
        set. That set (LIFE_SAFETY_EVENT_TYPES) keys on sound *classes*
        (smoke_alarm, ...), while the gate only sees the "acoustic"
        *category*, so it can never fire for these events; the structured
        payload's ``anomaly_severity`` is the authoritative signal here.
        Without this bypass a severity-2 anomaly maps to Finding severity
        "warning" and is silently dropped during quiet hours — precisely the
        window in which it must wake the screen.
        """
        if (getattr(event, "category", None) or "") != "acoustic":
            return False
        data = getattr(event, "data", None)
        return isinstance(data, dict) and data.get("anomaly_severity", 0) >= 2

    def _check_quiet_hours_engine(self, event: ProactiveEvent) -> bool | None:
        """Delegate quiet-hours check to the engine when available.

        Returns True if the event should be allowed (not quiet hours or
        life-safety bypass), False if it should be suppressed, or None
        if the engine is not available (caller falls back to local check).
        """
        try:
            from ..integrations.modality_wiring import (
                is_life_safety_event,
                should_speak_proactively,
            )
            # Life-safety events bypass quiet hours unconditionally (B2).
            event_category = getattr(event, "category", None) or ""
            if is_life_safety_event(event_category):
                return True
            # Check quiet hours via the engine's policy.
            quiet_hours_active = self._in_quiet_hours()
            allowed = should_speak_proactively(event_category, quiet_hours=quiet_hours_active)
            return allowed
        except Exception:
            return None

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
