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

from ..continuity.state_store import ACTOR_SYSTEM

logger = logging.getLogger("halbert.integrations.state_trackers")

DEFAULT_PERSONA_ID = "halbert"


def _record(ledger, subject: str, predicate: str, obj: str, source: str,
            *, reason: str, actor: str = ACTOR_SYSTEM,
            request_id=None, thread_id=None) -> None:
    """Write one state triple, never raising.

    ``StateStore.record_state`` closes the previous triple for the same
    (subject, predicate) automatically, so callers get supersession and a
    valid-time history for free.

    ``reason`` is mandatory here too, not just one level down. This funnel
    covers most tracker writes and will cover most future ones, so letting it
    default would quietly re-open the hole ``record_state`` was changed to
    close. A tracker is a deterministic rule, so its reason names itself
    ("tracker: disk health sweep") and its actor is the system.

    StateStore already fails soft; the guard here is defence in depth, because
    trackers sit on the hot path and ``ledger`` may be any duck-typed object.
    """
    if ledger is None:
        return
    try:
        ledger.record_state(
            subject, predicate, obj, source,
            reason=reason, actor=actor,
            request_id=request_id, thread_id=thread_id,
        )
    except Exception as e:
        logger.warning(f"Failed to record {subject}/{predicate}: {e}")


def default_ledger_path():
    """Halbert's own state-ledger db.

    Standalone today; once Plan A merges this table folds into the thread
    database and ``StateStore(conn=...)`` takes over — no data move.
    """
    from ..continuity.state_store import default_state_db_path

    return default_state_db_path()


def _default_ledger():
    """Open Halbert's machine-state ledger, or return None if unavailable.

    Halbert-owned per founder direction D1: Haloysius has no cross-session
    understanding, so the ledger is not a Haloysius component.
    """
    try:
        from ..continuity.state_store import StateStore

        return StateStore(db_path=str(default_ledger_path()))
    except Exception as e:
        logger.warning(f"State ledger unavailable, trackers will not record: {e}")
        return None


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
            _record(self._ledger, f"disk:{device}", "disk_health", status,
                    "state_tracker:disk_health",
                    reason="tracker: disk health sweep")


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
            _record(self._ledger, f"service:{service}", "service_status", status,
                    "state_tracker:service_status",
                    reason="tracker: service status sweep")


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
        why = "tracker: system resource sample"
        _record(self._ledger, "system", "cpu_load",
                f"{self._cpu_percent:.0f}%", src, reason=why)
        _record(self._ledger, "system", "memory_usage",
                f"{self._mem_percent:.0f}%", src, reason=why)
        _record(self._ledger, "system", "load_average",
                f"{self._load_avg:.2f}", src, reason=why)


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
        _record(self._ledger, "user", "admin_presence",
                "present" if self._admin_present else "absent",
                "state_tracker:admin_presence",
                reason="tracker: admin presence check")


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


def register_halbert_state_trackers(ledger=None, persona_id: str = DEFAULT_PERSONA_ID) -> dict:
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

    if ledger is None:
        ledger = _default_ledger()

    # Create tracker instances
    trackers = {
        "disk_health": DiskHealthTracker(ledger=ledger, persona_id=persona_id),
        "service_status": ServiceStatusTracker(ledger=ledger, persona_id=persona_id),
        "system_resources": SystemResourceTracker(ledger=ledger, persona_id=persona_id),
        "admin_presence": AdminPresenceTracker(ledger=ledger, persona_id=persona_id),
    }

    # Register each
    for tracker in trackers.values():
        register_state_tracker(tracker)

    # Register predicates with the renderer
    register_halbert_predicates()

    logger.info(f"Registered {len(trackers)} Halbert state trackers")
    return trackers
