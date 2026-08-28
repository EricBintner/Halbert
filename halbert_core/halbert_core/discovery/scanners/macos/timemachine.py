# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Time Machine Scanner - Backup status discovery.

macOS equivalent of Linux BackupScanner.

Discovers:
- Time Machine backup status
- Last backup time
- Backup destinations
- Backup health
"""

from __future__ import annotations
from typing import List
from datetime import datetime
import re

from ..base import BaseScanner
from ...schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class TimeMachineScanner(BaseScanner):
    """
    Scanner for Time Machine backup status.
    
    Equivalent to Linux BackupScanner but for Time Machine.
    """
    
    # Days since last backup thresholds
    BACKUP_WARNING_DAYS = 7
    BACKUP_CRITICAL_DAYS = 30
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.BACKUP
    
    def is_available(self) -> bool:
        """Check if tmutil is available."""
        return self.command_exists('tmutil')
    
    def scan(self) -> List[Discovery]:
        """Scan Time Machine status."""
        discoveries = []
        
        discoveries.extend(self._scan_status())
        discoveries.extend(self._scan_destinations())
        discoveries.extend(self._scan_last_backup())
        
        self.logger.info(f"Found {len(discoveries)} Time Machine discoveries")
        return discoveries
    
    def _scan_status(self) -> List[Discovery]:
        """Check Time Machine enabled status."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['tmutil', 'status'])
        if code != 0:
            return discoveries
        
        # Check if backup is running
        running = 'Running = 1' in stdout or 'BackupPhase' in stdout
        
        if running:
            # Extract progress if available
            progress_match = re.search(r'Percent\s*=\s*([\d.]+)', stdout)
            progress = float(progress_match.group(1)) * 100 if progress_match else None
            
            discovery_id = make_discovery_id(DiscoveryType.BACKUP, "tm-running")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.BACKUP,
                name="timemachine-running",
                title="Time Machine: Backup in Progress",
                description=f"Backup running" + (f" ({progress:.0f}%)" if progress else ""),
                severity=DiscoverySeverity.INFO,
                status="Running",
                data={
                    'tool': 'timemachine',
                    'running': True,
                    'progress': progress,
                },
                actions=[
                    DiscoveryAction(
                        id="tm-status",
                        label="Check Status",
                        command="tmutil status",
                    ),
                ],
            ))
        
        return discoveries
    
    def _scan_destinations(self) -> List[Discovery]:
        """Scan Time Machine destinations."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['tmutil', 'destinationinfo'])
        if code != 0:
            return discoveries
        
        # Check if Time Machine is configured
        if 'No destinations configured' in stdout:
            discovery_id = make_discovery_id(DiscoveryType.BACKUP, "tm-not-configured")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.BACKUP,
                name="timemachine-unconfigured",
                title="Time Machine: Not Configured",
                description="No backup destination configured - your data is not being backed up",
                severity=DiscoverySeverity.WARNING,
                status="Not Configured",
                data={
                    'tool': 'timemachine',
                    'configured': False,
                },
                actions=[
                    DiscoveryAction(
                        id="open-tm-prefs",
                        label="Open Time Machine Preferences",
                        command="open /System/Library/PreferencePanes/TimeMachine.prefPane",
                    ),
                ],
            ))
        else:
            # Parse destinations
            destinations = []
            current_dest = {}
            
            for line in stdout.splitlines():
                line = line.strip()
                if line.startswith('Name'):
                    if current_dest:
                        destinations.append(current_dest)
                    current_dest = {'name': line.split(':', 1)[1].strip()}
                elif line.startswith('Kind'):
                    current_dest['kind'] = line.split(':', 1)[1].strip()
                elif line.startswith('Mount Point'):
                    current_dest['mount_point'] = line.split(':', 1)[1].strip()
            
            if current_dest:
                destinations.append(current_dest)
            
            for dest in destinations:
                discovery_id = make_discovery_id(DiscoveryType.BACKUP, f"tm-dest-{dest.get('name', 'unknown')}")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.BACKUP,
                    name=f"timemachine-{dest.get('name', 'destination')}",
                    title=f"Time Machine: {dest.get('name', 'Backup')}",
                    description=f"Backup destination '{dest.get('name')}' ({dest.get('kind', 'Local')})",
                    severity=DiscoverySeverity.SUCCESS,
                    status="Configured",
                    data={
                        'tool': 'timemachine',
                        'destination': dest.get('mount_point', ''),
                        'source_path': '/',
                        'schedule': 'automatic',
                        **dest,
                    },
                    actions=[
                        DiscoveryAction(
                            id="tm-dest-info",
                            label="Destination Info",
                            command="tmutil destinationinfo",
                        ),
                    ],
                ))
        
        return discoveries
    
    def _scan_last_backup(self) -> List[Discovery]:
        """Check last backup time."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['tmutil', 'latestbackup'])
        if code != 0 or not stdout.strip():
            return discoveries
        
        backup_path = stdout.strip()
        
        # Extract date from backup path (format: .../2024-01-15-123456)
        date_match = re.search(r'(\d{4}-\d{2}-\d{2}-\d{6})', backup_path)
        
        if date_match:
            date_str = date_match.group(1)
            try:
                backup_date = datetime.strptime(date_str, '%Y-%m-%d-%H%M%S')
                days_ago = (datetime.now() - backup_date).days
                
                if days_ago > self.BACKUP_CRITICAL_DAYS:
                    severity = DiscoverySeverity.CRITICAL
                    title = f"Last Backup: {days_ago} days ago"
                    description = f"Last backup was {days_ago} days ago - backups may be failing"
                elif days_ago > self.BACKUP_WARNING_DAYS:
                    severity = DiscoverySeverity.WARNING
                    title = f"Last Backup: {days_ago} days ago"
                    description = f"Last backup was {days_ago} days ago - consider running a backup"
                elif days_ago == 0:
                    severity = DiscoverySeverity.SUCCESS
                    title = "Last Backup: Today"
                    description = f"Last backup completed today at {backup_date.strftime('%H:%M')}"
                else:
                    severity = DiscoverySeverity.SUCCESS
                    title = f"Last Backup: {days_ago} day{'s' if days_ago != 1 else ''} ago"
                    description = f"Last backup: {backup_date.strftime('%Y-%m-%d %H:%M')}"
                
                discovery_id = make_discovery_id(DiscoveryType.BACKUP, "tm-last-backup")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.BACKUP,
                    name="timemachine-last",
                    title=title,
                    description=description,
                    severity=severity,
                    status="Critical" if days_ago > self.BACKUP_CRITICAL_DAYS else ("Warning" if days_ago > self.BACKUP_WARNING_DAYS else "Healthy"),
                    data={
                        'tool': 'timemachine',
                        'last_run': backup_date.isoformat(),
                        'schedule': 'automatic',
                        'last_backup': backup_date.isoformat(),
                        'days_ago': days_ago,
                        'path': backup_path,
                    },
                    actions=[
                        DiscoveryAction(
                            id="start-backup",
                            label="Start Backup Now",
                            command="tmutil startbackup",
                            requires_approval=True,
                        ),
                        DiscoveryAction(
                            id="list-backups",
                            label="List Backups",
                            command="tmutil listbackups",
                        ),
                    ],
                ))
            
            except ValueError:
                pass
        
        return discoveries
