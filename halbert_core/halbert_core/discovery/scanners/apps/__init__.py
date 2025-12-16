"""
Application Discovery Scanners - Find installed apps across package formats.

Phase 26: Universal App Management

Linux:
- FlatpakScanner: Flatpak applications
- SnapScanner: Snap packages
- AppImageScanner: AppImage files

Cross-platform scanners in parent directory handle native packages.
macOS-specific scanners in ../macos/ handle Homebrew and App Store.
"""

from .flatpak import FlatpakScanner
from .snap import SnapScanner
from .appimage import AppImageScanner

__all__ = [
    'FlatpakScanner',
    'SnapScanner',
    'AppImageScanner',
]
