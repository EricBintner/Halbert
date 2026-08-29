# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Hardware-profile-aware compute router with multi-tier fallback.

Implements findings C3, H7, and H8 from the federated multi-node review.

C3 — Extends tier_router.py, does not replace it
-------------------------------------------------
This is NOT a standalone router.  It is a peer-aware extension of the
existing ``TierRouter`` (``model/tier_router.py``).  The ``PeerProvider``
(``model/providers/peer.py``) is registered as a new provider type in
``TierRouter``, and this module provides the fallback logic that decides
when to use the peer vs the local model vs template thoughts vs deferred
queue.

The existing ``TierRouter`` already has:
- ``_model_health`` dict for health tracking
- ``ModelSelection.fallback_used`` / ``fallback_from`` for fallback tracking
- ``RateLimiter`` for 429/529 handling
- ``MetaHarnessRouter`` (cascade_router.py) for outcome-based self-tuning

This module adds:
- Peer health probing (sub-second, per finding Pillar 3)
- Hardware-profile-aware fallback (H7)
- Turn-type-aware deferral (H8)

H7 — Hardware-profile-aware fallback
-------------------------------------
On ``SBC_LOW_POWER`` (≤4GB RAM, e.g., Pi 4 2GB), a local 3B model will
OOM.  The fallback chain must NOT attempt to load a micro-model on these
devices.  Instead, it falls back to template thoughts
(``HALBERT_LLM_THOUGHTS=0``) and defers the request.

On ``ENTRY_8GB`` (4-8GB, e.g., N100, Pi 5 4GB), a 3B model at Q4 is
viable (10-15 tok/s on N100, per the low-power hardware handoff §7.1).

On ``LAPTOP_16GB`` and above, a 7B-8B model is viable.

H8 — Turn-type-aware deferral (4-tier classification per §11.3)
-----------------------------------------------------------------
The satellite's ``advance_turn`` (cognitive monologue) is a continuous
tick.  If 10 satellites offloaded their monologue every 5-10 seconds,
the Desktop would receive 60-120 inference requests per minute —
permanently exhausting GPU VRAM (§11.3 Cognitive Contention Finding).

The 4-tier turn classification policy (§11.3):

  Turn Classification       | Offload?    | Fallback if Desktop offline
  --------------------------|-------------|-----------------------------
  ``cognitive_monologue``   | NO (local)  | Template thoughts (never deferred)
  ``interactive_user``      | YES (P2)    | Fast CPU template / micro-model (< 1.5s)
  ``high_value_event``      | YES (P3)    | Local heuristic rule evaluation
  ``sleep_consolidation``   | YES (P3)    | Deferred until Desktop awake + idle

Monologue turns are NEVER deferred (they'd flood the Desktop on wake
with 200+ queued requests).  Interactive user turns get a 1.5s queue
timeout (§11.4) — if the Desktop doesn't have a slot open in 1.5s, the
satellite aborts and runs local fallback.  Sleep consolidation is
batch-deferred until the Desktop is awake and idle.

Network Flapping Mitigation (§11.6)
------------------------------------
Workstations enter sleep, undergo DHCP renewals, and experience Wi-Fi
roaming.  The router maintains a rolling health window with a
3-consecutive-failure threshold before transitioning ONLINE→OFFLINE.
This prevents rapid flapping between local and remote models during
minor network packet loss.

Fallback chain (revised for hardware awareness + 4-tier turns)
---------------------------------------------------------------
::

    1. Desktop Compute Peer (LAN / GPU) [1.5s health probe]
       └─► If Online: Stream generation from peer's GPU model
       └─► cognitive_monologue: SKIP (never offloaded, go to step 3)
    2. Local Model (if hardware profile supports it)
       └─► SBC_LOW_POWER: SKIP (OOM risk) → go to step 3
       └─► ENTRY_8GB: 3B Q4 model (10-15 tok/s)
       └─► LAPTOP_16GB+: 7B-8B model
    3. Template Thoughts (always available, zero compute)
       └─► cognitive_monologue: use template, do NOT defer
       └─► interactive_user: use template as interim, defer to queue
       └─► high_value_event: use heuristic rules, defer to queue
       └─► sleep_consolidation: defer to queue (no interim needed)
    4. Deferred Task Queue (interactive_user + high_value_event + sleep_consolidation)
       └─► Replayed when Desktop peer comes back online
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Turn types (H8, §11.3 — 4-tier classification)
# ---------------------------------------------------------------------------

