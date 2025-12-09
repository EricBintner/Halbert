"""
Linux platform adapters.

Provides Linux-specific implementations:
- ingestion: journald log collection
- sensors: hwmon hardware sensors
- services: systemd service management
"""

from .ingestion import JournaldAdapter
from .sensors import HwmonAdapter
from .services import SystemdAdapter

__all__ = [
    'JournaldAdapter',
    'HwmonAdapter',
    'SystemdAdapter',
]
