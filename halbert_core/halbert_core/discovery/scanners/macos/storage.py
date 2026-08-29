# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
macOS Storage Scanner - Disk and APFS volume discovery.

macOS equivalent of Linux StorageScanner.

Uses:
- diskutil for disk/volume info
- df for usage stats
- system_profiler for physical disk model/SMART

Produces discoveries with names prefixed ``fs-`` (filesystems) and
``disk-`` (physical disks) so the Storage.tsx frontend filtering logic
(which was written for the Linux scanner) matches them unchanged.
"""

from __future__ import annotations
from typing import List, Optional
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

        # Physical disks first (so filesystems can reference them as parent_disk)
        disk_discoveries = self._scan_physical_disks()
        discoveries.extend(disk_discoveries)

        # Filesystems (mounted volumes from df)
        discoveries.extend(self._scan_filesystems())

        # APFS containers (as pseudo-disks)
        discoveries.extend(self._scan_apfs_containers())

        self.logger.info(f"Found {len(discoveries)} storage discoveries")
        return discoveries

    # ─────────────────────────────────────────────────────────────
    # Physical disks
    # ─────────────────────────────────────────────────────────────

    def _scan_physical_disks(self) -> List[Discovery]:
        """Scan physical disks via system_profiler."""
        discoveries = []

        code, stdout, _ = self.run_command(
            ['system_profiler', 'SPStorageDataType', '-json'],
            timeout=15,
        )
        if code != 0:
            return discoveries

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return discoveries

        for item in data.get('SPStorageDataType', []):
            name = item.get('_name', 'Unknown Disk')
            bsd_name = item.get('bsdName', '').replace('/dev/', '')
            size_str = item.get('size_in_bytes', item.get('SPStorageDataType', 'Unknown'))
            model = item.get('physical_drive_type', name)
            transport = item.get('interface', 'unknown')
            smart_status = item.get('smartstatus', 'Verified')

            # Normalize SMART status
            if isinstance(smart_status, str):
                smart_lower = smart_status.lower()
                if 'verified' in smart_lower or 'ok' in smart_lower:
                    smart_status = 'PASSED'
                elif 'failing' in smart_lower or 'failed' in smart_lower:
                    smart_status = 'FAILED'
                else:
                    smart_status = smart_status.upper()

            # Determine disk type
            disk_type = 'SSD'
            if 'hdd' in str(model).lower() or 'rotational' in str(model).lower():
                disk_type = 'HDD'
            if 'nvme' in transport.lower():
                disk_type = 'NVMe'

            # Determine severity
            if smart_status == 'FAILED':
                severity = DiscoverySeverity.CRITICAL
                status = 'SMART Failed'
            elif smart_status == 'WARNING':
                severity = DiscoverySeverity.WARNING
                status = 'SMART Warning'
            else:
                severity = DiscoverySeverity.SUCCESS
                status = 'Healthy'

            # Format size
            if isinstance(size_str, (int, float)) and size_str > 0:
                size_gb = size_str / (1024 ** 3)
                size_formatted = f"{size_gb:.0f}G"
            else:
                size_formatted = str(size_str)

            disk_name = f"disk-{bsd_name}" if bsd_name else f"disk-{name.lower().replace(' ', '-')}"

            discovery_id = make_discovery_id(DiscoveryType.STORAGE, disk_name)

            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.STORAGE,
                name=disk_name,
                title=f"{name} ({size_formatted})",
                description=f"{disk_type} disk{f' at /dev/{bsd_name}' if bsd_name else ''}",
                icon="hard-drive",
                severity=severity,
                status=status,
                status_detail=f"Transport: {transport}",
                source=f"/dev/{bsd_name}" if bsd_name else None,
                data={
                    "device": f"/dev/{bsd_name}" if bsd_name else name,
                    "size": size_formatted,
                    "model": name,
                    "type": disk_type,
                    "transport": transport,
                    "smart_status": smart_status,
                    "serial": "",
                    "uuid": "",
                    "wwn": "",
                },
                actions=[
                    DiscoveryAction(
                        id="smart_details",
                        label="SMART Details",
                        icon="activity",
                    ),
                    DiscoveryAction(
                        id="chat",
                        label="Chat",
                        icon="message-circle",
                    ),
                ],
                chat_context=f"This is a {disk_type} disk: {name}, {size_formatted}. "
                             f"Device: /dev/{bsd_name}. SMART status: {smart_status}.",
            ))

        return discoveries

    # ─────────────────────────────────────────────────────────────
    # Filesystems (mounted, from df)
    # ─────────────────────────────────────────────────────────────

    def _scan_filesystems(self) -> List[Discovery]:
        """Scan mounted filesystems via df -h (human-readable)."""
        discoveries = []

        code, stdout, _ = self.run_command(['df', '-h'])
        if code != 0:
            return discoveries

        for line in stdout.splitlines()[1:]:
            # macOS df -h has 9 columns:
            #   Filesystem Size Used Avail Capacity iused ifree %iused Mounted_on
            # The mount point (last column) can contain spaces, so split from
            # the left with maxsplit=8 to capture it as a single field.
            parts = line.split(None, 8)
            if len(parts) < 9:
                # Some lines (e.g. devfs) may have fewer columns; the mount
                # point is still the last field.
                if len(parts) < 6:
                    continue
                # Fall back: mount point is the last field
                device = parts[0]
                size = parts[1]
                used = parts[2]
                avail = parts[3]
                percent_str = parts[4].rstrip('%')
                mountpoint = parts[-1]
            else:
                device = parts[0]
                size = parts[1]
                used = parts[2]
                avail = parts[3]
                percent_str = parts[4].rstrip('%')
                mountpoint = parts[8]

            # Skip virtual / system filesystems
            skip_prefixes = ('devfs', 'map ', '/dev/lo', 'tmpfs', 'procfs', 'fdesc')
            if any(device.lower().startswith(p) for p in skip_prefixes):
                continue

            # Skip Xcode simulator volumes (dozens of tiny disk images)
            if '/CoreSimulator/' in mountpoint:
                continue
            # Skip Time Machine backup snapshots (mounted under .timemachine)
            if '/.timemachine/' in mountpoint:
                continue
            # Skip system-only volumes that share the same APFS container as /
            skip_mounts = {'/System/Volumes/VM', '/System/Volumes/Preboot',
                          '/System/Volumes/Update', '/System/Volumes/xarts',
                          '/System/Volumes/iSCPreboot', '/System/Volumes/Hardware',
                          '/System/Volumes/Recovery', '/System/Volumes/HardwareMACOS'}
            if mountpoint in skip_mounts:
                continue
            # Skip update staging mounts
            if '/System/Volumes/Update/SFR/mnt1' in mountpoint:
                continue
            if '/System/Volumes/Update/mnt1' in mountpoint:
                continue

            try:
                percent = int(percent_str)
            except ValueError:
                continue

            # Determine fstype
            fstype = self._get_fstype(mountpoint)

            # Determine severity
            if percent > self.USAGE_CRITICAL:
                severity = DiscoverySeverity.CRITICAL
                status = 'Critical'
            elif percent > self.USAGE_WARNING:
                severity = DiscoverySeverity.WARNING
                status = 'Warning'
            else:
                severity = DiscoverySeverity.SUCCESS
                status = 'Healthy'

            # Generate name slug from mountpoint
            name_slug = mountpoint.replace('/', '-').strip('-') or 'root'
            fs_name = f"fs-{name_slug}"

            discovery_id = make_discovery_id(DiscoveryType.STORAGE, fs_name)

            # Extract parent disk from device path
            parent_disk = self._get_parent_disk(device)

            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.STORAGE,
                name=fs_name,
                title=f"{mountpoint} ({size})",
                description=f"{fstype} filesystem, {avail} free",
                icon="folder",
                severity=severity,
                status=status,
                status_detail=f"{used} used of {size}",
                source=device,
                data={
                    "source": device,
                    "device": device,
                    "parent_disk": parent_disk,
                    "fstype": fstype,
                    "size": size,
                    "used": used,
                    "available": avail,
                    "percent": percent,
                    "mountpoint": mountpoint,
                    "array_type": None,
                    "array_profile": "single",
                    "array_members": [],
                },
                actions=[
                    DiscoveryAction(
                        id="analyze",
                        label="Analyze Usage",
                        icon="pie-chart",
                    ),
                    DiscoveryAction(
                        id="chat",
                        label="Chat",
                        icon="message-circle",
                    ),
                ],
                chat_context=f"This is a {fstype} filesystem mounted at {mountpoint}. "
                             f"Size: {size}, Used: {used} ({percent}%), Available: {avail}.",
            ))

        return discoveries

    # ─────────────────────────────────────────────────────────────
    # APFS containers
    # ─────────────────────────────────────────────────────────────

    def _scan_apfs_containers(self) -> List[Discovery]:
        """Scan APFS containers as pseudo-disk entries."""
        discoveries = []

        code, stdout, _ = self.run_command(['diskutil', 'apfs', 'list', '-plist'])
        if code != 0:
            return discoveries

        try:
            import plistlib
            data = plistlib.loads(stdout.encode())
        except Exception as e:
            self.logger.debug(f"Failed to parse APFS output: {e}")
            return discoveries

        for container in data.get('Containers', []):
            container_ref = container.get('ContainerReference', '')
            capacity = container.get('CapacityCeiling', 0)
            free = container.get('CapacityFree', 0)

            usage = 100 - (free / capacity * 100) if capacity > 0 else 0

            if usage > self.USAGE_CRITICAL:
                severity = DiscoverySeverity.CRITICAL
            elif usage > self.USAGE_WARNING:
                severity = DiscoverySeverity.WARNING
            else:
                severity = DiscoverySeverity.SUCCESS

            size_gb = capacity / (1024 ** 3)
            free_gb = free / (1024 ** 3)
            size_formatted = f"{size_gb:.0f}G"

            disk_name = f"disk-{container_ref}"
            discovery_id = make_discovery_id(DiscoveryType.STORAGE, disk_name)

            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.STORAGE,
                name=disk_name,
                title=f"APFS Container: {container_ref}",
                description=f"{size_gb:.1f} GB total, {free_gb:.1f} GB free ({usage:.1f}% used)",
                icon="hard-drive",
                severity=severity,
                status='Healthy',
                source=f"/dev/{container_ref}",
                data={
                    "device": f"/dev/{container_ref}",
                    "size": size_formatted,
                    "model": f"APFS Container ({container_ref})",
                    "type": "APFS",
                    "transport": "apfs",
                    "smart_status": "N/A",
                    "serial": "",
                    "uuid": "",
                    "wwn": "",
                    "capacity_bytes": capacity,
                    "free_bytes": free,
                    "usage_percent": round(usage, 1),
                    "volumes": len(container.get('Volumes', [])),
                },
                actions=[
                    DiscoveryAction(
                        id=f"apfs-info-{container_ref}",
                        label="Container Info",
                        command=f"diskutil apfs list {container_ref}",
                    ),
                ],
                chat_context=f"This is an APFS container: {container_ref}. "
                             f"Size: {size_gb:.1f} GB, Free: {free_gb:.1f} GB ({usage:.1f}% used).",
            ))

        return discoveries

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _get_fstype(self, mountpoint: str) -> str:
        """Get filesystem type for a mount point."""
        code, stdout, _ = self.run_command(['mount'], timeout=5)
        if code != 0:
            return 'unknown'

        for line in stdout.splitlines():
            if mountpoint in line:
                # Format: /dev/disk1s1 on / (apfs, local, read-only, journaled)
                match = re.search(r'on\s+' + re.escape(mountpoint) + r'\s*\(([^,)]+)', line)
                if match:
                    return match.group(1).strip()
        return 'unknown'

    def _get_parent_disk(self, device: str) -> Optional[str]:
        """
        Extract parent disk from a macOS device path.

        Examples:
            /dev/disk1s1 -> /dev/disk1
            /dev/disk2s3 -> /dev/disk2
        """
        if not device.startswith('/dev/'):
            return None

        # disk1s1 -> disk1 (strip the sN suffix)
        match = re.match(r'(/dev/disk\d+)s\d+', device)
        if match:
            return match.group(1)

        # Already a whole disk
        if re.match(r'/dev/disk\d+$', device):
            return device

        return None
