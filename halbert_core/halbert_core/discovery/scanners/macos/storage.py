# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
macOS Storage Scanner - Disk and APFS volume discovery.

macOS equivalent of Linux StorageScanner.

Uses:
- diskutil for disk/volume info
- df for usage stats
- tmutil for Time Machine disk status
"""

from __future__ import annotations
from typing import List
import json
import re

from ..base import BaseScanner
from ...schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class MacStorageScanner(BaseScanner):
    """
    Scanner for macOS storage and APFS volumes.
    
    Equivalent to Linux StorageScanner but for APFS/HFS+.
    """
    
    USAGE_WARNING = 80  # Percent
    USAGE_CRITICAL = 90
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.STORAGE
    
    def is_available(self) -> bool:
        """Check if diskutil is available."""
        return self.command_exists('diskutil')
    
    def scan(self) -> List[Discovery]:
        """Scan storage devices."""
        discoveries = []
        
        discoveries.extend(self._scan_volumes())
        discoveries.extend(self._scan_apfs_containers())
        discoveries.extend(self._scan_disk_usage())
        
        self.logger.info(f"Found {len(discoveries)} storage discoveries")
        return discoveries
    
    def _scan_volumes(self) -> List[Discovery]:
        """Scan mounted volumes."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['diskutil', 'list', '-plist'])
        if code != 0:
            return discoveries
        
        try:
            import plistlib
            data = plistlib.loads(stdout.encode())
            
            for disk in data.get('AllDisksAndPartitions', []):
                disk_id = disk.get('DeviceIdentifier', '')
                
                # Process partitions
                for partition in disk.get('Partitions', []):
                    part_id = partition.get('DeviceIdentifier', '')
                    mount_point = partition.get('MountPoint', '')
                    volume_name = partition.get('VolumeName', part_id)
                    size = partition.get('Size', 0)
                    
                    if not mount_point:
                        continue
                    
                    # Get usage
                    usage = self._get_mount_usage(mount_point)
                    
                    # Determine severity
                    if usage and usage > self.USAGE_CRITICAL:
                        severity = DiscoverySeverity.CRITICAL
                    elif usage and usage > self.USAGE_WARNING:
                        severity = DiscoverySeverity.WARNING
                    else:
                        severity = DiscoverySeverity.SUCCESS
                    
                    discovery_id = make_discovery_id(DiscoveryType.STORAGE, f"vol-{part_id}")
                    
                    discoveries.append(Discovery(
                        id=discovery_id,
                        type=DiscoveryType.STORAGE,
                        name=part_id,
                        title=f"Volume: {volume_name}",
                        description=f"{volume_name} at {mount_point} - {usage}% used" if usage else f"{volume_name} at {mount_point}",
                        severity=severity,
                        details={
                            'device': part_id,
                            'mount_point': mount_point,
                            'volume_name': volume_name,
                            'size_bytes': size,
                            'usage_percent': usage,
                        },
                        actions=[
                            DiscoveryAction(
                                id=f"info-{part_id}",
                                label="Volume Info",
                                command=f"diskutil info {part_id}",
                                dry_run=True,
                            ),
                        ],
                        tags=['storage', 'volume', 'macos'],
                    ))
        
        except Exception as e:
            self.logger.debug(f"Failed to parse diskutil output: {e}")
        
        return discoveries
    
    def _scan_apfs_containers(self) -> List[Discovery]:
        """Scan APFS containers."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['diskutil', 'apfs', 'list', '-plist'])
        if code != 0:
            return discoveries
        
        try:
            import plistlib
            data = plistlib.loads(stdout.encode())
            
            for container in data.get('Containers', []):
                container_ref = container.get('ContainerReference', '')
                capacity = container.get('CapacityCeiling', 0)
                free = container.get('CapacityFree', 0)
                
                usage = 100 - (free / capacity * 100) if capacity > 0 else 0
                
                # Determine severity
                if usage > self.USAGE_CRITICAL:
                    severity = DiscoverySeverity.CRITICAL
                elif usage > self.USAGE_WARNING:
                    severity = DiscoverySeverity.WARNING
                else:
                    severity = DiscoverySeverity.SUCCESS
                
                discovery_id = make_discovery_id(DiscoveryType.STORAGE, f"apfs-{container_ref}")
                
                size_gb = capacity / (1024**3)
                free_gb = free / (1024**3)
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.STORAGE,
                    name=container_ref,
                    title=f"APFS Container: {container_ref}",
                    description=f"{size_gb:.1f} GB total, {free_gb:.1f} GB free ({usage:.1f}% used)",
                    severity=severity,
                    details={
                        'container': container_ref,
                        'capacity_bytes': capacity,
                        'free_bytes': free,
                        'usage_percent': round(usage, 1),
                        'volumes': len(container.get('Volumes', [])),
                    },
                    actions=[
                        DiscoveryAction(
                            id=f"apfs-info-{container_ref}",
                            label="Container Info",
                            command=f"diskutil apfs list {container_ref}",
                            dry_run=True,
                        ),
                    ],
                    tags=['storage', 'apfs', 'container', 'macos'],
                ))
        
        except Exception as e:
            self.logger.debug(f"Failed to parse APFS output: {e}")
        
        return discoveries
    
    def _scan_disk_usage(self) -> List[Discovery]:
        """Scan disk usage with df."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['df', '-h'])
        if code != 0:
            return discoveries
        
        # Find root filesystem
        for line in stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6 and parts[-1] == '/':
                usage_str = parts[4].rstrip('%')
                try:
                    usage = int(usage_str)
                    
                    if usage > self.USAGE_CRITICAL:
                        severity = DiscoverySeverity.CRITICAL
                        title = f"Root Disk: {usage}% FULL"
                    elif usage > self.USAGE_WARNING:
                        severity = DiscoverySeverity.WARNING
                        title = f"Root Disk: {usage}% used"
                    else:
                        severity = DiscoverySeverity.SUCCESS
                        title = f"Root Disk: {usage}% used"
                    
                    discovery_id = make_discovery_id(DiscoveryType.STORAGE, "root-usage")
                    
                    discoveries.append(Discovery(
                        id=discovery_id,
                        type=DiscoveryType.STORAGE,
                        name="root-disk",
                        title=title,
                        description=f"Root filesystem at {usage}% capacity ({parts[2]} used of {parts[1]})",
                        severity=severity,
                        details={
                            'filesystem': parts[0],
                            'size': parts[1],
                            'used': parts[2],
                            'available': parts[3],
                            'usage_percent': usage,
                        },
                        actions=[
                            DiscoveryAction(
                                id="disk-usage",
                                label="Show Usage",
                                command="df -h",
                                dry_run=True,
                            ),
                            DiscoveryAction(
                                id="find-large",
                                label="Find Large Files",
                                command="du -sh /* 2>/dev/null | sort -hr | head -20",
                                dry_run=True,
                            ),
                        ],
                        tags=['storage', 'disk', 'usage', 'macos'],
                    ))
                    break
                except ValueError:
                    continue
        
        return discoveries
    
    def _get_mount_usage(self, mount_point: str) -> int | None:
        """Get usage percentage for a mount point."""
        code, stdout, _ = self.run_command(['df', mount_point])
        if code != 0:
            return None
        
        lines = stdout.strip().splitlines()
        if len(lines) < 2:
            return None
        
        parts = lines[1].split()
        if len(parts) >= 5:
            usage_str = parts[4].rstrip('%')
            try:
                return int(usage_str)
            except ValueError:
                pass
        
        return None
