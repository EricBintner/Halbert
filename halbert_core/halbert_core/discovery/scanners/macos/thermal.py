# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
macOS Thermal Scanner - Temperature and fan monitoring.

macOS equivalent of Linux ThermalScanner.

Uses:
- powermetrics for CPU/GPU temperature (requires sudo)
- psutil for basic temperature fallback
- system_profiler for hardware info
"""

from __future__ import annotations
from typing import List
import re

from ..base import BaseScanner
from ...schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class MacThermalScanner(BaseScanner):
    """
    Scanner for macOS thermal sensors.
    
    Equivalent to Linux ThermalScanner but uses IOKit/powermetrics.
    """
    
    # Temperature thresholds (Celsius)
    TEMP_WARNING = 80
    TEMP_CRITICAL = 95
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.HARDWARE
    
    def is_available(self) -> bool:
        """Check if thermal monitoring is available."""
        # powermetrics requires sudo, but we can still check if it exists
        return self.command_exists('powermetrics') or self.command_exists('system_profiler')
    
    def scan(self) -> List[Discovery]:
        """Scan thermal sensors."""
        discoveries = []
        
        # Try powermetrics first (requires sudo)
        temps = self._read_powermetrics()
        
        if not temps:
            # Fall back to psutil
            temps = self._read_psutil()
        
        if not temps:
            # No temperature data available
            discoveries.append(self._no_temp_data())
            return discoveries
        
        for temp_data in temps:
            discoveries.append(self._create_temp_discovery(temp_data))
        
        # Check for battery temperature
        battery_temp = self._read_battery_temp()
        if battery_temp:
            discoveries.append(battery_temp)
        
        self.logger.info(f"Found {len(discoveries)} thermal discoveries")
        return discoveries
    
    def _read_powermetrics(self) -> List[dict]:
        """Read temperatures via powermetrics (requires sudo)."""
        temps = []
        
        # Try without sudo first (will fail but quick)
        code, stdout, _ = self.run_command(
            ['sudo', '-n', 'powermetrics', '-n', '1', '-i', '1', '--samplers', 'thermal'],
            timeout=5
        )
        
        if code != 0:
            return temps
        
        # Parse thermal output
        for line in stdout.split('\n'):
            if 'CPU die temperature:' in line:
                match = re.search(r'(\d+\.?\d*)\s*C', line)
                if match:
                    temps.append({
                        'label': 'CPU Die',
                        'temp_c': float(match.group(1)),
                        'sensor': 'cpu_die',
                    })
            
            elif 'GPU die temperature:' in line:
                match = re.search(r'(\d+\.?\d*)\s*C', line)
                if match:
                    temps.append({
                        'label': 'GPU Die',
                        'temp_c': float(match.group(1)),
                        'sensor': 'gpu_die',
                    })
        
        return temps
    
    def _read_psutil(self) -> List[dict]:
        """Read temperatures via psutil (limited on macOS)."""
        temps = []
        
        try:
            import psutil
            
            # psutil.sensors_temperatures() is limited on macOS
            # but we can try
            sensor_temps = psutil.sensors_temperatures()
            
            for sensor_name, readings in sensor_temps.items():
                for reading in readings:
                    temps.append({
                        'label': reading.label or sensor_name,
                        'temp_c': reading.current,
                        'sensor': sensor_name,
                    })
        except Exception:
            pass
        
        return temps
    
    def _read_battery_temp(self) -> Discovery | None:
        """Read battery temperature."""
        try:
            import psutil
            battery = psutil.sensors_battery()
            
            if battery:
                # psutil doesn't give battery temp directly on macOS
                # but we can report battery status
                percent = battery.percent
                plugged = battery.power_plugged
                
                if percent < 20 and not plugged:
                    severity = DiscoverySeverity.WARNING
                elif percent < 10 and not plugged:
                    severity = DiscoverySeverity.CRITICAL
                else:
                    severity = DiscoverySeverity.SUCCESS
                
                discovery_id = make_discovery_id(DiscoveryType.HARDWARE, "battery-status")
                
                return Discovery(
                    id=discovery_id,
                    type=DiscoveryType.HARDWARE,
                    name="battery",
                    title=f"Battery: {percent}%",
                    description=f"Battery at {percent}% ({'charging' if plugged else 'on battery'})",
                    severity=severity,
                    details={
                        'percent': percent,
                        'plugged': plugged,
                        'time_left': battery.secsleft if battery.secsleft > 0 else None,
                    },
                    actions=[
                        DiscoveryAction(
                            id="battery-info",
                            label="Battery Details",
                            command="system_profiler SPPowerDataType",
                            dry_run=True,
                        ),
                    ],
                    tags=['hardware', 'battery', 'power', 'macos'],
                )
        except Exception:
            pass
        
        return None
    
    def _create_temp_discovery(self, temp_data: dict) -> Discovery:
        """Create a temperature discovery."""
        temp_c = temp_data['temp_c']
        label = temp_data['label']
        sensor = temp_data['sensor']
        
        # Determine severity
        if temp_c >= self.TEMP_CRITICAL:
            severity = DiscoverySeverity.CRITICAL
        elif temp_c >= self.TEMP_WARNING:
            severity = DiscoverySeverity.WARNING
        else:
            severity = DiscoverySeverity.SUCCESS
        
        discovery_id = make_discovery_id(DiscoveryType.HARDWARE, f"temp-{sensor}")
        
        return Discovery(
            id=discovery_id,
            type=DiscoveryType.HARDWARE,
            name=sensor,
            title=f"{label}: {temp_c}°C",
            description=f"{label} temperature is {temp_c}°C",
            severity=severity,
            details={
                'label': label,
                'temp_c': temp_c,
                'sensor': sensor,
                'threshold_warning': self.TEMP_WARNING,
                'threshold_critical': self.TEMP_CRITICAL,
            },
            tags=['hardware', 'thermal', 'temperature', 'macos'],
        )
    
    def _no_temp_data(self) -> Discovery:
        """Create discovery when no temperature data is available."""
        discovery_id = make_discovery_id(DiscoveryType.HARDWARE, "temp-unavailable")
        
        return Discovery(
            id=discovery_id,
            type=DiscoveryType.HARDWARE,
            name="thermal-unavailable",
            title="Temperature Monitoring Unavailable",
            description="Temperature sensors require sudo access to powermetrics",
            severity=DiscoverySeverity.INFO,
            details={
                'reason': 'powermetrics requires sudo',
                'suggestion': 'Configure passwordless sudo for powermetrics',
            },
            actions=[
                DiscoveryAction(
                    id="setup-sudo",
                    label="View Setup Instructions",
                    command="echo 'Add to sudoers: username ALL=(ALL) NOPASSWD: /usr/bin/powermetrics'",
                    dry_run=True,
                ),
            ],
            tags=['hardware', 'thermal', 'macos', 'permission'],
        )
