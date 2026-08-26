# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Web Search Tool

Provides web search capabilities for the agent.
Supports DuckDuckGo (no API key) and SearXNG (self-hosted).
"""

from __future__ import annotations
import asyncio
import logging
import aiohttp
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from urllib.parse import quote_plus

logger = logging.getLogger('halbert.tools.web_search')


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str
    source: str = "web"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source
        }


class WebSearchTool:
    """
    Web search tool supporting multiple backends.
    
    Backends:
    - DuckDuckGo (default, no API key needed)
    - SearXNG (self-hosted, configurable)
    """
    
    def __init__(
        self,
        backend: str = "duckduckgo",
        searxng_url: str = None,
        timeout: int = 10,
        max_results: int = 5,
    ):
        """
        Initialize web search tool.
        
        Args:
            backend: "duckduckgo" or "searxng"
            searxng_url: URL for SearXNG instance (if using searxng)
            timeout: Request timeout in seconds
            max_results: Maximum results to return
        """
        self.backend = backend
        self.searxng_url = searxng_url
        self.timeout = timeout
        self.max_results = max_results
    
    async def search(self, query: str, num_results: int = None) -> List[SearchResult]:
        """
        Perform web search.
        
        Args:
            query: Search query
            num_results: Number of results (defaults to max_results)
            
        Returns:
            List of SearchResult objects
        """
        num_results = num_results or self.max_results
        
        if self.backend == "searxng" and self.searxng_url:
            return await self._search_searxng(query, num_results)
        else:
            return await self._search_duckduckgo(query, num_results)
    
    async def _search_duckduckgo(self, query: str, num_results: int) -> List[SearchResult]:
        """Search using DuckDuckGo HTML interface."""
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, 
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"DuckDuckGo returned status {resp.status}")
                        return []
                    
                    html = await resp.text()
                    return self._parse_duckduckgo_html(html, num_results)
                    
        except asyncio.TimeoutError:
            logger.error("DuckDuckGo search timeout")
            return []
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return []
    
    def _parse_duckduckgo_html(self, html: str, num_results: int) -> List[SearchResult]:
        """Parse DuckDuckGo HTML results."""
        results = []
        
        try:
            # Simple regex-based parsing (avoids BeautifulSoup dependency)
            import re
            
            # Find result blocks
            result_pattern = re.compile(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>.*?'
                r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>',
                re.DOTALL
            )
            
            # Alternative pattern for snippet
            alt_pattern = re.compile(
                r'<a[^>]*rel="nofollow"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>.*?'
                r'<span[^>]*class="result__snippet[^"]*"[^>]*>([^<]*)',
                re.DOTALL
            )
            
            matches = result_pattern.findall(html)
            if not matches:
                matches = alt_pattern.findall(html)
            
            for url, title, snippet in matches[:num_results]:
                # Clean up
                title = self._clean_text(title)
                snippet = self._clean_text(snippet)
                
                if title and url:
                    results.append(SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source="duckduckgo"
                    ))
            
            # Fallback: simpler extraction
            if not results:
                link_pattern = re.compile(r'<a[^>]*href="(https?://[^"]+)"[^>]*>([^<]+)</a>')
                for url, title in link_pattern.findall(html)[:num_results]:
                    if 'duckduckgo.com' not in url:
                        results.append(SearchResult(
                            title=self._clean_text(title),
                            url=url,
                            snippet="",
                            source="duckduckgo"
                        ))
            
        except Exception as e:
            logger.error(f"Error parsing DuckDuckGo results: {e}")
        
        return results
    
    async def _search_searxng(self, query: str, num_results: int) -> List[SearchResult]:
        """Search using SearXNG instance."""
        url = f"{self.searxng_url}/search"
        
        params = {
            "q": query,
            "format": "json",
            "engines": "google,bing,duckduckgo",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"SearXNG returned status {resp.status}")
                        return []
                    
                    data = await resp.json()
                    return self._parse_searxng_results(data, num_results)
                    
        except asyncio.TimeoutError:
            logger.error("SearXNG search timeout")
            return []
        except Exception as e:
            logger.error(f"SearXNG search error: {e}")
            return []
    
    def _parse_searxng_results(self, data: Dict, num_results: int) -> List[SearchResult]:
        """Parse SearXNG JSON results."""
        results = []
        
        for item in data.get("results", [])[:num_results]:
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                source=item.get("engine", "searxng")
            ))
        
        return results
    
    def _clean_text(self, text: str) -> str:
        """Clean HTML entities and whitespace."""
        import html
        text = html.unescape(text)
        text = ' '.join(text.split())
        return text.strip()
    
    def get_schema(self) -> Dict:
        """Get tool schema for LLM."""
        return {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for information. Use when you need current information not in your training data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results (1-10)",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            }
        }


# Tool handler for ToolExecutor
async def handle_web_search(args: Dict) -> str:
    """Handle web_search tool call."""
    query = args.get("query", "")
    num_results = args.get("num_results", 5)
    
    if not query:
        return "Error: No search query provided"
    
    tool = WebSearchTool()
    results = await tool.search(query, num_results)
    
    if not results:
        return f"No results found for: {query}"
    
    # Format results
    lines = [f"Web search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.title}")
        lines.append(f"   URL: {r.url}")
        if r.snippet:
            lines.append(f"   {r.snippet[:200]}...")
        lines.append("")
    
    return "\n".join(lines)
