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
from typing import List

from ..findings.store import FindingStore, Finding
from ..findings.proposals import ProposalStore
from ..findings.detectors.dropin_conflicts import DropinConflictDetector
from ..findings.detectors.fstab_phantom import FstabPhantomDetector
from ..findings.detectors.permissions_hygiene import PermissionsHygieneDetector
from ..config.being_config import BeingConfig, load_being_config
from ..autonomy.guardrails import GuardrailEnforcer
from .events import ProactiveEvent, get_event_bus
from .gate import ProactiveGate

logger = logging.getLogger(__name__)


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
                    # Check if this finding already exists (dedup by title+detector)
                    existing = self._find_existing(finding)
                    if existing:
                        continue  # Already known, don't re-add

                    # Store the finding
                    finding_id = self.findings.add(finding)

                    # Create a proactive event
                    event = ProactiveEvent.create(
                        type="finding",
                        severity=finding.severity,
                        title=finding.title,
                        body=finding.description,
                        finding_id=finding_id,
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
        """Synchronous wrapper for run_all()."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.run_all())

    def _find_existing(self, finding: Finding) -> bool:
        """Check if a similar finding already exists (same detector + title).

        Checks both open AND snoozed findings — snoozed findings should
        not be re-created while the snooze is active. Dismissed findings
        are also checked — if the user dismissed it, don't re-add unless
        the condition has changed.
        """
        # Check open findings
        for existing in self.findings.list_open():
            if existing.detector == finding.detector and existing.title == finding.title:
                return True

        # Check snoozed and dismissed findings via list_all
        for existing in self.findings.list_all(limit=500):
            if existing.status in ("snoozed", "dismissed"):
                if existing.detector == finding.detector and existing.title == finding.title:
                    return True

        return False
