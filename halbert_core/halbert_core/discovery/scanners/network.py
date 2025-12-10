"""
Network Scanner - Discover network interfaces, connections, and configuration.

Implements Phase 9 research from docs/Phase9/deep-dives/07-network-deep-dive.md

Discovers:
- Network interfaces (ethernet, wifi, virtual)
- Active connections
- Firewall status
- Open ports
"""

from __future__ import annotations
from typing import List, Optional
import json
import re

from .base import BaseScanner
from ..schema import (
    Discovery, 
    DiscoveryType, 
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class NetworkScanner(BaseScanner):
    """
    Scanner for network configuration.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.NETWORK
    
    def _get_learned_type(self, name: str) -> Optional[str]:
        """Check if we have a learned classification for this interface."""
        try:
            from ..learned import get_learned_store
            store = get_learned_store()
            classification = store.get(name)
            if classification:
                return classification.type
        except Exception:
            pass
        return None
    
    def _get_icon_for_type(self, iface_type: str) -> str:
        """Get the appropriate icon for an interface type."""
        type_lower = iface_type.lower()
        if 'vpn' in type_lower or 'tailscale' in type_lower or 'wireguard' in type_lower:
            return 'shield'
        if 'wifi' in type_lower or 'wireless' in type_lower:
            return 'wifi'
        if 'docker' in type_lower or 'container' in type_lower:
            return 'container'
        if 'unknown' in type_lower:
            return 'help-circle'
        return 'network'
    
    def _find_interface_config(self, name: str, info_kind: Optional[str] = None) -> Optional[str]:
        """Find configuration file for a network interface."""
        from pathlib import Path
        
        # NetworkManager connections
        nm_paths = [
            Path(f"/etc/NetworkManager/system-connections/{name}.nmconnection"),
            Path(f"/etc/NetworkManager/system-connections/{name}"),
        ]
        for p in nm_paths:
            if p.exists():
                return str(p)
        
        # Check all NetworkManager connections for this interface
        nm_dir = Path("/etc/NetworkManager/system-connections")
        if nm_dir.exists():
            for conn_file in nm_dir.iterdir():
                content = self.read_file(str(conn_file))
                if content and f"interface-name={name}" in content:
                    return str(conn_file)
        
        # systemd-networkd
        networkd_paths = [
            Path(f"/etc/systemd/network/{name}.network"),
            Path(f"/etc/systemd/network/{name}.netdev"),
            Path(f"/etc/systemd/network/10-{name}.network"),
            Path(f"/etc/systemd/network/20-{name}.network"),
        ]
        for p in networkd_paths:
            if p.exists():
                return str(p)
        
        # Netplan (Ubuntu) - look for files with interface name or bridge/bond configs
        netplan_dir = Path("/etc/netplan")
        if netplan_dir.exists():
            # Check if any yaml contains the interface name
            for yaml_file in netplan_dir.glob("*.yaml"):
                content = self.read_file(str(yaml_file))
                if content and name in content:
                    return str(yaml_file)
            
            # For bridge/bond, look for bridge-bond config file even without reading
            if info_kind in ('bridge', 'bond'):
                for yaml_file in netplan_dir.glob("*bridge*bond*.yaml"):
                    return str(yaml_file)
                for yaml_file in netplan_dir.glob("*.yaml"):
                    fname = yaml_file.name.lower()
                    if 'bridge' in fname or 'bond' in fname or info_kind in fname:
                        return str(yaml_file)
        
        # Legacy interfaces file (Debian)
        interfaces_file = Path("/etc/network/interfaces")
        if interfaces_file.exists():
            content = self.read_file(str(interfaces_file))
            if content and name in content:
                return str(interfaces_file)
        
        # Bridge-specific config
        if info_kind == 'bridge':
            bridge_conf = Path(f"/etc/systemd/network/{name}.netdev")
            if bridge_conf.exists():
                return str(bridge_conf)
        
        return None
    
    def scan(self) -> List[Discovery]:
        """Scan system for network resources."""
        discoveries = []
        
        discoveries.extend(self._scan_interfaces())
        discoveries.extend(self._scan_firewall())
        discoveries.extend(self._scan_listening_ports())
        
        self.logger.info(f"Found {len(discoveries)} network items")
        return discoveries
    
    def _scan_interfaces(self) -> List[Discovery]:
        """Scan network interfaces."""
        discoveries = []
        
        # Get interface info with link details (includes master/bridge info)
        code, stdout, _ = self.run_command(["ip", "-j", "-d", "link"])
        
        if code != 0:
            return discoveries
        
        try:
            link_info = json.loads(stdout)
            # Build a map of interface name -> link details (for master, linkinfo, etc.)
            link_map = {iface.get('ifname', ''): iface for iface in link_info}
        except json.JSONDecodeError:
            link_map = {}
        
        # Get address info
        code, stdout, _ = self.run_command(["ip", "-j", "addr"])
        
        if code != 0:
            return discoveries
        
        try:
            interfaces = json.loads(stdout)
            
            for iface in interfaces:
                name = iface.get('ifname', '')
                operstate = iface.get('operstate', 'unknown')
                
                # Skip loopback
                if name == 'lo':
                    continue
                
                # Get link details for this interface
                link_details = link_map.get(name, {})
                master = link_details.get('master')  # Bridge master if this is a port
                link_type = link_details.get('link_type', '')
                linkinfo = link_details.get('linkinfo', {})
                info_kind = linkinfo.get('info_kind', '')
                
                # Get addresses
                addr_info = iface.get('addr_info', [])
                ipv4 = None
                ipv6 = None
                
                for addr in addr_info:
                    if addr.get('family') == 'inet':
                        ipv4 = addr.get('local')
                    elif addr.get('family') == 'inet6' and not addr.get('local', '').startswith('fe80'):
                        ipv6 = addr.get('local')
                
                # Check learned classifications first
                learned_type = self._get_learned_type(name)
                
                # Determine interface type with better detection
                if learned_type:
                    iface_type = learned_type
                    icon = self._get_icon_for_type(learned_type)
                elif info_kind == 'bridge' or name.startswith('br') and not name.startswith('br-'):
                    iface_type = 'Bridge'
                    icon = 'network'
                elif info_kind == 'bond' or name.startswith('bond'):
                    iface_type = 'Bond'
                    icon = 'network'
                elif name.startswith('wl'):
                    iface_type = 'WiFi'
                    icon = 'wifi'
                elif name.startswith('en') or name.startswith('eth'):
                    iface_type = 'Ethernet'
                    icon = 'network'
                elif name.startswith('docker') or name.startswith('br-'):
                    iface_type = 'Docker'
                    icon = 'container'
                elif name.startswith('veth'):
                    iface_type = 'Virtual'
                    icon = 'network'
                elif name.startswith('tun') or name.startswith('tap'):
                    iface_type = 'VPN'
                    icon = 'shield'
                elif 'tailscale' in name:
                    iface_type = 'Tailscale VPN'
                    icon = 'shield'
                else:
                    iface_type = 'Unknown'
                    icon = 'help-circle'
                
                # Determine status with bridge awareness
                # Priority: IP presence > operstate (virtual interfaces often report UNKNOWN)
                if ipv4:
                    status = 'Connected'
                    severity = DiscoverySeverity.SUCCESS
                elif operstate == 'UP':
                    if master:
                        # Bridged interface - no IP is expected, the bridge has the IP
                        status = f'Bridged to {master}'
                        severity = DiscoverySeverity.SUCCESS
                    else:
                        status = 'Up (No IP)'
                        severity = DiscoverySeverity.WARNING
                elif operstate == 'DOWN':
                    status = 'Down'
                    severity = DiscoverySeverity.INFO
                elif master:
                    # Bridged interface with unknown state
                    status = f'Bridged to {master}'
                    severity = DiscoverySeverity.INFO
                else:
                    status = operstate.title() if operstate else 'Unknown'
                    severity = DiscoverySeverity.INFO
                
                discovery_id = make_discovery_id(DiscoveryType.NETWORK, f"iface-{name}")
                
                # Try to find config file for this interface
                config_path = self._find_interface_config(name, info_kind)
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.NETWORK,
                    name=f"iface-{name}",
                    title=f"{name} ({iface_type})",
                    description=f"IP: {ipv4 or 'None'}" if ipv4 else (f"Bridged to {master}" if master else f"{iface_type} interface"),
                    icon=icon,
                    severity=severity,
                    status=status,
                    status_detail=f"State: {operstate}" + (f", master: {master}" if master else ""),
                    source=f"/sys/class/net/{name}",
                    data={
                        "interface": name,
                        "type": iface_type,
                        "operstate": operstate,
                        "ipv4": ipv4,
                        "ipv6": ipv6,
                        "mac": iface.get('address'),
                        "master": master,  # Bridge master if this is a port
                        "link_type": link_type,
                        "info_kind": info_kind,
                        "config_path": config_path,
                    },
                    actions=[
                        DiscoveryAction(id="details", label="Details", icon="info"),
                        DiscoveryAction(id="chat", label="Chat", icon="message-circle"),
                    ],
                    chat_context=f"Network interface {name} ({iface_type}). "
                                f"Status: {status}. IP: {ipv4 or 'None'}." +
                                (f" Bridged to {master}." if master else ""),
                ))
                
        except json.JSONDecodeError:
            pass
        
        return discoveries
    
    def _scan_firewall(self) -> List[Discovery]:
        """Check firewall status."""
        discoveries = []
        
        # Check UFW
        if self.command_exists("ufw"):
            code, stdout, _ = self.run_command(["ufw", "status"])
            if code == 0:
                is_active = "Status: active" in stdout
                
                discovery_id = make_discovery_id(DiscoveryType.NETWORK, "firewall-ufw")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.NETWORK,
                    name="firewall-ufw",
                    title="UFW Firewall",
                    description="Uncomplicated Firewall",
                    icon="shield",
                    severity=DiscoverySeverity.SUCCESS if is_active else DiscoverySeverity.WARNING,
                    status="Active" if is_active else "Inactive",
                    source="ufw",
                    data={
                        "tool": "ufw",
                        "active": is_active,
                    },
                    actions=[
                        DiscoveryAction(id="rules", label="Show Rules", icon="list"),
                        DiscoveryAction(id="chat", label="Chat", icon="message-circle"),
                    ],
                    chat_context=f"UFW Firewall is {'active' if is_active else 'inactive'}.",
                ))
        
        # Check firewalld
        if self.command_exists("firewall-cmd"):
            code, stdout, _ = self.run_command(["firewall-cmd", "--state"])
            if code == 0:
                is_active = "running" in stdout.lower()
                
                discovery_id = make_discovery_id(DiscoveryType.NETWORK, "firewall-firewalld")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.NETWORK,
                    name="firewall-firewalld",
                    title="firewalld",
                    description="Dynamic firewall daemon",
                    icon="shield",
                    severity=DiscoverySeverity.SUCCESS if is_active else DiscoverySeverity.WARNING,
                    status="Running" if is_active else "Stopped",
                    source="firewalld",
                    data={
                        "tool": "firewalld",
                        "active": is_active,
                    },
                    actions=[
                        DiscoveryAction(id="zones", label="Show Zones", icon="list"),
                        DiscoveryAction(id="chat", label="Chat", icon="message-circle"),
                    ],
                    chat_context=f"firewalld is {'running' if is_active else 'stopped'}.",
                ))
        
        return discoveries
    
    def _scan_listening_ports(self) -> List[Discovery]:
        """Scan for listening ports with process details."""
        discoveries = []
        
        code, stdout, _ = self.run_command(["ss", "-tlnp"])
        
        if code != 0:
            return discoveries
        
        # Common ports info - expanded with descriptions
        well_known = {
            22: {"name": "SSH", "desc": "Secure Shell - Remote terminal access", "protocol": "TCP"},
            53: {"name": "DNS", "desc": "Domain Name System - Name resolution", "protocol": "TCP/UDP"},
            80: {"name": "HTTP", "desc": "Web server - Unencrypted web traffic", "protocol": "TCP"},
            139: {"name": "NetBIOS", "desc": "Windows file sharing (legacy)", "protocol": "TCP"},
            443: {"name": "HTTPS", "desc": "Secure web server - Encrypted web traffic", "protocol": "TCP"},
            445: {"name": "SMB", "desc": "Windows/Samba file sharing", "protocol": "TCP"},
            631: {"name": "CUPS", "desc": "Printing service - Print server", "protocol": "TCP"},
            3000: {"name": "Dev Server", "desc": "Common development server port (Node.js, React)", "protocol": "TCP"},
            3306: {"name": "MySQL", "desc": "MySQL database server", "protocol": "TCP"},
            3350: {"name": "XRDP", "desc": "Remote Desktop Protocol for Linux", "protocol": "TCP"},
            3389: {"name": "RDP", "desc": "Windows Remote Desktop Protocol", "protocol": "TCP"},
            3390: {"name": "RDP Alt", "desc": "Alternative RDP port", "protocol": "TCP"},
            5173: {"name": "Vite", "desc": "Vite development server", "protocol": "TCP"},
            5201: {"name": "iperf3", "desc": "Network performance testing", "protocol": "TCP"},
            5432: {"name": "PostgreSQL", "desc": "PostgreSQL database server", "protocol": "TCP"},
            5900: {"name": "VNC", "desc": "Virtual Network Computing - Screen sharing", "protocol": "TCP"},
            6379: {"name": "Redis", "desc": "Redis in-memory data store", "protocol": "TCP"},
            8000: {"name": "Dev Server", "desc": "Common development server port (Python, etc.)", "protocol": "TCP"},
            8080: {"name": "HTTP Alt", "desc": "Alternative HTTP port - Web proxy or dev server", "protocol": "TCP"},
            9000: {"name": "PHP-FPM", "desc": "PHP FastCGI Process Manager", "protocol": "TCP"},
            27017: {"name": "MongoDB", "desc": "MongoDB NoSQL database", "protocol": "TCP"},
            41641: {"name": "Tailscale", "desc": "Tailscale VPN peer connections", "protocol": "UDP"},
        }
        
        # Parse listening ports with process info
        port_details = []
        seen_ports = set()
        
        for line in stdout.strip().splitlines()[1:]:  # Skip header
            parts = line.split()
            if len(parts) >= 4:
                local = parts[3]
                # Extract port and address
                if ':' in local:
                    addr_port = local.rsplit(':', 1)
                    port_str = addr_port[-1]
                    addr = addr_port[0] if len(addr_port) > 1 else '*'
                    
                    if port_str.isdigit():
                        port = int(port_str)
                        
                        # Skip duplicates
                        if port in seen_ports:
                            continue
                        seen_ports.add(port)
                        
                        # Extract process name from last column
                        process = "unknown"
                        if len(parts) >= 6:
                            proc_info = parts[-1]
                            # Parse users:(("process",pid,fd)) format
                            match = re.search(r'\("([^"]+)"', proc_info)
                            if match:
                                process = match.group(1)
                        
                        # Get well-known info or create generic
                        known = well_known.get(port, {})
                        
                        port_details.append({
                            "port": port,
                            "address": addr,
                            "process": process,
                            "name": known.get("name", process if process != "unknown" else f"Port {port}"),
                            "description": known.get("desc", f"Service running on port {port}"),
                            "protocol": known.get("protocol", "TCP"),
                        })
        
        # Sort by port number
        port_details.sort(key=lambda x: x["port"])
        ports = [p["port"] for p in port_details]
        
        # Create a summary discovery
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
                source="ss",
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
