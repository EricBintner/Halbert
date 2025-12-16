"""
macOS Network Scanner - Network configuration and connectivity.

macOS equivalent of Linux NetworkScanner.

Uses:
- networksetup for interface configuration
- scutil for DNS and network state
- ifconfig for interface details
"""

from __future__ import annotations
from typing import List
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
        discoveries.extend(self._scan_dns())
        discoveries.extend(self._scan_wifi())
        discoveries.extend(self._scan_connectivity())
        
        self.logger.info(f"Found {len(discoveries)} network discoveries")
        return discoveries
    
    def _scan_interfaces(self) -> List[Discovery]:
        """Scan network interfaces."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['networksetup', '-listallhardwareports'])
        if code != 0:
            return discoveries
        
        # Parse hardware ports
        current_port = None
        current_device = None
        
        for line in stdout.splitlines():
            if line.startswith('Hardware Port:'):
                current_port = line.split(':', 1)[1].strip()
            elif line.startswith('Device:'):
                current_device = line.split(':', 1)[1].strip()
                
                if current_port and current_device:
                    # Get interface status
                    status = self._get_interface_status(current_device)
                    
                    discovery_id = make_discovery_id(DiscoveryType.NETWORK, f"iface-{current_device}")
                    
                    discoveries.append(Discovery(
                        id=discovery_id,
                        type=DiscoveryType.NETWORK,
                        name=current_device,
                        title=f"{current_port} ({current_device})",
                        description=f"Interface {current_device}: {status.get('status', 'unknown')}",
                        severity=DiscoverySeverity.SUCCESS if status.get('active') else DiscoverySeverity.INFO,
                        details={
                            'port_name': current_port,
                            'device': current_device,
                            'ip': status.get('ip'),
                            'active': status.get('active', False),
                        },
                        actions=[
                            DiscoveryAction(
                                id=f"info-{current_device}",
                                label="Show Details",
                                command=f"ifconfig {current_device}",
                                dry_run=True,
                            ),
                        ],
                        tags=['network', 'interface', 'macos'],
                    ))
        
        return discoveries
    
    def _get_interface_status(self, device: str) -> dict:
        """Get status of a specific interface."""
        code, stdout, _ = self.run_command(['ifconfig', device])
        
        if code != 0:
            return {'status': 'error', 'active': False}
        
        status = {'active': False, 'status': 'inactive'}
        
        # Check if UP
        if 'status: active' in stdout.lower():
            status['active'] = True
            status['status'] = 'active'
        elif 'status: inactive' in stdout.lower():
            status['status'] = 'inactive'
        
        # Get IP address
        ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', stdout)
        if ip_match:
            status['ip'] = ip_match.group(1)
            status['active'] = True
            status['status'] = f"active ({status['ip']})"
        
        return status
    
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
                details={
                    'servers': dns_servers,
                    'count': len(dns_servers),
                },
                actions=[
                    DiscoveryAction(
                        id="show-dns",
                        label="Show DNS Details",
                        command="scutil --dns",
                        dry_run=True,
                    ),
                ],
                tags=['network', 'dns', 'macos'],
            ))
        
        return discoveries
    
    def _scan_wifi(self) -> List[Discovery]:
        """Scan WiFi status."""
        discoveries = []
        
        # Use airport utility
        airport_path = '/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport'
        
        code, stdout, _ = self.run_command([airport_path, '-I'])
        if code != 0:
            return discoveries
        
        # Parse airport output
        ssid = None
        signal = None
        channel = None
        
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith('SSID:'):
                ssid = line.split(':', 1)[1].strip()
            elif line.startswith('agrCtlRSSI:'):
                signal = int(line.split(':', 1)[1].strip())
            elif line.startswith('channel:'):
                channel = line.split(':', 1)[1].strip()
        
        if ssid:
            # Determine signal quality
            if signal and signal > -50:
                severity = DiscoverySeverity.SUCCESS
                quality = "Excellent"
            elif signal and signal > -60:
                severity = DiscoverySeverity.SUCCESS
                quality = "Good"
            elif signal and signal > -70:
                severity = DiscoverySeverity.WARNING
                quality = "Fair"
            else:
                severity = DiscoverySeverity.WARNING
                quality = "Weak"
            
            discovery_id = make_discovery_id(DiscoveryType.NETWORK, "wifi-status")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.NETWORK,
                name="wifi",
                title=f"WiFi: {ssid}",
                description=f"Connected to '{ssid}' - {quality} signal ({signal} dBm)",
                severity=severity,
                details={
                    'ssid': ssid,
                    'signal_dbm': signal,
                    'channel': channel,
                    'quality': quality,
                },
                actions=[
                    DiscoveryAction(
                        id="wifi-scan",
                        label="Scan Networks",
                        command=f"{airport_path} -s",
                        dry_run=True,
                    ),
                ],
                tags=['network', 'wifi', 'wireless', 'macos'],
            ))
        
        return discoveries
    
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
            details={
                'connected': code == 0,
            },
            actions=[
                DiscoveryAction(
                    id="test-connectivity",
                    label="Test Connectivity",
                    command="ping -c 3 8.8.8.8",
                    dry_run=True,
                ),
            ],
            tags=['network', 'internet', 'connectivity', 'macos'],
        ))
        
        return discoveries
