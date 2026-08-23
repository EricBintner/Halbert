"""
FreeBSD Handbook scraper.

Scrapes the FreeBSD Handbook from docs.freebsd.org.
Licensed under the FreeBSD Documentation License (BSD-like, permits redistribution
with copyright notice).

The FreeBSD Handbook covers many concepts shared with macOS (BSD-derived),
including networking, filesystem, security, and system administration.
Works on any platform.
"""

import logging
import json
import re
import hashlib
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class FreeBSDHandbookScraper(BaseScraper):
    """
    Scrape the FreeBSD Handbook from docs.freebsd.org.

    Sources:
    - https://docs.freebsd.org/en/books/handbook/
    - License: FreeBSD Documentation License (redistribution permitted with attribution)
    """

    HANDBOOK_BASE = "https://docs.freebsd.org/en/books/handbook"

    # Chapter slugs mapped to categories
    CHAPTERS = [
        ("introduction", "general", "Introduction"),
        ("bsdinstall", "installation", "Installing FreeBSD"),
        ("basics", "system_admin", "FreeBSD Basics"),
        ("ports", "package_management", "Installing Applications: Packages and Ports"),
        ("x11", "desktop", "The X Window System"),
        ("wayland", "desktop", "Wayland"),
        ("desktop", "desktop", "Desktop Applications"),
        ("multimedia", "multimedia", "Multimedia"),
        ("kernelconfig", "kernel", "Configuring the FreeBSD Kernel"),
        ("printing", "peripherals", "Printing"),
        ("linuxemu", "compatibility", "Linux Binary Compatibility"),
        ("wine", "compatibility", "Wine"),
        ("config", "system_admin", "Configuration and Tuning"),
        ("boot", "boot", "The Booting Process"),
        ("security", "security", "Security"),
        ("jails", "containers", "Jails"),
        ("containers", "containers", "FreeBSD Containers"),
        ("mac", "security", "Mandatory Access Control"),
        ("audit", "security", "Security Event Auditing"),
        ("disks", "storage", "Storage"),
        ("geom", "storage", "GEOM: Modular Disk Transformation Framework"),
        ("zfs", "storage", "The Z File System (ZFS)"),
        ("filesystems", "storage", "Other File Systems"),
        ("virtualization", "virtualization", "Virtualization Guests"),
        ("l10n", "localization", "Localization - i18n/L10n Setup and Use"),
        ("cutting-edge", "updates", "Updating and Upgrading FreeBSD"),
        ("dtrace", "debugging", "DTrace"),
        ("usb-device-mode", "peripherals", "USB Device Mode"),
        ("serialcomms", "peripherals", "Serial Communications"),
        ("ppp-and-slip", "networking", "PPP and SLIP"),
        ("mail", "networking", "Electronic Mail"),
        ("network-servers", "networking", "Network Servers"),
        ("firewalls", "security", "Firewalls"),
        ("advanced-networking", "networking", "Advanced Networking"),
        ("network", "networking", "Network Configuration"),
        ("mirrors", "installation", "Obtaining FreeBSD"),
        ("bibliography", "general", "Bibliography"),
        ("eresources", "general", "Resources on the Internet"),
        ("pgpkeys", "security", "PGP Keys"),
        ("colophon", "general", "Colophon"),
        ("glossary", "general", "Glossary"),
    ]

    def __init__(self, config: ScraperConfig):
        """Initialize FreeBSD Handbook scraper."""
        super().__init__(config)

    def get_source_name(self) -> str:
        """Get source name."""
        return "freebsd-handbook"

    def scrape(self) -> List[ScrapedDocument]:
        """
        Scrape FreeBSD Handbook chapters.

        Returns:
            List of scraped documents
        """
        documents = []

        logger.info(f"Scraping {len(self.CHAPTERS)} FreeBSD Handbook chapters...")

        for slug, category, title in self.CHAPTERS:
            url = f"{self.HANDBOOK_BASE}/{slug}/"

            try:
                html = self.fetch_url(url)
                if html is None:
                    logger.warning(f"Failed to fetch chapter: {slug}")
                    continue

                content = self._extract_content(html)

                if content and len(content) > 200:
                    doc_id = f"freebsd-handbook-{slug}"

                    documents.append(ScrapedDocument(
                        id=doc_id,
                        url=url,
                        title=f"FreeBSD Handbook: {title}",
                        content=content,
                        source="freebsd-handbook",
                        category=category,
                        tags=["freebsd", "bsd", "macos", "handbook", slug],
                        scraped_at=datetime.utcnow().isoformat(),
                        metadata={
                            "platform": "bsd",
                            "doc_type": "handbook_chapter",
                            "chapter": slug,
                            "license": "FreeBSD Documentation License",
                        }
                    ))
                    logger.info(f"Scraped chapter: {title} ({len(content)} chars)")
                else:
                    logger.warning(f"Chapter {slug} had insufficient content")

            except Exception as e:
                logger.warning(f"Failed to scrape {slug}: {e}")

        logger.info(f"Total FreeBSD Handbook documents: {len(documents)}")
        return documents

    def _extract_content(self, html: str) -> str:
        """Extract main content from FreeBSD Handbook page."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # FreeBSD docs use AsciiDoc rendered to HTML
            # Main content is usually in <main> or <article> or <div class="body">
            main = (
                soup.find('main')
                or soup.find('article')
                or soup.find('div', class_='body')
                or soup.find('div', class_='content')
                or soup.find('div', id='content')
            )

            if not main:
                # Fallback: get body but remove nav/header/footer
                main = soup.find('body')
                if main:
                    for tag in main.find_all(['nav', 'header', 'footer', 'script', 'style']):
                        tag.decompose()

            if main:
                # Remove navigation, scripts, styles, edit links
                for tag in main.find_all(['script', 'style', 'nav', 'header', 'footer']):
                    tag.decompose()

                # Remove "Edit" links and page navigation
                for tag in main.find_all('a', class_=re.compile(r'edit|nav|prev|next', re.I)):
                    tag.decompose()

                # Remove TOC if present
                toc = main.find('div', class_=re.compile(r'toc', re.I))
                if toc:
                    toc.decompose()

                text = main.get_text(separator='\n', strip=True)

                # Clean up
                text = re.sub(r'\n{3,}', '\n\n', text)
                text = re.sub(r'Edit\s*$', '', text, flags=re.MULTILINE)

                return text.strip()

            return ""
        except Exception as e:
            logger.debug(f"Failed to extract content: {e}")
            return ""


def main():
    """CLI entry point for FreeBSD Handbook scraper."""
    import argparse

    parser = argparse.ArgumentParser(description="Scrape FreeBSD Handbook")
    parser.add_argument('--output-dir', type=Path, required=True, help="Output directory")
    parser.add_argument('--rate-limit', type=float, default=2.0, help="Seconds between requests")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    config = ScraperConfig(
        output_dir=args.output_dir,
        rate_limit_delay=args.rate_limit,
    )

    scraper = FreeBSDHandbookScraper(config)
    documents = scraper.scrape()

    # Save to JSONL
    output_file = args.output_dir / "freebsd_handbook.jsonl"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        for doc in documents:
            f.write(json.dumps(doc.to_dict()) + '\n')

    print(f"Saved {len(documents)} documents to {output_file}")


if __name__ == '__main__':
    main()
