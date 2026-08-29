# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""mDNS peer discovery — beacon broadcast and listener.

Implements findings H9 and H10 from the federated multi-node review.

H9 — mDNS is LAN-only, does not cross Tailscale
------------------------------------------------
mDNS uses link-local multicast (224.0.0.251 / ff02::fb) which does NOT
traverse WireGuard tunnels (Tailscale).  This module documents that
limitation explicitly and the Instance Switcher's manual IP entry
(Pillar 1.3 "Advanced IT Backdoor") is the Tailscale path.

If Tailscale discovery is needed in the future, options are:
1. mDNS reflector (avahi-daemon with enable-reflector=yes on a bridge node)
2. Tailscale's peer discovery API (tailscale status JSON parsing)
3. Manual pairing only (current fallback)

H10 — zeroconf is a lazy optional extra (Haloysius subtractive contract)
------------------------------------------------------------------------
``zeroconf`` is NOT in requirements.txt.  It is imported lazily inside
``_start_zeroconf_listener()`` and ``_start_zeroconf_beacon()``.  If the
package is not installed, discovery gracefully degrades to manual
pairing only.  Add ``zeroconf>=0.131.0`` to the ``[federation]`` extra
in pyproject.toml / setup.cfg.

Service announcement
--------------------
The Compute Host advertises service type ``_halbert._tcp`` on the local
LAN.  The TXT record includes::

    node_id=studio-mac
    node_name=Studio Mac
    role=compute_provider
    capabilities=gpu_llm,sourceprep,apple_foundation,vision
    api_port=8000
    compute_backends=ollama,apple_foundation

Satellites listen for ``_halbert._tcp`` and present discovered hosts in
the PeerPairingModal for one-click pairing.

Finding M13 — Apple Intelligence in the TXT record
---------------------------------------------------
The ``compute_backends`` field distinguishes which inference backends
the host offers.  A Mac Studio might advertise ``apple_foundation,ollama``
while a Linux GPU rig advertises ``vllm,ollama``.  Satellites use this
to route to the right backend (finding M13).
"""
from __future__ import annotations

import logging
import socket
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# mDNS service type for Halbert peer discovery.
# Following the convention: _<service>._<protocol>
SERVICE_TYPE = "_halbert._tcp."


# ---------------------------------------------------------------------------
# Discovered peer data
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredPeer:
    """A peer discovered via mDNS or manual entry.

    This is the unauthenticated discovery record — it has no token.
    The user must pair (exchange token) before any compute or fleet
    interaction is allowed.
    """
    node_id: str
    node_name: str
    role: str                              # "compute_provider" | "satellite"
    host: str                              # IP address or hostname
    port: int
    capabilities: List[str] = field(default_factory=list)
    compute_backends: List[str] = field(default_factory=list)  # M13: ollama, apple_foundation, vllm, mlx

    @property
    def endpoint(self) -> str:
        return f"http://{self.host}:{self.port}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "role": self.role,
            "host": self.host,
            "port": self.port,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities,
            "compute_backends": self.compute_backends,
        }


# ---------------------------------------------------------------------------
# TXT record serialization
# ---------------------------------------------------------------------------

def build_txt_record(
    node_id: str,
    node_name: str,
    role: str,
    port: int,
    capabilities: List[str],
    compute_backends: List[str],
) -> Dict[str, str]:
    """Build the mDNS TXT record for this node.

    All values are strings (mDNS TXT record requirement).
    """
    return {
        "node_id": node_id,
        "node_name": node_name,
        "role": role,
        "api_port": str(port),
        "capabilities": ",".join(capabilities),
        "compute_backends": ",".join(compute_backends),
    }


def parse_txt_record(txt: Dict[str, Any]) -> Dict[str, Any]:
    """Parse an mDNS TXT record into structured fields."""
    return {
        "node_id": txt.get("node_id", "unknown"),
        "node_name": txt.get("node_name", txt.get("node_id", "unknown")),
        "role": txt.get("role", "satellite"),
        "port": int(txt.get("api_port", "8000")),
        "capabilities": txt.get("capabilities", "").split(",") if txt.get("capabilities") else [],
        "compute_backends": txt.get("compute_backends", "").split(",") if txt.get("compute_backends") else [],
    }


# ---------------------------------------------------------------------------
# Beacon — broadcast this node's presence on LAN
# ---------------------------------------------------------------------------

class PeerBeacon:
    """Broadcasts this Halbert node's presence via mDNS.

    Only the Compute Host needs to broadcast (satellites listen).
    But broadcasting from both is harmless and enables bidirectional
    discovery (Desktop can also discover satellites for the Fleet Cockpit).

    TODO(federation-9.7): Implement using zeroconf.ServiceRegistration.
    """

    def __init__(
        self,
        node_id: str,
        node_name: str,
        role: str,
        port: int,
        capabilities: List[str],
        compute_backends: List[str],
    ):
        self.node_id = node_id
        self.node_name = node_name
        self.role = role
        self.port = port
        self.capabilities = capabilities
        self.compute_backends = compute_backends
        self._zeroconf = None
        self._registration = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start broadcasting. Imports zeroconf lazily (H10)."""
        try:
            from zeroconf import Zeroconf, ServiceInfo
        except ImportError:
            logger.warning(
                "zeroconf not installed — mDNS beacon disabled. "
                "Install with: pip install 'halbert-core[federation]' "
                "or use manual pairing (Instance Switcher → Add Instance)."
            )
            return

        # TODO(federation-9.7): Create ServiceInfo and register with Zeroconf
        # The service name is "Halbert <node_name>._halbert._tcp.local."
        # The TXT record is built via build_txt_record()
        raise NotImplementedError("PeerBeacon.start() — TODO(federation-9.7)")

    def stop(self) -> None:
        """Stop broadcasting and clean up."""
        if self._zeroconf is None:
            return
        # TODO(federation-9.7): Unregister service and close zeroconf
        raise NotImplementedError("PeerBeacon.stop() — TODO(federation-9.7)")


