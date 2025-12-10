"""
Web scrapers for RAG data acquisition.

Scrapes documentation from various sources:
- Arch Wiki
- Stack Overflow
- Ubuntu Documentation
- Apple Developer Documentation
"""

from .base import BaseScraper, ScraperConfig, ScrapedDocument
from .arch_wiki import ArchWikiScraper
from .stackoverflow import StackOverflowScraper

__all__ = [
    'BaseScraper',
    'ScraperConfig',
    'ScrapedDocument',
    'ArchWikiScraper',
    'StackOverflowScraper',
]
