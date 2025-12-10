"""
Dry-run simulator for approval workflows.

Phase 3 M4: Simulates actions before execution to show user what will happen.
"""

from __future__ import annotations
import logging
import subprocess
import difflib
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger('halbert.approval.simulator')


@dataclass
class SimulationResult:
    """
    Result of dry-run simulation.
    
    Shows user what will happen if action is executed.
    """
    success: bool
    action: str
    
    # Before/after state
    before: Dict[str, Any]
    after: Dict[str, Any]
    
    # Changes (for diff display)
    changes: List[Dict[str, Any]]
    
    # Side effects
    affected_files: List[str]
    affected_services: List[str]
    affected_processes: List[int]
    
    # Warnings
    warnings: List[str]
    
    # Execution details
    commands_to_run: List[str]
    estimated_duration_s: float
    reversible: bool
    rollback_strategy: Optional[str] = None
    
    # Error if simulation failed
    error: Optional[str] = None


class DryRunSimulator:
    """
    Simulates autonomous actions before execution.
    
    Provides dry-run capabilities for different action types:
    - File modifications (show diffs)
    - Configuration changes (show before/after)
    - System commands (show what will run)
    - Service operations (show affected services)
    
    Example:
        simulator = DryRunSimulator()
        
        result = simulator.simulate_file_write(
            path='/etc/myapp/config.yml',
            new_content='...',
            current_content='...'
        )
        
        # Show user the diff
        for change in result.changes:
            print(change['diff'])
    """
    
    def simulate_file_write(
        self,
        path: str,
        new_content: str,
        current_content: Optional[str] = None
    ) -> SimulationResult:
        """
        Simulate file write operation.
        
        Args:
            path: File path to write
            new_content: New file content
            current_content: Current content (or None if file doesn't exist)
        
        Returns:
            SimulationResult with diff
        """
        if current_content is None:
            # File doesn't exist - will be created
            diff_lines = [
                f"+++ {path} (new file)",
                "",
                *[f"+ {line}" for line in new_content.splitlines()]
            ]
            
            changes = [{
                'type': 'file_create',
                'path': path,
                'diff': '\n'.join(diff_lines)
            }]
            
            warnings = [f"New file will be created: {path}"]
            reversible = True
            rollback_strategy = f"Delete {path}"
        
        else:
            # File exists - will be modified
            diff = difflib.unified_diff(
                current_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"{path} (current)",
                tofile=f"{path} (new)",
                lineterm=''
            )
            
            diff_text = '\n'.join(diff)
            
            changes = [{
                'type': 'file_modify',
                'path': path,
                'diff': diff_text
            }]
            
            warnings = []
            reversible = True
            rollback_strategy = f"Restore {path} from backup"
        
        return SimulationResult(
            success=True,
            action=f"Write file: {path}",
            before={'file': path, 'exists': current_content is not None},
            after={'file': path, 'exists': True},
            changes=changes,
            affected_files=[path],
            affected_services=[],
            affected_processes=[],
            warnings=warnings,
            commands_to_run=[f"write_file('{path}', <content>)"],
            estimated_duration_s=0.1,
            reversible=reversible,
            rollback_strategy=rollback_strategy
        )
    
    def simulate_command(
        self,
        command: str,
        dry_run_flag: Optional[str] = None
    ) -> SimulationResult:
        """
        Simulate command execution.
        
        Args:
            command: Command to run
            dry_run_flag: Dry-run flag for the command (e.g., '--dry-run')
        
        Returns:
            SimulationResult with command output
        """
        warnings = []
        
        # Detect dangerous commands
        dangerous_keywords = ['rm -rf', 'dd if=', 'mkfs', 'fdisk', ':(){:|:&};:']
        for keyword in dangerous_keywords:
            if keyword in command:
                warnings.append(f"DANGER: Command contains '{keyword}'")
        
        # Try to run with dry-run flag if provided
        if dry_run_flag:
            try:
                result = subprocess.run(
                    f"{command} {dry_run_flag}",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                output = result.stdout + result.stderr
                
                changes = [{
                    'type': 'command_output',
                    'command': command,
                    'dry_run_output': output
                }]
                
                return SimulationResult(
                    success=True,
                    action=f"Execute: {command}",
                    before={},
                    after={},
                    changes=changes,
                    affected_files=[],
                    affected_services=[],
                    affected_processes=[],
                    warnings=warnings,
                    commands_to_run=[command],
                    estimated_duration_s=1.0,
                    reversible=False,
                    rollback_strategy=None
                )
            
            except Exception as e:
                logger.warning(f"Dry-run execution failed: {e}")
        
        # Fallback: Just show what will run
        changes = [{
            'type': 'command',
            'command': command,
            'note': 'Dry-run not available for this command'
        }]
        
        return SimulationResult(
            success=True,
            action=f"Execute: {command}",
            before={},
            after={},
            changes=changes,
            affected_files=[],
            affected_services=[],
            affected_processes=[],
            warnings=warnings + ['Cannot preview command output (no dry-run support)'],
            commands_to_run=[command],
            estimated_duration_s=1.0,
            reversible=False,
            rollback_strategy=None
        )
    
    def simulate_service_restart(
        self,
        service: str
    ) -> SimulationResult:
        """
        Simulate service restart.
        
        Args:
            service: Service name (e.g., 'nginx')
        
        Returns:
            SimulationResult with service impact
        """
        changes = [{
            'type': 'service_restart',
            'service': service,
            'steps': [
                f'1. Stop {service}',
                f'2. Wait for graceful shutdown (~5s)',
                f'3. Start {service}',
                f'4. Wait for healthy status (~10s)'
            ]
        }]
        
        warnings = [
            f"Service '{service}' will be briefly unavailable (~15s)",
            "Active connections may be dropped"
        ]
        
        return SimulationResult(
            success=True,
            action=f"Restart service: {service}",
            before={'service': service, 'status': 'running'},
            after={'service': service, 'status': 'running'},
            changes=changes,
            affected_files=[],
            affected_services=[service],
            affected_processes=[],
            warnings=warnings,
            commands_to_run=[f"systemctl restart {service}"],
            estimated_duration_s=15.0,
            reversible=True,
            rollback_strategy=f"systemctl start {service} (if fails to restart)"
        )
    
    def simulate_fan_throttle(
        self,
        current_rpm: int,
        target_rpm: int,
        hwmon_path: str
    ) -> SimulationResult:
        """
        Simulate fan speed change.
        
        Args:
            current_rpm: Current fan speed
            target_rpm: Target fan speed
            hwmon_path: Path to hwmon PWM control
        
        Returns:
            SimulationResult with fan change details
        """
        # Calculate PWM value (simplified)
        # Assume: 0 RPM = PWM 0, 5000 RPM = PWM 255
        current_pwm = int((current_rpm / 5000) * 255)
        target_pwm = int((target_rpm / 5000) * 255)
        
        changes = [{
            'type': 'hardware_control',
            'device': 'cpu_fan',
            'parameter': 'speed',
            'before': f"{current_rpm} RPM (PWM {current_pwm})",
            'after': f"{target_rpm} RPM (PWM {target_pwm})",
            'change': f"{target_rpm - current_rpm:+d} RPM"
        }]
        
        warnings = []
        if target_rpm > 4000:
            warnings.append("High fan speed may be noisy")
        if target_rpm < 1000:
            warnings.append("Low fan speed may cause overheating")
        
        return SimulationResult(
            success=True,
            action=f"Adjust fan speed: {current_rpm} → {target_rpm} RPM",
            before={'fan_rpm': current_rpm, 'fan_pwm': current_pwm},
            after={'fan_rpm': target_rpm, 'fan_pwm': target_pwm},
            changes=changes,
            affected_files=[hwmon_path],
            affected_services=[],
            affected_processes=[],
            warnings=warnings,
            commands_to_run=[f"echo {target_pwm} > {hwmon_path}"],
            estimated_duration_s=0.5,
            reversible=True,
            rollback_strategy=f"echo {current_pwm} > {hwmon_path}"
        )
    
    def simulate_package_update(
        self,
        packages: List[str],
        package_manager: str = 'apt'
    ) -> SimulationResult:
        """
        Simulate package update.
        
        Args:
            packages: List of package names
            package_manager: Package manager ('apt', 'dnf', 'pacman')
        
        Returns:
            SimulationResult with package changes
        """
        changes = [{
            'type': 'package_update',
            'packages': packages,
            'count': len(packages)
        }]
        
        warnings = [
            f"{len(packages)} package(s) will be updated",
            "System may require reboot if kernel is updated"
        ]
        
        # Build command based on package manager
        commands = {
            'apt': f"apt-get install --dry-run {' '.join(packages)}",
            'dnf': f"dnf update --assumeno {' '.join(packages)}",
            'pacman': f"pacman -S --print {' '.join(packages)}"
        }
        
        cmd = commands.get(package_manager, f"update {' '.join(packages)}")
        
        return SimulationResult(
            success=True,
            action=f"Update packages: {', '.join(packages)}",
            before={'packages': packages, 'version': 'current'},
            after={'packages': packages, 'version': 'latest'},
            changes=changes,
            affected_files=[],
            affected_services=[],
            affected_processes=[],
            warnings=warnings,
            commands_to_run=[cmd],
            estimated_duration_s=60.0,
            reversible=False,
            rollback_strategy="Package downgrade possible but complex"
        )
