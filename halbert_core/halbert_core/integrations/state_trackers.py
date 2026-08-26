# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Halbert State Trackers — consumer-side registration with Haloysius.

Registers machine-relevant state trackers (disk health, service status,
system resources) with Haloysius's StateTracker protocol, and registers
predicates + subject labels with the AdaptiveStateRenderer.

This is a consumer-side module: zero changes to Haloysius core.
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger("halbert.integrations.state_trackers")

DEFAULT_PERSONA_ID = "halbert"


def _record(ledger, persona_id: str, subject: str, predicate: str,
            obj: str, source: str) -> None:
    """Write one state triple, never raising.

    ``TemporalStateLedger.record`` closes the previous triple for the same
    (persona_id, subject, predicate) automatically, so callers get supersession
    and a valid-time history for free.
    """
    if ledger is None:
        return
    try:
        ledger.record(persona_id, subject, predicate, obj, source)
    except Exception as e:
        logger.warning(f"Failed to record {subject}/{predicate}: {e}")


class DiskHealthTracker:
    """Tracks disk health state for the persona.

    Event-driven: update_from_turn() is a no-op. External code calls
    update_health() when discovery detects disk state changes, then
    sync_to_ledger() writes to the TemporalStateLedger.
    """

    def __init__(self, ledger=None, persona_id: str = DEFAULT_PERSONA_ID):
        self._ledger = ledger
        self._persona_id = persona_id
        self._disk_states: dict[str, str] = {}  # device -> health status

    @property
    def name(self) -> str:
        return "disk_health"

    @property
    def category(self):
        from haloysius.persona.state_tracker import InternalStateCategory
        return InternalStateCategory.PHYSIOLOGICAL

    def update_from_turn(self, persona_id, user_message, ai_response, scene_markers=None):
        pass  # Event-driven, not conversation-driven

    def update_health(self, device: str, status: str) -> None:
        """Called by SystemEventMapper when disk health changes."""
        self._disk_states[device] = status
        self.sync_to_ledger()

    def sync_to_ledger(self) -> None:
        for device, status in self._disk_states.items():
            _record(self._ledger, self._persona_id, f"disk:{device}",
                    "disk_health", status, "state_tracker:disk_health")


class ServiceStatusTracker:
    """Tracks service status (running, failed, degraded) for the persona."""

    def __init__(self, ledger=None, persona_id: str = DEFAULT_PERSONA_ID):
        self._ledger = ledger
        self._persona_id = persona_id
        self._service_states: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "service_status"

    @property
    def category(self):
        from haloysius.persona.state_tracker import InternalStateCategory
        return InternalStateCategory.OPERATIONAL

    def update_from_turn(self, persona_id, user_message, ai_response, scene_markers=None):
        pass

    def update_status(self, service: str, status: str) -> None:
        self._service_states[service] = status
        self.sync_to_ledger()

    def sync_to_ledger(self) -> None:
        for service, status in self._service_states.items():
            _record(self._ledger, self._persona_id, f"service:{service}",
                    "service_status", status, "state_tracker:service_status")


class SystemResourceTracker:
    """Tracks CPU, memory, and load average for the persona."""

    def __init__(self, ledger=None, persona_id: str = DEFAULT_PERSONA_ID):
        self._ledger = ledger
        self._persona_id = persona_id
        self._cpu_percent: float = 0.0
        self._mem_percent: float = 0.0
        self._load_avg: float = 0.0

    @property
    def name(self) -> str:
        return "system_resources"

    @property
    def category(self):
        from haloysius.persona.state_tracker import InternalStateCategory
        return InternalStateCategory.PHYSIOLOGICAL

    def update_from_turn(self, persona_id, user_message, ai_response, scene_markers=None):
        pass

    def update_resources(self, cpu: float, mem: float, load: float) -> None:
        self._cpu_percent = cpu
        self._mem_percent = mem
        self._load_avg = load
        self.sync_to_ledger()

    def sync_to_ledger(self) -> None:
        src = "state_tracker:system_resources"
        _record(self._ledger, self._persona_id, "system", "cpu_load",
                f"{self._cpu_percent:.0f}%", src)
        _record(self._ledger, self._persona_id, "system", "memory_usage",
                f"{self._mem_percent:.0f}%", src)
        _record(self._ledger, self._persona_id, "system", "load_average",
                f"{self._load_avg:.2f}", src)


