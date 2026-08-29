# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Satellite telemetry agent — reuses the discovery engine, does not duplicate it.

Implements finding M12 from the federated multi-node review.

M12 — Telemetry agent duplicates the discovery engine
------------------------------------------------------
The ``discovery/`` package already has scanners (storage, service,
network, thermal, process) producing structured ``Discovery`` objects on
both macOS and Linux, with platform-aware registration.  Building a
parallel ``runtime/telemetry_agent.py`` would mean two code paths for
"what services are running on this Pi," two data shapes, and two update
cadences.

This module is a thin wrapper that:
1. Calls ``DiscoveryEngine.scan_all()`` periodically (every 60s by default)
2. Diffs against the last snapshot to produce a delta
3. Adds live vitals (CPU%, RAM%, temp) via ``psutil`` — the one thing the
   discovery engine doesn't provide as a continuous stream
4. Publishes the telemetry to the Desktop's Fleet Cockpit via SSE or
   periodic POST

Data flow
---------
::

    Satellite                          Desktop (Fleet Cockpit)
    ┌──────────────┐                   ┌──────────────────┐
    │ DiscoveryEngine │                │ fleet.py route   │
    │   .scan_all()   │                │   /api/fleet/    │
    │       ↓         │                │     {node_id}/   │
    │ TelemetryAgent  │── POST ──────► │   telemetry      │
    │   + vitals      │                │       ↓          │
    │   (psutil)      │                │  Fleet Cockpit UI│
    └──────────────┘                   └──────────────────┘

The telemetry payload is a ``Discovery`` snapshot + vitals, NOT a
parallel metrics format.  The Desktop's Fleet Cockpit renders it using
the same components that render local discoveries.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Vitals — the live metrics that discovery doesn't cover
# ---------------------------------------------------------------------------

@dataclass
class Vitals:
    """Live system vitals (the continuous metrics that Discovery snapshots don't provide).

    Discovery scans are periodic (every 60s) and structural (what services
    exist, what disks are mounted).  Vitals are continuous (every 5s) and
    operational (CPU%, RAM%, temperature right now).
    """
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_available_mb: float = 0.0
    temperature_c: Optional[float] = None  # None if no temp sensor (e.g., most Macs)
    uptime_seconds: float = 0.0
    load_average_1m: Optional[float] = None  # None on macOS (no /proc/loadavg in the same way)
    disk_percent: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_percent": round(self.cpu_percent, 1),
            "memory_percent": round(self.memory_percent, 1),
            "memory_available_mb": round(self.memory_available_mb, 1),
            "temperature_c": self.temperature_c,
            "uptime_seconds": round(self.uptime_seconds, 0),
            "load_average_1m": self.load_average_1m,
            "disk_percent": round(self.disk_percent, 1),
        }


# ---------------------------------------------------------------------------
# Telemetry payload
# ---------------------------------------------------------------------------

@dataclass
class TelemetryPayload:
    """The full telemetry payload sent from satellite to Desktop.

    Combines:
    - ``discoveries``: snapshot from DiscoveryEngine.scan_all() (M12 — reuse)
    - ``vitals``: live CPU/RAM/temp from psutil
    - ``metadata``: node identity, timestamp
    """
    node_id: str
    timestamp: float = field(default_factory=time.time)
    discoveries: List[Dict[str, Any]] = field(default_factory=list)
    vitals: Vitals = field(default_factory=Vitals)
    discovery_count: int = 0
    discovery_delta: int = 0  # changes since last snapshot

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "discoveries": self.discoveries,
            "vitals": self.vitals.to_dict(),
            "discovery_count": self.discovery_count,
            "discovery_delta": self.discovery_delta,
        }


# ---------------------------------------------------------------------------
# Telemetry agent
# ---------------------------------------------------------------------------

