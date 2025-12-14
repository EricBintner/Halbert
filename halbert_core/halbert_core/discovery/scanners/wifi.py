"""
WiFi Scanner - Wireless network configuration and issues.

Common forum questions this addresses:
- "WiFi not working after update"
- "WiFi keeps disconnecting"
- "Slow WiFi speed"
- "Can't see 5GHz networks"
- "WiFi driver not loaded"
- "Wrong country code / can't use some channels"
- "WiFi works but no internet"
- "Bluetooth interfering with WiFi"

Discovers:
- WiFi interfaces and drivers
- Current connection status
- Signal strength
- WiFi regulatory domain
- Power management settings
- Available networks (if connected)
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


class WifiScanner(BaseScanner):
    """
    Scanner for WiFi configuration and troubleshooting.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.NETWORK
    
    def scan(self) -> List[Discovery]:
        """Scan WiFi configuration."""
        discoveries = []
        
        discoveries.extend(self._scan_wifi_interfaces())
        discoveries.extend(self._scan_wifi_connection())
        discoveries.extend(self._scan_wifi_regulatory())
        discoveries.extend(self._scan_wifi_power_mgmt())
        
        self.logger.info(f"Found {len(discoveries)} WiFi discoveries")
        return discoveries
    
    def _scan_wifi_interfaces(self) -> List[Discovery]:
        """Scan for WiFi interfaces and their drivers."""
        discoveries = []
        
        # Get wireless interfaces
        code, stdout, _ = self.run_command(["iw", "dev"])
        
        interfaces = []
        current_if = None
        
        if code == 0:
            for line in stdout.splitlines():
                if "Interface" in line:
                    current_if = {"name": line.split()[-1]}
                    interfaces.append(current_if)
                elif current_if:
                    if "type" in line:
                        current_if["type"] = line.split()[-1]
                    elif "addr" in line:
                        current_if["mac"] = line.split()[-1]
        
        for iface in interfaces:
            if_name = iface["name"]
            
            # Get driver info
            driver = "Unknown"
            driver_path = Path(f"/sys/class/net/{if_name}/device/driver")
            if driver_path.exists():
                try:
                    driver = driver_path.resolve().name
                except:
                    pass
            
            # Check if interface is up
            operstate_file = Path(f"/sys/class/net/{if_name}/operstate")
            state = "unknown"
            if operstate_file.exists():
                state = operstate_file.read_text().strip()
            
            # Known problematic drivers
            issues = []
            problem_drivers = {
                "rtl8821ce": "Known issues with kernel updates",
                "bcma-pci-bridge": "May need firmware",
                "brcmfmac": "Broadcom - may need proprietary driver",
            }
            if driver in problem_drivers:
                issues.append(problem_drivers[driver])
            
            severity = DiscoverySeverity.WARNING if issues else DiscoverySeverity.SUCCESS
            status = state.title()
            
            discovery_id = make_discovery_id(DiscoveryType.NETWORK, f"wifi-{if_name}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.NETWORK,
                name=f"wifi-{if_name}",
                title=f"WiFi: {if_name}",
                description=f"Driver: {driver}, State: {state}",
                icon="wifi",
                severity=severity,
                status=status,
                status_detail="; ".join(issues) if issues else None,
                data={
                    "interface": if_name,
                    "driver": driver,
                    "state": state,
                    "mac": iface.get("mac"),
                    "type": iface.get("type"),
                    "issues": issues,
                    "is_wifi_interface": True,
                },
                actions=[
                    DiscoveryAction(
                        id="up",
                        label="Bring Up",
                        icon="wifi",
                        command=f"sudo ip link set {if_name} up",
                        requires_approval=True,
                    ),
                    DiscoveryAction(
                        id="scan",
                        label="Scan Networks",
                        icon="search",
                        command=f"sudo iw {if_name} scan | grep SSID",
                    ),
                ],
                chat_context=f"WiFi interface {if_name} using {driver} driver, state: {state}. "
                            f"{'⚠️ ' + '; '.join(issues) + '. ' if issues else ''}"
                            f"Not working? Try 'sudo modprobe -r {driver} && sudo modprobe {driver}'.",
            ))
        
        return discoveries
    
    def _scan_wifi_connection(self) -> List[Discovery]:
        """Scan current WiFi connection details."""
        discoveries = []
        
        # Use iwconfig for connection info
        code, stdout, _ = self.run_command(["iwconfig"], timeout=5)
        
        if code != 0:
            return discoveries
        
        # Parse iwconfig output
        current_if = None
        connections = {}
        
        for line in stdout.splitlines():
            # Interface line: wlan0     IEEE 802.11  ESSID:"MyNetwork"
            if not line.startswith(" ") and "IEEE 802.11" in line:
                parts = line.split()
                if_name = parts[0]
                current_if = if_name
                connections[if_name] = {}
                
                # Extract ESSID
                essid_match = re.search(r'ESSID:"([^"]*)"', line)
                if essid_match:
                    connections[if_name]["essid"] = essid_match.group(1)
            elif current_if:
                # Signal level: Link Quality=70/70  Signal level=-40 dBm
                signal_match = re.search(r'Signal level[=:](-?\d+)\s*dBm', line)
                if signal_match:
                    connections[current_if]["signal_dbm"] = int(signal_match.group(1))
                
                quality_match = re.search(r'Link Quality[=:](\d+)/(\d+)', line)
                if quality_match:
                    connections[current_if]["quality"] = f"{quality_match.group(1)}/{quality_match.group(2)}"
                
                # Bit Rate
                rate_match = re.search(r'Bit Rate[=:](\d+\.?\d*)\s*(Mb/s|Gb/s)', line)
                if rate_match:
                    connections[current_if]["bitrate"] = f"{rate_match.group(1)} {rate_match.group(2)}"
                
                # Frequency/Channel
                freq_match = re.search(r'Frequency[=:](\d+\.?\d*)\s*GHz', line)
                if freq_match:
                    connections[current_if]["frequency"] = f"{freq_match.group(1)} GHz"
        
        for if_name, conn in connections.items():
            if not conn.get("essid"):
                continue  # Not connected
            
            essid = conn["essid"]
            signal = conn.get("signal_dbm", -100)
            quality = conn.get("quality", "Unknown")
            bitrate = conn.get("bitrate", "Unknown")
            freq = conn.get("frequency", "Unknown")
            
            # Determine signal quality
            if signal >= -50:
                signal_quality = "Excellent"
                severity = DiscoverySeverity.SUCCESS
            elif signal >= -60:
                signal_quality = "Good"
                severity = DiscoverySeverity.SUCCESS
            elif signal >= -70:
                signal_quality = "Fair"
                severity = DiscoverySeverity.INFO
            else:
                signal_quality = "Weak"
                severity = DiscoverySeverity.WARNING
            
            # Detect 2.4 vs 5 GHz
            band = "5 GHz" if "5." in freq else "2.4 GHz"
            
            discovery_id = make_discovery_id(DiscoveryType.NETWORK, f"wifi-conn-{if_name}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.NETWORK,
                name=f"wifi-conn-{if_name}",
                title=f"Connected: {essid}",
                description=f"{band}, Signal: {signal_quality} ({signal} dBm)",
                icon="wifi",
                severity=severity,
                status=f"{signal_quality} ({signal} dBm)",
                status_detail=f"{bitrate}, {band}",
                data={
                    "interface": if_name,
                    "essid": essid,
                    "signal_dbm": signal,
                    "signal_quality": signal_quality,
                    "quality": quality,
                    "bitrate": bitrate,
                    "frequency": freq,
                    "band": band,
                    "is_wifi_connection": True,
                },
                chat_context=f"Connected to '{essid}' on {band}. Signal: {signal_quality} ({signal} dBm). "
                            f"Speed: {bitrate}. "
                            f"{'⚠️ Weak signal - move closer to router or check for interference. ' if signal < -70 else ''}"
                            f"{'Consider using 5GHz for faster speeds if available. ' if '2.4' in band else ''}",
            ))
        
        return discoveries
    
    def _scan_wifi_regulatory(self) -> List[Discovery]:
        """Scan WiFi regulatory domain (country code)."""
        discoveries = []
        
        code, stdout, _ = self.run_command(["iw", "reg", "get"])
        
        if code != 0:
            return discoveries
        
        country = "Unknown"
        for line in stdout.splitlines():
            if "country" in line.lower():
                match = re.search(r'country\s+(\w{2})', line)
                if match:
                    country = match.group(1)
                    break
        
        # Check for unset/world domain
        issues = []
        if country in ["00", "Unknown"]:
            issues.append("Country not set - some channels may be unavailable")
        
        severity = DiscoverySeverity.WARNING if issues else DiscoverySeverity.SUCCESS
        
        discovery_id = make_discovery_id(DiscoveryType.NETWORK, "wifi-regulatory")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.NETWORK,
            name="wifi-regulatory",
            title="WiFi Regulatory Domain",
            description=f"Country: {country}",
            icon="globe",
            severity=severity,
            status=f"Country: {country}",
            status_detail="; ".join(issues) if issues else None,
            data={
                "country": country,
                "issues": issues,
                "is_regulatory": True,
            },
            actions=[
                DiscoveryAction(
                    id="set-country",
                    label="Set Country",
                    icon="globe",
                    command="sudo iw reg set US",  # Example
                    requires_approval=True,
                ),
            ],
            chat_context=f"WiFi regulatory domain: {country}. "
                        f"{'⚠️ ' + '; '.join(issues) + ' Set with: sudo iw reg set <XX> where XX is your country code. ' if issues else ''}"
                        f"Wrong country may limit available channels and cause 5GHz issues.",
        ))
        
        return discoveries
    
    def _scan_wifi_power_mgmt(self) -> List[Discovery]:
        """Check WiFi power management (causes disconnections)."""
        discoveries = []
        
        # Find WiFi interfaces
        code, stdout, _ = self.run_command(["iw", "dev"])
        
        interfaces = []
        for line in stdout.splitlines():
            if "Interface" in line:
                interfaces.append(line.split()[-1])
        
        for if_name in interfaces:
            code, stdout, _ = self.run_command(["iw", if_name, "get", "power_save"])
            
            if code == 0:
                power_save_on = "on" in stdout.lower()
                
                # Power save can cause disconnections
                issues = []
                if power_save_on:
                    issues.append("Power save enabled - may cause disconnections")
                
                severity = DiscoverySeverity.INFO if power_save_on else DiscoverySeverity.SUCCESS
                
                discovery_id = make_discovery_id(DiscoveryType.NETWORK, f"wifi-power-{if_name}")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.NETWORK,
                    name=f"wifi-power-{if_name}",
                    title=f"WiFi Power Save: {if_name}",
                    description=f"Power save: {'On' if power_save_on else 'Off'}",
                    icon="battery",
                    severity=severity,
                    status="On" if power_save_on else "Off",
                    status_detail="; ".join(issues) if issues else None,
                    data={
                        "interface": if_name,
                        "power_save": power_save_on,
                        "issues": issues,
                        "is_wifi_power": True,
                    },
                    actions=[
                        DiscoveryAction(
                            id="disable-power-save",
                            label="Disable Power Save",
                            icon="zap",
                            command=f"sudo iw {if_name} set power_save off",
                            requires_approval=True,
                        ),
                    ] if power_save_on else [],
                    chat_context=f"WiFi power save on {if_name}: {'enabled' if power_save_on else 'disabled'}. "
                                f"{'⚠️ Power save can cause random disconnections. Disable with: sudo iw {if_name} set power_save off. Make permanent in /etc/NetworkManager/conf.d/. ' if power_save_on else ''}",
                ))
        
        return discoveries
