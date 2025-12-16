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

__all__ = [
    'BaseScraper',
    'ScraperConfig',
    'ScrapedDocument',
    # Linux
    'ArchWikiScraper',
    'StackOverflowScraper',
    # Linux App Formats (Phase 26)
    'FlatpakDocsScraper',
    'SnapDocsScraper',
    'AppImageDocsScraper',
    # macOS
    'HomebrewScraper',
    'MacOSSupportScraper',
]