class TurnType(str, Enum):
    """The type of cognitive turn, determining offload and deferral policy.

    Per §11.3, there are four turn classifications with distinct rules:
    - cognitive_monologue: NEVER offloaded (would flood Desktop GPU)
    - interactive_user: Offloaded with 1.5s queue timeout (§11.4)
    - high_value_event: Offloaded as Priority 3 (Frigo/person detection)
    - sleep_consolidation: Offloaded as Priority 3 batch (3 AM synthesis)
    """
    COGNITIVE_MONOLOGUE = "cognitive_monologue"  # advance_turn tick — strictly local
    INTERACTIVE_USER = "interactive_user"        # voice/chat input — P2, 1.5s timeout
    HIGH_VALUE_EVENT = "high_value_event"        # Frigate/security alert — P3
    SLEEP_CONSOLIDATION = "sleep_consolidation"  # daily memory synthesis — P3 batch


# ---------------------------------------------------------------------------
# Fallback result
# ---------------------------------------------------------------------------

@dataclass
class FallbackResult:
    """The outcome of a fallback decision.

    This extends ``ModelSelection`` (from tier_router.py) with
    federation-specific fields.
    """
    source: str                    # "peer" | "local_model" | "template" | "deferred"
    model_id: Optional[str] = None
    peer_node_id: Optional[str] = None
    fallback_used: bool = False
    fallback_from: Optional[str] = None
    deferred: bool = False
    reason: str = ""


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class ComputeRouter:
    """Hardware-profile-aware fallback router for satellite nodes.

    This is instantiated on SATELLITE nodes (not the Compute Host).  It
    decides where to send each inference request:

    1. Try the Desktop peer (if online and healthy)
    2. Fall back to local model (if hardware supports it)
    3. Fall back to template thoughts (always available)
    4. Defer to queue (user/automation turns only, not monologue)

    The router reuses ``TierRouter``'s health tracking and fallback
    mechanisms.  It does NOT replace ``TierRouter`` — it wraps it with
    peer-aware logic.
    """

    def __init__(
        self,
        peer_endpoint: Optional[str] = None,
        peer_token: Optional[str] = None,
        hardware_profile: str = "unknown",
        health_probe_interval: float = 1.5,
    ):
        """
        Args:
            peer_endpoint: The Desktop peer's compute endpoint URL
                (e.g., "http://desktop.lan:8000").  None = no peer configured.
            peer_token: Bearer token for the peer (from peers_config).
            hardware_profile: The local HardwareProfile value string
                (e.g., "sbc_low_power", "entry_8gb", "laptop_16gb").
            health_probe_interval: How often to probe the peer's health
                (seconds).  Default 1.5s per Pillar 3.
        """
        self.peer_endpoint = peer_endpoint
        self.peer_token = peer_token
        self.hardware_profile = hardware_profile
        self.health_probe_interval = health_probe_interval

        # Peer health state (§11.6 — 3-consecutive-failure threshold)
        # The rolling health window prevents rapid flapping between local
        # and remote models during minor network packet loss, DHCP
        # renewals, or Wi-Fi roaming latency.
        self._peer_online: bool = False
        self._last_probe: float = 0.0
        self._probe_lock = None  # asyncio.Lock, created lazily
        self._consecutive_failures: int = 0
        self._failure_threshold: int = 3  # §11.6: 3 failures before OFFLINE

        # Deferred task queue (H8 — interactive_user + high_value_event +
        # sleep_consolidation only; cognitive_monologue is never deferred)
        self._deferred_queue: list = []  # TODO(federation-9.6): use asyncio.Queue

        logger.info(
            "ComputeRouter initialized: peer=%s, hardware=%s, probe_interval=%ss",
            peer_endpoint or "none", hardware_profile, health_probe_interval,
        )

    async def route(
        self,
        messages: list,
        model: str,
        turn_type: TurnType = TurnType.INTERACTIVE_USER,
        tools: Optional[list] = None,
    ) -> FallbackResult:
        """Route an inference request through the fallback chain.

        This is the main entry point.  Called by the satellite's agent
        loop when it needs LLM inference.

        Per §11.3, cognitive_monologue turns are NEVER sent to the peer
        (they run strictly local with template thoughts).  All other turn
        types attempt the peer first, with a 1.5s queue timeout for
        interactive_user turns (§11.4).

        TODO(federation-9.6): Implement the full fallback chain:
        1. If turn_type == COGNITIVE_MONOLOGUE: skip peer, go to step 3
        2. Probe peer health (if stale, respecting 3-failure threshold)
           a. If peer online: call PeerProvider with appropriate priority
              - interactive_user: P2 with 1.5s queue timeout (§11.4)
              - high_value_event: P3
              - sleep_consolidation: P3 batch
           b. Return FallbackResult(source="peer")
        3. If peer offline and hardware supports local model:
           a. Call local model → return FallbackResult(source="local_model")
        4. If peer offline and hardware does NOT support local model (SBC_LOW_POWER):
           a. cognitive_monologue: return FallbackResult(source="template")
           b. interactive_user: return FallbackResult(source="template", deferred=True)
           c. high_value_event: return FallbackResult(source="heuristic", deferred=True)
           d. sleep_consolidation: return FallbackResult(source="deferred", deferred=True)
        """
        raise NotImplementedError("ComputeRouter.route() — TODO(federation-9.6)")

    async def _probe_peer_health(self) -> bool:
        """Sub-second health probe to the Desktop peer.

        TODO(federation-9.6): GET <peer_endpoint>/api/compute/v1/health
        with the bearer token.  Timeout after 1.5s.  Update _peer_online
        and _last_probe.

        §11.6 Network Flapping Mitigation:
        A single probe failure does NOT transition to OFFLINE.  The
        router tracks ``_consecutive_failures`` and only marks the peer
        as offline after ``_failure_threshold`` (default 3) consecutive
        failures.  A single success resets the failure counter to 0.

        This prevents rapid flapping between local and remote models
        during minor network packet loss, DHCP renewals, or Wi-Fi
        roaming latency.
        """
        raise NotImplementedError("ComputeRouter._probe_peer_health() — TODO(federation-9.6)")

    def _hardware_supports_local_model(self) -> bool:
        """Check if the local hardware profile can run a useful local model.

        Per finding H7 and the low-power hardware handoff §7.1:
        - SBC_LOW_POWER (≤4GB): False — OOM risk, use template thoughts
        - ENTRY_8GB (4-8GB): True — 3B Q4 model at 10-15 tok/s
        - LAPTOP_16GB+: True — 7B-8B model
        - UNKNOWN: False — conservative, don't risk OOM
        """
        return self.hardware_profile in ("entry_8gb", "laptop_16gb", "workstation_32gb",
                                         "workstation_64gb", "mac_studio_128gb",
                                         "server_128gb_plus")

    def _should_defer(self, turn_type: TurnType) -> bool:
        """Whether a turn should be deferred to the replay queue (H8, §11.3).

        Per the 4-tier classification:
        - cognitive_monologue: NEVER deferred (would flood Desktop on wake)
        - interactive_user: deferred (replay when peer returns)
        - high_value_event: deferred (replay when peer returns)
        - sleep_consolidation: deferred (batch replay when Desktop is idle)
        """
        return turn_type != TurnType.COGNITIVE_MONOLOGUE

    def _should_offload(self, turn_type: TurnType) -> bool:
        """Whether a turn should be offloaded to the Desktop peer at all.

        Per §11.3, cognitive_monologue is NEVER offloaded — it runs
        strictly local using template thoughts.  All other turn types
        are eligible for peer offload (subject to peer health and
        hardware profile).
        """
        return turn_type != TurnType.COGNITIVE_MONOLOGUE

    async def replay_deferred(self) -> int:
        """Replay deferred tasks when the peer comes back online.

        TODO(federation-9.6): Drain the deferred queue, submitting each
        request to the now-online peer.  Return the number of tasks
        replayed.

        Called when ``_probe_peer_health()`` transitions from offline
        to online.
        """
        raise NotImplementedError("ComputeRouter.replay_deferred() — TODO(federation-9.6)")
