"""
Web scrapers for RAG data acquisition.

Scrapes documentation from various sources:

Linux:
- Arch Wiki
- Stack Overflow
- Man pages

macOS (Phase 25):
- Homebrew documentation & formulas
- macOS command reference (SS64)
- macOS man pages (requires macOS)
- macOS support guides
"""

from .base import BaseScraper, ScraperConfig, ScrapedDocument
from .arch_wiki import ArchWikiScraper
from .stackoverflow import StackOverflowScraper
from .homebrew import HomebrewScraper
from .macos_support import MacOSSupportScraper
from .flatpak_docs import FlatpakDocsScraper
from .snap_docs import SnapDocsScraper
from .appimage_docs import AppImageDocsScraper
# Phase 27: RAG Coverage
from .systemd_docs import SystemdDocsScraper
from .unix_se import UnixSEScraper
from .serverfault import ServerFaultScraper
from .ubuntu_docs import UbuntuDocsScraper
from .networking_docs import NetworkingDocsScraper

__all__ = [
    'BaseScraper',
    'ScraperConfig',
    'ScrapedDocument',
    # Linux Core
    'ArchWikiScraper',
    'StackOverflowScraper',
    # Linux App Formats (Phase 26)
    'FlatpakDocsScraper',
    'SnapDocsScraper',
    'AppImageDocsScraper',
    # Phase 27: RAG Coverage
    'SystemdDocsScraper',
    'UnixSEScraper',
    'ServerFaultScraper',
    'UbuntuDocsScraper',
    'NetworkingDocsScraper',
    # macOS
    'HomebrewScraper',
    'MacOSSupportScraper',
]
