# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Laptop Scanner - Laptop-specific hardware and power management.

Common forum questions this addresses:
- "Why does my laptop drain battery so fast?"
- "Suspend doesn't work / laptop won't wake up"
- "Lid close does nothing / wrong action"
- "Battery shows wrong percentage"
- "Laptop runs hot on battery"
- "TLP/power-profiles-daemon not working"

Discovers:
- Battery health, cycle count, wear level
- Power profile (performance/balanced/power-saver)
- TLP status if installed
- Suspend/hibernate capability
- Lid switch configuration
- Backlight control availability
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
from ...system.display_power import iter_backlight_interfaces


class LaptopScanner(BaseScanner):
    """
    Scanner for laptop-specific features.
    
    Discovers battery health, power management, suspend capability.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.POWER
    
    def scan(self) -> List[Discovery]:
        """Scan laptop-specific features."""
        discoveries = []
        
        # Only scan if this looks like a laptop
        if not self._is_laptop():
            return discoveries
        
        discoveries.extend(self._scan_battery())
        discoveries.extend(self._scan_power_profile())
        discoveries.extend(self._scan_tlp())
        discoveries.extend(self._scan_suspend())
        discoveries.extend(self._scan_lid_switch())
        discoveries.extend(self._scan_backlight())
        
        self.logger.info(f"Found {len(discoveries)} laptop discoveries")
        return discoveries
    
    def _is_laptop(self) -> bool:
        """Check if this is a laptop."""
        # Check for battery
        if list(Path("/sys/class/power_supply").glob("BAT*")):
            return True
        # Check DMI chassis type
        chassis_file = Path("/sys/class/dmi/id/chassis_type")
        if chassis_file.exists():
            try:
                chassis = int(chassis_file.read_text().strip())
                # 8=Portable, 9=Laptop, 10=Notebook, 11=Hand Held, 14=Sub Notebook
                return chassis in [8, 9, 10, 11, 14]
            except:
                pass
        return False
    
    def _scan_battery(self) -> List[Discovery]:
        """Scan battery health and status."""
        discoveries = []
        
        for bat_path in Path("/sys/class/power_supply").glob("BAT*"):
            bat_name = bat_path.name
            
            # Read battery info
            def read_val(name):
                f = bat_path / name
                return f.read_text().strip() if f.exists() else None
            
            status = read_val("status") or "Unknown"
            capacity = int(read_val("capacity") or 0)
            
            # Calculate wear level if available
            energy_full = read_val("energy_full") or read_val("charge_full")
            energy_design = read_val("energy_full_design") or read_val("charge_full_design")
            
            wear_level = None
            if energy_full and energy_design:
                try:
                    wear_level = 100 - (int(energy_full) / int(energy_design) * 100)
                except:
                    pass
            
            # Get cycle count
            cycle_count = read_val("cycle_count")
            
            # Determine severity
            if wear_level and wear_level > 30:
                severity = DiscoverySeverity.WARNING
                status_detail = f"Worn: {wear_level:.0f}% capacity lost"
            elif capacity < 20 and status != "Charging":
                severity = DiscoverySeverity.WARNING
                status_detail = "Low battery"
            else:
                severity = DiscoverySeverity.SUCCESS
                status_detail = f"Health: {100-wear_level:.0f}%" if wear_level else None
            
            discovery_id = make_discovery_id(DiscoveryType.POWER, f"battery-{bat_name}")
            
            data = {
                "battery": bat_name,
                "status": status,
                "capacity_percent": capacity,
                "is_battery": True,
            }
            if wear_level is not None:
                data["wear_level_percent"] = wear_level
            if cycle_count:
                data["cycle_count"] = int(cycle_count)
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.POWER,
                name=f"battery-{bat_name}",
                title=f"Battery: {bat_name}",
                description=f"{capacity}% - {status}",
                icon="battery",
                severity=severity,
                status=f"{capacity}% ({status})",
                status_detail=status_detail,
                source=str(bat_path),
                data=data,
                chat_context=f"Battery {bat_name}: {capacity}% capacity, status: {status}. "
                            f"{'⚠️ Battery has significant wear (' + str(int(wear_level)) + '% capacity lost). ' if wear_level and wear_level > 20 else ''}"
                            f"{'Cycle count: ' + str(cycle_count) + '. ' if cycle_count else ''}",
            ))
        
        return discoveries
    
    def _scan_power_profile(self) -> List[Discovery]:
        """Scan current power profile."""
        discoveries = []
        
        # Check power-profiles-daemon
        code, stdout, _ = self.run_command(["powerprofilesctl", "get"])
        if code == 0:
            profile = stdout.strip()
            discovery_id = make_discovery_id(DiscoveryType.POWER, "power-profile")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.POWER,
                name="power-profile",
                title="Power Profile",
                description=f"Current profile: {profile}",
                icon="zap",
                severity=DiscoverySeverity.SUCCESS,
                status=profile.title(),
                data={
                    "profile": profile,
                    "daemon": "power-profiles-daemon",
                    "is_power_profile": True,
                },
                actions=[
                    DiscoveryAction(
                        id="balanced",
                        label="Balanced",
                        icon="activity",
                        command="powerprofilesctl set balanced",
                    ),
                    DiscoveryAction(
                        id="power-saver",
                        label="Power Saver",
                        icon="battery",
                        command="powerprofilesctl set power-saver",
                    ),
                    DiscoveryAction(
                        id="performance",
                        label="Performance",
                        icon="zap",
                        command="powerprofilesctl set performance",
                    ),
                ],
                chat_context=f"Power profile is set to '{profile}'. "
                            f"Use 'powerprofilesctl set <profile>' to change. "
                            f"Available: power-saver, balanced, performance.",
            ))
        
        return discoveries
    
    def _scan_tlp(self) -> List[Discovery]:
        """Scan TLP power management status."""
        discoveries = []
        
        code, stdout, _ = self.run_command(["tlp-stat", "-s"], timeout=5)
        if code == 0:
            # Parse TLP status
            mode = "Unknown"
            for line in stdout.splitlines():
                if "Mode" in line:
                    mode = line.split("=")[-1].strip() if "=" in line else line.split()[-1]
                    break
            
            discovery_id = make_discovery_id(DiscoveryType.POWER, "tlp")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.POWER,
                name="tlp",
                title="TLP Power Management",
                description=f"TLP is active, mode: {mode}",
                icon="battery-charging",
                severity=DiscoverySeverity.SUCCESS,
                status=f"Active ({mode})",
                data={
                    "tlp_active": True,
                    "mode": mode,
                    "is_power_manager": True,
                },
                chat_context=f"TLP advanced power management is active in {mode} mode. "
                            f"Run 'tlp-stat' for detailed power info.",
            ))
        
        return discoveries
    
    def _scan_suspend(self) -> List[Discovery]:
        """Scan suspend/hibernate capability."""
        discoveries = []
        
        # Check available sleep states
        sleep_states_file = Path("/sys/power/state")
        if sleep_states_file.exists():
            states = sleep_states_file.read_text().strip().split()
            
            # Check suspend capability
            has_suspend = "mem" in states
            has_hibernate = "disk" in states
            
            # Check for common suspend issues
            issues = []
            
            # Check if secure boot might interfere with hibernate
            secure_boot = Path("/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c")
            if secure_boot.exists() and has_hibernate:
                issues.append("Secure Boot may prevent hibernate")
            
            # Check swap for hibernate
            code, stdout, _ = self.run_command(["swapon", "--show=SIZE", "--noheadings"])
            if code == 0 and not stdout.strip() and has_hibernate:
                issues.append("No swap configured - hibernate requires swap")
            
            status = []
            if has_suspend:
                status.append("Suspend: Yes")
            if has_hibernate:
                status.append("Hibernate: Yes")
            
            severity = DiscoverySeverity.WARNING if issues else DiscoverySeverity.SUCCESS
            
            discovery_id = make_discovery_id(DiscoveryType.POWER, "sleep-states")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.POWER,
                name="sleep-states",
                title="Sleep States",
                description=f"Available: {', '.join(states)}",
                icon="moon",
                severity=severity,
                status="; ".join(status) if status else "Limited",
                status_detail="; ".join(issues) if issues else None,
                data={
                    "states": states,
                    "has_suspend": has_suspend,
                    "has_hibernate": has_hibernate,
                    "issues": issues,
                    "is_sleep_config": True,
                },
                chat_context=f"Sleep states available: {', '.join(states)}. "
                            f"{'Issues: ' + '; '.join(issues) + '. ' if issues else ''}"
                            f"Test with 'systemctl suspend' or 'systemctl hibernate'.",
            ))
        
        return discoveries
    
    def _scan_lid_switch(self) -> List[Discovery]:
        """Scan lid switch configuration."""
        discoveries = []
        
        # Check logind.conf for lid switch action
        logind_conf = Path("/etc/systemd/logind.conf")
        lid_action = "suspend"  # Default
        
        if logind_conf.exists():
            for line in logind_conf.read_text().splitlines():
                if line.startswith("HandleLidSwitch="):
                    lid_action = line.split("=")[1].strip()
                    break
        
        # Check if lid switch works
        lid_state_file = Path("/proc/acpi/button/lid/LID0/state")
        lid_present = lid_state_file.exists()
        
        if lid_present:
            discovery_id = make_discovery_id(DiscoveryType.POWER, "lid-switch")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.POWER,
                name="lid-switch",
                title="Lid Switch",
                description=f"Action: {lid_action}",
                icon="laptop",
                severity=DiscoverySeverity.SUCCESS,
                status=f"Action: {lid_action}",
                data={
                    "lid_action": lid_action,
                    "config_file": str(logind_conf),
                    "is_lid_config": True,
                },
                chat_context=f"Lid switch is configured to '{lid_action}' when closed. "
                            f"Change in /etc/systemd/logind.conf with HandleLidSwitch= setting.",
            ))
        
        return discoveries
    
    def _scan_backlight(self) -> List[Discovery]:
        """Scan backlight control.

        The sysfs walk lives in ``system/display_power.py``
        (``iter_backlight_interfaces``) so the read-only scanner here and
        the write-side screen power daemon describe the same devices with
        the same rules — one discovery path, not two copies of the same
        directory logic.
        """
        discoveries = []

        for name, bl, brightness, max_brightness in iter_backlight_interfaces():
            try:
                percent = int(brightness / max_brightness * 100)

                discovery_id = make_discovery_id(DiscoveryType.POWER, f"backlight-{name}")

                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.POWER,
                    name=f"backlight-{name}",
                    title=f"Backlight: {name}",
                    description=f"Brightness: {percent}%",
                    icon="sun",
                    severity=DiscoverySeverity.SUCCESS,
                    status=f"{percent}%",
                    source=str(bl),
                    data={
                        "interface": name,
                        "brightness": brightness,
                        "max_brightness": max_brightness,
                        "percent": percent,
                        "is_backlight": True,
                    },
                        chat_context=f"Display backlight ({name}) at {percent}%. "
                                  f"Adjust with 'brightnessctl' or keyboard keys.",
                    ))
            except Exception:
                continue

        return discoveries
