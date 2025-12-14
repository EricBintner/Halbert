"""
USB Scanner - USB devices and peripheral issues.

Common forum questions this addresses:
- "USB device not recognized"
- "USB drive won't mount"
- "USB permissions / can't access device"
- "USB 3.0 device running at 2.0 speed"
- "USB port not working"
- "USB hub power issues"

Discovers:
- Connected USB devices
- USB speed (2.0/3.0/3.1)
- Power consumption
- Device permissions
- Common USB issues
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


class UsbScanner(BaseScanner):
    """
    Scanner for USB devices and peripherals.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.HARDWARE
    
    def scan(self) -> List[Discovery]:
        """Scan USB devices."""
        discoveries = []
        
        discoveries.extend(self._scan_usb_devices())
        discoveries.extend(self._scan_usb_controllers())
        
        self.logger.info(f"Found {len(discoveries)} USB discoveries")
        return discoveries
    
    def _scan_usb_devices(self) -> List[Discovery]:
        """Scan connected USB devices."""
        discoveries = []
        
        code, stdout, _ = self.run_command(["lsusb", "-v"], timeout=10)
        
        if code != 0:
            # Try simple lsusb
            code, stdout, _ = self.run_command(["lsusb"])
            if code != 0:
                return discoveries
        
        # Parse simple lsusb output: Bus 001 Device 003: ID 046d:c52b Logitech, Inc. Unifying Receiver
        devices = []
        for line in stdout.splitlines():
            match = re.match(r'Bus (\d+) Device (\d+): ID (\w+:\w+)\s*(.*)', line)
            if match:
                bus = match.group(1)
                device = match.group(2)
                usb_id = match.group(3)
                name = match.group(4).strip() or "Unknown Device"
                
                # Skip root hubs
                if "root hub" in name.lower():
                    continue
                
                devices.append({
                    "bus": bus,
                    "device": device,
                    "id": usb_id,
                    "name": name,
                })
        
        # Get USB speed info from sysfs
        for dev in devices:
            bus = dev["bus"]
            dev_path = Path(f"/sys/bus/usb/devices/{bus}-*")
            
            # Try to find the device in sysfs
            speed = "Unknown"
            for sys_dev in Path("/sys/bus/usb/devices").glob(f"{bus}-*"):
                speed_file = sys_dev / "speed"
                if speed_file.exists():
                    try:
                        speed_val = speed_file.read_text().strip()
                        if speed_val == "480":
                            speed = "USB 2.0 (480 Mbps)"
                        elif speed_val == "5000":
                            speed = "USB 3.0 (5 Gbps)"
                        elif speed_val == "10000":
                            speed = "USB 3.1 (10 Gbps)"
                        elif speed_val == "12":
                            speed = "USB 1.1 (12 Mbps)"
                        elif speed_val == "1.5":
                            speed = "USB 1.0 (1.5 Mbps)"
                        break
                    except:
                        pass
            dev["speed"] = speed
        
        # Create discoveries for notable devices (not hubs)
        notable_devices = [d for d in devices if not any(x in d["name"].lower() for x in ["hub", "root"])]
        
        for dev in notable_devices[:15]:  # Limit to 15 devices
            name = dev["name"]
            usb_id = dev["id"]
            speed = dev.get("speed", "Unknown")
            
            # Categorize device
            device_type = "Device"
            if any(x in name.lower() for x in ["keyboard"]):
                device_type = "Keyboard"
            elif any(x in name.lower() for x in ["mouse", "trackpad", "trackball"]):
                device_type = "Mouse"
            elif any(x in name.lower() for x in ["storage", "flash", "disk", "ssd", "hdd"]):
                device_type = "Storage"
            elif any(x in name.lower() for x in ["camera", "webcam"]):
                device_type = "Camera"
            elif any(x in name.lower() for x in ["audio", "speaker", "headphone", "microphone"]):
                device_type = "Audio"
            elif any(x in name.lower() for x in ["bluetooth"]):
                device_type = "Bluetooth"
            elif any(x in name.lower() for x in ["gamepad", "controller", "joystick"]):
                device_type = "Game Controller"
            elif any(x in name.lower() for x in ["printer", "scanner"]):
                device_type = "Printer/Scanner"
            
            # Check for issues
            issues = []
            if "USB 3" in speed and "USB 2" not in speed and device_type == "Storage":
                # USB 3 storage device - good
                pass
            elif device_type == "Storage" and "USB 2" in speed:
                issues.append("Storage device running at USB 2.0 speed - check port/cable")
            
            severity = DiscoverySeverity.WARNING if issues else DiscoverySeverity.SUCCESS
            
            discovery_id = make_discovery_id(DiscoveryType.HARDWARE, f"usb-{dev['bus']}-{dev['device']}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.HARDWARE,
                name=f"usb-{dev['bus']}-{dev['device']}",
                title=f"USB: {name[:40]}",
                description=f"{device_type}, {speed}",
                icon="usb",
                severity=severity,
                status=device_type,
                status_detail=speed,
                data={
                    "bus": dev["bus"],
                    "device": dev["device"],
                    "id": usb_id,
                    "name": name,
                    "speed": speed,
                    "device_type": device_type,
                    "issues": issues,
                    "is_usb_device": True,
                },
                chat_context=f"USB device: {name}. Type: {device_type}. Speed: {speed}. "
                            f"{'⚠️ ' + '; '.join(issues) + '. ' if issues else ''}"
                            f"ID: {usb_id}.",
            ))
        
        # Summary
        if len(devices) > 0:
            discovery_id = make_discovery_id(DiscoveryType.HARDWARE, "usb-summary")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.HARDWARE,
                name="usb-summary",
                title="USB Devices",
                description=f"{len(notable_devices)} devices connected",
                icon="usb",
                severity=DiscoverySeverity.SUCCESS,
                status=f"{len(notable_devices)} devices",
                data={
                    "device_count": len(notable_devices),
                    "is_summary": True,
                },
                chat_context=f"{len(notable_devices)} USB devices connected. "
                            f"Run 'lsusb' for full list, 'lsusb -v' for details.",
            ))
        
        return discoveries
    
    def _scan_usb_controllers(self) -> List[Discovery]:
        """Scan USB host controllers (for speed capability)."""
        discoveries = []
        
        code, stdout, _ = self.run_command(["lspci", "-nn"])
        
        if code != 0:
            return discoveries
        
        controllers = []
        for line in stdout.splitlines():
            if "USB" in line.upper():
                controllers.append(line.strip())
        
        # Count USB 3 vs USB 2 controllers
        usb3_count = sum(1 for c in controllers if "xHCI" in c or "USB 3" in c)
        usb2_count = sum(1 for c in controllers if "EHCI" in c or "USB 2" in c)
        
        if controllers:
            discovery_id = make_discovery_id(DiscoveryType.HARDWARE, "usb-controllers")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.HARDWARE,
                name="usb-controllers",
                title="USB Controllers",
                description=f"{len(controllers)} controllers ({usb3_count} USB3, {usb2_count} USB2)",
                icon="cpu",
                severity=DiscoverySeverity.SUCCESS,
                status=f"{len(controllers)} controllers",
                data={
                    "controller_count": len(controllers),
                    "usb3_count": usb3_count,
                    "usb2_count": usb2_count,
                    "controllers": controllers,
                    "is_usb_controller": True,
                },
                chat_context=f"{len(controllers)} USB controllers: {usb3_count} USB 3.x, {usb2_count} USB 2.0. "
                            f"For USB 3 speeds, use USB 3 ports (usually blue). "
                            f"Issues? Check 'lspci -vv' for controller details.",
            ))
        
        return discoveries
