"""
Web Search Module using SearXNG

Provides web search capabilities through SearXNG public instances.
Falls back between instances for reliability.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin

import aiohttp

logger = logging.getLogger("halbert")


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str
    source: str = ""  # Which engine returned this
    score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
            "score": self.score,
        }
    
    def to_rag_context(self) -> str:
        """Format for RAG context injection."""
        return f"[{self.title}]({self.url}): {self.snippet}"


@dataclass
class InstanceHealth:
    """Health status of a SearXNG instance."""
    url: str
    healthy: bool = False
    latency_ms: float = 0.0
    last_check: float = 0.0
    error: Optional[str] = None


@dataclass 
class SearchCache:
    """Simple in-memory cache for search results."""
    results: Dict[str, List[SearchResult]] = field(default_factory=dict)
    timestamps: Dict[str, float] = field(default_factory=dict)
    ttl_seconds: int = 3600  # 1 hour default
    max_entries: int = 500
    
    def _hash_query(self, query: str) -> str:
        """Create cache key from query."""
        return hashlib.md5(query.lower().strip().encode()).hexdigest()
    
    def get(self, query: str) -> Optional[List[SearchResult]]:
        """Get cached results if fresh."""
        key = self._hash_query(query)
        if key in self.results:
            if time.time() - self.timestamps.get(key, 0) < self.ttl_seconds:
                logger.debug(f"Cache hit for query: {query[:50]}...")
                return self.results[key]
            else:
                # Expired
                del self.results[key]
                del self.timestamps[key]
        return None
    
    def set(self, query: str, results: List[SearchResult]):
        """Cache results."""
        # Evict old entries if at capacity
        if len(self.results) >= self.max_entries:
            oldest_key = min(self.timestamps, key=self.timestamps.get)
            del self.results[oldest_key]
            del self.timestamps[oldest_key]
        
        key = self._hash_query(query)
        self.results[key] = results
        self.timestamps[key] = time.time()
        logger.debug(f"Cached {len(results)} results for: {query[:50]}...")


class WebSearch:
    """
    Web search using SearXNG public instances.
    
    Features:
    - Multiple instance fallback
    - Instance health monitoring
    - Result caching
    - Rate limiting
    """
    
    # Default public SearXNG instances (curated for reliability)
    # See https://searx.space for full list
    DEFAULT_INSTANCES = [
        "https://search.ononoki.org",
        "https://searx.work",
        "https://search.nerdvpn.de",
        "https://searx.ox2.fr",
        "https://search.mdosch.de",
        "https://searx.fmac.xyz",
        "https://searx.zhenyapav.com",
        "https://paulgo.io",
        "https://search.inetol.net",
        "https://searxng.site",
    ]
    
    def __init__(
        self,
        instances: Optional[List[str]] = None,
        self_hosted: Optional[str] = None,
        timeout: int = 10,
        cache_ttl: int = 3600,
        max_results: int = 10,
    ):
        """
        Initialize web search.
        
        Args:
            instances: List of SearXNG instance URLs (uses defaults if None)
            self_hosted: Optional self-hosted instance URL (takes priority)
            timeout: Request timeout in seconds
            cache_ttl: Cache TTL in seconds
            max_results: Default max results per search
        """
        self.instances = instances or self.DEFAULT_INSTANCES.copy()
        self.self_hosted = self_hosted
        self.timeout = timeout
        self.max_results = max_results
        
        # Instance health tracking
        self.instance_health: Dict[str, InstanceHealth] = {}
        
        # Result caching
        self.cache = SearchCache(ttl_seconds=cache_ttl)
        
        # Rate limiting (queries per second per instance)
        self._last_query_time: Dict[str, float] = {}
        self._min_query_interval = 1.0  # 1 second between queries per instance
        
        logger.info(f"WebSearch initialized with {len(self.instances)} instances")
    
    async def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        engines: Optional[List[str]] = None,
        time_range: Optional[str] = None,
        use_cache: bool = True,
    ) -> List[SearchResult]:
        """
        Search the web using SearXNG.
        
        Args:
            query: Search query
            max_results: Max results to return
            engines: Specific engines to use (e.g., ["google", "duckduckgo"])
            time_range: Time filter ("day", "week", "month", "year")
            use_cache: Whether to use cached results
            
        Returns:
            List of SearchResult objects
        """
        if not query.strip():
            return []
        
        max_results = max_results or self.max_results
        
        # Check cache first
        if use_cache:
            cached = self.cache.get(query)
            if cached:
                return cached[:max_results]
        
        # Build instance priority list
        instances = self._get_instance_priority()
        
        # Try each instance until one works
        last_error = None
        for instance in instances:
            try:
                results = await self._search_instance(
                    instance, query, max_results, engines, time_range
                )
                if results:
                    # Cache successful results
                    self.cache.set(query, results)
                    return results
            except Exception as e:
                last_error = e
                logger.warning(f"Search failed on {instance}: {e}")
                self._mark_instance_unhealthy(instance, str(e))
                continue
        
        # All SearXNG instances failed, try DuckDuckGo fallback
        logger.warning(f"All SearXNG instances failed, trying DuckDuckGo fallback...")
        results = await self._search_duckduckgo(query, max_results)
        if results:
            self.cache.set(query, results)
            return results
        
        logger.error(f"All search methods failed for query: {query[:50]}...")
        if last_error:
            logger.error(f"Last error: {last_error}")
        return []
    
    async def _search_instance(
        self,
        instance: str,
        query: str,
        max_results: int,
        engines: Optional[List[str]],
        time_range: Optional[str],
    ) -> List[SearchResult]:
        """Execute search on a specific instance."""
        
        # Rate limiting
        await self._rate_limit(instance)
        
        # Build search URL
        params = {
            "q": query,
            "format": "json",
            "categories": "general",
        }
        
        if engines:
            params["engines"] = ",".join(engines)
        if time_range:
            params["time_range"] = time_range
        
        search_url = f"{instance.rstrip('/')}/search"
        
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                search_url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                    "Accept": "application/json",
                }
            ) as response:
                latency_ms = (time.time() - start_time) * 1000
                
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}: {await response.text()}")
                
                # Check content type
                content_type = response.headers.get("Content-Type", "")
                if "json" not in content_type:
                    raise Exception(f"{response.status}, message='Attempt to decode JSON with unexpected mimetype: {content_type}', url='{response.url}'")
                
                data = await response.json()
                
                # Update instance health
                self._mark_instance_healthy(instance, latency_ms)
                
                # Parse results
                results = []
                for item in data.get("results", [])[:max_results]:
                    results.append(SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        source=item.get("engine", instance),
                        score=item.get("score", 0.0),
                    ))
                
                logger.info(f"Search on {instance} returned {len(results)} results in {latency_ms:.0f}ms")
                return results
    
    async def _search_duckduckgo(self, query: str, max_results: int) -> List[SearchResult]:
        """
        Fallback: Use DuckDuckGo HTML search (no API key needed).
        
        This scrapes DuckDuckGo's HTML lite version.
        """
        try:
            search_url = "https://html.duckduckgo.com/html/"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    search_url,
                    data={"q": query},
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    headers={
                        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                    }
                ) as response:
                    if response.status != 200:
                        return []
                    
                    html = await response.text()
                    
                    # Parse results from HTML
                    results = []
                    
                    # Simple regex parsing for result links
                    import re
                    
                    # Find result blocks
                    result_pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>'
                    snippet_pattern = r'<a class="result__snippet"[^>]*>([^<]+)</a>'
                    
                    links = re.findall(result_pattern, html)
                    snippets = re.findall(snippet_pattern, html)
                    
                    for i, (url, title) in enumerate(links[:max_results]):
                        snippet = snippets[i] if i < len(snippets) else ""
                        results.append(SearchResult(
                            title=title.strip(),
                            url=url,
                            snippet=snippet.strip(),
                            source="duckduckgo",
                        ))
                    
                    if results:
                        logger.info(f"DuckDuckGo fallback returned {len(results)} results")
                    
                    return results
                    
        except Exception as e:
            logger.warning(f"DuckDuckGo fallback failed: {e}")
            return []
    
    async def _rate_limit(self, instance: str):
        """Ensure we don't query too frequently."""
        last_time = self._last_query_time.get(instance, 0)
        elapsed = time.time() - last_time
        
        if elapsed < self._min_query_interval:
            await asyncio.sleep(self._min_query_interval - elapsed)
        
        self._last_query_time[instance] = time.time()
    
    def _get_instance_priority(self) -> List[str]:
        """Get instances sorted by health/priority."""
        instances = []
        
        # Self-hosted always first if configured
        if self.self_hosted:
            instances.append(self.self_hosted)
        
        # Sort remaining by health
        healthy = []
        unhealthy = []
        
        for url in self.instances:
            health = self.instance_health.get(url)
            if health and not health.healthy:
                unhealthy.append(url)
            else:
                healthy.append((url, health.latency_ms if health else float('inf')))
        
        # Sort healthy by latency
        healthy.sort(key=lambda x: x[1])
        instances.extend([url for url, _ in healthy])
        instances.extend(unhealthy)
        
        return instances
    
    def _mark_instance_healthy(self, instance: str, latency_ms: float):
        """Mark an instance as healthy."""
        self.instance_health[instance] = InstanceHealth(
            url=instance,
            healthy=True,
            latency_ms=latency_ms,
            last_check=time.time(),
        )
    
    def _mark_instance_unhealthy(self, instance: str, error: str):
        """Mark an instance as unhealthy."""
        self.instance_health[instance] = InstanceHealth(
            url=instance,
            healthy=False,
            latency_ms=0,
            last_check=time.time(),
            error=error,
        )
    
    async def check_all_instances(self) -> Dict[str, InstanceHealth]:
        """Check health of all configured instances."""
        results = {}
        
        async def check_one(url: str):
            try:
                start = time.time()
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{url.rstrip('/')}/search",
                        params={"q": "test", "format": "json"},
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as response:
                        latency = (time.time() - start) * 1000
                        if response.status == 200:
                            self._mark_instance_healthy(url, latency)
                        else:
                            self._mark_instance_unhealthy(url, f"HTTP {response.status}")
            except Exception as e:
                self._mark_instance_unhealthy(url, str(e))
            
            results[url] = self.instance_health[url]
        
        # Check all in parallel
        all_instances = [self.self_hosted] if self.self_hosted else []
        all_instances.extend(self.instances)
        
        await asyncio.gather(*[check_one(url) for url in all_instances])
        
        return results
    
    def get_instance_status(self) -> List[Dict[str, Any]]:
        """Get current status of all instances."""
        status = []
        
        all_instances = [self.self_hosted] if self.self_hosted else []
        all_instances.extend(self.instances)
        
        for url in all_instances:
            health = self.instance_health.get(url)
            status.append({
                "url": url,
                "healthy": health.healthy if health else None,
                "latency_ms": health.latency_ms if health else None,
                "last_check": health.last_check if health else None,
                "error": health.error if health else None,
                "is_self_hosted": url == self.self_hosted,
            })
        
        return status
    
    async def search_for_rag(
        self,
        query: str,
        max_results: int = 5,
    ) -> str:
        """
        Search and format results for RAG context injection.
        
        Returns formatted string suitable for LLM context.
        """
        results = await self.search(query, max_results=max_results)
        
        if not results:
            return ""
        
        lines = ["**Web Search Results:**", ""]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. [{r.title}]({r.url})")
            if r.snippet:
                lines.append(f"   {r.snippet[:200]}...")
            lines.append("")
        
        return "\n".join(lines)


# Global instance (lazy loaded)
_web_search: Optional[WebSearch] = None


def get_web_search() -> WebSearch:
    """Get or create the global WebSearch instance."""
    global _web_search
    if _web_search is None:
        _web_search = WebSearch()
    return _web_search


async def web_search(query: str, max_results: int = 10) -> List[SearchResult]:
    """Convenience function for quick searches."""
    return await get_web_search().search(query, max_results=max_results)


async def web_search_for_rag(query: str, max_results: int = 5) -> str:
    """Convenience function for RAG context searches."""
    return await get_web_search().search_for_rag(query, max_results=max_results)
