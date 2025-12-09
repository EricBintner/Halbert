"""
RAG Ingestion Engine - Quality-First Auto-Ingest System

Phase 10: Self-maintaining RAG with trusted sources.
"""

import logging
import requests
import hashlib
import yaml
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup

logger = logging.getLogger('cerebric')


@dataclass
class SourceInfo:
    """Information about a source domain."""
    pattern: str
    name: str
    trust: str
    tier: int
    requires_manual_curation: bool = False
    requires_vote_filter: Optional[int] = None


@dataclass
class DocumentMetadata:
    """Full attribution metadata for a document."""
    source_url: str
    source_name: str
    trust_tier: int
    publisher: str
    fetch_date: str
    content_hash: str


@dataclass
class IngestResult:
    """Result of an ingestion attempt."""
    success: bool
    url: str
    title: str = ""
    doc_count: int = 0
    error: str = ""
    trust_tier: int = 0
    source_name: str = ""
    warnings: List[str] = field(default_factory=list)


class SourceRegistry:
    """
    Smart source registry with auto-detection for documentation sites.
    
    Uses:
    1. Blocklist for known bad sources
    2. Whitelist for known good sources (bonus trust)
    3. URL pattern heuristics for docs detection
    4. Content analysis for quality validation
    """
    
    # URL patterns that indicate documentation
    DOCS_URL_PATTERNS = [
        '/docs/', '/doc/', '/documentation/', '/guide/', '/guides/',
        '/kb/', '/knowledge/', '/wiki/', '/manual/', '/reference/',
        '/tutorial/', '/tutorials/', '/howto/', '/how-to/',
        '/learn/', '/getting-started/', '/quickstart/',
        'docs.', 'wiki.', 'help.', 'support.', 'developer.',
        'readthedocs.io', 'gitbook.io', 'readme.io',
    ]
    
    # Domain patterns that are usually documentation
    DOCS_DOMAIN_PATTERNS = [
        'readthedocs.io', 'readthedocs.org',
        'gitbook.io', 'readme.io',
        'wiki.', 'docs.', 'documentation.',
        '.io/docs', '.com/docs', '.org/docs',
    ]
    
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            this_file = Path(__file__).resolve()
            repo_root = this_file.parent.parent.parent.parent
            self.config_path = repo_root / 'config' / 'approved_sources.yml'
        else:
            self.config_path = config_path
        
        self.tier_1: List[SourceInfo] = []
        self.tier_2: List[SourceInfo] = []
        self.tier_3: List[SourceInfo] = []
        self.blocked: List[Dict] = []
        
        self._load_config()
    
    def _load_config(self):
        """Load approved sources from YAML."""
        if not self.config_path.exists():
            logger.warning(f"Approved sources config not found: {self.config_path}")
            return
        
        with open(self.config_path) as f:
            config = yaml.safe_load(f)
        
        for item in config.get('tier_1_official', []):
            self.tier_1.append(SourceInfo(
                pattern=item['pattern'],
                name=item['name'],
                trust=item['trust'],
                tier=1
            ))
        
        for item in config.get('tier_2_community', []):
            self.tier_2.append(SourceInfo(
                pattern=item['pattern'],
                name=item['name'],
                trust=item['trust'],
                tier=2
            ))
        
        for item in config.get('tier_3_expert', []):
            self.tier_3.append(SourceInfo(
                pattern=item['pattern'],
                name=item['name'],
                trust=item['trust'],
                tier=3,
                requires_manual_curation=item.get('requires_manual_curation', False),
                requires_vote_filter=item.get('requires_vote_filter')
            ))
        
        self.blocked = config.get('blocked', [])
        
        logger.info(f"Loaded source registry: {len(self.tier_1)} tier1, {len(self.tier_2)} tier2, {len(self.tier_3)} tier3, {len(self.blocked)} blocked")
    
    def _pattern_matches(self, pattern: str, domain: str) -> bool:
        """Check if domain matches pattern (supports wildcards)."""
        if pattern.startswith('*.'):
            suffix = pattern[1:]
            return domain.endswith(suffix) or domain == pattern[2:]
        return domain == pattern or domain.endswith('.' + pattern)
    
    def _looks_like_docs(self, url: str) -> bool:
        """
        Heuristic: Does this URL look like documentation?
        """
        url_lower = url.lower()
        
        # Check URL patterns
        for pattern in self.DOCS_URL_PATTERNS:
            if pattern in url_lower:
                return True
        
        # Check domain patterns
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        for pattern in self.DOCS_DOMAIN_PATTERNS:
            if pattern in domain or pattern in url_lower:
                return True
        
        return False
    
    def check_source(self, url: str) -> Tuple[Optional[SourceInfo], Optional[str]]:
        """
        Check if URL is acceptable.
        
        Logic:
        1. If blocked -> reject
        2. If whitelisted -> return with tier
        3. If looks like docs -> auto-approve as tier 2
        4. Otherwise -> unknown (but still allow with warning)
        
        Returns:
            (SourceInfo, None) if approved
            (None, reason) if blocked
            (None, None) if unknown (but can still be added)
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Check blocked first
        for blocked in self.blocked:
            if self._pattern_matches(blocked['pattern'], domain):
                return None, blocked.get('reason', 'Blocked source')
        
        # Check explicit whitelist (bonus trust)
        for source in self.tier_1:
            if self._pattern_matches(source.pattern, domain):
                return source, None
        
        for source in self.tier_2:
            if self._pattern_matches(source.pattern, domain):
                return source, None
        
        for source in self.tier_3:
            if self._pattern_matches(source.pattern, domain):
                return source, None
        
        # Auto-detect: Does it look like documentation?
        if self._looks_like_docs(url):
            # Auto-approve as tier 2 (community/detected)
            return SourceInfo(
                pattern=domain,
                name=f"{domain} (auto-detected docs)",
                trust="auto_detected",
                tier=2
            ), None
        
        # Unknown but not blocked - return None but DON'T block
        # The caller can decide to allow with a warning
        return None, None


class URLAnalyzer:
    """
    Analyze URLs before ingestion.
    Detects content type, JS requirements, etc.
    """
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
    
    def validate_url(self, url: str) -> Tuple[bool, str]:
        """
        Validate URL is accessible.
        
        Returns:
            (True, content_type) if accessible
            (False, error_message) if not
        """
        try:
            response = requests.head(url, timeout=self.timeout, allow_redirects=True)
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', 'unknown')
                return True, content_type
            elif response.status_code == 404:
                return False, "404 Not Found"
            elif response.status_code == 403:
                return False, "403 Forbidden"
            else:
                return False, f"HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            return False, "Timeout"
        except requests.exceptions.ConnectionError:
            return False, "Connection error"
        except Exception as e:
            return False, str(e)
    
    def detect_content_type(self, content_type: str) -> str:
        """Determine extraction strategy from content type."""
        if 'html' in content_type.lower():
            return 'html'
        elif 'pdf' in content_type.lower():
            return 'pdf'
        elif 'json' in content_type.lower():
            return 'json'
        elif 'text/plain' in content_type.lower():
            return 'text'
        return 'unknown'
    
    def check_js_heavy(self, url: str) -> bool:
        """
        Heuristic to detect if page requires JavaScript.
        (Simple check - could be improved with Playwright)
        """
        # Known JS-heavy sites
        js_heavy_patterns = [
            'docs.github.com',
            'developer.mozilla.org',
            'react.dev',
            'vuejs.org',
        ]
        
        domain = urlparse(url).netloc.lower()
        return any(p in domain for p in js_heavy_patterns)


class ContentExtractor:
    """
    Extract content from web pages and PDFs.
    """
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    def extract_pdf(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Extract content from PDF URL.
        
        Returns:
            (title, description, full_text) or (None, None, None) on error
        """
        try:
            import pdfplumber
            import tempfile
            
            # Download PDF
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            # Save to temp file and extract
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
                f.write(response.content)
                temp_path = f.name
            
            try:
                text_parts = []
                with pdfplumber.open(temp_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
                
                full_text = '\n\n'.join(text_parts)
                
                # Extract title from first line or URL
                title = ""
                lines = full_text.split('\n')[:10]
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 5 and len(line) < 200:
                        title = line
                        break
                
                if not title:
                    # Use filename from URL
                    title = url.split('/')[-1].replace('.pdf', '').replace('-', ' ').replace('_', ' ')
                
                # Description from first paragraph
                description = ""
                for line in lines[1:10]:
                    line = line.strip()
                    if len(line) > 50:
                        description = line[:300]
                        break
                
                return title, description, full_text
                
            finally:
                import os
                os.unlink(temp_path)
                
        except ImportError:
            logger.error("pdfplumber not installed. Run: pip install pdfplumber")
            return None, None, None
        except Exception as e:
            logger.error(f"Failed to extract PDF {url}: {e}")
            return None, None, None
    
    def extract_html(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Extract content from HTML page.
        
        Returns:
            (title, description, full_text) or (None, None, None) on error
        """
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header']):
                element.decompose()
            
            # Extract title
            title = ""
            if soup.title:
                title = soup.title.string or ""
            if not title:
                h1 = soup.find('h1')
                if h1:
                    title = h1.get_text(strip=True)
            
            # Extract main content
            main = soup.find('main') or soup.find('article') or soup.find('body')
            if main:
                text = main.get_text(separator='\n', strip=True)
            else:
                text = soup.get_text(separator='\n', strip=True)
            
            # Extract description (first meaningful paragraph)
            description = ""
            for p in soup.find_all('p'):
                p_text = p.get_text(strip=True)
                if len(p_text) > 50:
                    description = p_text[:300]
                    break
            
            return title, description, text
            
        except Exception as e:
            logger.error(f"Failed to extract {url}: {e}")
            return None, None, None


class QualityValidator:
    """
    Validate document quality before adding to corpus.
    
    Uses content analysis to determine if something looks like
    useful technical documentation.
    """
    
    MIN_CONTENT_LENGTH = 500
    
    # Technical terms that indicate documentation
    TECH_INDICATORS = [
        'install', 'configure', 'setup', 'command', 'run', 'execute',
        'sudo', 'apt', 'yum', 'dnf', 'pacman', 'pip', 'npm',
        'config', 'file', 'directory', 'path', 'server', 'client',
        'linux', 'unix', 'bash', 'shell', 'terminal', 'cli',
        'docker', 'container', 'kubernetes', 'systemd', 'service',
        'api', 'http', 'https', 'port', 'network', 'firewall',
        'database', 'sql', 'query', 'table', 'schema',
        'function', 'class', 'method', 'variable', 'parameter',
        'error', 'debug', 'log', 'troubleshoot', 'fix',
        'example', 'usage', 'syntax', 'options', 'flags',
    ]
    
    def validate(self, title: str, content: str) -> Tuple[bool, List[str]]:
        """
        Validate document quality.
        
        Returns:
            (is_valid, list_of_warnings)
        """
        warnings = []
        
        # Check content length
        if len(content) < self.MIN_CONTENT_LENGTH:
            return False, [f"Content too short ({len(content)} chars, min {self.MIN_CONTENT_LENGTH})"]
        
        # Check for title
        if not title or len(title) < 3:
            warnings.append("Missing or very short title")
        
        # Check for code blocks (good indicator of docs)
        has_code = '```' in content or '    ' in content or '<code>' in content
        
        # Check for technical terms
        content_lower = content.lower()
        tech_term_count = sum(1 for term in self.TECH_INDICATORS if term in content_lower)
        
        # Check language (basic heuristic)
        common_english = ['the', 'and', 'is', 'to', 'of', 'in', 'for', 'with']
        words = content_lower.split()[:100]
        english_count = sum(1 for w in words if w in common_english)
        if english_count < 3:
            warnings.append("May not be English content")
        
        # Quality score
        if tech_term_count < 3 and not has_code:
            warnings.append("Low technical content - may not be documentation")
        
        return True, warnings
    
    def compute_hash(self, content: str) -> str:
        """Compute content hash for duplicate detection."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def looks_like_docs(self, content: str) -> Tuple[bool, float]:
        """
        Analyze content to determine if it looks like documentation.
        
        Returns:
            (is_docs, confidence_score)
        """
        content_lower = content.lower()
        
        # Count indicators
        tech_terms = sum(1 for term in self.TECH_INDICATORS if term in content_lower)
        has_code = '```' in content or '<code>' in content or '<pre>' in content
        has_headings = '#' in content or '<h1>' in content or '<h2>' in content
        has_lists = '- ' in content or '* ' in content or '<li>' in content
        
        # Calculate score
        score = 0
        score += min(tech_terms * 5, 40)  # Up to 40 points for tech terms
        score += 20 if has_code else 0
        score += 15 if has_headings else 0
        score += 15 if has_lists else 0
        score += 10 if len(content) > 2000 else 0
        
        is_docs = score >= 30
        confidence = min(score / 100, 1.0)
        
        return is_docs, confidence


class RAGIngestionEngine:
    """
    Main ingestion engine - orchestrates the full process.
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.registry = SourceRegistry()
        self.analyzer = URLAnalyzer()
        self.extractor = ContentExtractor()
        self.validator = QualityValidator()
        
        if data_dir is None:
            this_file = Path(__file__).resolve()
            repo_root = this_file.parent.parent.parent.parent
            self.data_dir = repo_root / 'data' / 'linux'
        else:
            self.data_dir = data_dir
        
        self.user_sources_dir = self.data_dir / 'user-sources'
        self.user_sources_dir.mkdir(parents=True, exist_ok=True)
    
    def add_url(self, url: str, force_trust: bool = False) -> IngestResult:
        """
        Add a single URL to the RAG corpus.
        
        Args:
            url: URL to ingest
            force_trust: If True, skip source validation (for unknown sources)
        
        Returns:
            IngestResult with success/failure details
        """
        result = IngestResult(success=False, url=url)
        
        # Step 1: Check source (blocklist, whitelist, auto-detect)
        source_info, blocked_reason = self.registry.check_source(url)
        
        if blocked_reason:
            result.error = f"Blocked source: {blocked_reason}"
            return result
        
        if source_info:
            # Known or auto-detected source
            result.trust_tier = source_info.tier
            result.source_name = source_info.name
            
            if source_info.requires_manual_curation:
                result.warnings.append(f"Source '{source_info.name}' typically requires manual curation")
            
            if source_info.trust == "auto_detected":
                result.warnings.append("Auto-detected as documentation based on URL patterns")
        else:
            # Unknown source - allow with warning (not blocked = probably fine)
            result.trust_tier = 3  # Tier 3 = unverified but allowed
            result.source_name = urlparse(url).netloc
            result.warnings.append("Unknown source type - content will be validated")
        
        # Step 2: Validate URL
        valid, content_type_or_error = self.analyzer.validate_url(url)
        if not valid:
            result.error = f"URL validation failed: {content_type_or_error}"
            return result
        
        content_type = self.analyzer.detect_content_type(content_type_or_error)
        
        if content_type not in ('html', 'text', 'pdf'):
            result.error = f"Unsupported content type: {content_type}"
            return result
        
        # Check for JS-heavy sites
        if content_type == 'html' and self.analyzer.check_js_heavy(url):
            result.warnings.append("Site may require JavaScript - extraction might be incomplete")
        
        # Step 3: Extract content based on type
        if content_type == 'pdf':
            title, description, content = self.extractor.extract_pdf(url)
        else:
            title, description, content = self.extractor.extract_html(url)
        
        if not content:
            result.error = "Failed to extract content"
            return result
        
        result.title = title or urlparse(url).path.split('/')[-1]
        
        # Step 4: Validate quality
        is_valid, warnings = self.validator.validate(title, content)
        result.warnings.extend(warnings)
        
        if not is_valid:
            result.error = f"Quality validation failed: {warnings}"
            return result
        
        # Step 5: Create document with full attribution
        content_hash = self.validator.compute_hash(content)
        
        doc = {
            'name': result.title,
            'description': description or '',
            'content': content,  # RAG expects 'content' field
            'metadata': {
                'source_url': url,
                'source_name': result.source_name,
                'trust_tier': result.trust_tier,
                'publisher': result.source_name,
                'fetch_date': datetime.now().isoformat(),
                'content_hash': content_hash
            }
        }
        
        # Step 6: Save to user sources
        output_file = self.user_sources_dir / 'user_added.jsonl'
        
        with open(output_file, 'a') as f:
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')
        
        result.success = True
        result.doc_count = 1
        
        logger.info(f"Added document: {result.title} from {result.source_name} (Tier {result.trust_tier})")
        
        return result
    
    def add_urls(self, urls: List[str], force_trust: bool = False) -> List[IngestResult]:
        """Add multiple URLs."""
        results = []
        for url in urls:
            result = self.add_url(url, force_trust)
            results.append(result)
        return results
    
    def get_user_doc_count(self) -> int:
        """Get count of user-added documents."""
        output_file = self.user_sources_dir / 'user_added.jsonl'
        if not output_file.exists():
            return 0
        
        with open(output_file) as f:
            return sum(1 for _ in f)


class SitemapCrawler:
    """
    Crawl sitemaps to discover URLs for ingestion.
    """
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    def fetch_sitemap(self, sitemap_url: str) -> List[str]:
        """
        Fetch and parse a sitemap XML.
        
        Returns list of URLs found in sitemap.
        """
        try:
            response = requests.get(sitemap_url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'xml')
            
            urls = []
            
            # Check for sitemap index (sitemapindex)
            sitemaps = soup.find_all('sitemap')
            if sitemaps:
                # This is a sitemap index, recursively fetch each sitemap
                for sitemap in sitemaps[:10]:  # Limit to 10 sub-sitemaps
                    loc = sitemap.find('loc')
                    if loc:
                        sub_urls = self.fetch_sitemap(loc.text.strip())
                        urls.extend(sub_urls)
            else:
                # Regular sitemap with URLs
                for url_tag in soup.find_all('url'):
                    loc = url_tag.find('loc')
                    if loc:
                        urls.append(loc.text.strip())
            
            return urls
            
        except Exception as e:
            logger.error(f"Failed to fetch sitemap {sitemap_url}: {e}")
            return []
    
    def filter_urls(
        self,
        urls: List[str],
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        max_urls: int = 100
    ) -> List[str]:
        """
        Filter URLs based on patterns.
        
        Args:
            urls: List of URLs to filter
            include_patterns: Only include URLs matching these patterns
            exclude_patterns: Exclude URLs matching these patterns
            max_urls: Maximum number of URLs to return
        """
        filtered = []
        
        for url in urls:
            # Check excludes first
            if exclude_patterns:
                excluded = False
                for pattern in exclude_patterns:
                    if pattern in url:
                        excluded = True
                        break
                if excluded:
                    continue
            
            # Check includes
            if include_patterns:
                included = False
                for pattern in include_patterns:
                    if pattern in url:
                        included = True
                        break
                if not included:
                    continue
            
            filtered.append(url)
            
            if len(filtered) >= max_urls:
                break
        
        return filtered


def test_ingestion():
    """Test the ingestion engine."""
    print("="*60)
    print("RAG Ingestion Engine Test")
    print("="*60)
    
    engine = RAGIngestionEngine()
    
    # Test URLs
    test_urls = [
        ("https://borgbackup.readthedocs.io/en/stable/quickstart.html", "Tier 1 - should work"),
        ("https://wiki.archlinux.org/title/Bash", "Tier 1 - should work"),
        ("https://medium.com/some-article", "Blocked - should fail"),
        ("https://example-unknown.com/docs", "Unknown - should warn"),
    ]
    
    for url, description in test_urls:
        print(f"\nTest: {description}")
        print(f"URL: {url}")
        
        result = engine.add_url(url)
        
        if result.success:
            print(f"✅ Success: {result.title}")
            print(f"   Source: {result.source_name} (Tier {result.trust_tier})")
        else:
            print(f"❌ Failed: {result.error}")
        
        if result.warnings:
            print(f"   ⚠️ Warnings: {result.warnings}")


if __name__ == '__main__':
    test_ingestion()
