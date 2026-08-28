# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Homebrew Apps Scanner - Enhanced Homebrew discovery for Apps tab.

Phase 26: Universal App Management

Extends the existing HomebrewScanner with:
- Detailed formula and cask information
- Update checking
- Dependency tracking
- Cleanup recommendations
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


class HomebrewAppScanner(BaseScanner):
    """
    Enhanced Homebrew scanner for the Apps tab.
    
    Provides detailed information about installed formulas and casks,
    update availability, and maintenance recommendations.
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
            return discoveries
        
        discoveries.extend(self._scan_formulas())
        discoveries.extend(self._scan_casks())
        discoveries.extend(self._scan_updates())
        discoveries.extend(self._scan_health())
        discoveries.extend(self._scan_cleanup())
        
        self.logger.info(f"Found {len(discoveries)} Homebrew discoveries")
        return discoveries
    
    def _scan_formulas(self) -> List[Discovery]:
        """Scan installed Homebrew formulas (CLI tools)."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['brew', 'list', '--formula', '-1'])
        
        if code != 0:
            return discoveries
        
        formulas = [f.strip() for f in stdout.strip().splitlines() if f.strip()]
        
        if formulas:
            # Get detailed info for summary
            formula_info = []
            for formula in formulas[:10]:  # Limit for performance
                info = self._get_formula_info(formula)
                if info:
                    formula_info.append(info)
            
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "homebrew-formulas")
            
            sample = formulas[:5]
            more = f" (+{len(formulas) - 5} more)" if len(formulas) > 5 else ""
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="homebrew-formulas",
                title=f"Homebrew: {len(formulas)} Formulas",
                description=f"CLI tools: {', '.join(sample)}{more}",
                severity=DiscoverySeverity.INFO,
                data={
                    'count': len(formulas),
                    'formulas': formulas,
                    'sample_info': formula_info,
                },
                actions=[
                    DiscoveryAction(
                        id="list-formulas",
                        label="List All",
                        command="brew list --formula",
                    ),
                    DiscoveryAction(
                        id="upgrade-formulas",
                        label="Upgrade All",
                        command="brew upgrade",
                        requires_approval=True,
                    ),
                ],
            ))
        
        return discoveries
    
    def _scan_casks(self) -> List[Discovery]:
        """Scan installed Homebrew casks (GUI apps)."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['brew', 'list', '--cask', '-1'])
        
        if code != 0:
            return discoveries
        
        casks = [c.strip() for c in stdout.strip().splitlines() if c.strip()]
        
        if casks:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "homebrew-casks")
            
            sample = casks[:5]
            more = f" (+{len(casks) - 5} more)" if len(casks) > 5 else ""
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="homebrew-casks",
                title=f"Homebrew: {len(casks)} Casks",
                description=f"GUI apps: {', '.join(sample)}{more}",
                severity=DiscoverySeverity.INFO,
                data={
                    'count': len(casks),
                    'casks': casks,
                },
                actions=[
                    DiscoveryAction(
                        id="list-casks",
                        label="List All",
                        command="brew list --cask",
                    ),
                    DiscoveryAction(
                        id="upgrade-casks",
                        label="Upgrade All",
                        command="brew upgrade --cask",
                        requires_approval=True,
                    ),
                ],
            ))
        
        return discoveries
    
    def _scan_updates(self) -> List[Discovery]:
        """Check for available Homebrew updates."""
        discoveries = []
        
        # Check outdated formulas
        code, stdout, _ = self.run_command(['brew', 'outdated', '--formula'])
        
        outdated_formulas = []
        if code == 0 and stdout.strip():
            outdated_formulas = [l.strip() for l in stdout.strip().splitlines() if l.strip()]
        
        # Check outdated casks
        code, stdout, _ = self.run_command(['brew', 'outdated', '--cask'])
        
        outdated_casks = []
        if code == 0 and stdout.strip():
            outdated_casks = [l.strip() for l in stdout.strip().splitlines() if l.strip()]
        
        total_outdated = len(outdated_formulas) + len(outdated_casks)
        
        if total_outdated > 0:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "homebrew-updates")
            
            all_outdated = outdated_formulas[:3] + outdated_casks[:3]
            more = f" (+{total_outdated - len(all_outdated)} more)" if total_outdated > 6 else ""
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="homebrew-updates",
                title=f"Homebrew: {total_outdated} Updates Available",
                description=f"Outdated: {', '.join(all_outdated)}{more}",
                severity=DiscoverySeverity.WARNING if total_outdated > 10 else DiscoverySeverity.INFO,
                data={
                    'total': total_outdated,
                    'formulas': outdated_formulas,
                    'casks': outdated_casks,
                },
                actions=[
                    DiscoveryAction(
                        id="show-outdated",
                        label="Show All Outdated",
                        command="brew outdated",
                    ),
                    DiscoveryAction(
                        id="upgrade-all",
                        label="Upgrade All",
                        command="brew upgrade",
                        requires_approval=True,
                    ),
                ],
            ))
        
        return discoveries
    
    def _scan_health(self) -> List[Discovery]:
        """Run brew doctor to check for issues."""
        discoveries = []
        
        code, stdout, stderr = self.run_command(['brew', 'doctor'], timeout=30)
        
        # brew doctor returns non-zero if there are warnings
        if code != 0 or 'Warning' in stdout or 'Warning' in stderr:
            output = stdout + stderr
            warnings = [l for l in output.splitlines() if l.strip().startswith('Warning')]
            
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "homebrew-health")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="homebrew-health",
                title=f"Homebrew: {len(warnings)} Warnings",
                description="Run 'brew doctor' for details",
                severity=DiscoverySeverity.WARNING,
                data={
                    'warning_count': len(warnings),
                    'warnings': warnings[:5],
                    'full_output': output[:1000],
                },
                actions=[
                    DiscoveryAction(
                        id="run-doctor",
                        label="Run Doctor",
                        command="brew doctor",
                    ),
                ],
            ))
        else:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "homebrew-healthy")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="homebrew-healthy",
                title="Homebrew: Healthy",
                description="No issues found by brew doctor",
                severity=DiscoverySeverity.SUCCESS,
                data={},
                actions=[],
            ))
        
        return discoveries
    
    def _scan_cleanup(self) -> List[Discovery]:
        """Check for cleanup opportunities."""
        discoveries = []
        
        # Check what would be cleaned up
        code, stdout, _ = self.run_command(['brew', 'cleanup', '-n'])
        
        if code == 0 and stdout.strip():
            lines = stdout.strip().splitlines()
            # Filter to actual cleanup items
            cleanup_items = [l for l in lines if l.strip() and not l.startswith('=')]
            
            if cleanup_items:
                discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "homebrew-cleanup")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.PACKAGE,
                    name="homebrew-cleanup",
                    title=f"Homebrew: {len(cleanup_items)} Items to Clean",
                    description="Old versions and cache can be removed",
                    severity=DiscoverySeverity.INFO,
                    data={
                        'items': cleanup_items[:10],
                        'total': len(cleanup_items),
                    },
                    actions=[
                        DiscoveryAction(
                            id="preview-cleanup",
                            label="Preview Cleanup",
                            command="brew cleanup -n",
                        ),
                        DiscoveryAction(
                            id="run-cleanup",
                            label="Run Cleanup",
                            command="brew cleanup",
                            requires_approval=True,
                        ),
                    ],
                ))
        
        return discoveries
    
    def _get_formula_info(self, formula: str) -> Optional[dict]:
        """Get detailed info for a formula."""
        code, stdout, _ = self.run_command(['brew', 'info', '--json=v2', formula], timeout=10)
        
        if code != 0:
            return None
        
        try:
            data = json.loads(stdout)
            if data.get('formulae'):
                f = data['formulae'][0]
                return {
                    'name': f.get('name'),
                    'version': f.get('versions', {}).get('stable'),
                    'description': f.get('desc'),
                    'homepage': f.get('homepage'),
                }
        except (json.JSONDecodeError, KeyError, IndexError):
            pass
        
        return None
