# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Linux man pages extractor.

Extracts ALL man pages from Linux system for RAG indexing.
This is ESSENTIAL for accurate command suggestions.
"""

import logging
import subprocess
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import re
import json

from .base import ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class LinuxManPageExtractor:
    """
    Extract ALL man pages from Linux system.
    
    This provides the foundation for accurate command syntax suggestions.
    Without man pages, the AI hallucinates command options.
    """
    
    # Section descriptions for categorization
    SECTION_DESCRIPTIONS = {
        '1': 'user_commands',
        '2': 'system_calls',
        '3': 'library_functions',
        '4': 'special_files',
        '5': 'file_formats',
        '6': 'games',
        '7': 'miscellaneous',
        '8': 'system_admin',
        '9': 'kernel_routines',
    }
    
    def __init__(self, output_dir: Path):
        """
        Initialize extractor.
        
        Args:
            output_dir: Output directory for extracted pages
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized LinuxManPageExtractor with output_dir={output_dir}")
    
    def check_platform(self) -> bool:
        """Check if running on Linux."""
        import platform
        is_linux = platform.system() == 'Linux'
        
        if not is_linux:
            logger.error("This extractor must be run on Linux")
        
        return is_linux
    
    def get_man_pages_list(self) -> List[tuple]:
        """
        Get list of ALL available man pages.
        
        Returns:
            List of (name, section) tuples
        """
        if not self.check_platform():
            return []
        
        logger.info("Getting list of ALL man pages...")
        
        try:
            # Use man -k . to get all man pages (apropos with wildcard)
            result = subprocess.run(
                ['man', '-k', '.'],
                capture_output=True,
                text=True,
                timeout=60  # May take a while for all pages
            )
            
            if result.returncode != 0:
                logger.error(f"man -k command failed: {result.stderr}")
                return []
            
            # Parse output: "name (section) - description"
            # or "name(section) - description"
            pages = []
            seen = set()
            
            for line in result.stdout.split('\n'):
                if not line.strip():
                    continue
                
                # Match "name (section)" or "name(section)"
                match = re.match(r'([a-zA-Z0-9_\-\.]+)\s*\(([0-9]+[a-zA-Z]*)\)', line)
                if match:
                    name = match.group(1)
                    section = match.group(2)
                    key = f"{name}:{section}"
                    
                    if key not in seen:
                        seen.add(key)
                        pages.append((name, section))
            
            logger.info(f"Found {len(pages)} unique man pages")
            return pages
            
        except subprocess.TimeoutExpired:
            logger.error("man -k command timed out")
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
            # Get formatted man page content (plain text, no formatting codes)
            result = subprocess.run(
                ['man', '--no-justification', section, name],
                capture_output=True,
                text=True,
                timeout=10,
                env={
                    'MANWIDTH': '100',  # Wider for better readability
                    'LANG': 'C',  # Consistent formatting
                    'LC_ALL': 'C',
                }
            )
            
            if result.returncode != 0:
                logger.debug(f"Failed to get man page: {name}({section})")
                return None
            
            content = result.stdout
            
            # Clean up escape sequences that might remain
            content = re.sub(r'\x1b\[[0-9;]*m', '', content)  # ANSI codes
            content = re.sub(r'.\x08', '', content)  # Backspace overstrikes
            
            if not content or len(content) < 50:
                logger.debug(f"Man page too short: {name}({section})")
                return None
            
            # Extract description from NAME section
            description = self._extract_description(content)
            
            # Determine category based on section
            category = self.SECTION_DESCRIPTIONS.get(section[0], 'other')
            
            # Create document
            doc = ScrapedDocument(
                id=f"linux_man_{name}_{section}",
                url=f"man://{section}/{name}",
                title=f"{name}({section}) - {description[:100]}" if description else f"{name}({section})",
                content=content,
                source='linux_man',
                category=category,
                scraped_at=datetime.utcnow(),
                metadata={
                    'section': section,
                    'section_name': self.SECTION_DESCRIPTIONS.get(section[0], 'other'),
                    'command': name,
                }
            )
            
            return doc
            
        except subprocess.TimeoutExpired:
            logger.debug(f"Timeout extracting: {name}({section})")
            return None
        except Exception as e:
            logger.debug(f"Error extracting {name}({section}): {e}")
            return None
    
    def _extract_description(self, content: str) -> str:
        """Extract description from NAME section."""
        lines = content.split('\n')
        in_name_section = False
        
        for line in lines[:30]:  # Check first 30 lines
            if 'NAME' in line and line.strip() == 'NAME':
                in_name_section = True
                continue
            
            if in_name_section:
                if line.strip() and not line.startswith(' ' * 7):
                    # Next section started
                    break
                if ' - ' in line or ' — ' in line:
                    # Found description line
                    desc = line.split(' - ', 1)[-1].split(' — ', 1)[-1].strip()
                    return desc
        
        return ""
    
    def extract_all(self, max_pages: int = None, progress_callback=None) -> List[ScrapedDocument]:
        """
        Extract ALL man pages from the system.
        
        Args:
            max_pages: Optional limit (None = all pages)
            progress_callback: Optional callback(current, total) for progress
            
        Returns:
            List of ScrapedDocument objects
        """
        pages = self.get_man_pages_list()
        
        if not pages:
            logger.error("No man pages found!")
            return []
        
        if max_pages:
            pages = pages[:max_pages]
        
        total = len(pages)
        logger.info(f"Extracting {total} man pages...")
        
        documents = []
        errors = 0
        
        for i, (name, section) in enumerate(pages):
            doc = self.extract_man_page(name, section)
            
            if doc:
                documents.append(doc)
            else:
                errors += 1
            
            if progress_callback and i % 100 == 0:
                progress_callback(i, total)
            
            if i % 500 == 0 and i > 0:
                logger.info(f"Progress: {i}/{total} pages extracted ({len(documents)} successful)")
        
        logger.info(f"Extracted {len(documents)} man pages ({errors} errors)")
        
        return documents
    
    def save_documents(self, documents: List[ScrapedDocument], filename: str = "linux_man_pages.jsonl"):
        """Save documents to JSONL file."""
        output_path = self.output_dir / filename
        
        with open(output_path, 'w') as f:
            for doc in documents:
                f.write(json.dumps({
                    'id': doc.id,
                    'url': doc.url,
                    'title': doc.title,
                    'content': doc.content,
                    'source': doc.source,
                    'category': doc.category,
                    'scraped_at': doc.scraped_at.isoformat() if doc.scraped_at else None,
                    'metadata': doc.metadata,
                }) + '\n')
        
        logger.info(f"Saved {len(documents)} documents to {output_path}")
        return output_path


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract Linux man pages for RAG')
    parser.add_argument('--output-dir', default='data/linux/man-pages', help='Output directory')
    parser.add_argument('--max-pages', type=int, default=None, help='Max pages to extract (default: all)')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    extractor = LinuxManPageExtractor(args.output_dir)
    documents = extractor.extract_all(max_pages=args.max_pages)
    
    if documents:
        extractor.save_documents(documents)
        print(f"\nExtracted {len(documents)} man pages to {args.output_dir}")
    else:
        print("No documents extracted!")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
