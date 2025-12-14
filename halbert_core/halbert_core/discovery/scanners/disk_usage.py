"""
Disk Usage Scanner - Find what's consuming disk space.

Enables scenarios:
- S5.2: "What's eating disk space?" → Large directories, growth
- S10.4: "Full disk emergency" → Quick identification of space hogs
- S9.8: "Digital Declutterer" → Old files, duplicates

Discovers:
- Large directories (top space consumers)
- Old log files taking space
- Cache directories (apt, npm, pip, etc.)
- Trash that can be emptied
- Potential cleanup targets
"""

from __future__ import annotations
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime, timedelta

from .base import BaseScanner
from ..schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class DiskUsageScanner(BaseScanner):
    """
    Scanner for disk space consumption analysis.
    
    Discovers:
    - Large directories
    - Cache directories
    - Log files
    - Cleanup opportunities
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.STORAGE
    
    def scan(self) -> List[Discovery]:
        """Scan disk usage."""
        discoveries = []
        
        discoveries.extend(self._scan_large_directories())
        discoveries.extend(self._scan_cache_directories())
        discoveries.extend(self._scan_log_files())
        discoveries.extend(self._scan_trash())
        
        self.logger.info(f"Found {len(discoveries)} disk usage discoveries")
        return discoveries
    
    def _scan_large_directories(self) -> List[Discovery]:
        """Find large directories consuming space."""
        discoveries = []
        
        # Scan key directories
        scan_paths = [
            ("/home", "Home directories"),
            ("/var", "Variable data"),
            ("/opt", "Optional software"),
            ("/usr/local", "Local installations"),
        ]
        
        large_dirs = []
        
        for path, desc in scan_paths:
            if not Path(path).exists():
                continue
            
            # Get directory sizes (depth 1)
            code, stdout, _ = self.run_command([
                "du", "-h", "--max-depth=1", path
            ], timeout=30)
            
            if code != 0:
                continue
            
            for line in stdout.strip().splitlines():
                parts = line.split('\t')
                if len(parts) >= 2:
                    size_str = parts[0].strip()
                    dir_path = parts[1].strip()
                    
                    # Parse size to bytes for sorting
                    size_bytes = self._parse_size(size_str)
                    
                    # Only include dirs > 1GB
                    if size_bytes >= 1024**3:
                        large_dirs.append((dir_path, size_str, size_bytes))
        
        # Sort by size and take top 10
        large_dirs.sort(key=lambda x: x[2], reverse=True)
        
        for dir_path, size_str, size_bytes in large_dirs[:10]:
            # Determine severity based on size
            if size_bytes >= 50 * 1024**3:  # > 50GB
                severity = DiscoverySeverity.WARNING
            else:
                severity = DiscoverySeverity.INFO
            
            dir_name = Path(dir_path).name
            discovery_id = make_discovery_id(DiscoveryType.STORAGE, f"large-{dir_name}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.STORAGE,
                name=f"large-{dir_name}",
                title=f"Large Directory: {dir_path}",
                description=f"Using {size_str} of disk space",
                icon="folder",
                severity=severity,
                status=size_str,
                source=dir_path,
                data={
                    "path": dir_path,
                    "size": size_str,
                    "size_bytes": size_bytes,
                    "is_large_dir": True,
                },
                chat_context=f"Directory '{dir_path}' is using {size_str}. "
                            f"{'This is a significant amount of space.' if size_bytes >= 10*1024**3 else ''}",
            ))
        
        return discoveries
    
    def _scan_cache_directories(self) -> List[Discovery]:
        """Find cache directories that can be cleaned."""
        discoveries = []
        
        # Common cache locations
        cache_paths = [
            ("/var/cache/apt/archives", "APT package cache", "sudo apt clean"),
            ("/var/cache/dnf", "DNF package cache", "sudo dnf clean all"),
            ("/var/cache/pacman/pkg", "Pacman cache", "sudo paccache -r"),
            ("~/.cache", "User cache", "rm -rf ~/.cache/*"),
            ("~/.npm/_cacache", "NPM cache", "npm cache clean --force"),
            ("~/.local/share/Trash", "Trash", "rm -rf ~/.local/share/Trash/*"),
            ("/tmp", "Temp files", "sudo rm -rf /tmp/*"),
            ("~/.cache/pip", "Pip cache", "pip cache purge"),
            ("~/.cache/yarn", "Yarn cache", "yarn cache clean"),
            ("~/.gradle/caches", "Gradle cache", "rm -rf ~/.gradle/caches"),
            ("~/.m2/repository", "Maven cache", None),
        ]
        
        home = str(Path.home())
        
        for path_template, desc, clean_cmd in cache_paths:
            path = path_template.replace("~", home)
            
            if not Path(path).exists():
                continue
            
            # Get size
            code, stdout, _ = self.run_command(["du", "-sh", path], timeout=10)
            if code != 0:
                continue
            
            size_str = stdout.split()[0] if stdout.split() else "0"
            size_bytes = self._parse_size(size_str)
            
            # Only report if > 100MB
            if size_bytes < 100 * 1024**2:
                continue
            
            cache_name = Path(path).name
            discovery_id = make_discovery_id(DiscoveryType.STORAGE, f"cache-{cache_name}")
            
            actions = []
            if clean_cmd:
                actions.append(DiscoveryAction(
                    id="clean",
                    label="Clean",
                    icon="trash-2",
                    command=clean_cmd,
                    requires_approval=True,
                ))
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.STORAGE,
                name=f"cache-{cache_name}",
                title=f"Cache: {desc}",
                description=f"Using {size_str} at {path}",
                icon="database",
                severity=DiscoverySeverity.INFO,
                status=size_str,
                source=path,
                data={
                    "path": path,
                    "size": size_str,
                    "size_bytes": size_bytes,
                    "cache_type": desc,
                    "clean_command": clean_cmd,
                    "is_cache": True,
                    "is_cleanable": clean_cmd is not None,
                },
                actions=actions,
                chat_context=f"{desc} at '{path}' is using {size_str}. "
                            f"{'Can be cleaned with: ' + clean_cmd if clean_cmd else 'Review before cleaning.'}",
            ))
        
        return discoveries
    
    def _scan_log_files(self) -> List[Discovery]:
        """Find large log files."""
        discoveries = []
        
        # Check /var/log size
        code, stdout, _ = self.run_command(["du", "-sh", "/var/log"], timeout=10)
        if code == 0:
            size_str = stdout.split()[0] if stdout.split() else "0"
            size_bytes = self._parse_size(size_str)
            
            if size_bytes >= 500 * 1024**2:  # > 500MB
                discovery_id = make_discovery_id(DiscoveryType.STORAGE, "logs-var")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.STORAGE,
                    name="logs-var",
                    title="System Logs",
                    description=f"/var/log is using {size_str}",
                    icon="file-text",
                    severity=DiscoverySeverity.INFO if size_bytes < 2*1024**3 else DiscoverySeverity.WARNING,
                    status=size_str,
                    source="/var/log",
                    data={
                        "path": "/var/log",
                        "size": size_str,
                        "size_bytes": size_bytes,
                        "is_log": True,
                    },
                    actions=[
                        DiscoveryAction(
                            id="vacuum",
                            label="Vacuum Journals",
                            icon="trash-2",
                            command="sudo journalctl --vacuum-size=500M",
                            requires_approval=True,
                        ),
                    ],
                    chat_context=f"System logs at /var/log are using {size_str}. "
                                f"Run 'sudo journalctl --vacuum-size=500M' to limit journal size.",
                ))
        
        return discoveries
    
    def _scan_trash(self) -> List[Discovery]:
        """Check trash/recycle bin size."""
        discoveries = []
        
        trash_paths = [
            Path.home() / ".local/share/Trash",
            Path("/root/.local/share/Trash"),
        ]
        
        for trash_path in trash_paths:
            if not trash_path.exists():
                continue
            
            code, stdout, _ = self.run_command(["du", "-sh", str(trash_path)], timeout=10)
            if code != 0:
                continue
            
            size_str = stdout.split()[0] if stdout.split() else "0"
            size_bytes = self._parse_size(size_str)
            
            if size_bytes < 100 * 1024**2:  # < 100MB
                continue
            
            discovery_id = make_discovery_id(DiscoveryType.STORAGE, "trash")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.STORAGE,
                name="trash",
                title="Trash",
                description=f"Trash contains {size_str} of deleted files",
                icon="trash",
                severity=DiscoverySeverity.INFO,
                status=size_str,
                source=str(trash_path),
                data={
                    "path": str(trash_path),
                    "size": size_str,
                    "size_bytes": size_bytes,
                    "is_trash": True,
                    "is_cleanable": True,
                },
                actions=[
                    DiscoveryAction(
                        id="empty",
                        label="Empty Trash",
                        icon="trash-2",
                        command=f"rm -rf {trash_path}/*",
                        requires_approval=True,
                    ),
                ],
                chat_context=f"Trash at '{trash_path}' contains {size_str}. "
                            f"Empty it to reclaim disk space.",
            ))
        
        return discoveries
    
    def _parse_size(self, size_str: str) -> int:
        """Parse size string like '1.5G' to bytes."""
        try:
            size_str = size_str.strip().upper()
            if size_str.endswith('T'):
                return int(float(size_str[:-1]) * 1024**4)
            elif size_str.endswith('G'):
                return int(float(size_str[:-1]) * 1024**3)
            elif size_str.endswith('M'):
                return int(float(size_str[:-1]) * 1024**2)
            elif size_str.endswith('K'):
                return int(float(size_str[:-1]) * 1024)
            else:
                return int(float(size_str))
        except:
            return 0
