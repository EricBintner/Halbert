"""
Base scraper with rate limiting and error handling.
"""

import logging
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import json
from abc import ABC, abstractmethod
import hashlib

logger = logging.getLogger('cerebric')


@dataclass
class ScraperConfig:
    """Configuration for web scraper."""
    output_dir: Path
    rate_limit_delay: float = 1.0  # Seconds between requests
    max_retries: int = 3
    timeout: int = 30
    user_agent: str = "Cerebric/1.0 (Educational Purpose)"
    respect_robots_txt: bool = True


@dataclass
class ScrapedDocument:
    """Scraped document with metadata."""
    id: str
    url: str
    title: str
    content: str
    source: str  # 'arch_wiki', 'stackoverflow', etc.
    category: str  # 'system_admin', 'networking', etc.
    tags: List[str] = field(default_factory=list)
    scraped_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'url': self.url,
            'title': self.title,
            'content': self.content,
            'source': self.source,
            'category': self.category,
            'tags': self.tags,
            'scraped_at': self.scraped_at,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScrapedDocument':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            url=data['url'],
            title=data['title'],
            content=data['content'],
            source=data['source'],
            category=data.get('category', 'general'),
            tags=data.get('tags', []),
            scraped_at=data.get('scraped_at', ''),
            metadata=data.get('metadata', {})
        )


class BaseScraper(ABC):
    """
    Base class for web scrapers.
    
    Implements rate limiting, retries, and output management.
    """
    
    def __init__(self, config: ScraperConfig):
        """
        Initialize scraper.
        
        Args:
            config: Scraper configuration
        """
        self.config = config
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self._last_request_time = 0
        self._documents: List[ScrapedDocument] = []
        
        logger.info(f"Initialized {self.__class__.__name__} with output_dir={config.output_dir}")
    
    @abstractmethod
    def scrape(self) -> List[ScrapedDocument]:
        """
        Scrape documents from source.
        
        Returns:
            List of scraped documents
        """
        pass
    
    @abstractmethod
    def get_source_name(self) -> str:
        """Get source name (e.g., 'arch_wiki')."""
        pass
    
    def rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.config.rate_limit_delay:
            sleep_time = self.config.rate_limit_delay - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.time()
    
    def fetch_url(self, url: str, retries: int = 0) -> Optional[str]:
        """
        Fetch URL with retries and error handling.
        
        Args:
            url: URL to fetch
            retries: Current retry count
            
        Returns:
            HTML content or None on failure
        """
        try:
            import requests
            
            self.rate_limit()
            
            headers = {'User-Agent': self.config.user_agent}
            response = requests.get(
                url,
                headers=headers,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            
            logger.debug(f"Fetched {url} ({len(response.text)} bytes)")
            return response.text
            
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            
            if retries < self.config.max_retries:
                wait_time = 2 ** retries  # Exponential backoff
                logger.info(f"Retrying in {wait_time}s (attempt {retries + 1}/{self.config.max_retries})")
                time.sleep(wait_time)
                return self.fetch_url(url, retries + 1)
            
            logger.error(f"Failed to fetch {url} after {self.config.max_retries} retries")
            return None
    
    def generate_doc_id(self, url: str) -> str:
        """
        Generate unique document ID from URL.
        
        Args:
            url: Document URL
            
        Returns:
            MD5 hash of URL
        """
        return hashlib.md5(url.encode()).hexdigest()
    
    def save_documents(self, documents: List[ScrapedDocument], filename: str = None):
        """
        Save documents to JSONL file.
        
        Args:
            documents: List of documents to save
            filename: Output filename (default: source_name.jsonl)
        """
        if not documents:
            logger.warning("No documents to save")
            return
        
        if filename is None:
            filename = f"{self.get_source_name()}.jsonl"
        
        output_path = self.config.output_dir / filename
        
        logger.info(f"Saving {len(documents)} documents to {output_path}")
        
        with open(output_path, 'w') as f:
            for doc in documents:
                f.write(json.dumps(doc.to_dict()) + '\n')
        
        logger.info(f"Saved {len(documents)} documents to {output_path}")
    
    def load_documents(self, filename: str = None) -> List[ScrapedDocument]:
        """
        Load documents from JSONL file.
        
        Args:
            filename: Input filename (default: source_name.jsonl)
            
        Returns:
            List of loaded documents
        """
        if filename is None:
            filename = f"{self.get_source_name()}.jsonl"
        
        input_path = self.config.output_dir / filename
        
        if not input_path.exists():
            logger.warning(f"File not found: {input_path}")
            return []
        
        documents = []
        with open(input_path, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    documents.append(ScrapedDocument.from_dict(data))
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse line: {e}")
        
        logger.info(f"Loaded {len(documents)} documents from {input_path}")
        return documents
    
    def clean_text(self, text: str) -> str:
        """
        Clean and normalize text.
        
        Args:
            text: Input text
            
        Returns:
            Cleaned text
        """
        # Remove excessive whitespace
        lines = [line.strip() for line in text.split('\n')]
        lines = [line for line in lines if line]
        text = '\n'.join(lines)
        
        # Remove multiple blank lines
        while '\n\n\n' in text:
            text = text.replace('\n\n\n', '\n\n')
        
        return text.strip()
    
    def validate_document(self, doc: ScrapedDocument) -> bool:
        """
        Validate scraped document.
        
        Args:
            doc: Document to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not doc.id:
            logger.warning("Document missing ID")
            return False
        
        if not doc.url:
            logger.warning(f"Document {doc.id} missing URL")
            return False
        
        if not doc.title:
            logger.warning(f"Document {doc.id} missing title")
            return False
        
        if not doc.content or len(doc.content) < 100:
            logger.warning(f"Document {doc.id} has insufficient content ({len(doc.content)} chars)")
            return False
        
        return True
    
    def deduplicate_documents(self, documents: List[ScrapedDocument]) -> List[ScrapedDocument]:
        """
        Remove duplicate documents based on URL.
        
        Args:
            documents: List of documents
            
        Returns:
            Deduplicated list
        """
        seen_urls = set()
        unique_docs = []
        
        for doc in documents:
            if doc.url not in seen_urls:
                seen_urls.add(doc.url)
                unique_docs.append(doc)
            else:
                logger.debug(f"Skipping duplicate: {doc.url}")
        
        if len(unique_docs) < len(documents):
            logger.info(f"Removed {len(documents) - len(unique_docs)} duplicates")
        
        return unique_docs
