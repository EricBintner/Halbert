"""
Package Scanner - Discover package management state.

Enables scenarios:
- S4.1: "Safe package installation" → Package info, dependencies
- S4.2: "System updates" → Available updates, security updates
- S4.3: "Held package resolution" → Why packages are held
- S4.4: "Cleanup unused packages" → Orphan packages, cache size
- S4.5: "Package origin tracing" → Package → repo/PPA source
- S10.10: "Broken package manager repair" → Lock files, broken deps

Discovers:
- Available updates (regular and security)
- Held/pinned packages
- Orphan packages (no longer needed)
- Package cache size
- Foreign packages (not from repos)
- Lock file status
"""

from __future__ import annotations
from typing import List, Dict, Optional
from pathlib import Path

from .base import BaseScanner
from ..schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class PackageScanner(BaseScanner):
    """
    Scanner for package management state.
    
    Supports apt (Debian/Ubuntu), dnf/yum (Fedora/RHEL), pacman (Arch).
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.PACKAGE
    
    def scan(self) -> List[Discovery]:
        """Scan package management state."""
        discoveries = []
        
        # Detect package manager
        pkg_manager = self._detect_package_manager()
        
        if pkg_manager == 'apt':
            discoveries.extend(self._scan_apt())
        elif pkg_manager == 'dnf':
            discoveries.extend(self._scan_dnf())
        elif pkg_manager == 'pacman':
            discoveries.extend(self._scan_pacman())
        
        # Check for lock files (all distros)
        discoveries.extend(self._scan_lock_files())
        
        self.logger.info(f"Found {len(discoveries)} package discoveries")
        return discoveries
    
    def _detect_package_manager(self) -> str:
        """Detect which package manager is available."""
        if self.command_exists("apt"):
            return "apt"
        elif self.command_exists("dnf"):
            return "dnf"
        elif self.command_exists("pacman"):
            return "pacman"
        return "unknown"
    
    def _scan_apt(self) -> List[Discovery]:
        """Scan apt-based system (Debian/Ubuntu)."""
        discoveries = []
        
        # Check for available updates
        code, stdout, _ = self.run_command(
            ["apt", "list", "--upgradable"],
            timeout=30
        )
        
        updates = []
        security_updates = []
        if code == 0:
            for line in stdout.strip().splitlines()[1:]:  # Skip header
                if line.strip():
                    pkg_name = line.split('/')[0]
                    updates.append(pkg_name)
                    if '-security' in line or 'security' in line.lower():
                        security_updates.append(pkg_name)
        
        if updates:
            severity = DiscoverySeverity.WARNING if security_updates else DiscoverySeverity.INFO
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "updates-available")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="updates-available",
                title="Updates Available",
                description=f"{len(updates)} packages can be updated ({len(security_updates)} security)",
                icon="download",
                severity=severity,
                status=f"{len(updates)} updates",
                status_detail=f"{len(security_updates)} security" if security_updates else None,
                data={
                    "update_count": len(updates),
                    "security_count": len(security_updates),
                    "packages": updates[:20],
                    "security_packages": security_updates,
                    "package_manager": "apt",
                },
                actions=[
                    DiscoveryAction(
                        id="update",
                        label="Update All",
                        icon="download",
                        command="sudo apt upgrade -y",
                        requires_approval=True,
                    ),
                ],
                chat_context=f"{len(updates)} package updates available. "
                            f"{'⚠️ ' + str(len(security_updates)) + ' are security updates!' if security_updates else ''} "
                            f"Run 'sudo apt upgrade' to update.",
            ))
        
        # Check for held packages
        code, stdout, _ = self.run_command(["apt-mark", "showhold"])
        if code == 0 and stdout.strip():
            held = stdout.strip().splitlines()
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "held-packages")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="held-packages",
                title="Held Packages",
                description=f"{len(held)} packages are held back from updates",
                icon="lock",
                severity=DiscoverySeverity.INFO,
                status=f"{len(held)} held",
                data={
                    "held_packages": held,
                    "held_count": len(held),
                },
                chat_context=f"{len(held)} packages are held: {', '.join(held[:5])}. "
                            f"These won't be updated until unhold. Use 'apt-mark unhold <pkg>' to release.",
            ))
        
        # Check for orphan packages
        code, stdout, _ = self.run_command(["apt", "autoremove", "--dry-run"])
        orphans = []
        if code == 0:
            for line in stdout.splitlines():
                if 'The following packages will be REMOVED' in line:
                    continue
                if line.strip().startswith(('Remv', '  ')):
                    # Parse package name
                    parts = line.strip().split()
                    for part in parts:
                        if part and not part.startswith(('(', ')')) and len(part) > 2:
                            orphans.append(part)
        
        if orphans:
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "orphan-packages")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="orphan-packages",
                title="Orphan Packages",
                description=f"{len(orphans)} packages no longer needed",
                icon="trash-2",
                severity=DiscoverySeverity.INFO,
                status=f"{len(orphans)} removable",
                data={
                    "orphan_packages": orphans[:50],
                    "orphan_count": len(orphans),
                },
                actions=[
                    DiscoveryAction(
                        id="clean",
                        label="Remove",
                        icon="trash-2",
                        command="sudo apt autoremove -y",
                        requires_approval=True,
                    ),
                ],
                chat_context=f"{len(orphans)} packages are no longer needed: {', '.join(orphans[:5])}... "
                            f"Run 'sudo apt autoremove' to clean up and free disk space.",
            ))
        
        # Check cache size
        code, stdout, _ = self.run_command(["du", "-sh", "/var/cache/apt/archives"])
        if code == 0:
            cache_size = stdout.split()[0] if stdout.split() else "0"
            # Only report if > 100MB
            if 'G' in cache_size or (cache_size.replace('.', '').isdigit() and float(cache_size.replace('M', '').replace('G', '')) > 100):
                discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "apt-cache")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.PACKAGE,
                    name="apt-cache",
                    title="APT Cache",
                    description=f"Package cache using {cache_size}",
                    icon="database",
                    severity=DiscoverySeverity.INFO,
                    status=cache_size,
                    data={
                        "cache_size": cache_size,
                    },
                    actions=[
                        DiscoveryAction(
                            id="clean",
                            label="Clean Cache",
                            icon="trash-2",
                            command="sudo apt clean",
                            requires_approval=True,
                        ),
                    ],
                    chat_context=f"APT package cache is using {cache_size}. "
                                f"Run 'sudo apt clean' to free this space.",
                ))
        
        return discoveries
    
    def _scan_dnf(self) -> List[Discovery]:
        """Scan dnf-based system (Fedora/RHEL)."""
        discoveries = []
        
        # Check for updates
        code, stdout, _ = self.run_command(
            ["dnf", "check-update", "-q"],
            timeout=60
        )
        
        # dnf check-update returns 100 when updates are available
        if code == 100:
            updates = [line.split()[0] for line in stdout.strip().splitlines() if line.strip()]
            
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "updates-available")
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="updates-available",
                title="Updates Available",
                description=f"{len(updates)} packages can be updated",
                icon="download",
                severity=DiscoverySeverity.INFO,
                status=f"{len(updates)} updates",
                data={
                    "update_count": len(updates),
                    "packages": updates[:20],
                    "package_manager": "dnf",
                },
                actions=[
                    DiscoveryAction(
                        id="update",
                        label="Update All",
                        icon="download",
                        command="sudo dnf upgrade -y",
                        requires_approval=True,
                    ),
                ],
                chat_context=f"{len(updates)} package updates available. Run 'sudo dnf upgrade' to update.",
            ))
        
        return discoveries
    
    def _scan_pacman(self) -> List[Discovery]:
        """Scan pacman-based system (Arch)."""
        discoveries = []
        
        # Check for updates
        code, stdout, _ = self.run_command(["checkupdates"], timeout=60)
        
        if code == 0 and stdout.strip():
            updates = [line.split()[0] for line in stdout.strip().splitlines()]
            
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "updates-available")
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="updates-available",
                title="Updates Available",
                description=f"{len(updates)} packages can be updated",
                icon="download",
                severity=DiscoverySeverity.INFO,
                status=f"{len(updates)} updates",
                data={
                    "update_count": len(updates),
                    "packages": updates[:20],
                    "package_manager": "pacman",
                },
                actions=[
                    DiscoveryAction(
                        id="update",
                        label="Update All",
                        icon="download",
                        command="sudo pacman -Syu --noconfirm",
                        requires_approval=True,
                    ),
                ],
                chat_context=f"{len(updates)} package updates available. Run 'sudo pacman -Syu' to update.",
            ))
        
        # Check for orphans
        code, stdout, _ = self.run_command(["pacman", "-Qdtq"])
        if code == 0 and stdout.strip():
            orphans = stdout.strip().splitlines()
            
            discovery_id = make_discovery_id(DiscoveryType.PACKAGE, "orphan-packages")
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PACKAGE,
                name="orphan-packages",
                title="Orphan Packages",
                description=f"{len(orphans)} packages no longer needed",
                icon="trash-2",
                severity=DiscoverySeverity.INFO,
                status=f"{len(orphans)} removable",
                data={
                    "orphan_packages": orphans,
                    "orphan_count": len(orphans),
                },
                actions=[
                    DiscoveryAction(
                        id="clean",
                        label="Remove",
                        icon="trash-2",
                        command="sudo pacman -Rns $(pacman -Qdtq)",
                        requires_approval=True,
                    ),
                ],
                chat_context=f"{len(orphans)} orphan packages: {', '.join(orphans[:5])}... "
                            f"Run 'sudo pacman -Rns $(pacman -Qdtq)' to remove.",
            ))
        
        return discoveries
    
    def _scan_lock_files(self) -> List[Discovery]:
        """Check for stale package manager lock files."""
        discoveries = []
        
        lock_files = [
            ("/var/lib/dpkg/lock-frontend", "dpkg", "apt"),
            ("/var/lib/dpkg/lock", "dpkg", "apt"),
            ("/var/lib/apt/lists/lock", "apt-lists", "apt"),
            ("/var/cache/apt/archives/lock", "apt-cache", "apt"),
            ("/var/run/yum.pid", "yum", "yum"),
            ("/var/lib/rpm/.rpm.lock", "rpm", "dnf"),
            ("/var/lib/pacman/db.lck", "pacman", "pacman"),
        ]
        
        for lock_path, lock_name, pkg_manager in lock_files:
            if Path(lock_path).exists():
                # Check if the lock is stale (process holding it doesn't exist)
                code, stdout, _ = self.run_command(["fuser", lock_path])
                
                if code == 0 and stdout.strip():
                    # Lock is held by a process
                    pids = stdout.strip().split()
                    
                    # Check if it's a real process or stale
                    code2, ps_out, _ = self.run_command(["ps", "-p", pids[0], "-o", "comm="])
                    if code2 == 0 and ps_out.strip():
                        # Real process holding lock - this is normal during updates
                        continue
                
                # Potentially stale lock
                discovery_id = make_discovery_id(DiscoveryType.PACKAGE, f"lock-{lock_name}")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.PACKAGE,
                    name=f"lock-{lock_name}",
                    title=f"Package Lock: {lock_name}",
                    description=f"Lock file exists at {lock_path}",
                    icon="lock",
                    severity=DiscoverySeverity.WARNING,
                    status="Locked",
                    data={
                        "lock_path": lock_path,
                        "lock_name": lock_name,
                        "package_manager": pkg_manager,
                        "is_lock_issue": True,
                    },
                    actions=[
                        DiscoveryAction(
                            id="remove-lock",
                            label="Remove Lock",
                            icon="unlock",
                            command=f"sudo rm -f {lock_path}",
                            requires_approval=True,
                            danger=True,
                        ),
                    ],
                    chat_context=f"Package manager lock file exists at {lock_path}. "
                                f"This may prevent package operations. "
                                f"If no update is running, it may be stale and can be removed with 'sudo rm -f {lock_path}'.",
                ))
        
        return discoveries
