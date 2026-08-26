# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Ask Different (apple.stackexchange.com) scraper using the Stack Exchange API.

Scrapes high-quality macOS/Apple Q&A from Ask Different.
Licensed under CC BY-SA 4.0 (attribution required, ShareAlike).

This scraper improves on the existing StackOverflow/UnixSE scrapers by also
fetching the accepted answer or top-voted answer for each question, making
the Q&A content much more useful for RAG retrieval.
"""

import logging
import hashlib
import time
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class AskDifferentScraper(BaseScraper):
    """
    Scraper for Ask Different (apple.stackexchange.com).

    Uses the Stack Exchange API to fetch high-voted macOS/Apple Q&A.
    Also fetches the accepted or top-voted answer for each question.
    """

    API_BASE = 'https://api.stackexchange.com/2.3'
    SITE = 'apple'

    # macOS-relevant tags on Ask Different
    TARGET_TAGS = [
        'macos',
        'macbook',
        'macbookpro',
        'mac',
        'terminal',
        'bash',
        'homebrew',
        'launchd',
        'disk-utility',
        'time-machine',
        'filevault',
        'gatekeeper',
        'sip',
        'keychain',
        'apple-silicon',
        'rosetta',
        'finder',
        'dns',
        'network',
        'wifi',
        'bluetooth',
        'permissions',
        'crash',
        'kernel-panic',
        'backup',
        'icloud',
        'apple-id',
        'recovery-mode',
        'apfs',
        'boot',
        'sleep',
        'battery',
        'performance',
        'security',
        'encryption',
        'script',
        'automator',
        'plist',
        'xcode',
        'git',
        'python',
        'ssh',
        'vpn',
        'firewall',
        'upgrade',
        'installation',
        'uninstall',
        'settings',
        'preferences',
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
        return 'ask-different'

    def scrape(self, max_questions: int = 500, min_score: int = 10) -> List[ScrapedDocument]:
        """
        Scrape Ask Different questions with answers.

        Args:
            max_questions: Maximum questions to scrape
            min_score: Minimum question score (upvotes)
        """
        logger.info(f"Starting Ask Different scrape (max={max_questions}, min_score={min_score})")

        documents = []
        seen_ids = set()
        per_tag = max(5, max_questions // len(self.TARGET_TAGS))

        for tag in self.TARGET_TAGS:
            logger.info(f"Scraping tag: {tag}")

            questions = self._fetch_questions(tag, per_tag, min_score)

            for q in questions:
                if q['question_id'] in seen_ids:
                    continue
                seen_ids.add(q['question_id'])

                # Fetch the accepted or top answer
                answer = self._fetch_answer(q)

                doc = self._convert_to_document(q, answer)
                if doc and self._validate_document(doc):
                    documents.append(doc)

            # Rate limiting
            time.sleep(1)

        logger.info(f"Total Ask Different documents: {len(documents)}")
        return documents

    def _fetch_questions(self, tag: str, max_results: int, min_score: int) -> List[Dict[str, Any]]:
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

            if 'quota_remaining' in data:
                logger.debug(f"API quota remaining: {data['quota_remaining']}")

            return data.get('items', [])

        except Exception as e:
            logger.error(f"Failed to fetch questions for {tag}: {e}")
            return []

    def _fetch_answer(self, question: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Fetch the accepted answer or top-voted answer for a question.

        Args:
            question: Question object from API

        Returns:
            Answer object or None
        """
        try:
            import requests
        except ImportError:
            return None

        q_id = question.get('question_id')
        accepted_answer_id = question.get('accepted_answer_id')

        # If there's an accepted answer, fetch it
        if accepted_answer_id:
            params = {
                'site': self.SITE,
                'filter': 'withbody',
                'order': 'desc',
                'sort': 'votes',
            }
            if self.api_key:
                params['key'] = self.api_key

            try:
                self.rate_limit()
                response = requests.get(
                    f"{self.API_BASE}/answers/{accepted_answer_id}",
                    params=params,
                    timeout=self.config.timeout
                )
                response.raise_for_status()
                data = response.json()
                items = data.get('items', [])
                if items:
                    return items[0]
            except Exception as e:
                logger.debug(f"Failed to fetch accepted answer for {q_id}: {e}")

        # Otherwise, fetch top-voted answers to the question
        if not question.get('is_answered', False):
            return None

        params = {
            'site': self.SITE,
            'sort': 'votes',
            'order': 'desc',
            'filter': 'withbody',
            'pagesize': 1,
        }
        if self.api_key:
            params['key'] = self.api_key

        try:
            self.rate_limit()
            response = requests.get(
                f"{self.API_BASE}/questions/{q_id}/answers",
                params=params,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            data = response.json()
            items = data.get('items', [])
            if items:
                return items[0]
        except Exception as e:
            logger.debug(f"Failed to fetch answers for {q_id}: {e}")

        return None

    def _convert_to_document(
        self, question: Dict[str, Any], answer: Optional[Dict[str, Any]]
    ) -> Optional[ScrapedDocument]:
        """Convert question + answer to ScrapedDocument."""
        try:
            q_id = question['question_id']
            title = question.get('title', '')
            body = question.get('body', '')
            tags = question.get('tags', [])
            score = question.get('score', 0)
            answer_count = question.get('answer_count', 0)
            is_answered = question.get('is_answered', False)
            link = question.get('link', f'https://apple.stackexchange.com/q/{q_id}')

            # Build content with question and answer
            content = f"# {title}\n\n"
            content += f"**Score**: {score} | **Answers**: {answer_count}\n\n"
            content += "## Question\n\n"
            content += self._clean_html(body)

            if answer:
                a_score = answer.get('score', 0)
                a_body = answer.get('body', '')
                is_accepted = answer.get('is_accepted', False)

                content += "\n\n## Answer"
                if is_accepted:
                    content += " (Accepted)"
                content += f"\n\n**Answer Score**: {a_score}\n\n"
                content += self._clean_html(a_body)

            return ScrapedDocument(
                id=self._generate_id(f"ask-different-{q_id}"),
                url=link,
                title=title,
                content=content,
                source=self.get_source_name(),
                category=self._categorize_tags(tags),
                tags=['macos', 'apple', 'stackexchange'] + tags[:5],
                scraped_at=datetime.now().isoformat(),
                metadata={
                    'question_id': q_id,
                    'score': score,
                    'answer_count': answer_count,
                    'is_answered': is_answered,
                    'answer_score': answer.get('score', 0) if answer else 0,
                    'has_accepted_answer': answer.get('is_accepted', False) if answer else False,
                    'original_tags': tags,
                    'license': 'CC BY-SA 4.0',
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
            import re
            text = re.sub(r'<[^>]+>', '', html)
            return text.strip()

    def _categorize_tags(self, tags: List[str]) -> str:
        """Categorize based on tags."""
        categories = {
            'networking': ['network', 'wifi', 'dns', 'bluetooth', 'vpn', 'firewall', 'ssh'],
            'shell': ['terminal', 'bash', 'script', 'automator'],
            'system_admin': ['launchd', 'boot', 'sleep', 'performance', 'settings', 'preferences', 'plist'],
            'security': ['security', 'filevault', 'gatekeeper', 'sip', 'keychain', 'encryption', 'permissions'],
            'storage': ['disk-utility', 'apfs', 'time-machine', 'backup'],
            'packages': ['homebrew', 'installation', 'uninstall', 'upgrade'],
            'hardware': ['macbook', 'macbookpro', 'mac', 'apple-silicon', 'rosetta', 'battery'],
            'development': ['xcode', 'git', 'python'],
            'recovery': ['recovery-mode', 'kernel-panic', 'crash'],
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
        return hashlib.md5(name.encode()).hexdigest()[:16]


def main():
    """CLI entry point for Ask Different scraper."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Scrape Ask Different (apple.stackexchange.com)")
    parser.add_argument('--output-dir', type=Path, default=Path('data/macos/ask-different'))
    parser.add_argument('--max-questions', type=int, default=500)
    parser.add_argument('--min-score', type=int, default=10)
    parser.add_argument('--api-key', type=str, help='Stack Exchange API key')
    parser.add_argument('--rate-limit', type=float, default=1.0)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    config = ScraperConfig(
        output_dir=args.output_dir,
        rate_limit_delay=args.rate_limit,
    )

    scraper = AskDifferentScraper(config, api_key=args.api_key)
    documents = scraper.scrape(max_questions=args.max_questions, min_score=args.min_score)

    output_file = args.output_dir / "ask_different.jsonl"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        for doc in documents:
            f.write(json.dumps(doc.to_dict()) + '\n')

    print(f"Saved {len(documents)} documents to {output_file}")


if __name__ == '__main__':
    main()