# ---------------------------------------------------------------------------
# Listener — discover other Halbert nodes on LAN
# ---------------------------------------------------------------------------

class PeerListener:
    """Listens for mDNS announcements from other Halbert nodes.

    Calls ``on_discovered`` callback when a new peer is found, and
    ``on_lost`` when a peer disappears (mDNS goodbye packet or timeout).

    TODO(federation-9.7): Implement using zeroconf.ServiceBrowser.
    """

    def __init__(
        self,
        on_discovered: Callable[[DiscoveredPeer], None],
        on_lost: Optional[Callable[[str], None]] = None,
    ):
        """
        Args:
            on_discovered: Called when a new peer appears on the LAN.
            on_lost: Called when a peer disappears (node_id as arg).
        """
        self.on_discovered = on_discovered
        self.on_lost = on_lost
        self._zeroconf = None
        self._browser = None
        self._discovered: Dict[str, DiscoveredPeer] = {}  # node_id -> peer
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start listening for _halbert._tcp announcements.

        Imports zeroconf lazily (H10). If not installed, logs a warning
        and returns — manual pairing is the fallback.
        """
        try:
            from zeroconf import Zeroconf, ServiceBrowser
        except ImportError:
            logger.warning(
                "zeroconf not installed — mDNS discovery disabled. "
                "Install with: pip install 'halbert-core[federation]' "
                "or use manual pairing (Instance Switcher → Add Instance)."
            )
            return

        # TODO(federation-9.7): Create Zeroconf and ServiceBrowser with
        # a custom ServiceListener that parses TXT records and calls
        # self.on_discovered with DiscoveredPeer objects.
        raise NotImplementedError("PeerListener.start() — TODO(federation-9.7)")

    def stop(self) -> None:
        """Stop listening and clean up."""
        if self._zeroconf is None:
            return
        # TODO(federation-9.7): Cancel ServiceBrowser and close zeroconf
        raise NotImplementedError("PeerListener.stop() — TODO(federation-9.7)")

    def get_discovered(self) -> List[DiscoveredPeer]:
        """Return all currently-discovered peers (snapshot)."""
        with self._lock:
            return list(self._discovered.values())


# ---------------------------------------------------------------------------
# Convenience — get this node's identity for mDNS
# ---------------------------------------------------------------------------

def get_node_identity() -> Dict[str, Any]:
    """Get this node's identity for mDNS announcement.

    Reads from env vars (Phase 7 multi-instance) and hardware detection
    to build the TXT record fields.

    TODO(federation-9.7): Call HardwareDetector to populate
    compute_backends (ollama, apple_foundation, mlx, vllm).
    """
    import os
    node_id = os.environ.get("HALBERT_PERSONA_ID", "halbert") + "-" + socket.gethostname()
    node_name = os.environ.get("HALBERT_DISPLAY_NAME", socket.gethostname())
    role = "compute_provider" if os.environ.get("HALBERT_ROLE", "host") == "host" else "satellite"
    port = int(os.environ.get("HALBERT_PORT", "8000"))

    # TODO(federation-9.7): Detect compute backends from hardware + running services
    # - Check if Ollama is running (curl localhost:11434/api/tags)
    # - Check if apple-foundation bridge is running (HardwareDetector)
    # - Check if vLLM is running
    compute_backends: List[str] = []

    # Capabilities — what this node can offer to peers
    capabilities: List[str] = []
    if role == "compute_provider":
        capabilities.append("gpu_llm")
        # TODO(federation-9.7): Check if SourcePrep daemon is running
        # capabilities.append("sourceprep")
        # TODO(federation-9.10): Check if apple_intelligence is available
        # capabilities.append("apple_foundation")

    return {
        "node_id": node_id,
        "node_name": node_name,
        "role": role,
        "port": port,
        "capabilities": capabilities,
        "compute_backends": compute_backends,
    }
