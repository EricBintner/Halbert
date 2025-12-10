"""
macOS man pages extractor.

Extracts man pages from macOS system for RAG indexing.
NOTE: Must be run on a macOS system.
"""

import logging
import subprocess
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import re

from .base import ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class MacOSManPageExtractor:
    """
    Extract man pages from macOS system.
    
    NOTE: This must be run on a macOS machine.
    """
    
    def __init__(self, output_dir: Path):
        """
        Initialize extractor.
        
        Args:
            output_dir: Output directory for extracted pages
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized MacOSManPageExtractor with output_dir={output_dir}")
    
    def check_platform(self) -> bool:
        """Check if running on macOS."""
        import platform
        is_macos = platform.system() == 'Darwin'
        
        if not is_macos:
            logger.error("This extractor must be run on macOS (Darwin)")
        
        return is_macos
    
    def get_man_pages_list(self) -> List[tuple]:
        """
        Get list of available man pages.
        
        Returns:
            List of (name, section) tuples
        """
        if not self.check_platform():
            return []
        
        logger.info("Getting list of man pages...")
        
        try:
            # Use apropos to get all man pages
            result = subprocess.run(
                ['apropos', '.'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"apropos command failed: {result.stderr}")
                return []
            
            # Parse output: "name(section) - description"
            pages = []
            for line in result.stdout.split('\n'):
                if not line.strip():
                    continue
                
                # Match "name(section)"
                match = re.match(r'([a-zA-Z0-9_\-\.]+)\(([0-9]+[a-z]*)\)', line)
                if match:
                    name = match.group(1)
                    section = match.group(2)
                    pages.append((name, section))
            
            logger.info(f"Found {len(pages)} man pages")
            return pages
            
        except subprocess.TimeoutExpired:
            logger.error("apropos command timed out")
            return []
        except Exception as e:
            logger.error(f"Failed to get man pages list: {e}")
            return []
    
    def extract_man_page(self, name: str, section: str) -> Optional[ScrapedDocument]:
        """
        Extract a single man page.
        
        Args:
            name: Page name
            section: Page section
            
        Returns:
            ScrapedDocument or None on failure
        """
        try:
            # Get formatted man page content
            result = subprocess.run(
                ['man', section, name],
                capture_output=True,
                text=True,
                timeout=10,
                env={'MANWIDTH': '80'}  # Set width for consistent formatting
            )
            
            if result.returncode != 0:
                logger.debug(f"Failed to get man page: {name}({section})")
                return None
            
            content = result.stdout
            
            if not content or len(content) < 100:
                logger.debug(f"Man page too short: {name}({section})")
                return None
            
            # Extract description from first line
            lines = content.split('\n')
            description = ""
            for line in lines[:20]:  # Check first 20 lines
                if 'NAME' in line or 'SYNOPSIS' in line:
                    continue
                if line.strip() and not line.startswith(' ') * 4:
                    description = line.strip()
                    if '-' in description:
                        description = description.split('-', 1)[-1].strip()
                        break
            
            # Determine category
            category = self._determine_category(name, section, content)
            
            # Create document
            doc = ScrapedDocument(
                id=f"macos_{name}_{section}",
                url=f"x-man-page://{section}/{name}",
                title=f"{name}({section})",
                content=content,
                source='macos_man',
                category=category,
                tags=[f"section{section}", "macos", "man_page"],
                scraped_at=datetime.now().isoformat(),
                metadata={
                    'name': name,
                    'section': section,
                    'description': description,
                    'platform': 'macos'
                }
            )
            
            return doc
            
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout extracting: {name}({section})")
            return None
        except Exception as e:
            logger.warning(f"Failed to extract {name}({section}): {e}")
            return None
    
    def _determine_category(self, name: str, section: str, content: str) -> str:
        """Determine category from man page."""
        # Section-based categorization
        section_categories = {
            '1': 'user_commands',
            '2': 'system_calls',
            '3': 'library_functions',
            '4': 'devices',
            '5': 'file_formats',
            '6': 'games',
            '7': 'misc',
            '8': 'system_admin',
            '9': 'kernel',
        }
        
        base_section = section.rstrip('abcdefghijklmnopqrstuvwxyz')
        category = section_categories.get(base_section, 'general')
        
        # Refine based on name and content
        name_lower = name.lower()
        content_lower = content.lower()[:500]
        
        if any(kw in name_lower for kw in ['launchd', 'launchctl', 'systemd']):
            category = 'system_admin'
        elif any(kw in name_lower for kw in ['network', 'ifconfig', 'route']):
            category = 'networking'
        elif any(kw in name_lower for kw in ['security', 'sudo', 'chmod']):
            category = 'security'
        
        return category
    
    def extract_all(self, max_pages: Optional[int] = None) -> List[ScrapedDocument]:
        """
        Extract all man pages.
        
        Args:
            max_pages: Maximum pages to extract (optional)
            
        Returns:
            List of extracted documents
        """
        if not self.check_platform():
            logger.error("Cannot extract man pages: not running on macOS")
            return []
        
        logger.info("Starting macOS man pages extraction")
        
        # Get list of pages
        pages = self.get_man_pages_list()
        
        if not pages:
            logger.error("No man pages found")
            return []
        
        if max_pages:
            pages = pages[:max_pages]
            logger.info(f"Limiting to {max_pages} pages")
        
        # Extract each page
        documents = []
        total = len(pages)
        
        for i, (name, section) in enumerate(pages, 1):
            if i % 50 == 0:
                logger.info(f"Progress: {i}/{total} ({i*100//total}%)")
            
            doc = self.extract_man_page(name, section)
            if doc:
                documents.append(doc)
        
        logger.info(f"Extracted {len(documents)} man pages from {total} candidates")
        
        # Save to JSONL
        self._save_documents(documents)
        
        return documents
    
    def _save_documents(self, documents: List[ScrapedDocument]):
        """Save documents to JSONL."""
        import json
        
        if not documents:
            logger.warning("No documents to save")
            return
        
        output_path = self.output_dir / 'macos_man_pages.jsonl'
        
        logger.info(f"Saving {len(documents)} documents to {output_path}")
        
        with open(output_path, 'w') as f:
            for doc in documents:
                f.write(json.dumps(doc.to_dict()) + '\n')
        
        logger.info(f"Saved to {output_path}")


def extract_macos_man_pages_cli():
    """CLI entry point for macOS man page extraction."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Extract man pages from macOS'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('data/mac/man-pages'),
        help='Output directory'
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        help='Maximum pages to extract (optional)'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create extractor
    extractor = MacOSManPageExtractor(args.output_dir)
    
    # Extract
    documents = extractor.extract_all(max_pages=args.max_pages)
    
    logger.info(f"Extracted {len(documents)} documents")
    logger.info(f"Output: {args.output_dir / 'macos_man_pages.jsonl'}")


if __name__ == '__main__':
    extract_macos_man_pages_cli()
