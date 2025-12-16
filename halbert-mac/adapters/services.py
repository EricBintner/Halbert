"""
macOS launchd service management adapter.

Provides launchd-specific service management functionality.
Equivalent to Linux systemd adapter.
"""

import subprocess
from typing import Dict, Any, List, Optional


class LaunchdAdapter:
    """
    Adapter for macOS launchd service management.
    
    Equivalent to Linux SystemdAdapter, but uses macOS launchctl.
    """
    
    def __init__(self):
        self.name = "launchd"
    
    def manage_service(
        self,
        name: str,
        action: str,
        dry_run: bool = False,
        domain: str = 'system'
    ) -> Dict[str, Any]:
        """
        Manage a launchd service.
        
        Args:
            name: Service name (e.g., 'com.apple.sshd')
            action: Action (start, stop, restart, enable, disable, status)
            dry_run: If True, don't actually execute
            domain: Service domain ('system', 'user', 'gui/<uid>')
            
        Returns:
            Result dict
        """
        valid_actions = ['start', 'stop', 'restart', 'enable', 'disable', 'status']
        
        if action not in valid_actions:
            return {
                'ok': False,
                'message': f"Invalid action '{action}'. Valid: {valid_actions}"
            }
        
        # Build launchctl command
        # Note: launchd uses different commands than systemd
        if action == 'start':
            # Load the service
            cmd = ['launchctl', 'bootstrap', domain, f'/Library/LaunchDaemons/{name}.plist']
        elif action == 'stop':
            # Unload the service
            cmd = ['launchctl', 'bootout', domain, f'/Library/LaunchDaemons/{name}.plist']
        elif action == 'restart':
            # launchd doesn't have direct restart, return error
            return {
                'ok': False,
                'message': 'Restart not directly supported by launchd. Use stop then start.'
            }
        elif action == 'enable':
            # Enable service
            cmd = ['launchctl', 'enable', f'{domain}/{name}']
        elif action == 'disable':
            # Disable service
            cmd = ['launchctl', 'disable', f'{domain}/{name}']
        elif action == 'status':
            # Check if service is loaded
            cmd = ['launchctl', 'list', name]
        
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
    
    def list_services(self) -> List[Dict[str, Any]]:
        """
        List launchd services.
        
        Returns:
            List of service info dicts
        """
        try:
            result = subprocess.run(
                ['launchctl', 'list'],
                capture_output=True,
                text=True
            )
            
            services = []
            if result.returncode == 0:
                # Parse launchctl list output
                # Format: PID Status Label
                for line in result.stdout.split('\n')[1:]:  # Skip header
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 3:
                            services.append({
                                'pid': parts[0],
                                'status': parts[1],
                                'name': parts[2],
                            })
                        elif len(parts) == 2:
                            # Some services don't have PID
                            services.append({
                                'pid': '-',
                                'status': parts[0],
                                'name': parts[1],
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
                ['launchctl', 'list', name],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Service is loaded
                # Parse output to get PID and status
                output = result.stdout
                
                # Extract PID from output
                import re
                pid_match = re.search(r'"PID"\s*=\s*(\d+)', output)
                pid = int(pid_match.group(1)) if pid_match else None
                
                # Extract LastExitStatus
                exit_match = re.search(r'"LastExitStatus"\s*=\s*(\d+)', output)
                exit_status = int(exit_match.group(1)) if exit_match else 0
                
                return {
                    'ok': True,
                    'name': name,
                    'loaded': True,
                    'active': pid is not None,
                    'pid': pid,
                    'exit_status': exit_status,
                    'output': output,
                }
            else:
                # Service not loaded
                return {
                    'ok': True,
                    'name': name,
                    'loaded': False,
                    'active': False,
                    'message': 'Service not loaded',
                }
        
        except Exception as e:
            return {
                'ok': False,
                'error': str(e),
            }
    
    def is_available(self) -> bool:
        """
        Check if launchd is available.
        
        Returns:
            True if launchctl command exists
        """
        try:
            result = subprocess.run(
                ['which', 'launchctl'],
                capture_output=True
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def list_launch_daemons(self) -> List[str]:
        """
        List available launch daemon plist files.
        
        Returns:
            List of daemon names
        """
        import glob
        import os
        
        daemons = []
        
        # System daemons
        for path in glob.glob('/Library/LaunchDaemons/*.plist'):
            daemon_name = os.path.basename(path).replace('.plist', '')
            daemons.append(daemon_name)
        
        # User daemons (if running as user)
        user_daemons_path = os.path.expanduser('~/Library/LaunchAgents')
        if os.path.exists(user_daemons_path):
            for path in glob.glob(f'{user_daemons_path}/*.plist'):
                daemon_name = os.path.basename(path).replace('.plist', '')
                daemons.append(daemon_name)
        
        return sorted(daemons)
