"""
Arch Wiki scraper for Linux documentation.

Scrapes high-quality system administration content from Arch Wiki.
"""

import logging
from typing import List, Optional
from datetime import datetime
import re

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('cerebric')


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
        Get list of pages in a category (future enhancement).
        
        Args:
            category: Category name
            
        Returns:
            List of page titles
        """
        # This would use the Arch Wiki API to get all pages in a category
        # For now, we use the hardcoded PRIORITY_PAGES list
        logger.info(f"Category scraping not yet implemented: {category}")
        return []


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
        default=50,
        help='Maximum pages to scrape'
    )
    parser.add_argument(
        '--rate-limit',
        type=float,
        default=1.0,
        help='Seconds between requests'
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
    
    # Scrape
    documents = scraper.scrape(max_pages=args.max_pages)
    
    logger.info(f"Scraped {len(documents)} documents")
    logger.info(f"Output: {args.output_dir / 'arch_wiki.jsonl'}")


if __name__ == '__main__':
    scrape_arch_wiki_cli()
