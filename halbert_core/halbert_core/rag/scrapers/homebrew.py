# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Homebrew documentation scraper.

Scrapes Homebrew formula information and documentation.
Works on any platform (scrapes from web API).
"""

import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import hashlib

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class HomebrewScraper(BaseScraper):
    """
    Scrape Homebrew formula documentation.
    
    Sources:
    - formulae.brew.sh API (JSON)
    - Homebrew docs (brew.sh/docs)
    """
    
    # API endpoints
    FORMULA_API = "https://formulae.brew.sh/api/formula.json"
    CASK_API = "https://formulae.brew.sh/api/cask.json"
    DOCS_BASE = "https://docs.brew.sh"
    
    # Important doc pages to scrape
    DOCS_PAGES = [
        ("Installation", "/Installation"),
        ("FAQ", "/FAQ"),
        ("Tips-N'-Tricks", "/Tips-N'-Tricks"),
        ("Troubleshooting", "/Troubleshooting"),
        ("Common-Issues", "/Common-Issues"),
        ("Formula-Cookbook", "/Formula-Cookbook"),
        ("Cask-Cookbook", "/Cask-Cookbook"),
        ("How-To-Open-a-Pull-Request", "/How-To-Open-a-Homebrew-related-Pull-Request"),
        ("Acceptable-Formulae", "/Acceptable-Formulae"),
        ("Versions", "/Versions"),
        ("Manpage", "/Manpage"),
        ("Shell-Completion", "/Shell-Completion"),
        ("Analytics", "/Analytics"),
    ]
    
    def __init__(self, config: ScraperConfig, max_formulas: int = 500):
        """
        Initialize Homebrew scraper.
        
        Args:
            config: Scraper configuration
            max_formulas: Maximum number of formulas to scrape
        """
        super().__init__(config)
        self.max_formulas = max_formulas
    
    def get_source_name(self) -> str:
        """Get source name."""
        return "homebrew"
    
    def _rate_limit(self):
        """Rate limit wrapper."""
        self.rate_limit()
    
    def _make_request(self, url: str):
        """Make HTTP request with rate limiting."""
        import requests
        self.rate_limit()
        response = requests.get(url, timeout=self.config.timeout)
        response.raise_for_status()
        return response
    
    def scrape(self) -> List[ScrapedDocument]:
        """
        Scrape Homebrew documentation.
        
        Returns:
            List of scraped documents
        """
        documents = []
        
        # 1. Scrape main documentation pages
        logger.info("Scraping Homebrew documentation pages...")
        documents.extend(self._scrape_docs())
        
        # 2. Scrape formula metadata
        logger.info(f"Scraping top {self.max_formulas} Homebrew formulas...")
        documents.extend(self._scrape_formulas())
        
        # 3. Scrape popular casks
        logger.info("Scraping popular Homebrew casks...")
        documents.extend(self._scrape_casks())
        
        logger.info(f"Total Homebrew documents: {len(documents)}")
        return documents
    
    def _scrape_docs(self) -> List[ScrapedDocument]:
        """Scrape Homebrew documentation pages."""
        documents = []
        
        for title, path in self.DOCS_PAGES:
            url = f"{self.DOCS_BASE}{path}"
            
            try:
                response = self._make_request(url)
                if response is None:
                    continue
                
                # Parse markdown content from GitHub pages
                content = self._extract_doc_content(response.text, title)
                
                if content and len(content) > 200:
                    doc_id = f"homebrew-doc-{hashlib.md5(url.encode()).hexdigest()[:12]}"
                    
                    documents.append(ScrapedDocument(
                        id=doc_id,
                        url=url,
                        title=f"Homebrew: {title}",
                        content=content,
                        source="homebrew-docs",
                        category="package_management",
                        tags=["homebrew", "macos", "package-manager", title.lower()],
                        scraped_at=datetime.utcnow().isoformat(),
                        metadata={
                            "platform": "macos",
                            "doc_type": "official",
                        }
                    ))
                    logger.debug(f"Scraped doc: {title}")
                
                self._rate_limit()
                
            except Exception as e:
                logger.warning(f"Failed to scrape {url}: {e}")
        
        return documents
    
    def _scrape_formulas(self) -> List[ScrapedDocument]:
        """Scrape Homebrew formula information."""
        documents = []
        
        try:
            response = self._make_request(self.FORMULA_API)
            if response is None:
                return documents
            
            formulas = response.json()
            
            # Sort by analytics (most installed) if available
            # Take top N formulas
            formulas = formulas[:self.max_formulas]
            
            for formula in formulas:
                try:
                    doc = self._formula_to_document(formula)
                    if doc:
                        documents.append(doc)
                except Exception as e:
                    logger.debug(f"Failed to process formula: {e}")
            
            logger.info(f"Scraped {len(documents)} formulas")
            
        except Exception as e:
            logger.error(f"Failed to fetch formula list: {e}")
        
        return documents
    
    def _formula_to_document(self, formula: Dict[str, Any]) -> Optional[ScrapedDocument]:
        """Convert formula JSON to document."""
        name = formula.get('name', '')
        if not name:
            return None
        
        desc = formula.get('desc', '')
        homepage = formula.get('homepage', '')
        
        # Build content
        content_parts = [
            f"# {name}",
            f"\n{desc}\n" if desc else "",
            f"\n**Homepage**: {homepage}\n" if homepage else "",
        ]
        
        # Add installation info
        content_parts.append(f"\n## Installation\n```bash\nbrew install {name}\n```\n")
        
        # Add dependencies
        deps = formula.get('dependencies', [])
        if deps:
            content_parts.append(f"\n## Dependencies\n")
            for dep in deps[:10]:  # Limit to 10
                content_parts.append(f"- {dep}\n")
        
        # Add caveats
        caveats = formula.get('caveats', '')
        if caveats:
            content_parts.append(f"\n## Caveats\n{caveats}\n")
        
        # Add version info
        versions = formula.get('versions', {})
        if versions:
            stable = versions.get('stable', '')
            if stable:
                content_parts.append(f"\n## Version\nStable: {stable}\n")
        
        content = ''.join(content_parts)
        
        if len(content) < 100:
            return None
        
        doc_id = f"homebrew-formula-{name}"
        
        return ScrapedDocument(
            id=doc_id,
            url=f"https://formulae.brew.sh/formula/{name}",
            title=f"Homebrew Formula: {name}",
            content=content,
            source="homebrew-formulas",
            category="package_management",
            tags=["homebrew", "macos", "formula", name],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={
                "platform": "macos",
                "formula_name": name,
                "version": versions.get('stable', ''),
            }
        )
    
    def _scrape_casks(self) -> List[ScrapedDocument]:
        """Scrape popular Homebrew casks."""
        documents = []
        
        try:
            response = self._make_request(self.CASK_API)
            if response is None:
                return documents
            
            casks = response.json()
            
            # Take top 200 casks
            casks = casks[:200]
            
            for cask in casks:
                try:
                    doc = self._cask_to_document(cask)
                    if doc:
                        documents.append(doc)
                except Exception as e:
                    logger.debug(f"Failed to process cask: {e}")
            
            logger.info(f"Scraped {len(documents)} casks")
            
        except Exception as e:
            logger.error(f"Failed to fetch cask list: {e}")
        
        return documents
    
    def _cask_to_document(self, cask: Dict[str, Any]) -> Optional[ScrapedDocument]:
        """Convert cask JSON to document."""
        token = cask.get('token', '')
        if not token:
            return None
        
        name = cask.get('name', [token])[0] if cask.get('name') else token
        desc = cask.get('desc', '')
        homepage = cask.get('homepage', '')
        
        content_parts = [
            f"# {name}",
            f"\n{desc}\n" if desc else "",
            f"\n**Homepage**: {homepage}\n" if homepage else "",
            f"\n## Installation\n```bash\nbrew install --cask {token}\n```\n",
        ]
        
        # Add caveats
        caveats = cask.get('caveats', '')
        if caveats:
            content_parts.append(f"\n## Caveats\n{caveats}\n")
        
        content = ''.join(content_parts)
        
        if len(content) < 100:
            return None
        
        doc_id = f"homebrew-cask-{token}"
        
        return ScrapedDocument(
            id=doc_id,
            url=f"https://formulae.brew.sh/cask/{token}",
            title=f"Homebrew Cask: {name}",
            content=content,
            source="homebrew-casks",
            category="package_management",
            tags=["homebrew", "macos", "cask", token],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={
                "platform": "macos",
                "cask_token": token,
            }
        )
    
    def _extract_doc_content(self, html: str, title: str) -> str:
        """Extract content from Homebrew docs HTML."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find main content
            main = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
            
            if main:
                # Remove script/style tags
                for tag in main.find_all(['script', 'style', 'nav']):
                    tag.decompose()
                
                return main.get_text(separator='\n', strip=True)
            
            return ""
        except Exception as e:
            logger.debug(f"Failed to extract content: {e}")
            return ""


def main():
    """CLI entry point for Homebrew scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape Homebrew documentation")
    parser.add_argument('--output-dir', type=Path, required=True, help="Output directory")
    parser.add_argument('--max-formulas', type=int, default=500, help="Max formulas to scrape")
    parser.add_argument('--rate-limit', type=float, default=0.5, help="Seconds between requests")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    config = ScraperConfig(
        output_dir=args.output_dir,
        rate_limit_delay=args.rate_limit,
    )
    
    scraper = HomebrewScraper(config, max_formulas=args.max_formulas)
    documents = scraper.scrape()
    
    # Save to JSONL
    output_file = args.output_dir / "homebrew.jsonl"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        for doc in documents:
            f.write(json.dumps(doc.to_dict()) + '\n')
    
    print(f"Saved {len(documents)} documents to {output_file}")


if __name__ == '__main__':
    main()
