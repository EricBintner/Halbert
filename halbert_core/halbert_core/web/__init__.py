"""
Web search and grounding module for Halbert.

Provides web search capabilities using SearXNG public instances.
"""

from .search import WebSearch, SearchResult

__all__ = ["WebSearch", "SearchResult"]
