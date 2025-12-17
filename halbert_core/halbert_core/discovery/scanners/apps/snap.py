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
        """Scan for Snap packages with unified app list and update status."""
        discoveries = []
        
        if not self.is_available():
            return discoveries
        
        # Get updates first so we can merge status into snaps
        snap_updates = self._get_updates()
        
        # Scan installed snaps with update status merged in
        discoveries.extend(self._scan_installed(snap_updates))
        discoveries.extend(self._scan_services())
        
        self.logger.info(f"Found {len(discoveries)} Snap discoveries")
        return discoveries
    
    def _get_updates(self) -> set[str]:
        """Get set of snap names that have updates available."""
        updates = set()
        
        # snap refresh --list shows pending updates
        code, stdout, _ = self.run_command(['snap', 'refresh', '--list'])
        
        if code != 0:
            return updates
        
        lines = stdout.strip().splitlines()
        for line in lines:
            if line.startswith('Name') or not line.strip():
                continue
            parts = line.split()
            if parts:
                updates.add(parts[0])
        
        return updates
    
    def _scan_installed(self, snap_updates: set[str]) -> List[Discovery]:
        """Scan installed Snap packages with update status merged in."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['snap', 'list'])
        
        if code != 0:
            return discoveries
        
        snaps = []
        update_count = 0
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
                
                # Find icon path for the snap
                icon_path = self._find_snap_icon(name)
                
                # Check if this snap has an update available
                has_update = name in snap_updates
                if has_update:
                    update_count += 1
                
                snaps.append({
                    'name': name,
                    'version': version,
                    'revision': rev,
                    'tracking': tracking,
                    'publisher': publisher,
                    'notes': notes,
                    'classic': 'classic' in notes,
                    'icon': icon_path,
                    'has_update': has_update,
                    'status': 'update_available' if has_update else 'current',
                })
        
        if snaps:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "snap-apps")
            
            # Count classic vs confined
            classic_count = sum(1 for s in snaps if s['classic'])
            
            # Build description
            if update_count > 0:
                desc = f"{len(snaps)} snaps installed, {update_count} update{'s' if update_count != 1 else ''} available"
            else:
                desc = f"{len(snaps)} snaps installed, all up to date"
            if classic_count:
                desc += f" ({classic_count} classic)"
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="snap-apps",
                title=f"Snap Apps",
                description=desc,
                severity=DiscoverySeverity.WARNING if update_count > 0 else DiscoverySeverity.SUCCESS,
                data={
                    'count': len(snaps),
                    'update_count': update_count,
                    'classic_count': classic_count,
                    'snaps': snaps,
                    'source': 'snap',
                },
                actions=[
                    DiscoveryAction(
                        id="list-snaps",
                        label="List All Snaps",
                        command="snap list",
                    ),
                    DiscoveryAction(
                        id="refresh-snaps",
                        label="Update All",
                        command="sudo snap refresh",
                        requires_approval=True,
                    ),
                ],
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
                data={
                    'total': len(services),
                    'running': running,
                    'services': services,
                },
                actions=[
                    DiscoveryAction(
                        id="list-services",
                        label="List Services",
                        command="snap services",
                    ),
                ],
            ))
        
        return discoveries
    
    def _find_snap_icon(self, snap_name: str) -> str | None:
        """
        Find the icon path for a Snap package.
        
        Snap icons are typically at:
        - /snap/<name>/current/meta/gui/icon.png (or .svg)
        - /var/lib/snapd/snap/<name>/current/meta/gui/icon.png
        """
        from pathlib import Path
        
        # Common icon locations for snaps
        possible_paths = [
            Path(f'/snap/{snap_name}/current/meta/gui/icon.png'),
            Path(f'/snap/{snap_name}/current/meta/gui/icon.svg'),
            Path(f'/var/lib/snapd/snap/{snap_name}/current/meta/gui/icon.png'),
            Path(f'/var/lib/snapd/snap/{snap_name}/current/meta/gui/icon.svg'),
            # Also check desktop file exports
            Path(f'/var/lib/snapd/desktop/icons/hicolor/256x256/apps/snap.{snap_name}.png'),
            Path(f'/var/lib/snapd/desktop/icons/hicolor/512x512/apps/snap.{snap_name}.png'),
        ]
        
        for icon_path in possible_paths:
            if icon_path.exists():
                return str(icon_path)
        
        return None
