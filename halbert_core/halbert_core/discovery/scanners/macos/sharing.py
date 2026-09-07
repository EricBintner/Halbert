# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
macOS Sharing Scanner - Discovers network shares, VPN peers, and cloud mounts.

macOS equivalent of the Linux SharingScanner. Inherits cross-platform
scanning logic (Tailscale, WireGuard, rclone, FUSE) from SharingScanner
and overrides the platform-specific parts:

- SMB mounts via `mount -t smbfs` (macOS uses smbfs, not cifs)
- NFS mounts via `mount -t nfs`
- macOS sharing services via launchctl (sharingd, screensharing, etc.)
- macOS file sharing via `sharing -l` (when available without root)
- Samba exports are not standard on macOS (skipped)
"""

from __future__ import annotations
from typing import List
from pathlib import Path
import re

from ..sharing import SharingScanner
from ...schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    make_discovery_id,
)


class MacSharingScanner(SharingScanner):
    """
    Scanner for network file sharing on macOS.

    Inherits Tailscale, WireGuard, rclone, and FUSE scanning from
    SharingScanner (these tools work identically on macOS). Overrides
    NFS/SMB mount scanning and adds macOS-native sharing service discovery.
    """

    @property
    def name(self) -> str:
        return "MacSharingScanner"

    def is_available(self) -> bool:
        """Check if this scanner can run on macOS."""
        # Always available on macOS — mount and launchctl always exist
        return True

    def scan(self) -> List[Discovery]:
        """Scan system for sharing resources on macOS."""
        discoveries = []

        # macOS-native sharing services (launchctl)
        discoveries.extend(self._scan_macos_sharing_services())

        # Mounted shares
        discoveries.extend(self._scan_nfs_mounts())
        discoveries.extend(self._scan_smb_mounts())

        # VPN peers (cross-platform, inherited)
        discoveries.extend(self._scan_tailscale())
        discoveries.extend(self._scan_tailscale_drives())
        discoveries.extend(self._scan_wireguard())

        # Cloud mounts (cross-platform, inherited)
        discoveries.extend(self._scan_rclone_mounts())
        discoveries.extend(self._scan_fuse_mounts())

        self.logger.info(f"Found {len(discoveries)} sharing items on macOS")
        return discoveries

    # ─────────────────────────────────────────────────────────────
    # macOS-native sharing services (launchctl)
    # ─────────────────────────────────────────────────────────────

    # Known macOS sharing services and their launchd identifiers.
    # These are checked via `launchctl list` (no root required).
    _MACOS_SHARING_SERVICES = {
        'com.apple.screensharing': {
            'label': 'Screen Sharing',
            'description': 'Remote screen control via VNC',
            'icon': 'monitor',
        },
        'com.apple.sharingd': {
            'label': 'File Sharing (AirDrop)',
            'description': 'AirDrop and local file sharing',
            'icon': 'share-2',
        },
        'com.apple.smbd': {
            'label': 'SMB File Sharing',
            'description': 'Windows file sharing (SMB)',
            'icon': 'share-2',
        },
        'com.apple.nfsd': {
            'label': 'NFS File Sharing',
            'description': 'NFS export service',
            'icon': 'share-2',
        },
        'com.apple.RemoteDesktop': {
            'label': 'Remote Management',
            'description': 'Apple Remote Desktop management',
            'icon': 'monitor',
        },
        'com.apple.RemoteLogin': {
            'label': 'Remote Login (SSH)',
            'description': 'SSH remote login service',
            'icon': 'terminal',
        },
        'com.apple.AppleFileServer': {
            'label': 'AFP File Sharing',
            'description': 'Apple Filing Protocol file sharing (legacy)',
            'icon': 'share-2',
        },
        'com.apple.amp.mediasharingd': {
            'label': 'Media Sharing',
            'description': 'Music and media sharing via Home Sharing',
            'icon': 'music',
        },
        'com.apple.BluetoothSharingd': {
            'label': 'Bluetooth Sharing',
            'description': 'Bluetooth file sharing',
            'icon': 'bluetooth',
        },
        'com.apple.PrinterProxy': {
            'label': 'Printer Sharing',
            'description': 'Shared printer access',
            'icon': 'printer',
        },
    }

    def _scan_macos_sharing_services(self) -> List[Discovery]:
        """Discover macOS sharing services via launchctl list."""
        discoveries = []

        code, stdout, _ = self.run_command(['launchctl', 'list'])
        if code != 0:
            return discoveries

        # Parse launchctl list output: PID\tStatus\tLabel
        active_labels = set()
        for line in stdout.splitlines():
            parts = line.split('\t')
            if len(parts) >= 3:
                label = parts[2].strip()
                pid = parts[0].strip()
                # A service is running if it has a PID (not '-')
                if pid and pid != '-':
                    active_labels.add(label)

        for service_id, info in self._MACOS_SHARING_SERVICES.items():
            is_active = service_id in active_labels

            discovery_id = make_discovery_id(
                DiscoveryType.SHARING, f"macos-share-{service_id}"
            )

            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SHARING,
                name=f"macos-share-{service_id.split('.')[-1]}",
                title=info['label'],
                description=info['description'],
                severity=DiscoverySeverity.SUCCESS if is_active else DiscoverySeverity.INFO,
                status='Active' if is_active else 'Available',
                data={
                    'share_type': 'macos-service',
                    'service_id': service_id,
                    'active': is_active,
                },
                icon=info['icon'],
            ))

        return discoveries

    # ─────────────────────────────────────────────────────────────
    # NFS mounts (macOS: `mount -t nfs`)
    # ─────────────────────────────────────────────────────────────

    def _scan_nfs_mounts(self) -> List[Discovery]:
        """Scan for mounted NFS shares on macOS."""
        discoveries = []

        code, stdout, _ = self.run_command(['mount', '-t', 'nfs'])
        if code != 0 or not stdout.strip():
            return discoveries

        for line in stdout.strip().splitlines():
            # macOS mount output format:
            # server:/export on /mount/point (nfs, ...)
            m = re.match(r'(\S+) on (\S+) \(([^)]+)\)', line)
            if not m:
                continue

            source = m.group(1)
            mount_point = m.group(2)
            options = m.group(3)

            if ':' in source:
                server, export_path = source.split(':', 1)
            else:
                server = 'unknown'
                export_path = source

            is_connected = Path(mount_point).is_dir()
            is_rw = 'rw' in options

            discovery_id = make_discovery_id(
                DiscoveryType.SHARING, f"nfs-mount-{mount_point}"
            )

            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SHARING,
                name=f"nfs-mount-{mount_point.replace('/', '-')}",
                title=mount_point,
                description=f"NFS mount from {server}",
                severity=DiscoverySeverity.SUCCESS if is_connected else DiscoverySeverity.WARNING,
                status='Connected' if is_connected else 'Disconnected',
                data={
                    'share_type': 'nfs-mount',
                    'server': server,
                    'export_path': export_path,
                    'mount_point': mount_point,
                    'options': options,
                    'read_write': is_rw,
                    'connected': is_connected,
                },
                icon='hard-drive',
            ))

        return discoveries

    # ─────────────────────────────────────────────────────────────
    # SMB mounts (macOS: `mount -t smbfs`)
    # ─────────────────────────────────────────────────────────────

    def _scan_smb_mounts(self) -> List[Discovery]:
        """Scan for mounted SMB shares on macOS."""
        discoveries = []

        code, stdout, _ = self.run_command(['mount', '-t', 'smbfs'])
        if code != 0 or not stdout.strip():
            return discoveries

        for line in stdout.strip().splitlines():
            # macOS mount output: //user@server/share on /mount/point (smbfs, ...)
            m = re.match(r'(\S+) on (\S+) \(([^)]+)\)', line)
            if not m:
                continue

            source = m.group(1)
            mount_point = m.group(2)
            options = m.group(3)

            # Parse server and share from //user@server/share or //server/share
            match = re.match(r'//(?:([^@]+)@)?([^/]+)/(.+)', source)
            if match:
                user = match.group(1) or ''
                server = match.group(2)
                share_name = match.group(3)
            else:
                server = 'unknown'
                share_name = source

            is_connected = Path(mount_point).is_dir()
            is_rw = 'rw' in options

            discovery_id = make_discovery_id(
                DiscoveryType.SHARING, f"smb-mount-{mount_point}"
            )

            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SHARING,
                name=f"smb-mount-{mount_point.replace('/', '-')}",
                title=mount_point,
                description=f"SMB share from {server}",
                severity=DiscoverySeverity.SUCCESS if is_connected else DiscoverySeverity.WARNING,
                status='Connected' if is_connected else 'Disconnected',
                data={
                    'share_type': 'smb-mount',
                    'server': server,
                    'share_name': share_name,
                    'mount_point': mount_point,
                    'options': options,
                    'read_write': is_rw,
                    'has_credentials': bool(user),
                    'connected': is_connected,
                },
                icon='hard-drive',
            ))

        return discoveries

    # ─────────────────────────────────────────────────────────────
    # Cloud mounts — macOS overrides (macFUSE/osxfuse, not Linux fuse.*)
    # ─────────────────────────────────────────────────────────────

    def _scan_rclone_mounts(self) -> List[Discovery]:
        """Scan for rclone FUSE mounts on macOS.

        macOS uses macFUSE/osxfuse, not Linux's fuse.rclone.
        We check mount output for rclone-related osxfuse entries.
        """
        discoveries = []

        # Check for rclone mount processes
        code, stdout, _ = self.run_command(['pgrep', '-a', 'rclone'])
        if code != 0 or 'mount' not in stdout:
            return discoveries

        # On macOS, rclone mounts show up in `mount` output with osxfuse
        code, mount_out, _ = self.run_command(['mount'])
        if code != 0:
            return discoveries

        for line in mount_out.splitlines():
            if 'rclone' not in line.lower() and 'osxfuse' not in line.lower():
                continue
            # macOS mount format: rclone:remote on /mount/point (osxfuse, ...)
            m = re.match(r'(\S+) on (\S+) \(([^)]+)\)', line)
            if not m:
                continue

            source = m.group(1)
            mount_point = m.group(2)

            if ':' in source:
                remote = source.split(':')[0]
            else:
                remote = source

            is_connected = Path(mount_point).is_dir()

            discovery_id = make_discovery_id(
                DiscoveryType.SHARING, f"rclone-{mount_point}"
            )

            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SHARING,
                name=f"rclone-{mount_point.replace('/', '-')}",
                title=mount_point,
                description=f"rclone mount: {remote}",
                severity=DiscoverySeverity.SUCCESS if is_connected else DiscoverySeverity.WARNING,
                status='Mounted' if is_connected else 'Disconnected',
                data={
                    'share_type': 'rclone-mount',
                    'remote': remote,
                    'source': source,
                    'mount_point': mount_point,
                    'connected': is_connected,
                },
                icon='cloud',
            ))

        return discoveries

    def _scan_fuse_mounts(self) -> List[Discovery]:
        """Scan for other FUSE cloud mounts on macOS (sshfs, etc.).

        macOS uses macFUSE/osxfuse filesystem type, not Linux fuse.sshfs etc.
        """
        discoveries = []

        # macOS FUSE type labels
        fuse_labels = {
            'sshfs': ('SSHFS', 'server'),
            's3fs': ('S3', 'cloud'),
            'gcsfuse': ('GCS', 'cloud'),
            'google-drive': ('Google Drive', 'cloud'),
            'rclone': ('rclone', 'cloud'),
        }

        code, stdout, _ = self.run_command(['mount'])
        if code != 0:
            return discoveries

        for line in stdout.splitlines():
            if 'osxfuse' not in line.lower() and 'macfuse' not in line.lower():
                continue

            m = re.match(r'(\S+) on (\S+) \(([^)]+)\)', line)
            if not m:
                continue

            source = m.group(1)
            mount_point = m.group(2)
            options = m.group(3)

            # Identify the FUSE subtype from the source or options
            label = 'FUSE'
            icon_name = 'cloud'
            source_lower = source.lower()
            for key, (lbl, icn) in fuse_labels.items():
                if key in source_lower:
                    label = lbl
                    icon_name = icn
                    break

            is_connected = Path(mount_point).is_dir()

            discovery_id = make_discovery_id(
                DiscoveryType.SHARING,
                f"osxfuse-{mount_point}"
            )

            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SHARING,
                name=f"{label.lower()}-{mount_point.replace('/', '-')}",
                title=mount_point,
                description=f"{label} mount: {source}",
                severity=DiscoverySeverity.SUCCESS if is_connected else DiscoverySeverity.WARNING,
                status='Mounted' if is_connected else 'Disconnected',
                data={
                    'share_type': f'osxfuse-{label.lower()}',
                    'label': label,
                    'source': source,
                    'mount_point': mount_point,
                    'connected': is_connected,
                },
                icon=icon_name,
            ))

        return discoveries
