# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Wake-on-LAN magic packet sender.

P6a — Provides the HA server (always-on mind) the ability to wake a
sleeping workstation so it can serve compute requests.  WoL is LAN-only
(magic packets are broadcast frames that don't cross routers or Tunnels
like Tailscale).  It is off by default and must be explicitly enabled per
peer in ``peers_config`` (P6c).

The magic packet format is standard:
- 6 bytes of ``0xFF`` (sync stream)
- 16 repetitions of the target MAC address (96 bytes)
- Total: 102 bytes, sent as a UDP broadcast to port 9 (discard) or 7.

Pure stdlib (``socket``) — no new dependencies.
"""
from __future__ import annotations

import logging
import re
import socket
from typing import Optional

logger = logging.getLogger(__name__)

# Standard WoL ports.  Port 9 (discard) is the most widely supported;
# some NICs listen on port 7 (echo).  We send to both for compatibility.
WOL_PORT_PRIMARY = 9
WOL_PORT_SECONDARY = 7

# Default broadcast address.  Can be overridden by the caller.
DEFAULT_BROADCAST = "255.255.255.255"

# Regex for validating MAC addresses: AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF
_MAC_PATTERN = re.compile(
    r"^[0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}$"
)


def parse_mac(mac_address: str) -> bytes:
    """Parse a MAC address string into 6 bytes.

    Accepts ``AA:BB:CC:DD:EE:FF`` or ``AA-BB-CC-DD-EE-FF`` (case-insensitive).
    Surrounding whitespace is stripped.  Raises ValueError on invalid format.
    """
    if not isinstance(mac_address, str):
        raise ValueError(f"MAC address must be a string, got {type(mac_address).__name__}")
    mac_address = mac_address.strip()
    if not _MAC_PATTERN.match(mac_address):
        raise ValueError(
            f"Invalid MAC address {mac_address!r} — expected AA:BB:CC:DD:EE:FF "
            f"or AA-BB-CC-DD-EE-FF"
        )
    hex_str = mac_address.replace(":", "").replace("-", "")
    return bytes(int(hex_str[i:i + 2], 16) for i in range(0, 12, 2))


def build_magic_packet(mac_address: str) -> bytes:
    """Construct the WoL magic packet payload.

    The payload is 6 bytes of ``0xFF`` followed by 16 repetitions of the
    target MAC address (102 bytes total).

    Raises ValueError if the MAC address is invalid.
    """
    mac_bytes = parse_mac(mac_address)
    return b"\xff" * 6 + mac_bytes * 16


def send_wol_packet(
    mac_address: str,
    broadcast_address: str = DEFAULT_BROADCAST,
    port: int = WOL_PORT_PRIMARY,
) -> bool:
    """Send a Wake-on-LAN magic packet to wake a sleeping machine.

    Args:
        mac_address: Target MAC address (e.g., ``"AA:BB:CC:DD:EE:FF"``).
        broadcast_address: Broadcast IP to send to.  Defaults to
            ``255.255.255.255`` (limited broadcast).  For subnet-directed
            broadcast, use the subnet's broadcast address (e.g.,
            ``192.168.1.255``).
        port: UDP port to send to.  Default 9 (discard).  Some NICs
            require port 7 (echo).

    Returns:
        True if the packet was sent successfully, False on error.
        Errors are logged but not raised — the caller (ComputeRouter)
        should treat a failed wake attempt as "peer still asleep" and
        proceed to the next fallback step.
    """
    try:
        payload = build_magic_packet(mac_address)
    except (ValueError, TypeError) as e:
        logger.error("WoL: %s", e)
        return False

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(payload, (broadcast_address, port))
        logger.info(
            "WoL: magic packet sent to %s at %s:%d (%d bytes)",
            mac_address, broadcast_address, port, len(payload),
        )
        return True
    except (OSError, TypeError) as e:
        logger.warning("WoL: failed to send magic packet to %s: %s", mac_address, e)
        return False


def send_wol_packet_dual(
    mac_address: str,
    broadcast_address: str = DEFAULT_BROADCAST,
) -> bool:
    """Send the WoL magic packet to both standard ports (7 and 9).

    Some NICs only listen on one port.  Sending to both maximizes
    compatibility.  Returns True if at least one send succeeded.
    """
    ok1 = send_wol_packet(mac_address, broadcast_address, WOL_PORT_PRIMARY)
    ok2 = send_wol_packet(mac_address, broadcast_address, WOL_PORT_SECONDARY)
    return ok1 or ok2
