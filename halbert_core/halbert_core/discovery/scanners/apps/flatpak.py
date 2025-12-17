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
        """Scan for Flatpak apps."""
        discoveries = []
        
        if not self.is_available():
            return discoveries
        
        discoveries.extend(self._scan_installed_apps())
        discoveries.extend(self._scan_updates())
        discoveries.extend(self._scan_remotes())
        
        self.logger.info(f"Found {len(discoveries)} Flatpak discoveries")
        return discoveries
    
    def _scan_installed_apps(self) -> List[Discovery]:
        """Scan installed Flatpak applications."""
        discoveries = []
        
        # Get installed apps with details
        code, stdout, _ = self.run_command([
            'flatpak', 'list', '--app', '--columns=application,name,version,origin,installation'
        ])
        
        if code != 0:
            return discoveries
        
        app_count = 0
        apps_info = []
        
        for line in stdout.strip().splitlines():
            parts = line.split('\t')
            if len(parts) >= 4:
                app_id = parts[0]
                name = parts[1] if len(parts) > 1 else app_id
                version = parts[2] if len(parts) > 2 else 'unknown'
                origin = parts[3] if len(parts) > 3 else 'unknown'
                installation = parts[4] if len(parts) > 4 else 'system'
                
                apps_info.append({
                    'app_id': app_id,
                    'name': name,
                    'version': version,
                    'origin': origin,
                    'installation': installation,
                })
                app_count += 1
        
        # Create summary discovery
        if app_count > 0:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "flatpak-apps-summary")
            
            # Show first few apps
            app_names = [a['name'] for a in apps_info[:5]]
            more = f" (+{app_count - 5} more)" if app_count > 5 else ""
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="flatpak-apps",
                title=f"Flatpak: {app_count} Apps Installed",
                description=f"Installed: {', '.join(app_names)}{more}",
                severity=DiscoverySeverity.INFO,
                data={
                    'count': app_count,
                    'apps': apps_info,
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
    
    def _scan_updates(self) -> List[Discovery]:
        """Check for available Flatpak updates."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['flatpak', 'remote-ls', '--updates', '--columns=application,name'])
        
        if code != 0:
            return discoveries
        
        updates = []
        for line in stdout.strip().splitlines():
            if line:
                parts = line.split('\t')
                app_id = parts[0]
                name = parts[1] if len(parts) > 1 else app_id
                updates.append({'app_id': app_id, 'name': name})
        
        if updates:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "flatpak-updates")
            
            update_names = [u['name'] for u in updates[:5]]
            more = f" (+{len(updates) - 5} more)" if len(updates) > 5 else ""
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="flatpak-updates",
                title=f"Flatpak: {len(updates)} Updates Available",
                description=f"Updates: {', '.join(update_names)}{more}",
                severity=DiscoverySeverity.WARNING if len(updates) > 5 else DiscoverySeverity.INFO,
                data={
                    'count': len(updates),
                    'updates': updates,
                },
                actions=[
                    DiscoveryAction(
                        id="show-updates",
                        label="Show Updates",
                        command="flatpak remote-ls --updates",
                    ),
                    DiscoveryAction(
                        id="update-all",
                        label="Update All",
                        command="flatpak update -y",
                        requires_approval=True,
                    ),
                ],
            ))
        
        return discoveries
    
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
