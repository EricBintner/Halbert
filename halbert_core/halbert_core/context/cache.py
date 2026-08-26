# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Context Cache

Caches assembled context to avoid redundant retrieval.
Based on research5.md Part 1.1.
"""

from __future__ import annotations
import time
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List
from collections import OrderedDict

logger = logging.getLogger('halbert.context.cache')


@dataclass
class CacheEntry:
    """A cached context entry."""
    key: str
    content: str
    sources: List[Dict]
    total_tokens: int
    created_at: float
    last_accessed: float
    access_count: int = 0
    ttl_seconds: float = 300  # 5 minutes default
    
    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() > self.created_at + self.ttl_seconds
    
    @property
    def age_seconds(self) -> float:
        """Get age in seconds."""
        return time.time() - self.created_at


class ContextCache:
    """
    LRU cache for assembled context.
    
    Features:
    - Query-based caching with semantic hashing
    - TTL expiration
    - LRU eviction
    - Hit/miss statistics
    """
    
    def __init__(
        self,
        max_size: int = 100,
        default_ttl: float = 300,
        max_memory_mb: float = 50
    ):
        """
        Initialize context cache.
        
        Args:
            max_size: Maximum number of entries
            default_ttl: Default TTL in seconds
            max_memory_mb: Maximum memory usage in MB
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.max_memory_bytes = int(max_memory_mb * 1024 * 1024)
        
        # LRU cache using OrderedDict
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        
        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
    
    def get(self, query: str, context_hash: str = None) -> Optional[CacheEntry]:
        """
        Get cached context for a query.
        
        Args:
            query: User query
            context_hash: Optional hash of additional context
            
        Returns:
            CacheEntry if found and valid, None otherwise
        """
        key = self._make_key(query, context_hash)
        
        if key not in self._cache:
            self._misses += 1
            return None
        
        entry = self._cache[key]
        
        # Check expiration
        if entry.is_expired:
            self._remove(key)
            self._misses += 1
            return None
        
        # Update access
        entry.last_accessed = time.time()
        entry.access_count += 1
        
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        
        self._hits += 1
        logger.debug(f"Cache hit for: {query[:30]}...")
        
        return entry
    
    def put(
        self,
        query: str,
        content: str,
        sources: List[Dict],
        total_tokens: int,
        context_hash: str = None,
        ttl: float = None
    ) -> str:
        """
        Cache assembled context.
        
        Args:
            query: User query
            content: Assembled content
            sources: Source metadata
            total_tokens: Token count
            context_hash: Optional context hash
            ttl: Optional custom TTL
            
        Returns:
            Cache key
        """
        key = self._make_key(query, context_hash)
        
        # Check if we need to evict
        self._evict_if_needed(len(content))
        
        now = time.time()
        entry = CacheEntry(
            key=key,
            content=content,
            sources=sources,
            total_tokens=total_tokens,
            created_at=now,
            last_accessed=now,
            ttl_seconds=ttl or self.default_ttl
        )
        
        self._cache[key] = entry
        self._cache.move_to_end(key)
        
        logger.debug(f"Cached: {query[:30]}... ({total_tokens} tokens)")
        
        return key
    
    def invalidate(self, query: str = None, pattern: str = None):
        """
        Invalidate cache entries.
        
        Args:
            query: Specific query to invalidate
            pattern: Pattern to match (substring)
        """
        if query:
            key = self._make_key(query)
            if key in self._cache:
                self._remove(key)
        elif pattern:
            to_remove = [
                k for k, v in self._cache.items()
                if pattern.lower() in v.content.lower()
            ]
            for key in to_remove:
                self._remove(key)
    
    def clear(self):
        """Clear all cache entries."""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cleared {count} cache entries")
    
    def cleanup(self):
        """Remove expired entries."""
        expired = [k for k, v in self._cache.items() if v.is_expired]
        for key in expired:
            self._remove(key)
        
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired entries")
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        
        return {
            "entries": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "evictions": self._evictions,
            "memory_estimate_kb": self._estimate_memory() / 1024
        }
    
    def _make_key(self, query: str, context_hash: str = None) -> str:
        """Generate cache key from query."""
        # Normalize query
        normalized = query.lower().strip()
        
        # Add context hash if provided
        if context_hash:
            normalized += f":{context_hash}"
        
        # Hash for shorter key
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def _remove(self, key: str):
        """Remove entry by key."""
        if key in self._cache:
            del self._cache[key]
    
    def _evict_if_needed(self, new_content_size: int):
        """Evict entries if over limits."""
        # Check count limit
        while len(self._cache) >= self.max_size:
            self._evict_lru()
        
        # Check memory limit
        while self._estimate_memory() + new_content_size > self.max_memory_bytes:
            if not self._cache:
                break
            self._evict_lru()
    
    def _evict_lru(self):
        """Evict least recently used entry."""
        if self._cache:
            # First item is LRU
            key = next(iter(self._cache))
            self._remove(key)
            self._evictions += 1
    
    def _estimate_memory(self) -> int:
        """Estimate memory usage in bytes."""
        return sum(len(v.content) for v in self._cache.values())


class SemanticCache(ContextCache):
    """
    Context cache with semantic similarity matching.
    
    Falls back to similar queries if exact match not found.
    """
    
    def __init__(
        self,
        embedding_service=None,
        similarity_threshold: float = 0.85,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.embeddings = embedding_service
        self.similarity_threshold = similarity_threshold
        self._query_embeddings: Dict[str, List[float]] = {}
    
    async def get_semantic(self, query: str) -> Optional[CacheEntry]:
        """
        Get cached context using semantic similarity.
        
        Falls back to similar queries if exact match not found.
        """
        # Try exact match first
        entry = self.get(query)
        if entry:
            return entry
        
        # If no embeddings service, can't do semantic matching
        if not self.embeddings:
            return None
        
        # Get query embedding
        try:
            query_emb = await self._get_embedding(query)
        except Exception as e:
            logger.warning(f"Failed to get embedding: {e}")
            return None
        
        # Find most similar cached query
        best_match = None
        best_score = 0.0
        
        for key, entry in self._cache.items():
            if entry.is_expired:
                continue
            
            if key in self._query_embeddings:
                cached_emb = self._query_embeddings[key]
                similarity = self._cosine_similarity(query_emb, cached_emb)
                
                if similarity > best_score and similarity >= self.similarity_threshold:
                    best_score = similarity
                    best_match = entry
        
        if best_match:
            logger.debug(f"Semantic cache hit (similarity={best_score:.2f})")
            self._hits += 1
            return best_match
        
        return None
    
    async def put_semantic(self, query: str, **kwargs) -> str:
        """Cache with semantic indexing."""
        key = self.put(query, **kwargs)
        
        # Store embedding for semantic matching
        if self.embeddings:
            try:
                emb = await self._get_embedding(query)
                self._query_embeddings[key] = emb
            except Exception as e:
                logger.warning(f"Failed to store embedding: {e}")
        
        return key
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text."""
        if hasattr(self.embeddings, 'embed'):
            return await self.embeddings.embed(text)
        elif hasattr(self.embeddings, 'encode'):
            return self.embeddings.encode(text).tolist()
        raise ValueError("Embedding service has no embed/encode method")
    
    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity."""
        import math
        
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot / (norm_a * norm_b)


# Global cache instance
_context_cache: Optional[ContextCache] = None


def get_context_cache() -> ContextCache:
    """Get global context cache."""
    global _context_cache
    if _context_cache is None:
        _context_cache = ContextCache()
    return _context_cache
