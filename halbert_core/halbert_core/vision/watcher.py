# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""VisualWatcher — proactive background screen monitor.

Periodically captures the active window, runs OCR, and publishes
ProactiveEvents when error patterns match. NOT part of DetectorRunner —
visual anomalies need 30s-5min cadence, not the 6-hour filesystem
detector sweep.

Two-stage gate for efficiency:
  Stage 1: MD5 hash of the captured image. If unchanged, skip OCR.
  Stage 2: OCR + pattern match only when pixels changed.

Privacy:
  - Captures the active window only (not full screen).
  - Respects vision_config.yml redaction settings.
  - Gated by both vision_config.yml (system) and being.yml (persona).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, List, Optional

from ..config.being_config import BeingConfig
from ..findings.store import Finding, FindingStore
from ..proactive.events import ProactiveEvent, get_event_bus
from ..proactive.gate import ProactiveGate

logger = logging.getLogger(__name__)

# Detector name for findings created by the watcher.
_DETECTOR_NAME = "visual_watcher"

# Event category for ProactiveGate's per-category overrides.
_EVENT_CATEGORY = "vision"


class VisualWatcher:
    """Background screen monitor. Captures, OCRs, and publishes
    ProactiveEvents when error patterns match.

    NOT part of DetectorRunner — visual anomalies need 30s-5min
    cadence, not the 6-hour filesystem detector sweep.
    """

    def __init__(
        self,
        being_config: BeingConfig,
        gate: ProactiveGate,
        finding_store: Optional[FindingStore] = None,
        reflex_matcher: Any = None,
        event_mapper: Any = None,
        memory_store: Any = None,
    ):
        self.config = being_config
        self.gate = gate
        self.findings = finding_store
        self.reflex_matcher = reflex_matcher
        self.event_mapper = event_mapper  # SystemEventMapper for cognition
        self.memory_store = memory_store  # HybridMemorySystem for episodic memory
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_hash: Optional[str] = None
        self._unchanged_count = 0
        # Pre-compile error patterns for fast matching
        self._compiled_patterns: List[re.Pattern] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile error patterns from being config."""
        patterns = self.config.senses.vision.error_patterns
        self._compiled_patterns = []
        for p in patterns:
            try:
                self._compiled_patterns.append(re.compile(p, re.IGNORECASE))
            except re.error as e:
                logger.warning(f"VisualWatcher: bad pattern {p!r}: {e}")

    def start(self) -> None:
        """Start the background watch loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name="halbert-visual-watcher",
        )
        self._thread.start()
        logger.info(
            f"VisualWatcher started (interval={self.config.senses.vision.interval_seconds}s)"
        )

    def stop(self) -> None:
        """Stop the background watch loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("VisualWatcher stopped")

    def _watch_loop(self) -> None:
        """Main loop: capture, hash, OCR, match, publish."""
        while self._running:
            try:
                self._check_screen()
            except Exception as e:
                logger.warning(f"VisualWatcher error: {e}")
            time.sleep(self._adaptive_interval())

    def _adaptive_interval(self) -> int:
        """Back off when the screen hasn't changed.

        Returns the configured interval when the screen is changing,
        and up to 5x the interval when it's been static for a while.
        """
        base = self.config.senses.vision.interval_seconds
        if self._unchanged_count == 0:
            return base
        # Linear backoff up to 5x, capped
        factor = min(1 + self._unchanged_count * 0.5, 5.0)
        return int(base * factor)

    def _check_screen(self) -> None:
        """Capture, hash, OCR, and check for error patterns.

        This is the core logic, separated from the loop so tests can
        call it directly without the threading machinery.
        """
        # Stage 1: Capture and hash
        result = self._capture_active_window()
        if result is None:
            return

        image_b64 = result.get("image")
        ocr_text = result.get("ocr_text", "")

        if image_b64 is None:
            return

        current_hash = hashlib.md5(image_b64.encode("ascii", errors="ignore")).hexdigest()
        if current_hash == self._last_hash:
            self._unchanged_count += 1
            return

        self._last_hash = current_hash
        self._unchanged_count = 0

        # Stage 2: OCR + pattern match (only if screen changed)
        if not ocr_text:
            return

        matched = self._match_patterns(ocr_text)
        if matched:
            self._publish_finding(matched, ocr_text, image_b64)

    def _capture_active_window(self) -> Optional[dict]:
        """Capture the active window with OCR. Returns dict with image/ocr_text."""
        try:
            from ..tools.vision_tools import capture_active_window_tool
            # capture_active_window_tool is async, but we're in a sync thread.
            # Use asyncio.run to call it.
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(capture_active_window_tool({}))
            finally:
                loop.close()
            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.debug(f"VisualWatcher capture failed: {e}")
        return None

    def _match_patterns(self, ocr_text: str) -> Optional[str]:
        """Check OCR text against error patterns. Returns first match or None."""
        for pattern in self._compiled_patterns:
            if pattern.search(ocr_text):
                return pattern.pattern
        return None

    def _publish_finding(
        self, matched_pattern: str, ocr_text: str, image_b64: str
    ) -> None:
        """Create a Finding and publish a ProactiveEvent."""
        # Truncate OCR text for the finding description
        ocr_excerpt = ocr_text[:500]

        # Determine severity from pattern
        severity = "warning"
        critical_patterns = ["panic", "kernel panic", "critical", "raid degraded"]
        for cp in critical_patterns:
            if cp in matched_pattern.lower():
                severity = "critical"
                break

        # Create Finding
        finding = Finding(
            id=str(__import__("uuid").uuid4()),
            detector=_DETECTOR_NAME,
            severity=severity,
            title=f"Visual error: {matched_pattern}",
            description=f"Screen OCR matched pattern '{matched_pattern}':\n{ocr_excerpt}",
            why_now="VisualWatcher detected error text on screen",
            why_care="The error may indicate a system problem requiring attention",
            why_so=f"OCR text matched pattern: {matched_pattern}",
            why_trust=["vision:active_window_ocr"],
        )

        finding_id = ""
        if self.findings is not None:
            try:
                finding_id = self.findings.add(finding)
            except Exception as e:
                logger.warning(f"VisualWatcher: failed to store finding: {e}")

        # Create ProactiveEvent
        event = ProactiveEvent.create(
            type="visual_finding",
            severity=severity,
            title=finding.title,
            body=ocr_excerpt,
            finding_id=finding_id or None,
            category=_EVENT_CATEGORY,
        )

        # Gate check
        should_notify, reason = self.gate.should_notify(event)
        if should_notify:
            try:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(get_event_bus().publish(event))
                finally:
                    loop.close()
                logger.info(f"VisualWatcher published: {finding.title}")
            except Exception as e:
                logger.warning(f"VisualWatcher: publish failed: {e}")
        else:
            logger.debug(f"VisualWatcher finding suppressed by gate: {reason}")

        # Feed the cognitive layer (worries, drives, emotions) regardless
        # of the gate — the being should "feel" the anomaly even if it
        # doesn't surface a notification to the user.
        if self.event_mapper is not None:
            try:
                self.event_mapper.add_event(
                    event_type="visual_anomaly",
                    severity=severity,
                    source="screen:active_window",
                    detail=f"{matched_pattern}: {ocr_excerpt}",
                )
            except Exception as e:
                logger.debug(f"VisualWatcher: event_mapper call failed: {e}")

        # Store as episodic memory with disk-cached screenshot (not base64).
        # Only anomalies are stored — routine unchanged captures are not.
        if self.memory_store is not None:
            try:
                from .cache import VisionCache
                cache = VisionCache()
                uri = cache.store(image_b64)
                from ..memory.hybrid import MemoryType
                self.memory_store.store(
                    content=f"Visual anomaly detected: {matched_pattern}\nOCR: {ocr_excerpt}",
                    memory_type=MemoryType.EPISODIC,
                    metadata={
                        "source": "vision",
                        "screenshot_uri": uri,
                        "pattern": matched_pattern,
                        "severity": severity,
                    },
                    importance=0.7 if severity == "critical" else 0.4,
                )
            except Exception as e:
                logger.debug(f"VisualWatcher: memory store failed: {e}")

        # Evaluate reflexes
        if self.reflex_matcher is not None:
            self._evaluate_reflexes(finding, finding_id)

    def _evaluate_reflexes(self, finding: Finding, finding_id: str) -> None:
        """Evaluate living reflexes against this finding."""
        try:
            for reflex in self.reflex_matcher.match(
                title=finding.title,
                body=finding.description,
                severity=finding.severity,
                category=_DETECTOR_NAME,
            ):
                action = reflex.action or "notify"
                if action == "escalate":
                    reflex_event = ProactiveEvent.create(
                        type="reflex_escalate", severity="critical",
                        title=f"Reflex escalated: {reflex.name}",
                        body=finding.title,
                        finding_id=finding_id or None,
                        category=reflex.category or _EVENT_CATEGORY,
                    )
                elif action == "command":
                    reflex_event = ProactiveEvent.create(
                        type="reflex_command_proposed", severity="warning",
                        title=f"Reflex command proposed: {reflex.name}",
                        body=reflex.command or "",
                        finding_id=finding_id or None,
                        category=reflex.category or _EVENT_CATEGORY,
                    )
                else:
                    reflex_event = ProactiveEvent.create(
                        type="reflex_fired", severity=finding.severity,
                        title=f"Reflex fired: {reflex.name}",
                        body=finding.title,
                        finding_id=finding_id or None,
                        category=reflex.category or _EVENT_CATEGORY,
                    )

                notify, reason = self.gate.should_notify(reflex_event)
                if notify:
                    try:
                        loop = asyncio.new_event_loop()
                        try:
                            loop.run_until_complete(get_event_bus().publish(reflex_event))
                        finally:
                            loop.close()
                    except Exception as e:
                        logger.warning(f"VisualWatcher reflex publish failed: {e}")
                else:
                    logger.debug(f"VisualWatcher reflex suppressed: {reason}")
        except Exception as e:
            logger.warning(f"VisualWatcher reflex evaluation failed: {e}")
