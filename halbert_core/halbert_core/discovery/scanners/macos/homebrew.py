"""
Homebrew Scanner - Discover Homebrew packages on macOS.

macOS equivalent of Linux PackageScanner.

Discovers:
- Installed formulas and casks
- Outdated packages
- Orphaned packages (not dependencies)
- Homebrew health status
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


class HomebrewScanner(BaseScanner):
    """
    Scanner for Homebrew package management on macOS.
    
    Equivalent to Linux PackageScanner.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.PACKAGE
    
    def is_available(self) -> bool:
        """Check if Homebrew is installed."""
        return self.command_exists('brew')
    
    def scan(self) -> List[Discovery]:
        """Scan Homebrew packages."""
        discoveries = []
        
        if not self.is_available():
            discoveries.append(self._homebrew_not_installed())
            return discoveries
        
        discoveries.extend(self._scan_outdated())
        discoveries.extend(self._scan_health())
        discoveries.extend(self._scan_casks())
        
        self.logger.info(f"Found {len(discoveries)} Homebrew discoveries")
        return discoveries
    
    def _homebrew_not_installed(self) -> Discovery:
        """Create discovery for missing Homebrew."""
        discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "homebrew-missing")
        
        return Discovery(
            id=discovery_id,
            type=DiscoveryType.PACKAGE,
            name="homebrew-missing",
            title="Homebrew Not Installed",
            description="Homebrew package manager is not installed on this system",
            severity=DiscoverySeverity.INFO,
            details={
                'install_url': 'https://brew.sh',
            },
            actions=[
                DiscoveryAction(
                    id="install-homebrew",
                    label="Install Homebrew",
                    command='/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
                    dry_run=True,
                    requires_approval=True,
                ),
            ],
            tags=['package', 'homebrew', 'macos', 'missing'],
        )
    
    def _scan_outdated(self) -> List[Discovery]:
        """Scan for outdated packages."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['brew', 'outdated', '--json'])
        if code != 0:
            return discoveries
        
        try:
            outdated = json.loads(stdout) if stdout.strip() else []
        except json.JSONDecodeError:
            return discoveries
        
        if not outdated:
            return discoveries
        
        # Create a summary discovery
        discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "brew-outdated-summary")
        
        package_list = [pkg.get('name', pkg) if isinstance(pkg, dict) else pkg for pkg in outdated[:10]]
        more_count = len(outdated) - 10 if len(outdated) > 10 else 0
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.PACKAGE,
            name="outdated-packages",
            title=f"{len(outdated)} Outdated Homebrew Packages",
            description=f"Packages needing update: {', '.join(package_list)}" + 
                       (f" (+{more_count} more)" if more_count else ""),
            severity=DiscoverySeverity.WARNING if len(outdated) > 10 else DiscoverySeverity.INFO,
            details={
                'count': len(outdated),
                'packages': [pkg.get('name', pkg) if isinstance(pkg, dict) else pkg for pkg in outdated],
            },
            actions=[
                DiscoveryAction(
                    id="upgrade-all",
                    label="Upgrade All",
                    command="brew upgrade",
                    dry_run=True,
                    requires_approval=True,
                ),
                DiscoveryAction(
                    id="list-outdated",
                    label="List Outdated",
                    command="brew outdated",
                    dry_run=True,
                ),
            ],
            tags=['package', 'homebrew', 'macos', 'outdated'],
        ))
        
        return discoveries
    
    def _scan_health(self) -> List[Discovery]:
        """Check Homebrew health."""
        discoveries = []
        
        code, stdout, stderr = self.run_command(['brew', 'doctor'], timeout=60)
        
        if code == 0:
            severity = DiscoverySeverity.SUCCESS
            title = "Homebrew Healthy"
            description = "No issues detected with Homebrew installation"
        else:
            severity = DiscoverySeverity.WARNING
            title = "Homebrew Issues Detected"
            # Extract first line of issues
            issues = stderr.strip().split('\n')[:3] if stderr else stdout.strip().split('\n')[:3]
            description = '; '.join(issues)
        
        discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "brew-health")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.PACKAGE,
            name="homebrew-health",
            title=title,
            description=description,
            severity=severity,
            details={
                'doctor_output': stdout[:1000] if stdout else None,
                'exit_code': code,
            },
            actions=[
                DiscoveryAction(
                    id="brew-doctor",
                    label="Run Diagnostics",
                    command="brew doctor",
                    dry_run=True,
                ),
                DiscoveryAction(
                    id="brew-cleanup",
                    label="Cleanup",
                    command="brew cleanup",
                    dry_run=True,
                    requires_approval=True,
                ),
            ],
            tags=['package', 'homebrew', 'macos', 'health'],
        ))
        
        return discoveries
    
    def _scan_casks(self) -> List[Discovery]:
        """Scan for outdated casks (GUI apps)."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['brew', 'outdated', '--cask', '--greedy'])
        if code != 0 or not stdout.strip():
            return discoveries
        
        outdated_casks = stdout.strip().splitlines()
        
        if not outdated_casks:
            return discoveries
        
        discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "brew-casks-outdated")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.PACKAGE,
            name="outdated-casks",
            title=f"{len(outdated_casks)} Outdated Cask Apps",
            description=f"GUI apps needing update: {', '.join(outdated_casks[:5])}" +
                       (f" (+{len(outdated_casks)-5} more)" if len(outdated_casks) > 5 else ""),
            severity=DiscoverySeverity.INFO,
            details={
                'count': len(outdated_casks),
                'casks': outdated_casks,
            },
            actions=[
                DiscoveryAction(
                    id="upgrade-casks",
                    label="Upgrade Casks",
                    command="brew upgrade --cask",
                    dry_run=True,
                    requires_approval=True,
                ),
            ],
            tags=['package', 'homebrew', 'macos', 'cask', 'outdated'],
        ))
        
        return discoveries
