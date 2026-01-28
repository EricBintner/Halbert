"""
Context Prioritizer

Intelligent prioritization of context items within token budget.
Based on research5.md Part 1.1.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

logger = logging.getLogger('halbert.context.prioritizer')


class ContextSource(Enum):
    """Sources of context items."""
    CONVERSATION = "conversation"
    RAG = "rag"
    MEMORY = "memory"
    DISCOVERY = "discovery"
    OBSERVATION = "observation"
    FILE = "file"
    WEB = "web"


@dataclass
class ContextItem:
    """A single context item with metadata for prioritization."""
    content: str
    source: ContextSource
    relevance: float = 0.5
    recency: float = 0.5
    importance: float = 0.5
    tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def priority_score(self) -> float:
        """Calculate priority score for ranking."""
        # Weighted combination of factors
        return (
            self.relevance * 0.4 +
            self.recency * 0.3 +
            self.importance * 0.3
        )
    
    @property
    def efficiency(self) -> float:
        """Score per token (higher is better)."""
        if self.tokens <= 0:
            return self.priority_score
        return self.priority_score / (self.tokens / 100)


class ContextPrioritizer:
    """
    Prioritizes context items within a token budget.
    
    Uses multiple signals:
    - Relevance to query
    - Recency of information
    - Source importance weights
    - Token efficiency
    """
    
    # Default source weights
    SOURCE_WEIGHTS = {
        ContextSource.CONVERSATION: 1.0,
        ContextSource.RAG: 0.8,
        ContextSource.MEMORY: 0.7,
        ContextSource.DISCOVERY: 0.6,
        ContextSource.OBSERVATION: 0.9,
        ContextSource.FILE: 0.85,
        ContextSource.WEB: 0.5,
    }
    
    def __init__(
        self,
        token_counter=None,
        source_weights: Dict[ContextSource, float] = None
    ):
        """
        Initialize prioritizer.
        
        Args:
            token_counter: Token counter instance
            source_weights: Custom source weights
        """
        self.token_counter = token_counter
        self.source_weights = source_weights or self.SOURCE_WEIGHTS
    
    def prioritize(
        self,
        items: List[ContextItem],
        max_tokens: int,
        min_items: int = 1,
        max_items: int = 20
    ) -> List[ContextItem]:
        """
        Select and order context items within budget.
        
        Args:
            items: All candidate items
            max_tokens: Token budget
            min_items: Minimum items to include
            max_items: Maximum items to include
            
        Returns:
            Prioritized list of items within budget
        """
        if not items:
            return []
        
        # Calculate tokens if not set
        for item in items:
            if item.tokens <= 0 and self.token_counter:
                item.tokens = self.token_counter.count(item.content)
        
        # Apply source weights to importance
        for item in items:
            weight = self.source_weights.get(item.source, 0.5)
            item.importance *= weight
        
        # Sort by priority score
        sorted_items = sorted(items, key=lambda x: x.priority_score, reverse=True)
        
        # Select items within budget
        selected = []
        total_tokens = 0
        
        for item in sorted_items:
            if len(selected) >= max_items:
                break
            
            if total_tokens + item.tokens <= max_tokens:
                selected.append(item)
                total_tokens += item.tokens
            elif len(selected) < min_items:
                # Force include if below minimum
                selected.append(item)
                total_tokens += item.tokens
        
        return selected
    
    def prioritize_by_efficiency(
        self,
        items: List[ContextItem],
        max_tokens: int
    ) -> List[ContextItem]:
        """
        Prioritize by information density (score per token).
        
        Useful when token budget is very tight.
        """
        if not items:
            return []
        
        # Calculate tokens
        for item in items:
            if item.tokens <= 0 and self.token_counter:
                item.tokens = self.token_counter.count(item.content)
        
        # Sort by efficiency
        sorted_items = sorted(items, key=lambda x: x.efficiency, reverse=True)
        
        selected = []
        total_tokens = 0
        
        for item in sorted_items:
            if total_tokens + item.tokens <= max_tokens:
                selected.append(item)
                total_tokens += item.tokens
        
        # Re-sort by priority for final order
        return sorted(selected, key=lambda x: x.priority_score, reverse=True)
    
    def balance_sources(
        self,
        items: List[ContextItem],
        max_tokens: int,
        source_quotas: Dict[ContextSource, float] = None
    ) -> List[ContextItem]:
        """
        Prioritize while balancing representation from each source.
        
        Args:
            items: All candidate items
            max_tokens: Token budget
            source_quotas: Fraction of budget per source (should sum to 1)
        """
        if not items:
            return []
        
        # Default quotas
        if source_quotas is None:
            source_quotas = {
                ContextSource.CONVERSATION: 0.25,
                ContextSource.RAG: 0.30,
                ContextSource.MEMORY: 0.15,
                ContextSource.DISCOVERY: 0.15,
                ContextSource.OBSERVATION: 0.10,
                ContextSource.FILE: 0.05,
            }
        
        # Group by source
        by_source: Dict[ContextSource, List[ContextItem]] = {}
        for item in items:
            if item.source not in by_source:
                by_source[item.source] = []
            by_source[item.source].append(item)
        
        # Sort each group
        for source in by_source:
            by_source[source].sort(key=lambda x: x.priority_score, reverse=True)
        
        # Allocate budget and select
        selected = []
        
        for source, quota in source_quotas.items():
            if source not in by_source:
                continue
            
            source_budget = int(max_tokens * quota)
            source_tokens = 0
            
            for item in by_source[source]:
                if item.tokens <= 0 and self.token_counter:
                    item.tokens = self.token_counter.count(item.content)
                
                if source_tokens + item.tokens <= source_budget:
                    selected.append(item)
                    source_tokens += item.tokens
        
        # Fill remaining budget with best remaining items
        remaining_budget = max_tokens - sum(i.tokens for i in selected)
        if remaining_budget > 0:
            used_ids = {id(i) for i in selected}
            remaining = [i for i in items if id(i) not in used_ids]
            remaining.sort(key=lambda x: x.priority_score, reverse=True)
            
            for item in remaining:
                if item.tokens <= remaining_budget:
                    selected.append(item)
                    remaining_budget -= item.tokens
        
        return sorted(selected, key=lambda x: x.priority_score, reverse=True)
    
    @staticmethod
    def calculate_relevance(query: str, content: str) -> float:
        """
        Calculate relevance score using simple heuristics.
        
        For production, use embeddings for semantic similarity.
        """
        query_words = set(query.lower().split())
        content_words = set(content.lower().split())
        
        if not query_words:
            return 0.5
        
        overlap = len(query_words & content_words)
        return min(1.0, overlap / len(query_words))
    
    @staticmethod
    def calculate_recency(timestamp: float, now: float = None) -> float:
        """
        Calculate recency score based on age.
        
        Args:
            timestamp: Item timestamp
            now: Current time (defaults to time.time())
            
        Returns:
            Recency score 0-1 (higher is more recent)
        """
        import time
        now = now or time.time()
        
        age_hours = (now - timestamp) / 3600
        
        if age_hours < 1:
            return 1.0
        elif age_hours < 24:
            return 0.9
        elif age_hours < 168:  # 1 week
            return 0.7
        elif age_hours < 720:  # 30 days
            return 0.5
        else:
            return 0.3
