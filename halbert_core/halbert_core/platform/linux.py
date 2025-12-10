"""
Linux platform implementation.

Implements platform-specific operations for Linux systems using:
- psutil for system info
- journald for log collection (via halbert-linux adapter)
- hwmon for sensors (via halbert-linux adapter)
- systemd for service management (via halbert-linux adapter)
- apt/yum for package management
"""

import subprocess
import sys
import os
from typing import Dict, List, Iterator, Optional, Any
import psutil
from .base import PlatformBridge

# Add halbert-linux to path
linux_adapter_path = os.path.join(os.path.dirname(__file__), '../../../halbert-linux')
if os.path.exists(linux_adapter_path) and linux_adapter_path not in sys.path:
    sys.path.insert(0, linux_adapter_path)


class LinuxPlatformBridge(PlatformBridge):
    """Linux platform implementation."""
    
    def __init__(self):
        """Initialize Linux platform bridge with adapters."""
        # Import adapters (lazy to avoid circular imports)
        try:
            from adapters import JournaldAdapter, HwmonAdapter, SystemdAdapter
            self._journald = JournaldAdapter()
            self._hwmon = HwmonAdapter()
            self._systemd = SystemdAdapter()
        except ImportError:
            # Adapters not available, fall back to basic implementation
            self._journald = None
            self._hwmon = None
            self._systemd = None
    
    @property
    def platform_name(self) -> str:
        return "linux"
    
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
            'buffers': getattr(mem, 'buffers', 0),
            'cached': getattr(mem, 'cached', 0),
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
            'platform': 'linux',
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
        Collect logs from journald using adapter.
        """
        if self._journald:
            # Use journald adapter
            yield from self._journald.collect_logs(
                filters=filters,
                follow=follow
            )
        else:
            # Fallback to basic journalctl
            cmd = ['journalctl', '--output=json', '--no-pager']
            
            if follow:
                cmd.append('--follow')
            
            if filters:
                if filters.get('unit'):
                    cmd.extend(['--unit', filters['unit']])
                if filters.get('since'):
                    cmd.extend(['--since', filters['since']])
            
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                for line in proc.stdout:
                    import json
                    try:
                        entry = json.loads(line)
                        yield {
                            'timestamp': entry.get('__REALTIME_TIMESTAMP'),
                            'message': entry.get('MESSAGE', ''),
                            'level': entry.get('PRIORITY', 'info'),
                            'unit': entry.get('_SYSTEMD_UNIT', ''),
                            'host': entry.get('_HOSTNAME', ''),
                            'pid': entry.get('_PID'),
                        }
                    except json.JSONDecodeError:
                        continue
            except FileNotFoundError:
                yield {'error': 'journalctl not found'}
    
    # ==========================================
    # Sensor Reading
    # ==========================================
    
    def read_sensors(self) -> List[Dict[str, Any]]:
        """
        Read sensors from /sys/class/hwmon using adapter.
        """
        if self._hwmon:
            # Use hwmon adapter (returns normalized halbert format)
            readings = self._hwmon.read_all_sensors()
            # Convert to simpler format for platform bridge
            sensors = []
            for reading in readings:
                if 'error' in reading:
                    sensors.append(reading)
                else:
                    sensors.append({
                        'label': reading.get('data', {}).get('label', 'unknown'),
                        'value': reading.get('data', {}).get('temp_c', 0),
                        'type': 'temperature',
                        'unit': '°C',
                    })
            return sensors
        else:
            # Fallback to basic hwmon reading
            sensors = []
            try:
                import glob
                for sensor_file in glob.glob('/sys/class/hwmon/hwmon*/temp*_input'):
                    try:
                        with open(sensor_file, 'r') as f:
                            temp_raw = int(f.read().strip())
                            temp_c = temp_raw / 1000.0
                            
                            # Get label if available
                            label_file = sensor_file.replace('_input', '_label')
                            try:
                                with open(label_file, 'r') as lf:
                                    label = lf.read().strip()
                            except FileNotFoundError:
                                label = sensor_file.split('/')[-1]
                            
                            sensors.append({
                                'label': label,
                                'value': temp_c,
                                'type': 'temperature',
                                'unit': '°C',
                            })
                    except (FileNotFoundError, ValueError):
                        continue
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
        """Manage systemd services using adapter."""
        if self._systemd:
            # Use systemd adapter
            return self._systemd.manage_service(name, action, dry_run)
        else:
            # Fallback to direct systemctl
            valid_actions = ['start', 'stop', 'restart', 'enable', 'disable', 'status']
            
            if action not in valid_actions:
                return {
                    'ok': False,
                    'message': f"Invalid action '{action}'. Valid: {valid_actions}"
                }
            
            cmd = ['systemctl', action, name]
            
            if dry_run:
                return {
                    'ok': True,
                    'message': f"Would execute: {' '.join(cmd)}",
                    'dry_run': True,
                }
            
            return self.execute_command(cmd)
    
    def list_services(self) -> List[Dict[str, Any]]:
        """List systemd services using adapter."""
        if self._systemd:
            # Use systemd adapter
            return self._systemd.list_services()
        else:
            # Fallback to direct systemctl
            result = self.execute_command(
                ['systemctl', 'list-units', '--type=service', '--all', '--no-pager']
            )
            
            services = []
            if result['ok']:
                # Parse systemctl output
                for line in result['stdout'].split('\n')[1:]:  # Skip header
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 4:
                            services.append({
                                'name': parts[0],
                                'loaded': parts[1],
                                'active': parts[2],
                                'status': parts[3],
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
        """Install package using apt (Ubuntu/Debian)."""
        # Detect package manager
        pkg_mgr = self._detect_package_manager()
        
        if pkg_mgr == 'apt':
            cmd = ['apt', 'install', '-y', name]
        elif pkg_mgr == 'yum':
            cmd = ['yum', 'install', '-y', name]
        elif pkg_mgr == 'dnf':
            cmd = ['dnf', 'install', '-y', name]
        else:
            return {
                'ok': False,
                'message': f"No supported package manager found"
            }
        
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
        """List installed packages."""
        pkg_mgr = self._detect_package_manager()
        
        if pkg_mgr == 'apt':
            cmd = ['dpkg', '-l']
        elif pkg_mgr in ['yum', 'dnf']:
            cmd = [pkg_mgr, 'list', 'installed']
        else:
            return []
        
        if pattern:
            cmd.append(pattern)
        
        result = self.execute_command(cmd)
        
        # Parse output (simplified)
        packages = []
        if result['ok']:
            for line in result['stdout'].split('\n'):
                if line.strip() and not line.startswith(('Listing', 'Desired')):
                    parts = line.split()
                    if len(parts) >= 2:
                        packages.append({
                            'name': parts[0] if pkg_mgr == 'apt' else parts[0].rsplit('.', 1)[0],
                            'version': parts[1] if len(parts) > 1 else 'unknown',
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
    
    def _detect_package_manager(self) -> Optional[str]:
        """Detect which package manager is available."""
        for mgr in ['apt', 'dnf', 'yum']:
            if subprocess.run(['which', mgr], capture_output=True).returncode == 0:
                return mgr
        return None
