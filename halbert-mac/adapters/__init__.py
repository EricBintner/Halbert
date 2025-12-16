"""
macOS platform adapters.

Provides macOS-specific implementations:
- ingestion: Unified Logging collection
- sensors: IOKit hardware sensors
- services: launchd service management
"""

from .ingestion import UnifiedLoggingAdapter
from .sensors import IOKitAdapter
from .services import LaunchdAdapter

__all__ = [
    'UnifiedLoggingAdapter',
    'IOKitAdapter',
    'LaunchdAdapter',
]
