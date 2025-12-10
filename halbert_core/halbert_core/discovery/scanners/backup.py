"""
Backup Scanner - Discover backup configurations on the system.

Implements Phase 9 research from docs/Phase9/deep-dives/02-backups-discovery.md

Discovers:
- rsync scripts/cron jobs
- rsnapshot configurations
- borg backup repositories
- restic repositories
- rclone configurations
- Timeshift snapshots
- Btrfs snapshots (snapper, btrbk)
- ZFS snapshots (zfs-auto-snapshot, sanoid)
- tar backup scripts
- systemd timer-based backups
- Back In Time
- Deja Dup
- Kopia
"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import json
import os
import re

from .base import BaseScanner
from ..schema import (
    Discovery, 
    DiscoveryType, 
    DiscoverySeverity,
    backup_discovery,
)


class BackupScanner(BaseScanner):
    """
    Scanner for backup configurations.
    
    Searches multiple locations:
    1. User crontab
    2. System crontabs (/etc/cron.*)
    3. systemd timers
    4. Tool-specific configs (borg, restic, rclone)
    5. Timeshift
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.BACKUP
    
    def scan(self) -> List[Discovery]:
        """Scan system for backup configurations."""
        discoveries = []
        
        # Scan different sources
        discoveries.extend(self._scan_user_crontab())
        discoveries.extend(self._scan_system_crontabs())
        discoveries.extend(self._scan_systemd_timers())
        discoveries.extend(self._scan_borg())
        discoveries.extend(self._scan_restic())
        discoveries.extend(self._scan_rclone())
        discoveries.extend(self._scan_timeshift())
        
        # Filesystem snapshots
        discoveries.extend(self._scan_btrfs_snapshots())
        discoveries.extend(self._scan_zfs_snapshots())
        
        # Additional tools
        discoveries.extend(self._scan_rsnapshot())
        discoveries.extend(self._scan_back_in_time())
        discoveries.extend(self._scan_deja_dup())
        discoveries.extend(self._scan_kopia())
        
        self.logger.info(f"Found {len(discoveries)} backup configurations")
        return discoveries
    
    # ─────────────────────────────────────────────────────────────
    # Crontab Scanning
    # ─────────────────────────────────────────────────────────────
    
    def _scan_user_crontab(self) -> List[Discovery]:
        """Scan user's crontab for backup jobs."""
        discoveries = []
        
        code, stdout, _ = self.run_command(["crontab", "-l"])
        if code != 0:
            return discoveries
        
        for job in self.parse_crontab(stdout):
            if self._is_backup_command(job['command']):
                discovery = self._parse_backup_cron(job, source="user_crontab")
                if discovery:
                    discoveries.append(discovery)
        
        return discoveries
    
    def _scan_system_crontabs(self) -> List[Discovery]:
        """Scan system crontabs for backup jobs."""
        discoveries = []
        
        cron_paths = [
            "/etc/crontab",
            "/etc/cron.d/",
            "/etc/cron.daily/",
            "/etc/cron.hourly/",
            "/etc/cron.weekly/",
            "/etc/cron.monthly/",
        ]
        
        for path in cron_paths:
            p = Path(path)
            if p.is_file():
                content = self.read_file(str(p))
                if content:
                    for job in self.parse_crontab(content):
                        if self._is_backup_command(job['command']):
                            discovery = self._parse_backup_cron(job, source=str(p))
                            if discovery:
                                discoveries.append(discovery)
            elif p.is_dir():
                for file in p.iterdir():
                    if file.is_file():
                        content = self.read_file(str(file))
                        if content and self._is_backup_command(content):
                            # Script-based backup
                            discoveries.append(self._script_to_discovery(file))
        
        return discoveries
    
    def _is_backup_command(self, cmd: str) -> bool:
        """Check if a command looks like a backup operation."""
        backup_indicators = [
            'rsync', 'rsnapshot', 'borg', 'restic', 'rclone', 
            'tar ', 'backup', 'bak ', 
            'duplicity', 'rdiff-backup', 'duplicati',
            'timeshift', 'snapper', 'btrbk',
            'zfs-auto-snapshot', 'sanoid', 'syncoid',
            'backintime', 'kopia', 'vorta',
        ]
        cmd_lower = cmd.lower()
        return any(ind in cmd_lower for ind in backup_indicators)
    
    def _parse_backup_cron(self, job: dict, source: str) -> Optional[Discovery]:
        """Parse a cron job into a backup discovery."""
        cmd = job['command']
        schedule = job['schedule']
        
        # Determine backup tool
        tool = self._detect_backup_tool(cmd)
        
        # Extract paths
        source_path, dest_path = self._extract_paths(cmd, tool)
        
        # Generate name
        name = self._generate_backup_name(tool, source_path, dest_path)
        
        return backup_discovery(
            name=name,
            description=f"Backup via {tool} scheduled in cron",
            schedule=self._humanize_schedule(schedule),
            destination=dest_path,
            source_path=source_path,
            tool=tool,
            status="Scheduled",
            severity=DiscoverySeverity.SUCCESS,
            cron_schedule=schedule,
            cron_source=source,
            command=cmd,
        )
    
    def _script_to_discovery(self, script_path: Path) -> Discovery:
        """Convert a backup script to a discovery."""
        content = self.read_file(str(script_path)) or ""
        tool = self._detect_backup_tool(content)
        
        return backup_discovery(
            name=script_path.stem,
            description=f"Backup script: {script_path.name}",
            schedule=self._get_cron_schedule_for_script(script_path),
            tool=tool,
            status="Scheduled",
            severity=DiscoverySeverity.SUCCESS,
            script_path=str(script_path),
        )
    
    # ─────────────────────────────────────────────────────────────
    # systemd Timer Scanning
    # ─────────────────────────────────────────────────────────────
    
    def _scan_systemd_timers(self) -> List[Discovery]:
        """Scan systemd timers for backup services."""
        discoveries = []
        
        code, stdout, _ = self.run_command([
            "systemctl", "list-timers", "--all", "--no-pager", "--output=json"
        ])
        
        if code != 0:
            # Fallback to text parsing
            code, stdout, _ = self.run_command([
                "systemctl", "list-timers", "--all", "--no-pager"
            ])
            if code != 0:
                return discoveries
            
            # Parse text output - look for backup-related timers
            backup_keywords = [
                'backup', 'borg', 'restic', 'rsync', 'rsnapshot',
                'snapper', 'btrbk', 'sanoid', 'zfs-auto-snapshot',
                'timeshift', 'kopia', 'duplicity', 'rclone',
            ]
            for line in stdout.splitlines()[1:]:  # Skip header
                if any(bk in line.lower() for bk in backup_keywords):
                    parts = line.split()
                    if len(parts) >= 5:
                        timer_name = parts[-1]
                        discoveries.append(self._timer_to_discovery(timer_name))
        else:
            # Parse JSON output
            backup_keywords = [
                'backup', 'borg', 'restic', 'rsync', 'rsnapshot',
                'snapper', 'btrbk', 'sanoid', 'zfs-auto-snapshot',
                'timeshift', 'kopia', 'duplicity', 'rclone',
            ]
            try:
                timers = json.loads(stdout)
                for timer in timers:
                    unit = timer.get('unit', '')
                    if any(bk in unit.lower() for bk in backup_keywords):
                        discoveries.append(self._timer_to_discovery(unit))
            except json.JSONDecodeError:
                pass
        
        return discoveries
    
    def _timer_to_discovery(self, timer_name: str) -> Discovery:
        """Convert a systemd timer to a discovery."""
        # Get timer info
        code, stdout, _ = self.run_command([
            "systemctl", "show", timer_name, "--property=Description,ActiveState"
        ])
        
        description = "systemd timer backup"
        status = "Unknown"
        
        if code == 0:
            for line in stdout.splitlines():
                if line.startswith("Description="):
                    description = line.split("=", 1)[1]
                elif line.startswith("ActiveState="):
                    status = line.split("=", 1)[1].title()
        
        return backup_discovery(
            name=timer_name.replace(".timer", ""),
            description=description,
            schedule="systemd timer",
            tool="systemd",
            status=status,
            severity=DiscoverySeverity.SUCCESS if status == "Active" else DiscoverySeverity.WARNING,
            timer_unit=timer_name,
        )
    
    # ─────────────────────────────────────────────────────────────
    # Tool-Specific Scanning
    # ─────────────────────────────────────────────────────────────
    
    def _scan_borg(self) -> List[Discovery]:
        """Scan for Borg backup repositories."""
        discoveries = []
        
        if not self.command_exists("borg"):
            return discoveries
        
        # Check common locations
        borg_locations = [
            self.get_home_dir() / ".config" / "borg",
            Path("/etc/borg"),
            self.get_home_dir() / ".borg",
        ]
        
        # Check BORG_REPO environment variable
        borg_repo = os.environ.get("BORG_REPO")
        if borg_repo:
            discoveries.append(backup_discovery(
                name="borg-default",
                description=f"Borg repository at {borg_repo}",
                destination=borg_repo,
                tool="borg",
                status="Configured",
                severity=DiscoverySeverity.SUCCESS,
            ))
        
        return discoveries
    
    def _scan_restic(self) -> List[Discovery]:
        """Scan for Restic backup configurations."""
        discoveries = []
        
        if not self.command_exists("restic"):
            return discoveries
        
        # Check common config locations
        restic_paths = [
            self.get_home_dir() / ".config" / "restic",
            Path("/etc/restic"),
        ]
        
        for path in restic_paths:
            if path.exists():
                for config_file in path.glob("*.conf"):
                    content = self.read_file(str(config_file))
                    if content:
                        discoveries.append(backup_discovery(
                            name=config_file.stem,
                            description=f"Restic configuration: {config_file.name}",
                            tool="restic",
                            status="Configured",
                            severity=DiscoverySeverity.SUCCESS,
                            config_path=str(config_file),
                        ))
        
        # Check RESTIC_REPOSITORY environment variable
        restic_repo = os.environ.get("RESTIC_REPOSITORY")
        if restic_repo:
            discoveries.append(backup_discovery(
                name="restic-default",
                description=f"Restic repository at {restic_repo}",
                destination=restic_repo,
                tool="restic",
                status="Configured",
                severity=DiscoverySeverity.SUCCESS,
            ))
        
        return discoveries
    
    def _scan_rclone(self) -> List[Discovery]:
        """Scan for rclone configurations."""
        discoveries = []
        
        if not self.command_exists("rclone"):
            return discoveries
        
        # List rclone remotes
        code, stdout, _ = self.run_command(["rclone", "listremotes"])
        if code == 0:
            for remote in stdout.strip().splitlines():
                remote = remote.rstrip(':')
                if remote:
                    discoveries.append(backup_discovery(
                        name=f"rclone-{remote}",
                        description=f"rclone remote: {remote}",
                        destination=remote,
                        tool="rclone",
                        status="Configured",
                        severity=DiscoverySeverity.INFO,
                        remote_name=remote,
                    ))
        
        return discoveries
    
    def _scan_timeshift(self) -> List[Discovery]:
        """Scan for Timeshift snapshots."""
        discoveries = []
        
        if not self.command_exists("timeshift"):
            return discoveries
        
        # Check Timeshift config
        timeshift_config = Path("/etc/timeshift/timeshift.json")
        if timeshift_config.exists():
            content = self.read_file(str(timeshift_config))
            if content:
                try:
                    config = json.loads(content)
                    schedule = []
                    if config.get("schedule_hourly"):
                        schedule.append("hourly")
                    if config.get("schedule_daily"):
                        schedule.append("daily")
                    if config.get("schedule_weekly"):
                        schedule.append("weekly")
                    if config.get("schedule_monthly"):
                        schedule.append("monthly")
                    
                    discoveries.append(backup_discovery(
                        name="timeshift",
                        description="Timeshift system snapshots",
                        schedule=", ".join(schedule) if schedule else "Manual",
                        destination=config.get("backup_device_uuid", "Unknown"),
                        tool="timeshift",
                        status="Configured",
                        severity=DiscoverySeverity.SUCCESS,
                        timeshift_config=config,
                    ))
                except json.JSONDecodeError:
                    pass
        
        return discoveries
    
    # ─────────────────────────────────────────────────────────────
    # Helper Methods
    # ─────────────────────────────────────────────────────────────
    
    def _detect_backup_tool(self, cmd: str) -> str:
        """Detect which backup tool a command uses."""
        cmd_lower = cmd.lower()
        
        if 'borg' in cmd_lower or 'vorta' in cmd_lower:
            return 'borg'
        elif 'restic' in cmd_lower:
            return 'restic'
        elif 'rclone' in cmd_lower:
            return 'rclone'
        elif 'rsnapshot' in cmd_lower:
            return 'rsnapshot'
        elif 'rsync' in cmd_lower:
            return 'rsync'
        elif 'duplicity' in cmd_lower:
            return 'duplicity'
        elif 'tar ' in cmd_lower or cmd_lower.startswith('tar'):
            return 'tar'
        elif 'timeshift' in cmd_lower:
            return 'timeshift'
        elif 'snapper' in cmd_lower:
            return 'snapper'
        elif 'btrbk' in cmd_lower:
            return 'btrbk'
        elif 'zfs-auto-snapshot' in cmd_lower:
            return 'zfs-auto-snapshot'
        elif 'sanoid' in cmd_lower or 'syncoid' in cmd_lower:
            return 'sanoid'
        elif 'backintime' in cmd_lower:
            return 'backintime'
        elif 'kopia' in cmd_lower:
            return 'kopia'
        else:
            return 'unknown'
    
    def _extract_paths(self, cmd: str, tool: str) -> tuple[Optional[str], Optional[str]]:
        """Extract source and destination paths from backup command."""
        # This is a simplified extraction - real implementation would be more robust
        
        if tool == 'rsync':
            # rsync [options] source destination
            parts = cmd.split()
            paths = [p for p in parts if p.startswith('/') or p.startswith('~')]
            if len(paths) >= 2:
                return paths[-2], paths[-1]
            elif len(paths) == 1:
                return paths[0], None
        
        return None, None
    
    def _generate_backup_name(
        self, 
        tool: str, 
        source: Optional[str], 
        dest: Optional[str]
    ) -> str:
        """Generate a human-readable name for a backup."""
        if source:
            # Use last path component
            source_name = Path(source).name or source.split('/')[-1]
            return f"{tool}-{source_name}"
        elif dest:
            dest_name = Path(dest).name or dest.split('/')[-1]
            return f"{tool}-to-{dest_name}"
        else:
            return f"{tool}-backup"
    
    def _humanize_schedule(self, cron_schedule: str) -> str:
        """Convert cron schedule to human-readable format."""
        parts = cron_schedule.split()
        if len(parts) != 5:
            return cron_schedule
        
        minute, hour, day, month, weekday = parts
        
        # Common patterns
        if cron_schedule == "0 * * * *":
            return "Every hour"
        elif cron_schedule == "0 0 * * *":
            return "Daily at midnight"
        elif minute == "0" and hour != "*" and day == "*" and month == "*" and weekday == "*":
            return f"Daily at {hour}:00"
        elif weekday == "0":
            return "Weekly on Sunday"
        elif day == "1" and month == "*":
            return "Monthly"
        else:
            return cron_schedule
    
    def _get_cron_schedule_for_script(self, script_path: Path) -> str:
        """Determine schedule based on cron directory."""
        parent = script_path.parent.name
        
        if parent == "cron.hourly":
            return "Hourly"
        elif parent == "cron.daily":
            return "Daily"
        elif parent == "cron.weekly":
            return "Weekly"
        elif parent == "cron.monthly":
            return "Monthly"
        else:
            return "Scheduled"
    
    # ─────────────────────────────────────────────────────────────
    # Btrfs Snapshot Scanning
    # ─────────────────────────────────────────────────────────────
    
    def _scan_btrfs_snapshots(self) -> List[Discovery]:
        """Scan for Btrfs snapshot configurations (snapper, btrbk)."""
        discoveries = []
        
        # Check for snapper
        discoveries.extend(self._scan_snapper())
        
        # Check for btrbk
        discoveries.extend(self._scan_btrbk())
        
        # Check for manual btrfs snapshots in common locations
        discoveries.extend(self._scan_btrfs_snapshot_dirs())
        
        return discoveries
    
    def _scan_snapper(self) -> List[Discovery]:
        """Scan for snapper configurations."""
        discoveries = []
        
        if not self.command_exists("snapper"):
            return discoveries
        
        # List snapper configs
        code, stdout, _ = self.run_command(["snapper", "list-configs"])
        if code != 0:
            return discoveries
        
        for line in stdout.strip().splitlines()[2:]:  # Skip header
            parts = line.split('|')
            if len(parts) >= 2:
                config_name = parts[0].strip()
                subvolume = parts[1].strip()
                
                # Get snapshot count
                code2, snap_out, _ = self.run_command(["snapper", "-c", config_name, "list"])
                snap_count = len(snap_out.strip().splitlines()) - 2 if code2 == 0 else 0
                
                discoveries.append(backup_discovery(
                    name=f"snapper-{config_name}",
                    description=f"Btrfs snapshots for {subvolume}",
                    destination=subvolume,
                    tool="snapper",
                    status="Active",
                    severity=DiscoverySeverity.SUCCESS,
                    snapshot_count=max(0, snap_count),
                    config_name=config_name,
                ))
        
        return discoveries
    
    def _scan_btrbk(self) -> List[Discovery]:
        """Scan for btrbk configurations."""
        discoveries = []
        
        btrbk_conf = Path("/etc/btrbk/btrbk.conf")
        if not btrbk_conf.exists():
            return discoveries
        
        content = self.read_file(str(btrbk_conf))
        if not content:
            return discoveries
        
        # Parse btrbk config for snapshot targets
        current_volume = None
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('volume'):
                current_volume = line.split()[1] if len(line.split()) > 1 else None
            elif line.startswith('subvolume') and current_volume:
                subvol = line.split()[1] if len(line.split()) > 1 else 'unknown'
                discoveries.append(backup_discovery(
                    name=f"btrbk-{Path(subvol).name}",
                    description=f"btrbk snapshots for {subvol}",
                    source_path=f"{current_volume}/{subvol}",
                    tool="btrbk",
                    status="Configured",
                    severity=DiscoverySeverity.SUCCESS,
                    config_path=str(btrbk_conf),
                ))
        
        return discoveries
    
    def _scan_btrfs_snapshot_dirs(self) -> List[Discovery]:
        """Check common Btrfs snapshot directories."""
        discoveries = []
        
        snapshot_dirs = [
            "/.snapshots",
            "/home/.snapshots",
            "/@snapshots",
            "/btrfs/@snapshots",
        ]
        
        for snap_dir in snapshot_dirs:
            p = Path(snap_dir)
            if p.exists() and p.is_dir():
                try:
                    snap_count = len(list(p.iterdir()))
                    if snap_count > 0:
                        discoveries.append(backup_discovery(
                            name=f"btrfs-snapshots-{p.name}",
                            description=f"Btrfs snapshots at {snap_dir}",
                            destination=snap_dir,
                            tool="btrfs",
                            status="Active",
                            severity=DiscoverySeverity.SUCCESS,
                            snapshot_count=snap_count,
                        ))
                except PermissionError:
                    pass
        
        return discoveries
    
    # ─────────────────────────────────────────────────────────────
    # ZFS Snapshot Scanning
    # ─────────────────────────────────────────────────────────────
    
    def _scan_zfs_snapshots(self) -> List[Discovery]:
        """Scan for ZFS snapshot configurations."""
        discoveries = []
        
        if not self.command_exists("zfs"):
            return discoveries
        
        # Check for zfs-auto-snapshot
        discoveries.extend(self._scan_zfs_auto_snapshot())
        
        # Check for sanoid
        discoveries.extend(self._scan_sanoid())
        
        # List existing ZFS snapshots
        code, stdout, _ = self.run_command(["zfs", "list", "-t", "snapshot", "-o", "name", "-H"])
        if code == 0 and stdout.strip():
            snapshots = stdout.strip().splitlines()
            
            # Group by dataset
            datasets = {}
            for snap in snapshots:
                if '@' in snap:
                    dataset = snap.split('@')[0]
                    datasets[dataset] = datasets.get(dataset, 0) + 1
            
            for dataset, count in datasets.items():
                discoveries.append(backup_discovery(
                    name=f"zfs-{dataset.replace('/', '-')}",
                    description=f"ZFS snapshots for {dataset}",
                    destination=dataset,
                    tool="zfs",
                    status="Active",
                    severity=DiscoverySeverity.SUCCESS,
                    snapshot_count=count,
                ))
        
        return discoveries
    
    def _scan_zfs_auto_snapshot(self) -> List[Discovery]:
        """Scan for zfs-auto-snapshot service."""
        discoveries = []
        
        # Check if zfs-auto-snapshot is installed
        code, _, _ = self.run_command(["which", "zfs-auto-snapshot"])
        if code != 0:
            return discoveries
        
        # Check for systemd timers or cron
        for interval in ['frequent', 'hourly', 'daily', 'weekly', 'monthly']:
            timer_name = f"zfs-auto-snapshot-{interval}.timer"
            code, _, _ = self.run_command(["systemctl", "is-enabled", timer_name])
            if code == 0:
                discoveries.append(backup_discovery(
                    name=f"zfs-auto-snapshot-{interval}",
                    description=f"ZFS automatic {interval} snapshots",
                    schedule=interval.title(),
                    tool="zfs-auto-snapshot",
                    status="Enabled",
                    severity=DiscoverySeverity.SUCCESS,
                ))
                break  # Found it, no need to check all intervals
        
        return discoveries
    
    def _scan_sanoid(self) -> List[Discovery]:
        """Scan for sanoid ZFS snapshot manager."""
        discoveries = []
        
        sanoid_conf = Path("/etc/sanoid/sanoid.conf")
        if not sanoid_conf.exists():
            return discoveries
        
        content = self.read_file(str(sanoid_conf))
        if not content:
            return discoveries
        
        # Check if sanoid timer is active
        code, _, _ = self.run_command(["systemctl", "is-active", "sanoid.timer"])
        status = "Active" if code == 0 else "Configured"
        
        # Parse sanoid.conf for datasets
        current_dataset = None
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                section = line[1:-1]
                if section != 'template_production' and not section.startswith('template_'):
                    current_dataset = section
                    discoveries.append(backup_discovery(
                        name=f"sanoid-{current_dataset.replace('/', '-')}",
                        description=f"Sanoid snapshots for {current_dataset}",
                        destination=current_dataset,
                        tool="sanoid",
                        status=status,
                        severity=DiscoverySeverity.SUCCESS if status == "Active" else DiscoverySeverity.INFO,
                        config_path=str(sanoid_conf),
                    ))
        
        return discoveries
    
    # ─────────────────────────────────────────────────────────────
    # Additional Backup Tools
    # ─────────────────────────────────────────────────────────────
    
    def _scan_rsnapshot(self) -> List[Discovery]:
        """Scan for rsnapshot configurations."""
        discoveries = []
        
        rsnapshot_conf = Path("/etc/rsnapshot.conf")
        if not rsnapshot_conf.exists():
            return discoveries
        
        content = self.read_file(str(rsnapshot_conf))
        if not content:
            return discoveries
        
        # Parse config
        snapshot_root = None
        intervals = []
        
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('snapshot_root'):
                parts = line.split()
                if len(parts) >= 2:
                    snapshot_root = parts[1]
            elif line.startswith('retain') or line.startswith('interval'):
                parts = line.split()
                if len(parts) >= 2:
                    intervals.append(parts[1])
        
        if snapshot_root or intervals:
            discoveries.append(backup_discovery(
                name="rsnapshot",
                description=f"rsnapshot backups to {snapshot_root or 'configured location'}",
                destination=snapshot_root,
                schedule=", ".join(intervals) if intervals else "Configured",
                tool="rsnapshot",
                status="Configured",
                severity=DiscoverySeverity.SUCCESS,
                config_path=str(rsnapshot_conf),
            ))
        
        return discoveries
    
    def _scan_back_in_time(self) -> List[Discovery]:
        """Scan for Back In Time configurations."""
        discoveries = []
        
        # Back In Time stores config in ~/.config/backintime/
        config_dir = self.get_home_dir() / ".config" / "backintime"
        if not config_dir.exists():
            return discoveries
        
        config_file = config_dir / "config"
        if not config_file.exists():
            return discoveries
        
        content = self.read_file(str(config_file))
        if not content:
            return discoveries
        
        # Parse config
        profiles = {}
        for line in content.splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                # Profile 1 is the main profile
                if 'profile1' in key or key.startswith('1.'):
                    profiles[key] = value
        
        dest = profiles.get('profile1.snapshots.path', profiles.get('1.snapshots.path', ''))
        schedule_mode = profiles.get('profile1.schedule.mode', profiles.get('1.schedule.mode', '0'))
        
        schedule_map = {
            '0': 'Disabled',
            '1': 'Every 5 minutes',
            '2': 'Every 10 minutes', 
            '4': 'Every hour',
            '7': 'Daily',
            '10': 'Weekly',
            '14': 'Monthly',
        }
        
        discoveries.append(backup_discovery(
            name="back-in-time",
            description="Back In Time snapshots",
            destination=dest,
            schedule=schedule_map.get(schedule_mode, 'Custom'),
            tool="backintime",
            status="Configured",
            severity=DiscoverySeverity.SUCCESS,
            config_path=str(config_file),
        ))
        
        return discoveries
    
    def _scan_deja_dup(self) -> List[Discovery]:
        """Scan for Deja Dup (GNOME Backups) configurations."""
        discoveries = []
        
        # Deja Dup uses dconf/gsettings - check for config files
        deja_dup_paths = [
            self.get_home_dir() / ".config" / "dconf" / "user",
            Path("/etc/dconf/db/local.d/"),
        ]
        
        # Try gsettings if available
        code, stdout, _ = self.run_command([
            "gsettings", "get", "org.gnome.DejaDup", "backend"
        ])
        
        if code == 0 and stdout.strip():
            backend = stdout.strip().strip("'")
            
            # Get destination
            code2, dest_out, _ = self.run_command([
                "gsettings", "get", "org.gnome.DejaDup", "folder"
            ])
            dest = dest_out.strip().strip("'") if code2 == 0 else ""
            
            # Get schedule
            code3, period_out, _ = self.run_command([
                "gsettings", "get", "org.gnome.DejaDup", "periodic"
            ])
            is_periodic = period_out.strip().lower() == 'true' if code3 == 0 else False
            
            discoveries.append(backup_discovery(
                name="deja-dup",
                description=f"Deja Dup backups ({backend})",
                destination=dest,
                schedule="Automatic" if is_periodic else "Manual",
                tool="deja-dup",
                status="Configured",
                severity=DiscoverySeverity.SUCCESS,
            ))
        
        return discoveries
    
    def _scan_kopia(self) -> List[Discovery]:
        """Scan for Kopia backup configurations."""
        discoveries = []
        
        if not self.command_exists("kopia"):
            return discoveries
        
        # Check for kopia repository
        code, stdout, _ = self.run_command(["kopia", "repository", "status", "--json"])
        if code == 0:
            try:
                status = json.loads(stdout)
                config_file = status.get('configFile', '')
                
                discoveries.append(backup_discovery(
                    name="kopia",
                    description="Kopia backup repository",
                    tool="kopia",
                    status="Connected",
                    severity=DiscoverySeverity.SUCCESS,
                    config_path=config_file,
                ))
            except json.JSONDecodeError:
                pass
        
        # Check for kopia systemd timer
        code, _, _ = self.run_command(["systemctl", "--user", "is-active", "kopia-backup.timer"])
        if code == 0:
            discoveries.append(backup_discovery(
                name="kopia-scheduled",
                description="Kopia scheduled backups",
                schedule="systemd timer",
                tool="kopia",
                status="Active",
                severity=DiscoverySeverity.SUCCESS,
                timer_unit="kopia-backup.timer",
            ))
        
        return discoveries
