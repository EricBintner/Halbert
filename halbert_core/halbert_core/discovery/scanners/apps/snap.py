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
        
        Snap icons can be in many locations:
        - /snap/<name>/current/meta/gui/icon.png (standard)
        - /snap/<name>/current/meta/gui/<name>.png (app-specific naming)
        - /snap/<name>/current/<name>.png (root level)
        - /snap/<name>/current/usr/share/icons/hicolor/*/apps/<name>.png
        """
        from pathlib import Path
        import glob
        
        snap_base = Path(f'/snap/{snap_name}/current')
        
        # Check standard icon.png/svg first
        standard_paths = [
            snap_base / 'meta/gui/icon.png',
            snap_base / 'meta/gui/icon.svg',
        ]
        for p in standard_paths:
            if p.exists():
                return str(p)
        
        # Check app-specific names in meta/gui (e.g., vscode.png, arduino.png)
        gui_dir = snap_base / 'meta/gui'
        if gui_dir.exists():
            for ext in ['.png', '.svg']:
                # Try exact snap name
                specific = gui_dir / f'{snap_name}{ext}'
                if specific.exists():
                    return str(specific)
                # Try any PNG/SVG in gui folder (except desktop files)
                for icon_file in gui_dir.glob(f'*{ext}'):
                    if icon_file.is_file():
                        return str(icon_file)
        
        # Check root level (e.g., /snap/0ad/current/0ad.png)
        for ext in ['.png', '.svg']:
            root_icon = snap_base / f'{snap_name}{ext}'
            if root_icon.exists():
                return str(root_icon)
        
        # Check hicolor icon theme inside snap
        hicolor_base = snap_base / 'usr/share/icons/hicolor'
        if hicolor_base.exists():
            for size in ['256x256', '512x512', '128x128', '64x64', '48x48', 'scalable']:
                size_dir = hicolor_base / size / 'apps'
                if size_dir.exists():
                    for ext in ['.png', '.svg']:
                        icon = size_dir / f'{snap_name}{ext}'
                        if icon.exists():
                            return str(icon)
        
        # Check snapd desktop exports
        desktop_exports = [
            Path(f'/var/lib/snapd/desktop/icons/hicolor/256x256/apps/snap.{snap_name}.png'),
            Path(f'/var/lib/snapd/desktop/icons/hicolor/512x512/apps/snap.{snap_name}.png'),
        ]
        for p in desktop_exports:
            if p.exists():
                return str(p)
        
        return None
