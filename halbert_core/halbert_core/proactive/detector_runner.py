"""
Detector runner — orchestrates detector execution and event publishing.

When the config watcher detects a change, or on a scheduled sweep, this
module runs all detectors, stores new findings, and publishes proactive
events (filtered by the ProactiveGate).

Phase 7 / T7e.1.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from ..findings.store import (
    FindingStore,
    Finding,
    FindingStatus,
    parse_timestamp,
)
from ..findings.proposals import ProposalStore
from ..findings.detectors.dropin_conflicts import DropinConflictDetector
from ..findings.detectors.fstab_phantom import FstabPhantomDetector
from ..findings.detectors.permissions_hygiene import PermissionsHygieneDetector
from ..config.being_config import BeingConfig, load_being_config
from ..autonomy.guardrails import GuardrailEnforcer
from .events import ProactiveEvent, get_event_bus
from .gate import ProactiveGate

logger = logging.getLogger(__name__)


# Detector name → ProactiveEvent category (drives ProactiveGate's
# per-category overrides). Anything unlisted falls back to "general".
_EVENT_CATEGORY = {
    "dropin_conflicts": "config",
    "fstab_phantom": "storage",
    "permissions_hygiene": "security",
}


class DetectorRunner:
    """Run all detectors, store findings, and publish proactive events.

    The gate filters events before they reach the SSE stream.
    """

    def __init__(
        self,
        finding_store: FindingStore | None = None,
        proposal_store: ProposalStore | None = None,
        being_config: BeingConfig | None = None,
        guardrails: GuardrailEnforcer | None = None,
        gate: ProactiveGate | None = None,
    ):
        self.findings = finding_store or FindingStore()
        self.proposals = proposal_store or ProposalStore()
        self.config = being_config or load_being_config()
        self.guardrails = guardrails or GuardrailEnforcer()
        self.gate = gate or ProactiveGate(
            being_config=self.config,
            guardrail_enforcer=self.guardrails,
            finding_store=self.findings,
        )

        # Register detectors
        self.detectors = [
            DropinConflictDetector(),
            FstabPhantomDetector(),
            PermissionsHygieneDetector(),
        ]

    async def run_all(self) -> List[ProactiveEvent]:
        """Run all detectors and publish events for new findings.

        Returns the list of events that passed the gate and were published.
        """
        published_events: List[ProactiveEvent] = []

        for detector in self.detectors:
            try:
                findings = detector.detect()
                for finding in findings:
                    # Dedup by detector+title (single targeted query)
                    existing = self._find_existing(finding)
                    if existing is not None:
                        if self._is_suppressed(existing):
                            continue  # Still known/active — don't re-add
                        # Snooze expired (or resolved and re-detected):
                        # re-surface the existing row instead of duplicating.
                        self.findings.update_status(
                            existing.id,
                            FindingStatus.OPEN.value,
                            snoozed_until="",
                        )
                        finding_id = existing.id
                        logger.info(
                            f"Finding {finding_id} re-surfaced "
                            f"(was {existing.status})"
                        )
                    else:
                        # Store the finding
                        finding_id = self.findings.add(finding)

                    # Create a proactive event
                    event = ProactiveEvent.create(
                        type="finding",
                        severity=finding.severity,
                        title=finding.title,
                        body=finding.description,
                        finding_id=finding_id,
                        category=_EVENT_CATEGORY.get(finding.detector, "general"),
                    )

                    # Check the gate
                    should_notify, reason = self.gate.should_notify(event)
                    if should_notify:
                        bus = get_event_bus()
                        await bus.publish(event)
                        published_events.append(event)
                    else:
                        logger.info(
                            f"Finding {finding_id} suppressed by gate: {reason}"
                        )
            except Exception as e:
                logger.warning(f"Detector {detector.__class__.__name__} failed: {e}")

        logger.info(
            f"Detector sweep complete: {len(published_events)} events published"
        )
        return published_events

    def run_all_sync(self) -> List[ProactiveEvent]:
        """Synchronous wrapper for run_all().

        Uses asyncio.run() when no loop is running in the current thread
        (the normal config-watcher worker-thread case). If a loop IS
        already running here, falls back to a dedicated loop that is
        always closed afterwards — no deprecated get_event_loop() and no
        leaked loops.
        """
        try:
            asyncio.get_running_loop()
            loop_running = True
        except RuntimeError:
            loop_running = False

        if not loop_running:
            return asyncio.run(self.run_all())

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.run_all())
        finally:
            loop.close()

    def _find_existing(self, finding: Finding) -> Optional[Finding]:
        """Return the newest existing finding with the same detector+title.

        Matches regardless of status — whether it still suppresses the new
        one is decided by _is_suppressed(). Returns None when unknown.
        """
        return self.findings.find_by_detector_title(finding.detector, finding.title)

    def _is_suppressed(self, existing: Finding) -> bool:
        """Decide whether an existing match suppresses a new finding.

        Suppressed: open (already known), dismissed (user said not a
        problem), and snoozed findings whose snooze is still in the future.
        Not suppressed: snoozed findings whose snoozed_until has passed —
        those re-surface instead of staying a permanent mute.
        """
        if existing.status == FindingStatus.SNOOZED.value:
            snoozed_until = parse_timestamp(existing.snoozed_until)
            if snoozed_until and datetime.now(timezone.utc) < snoozed_until:
                return True  # snooze still active
            return False  # expired — re-surface
        if existing.status == FindingStatus.RESOLVED.value:
            return False  # re-detected after resolution — re-surface
        # open / dismissed / anything else counts as already known
        return True
