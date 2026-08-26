# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
MacPorts Guide scraper.

Scrapes the MacPorts Guide from guide.macports.org.
MacPorts is the second major package manager for macOS (after Homebrew).
The guide covers installation, portfile authoring, and system administration.

License: The MacPorts Guide source is on GitHub (macports/macports-guide)
and the MacPorts project uses a BSD-like license.
"""

import logging
import json
import re
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class MacPortsGuideScraper(BaseScraper):
    """
    Scrape the MacPorts Guide from guide.macports.org.

    Sources:
    - https://guide.macports.org/
    - License: BSD-like (Apple/MacPorts Project)
    """

    GUIDE_BASE = "https://guide.macports.org"

    # Guide chapters to scrape
    CHAPTERS = [
        ("index.html", "introduction", "MacPorts Guide - Introduction"),
        ("#introduction.installing", "installation", "Installing MacPorts"),
        ("chunked/internals.html", "internals", "MacPorts Internals"),
        ("chunked/internals.installing.macports.html", "installation", "Installing MacPorts (Detailed)"),
        ("chunked/internals.macports.subports.html", "development", "Subports"),
        ("chunked/internals.macports.api.html", "api", "MacPorts API"),
        ("chunked/internals.tests.html", "testing", "MacPorts Tests"),
        ("chunked/development.html", "development", "Portfile Development"),
        ("chunked/development.practices.html", "development", "Development Practices"),
        ("chunked/development.creating-portfile.html", "development", "Creating a Portfile"),
        ("chunked/development.dependencies.html", "development", "Port Dependencies"),
        ("chunked/development.variants.html", "development", "Port Variants"),
        ("chunked/development.patchfiles.html", "development", "Patch Files"),
        ("chunked/development.distfiles.html", "development", "Distfiles"),
        ("chunked/development.checksums.html", "development", "Checksums"),
        ("chunked/development.fetching.html", "development", "Fetching"),
        ("chunked/development.extract.html", "development", "Extract Phase"),
        ("chunked/development.configure.html", "development", "Configure Phase"),
        ("chunked/development.build.html", "development", "Build Phase"),
        ("chunked/development.destroot.html", "development", "Destroot Phase"),
        ("chunked/development.install.html", "development", "Install Phase"),
        ("chunked/development.binary-data.html", "development", "Binary Data in Portfiles"),
        ("chunked/development.generated-files.html", "development", "Generated Files"),
        ("chunked/project.html", "project", "Project Guidelines"),
        ("chunked/project.docs.html", "project", "Updating Documentation"),
        ("chunked/project.contributing.html", "project", "Contributing to MacPorts"),
        ("chunked/project.tickets.html", "project", "Ticket Guidelines"),
        ("chunked/project.submissions.html", "project", "Port Submissions"),
        ("chunked/project.commit-messages.html", "project", "Commit Messages"),
        ("chunked/project.xcode.html", "project", "XCode Project"),
    ]

    def __init__(self, config: ScraperConfig):
        super().__init__(config)

    def get_source_name(self) -> str:
        return 'macports-guide'

    def scrape(self) -> List[ScrapedDocument]:
        """Scrape MacPorts Guide chapters."""
        documents = []

        logger.info(f"Scraping {len(self.CHAPTERS)} MacPorts Guide chapters...")

        for path, category, title in self.CHAPTERS:
            # Skip anchor-only paths
            if path.startswith('#'):
                continue

            url = f"{self.GUIDE_BASE}/{path}"

            try:
                html = self.fetch_url(url)
                if html is None:
                    logger.warning(f"Failed to fetch: {path}")
                    continue

                content = self._extract_content(html)

                if content and len(content) > 200:
                    doc_id = f"macports-guide-{hashlib.md5(path.encode()).hexdigest()[:12]}"

                    documents.append(ScrapedDocument(
                        id=doc_id,
                        url=url,
                        title=title,
                        content=content,
                        source="macports-guide",
                        category=category,
                        tags=["macports", "macos", "package-manager", "guide", category],
                        scraped_at=datetime.utcnow().isoformat(),
                        metadata={
                            "platform": "macos",
                            "doc_type": "guide_chapter",
                            "chapter": path,
                            "license": "BSD-like (MacPorts)",
                        }
                    ))
                    logger.info(f"Scraped: {title} ({len(content)} chars)")
                else:
                    logger.warning(f"Insufficient content for {path}")

            except Exception as e:
                logger.warning(f"Failed to scrape {path}: {e}")

        logger.info(f"Total MacPorts Guide documents: {len(documents)}")
        return documents

    def _extract_content(self, html: str) -> str:
        """Extract main content from MacPorts Guide page."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # MacPorts guide uses DocBook rendered to HTML
            # Content is usually in <div class="chapter"> or <div class="section">
            # or just in the main body
            main = (
                soup.find('div', class_='chapter')
                or soup.find('div', class_='section')
                or soup.find('div', class_='book')
                or soup.find('main')
                or soup.find('body')
            )

            if main:
                # Remove navigation, scripts, styles
                for tag in main.find_all(['script', 'style', 'nav', 'header', 'footer']):
                    tag.decompose()

                # Remove TOC
                for tag in main.find_all('div', class_=re.compile(r'toc|navheader|navfooter', re.I)):
                    tag.decompose()

                text = main.get_text(separator='\n', strip=True)
                text = re.sub(r'\n{3,}', '\n\n', text)

                return text.strip()

            return ""
        except Exception as e:
            logger.debug(f"Failed to extract content: {e}")
            return ""


def main():
    """CLI entry point for MacPorts Guide scraper."""
    import argparse

    parser = argparse.ArgumentParser(description="Scrape MacPorts Guide")
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--rate-limit', type=float, default=2.0)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    config = ScraperConfig(
        output_dir=args.output_dir,
        rate_limit_delay=args.rate_limit,
    )

    scraper = MacPortsGuideScraper(config)
    documents = scraper.scrape()

    output_file = args.output_dir / "macports_guide.jsonl"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        for doc in documents:
            f.write(json.dumps(doc.to_dict()) + '\n')

    print(f"Saved {len(documents)} documents to {output_file}")


if __name__ == '__main__':
    main()
