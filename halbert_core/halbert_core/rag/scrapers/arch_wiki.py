# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Arch Wiki scraper for Linux documentation.

Scrapes high-quality system administration content from Arch Wiki.
"""

import logging
from typing import List, Optional
from datetime import datetime
import re

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class ArchWikiScraper(BaseScraper):
    """
    Scraper for Arch Wiki documentation.
    
    Focuses on system administration, configuration, and troubleshooting pages.
    """
    
    # Categories of interest for system administration
    TARGET_CATEGORIES = [
        'System_administration',
        'System_maintenance',
        'Boot_process',
        'File_systems',
        'Networking',
        'Security',
        'Package_management',
        'Kernel',
        'Hardware',
    ]
    
    # High-value individual pages
    PRIORITY_PAGES = [
        'Systemd',
        'Systemd/Timers',
        'Systemd/User',
        'Journalctl',
        'Cron',
        'Sudo',
        'Users_and_groups',
        'File_permissions_and_attributes',
        'Network_configuration',
        'Firewall',
        'OpenSSH',
        'Pacman',
        'makepkg',
        'Disk_encryption',
        'LVM',
        'RAID',
        'Syslinux',
        'GRUB',
        'Kernel_parameters',
    ]
    
    BASE_URL = 'https://wiki.archlinux.org'
    
    def get_source_name(self) -> str:
        """Get source name."""
        return 'arch_wiki'
    
    def scrape(self, max_pages: int = 100) -> List[ScrapedDocument]:
        """
        Scrape Arch Wiki pages.
        
        Args:
            max_pages: Maximum number of pages to scrape
            
        Returns:
            List of scraped documents
        """
        logger.info(f"Starting Arch Wiki scrape (max_pages={max_pages})")
        
        documents = []
        
        # Scrape priority pages first
        for page_title in self.PRIORITY_PAGES[:max_pages]:
            doc = self.scrape_page(page_title)
            if doc and self.validate_document(doc):
                documents.append(doc)
                logger.info(f"Scraped: {doc.title} ({len(doc.content)} chars)")
            
            if len(documents) >= max_pages:
                break
        
        logger.info(f"Scraped {len(documents)} pages from Arch Wiki")
        
        # Deduplicate and save
        documents = self.deduplicate_documents(documents)
        self.save_documents(documents)
        
        return documents
    
    def scrape_page(self, page_title: str) -> Optional[ScrapedDocument]:
        """
        Scrape a single Arch Wiki page.
        
        Args:
            page_title: Page title (e.g., 'Systemd')
            
        Returns:
            ScrapedDocument or None on failure
        """
        url = f"{self.BASE_URL}/title/{page_title.replace(' ', '_')}"
        
        html = self.fetch_url(url)
        if not html:
            return None
        
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract title
            title_elem = soup.find('h1', {'id': 'firstHeading'})
            title = title_elem.text.strip() if title_elem else page_title
            
            # Extract main content
            content_elem = soup.find('div', {'id': 'mw-content-text'})
            if not content_elem:
                logger.warning(f"No content found for {page_title}")
                return None
            
            # Remove unwanted elements
            for elem in content_elem.find_all(['script', 'style', 'noscript']):
                elem.decompose()
            
            # Extract text
            content = content_elem.get_text(separator='\n', strip=True)
            content = self.clean_text(content)
            
            # Extract categories/tags
            tags = self._extract_tags(soup)
            
            # Determine category
            category = self._determine_category(title, content, tags)
            
            # Create document
            doc = ScrapedDocument(
                id=self.generate_doc_id(url),
                url=url,
                title=title,
                content=content,
                source='arch_wiki',
                category=category,
                tags=tags,
                scraped_at=datetime.now().isoformat(),
                metadata={
                    'page_title': page_title,
                    'language': 'en'
                }
            )
            
            return doc
            
        except ImportError:
            logger.error("beautifulsoup4 not installed. Run: pip install beautifulsoup4")
            return None
        except Exception as e:
            logger.error(f"Failed to parse {page_title}: {e}")
            return None
    
    def _extract_tags(self, soup) -> List[str]:
        """Extract tags/categories from page."""
        tags = []
        
        # Look for category links
        cat_box = soup.find('div', {'id': 'catlinks'})
        if cat_box:
            for link in cat_box.find_all('a'):
                text = link.text.strip()
                if text and text not in ['Categories', 'Category']:
                    tags.append(text.lower().replace(' ', '_'))
        
        return tags[:10]  # Limit to 10 tags
    
    def _determine_category(self, title: str, content: str, tags: List[str]) -> str:
        """Determine document category based on content."""
        title_lower = title.lower()
        content_lower = content.lower()
        
        # Category keywords
        categories = {
            'system_admin': ['systemd', 'service', 'daemon', 'init', 'boot'],
            'networking': ['network', 'interface', 'ip', 'firewall', 'ssh', 'vpn'],
            'file_system': ['file system', 'mount', 'disk', 'partition', 'lvm', 'raid'],
            'security': ['security', 'encryption', 'sudo', 'permission', 'firewall'],
            'package_mgmt': ['pacman', 'package', 'makepkg', 'repository'],
            'kernel': ['kernel', 'module', 'driver'],
            'hardware': ['hardware', 'device', 'driver', 'usb', 'pci'],
            'shell': ['bash', 'shell', 'script', 'command line'],
        }
        
        # Check title and tags first (more reliable)
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in title_lower or any(keyword in tag for tag in tags):
                    return category
        
        # Check content (less reliable, more broad)
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in content_lower[:1000]:  # Check first 1000 chars
                    return category
        
        return 'general'
    
    def get_category_pages(self, category: str) -> List[str]:
        """
        Get list of pages in a category using MediaWiki API.
        
        Args:
            category: Category name (e.g., 'System_administration')
            
        Returns:
            List of page titles
        """
        pages = []
        api_url = f"{self.BASE_URL}/api.php"
        
        params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': f'Category:{category}',
            'cmlimit': '500',
            'cmtype': 'page',
            'format': 'json',
        }
        
        try:
            import time
            import requests
            
            while True:
                response = requests.get(api_url, params=params, timeout=30, headers={'User-Agent': self.config.user_agent})
                data = response.json()
                
                for member in data.get('query', {}).get('categorymembers', []):
                    pages.append(member['title'])
                
                # Check for continuation
                if 'continue' in data:
                    params['cmcontinue'] = data['continue']['cmcontinue']
                    time.sleep(0.5)  # Rate limit
                else:
                    break
            
            logger.info(f"Found {len(pages)} pages in category {category}")
            
        except Exception as e:
            logger.error(f"Failed to get category pages for {category}: {e}")
        
        return pages
    
    def get_all_pages(self, namespace: int = 0) -> List[str]:
        """
        Get ALL pages from Arch Wiki using MediaWiki API.
        
        Args:
            namespace: Namespace (0 = main content pages)
            
        Returns:
            List of all page titles
        """
        pages = []
        api_url = f"{self.BASE_URL}/api.php"
        
        params = {
            'action': 'query',
            'list': 'allpages',
            'apnamespace': str(namespace),
            'aplimit': '500',
            'format': 'json',
        }
        
        logger.info("Fetching ALL Arch Wiki pages (this may take a while)...")
        
        try:
            import time
            import requests
            
            while True:
                response = requests.get(api_url, params=params, timeout=30, headers={'User-Agent': self.config.user_agent})
                data = response.json()
                
                for page in data.get('query', {}).get('allpages', []):
                    title = page['title']
                    # Skip talk pages, user pages, etc.
                    if not any(title.startswith(prefix) for prefix in ['Talk:', 'User:', 'Template:', 'Category:', 'Help:']):
                        pages.append(title)
                
                # Check for continuation
                if 'continue' in data:
                    params['apcontinue'] = data['continue']['apcontinue']
                    time.sleep(0.3)  # Rate limit
                    
                    if len(pages) % 1000 == 0:
                        logger.info(f"Progress: {len(pages)} pages found...")
                else:
                    break
            
            logger.info(f"Found {len(pages)} total content pages")
            
        except Exception as e:
            logger.error(f"Failed to get all pages: {e}")
        
        return pages
    
    def scrape_all(self, max_pages: int = None, rate_limit: float = 0.5) -> List[ScrapedDocument]:
        """
        Scrape ALL Arch Wiki pages.
        
        Args:
            max_pages: Optional limit (None = all pages)
            rate_limit: Seconds between requests
            
        Returns:
            List of scraped documents
        """
        import time
        
        # Get all page titles
        all_pages = self.get_all_pages()
        
        if max_pages:
            all_pages = all_pages[:max_pages]
        
        total = len(all_pages)
        logger.info(f"Scraping {total} Arch Wiki pages...")
        
        documents = []
        errors = 0
        
        for i, page_title in enumerate(all_pages):
            doc = self.scrape_page(page_title)
            
            if doc and self.validate_document(doc):
                documents.append(doc)
            else:
                errors += 1
            
            # Rate limiting
            time.sleep(rate_limit)
            
            # Progress logging
            if (i + 1) % 100 == 0:
                logger.info(f"Progress: {i + 1}/{total} pages ({len(documents)} successful, {errors} errors)")
        
        logger.info(f"Scraped {len(documents)} pages from Arch Wiki ({errors} errors)")
        
        # Deduplicate and save
        documents = self.deduplicate_documents(documents)
        self.save_documents(documents)
        
        return documents


def scrape_arch_wiki_cli():
    """CLI entry point for Arch Wiki scraping."""
    import argparse
    from pathlib import Path
    
    parser = argparse.ArgumentParser(
        description='Scrape Arch Wiki documentation'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('data/linux/arch_wiki'),
        help='Output directory'
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        default=None,
        help='Maximum pages to scrape (default: ALL pages)'
    )
    parser.add_argument(
        '--rate-limit',
        type=float,
        default=0.5,
        help='Seconds between requests'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Scrape ALL pages (recommended for full coverage)'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create scraper
    config = ScraperConfig(
        output_dir=args.output_dir,
        rate_limit_delay=args.rate_limit
    )
    
    scraper = ArchWikiScraper(config)
    
    # Scrape - use scrape_all for full coverage
    if args.all or args.max_pages is None:
        logger.info("Scraping ALL Arch Wiki pages (this will take a while)...")
        documents = scraper.scrape_all(max_pages=args.max_pages, rate_limit=args.rate_limit)
    else:
        documents = scraper.scrape(max_pages=args.max_pages)
    
    logger.info(f"Scraped {len(documents)} documents")
    logger.info(f"Output: {args.output_dir / 'arch_wiki.jsonl'}")


if __name__ == '__main__':
    scrape_arch_wiki_cli()
