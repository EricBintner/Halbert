# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
macOS Discovery Scanners - Find things on macOS systems.

Each scanner implements BaseScanner and produces Discovery objects.
These are macOS equivalents of the Linux scanners.

Phase 25: macOS Platform Support

Cross-platform scanners (work as-is on macOS):
- ProcessScanner: psutil-based, no changes needed
- DiskUsageScanner: pathlib-based, no changes needed
- ContainerScanner: Docker CLI, works on macOS
- VirtualizationScanner: Detection only

macOS-specific scanners (this module):
- LaunchdScanner: launchd service discovery
- HomebrewScanner: Homebrew package management
- MacThermalScanner: IOKit temperature sensors
- MacNetworkScanner: networksetup-based
- MacWifiScanner: airport utility
- MacDisplayScanner: system_profiler displays
- MacAudioScanner: CoreAudio devices
- MacLaptopScanner: pmset, battery info
- MacUsbScanner: system_profiler USB
- MacStorageScanner: diskutil, APFS
- MacSecurityScanner: Gatekeeper, SIP
- MacErrorLogScanner: Unified Logging
- TimeMachineScanner: tmutil backup status
- MacScheduledScanner: launchd + cron
"""

from .launchd import LaunchdScanner
from .homebrew import HomebrewScanner
from .thermal import MacThermalScanner
from .network import MacNetworkScanner
from .storage import MacStorageScanner
from .security import MacSecurityScanner
from .timemachine import TimeMachineScanner
# Phase 26: Apps tab scanners
from .homebrew_apps import HomebrewAppScanner
from .mas import MacAppStoreScanner

__all__ = [
    'LaunchdScanner',
    'HomebrewScanner',
    'MacThermalScanner',
    'MacNetworkScanner',
    'MacStorageScanner',
    'MacSecurityScanner',
    'TimeMachineScanner',
    # Phase 26: Apps tab
    'HomebrewAppScanner',
    'MacAppStoreScanner',
]
