"""
Stack Overflow scraper using the Stack Exchange API.

Scrapes Q&A content related to Linux system administration.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import time

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('cerebric')


class StackOverflowScraper(BaseScraper):
    """
    Scraper for Stack Overflow using official API.
    
    Focuses on Linux and system administration questions.
    """
    
    API_BASE = 'https://api.stackexchange.com/2.3'
    
    # Tags of interest for system administration
    TARGET_TAGS = [
        'linux',
        'systemd',
        'bash',
        'shell',
        'ssh',
        'networking',
        'firewall',
        'sudo',
        'cron',
        'systemctl',
        'permissions',
        'disk-space',
        'filesystem',
        'kernel',
    ]
    
    def __init__(self, config: ScraperConfig, api_key: Optional[str] = None):
        """
        Initialize Stack Overflow scraper.
        
        Args:
            config: Scraper configuration
            api_key: Stack Exchange API key (optional, for higher rate limits)
        """
        super().__init__(config)
        self.api_key = api_key
        
        if not api_key:
            logger.warning(
                "No Stack Exchange API key provided. "
                "Rate limits will be lower. Get a key at: "
                "https://stackapps.com/apps/oauth/register"
            )
    
    def get_source_name(self) -> str:
        """Get source name."""
        return 'stackoverflow'
    
    def scrape(self, max_questions: int = 100, min_score: int = 5) -> List[ScrapedDocument]:
        """
        Scrape Stack Overflow questions.
        
        Args:
            max_questions: Maximum questions to scrape
            min_score: Minimum question score (upvotes)
            
        Returns:
            List of scraped documents
        """
        logger.info(
            f"Starting Stack Overflow scrape "
            f"(max_questions={max_questions}, min_score={min_score})"
        )
        
        documents = []
        
        for tag in self.TARGET_TAGS:
            logger.info(f"Scraping tag: {tag}")
            
            questions = self.fetch_questions_by_tag(
                tag=tag,
                max_results=max_questions // len(self.TARGET_TAGS),
                min_score=min_score
            )
            
            for question in questions:
                doc = self.convert_question_to_document(question)
                if doc and self.validate_document(doc):
                    documents.append(doc)
                    logger.info(f"Scraped Q: {doc.title[:60]}...")
            
            # API rate limiting is critical
            time.sleep(2)  # Be extra conservative
        
        logger.info(f"Scraped {len(documents)} questions from Stack Overflow")
        
        # Deduplicate and save
        documents = self.deduplicate_documents(documents)
        self.save_documents(documents)
        
        return documents
    
    def fetch_questions_by_tag(
        self,
        tag: str,
        max_results: int = 10,
        min_score: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Fetch questions with specific tag.
        
        Args:
            tag: Tag to search for
            min_score: Minimum question score
            max_results: Maximum number of results
            
        Returns:
            List of question objects from API
        """
        import requests
        
        params = {
            'site': 'stackoverflow',
            'tagged': tag,
            'sort': 'votes',
            'order': 'desc',
            'pagesize': min(max_results, 100),  # API max is 100
            'min': min_score,
            'filter': 'withbody',  # Include question body
        }
        
        if self.api_key:
            params['key'] = self.api_key
        
        url = f"{self.API_BASE}/questions"
        
        try:
            self.rate_limit()
            
            response = requests.get(url, params=params, timeout=self.config.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            if 'items' not in data:
                logger.warning(f"No items in API response for tag: {tag}")
                return []
            
            questions = data['items']
            
            # Check rate limit
            if 'quota_remaining' in data:
                logger.debug(f"API quota remaining: {data['quota_remaining']}")
            
            logger.info(f"Fetched {len(questions)} questions for tag: {tag}")
            return questions
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch questions for tag '{tag}': {e}")
            return []
        except Exception as e:
            logger.error(f"Error processing API response: {e}")
            return []
    
    def convert_question_to_document(self, question: Dict[str, Any]) -> Optional[ScrapedDocument]:
        """
        Convert Stack Overflow question to ScrapedDocument.
        
        Args:
            question: Question object from API
            
        Returns:
            ScrapedDocument or None
        """
        try:
            question_id = question.get('question_id')
            title = question.get('title', 'Untitled')
            body = question.get('body', '')
            
            if not question_id or not body:
                logger.warning("Question missing ID or body")
                return None
            
            url = f"https://stackoverflow.com/questions/{question_id}"
            
            # Clean HTML from body
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(body, 'html.parser')
                body_text = soup.get_text(separator='\n', strip=True)
            except ImportError:
                # Fallback: basic HTML stripping
                import re
                body_text = re.sub('<[^<]+?>', '', body)
            
            # Get answer if available
            answer_count = question.get('answer_count', 0)
            is_answered = question.get('is_answered', False)
            accepted_answer_id = question.get('accepted_answer_id')
            
            # Build content
            content_parts = [
                f"# {title}",
                "",
                "## Question",
                body_text,
            ]
            
            # Note: Full answer content would require separate API call
            # For now, we just note if there's an accepted answer
            if is_answered and accepted_answer_id:
                content_parts.append(f"\n(Accepted answer available at: {url})")
            elif answer_count > 0:
                content_parts.append(f"\n({answer_count} answers available at: {url})")
            
            content = '\n'.join(content_parts)
            content = self.clean_text(content)
            
            # Extract tags
            tags = question.get('tags', [])
            
            # Determine category from tags
            category = self._determine_category(tags)
            
            # Create document
            doc = ScrapedDocument(
                id=self.generate_doc_id(url),
                url=url,
                title=title,
                content=content,
                source='stackoverflow',
                category=category,
                tags=tags,
                scraped_at=datetime.now().isoformat(),
                metadata={
                    'question_id': question_id,
                    'score': question.get('score', 0),
                    'view_count': question.get('view_count', 0),
                    'answer_count': answer_count,
                    'is_answered': is_answered,
                    'creation_date': question.get('creation_date'),
                    'last_activity_date': question.get('last_activity_date'),
                }
            )
            
            return doc
            
        except Exception as e:
            logger.error(f"Failed to convert question {question.get('question_id')}: {e}")
            return None
    
    def _determine_category(self, tags: List[str]) -> str:
        """Determine category from tags."""
        tag_set = set(t.lower() for t in tags)
        
        categories = {
            'system_admin': {'systemd', 'systemctl', 'init', 'service', 'daemon'},
            'networking': {'networking', 'network', 'ssh', 'firewall', 'iptables'},
            'file_system': {'filesystem', 'disk-space', 'partition', 'mount'},
            'security': {'security', 'sudo', 'permissions', 'encryption'},
            'shell': {'bash', 'shell', 'scripting'},
        }
        
        for category, keywords in categories.items():
            if tag_set & keywords:
                return category
        
        if 'linux' in tag_set:
            return 'linux_general'
        
        return 'general'


def scrape_stackoverflow_cli():
    """CLI entry point for Stack Overflow scraping."""
    import argparse
    from pathlib import Path
    
    parser = argparse.ArgumentParser(
        description='Scrape Stack Overflow Q&A'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('data/linux/stackoverflow'),
        help='Output directory'
    )
    parser.add_argument(
        '--max-questions',
        type=int,
        default=100,
        help='Maximum questions to scrape'
    )
    parser.add_argument(
        '--min-score',
        type=int,
        default=5,
        help='Minimum question score'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        help='Stack Exchange API key (optional)'
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
        rate_limit_delay=2.0  # Stack Exchange rate limits are strict
    )
    
    scraper = StackOverflowScraper(config, api_key=args.api_key)
    
    # Scrape
    documents = scraper.scrape(
        max_questions=args.max_questions,
        min_score=args.min_score
    )
    
    logger.info(f"Scraped {len(documents)} documents")
    logger.info(f"Output: {args.output_dir / 'stackoverflow.jsonl'}")


if __name__ == '__main__':
    scrape_stackoverflow_cli()
