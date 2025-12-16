"""
Snap Scanner - Discover Snap packages.

Phase 26: Universal App Management

Discovers:
- Installed Snap packages
- Snap services
- Available updates
- Confinement modes
"""

from __future__ import annotations
from typing import List
import json

from ..base import BaseScanner
from ...schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class SnapScanner(BaseScanner):
    """
    Scanner for Snap packages.
    
    Snap is Canonical's universal package format with automatic updates.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.PACKAGE
    
    def is_available(self) -> bool:
        """Check if Snap is installed and running."""
        if not self.command_exists('snap'):
            return False
        
        # Check if snapd is running
        code, _, _ = self.run_command(['systemctl', 'is-active', 'snapd'], timeout=5)
        return code == 0
    
    def scan(self) -> List[Discovery]:
        """Scan for Snap packages."""
        discoveries = []
        
        if not self.is_available():
            return discoveries
        
        discoveries.extend(self._scan_installed())
        discoveries.extend(self._scan_updates())
        discoveries.extend(self._scan_services())
        
        self.logger.info(f"Found {len(discoveries)} Snap discoveries")
        return discoveries
    
    def _scan_installed(self) -> List[Discovery]:
        """Scan installed Snap packages."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['snap', 'list'])
        
        if code != 0:
            return discoveries
        
        snaps = []
        lines = stdout.strip().splitlines()
        
        # Skip header
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 4:
                name = parts[0]
                version = parts[1]
                rev = parts[2]
                tracking = parts[3] if len(parts) > 3 else ''
                publisher = parts[4] if len(parts) > 4 else ''
                notes = parts[5] if len(parts) > 5 else ''
                
                # Skip core snaps for cleaner output
                if name in ['core', 'core18', 'core20', 'core22', 'snapd', 'bare']:
                    continue
                
                snaps.append({
                    'name': name,
                    'version': version,
                    'revision': rev,
                    'tracking': tracking,
                    'publisher': publisher,
                    'notes': notes,
                    'classic': 'classic' in notes,
                })
        
        if snaps:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "snap-installed")
            
            snap_names = [s['name'] for s in snaps[:5]]
            more = f" (+{len(snaps) - 5} more)" if len(snaps) > 5 else ""
            
            # Count classic vs confined
            classic_count = sum(1 for s in snaps if s['classic'])
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="snap-apps",
                title=f"Snap: {len(snaps)} Packages Installed",
                description=f"Installed: {', '.join(snap_names)}{more}" + 
                           (f" ({classic_count} classic)" if classic_count else ""),
                severity=DiscoverySeverity.INFO,
                details={
                    'count': len(snaps),
                    'classic_count': classic_count,
                    'snaps': snaps,
                },
                actions=[
                    DiscoveryAction(
                        id="list-snaps",
                        label="List All Snaps",
                        command="snap list",
                        dry_run=True,
                    ),
                    DiscoveryAction(
                        id="refresh-snaps",
                        label="Update All",
                        command="sudo snap refresh",
                        dry_run=True,
                        requires_approval=True,
                    ),
                ],
                tags=['package', 'snap', 'apps', 'linux'],
            ))
        
        return discoveries
    
    def _scan_updates(self) -> List[Discovery]:
        """Check for available Snap updates."""
        discoveries = []
        
        # Note: snap refresh --list shows pending updates
        code, stdout, _ = self.run_command(['snap', 'refresh', '--list'])
        
        if code != 0:
            return discoveries
        
        updates = []
        lines = stdout.strip().splitlines()
        
        # Skip header if present
        for line in lines:
            if line.startswith('Name') or not line.strip():
                continue
            parts = line.split()
            if parts:
                updates.append({
                    'name': parts[0],
                    'version': parts[1] if len(parts) > 1 else '',
                })
        
        if updates:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "snap-updates")
            
            update_names = [u['name'] for u in updates[:5]]
            more = f" (+{len(updates) - 5} more)" if len(updates) > 5 else ""
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="snap-updates",
                title=f"Snap: {len(updates)} Updates Pending",
                description=f"Updates: {', '.join(update_names)}{more}",
                severity=DiscoverySeverity.INFO,
                details={
                    'count': len(updates),
                    'updates': updates,
                },
                actions=[
                    DiscoveryAction(
                        id="show-updates",
                        label="Show Updates",
                        command="snap refresh --list",
                        dry_run=True,
                    ),
                    DiscoveryAction(
                        id="refresh-all",
                        label="Update All",
                        command="sudo snap refresh",
                        dry_run=True,
                        requires_approval=True,
                    ),
                ],
                tags=['package', 'snap', 'updates', 'linux'],
            ))
        
        return discoveries
    
    def _scan_services(self) -> List[Discovery]:
        """Scan Snap services."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['snap', 'services'])
        
        if code != 0 or not stdout.strip():
            return discoveries
        
        services = []
        lines = stdout.strip().splitlines()
        
        # Skip header
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 3:
                service = parts[0]
                startup = parts[1]
                current = parts[2]
                
                services.append({
                    'name': service,
                    'startup': startup,
                    'current': current,
                    'running': current == 'active',
                })
        
        if services:
            running = sum(1 for s in services if s['running'])
            
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "snap-services")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="snap-services",
                title=f"Snap Services: {running}/{len(services)} Running",
                description=f"{len(services)} snap services configured",
                severity=DiscoverySeverity.INFO,
                details={
                    'total': len(services),
                    'running': running,
                    'services': services,
                },
                actions=[
                    DiscoveryAction(
                        id="list-services",
                        label="List Services",
                        command="snap services",
                        dry_run=True,
                    ),
                ],
                tags=['package', 'snap', 'services', 'linux'],
            ))
        
        return discoveries
