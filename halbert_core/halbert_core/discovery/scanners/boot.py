# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Boot Scanner - Discover boot configuration and performance.

Enables scenarios:
- S2.4: "Boot time reduction" → Boot time analysis, slow services
- S10.1: "Boot failure recovery" → Boot errors, grub config
- S10.2: "Rollback recent changes" → Kernel versions, boot entries

Discovers:
- Boot time breakdown (kernel, userspace, services)
- Slow services during boot
- Boot errors from journal
- Available kernels and boot entries
- GRUB configuration
"""

from __future__ import annotations
from typing import List, Dict, Optional
from pathlib import Path
import re

from .base import BaseScanner
from ..schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class BootScanner(BaseScanner):
    """
    Scanner for boot configuration and boot performance.
    
    Discovers:
    - Boot time analysis (systemd-analyze)
    - Slow boot services
    - Boot errors
    - Available kernels
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.SYSTEM_PRESERVATION
    
    def scan(self) -> List[Discovery]:
        """Scan boot information."""
        discoveries = []
        
        discoveries.extend(self._scan_boot_time())
        discoveries.extend(self._scan_slow_services())
        discoveries.extend(self._scan_boot_errors())
        discoveries.extend(self._scan_kernels())
        
        self.logger.info(f"Found {len(discoveries)} boot discoveries")
        return discoveries
    
    def _scan_boot_time(self) -> List[Discovery]:
        """Analyze boot time using systemd-analyze."""
        discoveries = []
        
        code, stdout, _ = self.run_command(["systemd-analyze"], timeout=10)
        
        if code != 0:
            return discoveries
        
        # Parse output like: "Startup finished in 3.5s (kernel) + 12.3s (userspace) = 15.8s"
        kernel_time = 0.0
        userspace_time = 0.0
        total_time = 0.0
        
        match = re.search(r'(\d+\.?\d*)s \(kernel\)', stdout)
        if match:
            kernel_time = float(match.group(1))
        
        match = re.search(r'(\d+\.?\d*)s \(userspace\)', stdout)
        if match:
            userspace_time = float(match.group(1))
        
        match = re.search(r'= (\d+\.?\d*)s', stdout)
        if match:
            total_time = float(match.group(1))
        
        # Determine severity based on boot time
        if total_time > 60:
            severity = DiscoverySeverity.WARNING
            status = f"Slow: {total_time:.1f}s"
        elif total_time > 30:
            severity = DiscoverySeverity.INFO
            status = f"Normal: {total_time:.1f}s"
        else:
            severity = DiscoverySeverity.SUCCESS
            status = f"Fast: {total_time:.1f}s"
        
        discovery_id = make_discovery_id(DiscoveryType.SYSTEM_PRESERVATION, "boot-time")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SYSTEM_PRESERVATION,
            name="boot-time",
            title="Boot Time Analysis",
            description=f"Last boot: {total_time:.1f}s (kernel: {kernel_time:.1f}s + userspace: {userspace_time:.1f}s)",
            icon="clock",
            severity=severity,
            status=status,
            data={
                "kernel_time_sec": kernel_time,
                "userspace_time_sec": userspace_time,
                "total_time_sec": total_time,
                "raw_output": stdout.strip(),
            },
            chat_context=f"Last boot took {total_time:.1f} seconds. "
                        f"Kernel initialization: {kernel_time:.1f}s. "
                        f"Userspace startup: {userspace_time:.1f}s. "
                        f"{'⚠️ Boot time is slow, consider analyzing slow services.' if total_time > 60 else ''}",
        ))
        
        return discoveries
    
    def _scan_slow_services(self) -> List[Discovery]:
        """Find services that slow down boot."""
        discoveries = []
        
        code, stdout, _ = self.run_command(["systemd-analyze", "blame"], timeout=15)
        
        if code != 0:
            return discoveries
        
        # Parse output: "    12.345s service-name.service"
        slow_services = []
        for line in stdout.strip().splitlines()[:20]:  # Top 20
            match = re.match(r'\s*(\d+\.?\d*)(ms|s)\s+(\S+)', line)
            if match:
                time_val = float(match.group(1))
                time_unit = match.group(2)
                service = match.group(3)
                
                # Convert to seconds
                if time_unit == 'ms':
                    time_sec = time_val / 1000.0
                else:
                    time_sec = time_val
                
                if time_sec >= 1.0:  # Only services taking >= 1 second
                    slow_services.append((service, time_sec))
        
        for service, time_sec in slow_services[:10]:
            if time_sec > 10:
                severity = DiscoverySeverity.WARNING
            else:
                severity = DiscoverySeverity.INFO
            
            service_name = service.replace('.service', '')
            discovery_id = make_discovery_id(DiscoveryType.SYSTEM_PRESERVATION, f"boot-slow-{service_name}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SYSTEM_PRESERVATION,
                name=f"boot-slow-{service_name}",
                title=f"Slow Boot: {service_name}",
                description=f"Takes {time_sec:.1f}s during boot",
                icon="clock",
                severity=severity,
                status=f"{time_sec:.1f}s",
                data={
                    "service": service,
                    "service_name": service_name,
                    "boot_time_sec": time_sec,
                    "is_slow_boot_service": True,
                },
                actions=[
                    DiscoveryAction(
                        id="analyze",
                        label="Analyze",
                        icon="search",
                    ),
                    DiscoveryAction(
                        id="disable",
                        label="Disable",
                        icon="power-off",
                        command=f"sudo systemctl disable {service}",
                        requires_approval=True,
                    ),
                ],
                chat_context=f"Service '{service_name}' takes {time_sec:.1f} seconds during boot. "
                            f"{'Consider disabling or optimizing this service to speed up boot.' if time_sec > 10 else ''}",
            ))
        
        return discoveries
    
    def _scan_boot_errors(self) -> List[Discovery]:
        """Find errors from the current boot."""
        discoveries = []
        
        # Get errors from current boot
        code, stdout, _ = self.run_command([
            "journalctl", "-b", "-p", "err", "--no-pager", "-n", "50"
        ], timeout=15)
        
        if code != 0 or not stdout.strip():
            return discoveries
        
        error_count = len(stdout.strip().splitlines())
        
        if error_count > 20:
            severity = DiscoverySeverity.WARNING
            status = f"{error_count} errors"
        elif error_count > 0:
            severity = DiscoverySeverity.INFO
            status = f"{error_count} errors"
        else:
            return discoveries
        
        discovery_id = make_discovery_id(DiscoveryType.SYSTEM_PRESERVATION, "boot-errors")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SYSTEM_PRESERVATION,
            name="boot-errors",
            title="Boot Errors",
            description=f"{error_count} errors logged during boot",
            icon="alert-circle",
            severity=severity,
            status=status,
            data={
                "error_count": error_count,
                "sample_errors": stdout.strip().splitlines()[:10],
            },
            chat_context=f"Found {error_count} errors in the current boot journal. "
                        f"Review with 'journalctl -b -p err' for details.",
        ))
        
        return discoveries
    
    def _scan_kernels(self) -> List[Discovery]:
        """Discover available kernels."""
        discoveries = []
        
        # Get current kernel
        code, current_kernel, _ = self.run_command(["uname", "-r"])
        current_kernel = current_kernel.strip() if code == 0 else "unknown"
        
        # List installed kernels
        kernels = []
        
        # Try /boot/vmlinuz-*
        vmlinuz_files = list(Path("/boot").glob("vmlinuz-*"))
        for vmlinuz in vmlinuz_files:
            kernel_version = vmlinuz.name.replace("vmlinuz-", "")
            kernels.append(kernel_version)
        
        # Sort kernels (newest first typically)
        kernels.sort(reverse=True)
        
        if not kernels:
            return discoveries
        
        discovery_id = make_discovery_id(DiscoveryType.SYSTEM_PRESERVATION, "kernels")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SYSTEM_PRESERVATION,
            name="kernels",
            title="Installed Kernels",
            description=f"Current: {current_kernel}, {len(kernels)} installed",
            icon="cpu",
            severity=DiscoverySeverity.SUCCESS,
            status=f"Running {current_kernel}",
            data={
                "current_kernel": current_kernel,
                "installed_kernels": kernels,
                "kernel_count": len(kernels),
            },
            chat_context=f"Currently running kernel {current_kernel}. "
                        f"{len(kernels)} kernel(s) available: {', '.join(kernels[:5])}. "
                        f"Can boot to a previous kernel if current one has issues.",
        ))
        
        return discoveries
