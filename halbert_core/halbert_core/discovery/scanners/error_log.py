# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Error Log Scanner - Discover recent system errors and failures.

Enables scenarios:
- S1.4: "Recent errors/failures" → What went wrong recently
- S10.3: "App won't start" → Related errors in logs
- S10.6: "System hang" → Kernel/driver errors
- S10.8: "Security breach" → Auth failures

Discovers:
- Recent critical/error log entries
- Grouped by service/component
- Authentication failures
- Kernel errors (dmesg)
- Application crashes
"""

from __future__ import annotations
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime
import re

from .base import BaseScanner
from ..schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class ErrorLogScanner(BaseScanner):
    """
    Scanner for system errors from journal and logs.
    
    Discovers:
    - Recent errors (last boot)
    - Errors by service
    - Authentication failures
    - Kernel errors
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.ALERT
    
    def scan(self) -> List[Discovery]:
        """Scan for recent errors."""
        discoveries = []
        
        discoveries.extend(self._scan_journal_errors())
        discoveries.extend(self._scan_auth_failures())
        discoveries.extend(self._scan_kernel_errors())
        discoveries.append(self._create_error_summary())
        
        self.logger.info(f"Found {len(discoveries)} error discoveries")
        return discoveries
    
    def _scan_journal_errors(self) -> List[Discovery]:
        """Scan journalctl for errors grouped by unit."""
        discoveries = []
        
        # Get errors from current boot grouped by unit
        code, stdout, _ = self.run_command([
            "journalctl", "-b", "-p", "err", 
            "-o", "json", "--no-pager", "-n", "500"
        ], timeout=30)
        
        if code != 0:
            return discoveries
        
        # Group errors by unit
        errors_by_unit: Dict[str, List[dict]] = defaultdict(list)
        
        import json
        for line in stdout.strip().splitlines():
            try:
                entry = json.loads(line)
                unit = entry.get('_SYSTEMD_UNIT', entry.get('SYSLOG_IDENTIFIER', 'unknown'))
                message = entry.get('MESSAGE', '')
                timestamp = entry.get('__REALTIME_TIMESTAMP', 0)
                
                errors_by_unit[unit].append({
                    'message': message[:200] if isinstance(message, str) else str(message)[:200],
                    'timestamp': timestamp,
                })
            except json.JSONDecodeError:
                continue
        
        # Create discovery for each unit with errors (limit to top 10)
        sorted_units = sorted(errors_by_unit.items(), key=lambda x: len(x[1]), reverse=True)
        
        for unit, errors in sorted_units[:10]:
            if len(errors) == 0:
                continue
            
            # Determine severity by error count
            if len(errors) > 20:
                severity = DiscoverySeverity.WARNING
            else:
                severity = DiscoverySeverity.INFO
            
            # Get sample errors
            sample_errors = [e['message'] for e in errors[:5]]
            
            unit_name = unit.replace('.service', '').replace('.', '_')
            discovery_id = make_discovery_id(DiscoveryType.ALERT, f"errors-{unit_name}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.ALERT,
                name=f"errors-{unit_name}",
                title=f"Errors: {unit}",
                description=f"{len(errors)} errors in current boot",
                icon="alert-circle",
                severity=severity,
                status=f"{len(errors)} errors",
                data={
                    "unit": unit,
                    "error_count": len(errors),
                    "sample_errors": sample_errors,
                    "is_error_log": True,
                },
                actions=[
                    DiscoveryAction(
                        id="view-logs",
                        label="View Logs",
                        icon="file-text",
                        command=f"journalctl -u {unit} -b -p err",
                    ),
                ],
                chat_context=f"Service '{unit}' has {len(errors)} errors this boot. "
                            f"Recent errors: {'; '.join(sample_errors[:3])}",
            ))
        
        return discoveries
    
    def _scan_auth_failures(self) -> List[Discovery]:
        """Scan for authentication failures."""
        discoveries = []
        
        # Get auth failures
        code, stdout, _ = self.run_command([
            "journalctl", "-b", "-u", "sshd", "-u", "systemd-logind",
            "--grep", "Failed|failure|invalid|denied",
            "-n", "100", "--no-pager"
        ], timeout=15)
        
        failure_count = 0
        if code == 0 and stdout.strip():
            failure_count = len([l for l in stdout.strip().splitlines() if l.strip()])
        
        if failure_count > 5:
            severity = DiscoverySeverity.WARNING if failure_count > 20 else DiscoverySeverity.INFO
            
            discovery_id = make_discovery_id(DiscoveryType.ALERT, "auth-failures")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.ALERT,
                name="auth-failures",
                title="Authentication Failures",
                description=f"{failure_count} auth failures this boot",
                icon="shield-alert",
                severity=severity,
                status=f"{failure_count} failures",
                data={
                    "failure_count": failure_count,
                    "sample_log": stdout[:500] if stdout else "",
                    "is_security_event": True,
                },
                actions=[
                    DiscoveryAction(
                        id="view-auth",
                        label="View Auth Log",
                        icon="file-text",
                        command="journalctl -b --grep 'Failed|failure' -u sshd -u systemd-logind",
                    ),
                ],
                chat_context=f"Found {failure_count} authentication failures this boot. "
                            f"{'⚠️ High number may indicate brute force attempt.' if failure_count > 20 else ''} "
                            f"Check with 'journalctl --grep Failed'.",
            ))
        
        return discoveries
    
    def _scan_kernel_errors(self) -> List[Discovery]:
        """Scan dmesg for kernel errors."""
        discoveries = []
        
        # Get kernel errors
        code, stdout, _ = self.run_command([
            "dmesg", "--level=err,crit,alert,emerg", "-T"
        ], timeout=10)
        
        if code != 0 or not stdout.strip():
            return discoveries
        
        errors = stdout.strip().splitlines()
        
        if len(errors) > 0:
            # Categorize errors
            hardware_errors = []
            driver_errors = []
            other_errors = []
            
            for error in errors:
                error_lower = error.lower()
                if any(kw in error_lower for kw in ['hardware', 'ata', 'sata', 'nvme', 'usb', 'pci', 'acpi', 'ecc', 'mce']):
                    hardware_errors.append(error)
                elif any(kw in error_lower for kw in ['driver', 'module', 'firmware']):
                    driver_errors.append(error)
                else:
                    other_errors.append(error)
            
            severity = DiscoverySeverity.WARNING if hardware_errors else DiscoverySeverity.INFO
            
            discovery_id = make_discovery_id(DiscoveryType.ALERT, "kernel-errors")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.ALERT,
                name="kernel-errors",
                title="Kernel Errors",
                description=f"{len(errors)} kernel errors (HW: {len(hardware_errors)}, Driver: {len(driver_errors)})",
                icon="cpu",
                severity=severity,
                status=f"{len(errors)} errors",
                data={
                    "total_count": len(errors),
                    "hardware_count": len(hardware_errors),
                    "driver_count": len(driver_errors),
                    "other_count": len(other_errors),
                    "hardware_errors": hardware_errors[:5],
                    "driver_errors": driver_errors[:5],
                    "is_kernel_error": True,
                },
                actions=[
                    DiscoveryAction(
                        id="view-dmesg",
                        label="View dmesg",
                        icon="terminal",
                        command="dmesg --level=err,crit -T | tail -50",
                    ),
                ],
                chat_context=f"Found {len(errors)} kernel errors: {len(hardware_errors)} hardware, "
                            f"{len(driver_errors)} driver-related. "
                            f"{'⚠️ Hardware errors detected - check components.' if hardware_errors else ''}"
                            f"Run 'dmesg --level=err -T' for details.",
            ))
        
        return discoveries
    
    def _create_error_summary(self) -> Discovery:
        """Create overall error summary."""
        # Quick count of errors
        code, stdout, _ = self.run_command([
            "journalctl", "-b", "-p", "err", "--no-pager", "-q"
        ], timeout=15)
        
        total_errors = len(stdout.strip().splitlines()) if code == 0 and stdout else 0
        
        # Get critical count
        code2, stdout2, _ = self.run_command([
            "journalctl", "-b", "-p", "crit", "--no-pager", "-q"
        ], timeout=10)
        
        critical_count = len(stdout2.strip().splitlines()) if code2 == 0 and stdout2 else 0
        
        # Determine severity
        if critical_count > 0:
            severity = DiscoverySeverity.CRITICAL
            status = f"{critical_count} critical, {total_errors} total"
        elif total_errors > 50:
            severity = DiscoverySeverity.WARNING
            status = f"{total_errors} errors"
        elif total_errors > 0:
            severity = DiscoverySeverity.INFO
            status = f"{total_errors} errors"
        else:
            severity = DiscoverySeverity.SUCCESS
            status = "No errors"
        
        discovery_id = make_discovery_id(DiscoveryType.ALERT, "error-summary")
        
        return Discovery(
            id=discovery_id,
            type=DiscoveryType.ALERT,
            name="error-summary",
            title="Error Summary",
            description=f"System has {total_errors} errors this boot ({critical_count} critical)",
            icon="alert-triangle",
            severity=severity,
            status=status,
            data={
                "total_errors": total_errors,
                "critical_count": critical_count,
                "is_summary": True,
            },
            chat_context=f"System error summary: {total_errors} total errors this boot, "
                        f"{critical_count} critical. "
                        f"{'⚠️ System has critical errors that need attention!' if critical_count > 0 else ''}"
                        f"{'System is experiencing many errors.' if total_errors > 50 else ''}",
        )
