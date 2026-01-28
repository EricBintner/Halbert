"""
Server Fault Stack Exchange Scraper.

Phase 27: RAG Coverage

Server Fault is for professional system administrators.
Higher-quality enterprise-focused Q&A than Stack Overflow.
"""

import logging
from typing import List, Optional
from datetime import datetime
import time

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class ServerFaultScraper(BaseScraper):
    """
    Scraper for Server Fault (serverfault.com).
    
    Enterprise-focused system administration Q&A.
    """
    
    API_BASE = 'https://api.stackexchange.com/2.3'
    SITE = 'serverfault'
    
    # Professional sysadmin tags
    TARGET_TAGS = [
        'linux',
        'ubuntu',
        'centos',
        'rhel',
        'debian',
        'nginx',
        'apache',
        'networking',
        'dns',
        'ssl',
        'tls',
        'certificates',
        'ssh',
        'backup',
        'monitoring',
        'docker',
        'kubernetes',
        'ansible',
        'puppet',
        'systemd',
        'security',
        'firewall',
        'load-balancing',
        'high-availability',
        'storage',
        'nfs',
        'iscsi',
        'lvm',
        'raid',
    ]
    
    def __init__(self, config: ScraperConfig, api_key: Optional[str] = None):
        super().__init__(config)
        self.api_key = api_key
    
    def get_source_name(self) -> str:
        return 'serverfault'
    
    def scrape(self, max_questions: int = 300, min_score: int = 15) -> List[ScrapedDocument]:
        """
        Scrape Server Fault questions.
        
        Higher min_score because SF has higher quality threshold.
        """
        logger.info(f"Starting ServerFault scrape (max={max_questions}, min_score={min_score})")
        
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
            
            time.sleep(2)  # Rate limiting
        
        logger.info(f"Total ServerFault documents: {len(documents)}")
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
            link = question.get('link', f'https://serverfault.com/q/{q_id}')
            
            content = f"# {title}\n\n"
            content += f"**Score**: {score} | **Source**: Server Fault (Professional Sysadmin)\n\n"
            content += "## Question\n\n"
            content += self._clean_html(body)
            
            return ScrapedDocument(
                id=self._generate_id(f"sf-{q_id}"),
                url=link,
                title=title,
                content=content,
                source=self.get_source_name(),
                category=self._categorize_tags(tags),
                tags=['serverfault', 'enterprise', 'sysadmin'] + tags[:5],
                scraped_at=datetime.now().isoformat(),
                metadata={
                    'question_id': q_id,
                    'score': score,
                    'original_tags': tags,
                }
            )
        except Exception as e:
            logger.error(f"Failed to convert question: {e}")
            return None
    
    def _clean_html(self, html: str) -> str:
        """Clean HTML to text."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            for code in soup.find_all('pre'):
                code.string = f"\n```\n{code.get_text()}\n```\n"
            for code in soup.find_all('code'):
                if code.parent.name != 'pre':
                    code.string = f"`{code.get_text()}`"
            return soup.get_text().strip()
        except ImportError:
            import re
            return re.sub(r'<[^>]+>', '', html).strip()
    
    def _categorize_tags(self, tags: List[str]) -> str:
        """Categorize based on tags."""
        categories = {
            'web_server': ['nginx', 'apache', 'httpd', 'load-balancing'],
            'networking': ['networking', 'dns', 'firewall', 'vpn'],
            'security': ['security', 'ssl', 'tls', 'certificates', 'ssh'],
            'storage': ['storage', 'nfs', 'iscsi', 'lvm', 'raid', 'backup'],
            'containers': ['docker', 'kubernetes', 'containers'],
            'automation': ['ansible', 'puppet', 'chef', 'terraform'],
            'monitoring': ['monitoring', 'nagios', 'prometheus', 'grafana'],
        }
        
        for category, keywords in categories.items():
            if any(t in keywords for t in tags):
                return category
        
        return 'system_admin'
    
    def _validate_document(self, doc: ScrapedDocument) -> bool:
        """Validate document quality."""
        return len(doc.content) >= 100 and bool(doc.title)
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(name.encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    
    parser = argparse.ArgumentParser(description="Scrape Server Fault")
    parser.add_argument("--output-dir", default="data/linux/serverfault")
    parser.add_argument("--max-questions", type=int, default=300)
    parser.add_argument("--min-score", type=int, default=15)
    parser.add_argument("--api-key", help="Stack Exchange API key")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = ServerFaultScraper(config, api_key=args.api_key)
    
    docs = scraper.scrape(max_questions=args.max_questions, min_score=args.min_score)
    
    if docs:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)
        scraper.save_documents(docs, "serverfault.jsonl")
