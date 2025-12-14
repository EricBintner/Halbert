"""
Thermal Scanner - Discover temperature sensors and thermal state.

Enables scenarios:
- S1.3: "Thermal monitoring" → CPU/GPU temps, fan speeds
- S2.6: "Fan noise reduction" → Fan curves, thermal thresholds
- S8.2: "Fan curve control" → Fan → sensor relationships
- S9.10: "Thermal stress warnings" → Temperature trends

Discovers:
- CPU/GPU/disk temperatures
- Fan speeds and RPM
- Thermal zones and thresholds
- Critical temperature warnings
"""

from __future__ import annotations
from typing import List, Dict, Optional
from pathlib import Path
import glob

from .base import BaseScanner
from ..schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class ThermalScanner(BaseScanner):
    """
    Scanner for thermal sensors, fans, and temperature monitoring.
    
    Discovers:
    - CPU core temperatures
    - GPU temperature (nvidia, amd)
    - Disk temperatures (from SMART)
    - Fan speeds
    - Thermal zones
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.HARDWARE
    
    def scan(self) -> List[Discovery]:
        """Scan system for thermal data."""
        discoveries = []
        
        discoveries.extend(self._scan_hwmon_sensors())
        discoveries.extend(self._scan_thermal_zones())
        discoveries.extend(self._scan_fans())
        discoveries.append(self._create_thermal_summary())
        
        self.logger.info(f"Found {len(discoveries)} thermal discoveries")
        return discoveries
    
    def _scan_hwmon_sensors(self) -> List[Discovery]:
        """Scan /sys/class/hwmon for temperature sensors."""
        discoveries = []
        hwmon_base = Path("/sys/class/hwmon")
        
        if not hwmon_base.exists():
            return discoveries
        
        for hwmon_dir in hwmon_base.iterdir():
            if not hwmon_dir.is_dir():
                continue
            
            # Get sensor name
            name_file = hwmon_dir / "name"
            sensor_name = "unknown"
            if name_file.exists():
                sensor_name = name_file.read_text().strip()
            
            # Find all temperature inputs
            for temp_file in hwmon_dir.glob("temp*_input"):
                try:
                    temp_num = temp_file.name.replace("temp", "").replace("_input", "")
                    temp_millic = int(temp_file.read_text().strip())
                    temp_c = temp_millic / 1000.0
                    
                    # Get label if available
                    label_file = hwmon_dir / f"temp{temp_num}_label"
                    label = f"Sensor {temp_num}"
                    if label_file.exists():
                        label = label_file.read_text().strip()
                    
                    # Get critical threshold if available
                    crit_file = hwmon_dir / f"temp{temp_num}_crit"
                    crit_temp = None
                    if crit_file.exists():
                        try:
                            crit_temp = int(crit_file.read_text().strip()) / 1000.0
                        except:
                            pass
                    
                    # Determine severity
                    if crit_temp and temp_c > crit_temp * 0.9:
                        severity = DiscoverySeverity.CRITICAL
                        status = f"{temp_c:.0f}°C (CRITICAL)"
                    elif temp_c > 80:
                        severity = DiscoverySeverity.WARNING
                        status = f"{temp_c:.0f}°C (High)"
                    elif temp_c > 60:
                        severity = DiscoverySeverity.INFO
                        status = f"{temp_c:.0f}°C"
                    else:
                        severity = DiscoverySeverity.SUCCESS
                        status = f"{temp_c:.0f}°C (Cool)"
                    
                    sensor_id = f"{sensor_name}-temp{temp_num}".replace(" ", "_").lower()
                    discovery_id = make_discovery_id(DiscoveryType.HARDWARE, f"thermal-{sensor_id}")
                    
                    discoveries.append(Discovery(
                        id=discovery_id,
                        type=DiscoveryType.HARDWARE,
                        name=f"thermal-{sensor_id}",
                        title=f"{sensor_name}: {label}",
                        description=f"Temperature sensor reading {temp_c:.1f}°C",
                        icon="thermometer",
                        severity=severity,
                        status=status,
                        status_detail=f"Critical: {crit_temp:.0f}°C" if crit_temp else None,
                        source=str(temp_file),
                        data={
                            "sensor_name": sensor_name,
                            "label": label,
                            "temp_celsius": temp_c,
                            "crit_celsius": crit_temp,
                            "hwmon_path": str(hwmon_dir),
                            "is_thermal": True,
                            "sensor_type": "temperature",
                        },
                        chat_context=f"{sensor_name} {label} is at {temp_c:.1f}°C. "
                                    f"{'⚠️ Temperature is critically high!' if severity == DiscoverySeverity.CRITICAL else ''}"
                                    f"{'Temperature is elevated.' if severity == DiscoverySeverity.WARNING else ''}",
                    ))
                except (ValueError, IOError):
                    continue
        
        return discoveries
    
    def _scan_thermal_zones(self) -> List[Discovery]:
        """Scan /sys/class/thermal for thermal zones."""
        discoveries = []
        thermal_base = Path("/sys/class/thermal")
        
        if not thermal_base.exists():
            return discoveries
        
        for zone_dir in thermal_base.glob("thermal_zone*"):
            if not zone_dir.is_dir():
                continue
            
            try:
                zone_num = zone_dir.name.replace("thermal_zone", "")
                
                # Get zone type
                type_file = zone_dir / "type"
                zone_type = "unknown"
                if type_file.exists():
                    zone_type = type_file.read_text().strip()
                
                # Get temperature
                temp_file = zone_dir / "temp"
                temp_c = 0.0
                if temp_file.exists():
                    temp_millic = int(temp_file.read_text().strip())
                    temp_c = temp_millic / 1000.0
                
                # Determine severity
                if temp_c > 90:
                    severity = DiscoverySeverity.CRITICAL
                elif temp_c > 75:
                    severity = DiscoverySeverity.WARNING
                else:
                    severity = DiscoverySeverity.SUCCESS
                
                discovery_id = make_discovery_id(DiscoveryType.HARDWARE, f"zone-{zone_num}")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.HARDWARE,
                    name=f"zone-{zone_num}",
                    title=f"Thermal Zone {zone_num}: {zone_type}",
                    description=f"Thermal zone at {temp_c:.1f}°C",
                    icon="thermometer",
                    severity=severity,
                    status=f"{temp_c:.0f}°C",
                    source=str(zone_dir),
                    data={
                        "zone_num": int(zone_num),
                        "zone_type": zone_type,
                        "temp_celsius": temp_c,
                        "is_thermal": True,
                        "sensor_type": "thermal_zone",
                    },
                    chat_context=f"Thermal zone {zone_num} ({zone_type}) is at {temp_c:.1f}°C.",
                ))
            except (ValueError, IOError):
                continue
        
        return discoveries
    
    def _scan_fans(self) -> List[Discovery]:
        """Scan for fan speeds from hwmon."""
        discoveries = []
        hwmon_base = Path("/sys/class/hwmon")
        
        if not hwmon_base.exists():
            return discoveries
        
        for hwmon_dir in hwmon_base.iterdir():
            if not hwmon_dir.is_dir():
                continue
            
            name_file = hwmon_dir / "name"
            sensor_name = "unknown"
            if name_file.exists():
                sensor_name = name_file.read_text().strip()
            
            for fan_file in hwmon_dir.glob("fan*_input"):
                try:
                    fan_num = fan_file.name.replace("fan", "").replace("_input", "")
                    rpm = int(fan_file.read_text().strip())
                    
                    # Get label if available
                    label_file = hwmon_dir / f"fan{fan_num}_label"
                    label = f"Fan {fan_num}"
                    if label_file.exists():
                        label = label_file.read_text().strip()
                    
                    # Determine status
                    if rpm == 0:
                        status = "Stopped"
                        severity = DiscoverySeverity.INFO
                    elif rpm < 500:
                        status = f"{rpm} RPM (Low)"
                        severity = DiscoverySeverity.SUCCESS
                    elif rpm > 3000:
                        status = f"{rpm} RPM (High)"
                        severity = DiscoverySeverity.WARNING
                    else:
                        status = f"{rpm} RPM"
                        severity = DiscoverySeverity.SUCCESS
                    
                    fan_id = f"{sensor_name}-fan{fan_num}".replace(" ", "_").lower()
                    discovery_id = make_discovery_id(DiscoveryType.HARDWARE, f"fan-{fan_id}")
                    
                    discoveries.append(Discovery(
                        id=discovery_id,
                        type=DiscoveryType.HARDWARE,
                        name=f"fan-{fan_id}",
                        title=f"{sensor_name}: {label}",
                        description=f"Fan running at {rpm} RPM",
                        icon="fan",
                        severity=severity,
                        status=status,
                        source=str(fan_file),
                        data={
                            "sensor_name": sensor_name,
                            "label": label,
                            "rpm": rpm,
                            "hwmon_path": str(hwmon_dir),
                            "is_fan": True,
                            "sensor_type": "fan",
                        },
                        chat_context=f"{label} is running at {rpm} RPM. "
                                    f"{'Fan is stopped.' if rpm == 0 else ''}"
                                    f"{'Fan is running fast - system may be hot.' if rpm > 3000 else ''}",
                    ))
                except (ValueError, IOError):
                    continue
        
        return discoveries
    
    def _create_thermal_summary(self) -> Discovery:
        """Create a summary of thermal state."""
        # Get CPU temp using sensors command if available
        code, stdout, _ = self.run_command(["sensors", "-j"], timeout=5)
        
        max_temp = 0.0
        max_fan = 0
        temp_readings = []
        fan_readings = []
        
        if code == 0:
            try:
                import json
                data = json.loads(stdout)
                for chip_name, chip_data in data.items():
                    for sensor_name, sensor_data in chip_data.items():
                        if isinstance(sensor_data, dict):
                            for key, value in sensor_data.items():
                                if 'temp' in key.lower() and 'input' in key.lower():
                                    temp_readings.append(value)
                                    max_temp = max(max_temp, value)
                                if 'fan' in key.lower() and 'input' in key.lower():
                                    fan_readings.append(value)
                                    max_fan = max(max_fan, int(value))
            except:
                pass
        
        # Determine overall status
        if max_temp > 90:
            severity = DiscoverySeverity.CRITICAL
            status = f"Critical: {max_temp:.0f}°C"
        elif max_temp > 75:
            severity = DiscoverySeverity.WARNING
            status = f"Warm: {max_temp:.0f}°C"
        elif max_temp > 0:
            severity = DiscoverySeverity.SUCCESS
            status = f"Normal: {max_temp:.0f}°C"
        else:
            severity = DiscoverySeverity.INFO
            status = "No sensors detected"
        
        discovery_id = make_discovery_id(DiscoveryType.HARDWARE, "thermal-summary")
        
        return Discovery(
            id=discovery_id,
            type=DiscoveryType.HARDWARE,
            name="thermal-summary",
            title="Thermal Summary",
            description=f"Max temp: {max_temp:.0f}°C, Fans: {len(fan_readings)}",
            icon="thermometer",
            severity=severity,
            status=status,
            data={
                "max_temp_celsius": max_temp,
                "max_fan_rpm": max_fan,
                "temp_readings": temp_readings,
                "fan_count": len(fan_readings),
                "is_summary": True,
                "sensor_type": "summary",
            },
            chat_context=f"System thermal summary: Max temperature {max_temp:.0f}°C, "
                        f"{len(fan_readings)} fans detected with max {max_fan} RPM. "
                        f"{'⚠️ System is running hot!' if max_temp > 75 else 'Temperatures normal.'}",
        )
