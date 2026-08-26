# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Virtualization Scanner - VM detection and hypervisor info.

Common forum questions this addresses:
- "Am I running in a VM?"
- "KVM/QEMU performance issues"
- "VirtualBox guest additions not working"
- "VMware tools not installed"
- "Nested virtualization not working"
- "VT-x/AMD-V not enabled"

Discovers:
- Whether running in a VM
- VM type (KVM, VirtualBox, VMware, etc.)
- Hardware virtualization support
- Guest tools status
- Hypervisor info (if host)
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


class VirtualizationScanner(BaseScanner):
    """
    Scanner for virtualization detection and configuration.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.HARDWARE
    
    def scan(self) -> List[Discovery]:
        """Scan virtualization environment."""
        discoveries = []
        
        discoveries.extend(self._detect_vm())
        discoveries.extend(self._check_hw_virtualization())
        discoveries.extend(self._scan_hypervisor())
        
        self.logger.info(f"Found {len(discoveries)} virtualization discoveries")
        return discoveries
    
    def _detect_vm(self) -> List[Discovery]:
        """Detect if running inside a VM."""
        discoveries = []
        
        # Use systemd-detect-virt
        code, stdout, _ = self.run_command(["systemd-detect-virt"])
        
        virt_type = stdout.strip() if code == 0 else "none"
        is_vm = virt_type != "none"
        
        if is_vm:
            # Determine VM type details
            vm_info = {
                "kvm": ("KVM/QEMU", "Install qemu-guest-agent for better integration"),
                "qemu": ("QEMU", "Install qemu-guest-agent"),
                "vmware": ("VMware", "Install open-vm-tools for better performance"),
                "oracle": ("VirtualBox", "Install virtualbox-guest-utils"),
                "virtualbox": ("VirtualBox", "Install virtualbox-guest-utils"),
                "xen": ("Xen", "PV drivers should be automatic"),
                "microsoft": ("Hyper-V", "Install hyperv-daemons"),
                "parallels": ("Parallels", "Install parallels tools"),
                "lxc": ("LXC Container", "Container, not full VM"),
                "docker": ("Docker Container", "Container, not full VM"),
                "podman": ("Podman Container", "Container, not full VM"),
                "wsl": ("WSL", "Windows Subsystem for Linux"),
            }
            
            vm_name, suggestion = vm_info.get(virt_type, (virt_type.title(), ""))
            
            # Check for guest tools
            guest_tools_installed = False
            if virt_type in ["kvm", "qemu"]:
                code, _, _ = self.run_command(["pgrep", "qemu-ga"])
                guest_tools_installed = code == 0
            elif virt_type in ["vmware"]:
                code, _, _ = self.run_command(["pgrep", "vmtoolsd"])
                guest_tools_installed = code == 0
            elif virt_type in ["oracle", "virtualbox"]:
                code, _, _ = self.run_command(["lsmod"])
                # Check for vboxguest module
                code2, stdout2, _ = self.run_command(["lsmod"])
                guest_tools_installed = "vboxguest" in stdout2 if code2 == 0 else False
            
            issues = []
            if not guest_tools_installed and virt_type not in ["lxc", "docker", "podman", "wsl"]:
                issues.append(f"Guest tools not detected - {suggestion}")
            
            severity = DiscoverySeverity.INFO if guest_tools_installed else DiscoverySeverity.WARNING
            
            discovery_id = make_discovery_id(DiscoveryType.HARDWARE, "virtualization")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.HARDWARE,
                name="virtualization",
                title="Virtual Machine Detected",
                description=f"Running in {vm_name}",
                icon="server",
                severity=severity,
                status=vm_name,
                status_detail="Guest tools: " + ("Installed" if guest_tools_installed else "Not detected"),
                data={
                    "is_vm": True,
                    "virt_type": virt_type,
                    "vm_name": vm_name,
                    "guest_tools_installed": guest_tools_installed,
                    "issues": issues,
                    "is_virtualization": True,
                },
                chat_context=f"Running inside {vm_name} virtual machine. "
                            f"Guest tools: {'installed' if guest_tools_installed else 'not detected'}. "
                            f"{'⚠️ ' + '; '.join(issues) if issues else ''}",
            ))
        else:
            # Running on bare metal
            discovery_id = make_discovery_id(DiscoveryType.HARDWARE, "virtualization")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.HARDWARE,
                name="virtualization",
                title="Bare Metal",
                description="Running on physical hardware",
                icon="server",
                severity=DiscoverySeverity.SUCCESS,
                status="Physical",
                data={
                    "is_vm": False,
                    "virt_type": "none",
                    "is_virtualization": True,
                },
                chat_context="Running on physical hardware (not a VM).",
            ))
        
        return discoveries
    
    def _check_hw_virtualization(self) -> List[Discovery]:
        """Check CPU virtualization support (VT-x/AMD-V)."""
        discoveries = []
        
        # Check /proc/cpuinfo for vmx (Intel) or svm (AMD)
        cpuinfo = Path("/proc/cpuinfo")
        if not cpuinfo.exists():
            return discoveries
        
        content = cpuinfo.read_text()
        
        has_intel_vt = "vmx" in content
        has_amd_v = "svm" in content
        has_hw_virt = has_intel_vt or has_amd_v
        
        virt_tech = "Intel VT-x" if has_intel_vt else ("AMD-V" if has_amd_v else "Not detected")
        
        # Check if KVM module is loaded
        code, stdout, _ = self.run_command(["lsmod"])
        kvm_loaded = "kvm" in stdout if code == 0 else False
        
        issues = []
        if not has_hw_virt:
            issues.append("Hardware virtualization not detected in CPU flags - may need BIOS enable")
        
        severity = DiscoverySeverity.SUCCESS if has_hw_virt else DiscoverySeverity.INFO
        
        discovery_id = make_discovery_id(DiscoveryType.HARDWARE, "hw-virtualization")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.HARDWARE,
            name="hw-virtualization",
            title="Hardware Virtualization",
            description=f"{virt_tech}" + (", KVM loaded" if kvm_loaded else ""),
            icon="cpu",
            severity=severity,
            status=virt_tech,
            status_detail="KVM: " + ("Loaded" if kvm_loaded else "Not loaded"),
            data={
                "has_hw_virt": has_hw_virt,
                "intel_vt": has_intel_vt,
                "amd_v": has_amd_v,
                "kvm_loaded": kvm_loaded,
                "issues": issues,
                "is_hw_virt": True,
            },
            chat_context=f"Hardware virtualization: {virt_tech}. "
                        f"{'KVM module loaded. ' if kvm_loaded else ''}"
                        f"{'⚠️ ' + issues[0] + ' ' if issues else ''}"
                        f"Enable VT-x/AMD-V in BIOS/UEFI for VM hosting.",
        ))
        
        return discoveries
    
    def _scan_hypervisor(self) -> List[Discovery]:
        """Scan for hypervisor capabilities (libvirt, VirtualBox, etc.)."""
        discoveries = []
        
        # Check for libvirt/KVM
        code, stdout, _ = self.run_command(["virsh", "list", "--all"], timeout=5)
        if code == 0:
            # Count VMs
            vms = [l for l in stdout.splitlines() if l.strip() and not l.strip().startswith('Id') and not l.strip().startswith('--')]
            running = sum(1 for v in vms if 'running' in v.lower())
            
            discovery_id = make_discovery_id(DiscoveryType.HARDWARE, "libvirt")
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.HARDWARE,
                name="libvirt",
                title="Libvirt/KVM",
                description=f"{len(vms)} VMs ({running} running)",
                icon="server",
                severity=DiscoverySeverity.SUCCESS,
                status=f"{running} running",
                data={
                    "vm_count": len(vms),
                    "running_count": running,
                    "is_hypervisor": True,
                },
                chat_context=f"Libvirt/KVM hypervisor: {len(vms)} VMs defined, {running} running. "
                            f"Manage with 'virsh' or virt-manager.",
            ))
        
        # Check for VirtualBox
        code, stdout, _ = self.run_command(["VBoxManage", "list", "vms"], timeout=5)
        if code == 0:
            vms = [l for l in stdout.splitlines() if l.strip()]
            
            # Get running VMs
            code2, stdout2, _ = self.run_command(["VBoxManage", "list", "runningvms"])
            running = len([l for l in stdout2.splitlines() if l.strip()]) if code2 == 0 else 0
            
            discovery_id = make_discovery_id(DiscoveryType.HARDWARE, "virtualbox")
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.HARDWARE,
                name="virtualbox",
                title="VirtualBox",
                description=f"{len(vms)} VMs ({running} running)",
                icon="box",
                severity=DiscoverySeverity.SUCCESS,
                status=f"{running} running",
                data={
                    "vm_count": len(vms),
                    "running_count": running,
                    "is_hypervisor": True,
                },
                chat_context=f"VirtualBox: {len(vms)} VMs, {running} running. "
                            f"Manage with 'VBoxManage' or VirtualBox GUI.",
            ))
        
        return discoveries
