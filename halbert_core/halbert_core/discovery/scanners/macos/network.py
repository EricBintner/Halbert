# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
macOS Network Scanner - Network configuration and connectivity.

macOS equivalent of Linux NetworkScanner.

Uses:
- networksetup for interface/hardware port listing
- ifconfig for interface status, MAC, speed, MTU
- system_profiler SPAirPortDataType for WiFi (replaces removed `airport` utility)
- socketfilterfw for Application Firewall status
- lsof for listening ports
- scutil for DNS and network state
- ping for connectivity
"""

from __future__ import annotations
from typing import List, Optional
import json
import re

from ..base import BaseScanner
from ...schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class MacNetworkScanner(BaseScanner):
    """
    Scanner for macOS network configuration.

    Equivalent to Linux NetworkScanner but uses macOS tools.
    Produces discoveries with names matching the Linux convention
    (iface-{device}, firewall-*, listening-ports) so the frontend
    Network.tsx filters work cross-platform.
    """

    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.NETWORK

    def is_available(self) -> bool:
        """Check if networksetup is available."""
        return self.command_exists('networksetup')

    def scan(self) -> List[Discovery]:
        """Scan network configuration."""
        discoveries = []

        discoveries.extend(self._scan_interfaces())
        discoveries.extend(self._scan_firewall())
        discoveries.extend(self._scan_listening_ports())
        discoveries.extend(self._scan_dns())
        discoveries.extend(self._scan_wifi())
        discoveries.extend(self._scan_connectivity())

        self.logger.info(f"Found {len(discoveries)} network discoveries")
        return discoveries

    # ─────────────────────────────────────────────────────────────
    # Interface scanning
    # ─────────────────────────────────────────────────────────────

    def _scan_interfaces(self) -> List[Discovery]:
        """Scan network interfaces via networksetup + ifconfig."""
        discoveries = []

        # Build a map of port_name -> device from networksetup
        port_map = self._list_hardware_ports()
        if not port_map:
            return discoveries

        for port_name, device in port_map.items():
            # Skip loopback
            if device == 'lo0':
                continue

            status = self._get_interface_status(device)

            # Determine interface type from port name / device
            iface_type, icon = self._classify_interface(port_name, device)

            # Determine status/severity
            ipv4 = status.get('ip')
            operstate = status.get('operstate', 'unknown')
            is_active = status.get('active', False)

            if ipv4:
                status_str = 'Connected'
                severity = DiscoverySeverity.SUCCESS
            elif is_active:
                status_str = 'Up (No IP)'
                severity = DiscoverySeverity.WARNING
            else:
                status_str = 'Down'
                severity = DiscoverySeverity.INFO

            discovery_id = make_discovery_id(DiscoveryType.NETWORK, f"iface-{device}")

            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.NETWORK,
                name=f"iface-{device}",
                title=f"{device} ({iface_type})",
                description=f"IP: {ipv4 or 'None'}" if ipv4 else f"{iface_type} interface",
                icon=icon,
                severity=severity,
                status=status_str,
                status_detail=f"State: {operstate}",
                source=f"ifconfig {device}",
                data={
                    "interface": device,
                    "type": iface_type,
                    "operstate": operstate,
                    "ipv4": ipv4,
                    "ipv6": status.get('ipv6'),
                    "mac": status.get('mac'),
                    "speed": status.get('speed'),
                    "mtu": status.get('mtu'),
                    "active": is_active,
                    "port_name": port_name,
                },
                actions=[
                    DiscoveryAction(
                        id=f"info-{device}",
                        label="Show Details",
                        command=f"ifconfig {device}",
                    ),
                    DiscoveryAction(id="chat", label="Chat", icon="message-circle"),
                ],
                chat_context=f"Network interface {device} ({iface_type}). "
                             f"Status: {status_str}. IP: {ipv4 or 'None'}.",
            ))

        return discoveries

    def _list_hardware_ports(self) -> dict:
        """Parse `networksetup -listallhardwareports` into {port_name: device}."""
        code, stdout, _ = self.run_command(['networksetup', '-listallhardwareports'])
        if code != 0:
            return {}

        port_map = {}
        current_port = None
        for line in stdout.splitlines():
            if line.startswith('Hardware Port:'):
                current_port = line.split(':', 1)[1].strip()
            elif line.startswith('Device:') and current_port:
                device = line.split(':', 1)[1].strip()
                port_map[current_port] = device
                current_port = None
        return port_map

    def _classify_interface(self, port_name: str, device: str) -> tuple:
        """Classify an interface by type and return (type, icon)."""
        name_lower = (port_name + ' ' + device).lower()
        if 'wi-fi' in name_lower or 'wifi' in name_lower or 'airport' in name_lower:
            return 'WiFi', 'wifi'
        if 'thunderbolt bridge' in name_lower:
            return 'Bridge', 'network'
        if 'thunderbolt' in name_lower:
            return 'Thunderbolt', 'network'
        if 'vpn' in name_lower or 'tailscale' in name_lower or 'wireguard' in name_lower:
            return 'VPN', 'shield'
        if 'docker' in name_lower or 'bridge' in name_lower:
            return 'Bridge', 'network'
        if 'ethernet' in name_lower or device.startswith('en'):
            return 'Ethernet', 'network'
        return 'Unknown', 'help-circle'

    def _get_interface_status(self, device: str) -> dict:
        """Get rich status of a specific interface via ifconfig."""
        code, stdout, _ = self.run_command(['ifconfig', device])
        if code != 0:
            return {'status': 'error', 'active': False, 'operstate': 'down'}

        status = {'active': False, 'operstate': 'down'}

        # Operstate: macOS uses "status: active" for link, flags UP for admin state
        if 'status: active' in stdout.lower():
            status['active'] = True
            status['operstate'] = 'up'
        elif '<UP,' in stdout or 'flags=8' in stdout[:200]:
            # Interface is admin-up but link may be down
            status['operstate'] = 'up' if 'status: inactive' not in stdout.lower() else 'down'
        else:
            status['operstate'] = 'down'

        # IPv4 address
        ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', stdout)
        if ip_match:
            status['ip'] = ip_match.group(1)
            status['active'] = True
            status['operstate'] = 'up'

        # IPv6 address (first non-link-local)
        for m in re.finditer(r'inet6 ([0-9a-f:]+)', stdout):
            addr = m.group(1)
            if not addr.startswith('fe80'):
                status['ipv6'] = addr.split('%')[0]
                break

        # MAC address
        mac_match = re.search(r'ether ([0-9a-f:]{17})', stdout)
        if mac_match:
            status['mac'] = mac_match.group(1)

        # MTU
        mtu_match = re.search(r'mtu (\d+)', stdout)
        if mtu_match:
            status['mtu'] = int(mtu_match.group(1))

        # Speed / media
        media_match = re.search(r'media:\s*\S+\s*\(([^)]+)\)', stdout)
        if media_match:
            status['speed'] = media_match.group(1)

        return status

    # ─────────────────────────────────────────────────────────────
    # Firewall (Application Firewall / socketfilterfw)
    # ─────────────────────────────────────────────────────────────

    def _scan_firewall(self) -> List[Discovery]:
        """Check macOS Application Firewall status via socketfilterfw."""
        discoveries = []

        socketfilterfw = '/usr/libexec/ApplicationFirewall/socketfilterfw'
        code, stdout, _ = self.run_command([socketfilterfw, '--getglobalstate'])
        if code != 0:
            return discoveries

        is_active = 'Firewall is enabled' in stdout or 'State = 1' in stdout

        # Also grab stealth mode and allow signed
        _, stealth_out, _ = self.run_command([socketfilterfw, '--getstealthmode'])
        stealth_on = 'Stealth mode enabled' in stealth_out

        discovery_id = make_discovery_id(DiscoveryType.NETWORK, "firewall-socketfilterfw")

        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.NETWORK,
            name="firewall-socketfilterfw",
            title="Application Firewall",
            description="macOS socketfilterfw" + (" + Stealth Mode" if stealth_on else ""),
            icon="shield",
            severity=DiscoverySeverity.SUCCESS if is_active else DiscoverySeverity.WARNING,
            status="Active" if is_active else "Inactive",
            source="socketfilterfw",
            data={
                "tool": "socketfilterfw",
                "active": is_active,
                "stealth_mode": stealth_on,
            },
            actions=[
                DiscoveryAction(
                    id="show-rules",
                    label="Show Rules",
                    command=f"{socketfilterfw} --listapps",
                ),
                DiscoveryAction(id="chat", label="Chat", icon="message-circle"),
            ],
            chat_context=f"macOS Application Firewall is {'active' if is_active else 'inactive'}."
                         + (" Stealth mode enabled." if stealth_on else ""),
        ))

        return discoveries

    # ─────────────────────────────────────────────────────────────
    # Listening ports (lsof)
    # ─────────────────────────────────────────────────────────────

    def _scan_listening_ports(self) -> List[Discovery]:
        """Scan for listening ports with process details via lsof."""
        discoveries = []

        code, stdout, _ = self.run_command(['lsof', '-i', '-P', '-n'])
        if code != 0:
            return discoveries

        well_known = {
            22: {"name": "SSH", "desc": "Secure Shell - Remote terminal access", "protocol": "TCP"},
            53: {"name": "DNS", "desc": "Domain Name System - Name resolution", "protocol": "TCP/UDP"},
            80: {"name": "HTTP", "desc": "Web server - Unencrypted web traffic", "protocol": "TCP"},
            139: {"name": "NetBIOS", "desc": "Windows file sharing (legacy)", "protocol": "TCP"},
            443: {"name": "HTTPS", "desc": "Secure web server - Encrypted web traffic", "protocol": "TCP"},
            445: {"name": "SMB", "desc": "Windows/Samba file sharing", "protocol": "TCP"},
            5000: {"name": "AirPlay", "desc": "AirPlay / ControlCenter receiver", "protocol": "TCP"},
            631: {"name": "CUPS", "desc": "Printing service - Print server", "protocol": "TCP"},
            7000: {"name": "AirPlay", "desc": "AirPlay receiver", "protocol": "TCP"},
            3000: {"name": "Dev Server", "desc": "Common development server port (Node.js, React)", "protocol": "TCP"},
            3306: {"name": "MySQL", "desc": "MySQL database server", "protocol": "TCP"},
            5173: {"name": "Vite", "desc": "Vite development server", "protocol": "TCP"},
            5432: {"name": "PostgreSQL", "desc": "PostgreSQL database server", "protocol": "TCP"},
            5900: {"name": "VNC", "desc": "Virtual Network Computing - Screen sharing", "protocol": "TCP"},
            6379: {"name": "Redis", "desc": "Redis in-memory data store", "protocol": "TCP"},
            8000: {"name": "Dev Server", "desc": "Common development server port (Python, etc.)", "protocol": "TCP"},
            8080: {"name": "HTTP Alt", "desc": "Alternative HTTP port - Web proxy or dev server", "protocol": "TCP"},
            9000: {"name": "PHP-FPM", "desc": "PHP FastCGI Process Manager", "protocol": "TCP"},
            41641: {"name": "Tailscale", "desc": "Tailscale VPN peer connections", "protocol": "UDP"},
        }

        port_details = []
        seen = set()

        for line in stdout.splitlines()[1:]:  # skip header
            parts = line.split()
            if len(parts) < 9:
                continue
            # lsof -i -P -n columns: COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME
            name_field = parts[-1]
            if 'LISTEN' not in name_field and '*:' not in name_field:
                continue
            # Extract address:port from NAME like *:5173 or 127.0.0.1:8000
            m = re.search(r'([\d.]+|\*):(\d+)', name_field)
            if not m:
                continue
            addr = m.group(1)
            port = int(m.group(2))
            if port in seen:
                continue
            seen.add(port)

            process = parts[0]
            known = well_known.get(port, {})

            port_details.append({
                "port": port,
                "address": addr,
                "process": process,
                "name": known.get("name", process),
                "description": known.get("desc", f"Service running on port {port}"),
                "protocol": known.get("protocol", "TCP"),
            })

        port_details.sort(key=lambda x: x["port"])
        ports = [p["port"] for p in port_details]

        if ports:
            highlighted = [f"{p['port']} ({p['name']})" for p in port_details[:5] if p.get('name')]

            discovery_id = make_discovery_id(DiscoveryType.NETWORK, "listening-ports")

            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.NETWORK,
                name="listening-ports",
                title=f"{len(ports)} Listening Ports",
                description=", ".join(highlighted) + (f" + {len(ports) - 5} more" if len(ports) > 5 else ""),
                icon="network",
                severity=DiscoverySeverity.INFO,
                status=f"{len(ports)} ports",
                source="lsof",
                data={
                    "ports": ports,
                    "port_details": port_details,
                    "count": len(ports),
                },
                actions=[
                    DiscoveryAction(id="list", label="List All", icon="list"),
                    DiscoveryAction(id="chat", label="Chat", icon="message-circle"),
                ],
                chat_context=f"System has {len(ports)} listening ports. "
                             f"Notable: {', '.join(highlighted)}.",
            ))

        return discoveries

    # ─────────────────────────────────────────────────────────────
    # DNS
    # ─────────────────────────────────────────────────────────────

    def _scan_dns(self) -> List[Discovery]:
        """Scan DNS configuration."""
        discoveries = []

        code, stdout, _ = self.run_command(['scutil', '--dns'])
        if code != 0:
            return discoveries

        # Parse DNS servers
        dns_servers = []
        for line in stdout.splitlines():
            if 'nameserver' in line:
                match = re.search(r'nameserver\[\d+\]\s*:\s*(\S+)', line)
                if match:
                    server = match.group(1)
                    if server not in dns_servers:
                        dns_servers.append(server)

        if dns_servers:
            discovery_id = make_discovery_id(DiscoveryType.NETWORK, "dns-servers")

            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.NETWORK,
                name="dns-config",
                title=f"DNS Servers: {len(dns_servers)} configured",
                description=f"Using DNS: {', '.join(dns_servers[:3])}" +
                           (f" (+{len(dns_servers)-3} more)" if len(dns_servers) > 3 else ""),
                severity=DiscoverySeverity.SUCCESS,
                data={
                    'servers': dns_servers,
                    'count': len(dns_servers),
                },
                actions=[
                    DiscoveryAction(
                        id="show-dns",
                        label="Show DNS Details",
                        command="scutil --dns",
                    ),
                ],
            ))

        return discoveries

    # ─────────────────────────────────────────────────────────────
    # WiFi (system_profiler + networksetup — replaces removed `airport`)
    # ─────────────────────────────────────────────────────────────

    def _scan_wifi(self) -> List[Discovery]:
        """Scan WiFi status using system_profiler (airport was removed in macOS 15)."""
        discoveries = []

        # Find the WiFi interface device (usually en1 on desktops, en0 on laptops)
        wifi_device = self._find_wifi_device()
        if not wifi_device:
            return discoveries

        # Get current SSID via networksetup
        code, ssid_out, _ = self.run_command(['networksetup', '-getairportnetwork', wifi_device])
        if code != 0:
            return discoveries

        ssid = None
        # Output: "Current Wi-Fi Network: <SSID>" or "You are not associated with..."
        m = re.search(r'Current Wi-Fi Network:\s*(.+)', ssid_out)
        if m:
            ssid = m.group(1).strip()

        if not ssid:
            # Not connected to WiFi — still report the interface exists but is disconnected
            discovery_id = make_discovery_id(DiscoveryType.NETWORK, "wifi-status")
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.NETWORK,
                name="wifi",
                title="WiFi: Disconnected",
                description=f"WiFi interface {wifi_device} is not associated with a network",
                severity=DiscoverySeverity.INFO,
                status="Disconnected",
                data={
                    'device': wifi_device,
                    'connected': False,
                },
                actions=[
                    DiscoveryAction(
                        id="wifi-scan",
                        label="Scan Networks",
                        command=f"system_profiler SPAirPortDataType",
                    ),
                ],
            ))
            return discoveries

        # Enrich with signal/channel from system_profiler SPAirPortDataType
        signal, channel, phymode, security = self._get_wifi_details(ssid)

        # Determine signal quality
        if signal is not None and signal > -50:
            severity = DiscoverySeverity.SUCCESS
            quality = "Excellent"
        elif signal is not None and signal > -60:
            severity = DiscoverySeverity.SUCCESS
            quality = "Good"
        elif signal is not None and signal > -70:
            severity = DiscoverySeverity.WARNING
            quality = "Fair"
        else:
            severity = DiscoverySeverity.WARNING
            quality = "Weak" if signal is not None else "Unknown"

        discovery_id = make_discovery_id(DiscoveryType.NETWORK, "wifi-status")

        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.NETWORK,
            name="wifi",
            title=f"WiFi: {ssid}",
            description=f"Connected to '{ssid}' - {quality} signal"
                        + (f" ({signal} dBm)" if signal is not None else ""),
            severity=severity,
            status="Connected",
            data={
                'ssid': ssid,
                'signal_dbm': signal,
                'channel': channel,
                'quality': quality,
                'phymode': phymode,
                'security': security,
                'device': wifi_device,
                'connected': True,
            },
            actions=[
                DiscoveryAction(
                    id="wifi-scan",
                    label="Scan Networks",
                    command="system_profiler SPAirPortDataType",
                ),
            ],
        ))

        return discoveries

    def _find_wifi_device(self) -> Optional[str]:
        """Find the WiFi interface device name from hardware ports."""
        port_map = self._list_hardware_ports()
        for port_name, device in port_map.items():
            if 'wi-fi' in port_name.lower() or 'wifi' in port_name.lower():
                return device
        return None

    def _get_wifi_details(self, ssid: str) -> tuple:
        """Get signal/channel/phy/security for the current SSID from system_profiler.

        Returns (signal_dbm, channel, phymode, security) — any may be None.
        """
        code, stdout, _ = self.run_command(
            ['system_profiler', 'SPAirPortDataType', '-json'],
            timeout=15,
        )
        if code != 0:
            return None, None, None, None

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return None, None, None, None

        interfaces = data.get('SPAirPortDataType', [])
        for iface in interfaces:
            for if_key, if_val in iface.items():
                if not isinstance(if_val, dict):
                    continue
                # Current network info is under spairport_airport_current_network
                current = if_val.get('spairport_airport_current_network')
                if not current:
                    # Some macOS versions nest differently
                    continue
                for net_name, net_info in current.items():
                    if not isinstance(net_info, dict):
                        continue
                    # Extract signal/noise
                    signal = None
                    sn = net_info.get('spairport_signal_noise', '')
                    if isinstance(sn, str):
                        m = re.match(r'(-?\d+)\s*dBm', sn)
                        if m:
                            signal = int(m.group(1))
                    channel = net_info.get('spairport_network_channel')
                    phymode = net_info.get('spairport_network_phymode')
                    security = self._parse_security(net_info.get('spairport_security_mode', ''))
                    return signal, channel, phymode, security

        return None, None, None, None

    def _parse_security(self, mode: str) -> Optional[str]:
        """Convert spairport_security_mode_* to a human-readable string."""
        mapping = {
            'spairport_security_mode_none': 'Open',
            'spairport_security_mode_wpa_personal': 'WPA',
            'spairport_security_mode_wpa2_personal': 'WPA2',
            'spairport_security_mode_wpa3_personal': 'WPA3',
            'spairport_security_mode_wpa_enterprise': 'WPA Enterprise',
            'spairport_security_mode_wpa2_enterprise': 'WPA2 Enterprise',
            'spairport_security_mode_wep': 'WEP',
        }
        return mapping.get(mode, mode.replace('spairport_security_mode_', '') if mode else None)

    # ─────────────────────────────────────────────────────────────
    # Connectivity
    # ─────────────────────────────────────────────────────────────

    def _scan_connectivity(self) -> List[Discovery]:
        """Check internet connectivity."""
        discoveries = []

        # Try to reach a reliable host
        code, _, _ = self.run_command(['ping', '-c', '1', '-t', '3', '8.8.8.8'])

        if code == 0:
            severity = DiscoverySeverity.SUCCESS
            status = "Connected"
            description = "Internet connectivity confirmed"
        else:
            severity = DiscoverySeverity.CRITICAL
            status = "No Connection"
            description = "Cannot reach internet (ping to 8.8.8.8 failed)"

        discovery_id = make_discovery_id(DiscoveryType.NETWORK, "internet-connectivity")

        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.NETWORK,
            name="internet",
            title=f"Internet: {status}",
            description=description,
            severity=severity,
            data={
                'connected': code == 0,
            },
            actions=[
                DiscoveryAction(
                    id="test-connectivity",
                    label="Test Connectivity",
                    command="ping -c 3 8.8.8.8",
                ),
            ],
        ))

        return discoveries
