"""
Sharing Scanner - Discovers network shares, VPN peers, and cloud mounts.

Covers:
- NFS mounts and exports
- SMB/CIFS mounts and Samba exports
- Tailscale peers and status
- WireGuard peers
- rclone cloud mounts

Based on Phase 17 research: docs/Phase17/SHARING-TAB-RESEARCH.md
"""

from __future__ import annotations
import json
import re
from typing import List, Optional
from pathlib import Path

from .base import BaseScanner
from ..schema import (
    Discovery, 
    DiscoveryType, 
    DiscoverySeverity,
    make_discovery_id,
)


class SharingScanner(BaseScanner):
    """
    Scanner for network file sharing.
    
    Discovers:
    - NFS mounts and exports
    - SMB/CIFS mounts and Samba shares
    - Tailscale peers
    - WireGuard peers
    - Cloud mounts (rclone, etc.)
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.SHARING
    
    def scan(self) -> List[Discovery]:
        """Scan system for sharing resources."""
        discoveries = []
        
        # NFS
        discoveries.extend(self._scan_nfs_mounts())
        discoveries.extend(self._scan_nfs_exports())
        
        # SMB/CIFS
        discoveries.extend(self._scan_cifs_mounts())
        discoveries.extend(self._scan_samba_exports())
        
        # VPN peers
        discoveries.extend(self._scan_tailscale())
        discoveries.extend(self._scan_tailscale_drives())
        discoveries.extend(self._scan_wireguard())
        
        # Cloud mounts
        discoveries.extend(self._scan_rclone_mounts())
        discoveries.extend(self._scan_fuse_mounts())
        
        self.logger.info(f"Found {len(discoveries)} sharing items")
        return discoveries
    
    # ─────────────────────────────────────────────────────────────
    # NFS Scanning
    # ─────────────────────────────────────────────────────────────
    
    def _scan_nfs_mounts(self) -> List[Discovery]:
        """Scan for mounted NFS shares."""
        discoveries = []
        
        # Get NFS mounts from /proc/mounts
        code, stdout, _ = self.run_command(['mount', '-t', 'nfs,nfs4'])
        if code != 0 or not stdout.strip():
            return discoveries
        
        for line in stdout.strip().splitlines():
            # Format: server:/export /mount/point type options
            parts = line.split()
            if len(parts) < 4:
                continue
            
            source = parts[0]
            mount_point = parts[2]
            fs_type = parts[4] if len(parts) > 4 else 'nfs'
            options = parts[5] if len(parts) > 5 else ''
            
            # Parse server and export path
            if ':' in source:
                server, export_path = source.split(':', 1)
            else:
                server = 'unknown'
                export_path = source
            
            # Check connectivity by testing mount point
            is_connected = Path(mount_point).is_dir()
            
            # Determine options
            is_rw = 'rw' in options
            nfs_version = '4' if 'nfs4' in fs_type else '3'
            
            discovery_id = make_discovery_id(DiscoveryType.SHARING, f"nfs-mount-{mount_point}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SHARING,
                name=f"nfs-mount-{mount_point.replace('/', '-')}",
                title=f"{mount_point}",
                description=f"NFS{nfs_version} mount from {server}",
                severity=DiscoverySeverity.SUCCESS if is_connected else DiscoverySeverity.WARNING,
                status='Connected' if is_connected else 'Disconnected',
                data={
                    'share_type': 'nfs-mount',
                    'server': server,
                    'export_path': export_path,
                    'mount_point': mount_point,
                    'fs_type': fs_type,
                    'options': options,
                    'nfs_version': nfs_version,
                    'read_write': is_rw,
                    'connected': is_connected,
                },
                icon='hard-drive',
            ))
        
        return discoveries
    
    def _scan_nfs_exports(self) -> List[Discovery]:
        """Scan for NFS exports from this machine."""
        discoveries = []
        
        # Check if NFS server is installed
        if not self.file_exists('/etc/exports'):
            return discoveries
        
        # Read exports file
        content = self.read_file('/etc/exports')
        if not content:
            return discoveries
        
        # Also try exportfs for active exports
        code, exportfs_out, _ = self.run_command(['exportfs', '-v'])
        active_exports = set()
        if code == 0:
            for line in exportfs_out.strip().splitlines():
                if line.strip():
                    parts = line.split()
                    if parts:
                        active_exports.add(parts[0])
        
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Format: /path/to/export client(options) client2(options)
            parts = line.split()
            if not parts:
                continue
            
            export_path = parts[0]
            clients = ' '.join(parts[1:]) if len(parts) > 1 else '*'
            
            is_active = export_path in active_exports
            
            discovery_id = make_discovery_id(DiscoveryType.SHARING, f"nfs-export-{export_path}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SHARING,
                name=f"nfs-export-{export_path.replace('/', '-')}",
                title=f"Export: {export_path}",
                description=f"NFS export to {clients[:50]}",
                severity=DiscoverySeverity.SUCCESS if is_active else DiscoverySeverity.INFO,
                status='Active' if is_active else 'Configured',
                data={
                    'share_type': 'nfs-export',
                    'export_path': export_path,
                    'clients': clients,
                    'active': is_active,
                    'config_path': '/etc/exports',
                },
                icon='share-2',
            ))
        
        return discoveries
    
    # ─────────────────────────────────────────────────────────────
    # SMB/CIFS Scanning
    # ─────────────────────────────────────────────────────────────
    
    def _scan_cifs_mounts(self) -> List[Discovery]:
        """Scan for mounted CIFS/SMB shares."""
        discoveries = []
        
        code, stdout, _ = self.run_command(['mount', '-t', 'cifs'])
        if code != 0 or not stdout.strip():
            return discoveries
        
        for line in stdout.strip().splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            
            source = parts[0]  # //server/share
            mount_point = parts[2]
            options = parts[5] if len(parts) > 5 else ''
            
            # Parse server and share
            match = re.match(r'//([^/]+)/(.+)', source)
            if match:
                server = match.group(1)
                share_name = match.group(2)
            else:
                server = 'unknown'
                share_name = source
            
            is_connected = Path(mount_point).is_dir()
            is_rw = 'rw' in options
            
            # Check for credentials
            has_creds = 'credentials=' in options or 'username=' in options
            
            discovery_id = make_discovery_id(DiscoveryType.SHARING, f"smb-mount-{mount_point}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SHARING,
                name=f"smb-mount-{mount_point.replace('/', '-')}",
                title=f"{mount_point}",
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
                    'has_credentials': has_creds,
                    'connected': is_connected,
                },
                icon='hard-drive',
            ))
        
        return discoveries
    
    def _scan_samba_exports(self) -> List[Discovery]:
        """Scan for Samba shares exported by this machine."""
        discoveries = []
        
        smb_conf = '/etc/samba/smb.conf'
        if not self.file_exists(smb_conf):
            return discoveries
        
        # Use testparm to get parsed config
        code, stdout, _ = self.run_command(['testparm', '-s'], timeout=5)
        if code != 0:
            return discoveries
        
        # Parse shares from testparm output
        current_share = None
        share_config = {}
        
        for line in stdout.splitlines():
            line = line.strip()
            
            # New section
            if line.startswith('[') and line.endswith(']'):
                # Save previous share
                if current_share and current_share not in ('global', 'printers', 'print$'):
                    self._add_samba_share(discoveries, current_share, share_config)
                
                current_share = line[1:-1]
                share_config = {}
            elif '=' in line and current_share:
                key, value = line.split('=', 1)
                share_config[key.strip()] = value.strip()
        
        # Don't forget last share
        if current_share and current_share not in ('global', 'printers', 'print$'):
            self._add_samba_share(discoveries, current_share, share_config)
        
        return discoveries
    
    def _add_samba_share(self, discoveries: list, name: str, config: dict):
        """Add a Samba share to discoveries."""
        path = config.get('path', '')
        comment = config.get('comment', '')
        guest_ok = config.get('guest ok', 'no').lower() == 'yes'
        read_only = config.get('read only', 'yes').lower() == 'yes'
        browseable = config.get('browseable', 'yes').lower() == 'yes'
        
        # Check if Samba is running
        code, _, _ = self.run_command(['systemctl', 'is-active', 'smbd'])
        is_active = code == 0
        
        discovery_id = make_discovery_id(DiscoveryType.SHARING, f"smb-export-{name}")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SHARING,
            name=f"smb-export-{name}",
            title=f"Share: {name}",
            description=comment or f"Samba share at {path}",
            severity=DiscoverySeverity.SUCCESS if is_active else DiscoverySeverity.INFO,
            status='Active' if is_active else 'Configured',
            data={
                'share_type': 'smb-export',
                'share_name': name,
                'path': path,
                'comment': comment,
                'guest_ok': guest_ok,
                'read_only': read_only,
                'browseable': browseable,
                'active': is_active,
                'config_path': '/etc/samba/smb.conf',
            },
            icon='share-2',
        ))
    
    # ─────────────────────────────────────────────────────────────
    # Tailscale Scanning
    # ─────────────────────────────────────────────────────────────
    
    def _scan_tailscale(self) -> List[Discovery]:
        """Scan Tailscale peers and status."""
        discoveries = []
        
        # Check if tailscale is installed
        if not self.command_exists('tailscale'):
            return discoveries
        
        # Get status JSON
        code, stdout, _ = self.run_command(['tailscale', 'status', '--json'])
        if code != 0:
            return discoveries
        
        try:
            status = json.loads(stdout)
        except json.JSONDecodeError:
            return discoveries
        
        # Get self info
        self_node = status.get('Self', {})
        self_hostname = self_node.get('HostName', 'this-machine')
        
        # Get peers
        peers = status.get('Peer', {})
        
        for peer_id, peer in peers.items():
            hostname = peer.get('HostName', 'unknown')
            dns_name = peer.get('DNSName', '')
            os_name = peer.get('OS', '')
            online = peer.get('Online', False)
            
            # Get IPs
            ips = peer.get('TailscaleIPs', [])
            primary_ip = ips[0] if ips else ''
            
            # Exit node info
            is_exit_node = peer.get('ExitNode', False)
            
            discovery_id = make_discovery_id(DiscoveryType.SHARING, f"tailscale-{hostname}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SHARING,
                name=f"tailscale-{hostname}",
                title=hostname,
                description=f"Tailscale peer ({os_name})" if os_name else "Tailscale peer",
                severity=DiscoverySeverity.SUCCESS if online else DiscoverySeverity.INFO,
                status='Online' if online else 'Offline',
                data={
                    'share_type': 'tailscale-peer',
                    'hostname': hostname,
                    'dns_name': dns_name.rstrip('.'),
                    'os': os_name,
                    'ip': primary_ip,
                    'all_ips': ips,
                    'online': online,
                    'is_exit_node': is_exit_node,
                    'peer_id': peer_id,
                },
                icon='globe' if online else 'globe',
            ))
        
        return discoveries
    
    def _scan_tailscale_drives(self) -> List[Discovery]:
        """Scan for Tailscale Drive shares (Taildrive/Tailshare)."""
        discoveries = []
        
        if not self.command_exists('tailscale'):
            return discoveries
        
        # Get local Tailscale Drive shares
        code, stdout, _ = self.run_command(['tailscale', 'drive', 'list'])
        if code != 0:
            return discoveries
        
        # Parse the output - format: name, path, as (user)
        lines = stdout.strip().splitlines()
        
        # Skip header lines
        for line in lines:
            # Skip header and separator lines
            if line.startswith('name') or line.startswith('-') or not line.strip():
                continue
            
            # Parse columns (they're space/tab separated)
            parts = line.split()
            if len(parts) >= 2:
                share_name = parts[0]
                share_path = parts[1]
                share_user = parts[2] if len(parts) > 2 else ''
                
                # Check if path exists
                is_active = Path(share_path).exists() if share_path else False
                
                discovery_id = make_discovery_id(DiscoveryType.SHARING, f"taildrive-{share_name}")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.SHARING,
                    name=f"taildrive-{share_name}",
                    title=f"Tailshare: {share_name}",
                    description=f"Tailscale Drive share at {share_path}",
                    severity=DiscoverySeverity.SUCCESS if is_active else DiscoverySeverity.WARNING,
                    status='Shared' if is_active else 'Path Missing',
                    data={
                        'share_type': 'taildrive',
                        'share_name': share_name,
                        'path': share_path,
                        'user': share_user,
                        'active': is_active,
                    },
                    icon='share-2',
                ))
        
        # Also check for remote Tailscale Drive mounts (WebDAV)
        # These would appear as fuse mounts at /tmp/taildrive or similar
        code, mount_out, _ = self.run_command(['mount'])
        if code == 0:
            for line in mount_out.splitlines():
                if 'taildrive' in line.lower() or '100.100.100.100' in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        source = parts[0]
                        mount_point = parts[2]
                        
                        discovery_id = make_discovery_id(DiscoveryType.SHARING, f"taildrive-mount-{mount_point}")
                        
                        discoveries.append(Discovery(
                            id=discovery_id,
                            type=DiscoveryType.SHARING,
                            name=f"taildrive-mount-{mount_point.replace('/', '-')}",
                            title=f"{mount_point}",
                            description=f"Tailscale Drive mount: {source}",
                            severity=DiscoverySeverity.SUCCESS,
                            status='Mounted',
                            data={
                                'share_type': 'taildrive-mount',
                                'source': source,
                                'mount_point': mount_point,
                                'connected': True,
                            },
                            icon='hard-drive',
                        ))
        
        return discoveries
    
    # ─────────────────────────────────────────────────────────────
    # WireGuard Scanning
    # ─────────────────────────────────────────────────────────────
    
    def _scan_wireguard(self) -> List[Discovery]:
        """Scan WireGuard interfaces and peers."""
        discoveries = []
        
        if not self.command_exists('wg'):
            return discoveries
        
        # Get WireGuard show output
        code, stdout, _ = self.run_command(['wg', 'show', 'all'])
        if code != 0 or not stdout.strip():
            return discoveries
        
        current_interface = None
        current_peer = None
        peer_data = {}
        
        for line in stdout.splitlines():
            line = line.strip()
            
            if line.startswith('interface:'):
                current_interface = line.split(':')[1].strip()
            elif line.startswith('peer:'):
                # Save previous peer
                if current_peer and current_interface:
                    self._add_wireguard_peer(discoveries, current_interface, current_peer, peer_data)
                
                current_peer = line.split(':')[1].strip()
                peer_data = {}
            elif ':' in line and current_peer:
                key, value = line.split(':', 1)
                peer_data[key.strip()] = value.strip()
        
        # Save last peer
        if current_peer and current_interface:
            self._add_wireguard_peer(discoveries, current_interface, current_peer, peer_data)
        
        return discoveries
    
    def _add_wireguard_peer(self, discoveries: list, interface: str, pubkey: str, data: dict):
        """Add a WireGuard peer to discoveries."""
        endpoint = data.get('endpoint', '')
        allowed_ips = data.get('allowed ips', '')
        latest_handshake = data.get('latest handshake', '')
        transfer = data.get('transfer', '')
        
        # Consider online if handshake was recent
        is_online = bool(latest_handshake and latest_handshake != 'Never')
        
        # Short key for display
        short_key = pubkey[:8] + '...'
        
        discovery_id = make_discovery_id(DiscoveryType.SHARING, f"wg-{interface}-{pubkey[:8]}")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SHARING,
            name=f"wg-{interface}-{pubkey[:8]}",
            title=f"WG: {short_key}",
            description=f"WireGuard peer on {interface}",
            severity=DiscoverySeverity.SUCCESS if is_online else DiscoverySeverity.INFO,
            status='Connected' if is_online else 'Configured',
            data={
                'share_type': 'wireguard-peer',
                'interface': interface,
                'public_key': pubkey,
                'endpoint': endpoint,
                'allowed_ips': allowed_ips,
                'latest_handshake': latest_handshake,
                'transfer': transfer,
                'online': is_online,
            },
            icon='shield',
        ))
    
    # ─────────────────────────────────────────────────────────────
    # Cloud Mount Scanning
    # ─────────────────────────────────────────────────────────────
    
    def _scan_rclone_mounts(self) -> List[Discovery]:
        """Scan for rclone FUSE mounts."""
        discoveries = []
        
        # Check for rclone mount processes
        code, stdout, _ = self.run_command(['pgrep', '-a', 'rclone'])
        if code != 0 or 'mount' not in stdout:
            return discoveries
        
        # Also check mount output
        code, mount_out, _ = self.run_command(['mount', '-t', 'fuse.rclone'])
        if code != 0:
            return discoveries
        
        for line in mount_out.strip().splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            
            source = parts[0]  # remote:path
            mount_point = parts[2]
            
            # Parse remote name
            if ':' in source:
                remote = source.split(':')[0]
            else:
                remote = source
            
            is_connected = Path(mount_point).is_dir()
            
            discovery_id = make_discovery_id(DiscoveryType.SHARING, f"rclone-{mount_point}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SHARING,
                name=f"rclone-{mount_point.replace('/', '-')}",
                title=f"{mount_point}",
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
        """Scan for other FUSE cloud mounts (s3fs, gcsfuse, sshfs)."""
        discoveries = []
        
        fuse_types = {
            'fuse.sshfs': ('SSHFS', 'server'),
            'fuse.s3fs': ('S3', 'cloud'),
            'fuse.gcsfuse': ('GCS', 'cloud'),
            'fuse.google-drive-ocamlfuse': ('Google Drive', 'cloud'),
        }
        
        code, stdout, _ = self.run_command(['mount'])
        if code != 0:
            return discoveries
        
        for line in stdout.splitlines():
            for fuse_type, (label, icon) in fuse_types.items():
                if fuse_type in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        source = parts[0]
                        mount_point = parts[2]
                        
                        is_connected = Path(mount_point).is_dir()
                        
                        discovery_id = make_discovery_id(
                            DiscoveryType.SHARING, 
                            f"{fuse_type.replace('.', '-')}-{mount_point}"
                        )
                        
                        discoveries.append(Discovery(
                            id=discovery_id,
                            type=DiscoveryType.SHARING,
                            name=f"{label.lower()}-{mount_point.replace('/', '-')}",
                            title=f"{mount_point}",
                            description=f"{label} mount: {source}",
                            severity=DiscoverySeverity.SUCCESS if is_connected else DiscoverySeverity.WARNING,
                            status='Mounted' if is_connected else 'Disconnected',
                            data={
                                'share_type': fuse_type,
                                'label': label,
                                'source': source,
                                'mount_point': mount_point,
                                'connected': is_connected,
                            },
                            icon=icon,
                        ))
        
        return discoveries
