"""
Morning report generator — consolidates the last 24 hours into a
natural-language summary published as a ProactiveEvent.

Phase 7 / T7d.1.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..config.being_config import BeingConfig, load_being_config
from ..findings.store import FindingStore, FindingStatus
from ..findings.proposals import ProposalStore, ProposalStatus
from .events import ProactiveEvent, get_event_bus

logger = logging.getLogger(__name__)


class MorningReportGenerator:
    """Generate a morning report from the last 24 hours of activity."""

    def __init__(
        self,
        finding_store: FindingStore,
        proposal_store: ProposalStore,
        being_config: BeingConfig | None = None,
    ):
        self.findings = finding_store
        self.proposals = proposal_store
        self.config = being_config or load_being_config()

    async def generate(self) -> ProactiveEvent:
        """Generate and publish the morning report.

        Consolidates:
        - Open findings (grouped by severity)
        - Pending proposals awaiting approval
        - Recently resolved findings (last 24h)
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        # Gather data
        open_findings = self.findings.list_open()
        pending_proposals = self.proposals.list_pending()

        # Group findings by severity
        critical = [f for f in open_findings if f.severity == "critical"]
        warnings = [f for f in open_findings if f.severity == "warning"]
        info = [f for f in open_findings if f.severity == "info"]

        # Build the report body
        body_parts: list[str] = []

        # Voice-aware intro
        if self.config.voice == "the_computer":
            body_parts.append("This system has completed its morning review.")
        elif self.config.voice == "hybrid":
            body_parts.append("I've completed the morning review of this system.")
        else:
            body_parts.append("I've completed my morning review.")

        # Findings summary
        if open_findings:
            body_parts.append(f"\n## Open Findings ({len(open_findings)} total)")
            if critical:
                body_parts.append(f"\n### Critical ({len(critical)})")
                for f in critical[:5]:
                    body_parts.append(f"- **{f.title}** — {f.why_care}")
            if warnings:
                body_parts.append(f"\n### Warnings ({len(warnings)})")
                for f in warnings[:5]:
                    body_parts.append(f"- **{f.title}** — {f.why_care}")
            if info:
                body_parts.append(f"\n### Info ({len(info)})")
                for f in info[:3]:
                    body_parts.append(f"- {f.title}")
        else:
            body_parts.append("\nNo open findings. The system looks clean.")

        # Pending proposals
        if pending_proposals:
            body_parts.append(f"\n## Pending Proposals ({len(pending_proposals)})")
            for p in pending_proposals[:5]:
                body_parts.append(f"- **{p.action}** — awaiting approval")
        else:
            body_parts.append("\nNo proposals awaiting approval.")

        # Purpose reminder
        if self.config.purpose:
            body_parts.append(f"\n---\n*Purpose: {self.config.purpose}*")

        body = "\n".join(body_parts)

        # Determine severity
        if critical:
            severity = "critical"
        elif warnings:
            severity = "warning"
        else:
            severity = "info"

        # Create the event
        event = ProactiveEvent.create(
            type="morning_report",
            severity=severity,
            title=f"Morning Report — {now.strftime('%B %d, %Y')}",
            body=body,
        )

        # Publish to the event bus
        bus = get_event_bus()
        await bus.publish(event)

        logger.info(f"Morning report generated: {event.title}")
        return event
