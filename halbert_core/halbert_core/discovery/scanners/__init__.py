"""
Discovery Scanners - Find things on the system.

Each scanner implements BaseScanner and produces Discovery objects.

Scanners map to user scenarios (docs/Genesis/scenarios/):
- ProcessScanner: S1.2, S1.6, S10.6, S11.2 (resource hogs, hangs)
- ThermalScanner: S1.3, S2.6, S8.2, S9.10 (temps, fans)
- BootScanner: S2.4, S10.1, S10.2 (boot time, recovery)
- PackageScanner: S4.1-S4.7, S10.10 (updates, orphans, locks)
- DiskUsageScanner: S5.2, S10.4, S9.8 (space hogs, cleanup)
- ErrorLogScanner: S1.4, S10.x (recent errors, diagnostics)
"""

from .base import BaseScanner
from .backup import BackupScanner
from .service import ServiceScanner
from .storage import StorageScanner
from .network import NetworkScanner
from .security import SecurityScanner
from .process import ProcessScanner
from .thermal import ThermalScanner
from .boot import BootScanner
from .package import PackageScanner
from .disk_usage import DiskUsageScanner
from .error_log import ErrorLogScanner

__all__ = [
    'BaseScanner',
    'BackupScanner',
    'ServiceScanner', 
    'StorageScanner',
    'NetworkScanner',
    'SecurityScanner',
    'ProcessScanner',
    'ThermalScanner',
    'BootScanner',
    'PackageScanner',
    'DiskUsageScanner',
    'ErrorLogScanner',
]