class AdminPresenceTracker:
    """Tracks whether an admin is actively interacting (relational state)."""

    def __init__(self, ledger=None, persona_id: str = DEFAULT_PERSONA_ID):
        self._ledger = ledger
        self._persona_id = persona_id
        self._admin_present: bool = False
        self._admin_user: str = ""

    @property
    def name(self) -> str:
        return "admin_presence"

    @property
    def category(self):
        from haloysius.persona.state_tracker import InternalStateCategory
        return InternalStateCategory.RELATIONAL

    def update_from_turn(self, persona_id, user_message, ai_response, scene_markers=None):
        if user_message:
            self._admin_present = True
            self.sync_to_ledger()

    def set_admin(self, username: str) -> None:
        self._admin_present = True
        self._admin_user = username
        self.sync_to_ledger()

    def clear_admin(self) -> None:
        self._admin_present = False
        self._admin_user = ""
        self.sync_to_ledger()

    def sync_to_ledger(self) -> None:
        _record(self._ledger, self._persona_id, "user", "admin_presence",
                "present" if self._admin_present else "absent",
                "state_tracker:admin_presence")


def register_halbert_predicates() -> None:
    """Register Halbert-specific predicates and subject labels with the renderer.

    This teaches Haloysius's AdaptiveStateRenderer how to render
    machine-specific state predicates as natural prose for the LLM prompt.
    """
    from haloysius.context.state_renderer import register_predicate, register_subject_label

    # Predicates
    register_predicate(
        "disk_health",
        label="Disk Health",
        prose_template="My disk {subject} health is {object}",
    )
    register_predicate(
        "service_status",
        label="Service Status",
        prose_template="Service {subject} is {object}",
    )
    register_predicate(
        "cpu_load",
        label="CPU Load",
        prose_template="CPU load is at {object}",
    )
    register_predicate(
        "memory_usage",
        label="Memory Usage",
        prose_template="Memory usage is at {object}",
    )
    register_predicate(
        "load_average",
        label="Load Average",
        prose_template="System load average is {object}",
    )
    register_predicate(
        "admin_presence",
        label="Admin Presence",
        prose_template="The admin is {object}",
    )
    register_predicate(
        "config_state",
        label="Config State",
        prose_template="Configuration for {subject} is {object}",
    )
    register_predicate(
        "uptime",
        label="Uptime",
        prose_template="System has been up for {object}",
    )

    # Subject labels
    register_subject_label("system", "System")
    register_subject_label("user", "Admin")

    logger.info("Registered Halbert predicates and subject labels")


def register_halbert_state_trackers(ledger=None) -> dict:
    """Register all Halbert state trackers with Haloysius continuity.

    Clears default (human-persona) trackers first, then registers
    machine-specific ones. Returns a dict of tracker instances for
    external event injection.

    Args:
        ledger: Optional TemporalStateLedger instance. If None, trackers
            will be registered but won't sync until a ledger is set.

    Returns:
        Dict mapping tracker names to tracker instances.
    """
    from haloysius.context.continuity import (
        register_state_tracker,
        clear_state_trackers,
    )

    # Clear human-persona defaults (clothing, location)
    clear_state_trackers()

    # Create tracker instances
    trackers = {
        "disk_health": DiskHealthTracker(ledger=ledger),
        "service_status": ServiceStatusTracker(ledger=ledger),
        "system_resources": SystemResourceTracker(ledger=ledger),
        "admin_presence": AdminPresenceTracker(ledger=ledger),
    }

    # Register each
    for tracker in trackers.values():
        register_state_tracker(tracker)

    # Register predicates with the renderer
    register_halbert_predicates()

    logger.info(f"Registered {len(trackers)} Halbert state trackers")
    return trackers
