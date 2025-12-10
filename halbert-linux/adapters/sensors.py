"""
Linux hwmon sensor adapter.

Wraps existing halbert_core hwmon sensor functionality
to work with platform abstraction layer.
"""

from typing import Dict, Any, List, Optional
import sys
import os
import glob

# Add halbert_core to path
halbert_path = os.path.join(os.path.dirname(__file__), '../../halbert_core')
if halbert_path not in sys.path:
    sys.path.insert(0, halbert_path)

from halbert_core.ingestion.hwmon import collect_temp


class HwmonAdapter:
    """
    Adapter for Linux hwmon hardware sensors.
    
    Wraps existing halbert_core.ingestion.hwmon functionality.
    """
    
    def __init__(self):
        self.name = "hwmon"
        self.base_path = "/sys/class/hwmon"
    
    def read_all_sensors(self) -> List[Dict[str, Any]]:
        """
        Read all available hwmon sensors.
        
        Returns:
            List of sensor readings
        """
        sensors = []
        
        try:
            # Find all temperature sensors
            for sensor_file in glob.glob(f'{self.base_path}/hwmon*/temp*_input'):
                # Get label if available
                label_file = sensor_file.replace('_input', '_label')
                label = None
                
                try:
                    with open(label_file, 'r') as f:
                        label = f.read().strip()
                except FileNotFoundError:
                    # Use sensor filename as label
                    label = sensor_file.split('/')[-1].replace('_input', '')
                
                # Collect temperature using existing function
                reading = collect_temp(sensor_file, label)
                sensors.append(reading)
        
        except Exception as e:
            sensors.append({
                'error': str(e),
                'source': 'hwmon',
            })
        
        return sensors
    
    def read_sensor(self, sensor_path: str, label: Optional[str] = None) -> Dict[str, Any]:
        """
        Read a specific sensor.
        
        Args:
            sensor_path: Path to sensor file
            label: Optional sensor label
            
        Returns:
            Sensor reading dict
        """
        return collect_temp(sensor_path, label)
    
    def list_sensors(self) -> List[Dict[str, str]]:
        """
        List available sensors.
        
        Returns:
            List of sensor info dicts
        """
        sensors = []
        
        try:
            for sensor_file in glob.glob(f'{self.base_path}/hwmon*/temp*_input'):
                label_file = sensor_file.replace('_input', '_label')
                label = None
                
                try:
                    with open(label_file, 'r') as f:
                        label = f.read().strip()
                except FileNotFoundError:
                    label = sensor_file.split('/')[-1].replace('_input', '')
                
                sensors.append({
                    'path': sensor_file,
                    'label': label,
                    'type': 'temperature',
                })
        
        except Exception:
            pass
        
        return sensors
    
    def is_available(self) -> bool:
        """
        Check if hwmon is available on this system.
        
        Returns:
            True if hwmon directory exists
        """
        return os.path.exists(self.base_path)
