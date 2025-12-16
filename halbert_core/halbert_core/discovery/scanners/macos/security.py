"""
macOS Security Scanner - Security configuration discovery.

macOS equivalent of Linux SecurityScanner.

Discovers:
- System Integrity Protection (SIP) status
- Gatekeeper status
- FileVault encryption status
- Firewall status
- Privacy permissions (TCC)
"""

from __future__ import annotations
from typing import List

from ..base import BaseScanner
from ...schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class MacSecurityScanner(BaseScanner):
    """
    Scanner for macOS security configuration.
    
    Equivalent to Linux SecurityScanner but for macOS security model.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.SECURITY
    
    def is_available(self) -> bool:
        """Check if security tools are available."""
        return self.command_exists('csrutil') or self.command_exists('spctl')
    
    def scan(self) -> List[Discovery]:
        """Scan security configuration."""
        discoveries = []
        
        discoveries.extend(self._scan_sip())
        discoveries.extend(self._scan_gatekeeper())
        discoveries.extend(self._scan_filevault())
        discoveries.extend(self._scan_firewall())
        
        self.logger.info(f"Found {len(discoveries)} security discoveries")
        return discoveries
    
    def _scan_sip(self) -> List[Discovery]:
        """Check System Integrity Protection status."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['csrutil', 'status'])
        if code != 0:
            return discoveries
        
        enabled = 'enabled' in stdout.lower() and 'disabled' not in stdout.lower()
        
        if enabled:
            severity = DiscoverySeverity.SUCCESS
            title = "SIP: Enabled"
            description = "System Integrity Protection is enabled (recommended)"
        else:
            severity = DiscoverySeverity.WARNING
            title = "SIP: Disabled"
            description = "System Integrity Protection is disabled - system is less secure"
        
        discovery_id = make_discovery_id(DiscoveryType.SECURITY, "sip-status")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SECURITY,
            name="sip",
            title=title,
            description=description,
            severity=severity,
            details={
                'enabled': enabled,
                'output': stdout.strip(),
            },
            actions=[
                DiscoveryAction(
                    id="sip-status",
                    label="Check SIP Status",
                    command="csrutil status",
                    dry_run=True,
                ),
            ],
            tags=['security', 'sip', 'macos'],
        ))
        
        return discoveries
    
    def _scan_gatekeeper(self) -> List[Discovery]:
        """Check Gatekeeper status."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['spctl', '--status'])
        if code != 0:
            return discoveries
        
        enabled = 'enabled' in stdout.lower()
        
        if enabled:
            severity = DiscoverySeverity.SUCCESS
            title = "Gatekeeper: Enabled"
            description = "Gatekeeper is enabled - apps are verified before running"
        else:
            severity = DiscoverySeverity.WARNING
            title = "Gatekeeper: Disabled"
            description = "Gatekeeper is disabled - unverified apps can run"
        
        discovery_id = make_discovery_id(DiscoveryType.SECURITY, "gatekeeper-status")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SECURITY,
            name="gatekeeper",
            title=title,
            description=description,
            severity=severity,
            details={
                'enabled': enabled,
            },
            actions=[
                DiscoveryAction(
                    id="gatekeeper-status",
                    label="Check Gatekeeper",
                    command="spctl --status",
                    dry_run=True,
                ),
            ],
            tags=['security', 'gatekeeper', 'macos'],
        ))
        
        return discoveries
    
    def _scan_filevault(self) -> List[Discovery]:
        """Check FileVault encryption status."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['fdesetup', 'status'])
        if code != 0:
            return discoveries
        
        enabled = 'on' in stdout.lower() or 'enabled' in stdout.lower()
        
        if enabled:
            severity = DiscoverySeverity.SUCCESS
            title = "FileVault: Enabled"
            description = "Disk encryption is enabled - data is protected"
        else:
            severity = DiscoverySeverity.WARNING
            title = "FileVault: Disabled"
            description = "Disk encryption is disabled - data is not encrypted at rest"
        
        discovery_id = make_discovery_id(DiscoveryType.SECURITY, "filevault-status")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SECURITY,
            name="filevault",
            title=title,
            description=description,
            severity=severity,
            details={
                'enabled': enabled,
                'output': stdout.strip(),
            },
            actions=[
                DiscoveryAction(
                    id="filevault-status",
                    label="Check FileVault",
                    command="fdesetup status",
                    dry_run=True,
                ),
            ],
            tags=['security', 'filevault', 'encryption', 'macos'],
        ))
        
        return discoveries
    
    def _scan_firewall(self) -> List[Discovery]:
        """Check firewall status."""
        discoveries = []
        
        # Check Application Firewall
        code, stdout, _ = self.run_command([
            '/usr/libexec/ApplicationFirewall/socketfilterfw',
            '--getglobalstate'
        ])
        
        if code != 0:
            return discoveries
        
        enabled = 'enabled' in stdout.lower()
        
        if enabled:
            severity = DiscoverySeverity.SUCCESS
            title = "Firewall: Enabled"
            description = "Application firewall is enabled"
        else:
            severity = DiscoverySeverity.INFO
            title = "Firewall: Disabled"
            description = "Application firewall is disabled"
        
        # Check stealth mode
        stealth_code, stealth_out, _ = self.run_command([
            '/usr/libexec/ApplicationFirewall/socketfilterfw',
            '--getstealthmode'
        ])
        stealth_enabled = 'enabled' in stealth_out.lower() if stealth_code == 0 else False
        
        discovery_id = make_discovery_id(DiscoveryType.SECURITY, "firewall-status")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SECURITY,
            name="firewall",
            title=title,
            description=description + (", stealth mode on" if stealth_enabled else ""),
            severity=severity,
            details={
                'enabled': enabled,
                'stealth_mode': stealth_enabled,
            },
            actions=[
                DiscoveryAction(
                    id="firewall-status",
                    label="Check Firewall",
                    command="/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate",
                    dry_run=True,
                ),
            ],
            tags=['security', 'firewall', 'macos'],
        ))
        
        return discoveries
