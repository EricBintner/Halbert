"""
Storage Scanner - Discover disks, filesystems, and storage health.

Implements Phase 9 research from:
- docs/Phase9/deep-dives/04-filesystem-health.md
- docs/Phase9/deep-dives/09-storage-systems.md

Discovers:
- Physical disks (with SMART status)
- Filesystems and mount points
- Disk usage warnings
- Special filesystems (bcachefs, btrfs, zfs)
"""

from __future__ import annotations
from typing import List, Optional
import glob
import json
import os
import re

from .base import BaseScanner
from ..schema import (
    Discovery, 
    DiscoveryType, 
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class StorageScanner(BaseScanner):
    """
    Scanner for storage devices and filesystems.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.STORAGE
    
    def scan(self) -> List[Discovery]:
        """Scan system for storage."""
        discoveries = []
        
        discoveries.extend(self._scan_disks())
        discoveries.extend(self._scan_filesystems())
        discoveries.extend(self._scan_unmounted_filesystems())
        
        self.logger.info(f"Found {len(discoveries)} storage items")
        return discoveries
    
    def _scan_disks(self) -> List[Discovery]:
        """Scan physical disks."""
        discoveries = []
        
        # Use lsblk to get disk info (UUID requires root for some devices)
        code, stdout, _ = self.run_command([
            "lsblk", "-J", "-o", 
            "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,MODEL,SERIAL,ROTA,TRAN,UUID,WWN"
        ])
        
        if code != 0:
            return discoveries
        
        try:
            data = json.loads(stdout)
            devices = data.get('blockdevices', [])
            
            for device in devices:
                if device.get('type') != 'disk':
                    continue
                
                name = device.get('name', '')
                size = device.get('size', 'Unknown')
                model = device.get('model', 'Unknown').strip() if device.get('model') else 'Unknown'
                is_rotational = device.get('rota', True)
                transport = device.get('tran', 'unknown')
                serial = device.get('serial', '').strip() if device.get('serial') else ''
                uuid = device.get('uuid', '').strip() if device.get('uuid') else ''
                wwn = device.get('wwn', '').strip() if device.get('wwn') else ''
                
                # Check SMART status
                smart_status = self._get_smart_status(f"/dev/{name}")
                
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
                
                disk_type = "HDD" if is_rotational else "SSD"
                if transport == 'nvme':
                    disk_type = "NVMe"
                
                discovery_id = make_discovery_id(DiscoveryType.STORAGE, f"disk-{name}")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.STORAGE,
                    name=f"disk-{name}",
                    title=f"{model} ({size})",
                    description=f"{disk_type} disk at /dev/{name}",
                    icon="hard-drive",
                    severity=severity,
                    status=status,
                    status_detail=f"Transport: {transport}",
                    source=f"/dev/{name}",
                    data={
                        "device": f"/dev/{name}",
                        "size": size,
                        "model": model,
                        "type": disk_type,
                        "transport": transport,
                        "smart_status": smart_status,
                        "serial": serial,
                        "uuid": uuid,
                        "wwn": wwn,
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
                    chat_context=f"This is a {disk_type} disk: {model}, {size}. "
                                f"Device: /dev/{name}. SMART status: {smart_status}.",
                ))
            
        except json.JSONDecodeError:
            pass
        
        # Discover MD RAID arrays from /proc/mdstat (they're not top-level in lsblk)
        discoveries.extend(self._scan_md_arrays())
        
        return discoveries
    
    def _scan_md_arrays(self) -> list:
        """Discover MD RAID arrays from /proc/mdstat."""
        discoveries = []
        
        try:
            with open('/proc/mdstat', 'r') as f:
                mdstat = f.read()
        except Exception:
            return discoveries
        
        # Parse mdstat for active arrays
        # Format: "md122 : active raid0 sds1[1] sdr1[0]"
        for line in mdstat.splitlines():
            if not line or line.startswith('Personalities') or line.startswith('unused'):
                continue
            if ':' not in line:
                continue
            
            parts = line.split(':')
            if len(parts) < 2:
                continue
            
            name = parts[0].strip()
            if not name.startswith('md'):
                continue
            
            info_parts = parts[1].split()
            if len(info_parts) < 2:
                continue
            
            # Get status and raid level
            status = info_parts[0] if info_parts else 'unknown'
            raid_level = 'raid'
            for part in info_parts:
                if part.startswith('raid'):
                    raid_level = part
                    break
            
            # Get member devices (format: sdX[N])
            members = []
            for part in info_parts:
                if '[' in part and ']' in part:
                    dev = part.split('[')[0]
                    # Remove partition number if present (sdr1 -> sdr)
                    base_dev = re.sub(r'\d+$', '', dev)
                    members.append(f"/dev/{base_dev}")
            
            # Get size from lsblk
            code, stdout, _ = self.run_command(["lsblk", "-n", "-o", "SIZE", f"/dev/{name}"])
            size = stdout.strip() if code == 0 else "Unknown"
            
            discovery_id = make_discovery_id(DiscoveryType.STORAGE, f"md-{name}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.STORAGE,
                name=f"md-{name}",
                title=f"MD {raid_level.upper()} ({size})",
                description=f"Software RAID array with {len(members)} disks",
                icon="hard-drive",
                severity=DiscoverySeverity.SUCCESS,
                status=status.capitalize(),
                status_detail=f"{len(members)} member disks",
                source=f"/dev/{name}",
                data={
                    "device": f"/dev/{name}",
                    "size": size,
                    "model": f"MD {raid_level.upper()}",
                    "type": "RAID",
                    "transport": "md",
                    "smart_status": "N/A",
                    "raid_level": raid_level,
                    "member_count": len(members),
                    "members": members,
                },
                actions=[
                    DiscoveryAction(
                        id="mdadm_details",
                        label="RAID Details",
                        icon="layers",
                    ),
                ],
                chat_context=f"This is an MD {raid_level.upper()} software RAID array. "
                            f"Size: {size}. Members: {len(members)} disks.",
            ))
        
        return discoveries
    
    def _get_mdadm_info(self, device: str) -> dict:
        """Get mdadm array information."""
        result = {"level": "raid", "member_count": 0, "members": []}
        
        # Parse /proc/mdstat for quick info
        try:
            with open('/proc/mdstat', 'r') as f:
                mdstat = f.read()
            
            # Extract device name (e.g., "md122" from "/dev/md122")
            dev_name = device.replace('/dev/', '')
            
            for line in mdstat.splitlines():
                if line.startswith(dev_name + ' '):
                    # Line format: "md122 : active raid0 sds1[1] sdr1[0]"
                    parts = line.split()
                    if 'raid' in line.lower():
                        for part in parts:
                            if part.startswith('raid'):
                                result["level"] = part
                                break
                    
                    # Count member devices (format: sdX[N])
                    members = [p for p in parts if '[' in p and ']' in p]
                    result["member_count"] = len(members)
                    result["members"] = [f"/dev/{m.split('[')[0]}" for m in members]
                    break
                    
        except Exception:
            pass
        
        return result
    
    def _get_smart_status(self, device: str) -> str:
        """Get SMART status for a device."""
        if not self.command_exists("smartctl"):
            return "N/A"
        
        # First check if device supports SMART
        code, info_out, info_err = self.run_command([
            "smartctl", "-i", device
        ], timeout=10)
        
        info_combined = (info_out + info_err).lower()
        
        # Check for permission denied
        if "permission denied" in info_combined or "operation not permitted" in info_combined:
            # Try with sudo (requires NOPASSWD in sudoers)
            code, info_out, info_err = self.run_command([
                "sudo", "-n", "smartctl", "-i", device
            ], timeout=10)
            info_combined = (info_out + info_err).lower()
            
            if "password is required" in info_combined:
                return "NO_ACCESS"
        
        # Check if SMART is supported
        if "smart support is:     unavailable" in info_combined or \
           "device does not support smart" in info_combined or \
           "smart support is: unavailable" in info_combined:
            return "N/A"
        
        # Now get health status
        code, stdout, stderr = self.run_command([
            "smartctl", "-H", device
        ], timeout=10)
        
        stdout_lower = stdout.lower()
        
        # SATA drives say "PASSED", SAS/SCSI say "OK"
        if "passed" in stdout_lower or "smart health status: ok" in stdout_lower:
            return "PASSED"
        elif "failed" in stdout_lower:
            return "FAILED"
        elif "warning" in stdout_lower:
            return "WARNING"
        else:
            return "UNKNOWN"
    
    def _get_parent_disk(self, device: str) -> Optional[str]:
        """
        Extract parent disk device from a partition device path.
        
        Examples:
            /dev/nvme0n1p2 -> /dev/nvme0n1
            /dev/sda1 -> /dev/sda
            /dev/mapper/root -> None (LVM)
            UUID=xxx -> None
        """
        if not device.startswith('/dev/'):
            return None
        
        # Handle LVM, mapper, md devices - can't easily get parent
        if '/mapper/' in device or device.startswith('/dev/md'):
            return None
        
        # NVMe: /dev/nvme0n1p2 -> /dev/nvme0n1
        nvme_match = re.match(r'(/dev/nvme\d+n\d+)p\d+', device)
        if nvme_match:
            return nvme_match.group(1)
        
        # SATA/SAS/USB: /dev/sda1 -> /dev/sda
        sata_match = re.match(r'(/dev/[a-z]+)\d+', device)
        if sata_match:
            return sata_match.group(1)
        
        # If no partition number, it might be the disk itself
        if re.match(r'/dev/(sd[a-z]+|nvme\d+n\d+)$', device):
            return device
        
        return None
    
    def _get_array_info(self, mountpoint: str, fstype: str, device: str) -> dict:
        """
        Get array/pool member devices for multi-disk filesystems.
        
        Returns dict with:
            type: "btrfs", "bcachefs", "zfs", "mdadm", "lvm", or None
            profile: "single", "raid0", "raid1", "raid5", "raid6", "raid10", etc.
            members: list of {"device": str, "size": str, "role": str}
        """
        if fstype == 'btrfs':
            return self._scan_btrfs_array(mountpoint)
        elif fstype == 'bcachefs':
            return self._scan_bcachefs_array(mountpoint)
        elif fstype == 'zfs':
            return self._scan_zfs_pool(mountpoint)
        elif device.startswith('/dev/md'):
            return self._scan_mdadm_array(device)
        elif device.startswith('/dev/bcache'):
            return self._scan_bcache_device(device)
        
        # Check if underlying device is bcache (e.g., btrfs on /dev/bcache0)
        if os.path.exists(f"/sys/block/{device.split('/')[-1]}/bcache"):
            return self._scan_bcache_device(device)
        
        # Single-disk filesystem
        return {"type": None, "profile": "single", "members": []}
    
    def _scan_btrfs_array(self, mountpoint: str) -> dict:
        """
        Scan btrfs filesystem for all member devices.
        
        Uses sysfs (no sudo needed): /sys/fs/btrfs/<uuid>/devices/
        Falls back to btrfs command if sysfs fails.
        """
        result = {"type": "btrfs", "profile": "single", "members": [], "data_profile": None, "metadata_profile": None}
        
        # First, get the btrfs UUID from findmnt
        code, stdout, _ = self.run_command(["findmnt", "-n", "-o", "UUID", mountpoint])
        if code == 0 and stdout.strip():
            uuid = stdout.strip()
            sysfs_path = f"/sys/fs/btrfs/{uuid}/devices"
            
            if os.path.isdir(sysfs_path):
                for dev_name in os.listdir(sysfs_path):
                    if dev_name.startswith('.'):
                        continue
                    # dev_name is like "nvme17n1p1" - convert to /dev/nvme17n1p1
                    device_path = f"/dev/{dev_name}"
                    # Get parent disk for size lookup
                    parent = self._get_parent_disk(device_path) or device_path
                    result["members"].append({
                        "device": parent,  # Use parent disk (e.g., /dev/nvme17n1)
                        "size": "Unknown",
                    })
                
                # Get profiles from btrfs fi df (doesn't need sudo)
                # Example output:
                # Data, RAID0: total=4.00TiB, used=1.40TiB
                # System, RAID1: total=64.00MiB, used=176.00KiB
                # Metadata, RAID1: total=10.00GiB, used=2.85GiB
                code2, stdout2, _ = self.run_command(["btrfs", "fi", "df", mountpoint])
                if code2 == 0:
                    for line in stdout2.splitlines():
                        if line.startswith('Data,'):
                            profile = line.split(',')[1].split(':')[0].strip().lower()
                            result["profile"] = profile
                            result["data_profile"] = profile
                        elif line.startswith('Metadata,'):
                            meta_profile = line.split(',')[1].split(':')[0].strip().lower()
                            result["metadata_profile"] = meta_profile
                
                if result["members"]:
                    return result
        
        # Fallback: try btrfs command (may need sudo)
        if self.command_exists("btrfs"):
            code, stdout, _ = self.run_command(["btrfs", "filesystem", "show", mountpoint], timeout=10)
            if code == 0:
                for line in stdout.splitlines():
                    line = line.strip()
                    if line.startswith('devid') and 'path' in line:
                        parts = line.split()
                        try:
                            path_idx = parts.index('path') + 1
                            size_idx = parts.index('size') + 1
                            device_path = parts[path_idx] if path_idx < len(parts) else None
                            device_size = parts[size_idx] if size_idx < len(parts) else "Unknown"
                            if device_path:
                                result["members"].append({
                                    "device": device_path,
                                    "size": device_size,
                                })
                        except (ValueError, IndexError):
                            continue
            
            # Get profiles from btrfs fi df
            code2, stdout2, _ = self.run_command(["btrfs", "fi", "df", mountpoint])
            if code2 == 0:
                for line in stdout2.splitlines():
                    if line.startswith('Data,'):
                        profile = line.split(',')[1].split(':')[0].strip().lower()
                        result["profile"] = profile
                        result["data_profile"] = profile
                    elif line.startswith('Metadata,'):
                        meta_profile = line.split(',')[1].split(':')[0].strip().lower()
                        result["metadata_profile"] = meta_profile
        
        return result
    
    def _scan_bcachefs_array(self, mountpoint: str) -> dict:
        """
        Scan bcachefs filesystem for all member devices with tier roles.
        
        bcachefs has configurable targets:
        - foreground_target: tier for new writes (cache/hot tier)
        - background_target: tier data moves to after aging (cold tier)
        - metadata_target: tier for filesystem metadata
        - promote_target: tier for promoted hot data
        
        Device labels indicate tier membership: "nvme.u2_01" -> tier "nvme"
        """
        result = {
            "type": "bcachefs", 
            "profile": "single", 
            "members": [], 
            "tiers": {},
            "targets": {},  # foreground, background, metadata, promote targets
            "data_profile": None,
            "metadata_profile": None,
        }
        
        # Get replication settings from mount options
        # bcachefs uses data_replicas=N and metadata_replicas=N
        # Display as "N replicas" to match bcachefs terminology
        code_mount, stdout_mount, _ = self.run_command(["findmnt", "-n", "-o", "OPTIONS", mountpoint])
        if code_mount == 0 and stdout_mount:
            for opt in stdout_mount.strip().split(','):
                if opt.startswith('data_replicas='):
                    n = opt.split('=')[1]
                    result["data_profile"] = "single" if n == "1" else f"{n} replicas"
                elif opt.startswith('metadata_replicas='):
                    n = opt.split('=')[1]
                    result["metadata_profile"] = "single" if n == "1" else f"{n} replicas"
        
        # First, try to get target configuration from any device
        # We need to find a device in this filesystem to read show-super
        targets = self._get_bcachefs_targets(mountpoint)
        if targets:
            result["targets"] = targets
        
        # Try bcachefs fs usage for detailed tier/label info
        # Note: requires root, use sudo -n with full path (NOPASSWD configured in /etc/sudoers.d/cerebric-bcachefs)
        bcachefs_path = "/usr/local/sbin/bcachefs"
        code, stdout, stderr = self.run_command(["sudo", "-n", bcachefs_path, "fs", "usage", mountpoint], timeout=10)
        self.logger.debug(f"bcachefs fs usage: code={code}, stdout_len={len(stdout) if stdout else 0}, stderr={stderr[:50] if stderr else ''}")
        
        if code == 0 and stdout.strip():
            tiers: dict = {}  # tier_name -> list of devices
            
            for line in stdout.splitlines():
                # Device lines: "nvme.u2_01 (device 0):         nvme12n1"
                # Or: "bg.hdd_14t_1 (device 4):       sdi"
                if '(device' in line and '):' in line:
                    try:
                        # Extract label and device
                        label_part = line.split('(device')[0].strip()
                        device_part = line.split('):')[1].split()[0].strip()
                        
                        if not device_part:
                            continue
                        
                        device_path = f"/dev/{device_part}" if not device_part.startswith('/dev/') else device_part
                        
                        # Determine tier from label prefix (e.g., "nvme" from "nvme.u2_01", "bg" from "bg.hdd_14t_1")
                        tier = label_part.split('.')[0] if '.' in label_part else label_part.split('_')[0]
                        
                        # Determine roles based on targets and tier (can be multiple)
                        roles = self._get_bcachefs_roles(tier, targets)
                        
                        result["members"].append({
                            "device": device_path,
                            "size": "Unknown",
                            "role": roles[0] if roles else "data",  # Primary role for backward compat
                            "roles": roles,  # All roles this device serves
                            "label": label_part,
                            "tier": tier,
                        })
                        
                        # Group by tier
                        if tier not in tiers:
                            tiers[tier] = []
                        tiers[tier].append(device_path)
                        
                    except (IndexError, ValueError):
                        continue
            
            result["tiers"] = tiers
            
            if result["members"]:
                # Determine profile based on tiers
                tier_count = len(tiers)
                if tier_count > 1:
                    result["profile"] = "tiered"
                elif len(result["members"]) > 1:
                    result["profile"] = "multi"
                return result
        
        # Fallback: findmnt returns colon-separated device list
        code, stdout, _ = self.run_command(["findmnt", "-n", "-o", "SOURCE", mountpoint])
        if code != 0 or not stdout.strip():
            return result
        
        source = stdout.strip()
        devices_list = []
        
        if ':' in source:
            devices_list = [d.strip() for d in source.split(':') if d.strip().startswith('/dev/')]
        elif source.startswith('/dev/'):
            devices_list = [source]
        
        # Get device transport types to infer tier roles
        transport_map = self._get_device_transports(devices_list)
        
        # Count by transport to determine majority (data) vs minority (cache)
        transport_counts: dict = {}
        for dev, transport in transport_map.items():
            transport_counts[transport] = transport_counts.get(transport, 0) + 1
        
        # NVMe/SSD with fewer devices = likely cache tier
        # HDD/md with more devices = likely data tier
        has_nvme = 'nvme' in transport_counts
        has_hdd = any(t in transport_counts for t in ['sata', 'sas', 'md'])
        
        for dev in devices_list:
            transport = transport_map.get(dev, 'unknown')
            
            # Infer role from transport type when we have mixed tiers
            if has_nvme and has_hdd:
                if transport == 'nvme':
                    role = 'cache'
                else:
                    role = 'data'
            else:
                role = 'data'
            
            result["members"].append({
                "device": dev,
                "size": "Unknown",
                "role": role,
                "tier": transport,
            })
            
            # Build tiers dict
            if transport not in result["tiers"]:
                result["tiers"][transport] = []
            result["tiers"][transport].append(dev)
        
        if len(result["tiers"]) > 1:
            result["profile"] = "tiered"
        elif len(result["members"]) > 1:
            result["profile"] = "multi"
        
        return result
    
    def _get_device_transports(self, devices: list) -> dict:
        """Get transport type for each device (nvme, sata, sas, md)."""
        result = {}
        for dev in devices:
            dev_name = dev.replace('/dev/', '')
            if dev_name.startswith('nvme'):
                result[dev] = 'nvme'
            elif dev_name.startswith('md'):
                result[dev] = 'md'
            elif dev_name.startswith('sd'):
                # Try to get actual transport from lsblk
                code, stdout, _ = self.run_command([
                    "lsblk", "-n", "-o", "TRAN", dev
                ], timeout=5)
                if code == 0 and stdout.strip():
                    result[dev] = stdout.strip().lower() or 'sata'
                else:
                    result[dev] = 'sata'  # default
            else:
                result[dev] = 'unknown'
        return result
    
    def _get_bcachefs_targets(self, mountpoint: str) -> dict:
        """
        Get bcachefs filesystem targets from show-super.
        
        Returns dict with:
            foreground: tier name for new writes
            background: tier name for aged data
            metadata: tier name for metadata
            promote: tier name for promoted hot data
        """
        targets = {}
        
        # Get source device from mountpoint
        code, stdout, _ = self.run_command(["findmnt", "-n", "-o", "SOURCE", mountpoint])
        if code != 0 or not stdout.strip():
            return targets
        
        # Get first device from potentially colon-separated list
        source = stdout.strip().split(':')[0].strip()
        if not source.startswith('/dev/'):
            return targets
        
        # Try show-super on the device (requires root, use full path for sudo NOPASSWD)
        bcachefs_path = "/usr/local/sbin/bcachefs"
        code, stdout, _ = self.run_command(["sudo", "-n", bcachefs_path, "show-super", source], timeout=10)
        
        if code != 0:
            return targets
        
        # Parse target lines
        for line in stdout.splitlines():
            line_lower = line.lower().strip()
            if '_target:' in line_lower:
                try:
                    key = line_lower.split('_target:')[0].strip().split()[-1]  # e.g., "foreground"
                    value = line.split(':')[1].strip()
                    if value and value.lower() != 'none':
                        targets[key] = value
                except (IndexError, ValueError):
                    continue
        
        return targets
    
    def _get_bcachefs_roles(self, tier: str, targets: dict) -> list:
        """
        Determine all roles of a bcachefs tier based on targets.
        
        A single tier can serve multiple purposes:
        - foreground: write cache (new writes land here)
        - promote: read cache (hot data promoted here)
        - metadata: filesystem metadata storage
        - background: cold/archive data storage
        
        Returns list of roles like ['foreground', 'metadata'] or ['data']
        """
        tier_lower = tier.lower()
        roles = []
        
        # Check which targets this tier serves
        if targets:
            if targets.get('foreground', '').lower() == tier_lower:
                roles.append('foreground')  # Write cache
            if targets.get('promote', '').lower() == tier_lower:
                roles.append('promote')  # Read cache
            if targets.get('metadata', '').lower() == tier_lower:
                roles.append('metadata')
            if targets.get('background', '').lower() == tier_lower:
                roles.append('data')
        
        # If we found roles from targets, return them
        if roles:
            return roles
        
        # Heuristic fallback based on common tier naming
        if tier_lower in ('nvme', 'ssd', 'cache', 'fg', 'fast', 'hot'):
            return ['cache']  # Generic cache when we can't determine specifics
        if tier_lower in ('meta', 'metadata'):
            return ['metadata']
        if tier_lower in ('hdd', 'bg', 'slow', 'cold', 'archive'):
            return ['data']
        
        return ['data']  # Default to data tier
    
    def _scan_zfs_pool(self, mountpoint: str) -> dict:
        """
        Scan ZFS pool for member devices with vdev type detection.
        
        ZFS structure:
        - data vdevs: mirror, raidz, raidz2, raidz3, or single disks
        - cache: L2ARC read cache (SSDs)
        - log: SLOG write log (fast SSDs/NVMe)
        - spare: hot spare disks
        
        Example zpool status output:
            config:
                NAME                                      STATE
                tank                                      ONLINE
                  mirror-0                                ONLINE
                    sda                                   ONLINE
                    sdb                                   ONLINE
                cache
                  nvme0n1                                 ONLINE
                logs
                  nvme1n1                                 ONLINE
        """
        result = {
            "type": "zfs", 
            "profile": "single", 
            "members": [], 
            "tiers": {},
            "data_profile": None,
            "metadata_profile": None,
        }
        
        if not self.command_exists("zpool"):
            return result
        
        # Get pool name from mountpoint
        code, stdout, _ = self.run_command(["zfs", "list", "-H", "-o", "name", mountpoint])
        if code != 0:
            return result
        
        pool_name = stdout.strip().split('/')[0] if stdout.strip() else None
        if not pool_name:
            return result
        
        # Get pool status
        code, stdout, _ = self.run_command(["zpool", "status", pool_name])
        if code != 0:
            return result
        
        # Parse zpool status for devices with role tracking
        in_config = False
        current_role = "data"  # Track current section: data, cache, logs, spare
        tiers: dict = {"data": [], "cache": [], "log": [], "spare": []}
        
        for line in stdout.splitlines():
            if 'config:' in line.lower():
                in_config = True
                continue
            if not in_config:
                continue
            
            parts = line.split()
            if not parts:
                continue
            
            potential_dev = parts[0].lower()
            
            # Check for vdev type headers (these change the current role)
            if potential_dev in ('cache', 'logs', 'log', 'spares', 'spare', 'special'):
                current_role = potential_dev.rstrip('s')  # normalize: logs->log, spares->spare
                continue
            
            # Check for data vdev types (ZFS native terminology)
            # mirror, raidz (single parity), raidz2 (double parity), raidz3 (triple parity)
            if potential_dev.startswith(('mirror', 'raidz')):
                vdev_type = potential_dev.split('-')[0]  # mirror-0 -> mirror
                result["profile"] = vdev_type
                # Set data profile using ZFS terminology
                if current_role == "data":
                    result["data_profile"] = vdev_type
                elif current_role == "special":
                    result["metadata_profile"] = vdev_type
                continue
            
            # Look for actual devices
            dev_name = parts[0]  # Use original case
            if dev_name.startswith('/dev/') or re.match(r'^(sd[a-z]+|nvme\d+n\d+)', dev_name):
                device = dev_name if dev_name.startswith('/dev/') else f"/dev/{dev_name}"
                result["members"].append({
                    "device": device,
                    "size": "Unknown",
                    "role": current_role,
                    "tier": current_role,
                })
                tiers[current_role].append(device)
        
        # Only include non-empty tiers
        result["tiers"] = {k: v for k, v in tiers.items() if v}
        
        # Set profile based on structure
        if len(result["tiers"]) > 1:
            result["profile"] = "tiered"
        
        return result
    
    def _scan_mdadm_array(self, device: str) -> dict:
        """Scan mdadm RAID array for member devices."""
        result = {"type": "mdadm", "profile": "unknown", "members": []}
        
        if not self.command_exists("mdadm"):
            return result
        
        code, stdout, _ = self.run_command(["mdadm", "--detail", device], timeout=10)
        if code != 0:
            return result
        
        for line in stdout.splitlines():
            line_stripped = line.strip()
            
            # Raid Level line: "Raid Level : raid1"
            if line_stripped.startswith('Raid Level'):
                parts = line_stripped.split(':')
                if len(parts) > 1:
                    result["profile"] = parts[1].strip()
            
            # Device lines at bottom: "0       8        1        0      active sync   /dev/sda1"
            if '/dev/' in line_stripped and ('active' in line_stripped or 'spare' in line_stripped):
                parts = line_stripped.split()
                device_path = None
                role = "data"
                for part in parts:
                    if part.startswith('/dev/'):
                        device_path = part
                    if part == 'spare':
                        role = "spare"
                
                if device_path:
                    result["members"].append({
                        "device": device_path,
                        "size": "Unknown",
                        "role": role,
                    })
        
        return result
    
    def _scan_bcache_device(self, device: str) -> dict:
        """
        Scan bcache device for backing and cache devices.
        
        bcache is a Linux kernel block layer cache:
        - backing device: The slow storage (HDD) exposed as /dev/bcacheN
        - cache device: The fast storage (SSD) used for caching
        
        bcache terminology:
        - writethrough: writes go to both cache and backing (safe)
        - writeback: writes go to cache first, then backing (fast)
        - writearound: writes bypass cache (for large sequential writes)
        
        sysfs paths:
        - /sys/block/bcacheN/bcache/backing_dev_name
        - /sys/block/bcacheN/bcache/cache/cache0 -> cache device
        - /sys/block/bcacheN/bcache/cache_mode
        """
        result = {
            "type": "bcache", 
            "profile": "tiered",  # bcache is always tiered (cache + backing)
            "members": [], 
            "tiers": {"cache": [], "backing": []},
            "data_profile": None,
            "metadata_profile": None,
        }
        
        dev_name = device.split('/')[-1]  # bcache0
        sysfs_base = f"/sys/block/{dev_name}/bcache"
        
        if not os.path.isdir(sysfs_base):
            return result
        
        # Get cache mode (writethrough, writeback, writearound)
        cache_mode_path = f"{sysfs_base}/cache_mode"
        if os.path.exists(cache_mode_path):
            try:
                with open(cache_mode_path) as f:
                    modes = f.read().strip()
                    # Format: "[writethrough] writeback writearound none"
                    # The active mode is in brackets
                    if '[' in modes and ']' in modes:
                        active = modes.split('[')[1].split(']')[0]
                        result["data_profile"] = active
            except:
                pass
        
        # Get backing device
        backing_path = f"{sysfs_base}/backing_dev_name"
        if os.path.exists(backing_path):
            try:
                with open(backing_path) as f:
                    backing_dev = f.read().strip()
                    if backing_dev:
                        backing_device = f"/dev/{backing_dev}" if not backing_dev.startswith('/dev/') else backing_dev
                        result["members"].append({
                            "device": backing_device,
                            "size": "Unknown",
                            "role": "backing",
                            "tier": "backing",
                        })
                        result["tiers"]["backing"].append(backing_device)
            except:
                pass
        
        # Get cache device - look in /sys/fs/bcache/*/cache0
        try:
            bcache_fs_path = "/sys/fs/bcache"
            if os.path.isdir(bcache_fs_path):
                for uuid_dir in os.listdir(bcache_fs_path):
                    cache_path = f"{bcache_fs_path}/{uuid_dir}/cache0"
                    if os.path.islink(cache_path):
                        cache_target = os.path.realpath(cache_path)
                        # Extract device name from path like /sys/devices/.../block/nvme0n1/...
                        if '/block/' in cache_target:
                            cache_dev = cache_target.split('/block/')[1].split('/')[0]
                            cache_device = f"/dev/{cache_dev}"
                            result["members"].append({
                                "device": cache_device,
                                "size": "Unknown",
                                "role": "cache",
                                "tier": "cache",
                            })
                            result["tiers"]["cache"].append(cache_device)
                            break
        except:
            pass
        
        return result
    
    def _scan_filesystems(self) -> List[Discovery]:
        """Scan mounted filesystems."""
        discoveries = []
        
        code, stdout, _ = self.run_command(["df", "-h", "--output=source,fstype,size,used,avail,pcent,target"])
        
        if code != 0:
            return discoveries
        
        lines = stdout.strip().splitlines()[1:]  # Skip header
        
        for line in lines:
            parts = line.split()
            if len(parts) < 7:
                continue
            
            source = parts[0]
            fstype = parts[1]
            size = parts[2]
            used = parts[3]
            avail = parts[4]
            percent_str = parts[5].rstrip('%')
            mountpoint = parts[6]
            
            # Skip pseudo filesystems
            if fstype in ['tmpfs', 'devtmpfs', 'squashfs', 'overlay', 'efivarfs']:
                continue
            if mountpoint.startswith('/snap/'):
                continue
            if source.startswith('/dev/loop'):
                continue
            
            try:
                percent = int(percent_str)
            except ValueError:
                percent = 0
            
            # Determine severity based on usage
            if percent >= 95:
                severity = DiscoverySeverity.CRITICAL
                status = f"{percent}% Full"
            elif percent >= 85:
                severity = DiscoverySeverity.WARNING
                status = f"{percent}% Used"
            else:
                severity = DiscoverySeverity.SUCCESS
                status = f"{percent}% Used"
            
            # Special handling for important mount points
            name = mountpoint.replace('/', '-').strip('-') or 'root'
            
            discovery_id = make_discovery_id(DiscoveryType.STORAGE, f"fs-{name}")
            
            # Extract parent disk from source device path
            parent_disk = self._get_parent_disk(source)
            
            # Get array/pool member devices for multi-disk filesystems
            array_info = self._get_array_info(mountpoint, fstype, source)
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.STORAGE,
                name=f"fs-{name}",
                title=f"{mountpoint} ({size})",
                description=f"{fstype} filesystem, {avail} free",
                icon="folder",
                severity=severity,
                status=status,
                status_detail=f"{used} used of {size}",
                source=source,
                data={
                    "source": source,
                    "device": source,  # Partition device (e.g., /dev/nvme0n1p2)
                    "parent_disk": parent_disk,  # Parent disk (e.g., /dev/nvme0n1)
                    "fstype": fstype,
                    "size": size,
                    "used": used,
                    "available": avail,
                    "percent": percent,
                    "mountpoint": mountpoint,
                    # Array/pool info for multi-disk filesystems
                    "array_type": array_info.get("type"),
                    "array_profile": array_info.get("profile"),
                    "data_profile": array_info.get("data_profile"),
                    "metadata_profile": array_info.get("metadata_profile"),
                    "array_members": array_info.get("members", []),
                    "array_tiers": array_info.get("tiers", {}),
                    # Tier target configuration (bcachefs/zfs)
                    "tier_targets": array_info.get("targets", {}),
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
    
    def _scan_unmounted_filesystems(self) -> List[Discovery]:
        """Scan for unmounted but available filesystems."""
        discoveries = []
        
        # Get all block devices with filesystem info using JSON for reliable parsing
        code, stdout, _ = self.run_command([
            "lsblk", "-J", "-o", "NAME,FSTYPE,LABEL,UUID,MOUNTPOINT"
        ])
        
        if code != 0:
            return discoveries
        
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return discoveries
        
        # Track mounted UUIDs to skip
        mounted_uuids: set = set()
        # Track unmounted filesystems grouped by UUID (for multi-device)
        unmounted_pools: Dict[str, Dict] = {}
        
        def process_device(device: dict):
            """Process a device and its children recursively."""
            name = device.get("name", "")
            fstype = device.get("fstype") or ""
            label = device.get("label") or ""
            uuid = device.get("uuid") or ""
            mountpoint = device.get("mountpoint") or ""
            
            # Process children first (partitions, etc.)
            for child in device.get("children", []):
                process_device(child)
            
            # Skip certain types
            if not fstype or fstype in ['linux_raid_member', 'swap', 'squashfs', 'vfat']:
                return
            if name.startswith('loop'):
                return
            
            # If mounted, record UUID
            if mountpoint and not mountpoint.startswith('['):
                if uuid:
                    mounted_uuids.add(uuid)
                return
            
            # Unmounted filesystem - group by UUID for multi-device
            if uuid:
                if uuid not in unmounted_pools:
                    unmounted_pools[uuid] = {
                        "uuid": uuid,
                        "label": label,
                        "fstype": fstype,
                        "devices": [],
                    }
                unmounted_pools[uuid]["devices"].append(f"/dev/{name}")
                # Use label from first device with a label
                if label and not unmounted_pools[uuid]["label"]:
                    unmounted_pools[uuid]["label"] = label
        
        # Process all block devices
        for device in data.get("blockdevices", []):
            process_device(device)
        
        # Remove any pools whose UUID is actually mounted somewhere
        for uuid in list(unmounted_pools.keys()):
            if uuid in mounted_uuids:
                del unmounted_pools[uuid]
        
        # Get total size for each pool
        for uuid, pool in unmounted_pools.items():
            # Calculate total size from devices
            total_bytes = 0
            for dev in pool["devices"]:
                code, size_out, _ = self.run_command(["lsblk", "-bno", "SIZE", dev])
                if code == 0 and size_out.strip():
                    try:
                        total_bytes += int(size_out.strip())
                    except ValueError:
                        pass
            
            # Format size
            if total_bytes >= 1024**4:
                size_str = f"{total_bytes / 1024**4:.1f}T"
            elif total_bytes >= 1024**3:
                size_str = f"{total_bytes / 1024**3:.1f}G"
            elif total_bytes >= 1024**2:
                size_str = f"{total_bytes / 1024**2:.1f}M"
            else:
                size_str = f"{total_bytes / 1024:.1f}K"
            
            pool["size"] = size_str
            pool["size_bytes"] = total_bytes
            
            # Create discovery
            label = pool["label"] or f"Unnamed {pool['fstype']}"
            fstype = pool["fstype"]
            device_count = len(pool["devices"])
            
            # Use label as the name, sanitized
            name_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', label.lower())
            discovery_id = make_discovery_id(DiscoveryType.STORAGE, f"unmounted-{name_slug}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.STORAGE,
                name=f"unmounted-{name_slug}",
                title=f"{label} ({size_str})",
                description=f"Unmounted {fstype} with {device_count} device{'s' if device_count > 1 else ''}",
                icon="hard-drive-download",  # Indicates action needed
                severity=DiscoverySeverity.INFO,
                status="Unmounted",
                status_detail=f"{device_count} device{'s' if device_count > 1 else ''} available",
                source=pool["devices"][0],
                data={
                    "uuid": uuid,
                    "label": label,
                    "fstype": fstype,
                    "size": size_str,
                    "size_bytes": total_bytes,
                    "devices": pool["devices"],
                    "device_count": device_count,
                    "mounted": False,
                    "mountpoint": None,
                },
                actions=[
                    DiscoveryAction(
                        id="mount",
                        label="Mount",
                        icon="folder-plus",
                    ),
                    DiscoveryAction(
                        id="chat",
                        label="Chat",
                        icon="message-circle",
                    ),
                ],
                chat_context=f"This is an unmounted {fstype} filesystem labeled '{label}'. "
                            f"Size: {size_str}. Devices: {', '.join(pool['devices'][:3])}{'...' if device_count > 3 else ''}.",
            ))
        
        return discoveries