class TelemetryAgent:
    """Collects and publishes telemetry from a satellite node.

    Runs as a background thread (not asyncio) because the discovery
    engine and psutil are synchronous.  The publish callback is called
    from the thread — the callback should be thread-safe (e.g., use
    ``requests.post`` which is thread-safe).

    TODO(federation-9.5): Implement the collection loop.
    """

    def __init__(
        self,
        node_id: str,
        desktop_endpoint: Optional[str] = None,
        peer_token: Optional[str] = None,
        discovery_interval: float = 60.0,
        vitals_interval: float = 5.0,
        on_publish: Optional[Any] = None,
    ):
        """
        Args:
            node_id: This satellite's node_id.
            desktop_endpoint: The Desktop's fleet endpoint URL for
                posting telemetry.  None = no remote publishing (local only).
            peer_token: Bearer token for authenticating to the Desktop.
            discovery_interval: How often to re-scan (seconds).  Default 60s.
            vitals_interval: How often to collect vitals (seconds).  Default 5s.
            on_publish: Optional callback(payload: TelemetryPayload) called
                when telemetry is collected.  If None, posts to desktop_endpoint.
        """
        self.node_id = node_id
        self.desktop_endpoint = desktop_endpoint
        self.peer_token = peer_token
        self.discovery_interval = discovery_interval
        self.vitals_interval = vitals_interval
        self.on_publish = on_publish

        self._thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        self._last_discoveries: List[Dict[str, Any]] = []
        self._engine = None  # DiscoveryEngine, created lazily

        logger.info(
            "TelemetryAgent initialized: node=%s, desktop=%s, discovery=%ss, vitals=%ss",
            node_id, desktop_endpoint or "local-only", discovery_interval, vitals_interval,
        )

    def start(self) -> None:
        """Start the telemetry collection thread.

        TODO(federation-9.5): Start a daemon thread that:
        1. Every ``discovery_interval`` seconds: call DiscoveryEngine.scan_all(),
           diff against _last_discoveries, build TelemetryPayload
        2. Every ``vitals_interval`` seconds: collect Vitals via psutil,
           merge with last discovery snapshot, build TelemetryPayload
        3. Publish via on_publish callback or POST to desktop_endpoint
        """
        # TODO(federation-9.5):
        # self._thread = threading.Thread(target=self._collection_loop, daemon=True)
        # self._thread.start()
        raise NotImplementedError("TelemetryAgent.start() — TODO(federation-9.5)")

    def stop(self) -> None:
        """Stop the telemetry collection thread."""
        self._shutdown.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def _collection_loop(self) -> None:
        """Main collection loop — runs in a daemon thread.

        TODO(federation-9.5): Implement the dual-interval loop:
        - Discovery scan every 60s (expensive — runs all scanners)
        - Vitals poll every 5s (cheap — just psutil calls)
        - Publish on each collection
        """
        raise NotImplementedError("TelemetryAgent._collection_loop() — TODO(federation-9.5)")

    def _collect_vitals(self) -> Vitals:
        """Collect live vitals via psutil.

        TODO(federation-9.5): Implement using psutil:
        - cpu_percent(interval=0.5)
        - virtual_memory()
        - disk_usage('/')
        - sensors_temperatures() (Linux only, may not exist on macOS)
        - uptime via psutil.boot_time()
        - loadavg via os.getloadavg() (Unix only)
        """
        raise NotImplementedError("TelemetryAgent._collect_vitals() — TODO(federation-9.5)")

    def _scan_discoveries(self) -> List[Dict[str, Any]]:
        """Run the discovery engine and return discoveries as dicts.

        TODO(federation-9.5): Get or create DiscoveryEngine, call
        scan_all(), convert Discovery objects to dicts.
        """
        raise NotImplementedError("TelemetryAgent._scan_discoveries() — TODO(federation-9.5)")

    def _publish(self, payload: TelemetryPayload) -> None:
        """Publish telemetry to the Desktop or via callback.

        TODO(federation-9.5): If on_publish is set, call it.  Otherwise,
        POST to {desktop_endpoint}/api/fleet/{node_id}/telemetry with
        the bearer token.
        """
        raise NotImplementedError("TelemetryAgent._publish() — TODO(federation-9.5)")
