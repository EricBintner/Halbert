# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Launchd Scanner - Discover launchd services on macOS.

macOS equivalent of Linux ServiceScanner (systemd).

Discovers:
- Running launchd services (daemons and agents)
- Failed services
- Disabled services
- User vs system services
"""

from __future__ import annotations
from typing import List, Optional
import plistlib
from pathlib import Path

from ..base import BaseScanner
from ...schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class LaunchdScanner(BaseScanner):
    """
    Scanner for macOS launchd services.
    
    Equivalent to Linux ServiceScanner but for launchd.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.SERVICE
    
    def is_available(self) -> bool:
        """Check if launchctl is available."""
        return self.command_exists('launchctl')
    
    def scan(self) -> List[Discovery]:
        """Scan for launchd services."""
        discoveries = []
        
        discoveries.extend(self._scan_running_services())
        discoveries.extend(self._scan_launch_daemons())
        discoveries.extend(self._scan_launch_agents())
        
        self.logger.info(f"Found {len(discoveries)} launchd services")
        return discoveries
    
    def _scan_running_services(self) -> List[Discovery]:
        """Scan currently running services via launchctl list."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['launchctl', 'list'])
        if code != 0:
            return discoveries
        
        for line in stdout.strip().splitlines()[1:]:  # Skip header
            parts = line.split()
            if len(parts) < 3:
                continue
            
            pid = parts[0]
            status = parts[1]
            name = parts[2]
            
            # Skip Apple internal services for cleaner output
            if name.startswith('com.apple.') and not self._is_notable_apple_service(name):
                continue
            
            # Determine severity based on status
            if status != '0' and status != '-':
                severity = DiscoverySeverity.WARNING
                status_text = f"Exit code {status}"
            elif pid == '-':
                severity = DiscoverySeverity.INFO
                status_text = "Not running"
            else:
                severity = DiscoverySeverity.SUCCESS
                status_text = f"Running (PID {pid})"
            
            discovery_id = make_discovery_id(DiscoveryType.SERVICE, f"launchd-{name}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SERVICE,
                name=name,
                title=f"launchd: {name}",
                description=f"Service {name} - {status_text}",
                severity=severity,
                details={
                    'pid': pid,
                    'exit_status': status,
                    'status_text': status_text,
                    'type': 'launchd',
                },
                actions=[
                    DiscoveryAction(
                        id=f"status-{name}",
                        label="Check Status",
                        command=f"launchctl list {name}",
                        dry_run=True,
                    ),
                ],
                tags=['service', 'launchd', 'macos'],
            ))
        
        return discoveries
    
    def _scan_launch_daemons(self) -> List[Discovery]:
        """Scan /Library/LaunchDaemons for installed daemons."""
        discoveries = []
        daemon_dir = Path('/Library/LaunchDaemons')
        
        if not daemon_dir.exists():
            return discoveries
        
        for plist_path in daemon_dir.glob('*.plist'):
            discovery = self._parse_plist(plist_path, 'daemon')
            if discovery:
                discoveries.append(discovery)
        
        return discoveries
    
    def _scan_launch_agents(self) -> List[Discovery]:
        """Scan LaunchAgents directories."""
        discoveries = []
        
        agent_dirs = [
            Path('/Library/LaunchAgents'),
            Path.home() / 'Library' / 'LaunchAgents',
        ]
        
        for agent_dir in agent_dirs:
            if not agent_dir.exists():
                continue
            
            for plist_path in agent_dir.glob('*.plist'):
                discovery = self._parse_plist(plist_path, 'agent')
                if discovery:
                    discoveries.append(discovery)
        
        return discoveries
    
    def _parse_plist(self, plist_path: Path, service_type: str) -> Optional[Discovery]:
        """Parse a launchd plist file."""
        try:
            with open(plist_path, 'rb') as f:
                plist = plistlib.load(f)
            
            label = plist.get('Label', plist_path.stem)
            
            # Skip Apple services
            if label.startswith('com.apple.'):
                return None
            
            program = plist.get('Program') or plist.get('ProgramArguments', [None])[0]
            run_at_load = plist.get('RunAtLoad', False)
            keep_alive = plist.get('KeepAlive', False)
            disabled = plist.get('Disabled', False)
            
            if disabled:
                severity = DiscoverySeverity.INFO
                status = "Disabled"
            elif keep_alive:
                severity = DiscoverySeverity.SUCCESS
                status = "Keep-alive enabled"
            elif run_at_load:
                severity = DiscoverySeverity.SUCCESS
                status = "Runs at load"
            else:
                severity = DiscoverySeverity.INFO
                status = "Manual start"
            
            discovery_id = make_discovery_id(DiscoveryType.SERVICE, f"plist-{label}")
            
            return Discovery(
                id=discovery_id,
                type=DiscoveryType.SERVICE,
                name=label,
                title=f"LaunchDaemon: {label}" if service_type == 'daemon' else f"LaunchAgent: {label}",
                description=f"{service_type.title()} '{label}' - {status}",
                severity=severity,
                details={
                    'plist_path': str(plist_path),
                    'program': program,
                    'run_at_load': run_at_load,
                    'keep_alive': keep_alive,
                    'disabled': disabled,
                    'type': service_type,
                },
                actions=[
                    DiscoveryAction(
                        id=f"load-{label}",
                        label="Load Service",
                        command=f"launchctl load {plist_path}",
                        dry_run=True,
                        requires_approval=True,
                    ),
                    DiscoveryAction(
                        id=f"unload-{label}",
                        label="Unload Service",
                        command=f"launchctl unload {plist_path}",
                        dry_run=True,
                        requires_approval=True,
                    ),
                ],
                tags=['service', 'launchd', 'macos', service_type],
            )
        
        except Exception as e:
            self.logger.debug(f"Failed to parse plist {plist_path}: {e}")
            return None
    
    def _is_notable_apple_service(self, name: str) -> bool:
        """Check if an Apple service is notable enough to show."""
        notable = [
            'com.apple.sshd',
            'com.apple.httpd',
            'com.apple.smbd',
            'com.apple.screensharing',
            'com.apple.RemoteDesktop',
        ]
        return name in notable
