# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Flatpak Scanner - Discover Flatpak applications.

Phase 26: Universal App Management

Discovers:
- Installed Flatpak applications
- Available updates
- Flatpak remotes (Flathub, etc.)
- App permissions and overrides
"""

from __future__ import annotations
from typing import List, Optional
import json

from ..base import BaseScanner
from ...schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class FlatpakScanner(BaseScanner):
    """
    Scanner for Flatpak applications.
    
    Flatpak provides sandboxed, distribution-agnostic apps.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.PACKAGE
    
    def is_available(self) -> bool:
        """Check if Flatpak is installed."""
        return self.command_exists('flatpak')
    
    def scan(self) -> List[Discovery]:
        """Scan for Flatpak apps with unified app list and update status."""
        discoveries = []
        
        if not self.is_available():
            return discoveries
        
        # Get updates first so we can merge status into apps
        app_updates, runtime_updates = self._get_updates()
        
        # Scan installed apps with update status merged in
        discoveries.extend(self._scan_installed_apps(app_updates))
        
        # Add runtime updates as separate discovery (collapsed in UI)
        if runtime_updates:
            discoveries.extend(self._create_runtime_updates_discovery(runtime_updates))
        
        discoveries.extend(self._scan_remotes())
        
        self.logger.info(f"Found {len(discoveries)} Flatpak discoveries")
        return discoveries
    
    def _get_updates(self) -> tuple[dict[str, dict], list[dict]]:
        """
        Get available updates, separated into app updates and runtime updates.
        
        Returns:
            Tuple of (app_updates dict keyed by app_id, runtime_updates list)
        """
        app_updates = {}
        runtime_updates = []
        
        # Get updates with ref type to distinguish apps from runtimes
        code, stdout, _ = self.run_command([
            'flatpak', 'remote-ls', '--updates', '--columns=application,name,ref'
        ])
        
        if code != 0:
            return app_updates, runtime_updates
        
        for line in stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split('\t')
            app_id = parts[0]
            name = parts[1] if len(parts) > 1 else app_id
            ref = parts[2] if len(parts) > 2 else ''
            
            update_info = {'app_id': app_id, 'name': name, 'ref': ref}
            
            # Check if it's an app or runtime based on ref
            if '/app/' in ref:
                app_updates[app_id] = update_info
            else:
                runtime_updates.append(update_info)
        
        return app_updates, runtime_updates
    
    def _scan_installed_apps(self, app_updates: dict[str, dict]) -> List[Discovery]:
        """Scan installed Flatpak applications with update status merged in."""
        discoveries = []
        
        # Get installed apps with details
        code, stdout, _ = self.run_command([
            'flatpak', 'list', '--app', '--columns=application,name,version,origin,installation'
        ])
        
        if code != 0:
            return discoveries
        
        apps_info = []
        update_count = 0
        
        for line in stdout.strip().splitlines():
            parts = line.split('\t')
            if len(parts) >= 4:
                app_id = parts[0]
                name = parts[1] if len(parts) > 1 else app_id
                version = parts[2] if len(parts) > 2 else 'unknown'
                origin = parts[3] if len(parts) > 3 else 'unknown'
                installation = parts[4] if len(parts) > 4 else 'system'
                
                # Find icon path for the app
                icon_path = self._find_flatpak_icon(app_id, installation)
                
                # Check if this app has an update available
                has_update = app_id in app_updates
                if has_update:
                    update_count += 1
                
                apps_info.append({
                    'app_id': app_id,
                    'name': name,
                    'version': version,
                    'origin': origin,
                    'installation': installation,
                    'icon': icon_path,
                    'has_update': has_update,
                    'status': 'update_available' if has_update else 'current',
                })
        
        # Create unified discovery with all apps
        if apps_info:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "flatpak-apps")
            
            # Build description
            if update_count > 0:
                desc = f"{len(apps_info)} apps installed, {update_count} update{'s' if update_count != 1 else ''} available"
            else:
                desc = f"{len(apps_info)} apps installed, all up to date"
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="flatpak-apps",
                title=f"Flatpak Apps",
                description=desc,
                severity=DiscoverySeverity.WARNING if update_count > 0 else DiscoverySeverity.SUCCESS,
                data={
                    'count': len(apps_info),
                    'update_count': update_count,
                    'apps': apps_info,
                    'source': 'flatpak',
                },
                actions=[
                    DiscoveryAction(
                        id="list-flatpak",
                        label="List All Apps",
                        command="flatpak list --app",
                    ),
                    DiscoveryAction(
                        id="update-flatpak",
                        label="Update All",
                        command="flatpak update -y",
                        requires_approval=True,
                    ),
                ],
            ))
        
        return discoveries
    
    def _create_runtime_updates_discovery(self, runtime_updates: list[dict]) -> List[Discovery]:
        """Create a separate discovery for runtime/extension updates."""
        discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "flatpak-runtimes")
        
        runtime_names = [r['name'] for r in runtime_updates[:3]]
        more = f" (+{len(runtime_updates) - 3} more)" if len(runtime_updates) > 3 else ""
        
        return [Discovery(
            id=discovery_id,
            type=DiscoveryType.PACKAGE,
            name="flatpak-runtimes",
            title=f"Flatpak Runtimes: {len(runtime_updates)} Updates",
            description=f"Runtime updates: {', '.join(runtime_names)}{more}",
            severity=DiscoverySeverity.INFO,
            data={
                'count': len(runtime_updates),
                'runtimes': runtime_updates,
                'source': 'flatpak',
                'is_runtime': True,
            },
            actions=[
                DiscoveryAction(
                    id="update-runtimes",
                    label="Update Runtimes",
                    command="flatpak update --runtime -y",
                    requires_approval=True,
                ),
            ],
        )]
    
    def _scan_remotes(self) -> List[Discovery]:
        """Scan Flatpak remotes (repositories)."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['flatpak', 'remotes', '--columns=name,url'])
        
        if code != 0:
            return discoveries
        
        remotes = []
        has_flathub = False
        
        for line in stdout.strip().splitlines():
            parts = line.split('\t')
            if parts:
                name = parts[0]
                url = parts[1] if len(parts) > 1 else ''
                remotes.append({'name': name, 'url': url})
                if 'flathub' in name.lower():
                    has_flathub = True
        
        if remotes:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "flatpak-remotes")
            
            remote_names = [r['name'] for r in remotes]
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="flatpak-remotes",
                title=f"Flatpak Remotes: {', '.join(remote_names)}",
                description=f"{len(remotes)} remote(s) configured" + (" (Flathub enabled)" if has_flathub else ""),
                severity=DiscoverySeverity.SUCCESS if has_flathub else DiscoverySeverity.INFO,
                data={
                    'remotes': remotes,
                    'has_flathub': has_flathub,
                },
                actions=[
                    DiscoveryAction(
                        id="list-remotes",
                        label="List Remotes",
                        command="flatpak remotes -d",
                    ),
                ],
            ))
        
        # Suggest Flathub if not configured
        if not has_flathub:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "flatpak-no-flathub")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="flatpak-no-flathub",
                title="Flathub Not Configured",
                description="Flathub is the main Flatpak repository with thousands of apps",
                severity=DiscoverySeverity.INFO,
                data={
                    'suggestion': 'Add Flathub for more apps',
                },
                actions=[
                    DiscoveryAction(
                        id="add-flathub",
                        label="Add Flathub",
                        command="flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo",
                        requires_approval=True,
                    ),
                ],
            ))
        
        return discoveries
    
    def _find_flatpak_icon(self, app_id: str, installation: str = 'system') -> Optional[str]:
        """
        Find the icon path for a Flatpak app.
        
        Icons are typically exported to:
        - System: /var/lib/flatpak/exports/share/icons/hicolor/*/apps/<app_id>.png
        - User: ~/.local/share/flatpak/exports/share/icons/hicolor/*/apps/<app_id>.png
        """
        from pathlib import Path
        
        # Determine base path based on installation type
        if installation == 'user':
            base_paths = [
                Path.home() / '.local/share/flatpak/exports/share/icons',
            ]
        else:
            base_paths = [
                Path('/var/lib/flatpak/exports/share/icons'),
            ]
        
        # Preferred icon sizes (larger first for better quality)
        sizes = ['512x512', '256x256', '128x128', '64x64', '48x48', 'scalable']
        extensions = ['.png', '.svg']
        
        for base_path in base_paths:
            for size in sizes:
                for ext in extensions:
                    # Try hicolor theme first
                    icon_path = base_path / 'hicolor' / size / 'apps' / f"{app_id}{ext}"
                    if icon_path.exists():
                        return str(icon_path)
        
        return None
