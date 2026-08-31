# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
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
from typing import Any, List, Optional

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
from ..findings.detectors.acoustic_anomaly import AcousticAnomalyDetector
from ..config.being_config import BeingConfig, load_being_config
from ..autonomy.guardrails import GuardrailEnforcer
from .events import ProactiveEvent, get_event_bus
from .gate import ProactiveGate
from .reflexes import ReflexMatcher

logger = logging.getLogger(__name__)


# Detector name → ProactiveEvent category (drives ProactiveGate's
# per-category overrides). Anything unlisted falls back to "general".
_EVENT_CATEGORY = {
    "dropin_conflicts": "config",
    "fstab_phantom": "storage",
    "permissions_hygiene": "security",
    "acoustic_anomaly": "acoustic",
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
        reflex_matcher: ReflexMatcher | None = None,
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
        # F3: living reflexes evaluated on each sweep (None -> no-op)
        self.reflex_matcher = reflex_matcher

        # Register detectors
        self.acoustic_detector = AcousticAnomalyDetector()
        self.detectors = [
            DropinConflictDetector(),
            FstabPhantomDetector(),
            PermissionsHygieneDetector(),
            self.acoustic_detector,
        ]
        # Detector classes that already logged a failure warning (O5: the
        # acoustic bridge can invoke _run_detector per sound event, so a
        # persistently failing detector — e.g. a locked DB — must not warn
        # every few seconds; repeats drop to debug).
        self._detector_warned: set = set()

    async def run_all(self) -> List[ProactiveEvent]:
        """Run all detectors and publish events for new findings.

        Returns the list of events that passed the gate and were published.
        """
        published_events: List[ProactiveEvent] = []

        for detector in self.detectors:
            published_events.extend(await self._run_detector(detector))

        logger.info(
            f"Detector sweep complete: {len(published_events)} events published"
        )
        return published_events

    async def run_acoustic(self) -> List[ProactiveEvent]:
        """Drain ONLY the acoustic anomaly detector and publish its findings.

        Used by the audio-pipeline acoustic bridge (O5): a tagged anomaly must
        reach the SSE stream immediately, not at the next scheduled sweep —
        but a per-sound-event run must never trigger the filesystem detectors
        (drop-in conflicts, fstab, permissions), which are sweep-scheduled by
        design. Shares the dedup / gate / reflex path with ``run_all``.
        """
        return await self._run_detector(self.acoustic_detector)

    async def _run_detector(self, detector) -> List[ProactiveEvent]:
        """Detect, dedup, store, gate, and publish one detector's findings.

        A detector failure is isolated to a log line — one broken detector
        never takes down the sweep (or, via run_acoustic, the audio pipeline).
        """
        published_events: List[ProactiveEvent] = []

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

                # Create a proactive event (``data`` carries the detector's
                # structured payload when it built one — e.g. the acoustic
                # module contract — else None).
                event = ProactiveEvent.create(
                    type="finding",
                    severity=finding.severity,
                    title=finding.title,
                    body=finding.description,
                    finding_id=finding_id,
                    category=_EVENT_CATEGORY.get(finding.detector, "general"),
                    data=finding.data,
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

                # F3: evaluate living reflexes against this finding.
                # Reflex events inherit the gate decision — a reflex derived
                # from a suppressed finding must not leak past quiet hours,
                # the proactivity dial, or safe mode.
                if self.reflex_matcher is not None:
                    for reflex in self.reflex_matcher.match(
                        title=finding.title,
                        body=finding.description,
                        severity=finding.severity,
                        category=finding.detector,
                    ):
                        reflex_event = self._reflex_event(reflex, finding, finding_id)
                        try:
                            notify, reason = self.gate.should_notify(reflex_event)
                            if not notify:
                                logger.info(
                                    f"Reflex '{reflex.name}' suppressed by gate: {reason}"
                                )
                                continue
                            await get_event_bus().publish(reflex_event)
                            published_events.append(reflex_event)
                        except Exception as e:
                            logger.warning(f"reflex publish failed: {e}")
        except Exception as e:
            # Warning-once per detector class: the acoustic bridge (O5) can
            # call this per sound event, so a persistent failure must not
            # warn every few seconds.
            name = detector.__class__.__name__
            if name in self._detector_warned:
                logger.debug(f"Detector {name} failed (repeat): {e}")
            else:
                self._detector_warned.add(name)
                logger.warning(f"Detector {name} failed: {e}")

        return published_events

    def _reflex_event(
        self, reflex: Any, finding: Finding, finding_id: str
    ) -> ProactiveEvent:
        """Build a proactive event for a fired reflex (F3).

        action=notify    -> reflex_fired (at the finding's severity)
        action=escalate  -> reflex_escalate (forced to critical)
        action=command   -> reflex_command_proposed (carries the command; the
                            approval/agent layer executes it, not the runner)
        """
        action = reflex.action or "notify"
        if action == "escalate":
            return ProactiveEvent.create(
                type="reflex_escalate", severity="critical",
                title=f"Reflex escalated: {reflex.name}",
                body=finding.title,
                finding_id=finding_id, category=reflex.category or "general",
            )
        if action == "command":
            return ProactiveEvent.create(
                type="reflex_command_proposed", severity="warning",
                title=f"Reflex command proposed: {reflex.name}",
                body=reflex.command or "",
                finding_id=finding_id, category=reflex.category or "general",
            )
        return ProactiveEvent.create(
            type="reflex_fired", severity=finding.severity,
            title=f"Reflex fired: {reflex.name}",
            body=finding.title,
            finding_id=finding_id, category=reflex.category or "general",
        )

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
