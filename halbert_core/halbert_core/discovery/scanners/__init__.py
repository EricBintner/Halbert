"""
Discovery Scanners - Find things on the system.

Each scanner implements BaseScanner and produces Discovery objects.

Scanners map to user scenarios (docs/Genesis/scenarios/):

System/Performance:
- ProcessScanner: S1.2, S1.6, S10.6, S11.2 (resource hogs, hangs)
- ThermalScanner: S1.3, S2.6, S8.2, S9.10 (temps, fans)
- ErrorLogScanner: S1.4, S10.x (recent errors, diagnostics)

Boot/System:
- BootScanner: S2.4 (boot time, slow services)
- BootloaderScanner: S10.1, S10.2 (GRUB, UEFI, secure boot)

Packages/Updates:
- PackageScanner: S4.1-S4.7, S10.10 (updates, orphans, locks)

Storage:
- StorageScanner: S5.5, S5.6 (disks, SMART, pools)
- DiskUsageScanner: S5.2, S10.4, S9.8 (space hogs, cleanup)

Network/Wireless:
- NetworkScanner: S6.1, S6.3 (interfaces, connectivity)
- WifiScanner: S6.6 (WiFi issues, signal, drivers)

Desktop/Display:
- DisplayScanner: S8.3 (monitors, GPUs, hybrid graphics)
- AudioScanner: audio devices, PulseAudio/PipeWire

Hardware:
- LaptopScanner: battery, power profiles, suspend
- UsbScanner: USB devices, speed, peripherals
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
from .laptop import LaptopScanner
from .display import DisplayScanner
from .audio import AudioScanner
from .bootloader import BootloaderScanner
from .wifi import WifiScanner
from .usb import UsbScanner

__all__ = [
    'BaseScanner',
    # Core
    'BackupScanner',
    'ServiceScanner', 
    'StorageScanner',
    'NetworkScanner',
    'SecurityScanner',
    # System/Performance
    'ProcessScanner',
    'ThermalScanner',
    'ErrorLogScanner',
    # Boot
    'BootScanner',
    'BootloaderScanner',
    # Packages
    'PackageScanner',
    # Storage
    'DiskUsageScanner',
    # Network
    'WifiScanner',
    # Desktop
    'DisplayScanner',
    'AudioScanner',
    # Hardware
    'LaptopScanner',
    'UsbScanner',
]
