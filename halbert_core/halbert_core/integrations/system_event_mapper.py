# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
System Event Mapper — maps discovery/telemetry events to PersonaCognition.

This is the consumer-side bridge that populates Haloysius's cognitive
layers (worries, drives, emotions) from real system events detected by
Halbert's discovery engine and telemetry collector.

RQ-C research: consumer-side, zero core changes. The mapper runs as a
background scan thread that polls discovery results and translates
system state changes into cognitive events.

Mapping table:
  Disk failure SMART alert  -> worry (disk_health, high intensity)
  Service crashed/failed    -> worry (service_stability, medium)
  High CPU > 90%            -> worry (resource_pressure, medium)
  High memory > 90%         -> worry (resource_pressure, medium)
  Service degraded          -> emotion (fear, low)
  All services healthy      -> emotion (joy, low) + resolve worries
  Admin session started     -> emotion (trust, medium)
  Config drift detected     -> drive (competence, "investigate config drift")
  Security anomaly          -> emotion (fear, high) + worry (security)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("halbert.integrations.system_event_mapper")


class SystemEventMapper:
    """Maps system events to PersonaCognition cognitive updates.

    Call populate_cognition() before advance_turn() to inject system
    state into the persona's worries, drives, and emotions.

    Optionally runs a background scan thread that polls discovery and
    telemetry, accumulating events for the next cognitive tick.
    """

    def __init__(
        self,
        discovery_engine=None,
        telemetry_store=None,
        trackers: Optional[Dict] = None,
        timeline=None,
    ):
        self._discovery = discovery_engine
        self._telemetry = telemetry_store
        self._trackers = trackers or {}
        self._timeline = timeline
        self._pending_events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._scan_thread: Optional[threading.Thread] = None
        self._scanning = False
        self._scan_interval = 30.0  # seconds
        if self._timeline is None:
            logger.warning(
                "No TimelineStore configured — system events will not be "
                "durably recorded (they still reach cognition this tick)"
            )

    def populate_cognition(self, cognition) -> None:
        """Populate PersonaCognition with current system state.

        Call this before advance_turn() so the cognitive tick operates
        on up-to-date worries/drives/emotions derived from system state.

        Args:
            cognition: Haloysius PersonaCognition instance
        """
        with self._lock:
            events = list(self._pending_events)
            self._pending_events.clear()

        for event in events:
            self._record_to_timeline(event)
            self._apply_event_to_cognition(cognition, event)

        # Also do a quick synchronous check for critical conditions
        self._check_critical_conditions(cognition)

    def _record_to_timeline(self, event: Dict[str, Any]) -> None:
        """A2b: record each drained event to the ledger before applying it.

        This is the primary mapper — the one a sysadmin install (no HA,
        no Frigate) actually has. Without this it has a ledger and still
        no writer. Uses the event's own timestamp (captured in add_event()
        at ingestion), never a fresh one at drain time.
        """
        if self._timeline is None:
            return
        try:
            from ..continuity.timeline import TimelineEvent

            self._timeline.record(TimelineEvent(
                timestamp=event.get("timestamp") or time.time(),
                event_type=event["type"],
                source=event["source"],
                severity=event["severity"],
                title=event["detail"],
            ))
        except Exception as e:
            logger.warning(f"Could not record system event to timeline: {e}")

    def add_event(self, event_type: str, severity: str, source: str, detail: str) -> None:
        """Add a system event for the next cognitive tick.

        Args:
            event_type: Category (disk_failure, service_crash, high_resource,
                config_drift, security_anomaly, service_recovered)
            severity: "critical", "warning", "info"
            source: What triggered it (e.g., "disk:/dev/sda1", "service:nginx")
            detail: Human-readable detail
        """
        with self._lock:
            self._pending_events.append({
                "type": event_type,
                "severity": severity,
                "source": source,
                "detail": detail,
                "timestamp": time.time(),
            })

    def _apply_event_to_cognition(self, cognition, event: Dict[str, Any]) -> None:
        """Apply a single system event to cognitive layers."""
        event_type = event["type"]
        severity = event["severity"]
        source = event["source"]
        detail = event["detail"]

        if event_type == "disk_failure":
            intensity = 0.9 if severity == "critical" else 0.5
            cognition.worries.add_worry(
                content=f"Disk {source} is failing: {detail}",
                source=source,
                category="disk_health",
                intensity=intensity,
                intrusion_rate=0.5 if severity == "critical" else 0.2,
            )
            cognition.emotional_state.add_emotion(
                emotion=self._emotion("FEAR"),
                intensity=intensity * 0.7,
                source=source,
            )

        elif event_type == "service_crash":
            intensity = 0.6
            cognition.worries.add_worry(
                content=f"Service {source} has crashed: {detail}",
                source=source,
                category="service_stability",
                intensity=intensity,
                intrusion_rate=0.3,
            )
            cognition.emotional_state.add_emotion(
                emotion=self._emotion("SADNESS"),
                intensity=0.4,
                source=source,
            )

        elif event_type == "high_resource":
            intensity = 0.5 if severity == "warning" else 0.7
            cognition.worries.add_worry(
                content=f"Resource pressure: {detail}",
                source=source,
                category="resource_pressure",
                intensity=intensity,
                intrusion_rate=0.2,
            )
            cognition.emotional_state.add_emotion(
                emotion=self._emotion("ANTICIPATION"),
                intensity=0.3,
                source=source,
            )

        elif event_type == "config_drift":
            cognition.drives.add_drive(
                category=self._drive("COMPETENCE"),
                content=f"Investigate config drift in {source}: {detail}",
                intensity=0.6,
                trigger=source,
            )

        elif event_type == "security_anomaly":
            cognition.worries.add_worry(
                content=f"Security anomaly detected: {detail}",
                source=source,
                category="security",
                intensity=0.9,
                intrusion_rate=0.6,
            )
            cognition.emotional_state.add_emotion(
                emotion=self._emotion("FEAR"),
                intensity=0.8,
                source=source,
            )

        elif event_type == "service_recovered":
            # Resolve matching worries
            for worry in cognition.worries.get_active_worries():
                if source in worry.source:
                    cognition.worries.resolve_worry(worry.id, "service recovered")
            cognition.emotional_state.add_emotion(
                emotion=self._emotion("JOY"),
                intensity=0.3,
                source=source,
            )

        elif event_type == "visual_anomaly":
            intensity = 0.7 if severity == "critical" else 0.4
            cognition.worries.add_worry(
                content=f"Screen anomaly: {detail}",
                source=source,
                category="visual_stability",
                intensity=intensity,
                intrusion_rate=0.3 if severity == "critical" else 0.1,
            )
            cognition.emotional_state.add_emotion(
                emotion=self._emotion("ANTICIPATION"),
                intensity=intensity * 0.6,
                source=source,
            )
            cognition.drives.add_drive(
                category=self._drive("COMPETENCE"),
                content=f"Investigate screen anomaly: {detail}",
                intensity=intensity * 0.5,
                trigger=source,
            )

        elif event_type == "acoustic_anomaly":
            intensity = 0.9 if severity == "critical" else 0.5
            cognition.worries.add_worry(
                content=f"Acoustic anomaly: {detail}",
                source=source,
                category="acoustic_safety",
                intensity=intensity,
                intrusion_rate=0.6 if severity == "critical" else 0.2,
            )
            cognition.emotional_state.add_emotion(
                emotion=self._emotion("FEAR"),
                intensity=intensity * 0.8,
                source=source,
            )
            cognition.emotional_state.add_emotion(
                emotion=self._emotion("ANTICIPATION"),
                intensity=intensity * 0.7,
                source=source,
            )
            cognition.drives.add_drive(
                category=self._drive("SAFETY"),
                content=f"Investigate acoustic anomaly: {detail}",
                intensity=intensity * 0.8,
                trigger=source,
            )

        # Update state trackers
        if event_type == "disk_failure" and "disk_health" in self._trackers:
            self._trackers["disk_health"].update_health(source, severity)
        elif event_type in ("service_crash", "service_recovered") and "service_status" in self._trackers:
            status = "failed" if event_type == "service_crash" else "running"
            self._trackers["service_status"].update_status(source, status)

    def _check_critical_conditions(self, cognition) -> None:
        """Quick synchronous check for critical system conditions.

        This supplements the event-driven approach with a polling check
        for conditions that might not have generated explicit events.
        """
        if self._discovery is None:
            return

        try:
            # Check disk space
            if hasattr(self._discovery, "get_disk_status"):
                disks = self._discovery.get_disk_status()
                for disk in disks or []:
                    usage = disk.get("usage_percent", 0)
                    if usage > 90:
                        cognition.worries.add_worry(
                            content=f"Disk {disk.get('device', 'unknown')} is at {usage:.0f}% capacity",
                            source=f"disk:{disk.get('device', 'unknown')}",
                            category="disk_space",
                            intensity=0.6,
                            intrusion_rate=0.2,
                        )
        except Exception:
            pass

    def start_background_scan(self) -> None:
        """Start a background thread that polls discovery for system events.

        The thread runs at _scan_interval seconds and feeds events into
        the pending queue for the next cognitive tick.
        """
        if self._scanning:
            return

        self._scanning = True
        self._scan_thread = threading.Thread(
            target=self._scan_loop,
            daemon=True,
            name="halbert-event-scanner",
        )
        self._scan_thread.start()
        logger.info("Started background system event scanner")

    def stop_background_scan(self) -> None:
        """Stop the background scan thread."""
        self._scanning = False
        if self._scan_thread:
            self._scan_thread.join(timeout=5)
            self._scan_thread = None
        logger.info("Stopped background system event scanner")

    def _scan_loop(self) -> None:
        """Background scan loop — polls discovery and telemetry."""
        while self._scanning:
            try:
                self._scan_discovery()
                self._scan_telemetry()
            except Exception as e:
                logger.error(f"Background scan error: {e}")
            time.sleep(self._scan_interval)

    def _scan_discovery(self) -> None:
        """Scan discovery results for new system events."""
        if self._discovery is None:
            return

        try:
            if hasattr(self._discovery, "get_service_status"):
                services = self._discovery.get_service_status()
                for svc in services or []:
                    status = svc.get("status", "").lower()
                    name = svc.get("name", "unknown")
                    if status in ("failed", "crashed", "dead"):
                        self.add_event(
                            event_type="service_crash",
                            severity="critical",
                            source=f"service:{name}",
                            detail=f"Service {name} is {status}",
                        )
                    elif status == "degraded":
                        self.add_event(
                            event_type="service_crash",
                            severity="warning",
                            source=f"service:{name}",
                            detail=f"Service {name} is degraded",
                        )
        except Exception as e:
            logger.debug(f"Discovery scan error: {e}")

    def _scan_telemetry(self) -> None:
        """Scan telemetry for resource pressure events."""
        if self._telemetry is None:
            return

        try:
            if hasattr(self._telemetry, "get_latest"):
                latest = self._telemetry.get_latest()
                if latest:
                    cpu = latest.get("cpu_percent", 0)
                    mem = latest.get("memory_percent", 0)
                    if cpu > 90:
                        self.add_event(
                            event_type="high_resource",
                            severity="critical",
                            source="system:cpu",
                            detail=f"CPU at {cpu:.0f}%",
                        )
                    if mem > 90:
                        self.add_event(
                            event_type="high_resource",
                            severity="critical",
                            source="system:memory",
                            detail=f"Memory at {mem:.0f}%",
                        )

                    # Update resource tracker
                    if "system_resources" in self._trackers:
                        load = latest.get("load_avg", 0)
                        self._trackers["system_resources"].update_resources(cpu, mem, load)
        except Exception as e:
            logger.debug(f"Telemetry scan error: {e}")

    @staticmethod
    def _emotion(name: str):
        """Get EmotionCategory by name (lazy import)."""
        from haloysius.persona.emotional_state import EmotionCategory
        return EmotionCategory[name]

    @staticmethod
    def _drive(name: str):
        """Get DriveCategory by name (lazy import)."""
        from haloysius.persona.drives import DriveCategory
        return DriveCategory[name]
