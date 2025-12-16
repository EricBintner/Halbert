"""
macOS IOKit sensor adapter.

Provides hardware sensor reading using macOS-specific tools (powermetrics, system_profiler).
Equivalent to Linux hwmon adapter.
"""

import subprocess
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


class IOKitAdapter:
    """
    Adapter for macOS hardware sensors via IOKit.
    
    Equivalent to Linux HwmonAdapter, but uses macOS powermetrics and system_profiler.
    """
    
    def __init__(self):
        self.name = "iokit"
    
    def read_all_sensors(self) -> List[Dict[str, Any]]:
        """
        Read all available hardware sensors.
        
        Returns:
            List of sensor readings in Cerebrix format
        """
        sensors = []
        
        # Collect CPU temperature
        sensors.extend(self._read_cpu_temp())
        
        # Collect battery info
        battery = self._read_battery()
        if battery:
            sensors.append(battery)
        
        # Collect fan speeds (if available)
        sensors.extend(self._read_fans())
        
        return sensors
    
    def _read_cpu_temp(self) -> List[Dict[str, Any]]:
        """
        Read CPU temperature using powermetrics.
        
        Note: Requires sudo on macOS.
        
        Returns:
            List of temperature sensor readings
        """
        sensors = []
        ts = datetime.now(timezone.utc).isoformat()
        
        try:
            # Run powermetrics with thermal samplers
            # Note: This requires sudo and may prompt for password
            result = subprocess.run(
                ['sudo', '-n', 'powermetrics', '-n', '1', '-i', '1000', '--samplers', 'thermal'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                # sudo failed (likely no passwordless sudo configured)
                return [{
                    "ts": ts,
                    "source": "iokit",
                    "type": "sensor_reading",
                    "subsystem": "thermal",
                    "severity": "warning",
                    "message": "powermetrics requires sudo access",
                    "data": {
                        "label": "cpu_temp",
                        "error": "sudo access required"
                    },
                    "tags": ["thermal", "macos", "permission_denied"],
                }]
            
            # Parse thermal output
            for line in result.stdout.split('\n'):
                # Look for CPU die temperature
                if 'CPU die temperature:' in line:
                    match = re.search(r'(\d+\.\d+)\s*C', line)
                    if match:
                        temp = float(match.group(1))
                        sensors.append({
                            "ts": ts,
                            "source": "iokit",
                            "type": "sensor_reading",
                            "subsystem": "thermal",
                            "severity": "info",
                            "message": f"CPU temp={temp}°C",
                            "data": {
                                "label": "cpu_die",
                                "temp_c": temp,
                            },
                            "tags": ["thermal", "macos"],
                        })
                
                # Look for GPU temperature if present
                elif 'GPU die temperature:' in line:
                    match = re.search(r'(\d+\.\d+)\s*C', line)
                    if match:
                        temp = float(match.group(1))
                        sensors.append({
                            "ts": ts,
                            "source": "iokit",
                            "type": "sensor_reading",
                            "subsystem": "thermal",
                            "severity": "info",
                            "message": f"GPU temp={temp}°C",
                            "data": {
                                "label": "gpu_die",
                                "temp_c": temp,
                            },
                            "tags": ["thermal", "macos"],
                        })
        
        except subprocess.TimeoutExpired:
            sensors.append({
                "ts": ts,
                "source": "iokit",
                "type": "sensor_reading",
                "subsystem": "thermal",
                "severity": "error",
                "message": "powermetrics timed out",
                "data": {"label": "cpu_temp"},
                "tags": ["thermal", "macos", "error"],
            })
        except Exception as e:
            sensors.append({
                "ts": ts,
                "source": "iokit",
                "type": "sensor_reading",
                "subsystem": "thermal",
                "severity": "error",
                "message": str(e),
                "data": {"label": "cpu_temp"},
                "tags": ["thermal", "macos", "error"],
            })
        
        return sensors
    
    def _read_battery(self) -> Optional[Dict[str, Any]]:
        """
        Read battery information.
        
        Returns:
            Battery sensor reading or None
        """
        ts = datetime.now(timezone.utc).isoformat()
        
        try:
            # Use psutil for battery (cross-platform)
            import psutil
            battery = psutil.sensors_battery()
            
            if battery:
                return {
                    "ts": ts,
                    "source": "iokit",
                    "type": "sensor_reading",
                    "subsystem": "power",
                    "severity": "info",
                    "message": f"Battery {battery.percent}% ({'charging' if battery.power_plugged else 'discharging'})",
                    "data": {
                        "label": "battery",
                        "percent": battery.percent,
                        "plugged": battery.power_plugged,
                        "time_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else None,
                    },
                    "tags": ["power", "battery", "macos"],
                }
        except ImportError:
            # psutil not available, try system_profiler
            try:
                result = subprocess.run(
                    ['system_profiler', 'SPPowerDataType', '-json'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    import json
                    data = json.loads(result.stdout)
                    # Parse battery data from system_profiler output
                    # Structure is complex, simplified here
                    return {
                        "ts": ts,
                        "source": "iokit",
                        "type": "sensor_reading",
                        "subsystem": "power",
                        "severity": "info",
                        "message": "Battery info available",
                        "data": {
                            "label": "battery",
                            "raw_data": data,
                        },
                        "tags": ["power", "battery", "macos"],
                    }
            except Exception:
                pass
        except Exception:
            pass
        
        return None
    
    def _read_fans(self) -> List[Dict[str, Any]]:
        """
        Read fan speeds (if available).
        
        Returns:
            List of fan sensor readings
        """
        # Fan information typically requires third-party tools on macOS
        # or direct IOKit access via Python bindings
        # For now, return empty list
        return []
    
    def list_sensors(self) -> List[Dict[str, str]]:
        """
        List available sensors.
        
        Returns:
            List of sensor info dicts
        """
        sensors = [
            {'label': 'cpu_die', 'type': 'temperature', 'source': 'powermetrics'},
            {'label': 'battery', 'type': 'power', 'source': 'psutil/system_profiler'},
        ]
        
        return sensors
    
    def is_available(self) -> bool:
        """
        Check if sensor reading is available.
        
        Returns:
            True if powermetrics or system_profiler available
        """
        try:
            # Check for powermetrics
            result = subprocess.run(
                ['which', 'powermetrics'],
                capture_output=True
            )
            if result.returncode == 0:
                return True
            
            # Check for system_profiler
            result = subprocess.run(
                ['which', 'system_profiler'],
                capture_output=True
            )
            return result.returncode == 0
        
        except Exception:
            return False
    
    def read_sensor(self, sensor_type: str) -> Optional[Dict[str, Any]]:
        """
        Read a specific sensor type.
        
        Args:
            sensor_type: Type of sensor ('cpu_temp', 'battery', 'fan')
            
        Returns:
            Sensor reading or None
        """
        if sensor_type == 'cpu_temp':
            temps = self._read_cpu_temp()
            return temps[0] if temps else None
        elif sensor_type == 'battery':
            return self._read_battery()
        elif sensor_type == 'fan':
            fans = self._read_fans()
            return fans[0] if fans else None
        else:
            return None
