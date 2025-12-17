"""
Unix & Linux Stack Exchange Scraper.

Phase 27: RAG Coverage

Uses Stack Exchange API to scrape high-quality Q&A from unix.stackexchange.com.
This is the premier Q&A site for Unix/Linux system administration.
"""

import logging
from typing import List, Optional
from datetime import datetime
import time

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class UnixSEScraper(BaseScraper):
    """
    Scraper for Unix & Linux Stack Exchange.
    
    Focuses on system administration, shell scripting, and Linux internals.
    """
    
    API_BASE = 'https://api.stackexchange.com/2.3'
    SITE = 'unix'
    
    # High-value tags for Linux sysadmin
    TARGET_TAGS = [
        'linux',
        'bash',
        'shell',
        'systemd',
        'networking',
        'ssh',
        'permissions',
        'filesystems',
        'package-management',
        'apt',
        'yum',
        'dnf',
        'grub',
        'kernel',
        'cron',
        'awk',
        'sed',
        'grep',
        'text-processing',
        'process',
        'security',
        'sudo',
        'users',
        'disk-usage',
        'mount',
        'nfs',
        'samba',
        'firewall',
        'iptables',
        'nftables',
    ]
    
    def __init__(self, config: ScraperConfig, api_key: Optional[str] = None):
        super().__init__(config)
        self.api_key = api_key
        
        if not api_key:
            logger.warning(
                "No Stack Exchange API key. Rate limits will be lower. "
                "Get one at: https://stackapps.com/apps/oauth/register"
            )
    
    def get_source_name(self) -> str:
        return 'unix-se'
    
    def scrape(self, max_questions: int = 500, min_score: int = 10) -> List[ScrapedDocument]:
        """
        Scrape Unix & Linux Stack Exchange questions.
        
        Args:
            max_questions: Maximum questions to scrape
            min_score: Minimum question score
        """
        logger.info(f"Starting Unix.SE scrape (max={max_questions}, min_score={min_score})")
        
        documents = []
        seen_ids = set()
        per_tag = max_questions // len(self.TARGET_TAGS)
        
        for tag in self.TARGET_TAGS:
            logger.info(f"Scraping tag: {tag}")
            
            questions = self._fetch_questions(tag, per_tag, min_score)
            
            for q in questions:
                if q['question_id'] in seen_ids:
                    continue
                seen_ids.add(q['question_id'])
                
                doc = self._convert_to_document(q)
                if doc and self._validate_document(doc):
                    documents.append(doc)
            
            # Rate limiting - be respectful
            time.sleep(2)
        
        logger.info(f"Total Unix.SE documents: {len(documents)}")
        return documents
    
    def _fetch_questions(self, tag: str, max_results: int, min_score: int) -> List[dict]:
        """Fetch questions from API."""
        try:
            import requests
        except ImportError:
            logger.error("requests library required")
            return []
        
        params = {
            'site': self.SITE,
            'tagged': tag,
            'sort': 'votes',
            'order': 'desc',
            'filter': 'withbody',
            'min': min_score,
            'pagesize': min(max_results, 100),
        }
        
        if self.api_key:
            params['key'] = self.api_key
        
        try:
            self.rate_limit()
            response = requests.get(
                f"{self.API_BASE}/questions",
                params=params,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Check quota
            if 'quota_remaining' in data:
                logger.debug(f"API quota remaining: {data['quota_remaining']}")
            
            return data.get('items', [])
            
        except Exception as e:
            logger.error(f"Failed to fetch questions for {tag}: {e}")
            return []
    
    def _convert_to_document(self, question: dict) -> Optional[ScrapedDocument]:
        """Convert API response to document."""
        try:
            q_id = question['question_id']
            title = question.get('title', '')
            body = question.get('body', '')
            tags = question.get('tags', [])
            score = question.get('score', 0)
            answer_count = question.get('answer_count', 0)
            is_answered = question.get('is_answered', False)
            link = question.get('link', f'https://unix.stackexchange.com/q/{q_id}')
            
            # Build content with question and answers
            content = f"# {title}\n\n"
            content += f"**Score**: {score} | **Answers**: {answer_count}\n\n"
            content += "## Question\n\n"
            content += self._clean_html(body)
            
            # Note: To get answers, we'd need another API call
            # For efficiency, we just include the question for now
            
            return ScrapedDocument(
                id=self._generate_id(f"unix-se-{q_id}"),
                url=link,
                title=title,
                content=content,
                source=self.get_source_name(),
                category=self._categorize_tags(tags),
                tags=['unix', 'linux', 'stackexchange'] + tags[:5],
                scraped_at=datetime.utcnow().isoformat(),
                metadata={
                    'question_id': q_id,
                    'score': score,
                    'answer_count': answer_count,
                    'is_answered': is_answered,
                    'original_tags': tags,
                }
            )
        except Exception as e:
            logger.error(f"Failed to convert question: {e}")
            return None
    
    def _clean_html(self, html: str) -> str:
        """Clean HTML to markdown-ish text."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # Convert code blocks
            for code in soup.find_all('pre'):
                code.string = f"\n```\n{code.get_text()}\n```\n"
            
            # Convert inline code
            for code in soup.find_all('code'):
                if code.parent.name != 'pre':
                    code.string = f"`{code.get_text()}`"
            
            return soup.get_text().strip()
        except ImportError:
            # Basic cleaning without BeautifulSoup
            import re
            text = re.sub(r'<[^>]+>', '', html)
            return text.strip()
    
    def _categorize_tags(self, tags: List[str]) -> str:
        """Categorize based on tags."""
        categories = {
            'networking': ['networking', 'ssh', 'firewall', 'iptables', 'nfs', 'samba', 'dns'],
            'shell': ['bash', 'shell', 'awk', 'sed', 'grep', 'text-processing'],
            'system_admin': ['systemd', 'cron', 'process', 'kernel', 'grub'],
            'security': ['security', 'permissions', 'sudo', 'users', 'encryption'],
            'storage': ['filesystems', 'disk-usage', 'mount', 'lvm', 'raid'],
            'packages': ['package-management', 'apt', 'yum', 'dnf', 'rpm'],
        }
        
        for category, keywords in categories.items():
            if any(t in keywords for t in tags):
                return category
        
        return 'general'
    
    def _validate_document(self, doc: ScrapedDocument) -> bool:
        """Validate document quality."""
        if len(doc.content) < 100:
            return False
        if not doc.title:
            return False
        return True
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(name.encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape Unix & Linux Stack Exchange")
    parser.add_argument("--output-dir", default="data/linux/unix-se")
    parser.add_argument("--max-questions", type=int, default=500)
    parser.add_argument("--min-score", type=int, default=10)
    parser.add_argument("--api-key", help="Stack Exchange API key")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    from pathlib import Path
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = UnixSEScraper(config, api_key=args.api_key)
    
    docs = scraper.scrape(max_questions=args.max_questions, min_score=args.min_score)
    
    if docs:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)
        scraper.save_documents(docs, f"{args.output_dir}/unix_se.jsonl")
