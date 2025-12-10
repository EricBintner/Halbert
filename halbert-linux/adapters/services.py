"""
Linux systemd service management adapter.

Provides systemd-specific service management functionality.
"""

import subprocess
from typing import Dict, Any, List, Optional


class SystemdAdapter:
    """
    Adapter for Linux systemd service management.
    """
    
    def __init__(self):
        self.name = "systemd"
    
    def manage_service(
        self,
        name: str,
        action: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Manage a systemd service.
        
        Args:
            name: Service name
            action: Action (start, stop, restart, enable, disable, status)
            dry_run: If True, don't actually execute
            
        Returns:
            Result dict
        """
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
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
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
    
    def list_services(
        self,
        service_type: str = 'service'
    ) -> List[Dict[str, Any]]:
        """
        List systemd services.
        
        Args:
            service_type: Type of unit (service, timer, etc.)
            
        Returns:
            List of service info dicts
        """
        try:
            result = subprocess.run(
                ['systemctl', 'list-units', f'--type={service_type}', '--all', '--no-pager'],
                capture_output=True,
                text=True
            )
            
            services = []
            if result.returncode == 0:
                # Parse systemctl output (skip header)
                for line in result.stdout.split('\n')[1:]:
                    if line.strip() and not line.startswith('UNIT'):
                        parts = line.split()
                        if len(parts) >= 4:
                            services.append({
                                'name': parts[0],
                                'loaded': parts[1],
                                'active': parts[2],
                                'status': parts[3],
                            })
            
            return services
        
        except Exception as e:
            return [{'error': str(e)}]
    
    def get_service_status(self, name: str) -> Dict[str, Any]:
        """
        Get detailed status of a service.
        
        Args:
            name: Service name
            
        Returns:
            Status dict
        """
        try:
            result = subprocess.run(
                ['systemctl', 'status', name],
                capture_output=True,
                text=True
            )
            
            # Parse status output
            is_active = 'active (running)' in result.stdout
            is_enabled = subprocess.run(
                ['systemctl', 'is-enabled', name],
                capture_output=True,
                text=True
            ).stdout.strip() == 'enabled'
            
            return {
                'ok': True,
                'name': name,
                'active': is_active,
                'enabled': is_enabled,
                'status': result.stdout,
            }
        
        except Exception as e:
            return {
                'ok': False,
                'error': str(e),
            }
    
    def is_available(self) -> bool:
        """
        Check if systemd is available.
        
        Returns:
            True if systemctl command exists
        """
        try:
            result = subprocess.run(
                ['which', 'systemctl'],
                capture_output=True
            )
            return result.returncode == 0
        except Exception:
            return False
