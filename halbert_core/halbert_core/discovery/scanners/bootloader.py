# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Bootloader Scanner - GRUB and boot configuration.

Common forum questions this addresses:
- "GRUB rescue mode / can't boot"
- "Dual boot Windows entry missing"
- "Boot menu timeout too short/long"
- "Added kernel parameters but they don't work"
- "Secure Boot issues"
- "UEFI vs Legacy BIOS?"
- "Can't boot after update"

Discovers:
- Boot mode (UEFI/Legacy)
- Secure Boot status
- GRUB configuration
- Boot entries
- Kernel command line parameters
- Last boot kernel
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


class BootloaderScanner(BaseScanner):
    """
    Scanner for bootloader and boot configuration.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.SYSTEM_PRESERVATION
    
    def scan(self) -> List[Discovery]:
        """Scan bootloader configuration."""
        discoveries = []
        
        discoveries.extend(self._scan_boot_mode())
        discoveries.extend(self._scan_secure_boot())
        discoveries.extend(self._scan_grub_config())
        discoveries.extend(self._scan_kernel_cmdline())
        discoveries.extend(self._scan_boot_entries())
        
        self.logger.info(f"Found {len(discoveries)} bootloader discoveries")
        return discoveries
    
    def _scan_boot_mode(self) -> List[Discovery]:
        """Detect UEFI vs Legacy BIOS boot."""
        discoveries = []
        
        efi_dir = Path("/sys/firmware/efi")
        is_uefi = efi_dir.exists()
        
        mode = "UEFI" if is_uefi else "Legacy BIOS"
        
        # Get more UEFI details
        efi_vars = None
        if is_uefi:
            efi_vars_dir = efi_dir / "efivars"
            if efi_vars_dir.exists():
                efi_vars = len(list(efi_vars_dir.iterdir()))
        
        discovery_id = make_discovery_id(DiscoveryType.SYSTEM_PRESERVATION, "boot-mode")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SYSTEM_PRESERVATION,
            name="boot-mode",
            title="Boot Mode",
            description=f"System booted in {mode}",
            icon="power",
            severity=DiscoverySeverity.SUCCESS,
            status=mode,
            data={
                "boot_mode": mode,
                "is_uefi": is_uefi,
                "efi_vars_count": efi_vars,
                "is_boot_mode": True,
            },
            chat_context=f"System booted in {mode} mode. "
                        f"{'UEFI provides Secure Boot, faster boot, GPT support. ' if is_uefi else 'Legacy BIOS uses MBR partitioning. '}"
                        f"Boot issues? Check {'efibootmgr' if is_uefi else 'grub-install'}.",
        ))
        
        return discoveries
    
    def _scan_secure_boot(self) -> List[Discovery]:
        """Check Secure Boot status."""
        discoveries = []
        
        # Check mokutil for Secure Boot status
        code, stdout, _ = self.run_command(["mokutil", "--sb-state"])
        
        if code == 0:
            secure_boot_enabled = "SecureBoot enabled" in stdout
            status = "Enabled" if secure_boot_enabled else "Disabled"
            
            issues = []
            if secure_boot_enabled:
                # Check for unsigned kernel modules
                code2, stdout2, _ = self.run_command(["lsmod"])
                # Common unsigned modules
                unsigned_modules = ["nvidia", "vboxdrv", "virtualbox"]
                loaded_unsigned = [m for m in unsigned_modules if m in stdout2.lower()]
                if loaded_unsigned:
                    issues.append(f"Unsigned modules loaded: {', '.join(loaded_unsigned)}")
            
            severity = DiscoverySeverity.WARNING if issues else DiscoverySeverity.SUCCESS
            
            discovery_id = make_discovery_id(DiscoveryType.SYSTEM_PRESERVATION, "secure-boot")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SYSTEM_PRESERVATION,
                name="secure-boot",
                title="Secure Boot",
                description=f"Secure Boot is {status}",
                icon="shield",
                severity=severity,
                status=status,
                status_detail="; ".join(issues) if issues else None,
                data={
                    "enabled": secure_boot_enabled,
                    "issues": issues,
                    "is_secure_boot": True,
                },
                chat_context=f"Secure Boot is {status}. "
                            f"{'⚠️ ' + '; '.join(issues) + ' - may cause issues. ' if issues else ''}"
                            f"{'Disable Secure Boot in UEFI settings if you need unsigned drivers (NVIDIA, VirtualBox). ' if secure_boot_enabled and issues else ''}",
            ))
        
        return discoveries
    
    def _scan_grub_config(self) -> List[Discovery]:
        """Scan GRUB configuration."""
        discoveries = []
        
        grub_default = Path("/etc/default/grub")
        if not grub_default.exists():
            return discoveries
        
        config = {}
        grub_content = grub_default.read_text()
        
        for line in grub_content.splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip().strip('"')
        
        timeout = config.get("GRUB_TIMEOUT", "Unknown")
        default_entry = config.get("GRUB_DEFAULT", "0")
        cmdline = config.get("GRUB_CMDLINE_LINUX_DEFAULT", "")
        
        discovery_id = make_discovery_id(DiscoveryType.SYSTEM_PRESERVATION, "grub-config")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SYSTEM_PRESERVATION,
            name="grub-config",
            title="GRUB Configuration",
            description=f"Timeout: {timeout}s, Default: {default_entry}",
            icon="settings",
            severity=DiscoverySeverity.SUCCESS,
            status=f"Timeout: {timeout}s",
            source="/etc/default/grub",
            data={
                "timeout": timeout,
                "default_entry": default_entry,
                "cmdline_default": cmdline,
                "all_config": config,
                "is_grub_config": True,
            },
            actions=[
                DiscoveryAction(
                    id="edit",
                    label="Edit Config",
                    icon="edit",
                ),
                DiscoveryAction(
                    id="update",
                    label="Update GRUB",
                    icon="refresh-cw",
                    command="sudo update-grub",
                    requires_approval=True,
                ),
            ],
            chat_context=f"GRUB bootloader config: timeout={timeout}s, default={default_entry}. "
                        f"Kernel params: {cmdline[:100]}... "
                        f"Edit /etc/default/grub then run 'sudo update-grub' to apply changes.",
        ))
        
        return discoveries
    
    def _scan_kernel_cmdline(self) -> List[Discovery]:
        """Scan current kernel command line."""
        discoveries = []
        
        cmdline_file = Path("/proc/cmdline")
        if not cmdline_file.exists():
            return discoveries
        
        cmdline = cmdline_file.read_text().strip()
        
        # Parse notable parameters
        params = cmdline.split()
        notable = {
            "quiet": "quiet" in params,
            "splash": "splash" in params,
            "nomodeset": "nomodeset" in params,
            "nvidia-drm.modeset": any("nvidia-drm.modeset" in p for p in params),
            "intel_iommu": any("intel_iommu" in p for p in params),
            "amd_iommu": any("amd_iommu" in p for p in params),
        }
        
        # Detect potential issues
        issues = []
        if notable["nomodeset"]:
            issues.append("nomodeset is set - disables GPU drivers, limits resolution")
        
        severity = DiscoverySeverity.WARNING if issues else DiscoverySeverity.SUCCESS
        
        discovery_id = make_discovery_id(DiscoveryType.SYSTEM_PRESERVATION, "kernel-cmdline")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SYSTEM_PRESERVATION,
            name="kernel-cmdline",
            title="Kernel Command Line",
            description=f"{len(params)} boot parameters",
            icon="terminal",
            severity=severity,
            status=f"{len(params)} params",
            status_detail="; ".join(issues) if issues else None,
            data={
                "cmdline": cmdline,
                "param_count": len(params),
                "notable": notable,
                "issues": issues,
                "is_cmdline": True,
            },
            chat_context=f"Kernel booted with {len(params)} parameters. "
                        f"{'Issues: ' + '; '.join(issues) + '. ' if issues else ''}"
                        f"Notable: quiet={'yes' if notable['quiet'] else 'no'}, nomodeset={'yes' if notable['nomodeset'] else 'no'}. "
                        f"Add kernel params in /etc/default/grub GRUB_CMDLINE_LINUX_DEFAULT.",
        ))
        
        return discoveries
    
    def _scan_boot_entries(self) -> List[Discovery]:
        """Scan UEFI boot entries."""
        discoveries = []
        
        # Only for UEFI systems
        if not Path("/sys/firmware/efi").exists():
            return discoveries
        
        code, stdout, _ = self.run_command(["efibootmgr", "-v"])
        if code != 0:
            return discoveries
        
        entries = []
        boot_order = []
        current = None
        
        for line in stdout.splitlines():
            # Boot order: BootOrder: 0000,0001,0002
            if line.startswith("BootOrder:"):
                boot_order = line.split(":")[1].strip().split(",")
            # Current: BootCurrent: 0001
            elif line.startswith("BootCurrent:"):
                current = line.split(":")[1].strip()
            # Entries: Boot0001* ubuntu HD(1,GPT,...)
            elif line.startswith("Boot") and "*" in line:
                match = re.match(r'Boot(\w{4})\*?\s+(.+?)(?:\t|$)', line)
                if match:
                    entry_id = match.group(1)
                    entry_name = match.group(2).strip()
                    entries.append({
                        "id": entry_id,
                        "name": entry_name,
                        "is_current": entry_id == current,
                    })
        
        if entries:
            discovery_id = make_discovery_id(DiscoveryType.SYSTEM_PRESERVATION, "boot-entries")
            
            entries_desc = ", ".join([e["name"] for e in entries[:5]])
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SYSTEM_PRESERVATION,
                name="boot-entries",
                title="UEFI Boot Entries",
                description=f"{len(entries)} entries: {entries_desc}",
                icon="list",
                severity=DiscoverySeverity.SUCCESS,
                status=f"{len(entries)} entries",
                data={
                    "entries": entries,
                    "boot_order": boot_order,
                    "current": current,
                    "is_boot_entries": True,
                },
                chat_context=f"UEFI has {len(entries)} boot entries: {entries_desc}. "
                            f"Current boot: {current}. "
                            f"Manage with 'efibootmgr'. Missing Windows? Try 'sudo update-grub' or add manually.",
            ))
        
        return discoveries
