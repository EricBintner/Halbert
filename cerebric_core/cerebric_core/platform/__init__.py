"""
Platform abstraction layer for Cerebric.

Provides unified interface for platform-specific operations (Linux, macOS).
Automatically detects platform and loads appropriate implementation.
"""

import sys
from typing import Optional
from .base import PlatformBridge


_platform_cache: Optional[PlatformBridge] = None


def get_platform_bridge() -> PlatformBridge:
    """
    Get platform bridge for current system.
    
    Auto-detects platform and returns appropriate implementation.
    Result is cached after first call.
    
    Returns:
        PlatformBridge instance for current platform
        
    Raises:
        UnsupportedPlatformError: If platform is not supported
    """
    global _platform_cache
    
    if _platform_cache is not None:
        return _platform_cache
    
    platform = sys.platform
    
    if platform.startswith('linux'):
        from .linux import LinuxPlatformBridge
        _platform_cache = LinuxPlatformBridge()
    elif platform == 'darwin':
        from .macos import MacPlatformBridge
        _platform_cache = MacPlatformBridge()
    else:
        raise UnsupportedPlatformError(
            f"Platform '{platform}' is not supported. "
            f"Supported platforms: linux, darwin (macOS)"
        )
    
    return _platform_cache


def reset_platform_cache():
    """Reset platform cache (useful for testing)."""
    global _platform_cache
    _platform_cache = None


class UnsupportedPlatformError(Exception):
    """Raised when platform is not supported."""
    pass


__all__ = [
    'PlatformBridge',
    'get_platform_bridge',
    'reset_platform_cache',
    'UnsupportedPlatformError',
]
