"""
Morning report generator — consolidates the last 24 hours into a
natural-language summary published as a ProactiveEvent.

Phase 7 / T7d.1.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from ..config.being_config import BeingConfig, load_being_config
from ..findings.store import FindingStore, FindingStatus
from ..findings.proposals import ProposalStore, ProposalStatus
from .events import ProactiveEvent, get_event_bus

logger = logging.getLogger(__name__)


class MorningReportGenerator:
    """Generate a morning report from the last 24 hours of activity.

    Optional integrations (T7d.1):
    - ``summarizer``: callable that rewrites the template body. Its output
      becomes the report body when it returns non-empty text; otherwise the
      template body stands.
    - ``config_changes_provider``: callable(hours) returning change entries
      (timestamped dicts with ``ts``/``path``/``kind``, or plain strings)
      for the "Config Changes" section.
    - ``gate``: ProactiveGate consulted before publishing. With no gate the
      generator constructs a default one defensively; when no gate can be
      built or evaluated, the report is NOT published (fail closed —
      proactivity "off" must mean no morning report).
    """

    def __init__(
        self,
        finding_store: FindingStore,
        proposal_store: ProposalStore,
        being_config: BeingConfig | None = None,
        summarizer: Optional[Callable[[str], str]] = None,
        config_changes_provider: Optional[Callable[[int], List[Any]]] = None,
        gate: Optional[Any] = None,
    ):
        self.findings = finding_store
        self.proposals = proposal_store
        self.config = being_config or load_being_config()
        self.summarizer = summarizer
        self.config_changes_provider = config_changes_provider
        self.gate = gate

    async def generate(self) -> ProactiveEvent:
        """Generate and publish the morning report.

        Consolidates:
        - Open findings (grouped by severity)
        - Pending proposals awaiting approval
        - Config changes from the last 24h
        - Recently resolved findings (last 24h)

        The event is published only when the ProactiveGate allows it.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        # Gather data
        open_findings = self.findings.list_open()
        pending_proposals = self.proposals.list_pending()

        # Config changes from the last 24h (T7d.1)
        config_changes: List[Any] = []
        if self.config_changes_provider is not None:
            try:
                config_changes = list(self.config_changes_provider(24) or [])
            except Exception as e:
                logger.warning(f"Config changes provider failed: {e}")
                config_changes = []

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

        # Config changes (T7d.1)
        if config_changes:
            body_parts.append(
                f"\n## Config Changes (last 24h, {len(config_changes)})"
            )
            for change in config_changes[:10]:
                body_parts.append(f"- {self._format_change(change)}")
            if len(config_changes) > 10:
                body_parts.append(f"- …and {len(config_changes) - 10} more")

        # Purpose reminder
        if self.config.purpose:
            body_parts.append(f"\n---\n*Purpose: {self.config.purpose}*")

        body = "\n".join(body_parts)

        # Optional LLM summarizer — on exception or empty output the
        # template body above stands.
        if self.summarizer is not None:
            try:
                summarized = self.summarizer(body)
                if summarized and summarized.strip():
                    body = summarized
                else:
                    logger.info("Summarizer returned empty text; using template body")
            except Exception as e:
                logger.warning(f"Summarizer failed; using template body: {e}")

        # Determine severity
        if critical:
            severity = "critical"
        elif warnings:
            severity = "warning"
        else:
            severity = "info"

        # Create the event. `category="reports"` matches the ProactiveEvent
        # contract; fall back without it while the field is not yet live.
        title = f"Morning Report — {now.strftime('%B %d, %Y')}"
        try:
            event = ProactiveEvent.create(
                type="morning_report",
                severity=severity,
                title=title,
                body=body,
                category="reports",
            )
        except TypeError:
            event = ProactiveEvent.create(
                type="morning_report",
                severity=severity,
                title=title,
                body=body,
            )

        # Gate before publish — proactivity "off" must mean no report.
        gate = self.gate or self._default_gate()
        if gate is None:
            logger.warning("Morning report not published: no gate available")
            return event
        try:
            should_notify, reason = gate.should_notify(event)
        except Exception as e:
            logger.warning(f"Gate evaluation failed; suppressing morning report: {e}")
            return event
        if not should_notify:
            logger.info(f"Morning report suppressed by gate: {reason}")
            return event

        # Publish to the event bus
        bus = get_event_bus()
        await bus.publish(event)

        logger.info(f"Morning report generated: {event.title}")
        return event

    @staticmethod
    def _format_change(change: Any) -> str:
        """Render a config change entry as a one-line bullet."""
        if isinstance(change, dict):
            path = change.get("path", "?")
            kind = change.get("kind", "unknown")
            if kind and kind != "unknown":
                return f"**{path}** ({kind}) changed"
            return f"**{path}** changed"
        return str(change)

    def _default_gate(self):
        """Construct a ProactiveGate defensively.

        Returns None when the gate stack cannot be built (being.yml
        malformed, proactive stack half-wired) — the caller fails closed.
        """
        try:
            from .gate import ProactiveGate

            return ProactiveGate(
                being_config=self.config,
                guardrail_enforcer=None,
            )
        except Exception as e:
            logger.warning(f"Could not construct default ProactiveGate: {e}")
            return None
