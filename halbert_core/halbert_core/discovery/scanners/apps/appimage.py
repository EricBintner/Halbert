"""
AppImage Scanner - Discover AppImage files.

Phase 26: Universal App Management

Discovers:
- AppImage files in common locations
- Running AppImages
- AppImage integration status
"""

from __future__ import annotations
from typing import List, Set
from pathlib import Path
import os
import stat

from ..base import BaseScanner
from ...schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class AppImageScanner(BaseScanner):
    """
    Scanner for AppImage applications.
    
    AppImages are portable, single-file Linux applications.
    No central registry - we scan common locations.
    """
    
    # Common AppImage locations
    SEARCH_PATHS = [
        Path.home() / 'Applications',
        Path.home() / '.local' / 'bin',
        Path.home() / 'Downloads',
        Path.home() / 'Desktop',
        Path('/opt'),
        Path('/usr/local/bin'),
    ]
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.PACKAGE
    
    def is_available(self) -> bool:
        """AppImage discovery is always available on Linux."""
        import platform
        return platform.system() == 'Linux'
    
    def scan(self) -> List[Discovery]:
        """Scan for AppImage files."""
        discoveries = []
        
        if not self.is_available():
            return discoveries
        
        appimages = self._find_appimages()
        
        if appimages:
            discoveries.append(self._create_summary(appimages))
            discoveries.extend(self._check_integration())
        
        self.logger.info(f"Found {len(discoveries)} AppImage discoveries")
        return discoveries
    
    def _find_appimages(self) -> List[dict]:
        """Find AppImage files in common locations."""
        appimages = []
        seen_paths: Set[str] = set()
        
        for search_path in self.SEARCH_PATHS:
            if not search_path.exists():
                continue
            
            try:
                # Search for .AppImage files
                for appimage in search_path.glob('**/*.AppImage'):
                    if str(appimage) in seen_paths:
                        continue
                    seen_paths.add(str(appimage))
                    
                    info = self._get_appimage_info(appimage)
                    if info:
                        appimages.append(info)
                
                # Also check for files with appimage in name (case insensitive)
                for appimage in search_path.glob('**/*.[aA][pP][pP][iI][mM][aA][gG][eE]'):
                    if str(appimage) in seen_paths:
                        continue
                    seen_paths.add(str(appimage))
                    
                    info = self._get_appimage_info(appimage)
                    if info:
                        appimages.append(info)
                        
            except PermissionError:
                continue
        
        return appimages
    
    def _get_appimage_info(self, path: Path) -> dict | None:
        """Get information about an AppImage file."""
        try:
            stat_info = path.stat()
            
            # Check if executable
            is_executable = bool(stat_info.st_mode & stat.S_IXUSR)
            
            # Get file size
            size_mb = stat_info.st_size / (1024 * 1024)
            
            # Extract name from filename
            name = path.stem
            # Clean up common suffixes
            for suffix in ['.AppImage', '-x86_64', '-x86', '.x86_64', '-linux']:
                name = name.replace(suffix, '')
            
            return {
                'name': name,
                'path': str(path),
                'size_mb': round(size_mb, 1),
                'executable': is_executable,
                'location': str(path.parent),
            }
        except Exception:
            return None
    
    def _create_summary(self, appimages: List[dict]) -> Discovery:
        """Create summary discovery for found AppImages."""
        discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "appimage-summary")
        
        names = [a['name'] for a in appimages[:5]]
        more = f" (+{len(appimages) - 5} more)" if len(appimages) > 5 else ""
        
        # Check for non-executable AppImages
        non_exec = [a for a in appimages if not a['executable']]
        
        if non_exec:
            severity = DiscoverySeverity.WARNING
            desc_suffix = f" ({len(non_exec)} not executable)"
        else:
            severity = DiscoverySeverity.INFO
            desc_suffix = ""
        
        total_size = sum(a['size_mb'] for a in appimages)
        
        return Discovery(
            id=discovery_id,
            type=DiscoveryType.PACKAGE,
            name="appimage-apps",
            title=f"AppImage: {len(appimages)} Apps Found",
            description=f"Found: {', '.join(names)}{more}{desc_suffix}",
            severity=severity,
            details={
                'count': len(appimages),
                'total_size_mb': round(total_size, 1),
                'non_executable': len(non_exec),
                'appimages': appimages,
            },
            actions=[
                DiscoveryAction(
                    id="list-appimages",
                    label="List Locations",
                    command="find ~ -name '*.AppImage' 2>/dev/null",
                    dry_run=True,
                ),
            ] + ([
                DiscoveryAction(
                    id="fix-permissions",
                    label="Fix Permissions",
                    command=f"chmod +x {' '.join(a['path'] for a in non_exec[:5])}",
                    dry_run=True,
                    requires_approval=True,
                )
            ] if non_exec else []),
            tags=['package', 'appimage', 'apps', 'linux'],
        )
    
    def _check_integration(self) -> List[Discovery]:
        """Check for AppImage integration tools."""
        discoveries = []
        
        # Check for AppImageLauncher
        has_launcher = self.command_exists('AppImageLauncher') or \
                      self.command_exists('appimagelauncherd')
        
        # Check for appimagetool
        has_tool = self.command_exists('appimagetool')
        
        if not has_launcher:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "appimage-no-launcher")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="appimage-integration",
                title="AppImageLauncher Not Installed",
                description="AppImageLauncher provides desktop integration for AppImages",
                severity=DiscoverySeverity.INFO,
                details={
                    'suggestion': 'Install AppImageLauncher for better integration',
                    'benefits': [
                        'Automatic desktop menu integration',
                        'AppImage updates support',
                        'Centralized management',
                    ],
                },
                actions=[
                    DiscoveryAction(
                        id="learn-launcher",
                        label="Learn More",
                        command="echo 'Visit: https://github.com/TheAssassin/AppImageLauncher'",
                        dry_run=True,
                    ),
                ],
                tags=['package', 'appimage', 'integration', 'linux'],
            ))
        
        return discoveries
