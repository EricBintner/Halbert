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
On ``SBC_LOW_POWER`` (<4GB RAM, e.g., Pi 4 2GB), a local 3B model will
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

Fallback chain (P4b — corrected order per the singular-entity handoff §8)
------------------------------------------------------------------------
The peer link's compute-offload is the *offline edge case*, not the normal
path: the primary compute for both bodies is the cloud LLM directly.
::

    1. Cloud LLM (normal case — internet up, all turn types)
       └─► cognitive_monologue included: §11.3's prohibition is about
           flooding a peer's GPU with high-frequency ticks, not cloud
    2. Local Model (no internet — if this node's hardware supports one, H7)
       └─► SBC_LOW_POWER / UNKNOWN: SKIP (OOM risk) → go to step 3
       └─► ENTRY_8GB: 3B Q4 model (10-15 tok/s)
       └─► LAPTOP_16GB+: 7B-8B model
    3. Peer Compute (offline fallback — any awake peer's model)
       └─► cognitive_monologue: SKIP (never the peer, §11.3 GPU flood)
       └─► Probed with the 3-consecutive-failure health window (§11.6)
       └─► Peer asleep? Wake-on-LAN attempt (P6b) — only for turns that
           can wait (high_value_event, sleep_consolidation); interactive
           voice takes the template immediately rather than making the
           user sit through a workstation boot
    4. Template Thoughts (degraded — must be clearly marked as such, P4c)
       └─► cognitive_monologue: use template, do NOT defer
       └─► interactive_user: use template as interim, defer to queue
       └─► high_value_event: use heuristic rules, defer to queue
       └─► sleep_consolidation: defer to queue (no interim needed)
    5. No-AI (last resort — "unconscious")
       └─► Template tier unavailable: no response at all. Rare (no
           internet, no local GPU, no awake peer, templates disabled).
           Acceptable — an honest silence beats a fake reply.
    Deferred Task Queue (interactive_user + high_value_event + sleep_consolidation)
       └─► Replayed when a compute tier comes back online
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from .connectivity import ConnectivityProbe
from .peers_config import PeersConfig
from .wake_on_lan import DEFAULT_BROADCAST, send_wol_packet_dual

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# P4c — Template degraded marker
# ---------------------------------------------------------------------------

DEGRADED_MARKER_PREFIX = "[no thinking power"

def is_degraded_response(text: str) -> bool:
    """Check if a response text carries the degraded marker (P4c)."""
    return DEGRADED_MARKER_PREFIX in text

def apply_degraded_marker(text: str, result: "FallbackResult") -> str:
    """Prepend the degraded marker to a response if the result is degraded.

    P4c — When template thoughts or heuristic rules serve a turn, the
    response includes a clear "no thinking power" indicator so the user
    knows it's degraded.  This is a no-op when the result is NOT degraded.
    """
    marker = result.degraded_marker()
    if marker is None:
        return text
    # Don't double-apply if already marked
    if is_degraded_response(text):
        return text
    return f"{marker} {text}"


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


#: Turn types that may wait for a Wake-on-LAN boot (P6b).  A sleeping
#: workstation takes tens of seconds to come up; a voice interaction
#: cannot ask the user to wait through that, so interactive turns take
#: the degraded template immediately.  Cognitive monologue never reaches
#: the peer tier at all (§11.3) and so never wakes it either.
WAKE_ELIGIBLE_TURN_TYPES = frozenset({
    TurnType.HIGH_VALUE_EVENT,
    TurnType.SLEEP_CONSOLIDATION,
})


# ---------------------------------------------------------------------------
# Fallback result
# ---------------------------------------------------------------------------

@dataclass
class FallbackResult:
    """The outcome of a fallback decision.

    This extends ``ModelSelection`` (from tier_router.py) with
    federation-specific fields.
    """
    source: str                    # "cloud" | "peer" | "local_model" | "template" | "heuristic" | "deferred" | "none"
    model_id: Optional[str] = None
    peer_node_id: Optional[str] = None
    fallback_used: bool = False
    fallback_from: Optional[str] = None
    deferred: bool = False
    reason: str = ""
    degraded: bool = False         # P4c: True when template/heuristic (no real AI)

    def degraded_marker(self) -> Optional[str]:
        """P4c — Return a user-visible marker string when this result is degraded.

        When template thoughts or heuristic rules serve a turn (no real AI
        compute was available), this returns a clear indicator so the user
        is never confused about whether they're talking to real AI.

        Returns None when the result is NOT degraded (peer or local model
        served the turn — real AI).
        """
        if not self.degraded:
            return None
        if self.source == "template":
            return "[no thinking power — template response]"
        if self.source == "heuristic":
            return "[no thinking power — heuristic response]"
        if self.source == "deferred":
            return "[no thinking power — request deferred for replay when compute returns]"
        return "[no thinking power]"


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class ComputeRouter:
    """Hardware-profile-aware fallback router for satellite nodes.

    This is instantiated on SATELLITE nodes (not the Compute Host).  It
    decides where to send each inference request:

    1. Cloud LLM when the internet is up (the normal case, all turn types)
    2. Fall back to the local model (if hardware supports it)
    3. Fall back to the Desktop peer (if online and healthy; never for
       cognitive_monologue)
    4. Fall back to template thoughts (degraded, clearly marked)
    5. No-AI (unconscious) when even the template tier is unavailable

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
        *,
        cloud_enabled: bool = False,
        connectivity: Optional[ConnectivityProbe] = None,
        template_enabled: bool = True,
        peers_config: Optional[PeersConfig] = None,
        wol_wait_timeout: float = 45.0,
        wol_poll_interval: float = 2.0,
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
            cloud_enabled: Whether a cloud LLM provider is configured on
                this node (the normal case in production — the router
                cannot read models.yml itself, so the wiring tells it).
                When True and the internet is up, cloud is the primary
                tier for every turn type.
            connectivity: The ``ConnectivityProbe`` deciding whether the
                cloud is reachable (P4a).  A default probe is built when
                ``cloud_enabled`` and none is given; pass one configured
                with the actual provider's base URL when available.
            template_enabled: Whether template thoughts may serve turns
                (they are the honest degraded tier, P4c marks them as
                such).  When False and no compute tier is available, the
                router returns the no-AI placement instead.
            peers_config: The paired-peer store consulted for Wake-on-LAN
                (P6b) — peers with ``wol_enabled`` and a MAC are wake
                targets.  None = no WoL tier.
            wol_wait_timeout: How long to wait for a woken peer to come
                online before falling through to the template tier
                (seconds).  A workstation boot is tens of seconds.
            wol_poll_interval: How often to re-probe peer health while
                waiting for a woken peer (seconds).
        """
        self.peer_endpoint = peer_endpoint
        self.peer_token = peer_token
        self.hardware_profile = hardware_profile
        self.health_probe_interval = health_probe_interval
        self.cloud_enabled = cloud_enabled
        self.template_enabled = template_enabled
        self.peers_config = peers_config
        self.wol_wait_timeout = wol_wait_timeout
        self.wol_poll_interval = wol_poll_interval
        self._connectivity = connectivity or ConnectivityProbe()

        # Peer health state (§11.6 — 3-consecutive-failure threshold)
        # The rolling health window prevents rapid flapping between local
        # and remote models during minor network packet loss, DHCP
        # renewals, or Wi-Fi roaming latency.
        self._peer_online: bool = False
        self._last_probe: float = 0.0
        self._probe_lock = asyncio.Lock()  # created eagerly to avoid race
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
        loop when it needs LLM inference.  It returns the *placement
        decision* — a :class:`FallbackResult` saying where the request
        goes — the generation itself is executed by the caller through
        ``PeerProvider`` / ``TierRouter``.

        Chain (P4b — corrected order, singular-entity handoff §8):
        1. Cloud LLM when the internet is up — every turn type.  Cloud is
           the normal compute path for both bodies; the peer link's
           compute-offload exists for the offline edge case, not the
           primary path.  cognitive_monologue is included: §11.3's
           prohibition is about flooding a peer's GPU with
           high-frequency ticks, not about cloud.
        2. No internet (or no cloud configured): this node's local model
           when the hardware profile supports one (ENTRY_8GB and above).
        3. No local model: the peer, probed with the §11.6 health window
           — but NEVER for cognitive_monologue (§11.3 GPU flood).
        4. No peer: template thoughts serve the turn (degraded, marked
           as such per P4c), and everything except cognitive_monologue
           is deferred to the replay queue:
           - interactive_user: template as interim, deferred
           - high_value_event: heuristic rules, deferred
           - sleep_consolidation: deferred only
        5. Template tier unavailable: no-AI — the entity is unconscious
           rather than pretending to think.

        Note: a ``source="peer"`` decision cannot yet produce tokens —
        ``PeerProvider``'s HTTP methods are still
        TODO(federation-9.3).  The decision layer is complete; the
        transport lands with Phase 9.3.
        """
        # A tier below cloud is only a *fallback* when cloud was the
        # primary that failed; with no cloud configured the top of the
        # available chain is not a fallback at all.
        fell_from = "cloud" if self.cloud_enabled else None

        # 1. Cloud first — the normal case for every turn type.
        if await self._cloud_available():
            return FallbackResult(
                source="cloud",
                model_id=model,
                reason="internet up — cloud LLM is the primary compute path",
            )

        # 2. No internet (or no cloud configured): local model when the
        #    hardware profile supports one (ENTRY_8GB and above, H7).
        if self._hardware_supports_local_model():
            return FallbackResult(
                source="local_model",
                model_id=model,
                fallback_used=self.cloud_enabled,
                fallback_from=fell_from,
                reason=(
                    "no internet — cloud offline, using the local model"
                    if self.cloud_enabled else
                    "no cloud configured — local model is the primary path "
                    "for this node"
                ),
            )

        # 3. No local model (SBC_LOW_POWER / UNKNOWN, H7): the peer, but
        #    never for cognitive_monologue (§11.3).
        if self._should_offload(turn_type) and self.peer_endpoint:
            peer_online = await self._probe_peer_health()
            if peer_online:
                return FallbackResult(
                    source="peer",
                    model_id=model,
                    peer_node_id=self._peer_node_id(),
                    fallback_used=self.cloud_enabled,
                    fallback_from=fell_from,
                    reason="no internet and no local model — offloading to compute peer",
                )
            # The peer was probed and is offline: the template tier below
            # falls back from it.
            fell_from = "peer"

            # P6b — the peer may be a sleeping workstation rather than a
            # dead one.  Before accepting the degraded tier, try to wake
            # it — but only for turns that can afford the boot wait.
            if await self._try_wake_peer(turn_type):
                return FallbackResult(
                    source="peer",
                    model_id=model,
                    peer_node_id=self._peer_node_id(),
                    fallback_used=True,
                    fallback_from="peer",
                    reason=(
                        "peer was asleep — woken via Wake-on-LAN and is "
                        "now serving the turn"
                    ),
                )

        # 4./5. Template thoughts (degraded), or no-AI when the template
        #      tier is unavailable.
        return self._template_fallback(messages, model, turn_type, tools,
                                       fallback_from=fell_from)

    async def _cloud_available(self) -> bool:
        """Whether the cloud tier can serve this turn: a cloud provider is
        configured and the connectivity probe says the internet is up.

        The probe is blocking (cached ~30s by ``ConnectivityProbe``), so
        it runs off the event loop exactly like the peer health probe —
        only a cache-miss probe ever costs the wait.
        """
        if not self.cloud_enabled:
            return False
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._connectivity.is_online)

    async def _try_wake_peer(self, turn_type: TurnType) -> bool:
        """P6b — wake a sleeping workstation and wait for it to serve.

        Sends the WoL magic packet (both standard ports, via
        ``wake_on_lan.send_wol_packet_dual``) to every WoL-enabled peer,
        then polls peer health until ``wol_wait_timeout``.  Returns True
        only when the peer came up and can serve the turn; a failed or
        unanswered wake is an ordinary miss — the caller proceeds to the
        template tier exactly as if no wake were possible.

        Eligibility is deliberate (``WAKE_ELIGIBLE_TURN_TYPES``):
        interactive voice takes the degraded template immediately rather
        than holding the user through a workstation boot, and
        cognitive_monologue never reaches the peer tier at all.  WoL is
        LAN-only (magic packets are broadcast frames), which is why it
        lives behind ``peers_config`` — the operator asserted the peer
        is on this LAN when they set its MAC.
        """
        if turn_type not in WAKE_ELIGIBLE_TURN_TYPES:
            return False
        if not self.peer_endpoint or self.peers_config is None:
            return False
        wol_peers = self.peers_config.list_wol_enabled_peers()
        if not wol_peers:
            return False

        loop = asyncio.get_running_loop()
        sent = False
        for peer in wol_peers:
            broadcast = peer.wol_broadcast or DEFAULT_BROADCAST
            if await loop.run_in_executor(
                None, send_wol_packet_dual, peer.wol_mac, broadcast
            ):
                sent = True
        if not sent:
            logger.warning(
                "WoL: could not send a magic packet to any enabled peer — "
                "proceeding to the template tier"
            )
            return False

        logger.info(
            "WoL: magic packet sent, waiting up to %.0fs for the peer to boot",
            self.wol_wait_timeout,
        )
        deadline = time.monotonic() + self.wol_wait_timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(self.wol_poll_interval)
            if await loop.run_in_executor(None, self._http_health_probe):
                # Fresh online state, wired back into the cached probe so
                # the very next route() hits the peer without re-probing.
                self._peer_online = True
                self._consecutive_failures = 0
                self._last_probe = time.monotonic()
                logger.info("WoL: peer is online after wake")
                return True
        logger.warning(
            "WoL: peer did not come online within %.0fs — proceeding to the "
            "template tier", self.wol_wait_timeout,
        )
        return False

    def _template_fallback(
        self,
        messages: list,
        model: str,
        turn_type: TurnType,
        tools: Optional[list],
        fallback_from: Optional[str] = "peer",
    ) -> FallbackResult:
        """Serve a turn from template thoughts on hardware with no local model.

        Per §11.3, cognitive_monologue is served a template and is NEVER
        deferred (a wake-up flood of 200+ queued monologue turns would
        exhaust the Desktop).  Every other turn type is queued for
        replay when a compute tier returns: interactive_user gets the
        template as an interim, high_value_event is answered by
        heuristic rules, and sleep_consolidation needs no interim at
        all.

        When template thoughts are disabled, the no-AI tier answers
        instead: no compute at all is available, and an honest silence
        beats a fake reply.  Deferral still applies — the turn replays
        when a compute tier comes back.
        """
        source_by_turn = {
            TurnType.COGNITIVE_MONOLOGUE: "template",
            TurnType.INTERACTIVE_USER: "template",
            TurnType.HIGH_VALUE_EVENT: "heuristic",
            TurnType.SLEEP_CONSOLIDATION: "deferred",
        }
        deferred = self._should_defer(turn_type)
        if deferred:
            self._deferred_queue.append({
                "model": model,
                "turn_type": turn_type.value,
                "messages": messages,
                "tools": tools,
                "queued_at": time.time(),
            })
        if not self.template_enabled:
            return FallbackResult(
                source="none",
                fallback_used=True,
                fallback_from=fallback_from,
                deferred=deferred,
                reason=(
                    "no compute tier available and template thoughts "
                    "disabled — no-AI (unconscious)"
                ),
            )
        source = source_by_turn[turn_type]
        return FallbackResult(
            source=source,
            fallback_used=True,
            fallback_from=fallback_from,
            deferred=deferred,
            degraded=True,  # P4c: template/heuristic = no real AI
            reason=(
                "no cloud, no local model, no peer (H7) — template thoughts; "
                "request deferred for replay"
                if deferred else
                "no cloud, no local model, no peer (H7) — template thoughts "
                "(cognitive_monologue is never deferred)"
            ),
        )

    def _peer_node_id(self) -> Optional[str]:
        """Best-effort node label for the configured peer endpoint, or None.

        The router is not told the peer's node_id (that lives in
        peers.json / mDNS discovery); the endpoint host stands in for
        logging until Phase 9 discovery wires the real identity.
        """
        if not self.peer_endpoint:
            return None
        endpoint = self.peer_endpoint.replace("peer://", "http://", 1)
        return endpoint.split("//", 1)[-1].split("/", 1)[0] or None

    async def _probe_peer_health(self) -> bool:
        """Sub-second health probe to the Desktop peer.

        GET ``<peer_endpoint>/api/compute/v1/health`` with the bearer
        token, 1.5s timeout, run off the event loop.  Results are cached
        for ``health_probe_interval`` seconds so a burst of turns probes
        the peer once, not once per turn.

        §11.6 Network Flapping Mitigation:
        A single probe failure does NOT transition to OFFLINE.  The
        router tracks ``_consecutive_failures`` and only marks the peer
        as offline after ``_failure_threshold`` (default 3) consecutive
        failures.  A single success resets the failure counter to 0.

        This prevents rapid flapping between local and remote models
        during minor network packet loss, DHCP renewals, or Wi-Fi
        roaming latency.

        The peer-side health route is not scaffolded in
        ``compute_endpoint.py`` yet (TODO(federation-9.x)), so probes
        against a current peer fail — which is honest: the router stays
        on its fallback chain until Phase 9 ships the route.
        """
        if not self.peer_endpoint:
            return False

        now = time.monotonic()
        if self._last_probe and (now - self._last_probe) < self.health_probe_interval:
            return self._peer_online

        async with self._probe_lock:
            # Re-check under the lock: a concurrent probe may have just
            # refreshed the cache.
            now = time.monotonic()
            if self._last_probe and (now - self._last_probe) < self.health_probe_interval:
                return self._peer_online

            loop = asyncio.get_running_loop()
            healthy = await loop.run_in_executor(None, self._http_health_probe)
            self._last_probe = now

            if healthy:
                self._peer_online = True
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self._failure_threshold:
                    self._peer_online = False

            return self._peer_online

    def _http_health_probe(self) -> bool:
        """Blocking single GET of the peer's health route (executor-safe)."""
        import requests

        endpoint = self.peer_endpoint.replace("peer://", "http://", 1)
        url = endpoint.rstrip("/") + "/api/compute/v1/health"
        headers = {"Authorization": f"Bearer {self.peer_token}"} if self.peer_token else {}
        try:
            resp = requests.get(url, headers=headers, timeout=1.5)
            return resp.status_code == 200
        except Exception:
            return False

    def _hardware_supports_local_model(self) -> bool:
        """Check if the local hardware profile can run a useful local model.

        Per finding H7 and the low-power hardware handoff §7.1:
        - SBC_LOW_POWER (<4GB): False — OOM risk, use template thoughts
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
        """Whether a turn may be sent to the Desktop *peer* at all.

        Per §11.3, cognitive_monologue is NEVER offloaded to the peer —
        10 satellites ticking every 5-10 seconds would flood the peer's
        GPU with 60-120 requests per minute.  All other turn types are
        eligible for peer offload (subject to peer health and hardware
        profile).

        P4b note: this gates the *peer* tier only.  The cloud tier sits
        above it and is allowed for every turn type — the §11.3 concern
        is a shared GPU, not cloud tokens.
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
