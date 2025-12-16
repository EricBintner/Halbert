"""
Mac App Store Scanner - Discover App Store applications.

Phase 26: Universal App Management

Discovers:
- Installed App Store apps (via mas CLI)
- Available updates
- App Store account status

Note: Requires 'mas' CLI tool (brew install mas)
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


class MacAppStoreScanner(BaseScanner):
    """
    Scanner for Mac App Store applications.
    
    Uses the 'mas' CLI tool to interact with the App Store.
    This scanner provides read-only information - we don't manage
    App Store apps, just show what's installed.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.PACKAGE
    
    def is_available(self) -> bool:
        """Check if mas CLI is installed and we're on macOS."""
        import platform
        if platform.system() != 'Darwin':
            return False
        return self.command_exists('mas')
    
    def scan(self) -> List[Discovery]:
        """Scan Mac App Store apps."""
        discoveries = []
        
        if not self.is_available():
            # Suggest installing mas if on macOS
            import platform
            if platform.system() == 'Darwin':
                discoveries.append(self._suggest_mas_install())
            return discoveries
        
        discoveries.extend(self._scan_installed())
        discoveries.extend(self._scan_updates())
        discoveries.extend(self._scan_account())
        
        self.logger.info(f"Found {len(discoveries)} Mac App Store discoveries")
        return discoveries
    
    def _suggest_mas_install(self) -> Discovery:
        """Suggest installing mas CLI."""
        discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "mas-not-installed")
        
        return Discovery(
            id=discovery_id,
            type=DiscoveryType.PACKAGE,
            name="mas-not-installed",
            title="Mac App Store CLI Not Installed",
            description="Install 'mas' to see App Store apps in Halbert",
            severity=DiscoverySeverity.INFO,
            details={
                'suggestion': "mas allows viewing App Store apps from terminal",
            },
            actions=[
                DiscoveryAction(
                    id="install-mas",
                    label="Install mas",
                    command="brew install mas",
                    dry_run=True,
                    requires_approval=True,
                ),
            ],
            tags=['package', 'appstore', 'mas', 'macos'],
        )
    
    def _scan_installed(self) -> List[Discovery]:
        """Scan installed App Store apps."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['mas', 'list'])
        
        if code != 0:
            return discoveries
        
        apps = []
        for line in stdout.strip().splitlines():
            if not line.strip():
                continue
            # Format: "123456789 App Name (1.2.3)"
            parts = line.split(None, 1)
            if len(parts) >= 2:
                app_id = parts[0]
                rest = parts[1]
                # Extract name and version
                if '(' in rest and rest.endswith(')'):
                    name = rest[:rest.rfind('(')].strip()
                    version = rest[rest.rfind('(')+1:-1]
                else:
                    name = rest
                    version = 'unknown'
                
                apps.append({
                    'id': app_id,
                    'name': name,
                    'version': version,
                })
        
        if apps:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "appstore-apps")
            
            app_names = [a['name'] for a in apps[:5]]
            more = f" (+{len(apps) - 5} more)" if len(apps) > 5 else ""
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="appstore-apps",
                title=f"App Store: {len(apps)} Apps",
                description=f"Installed: {', '.join(app_names)}{more}",
                severity=DiscoverySeverity.INFO,
                details={
                    'count': len(apps),
                    'apps': apps,
                    'note': "App Store apps are managed by macOS, shown here for reference",
                },
                actions=[
                    DiscoveryAction(
                        id="list-apps",
                        label="List All",
                        command="mas list",
                        dry_run=True,
                    ),
                ],
                tags=['package', 'appstore', 'macos', 'apps'],
            ))
        
        return discoveries
    
    def _scan_updates(self) -> List[Discovery]:
        """Check for App Store updates."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['mas', 'outdated'])
        
        if code != 0:
            return discoveries
        
        updates = []
        for line in stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split(None, 1)
            if len(parts) >= 2:
                updates.append({
                    'id': parts[0],
                    'name': parts[1].split('(')[0].strip() if '(' in parts[1] else parts[1],
                })
        
        if updates:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "appstore-updates")
            
            update_names = [u['name'] for u in updates[:5]]
            more = f" (+{len(updates) - 5} more)" if len(updates) > 5 else ""
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="appstore-updates",
                title=f"App Store: {len(updates)} Updates",
                description=f"Updates: {', '.join(update_names)}{more}",
                severity=DiscoverySeverity.INFO,
                details={
                    'count': len(updates),
                    'updates': updates,
                    'note': "Updates can be installed via App Store app or 'mas upgrade'",
                },
                actions=[
                    DiscoveryAction(
                        id="show-updates",
                        label="Show Updates",
                        command="mas outdated",
                        dry_run=True,
                    ),
                    DiscoveryAction(
                        id="open-appstore",
                        label="Open App Store",
                        command="open -a 'App Store'",
                        dry_run=True,
                    ),
                ],
                tags=['package', 'appstore', 'updates', 'macos'],
            ))
        
        return discoveries
    
    def _scan_account(self) -> List[Discovery]:
        """Check App Store account status."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['mas', 'account'])
        
        if code == 0 and stdout.strip():
            account = stdout.strip()
            
            # Don't create a discovery for normal signed-in state
            # Only notable if signed out
            if 'Not signed in' in account:
                discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "appstore-signed-out")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.PACKAGE,
                    name="appstore-signed-out",
                    title="App Store: Not Signed In",
                    description="Sign in to App Store to manage purchases",
                    severity=DiscoverySeverity.INFO,
                    details={},
                    actions=[
                        DiscoveryAction(
                            id="open-appstore",
                            label="Open App Store",
                            command="open -a 'App Store'",
                            dry_run=True,
                        ),
                    ],
                    tags=['package', 'appstore', 'account', 'macos'],
                ))
        
        return discoveries
