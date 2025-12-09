"""
macOS platform implementation.

Implements platform-specific operations for macOS using:
- psutil for system info
- Unified Logging (log stream) for logs (via cerebric-mac adapter)
- IOKit/powermetrics for sensors (via cerebric-mac adapter)
- launchd for service management (via cerebric-mac adapter)
- brew for package management
"""

import subprocess
import json
import re
import sys
import os
from typing import Dict, List, Iterator, Optional, Any
import psutil
from .base import PlatformBridge

# Add cerebric-mac to path
mac_adapter_path = os.path.join(os.path.dirname(__file__), '../../../cerebric-mac')
if os.path.exists(mac_adapter_path) and mac_adapter_path not in sys.path:
    sys.path.insert(0, mac_adapter_path)


class MacPlatformBridge(PlatformBridge):
    """macOS platform implementation."""
    
    def __init__(self):
        """Initialize macOS platform bridge with adapters."""
        # Import adapters (lazy to avoid circular imports)
        try:
            from adapters import UnifiedLoggingAdapter, IOKitAdapter, LaunchdAdapter
            self._unified_logging = UnifiedLoggingAdapter()
            self._iokit = IOKitAdapter()
            self._launchd = LaunchdAdapter()
        except ImportError:
            # Adapters not available, fall back to basic implementation
            self._unified_logging = None
            self._iokit = None
            self._launchd = None
    
    @property
    def platform_name(self) -> str:
        return "macos"
    
    # ==========================================
    # System Information
    # ==========================================
    
    def get_cpu_usage(self) -> float:
        """Get CPU usage using psutil."""
        return psutil.cpu_percent(interval=1.0)
    
    def get_memory_info(self) -> Dict[str, Any]:
        """Get memory info using psutil."""
        mem = psutil.virtual_memory()
        return {
            'total': mem.total,
            'available': mem.available,
            'percent': mem.percent,
            'used': mem.used,
            'free': mem.free,
        }
    
    def get_disk_usage(self, path: str = '/') -> Dict[str, Any]:
        """Get disk usage using psutil."""
        usage = psutil.disk_usage(path)
        return {
            'total': usage.total,
            'used': usage.used,
            'free': usage.free,
            'percent': usage.percent,
        }
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get system info."""
        import platform
        import socket
        
        return {
            'hostname': socket.gethostname(),
            'platform': 'macos',
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor(),
        }
    
    # ==========================================
    # Log Collection
    # ==========================================
    
    def collect_logs(
        self,
        filters: Optional[Dict[str, Any]] = None,
        follow: bool = False
    ) -> Iterator[Dict[str, Any]]:
        """
        Collect logs from macOS Unified Logging using adapter.
        """
        if self._unified_logging:
            # Use Unified Logging adapter
            yield from self._unified_logging.collect_logs(
                filters=filters,
                follow=follow
            )
        else:
            # Fallback to basic log command
            cmd = ['log', 'stream', '--style', 'json', '--level', 'info']
            
            if not follow:
                cmd = ['log', 'show', '--style', 'json', '--last', '1h']
            
            if filters:
                if filters.get('process'):
                    cmd.extend(['--process', filters['process']])
                if filters.get('subsystem'):
                    cmd.extend(['--subsystem', filters['subsystem']])
            
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                for line in proc.stdout:
                    try:
                        entry = json.loads(line)
                        yield {
                            'timestamp': entry.get('timestamp'),
                            'message': entry.get('eventMessage', ''),
                            'level': entry.get('messageType', 'info'),
                            'process': entry.get('processImagePath', ''),
                            'pid': entry.get('processID'),
                            'subsystem': entry.get('subsystem', 'system'),
                        }
                    except json.JSONDecodeError:
                        continue
            except FileNotFoundError:
                yield {'error': 'log command not found'}
    
    # ==========================================
    # Sensor Reading
    # ==========================================
    
    def read_sensors(self) -> List[Dict[str, Any]]:
        """
        Read sensors using IOKit adapter.
        """
        if self._iokit:
            # Use IOKit adapter (returns normalized cerebric format)
            readings = self._iokit.read_all_sensors()
            # Convert to simpler format for platform bridge
            sensors = []
            for reading in readings:
                if 'error' in reading:
                    sensors.append(reading)
                elif reading.get('subsystem') == 'thermal':
                    sensors.append({
                        'label': reading.get('data', {}).get('label', 'unknown'),
                        'value': reading.get('data', {}).get('temp_c', 0),
                        'type': 'temperature',
                        'unit': '°C',
                    })
                elif reading.get('subsystem') == 'power':
                    sensors.append({
                        'label': reading.get('data', {}).get('label', 'battery'),
                        'value': reading.get('data', {}).get('percent', 0),
                        'type': 'battery',
                        'unit': '%',
                        'plugged': reading.get('data', {}).get('plugged', False),
                    })
            return sensors
        else:
            # Fallback to basic powermetrics
            sensors = []
            
            try:
                # CPU temperature using powermetrics
                result = subprocess.run(
                    ['sudo', 'powermetrics', '-n', '1', '-i', '1000', '--samplers', 'thermal'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                for line in result.stdout.split('\n'):
                    if 'CPU die temperature:' in line:
                        match = re.search(r'(\d+\.\d+) C', line)
                        if match:
                            sensors.append({
                                'label': 'cpu_die',
                                'value': float(match.group(1)),
                                'type': 'temperature',
                                'unit': '°C',
                            })
                
                # Battery info
                battery = psutil.sensors_battery()
                if battery:
                    sensors.append({
                        'label': 'battery',
                        'value': battery.percent,
                        'type': 'battery',
                        'unit': '%',
                        'plugged': battery.power_plugged,
                    })
            
            except subprocess.TimeoutExpired:
                sensors.append({'error': 'powermetrics timed out'})
            except Exception as e:
                sensors.append({'error': str(e)})
            
            return sensors
    
    # ==========================================
    # Service Management
    # ==========================================
    
    def manage_service(
        self,
        name: str,
        action: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Manage launchd services using adapter."""
        if self._launchd:
            # Use launchd adapter
            return self._launchd.manage_service(name, action, dry_run)
        else:
            # Fallback to direct launchctl
            valid_actions = ['start', 'stop', 'restart', 'status']
            
            if action not in valid_actions:
                return {
                    'ok': False,
                    'message': f"Invalid action '{action}'. Valid: {valid_actions}"
                }
            
            if action == 'start':
                cmd = ['launchctl', 'load', f'/Library/LaunchDaemons/{name}.plist']
            elif action == 'stop':
                cmd = ['launchctl', 'unload', f'/Library/LaunchDaemons/{name}.plist']
            elif action == 'restart':
                return {'ok': False, 'message': 'restart not yet implemented for launchd'}
            elif action == 'status':
                cmd = ['launchctl', 'list', name]
            
            if dry_run:
                return {
                    'ok': True,
                    'message': f"Would execute: {' '.join(cmd)}",
                    'dry_run': True,
                }
            
            return self.execute_command(cmd)
    
    def list_services(self) -> List[Dict[str, Any]]:
        """List launchd services using adapter."""
        if self._launchd:
            # Use launchd adapter
            return self._launchd.list_services()
        else:
            # Fallback to direct launchctl
            result = self.execute_command(['launchctl', 'list'])
            
            services = []
            if result['ok']:
                for line in result['stdout'].split('\n')[1:]:  # Skip header
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 3:
                            services.append({
                                'pid': parts[0],
                                'status': parts[1],
                                'name': parts[2],
                            })
            
            return services
    
    # ==========================================
    # Package Management
    # ==========================================
    
    def install_package(
        self,
        name: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Install package using Homebrew."""
        if not self._has_brew():
            return {
                'ok': False,
                'message': 'Homebrew not installed. Install from https://brew.sh'
            }
        
        cmd = ['brew', 'install', name]
        
        if dry_run:
            return {
                'ok': True,
                'message': f"Would execute: {' '.join(cmd)}",
                'dry_run': True,
            }
        
        return self.execute_command(cmd)
    
    def list_packages(
        self,
        pattern: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List installed Homebrew packages."""
        if not self._has_brew():
            return []
        
        cmd = ['brew', 'list', '--versions']
        
        if pattern:
            cmd.append(pattern)
        
        result = self.execute_command(cmd)
        
        packages = []
        if result['ok']:
            for line in result['stdout'].split('\n'):
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2:
                        packages.append({
                            'name': parts[0],
                            'version': parts[1],
                        })
        
        return packages
    
    # ==========================================
    # Utility Methods
    # ==========================================
    
    def execute_command(
        self,
        command: List[str],
        dry_run: bool = False,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """Execute a system command."""
        if dry_run:
            return {
                'ok': True,
                'message': f"Would execute: {' '.join(command)}",
                'dry_run': True,
            }
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return {
                'ok': result.returncode == 0,
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                'ok': False,
                'error': 'Command timed out',
            }
        except Exception as e:
            return {
                'ok': False,
                'error': str(e),
            }
    
    def _has_brew(self) -> bool:
        """Check if Homebrew is installed."""
        return subprocess.run(
            ['which', 'brew'],
            capture_output=True
        ).returncode == 0
