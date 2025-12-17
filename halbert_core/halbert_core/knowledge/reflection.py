"""
Self-Reflection Module

Sprint 3: Self-RAG inspired reflection before answering.

Implements the ability to:
1. Evaluate retrieved knowledge relevance
2. Estimate confidence in answers
3. Decide when to retrieve more context
4. Provide reasoning traces

Based on Self-RAG paper concepts: reflect on retrieval quality
before generating responses.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .self_knowledge import KnowledgeEntry, KnowledgeType, get_self_knowledge
from .graph import KnowledgeGraph, RelationType, get_knowledge_graph

logger = logging.getLogger(__name__)


class RetrievalDecision(str, Enum):
    """Whether additional retrieval is needed."""
    SUFFICIENT = "sufficient"       # Have enough context
    NEED_MORE = "need_more"         # Should retrieve more
    NO_MATCH = "no_match"           # Query doesn't match our knowledge domain
    AMBIGUOUS = "ambiguous"         # Query is unclear


class ConfidenceLevel(str, Enum):
    """Confidence in the retrieved context."""
    HIGH = "high"           # Strong match, recent knowledge
    MEDIUM = "medium"       # Partial match or older knowledge
    LOW = "low"             # Weak match, may be outdated
    NONE = "none"           # No relevant knowledge found


@dataclass
class RetrievedContext:
    """A piece of retrieved knowledge with scoring."""
    entry: KnowledgeEntry
    relevance_score: float      # 0-1, how relevant to query
    freshness_score: float      # 0-1, how recent
    source_reliability: float   # 0-1, how reliable the source
    combined_score: float = 0.0
    
    def __post_init__(self):
        # Weighted combination
        self.combined_score = (
            self.relevance_score * 0.5 +
            self.freshness_score * 0.3 +
            self.source_reliability * 0.2
        )


@dataclass  
class ReflectionResult:
    """
    Result of self-reflection on a query.
    
    Provides reasoning about what we know and how confident we are.
    """
    query: str
    decision: RetrievalDecision
    confidence: ConfidenceLevel
    retrieved_contexts: List[RetrievedContext]
    reasoning: str                          # Human-readable explanation
    suggested_actions: List[str] = field(default_factory=list)
    graph_context: Optional[Dict] = None    # Related graph nodes
    reflection_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "query": self.query,
            "decision": self.decision.value,
            "confidence": self.confidence.value,
            "contexts": [
                {
                    "id": ctx.entry.id,
                    "subject": ctx.entry.subject,
                    "type": ctx.entry.type.value,
                    "relevance": ctx.relevance_score,
                    "combined_score": ctx.combined_score,
                }
                for ctx in self.retrieved_contexts
            ],
            "reasoning": self.reasoning,
            "suggested_actions": self.suggested_actions,
            "graph_context": self.graph_context,
            "reflection_time_ms": self.reflection_time_ms,
        }
    
    def get_context_string(self, max_entries: int = 5) -> str:
        """Get formatted context string for LLM consumption."""
        if not self.retrieved_contexts:
            return "No relevant self-knowledge found for this query."
        
        lines = [f"[Self-Reflection: {self.confidence.value} confidence]"]
        lines.append(f"Reasoning: {self.reasoning}")
        lines.append("")
        lines.append("Relevant Knowledge:")
        
        for i, ctx in enumerate(self.retrieved_contexts[:max_entries]):
            lines.append(f"  {i+1}. [{ctx.entry.type.value}] {ctx.entry.subject}")
            lines.append(f"     {ctx.entry.content[:200]}...")
            lines.append(f"     (relevance: {ctx.relevance_score:.2f})")
        
        if self.graph_context:
            lines.append("")
            lines.append(f"Related Components: {', '.join(self.graph_context.get('related', []))}")
        
        return "\n".join(lines)


class SelfReflector:
    """
    Self-reflection engine for evaluating knowledge retrieval.
    
    Inspired by Self-RAG: learns to retrieve, generate, and critique.
    """
    
    # Keywords that indicate different query intents
    SYSTEM_KEYWORDS = {
        'hardware', 'cpu', 'memory', 'disk', 'storage', 'network',
        'gpu', 'ram', 'ssd', 'nvme', 'interface', 'device'
    }
    
    IDENTITY_KEYWORDS = {
        'who', 'what', 'name', 'halbert', 'assistant', 'purpose',
        'role', 'identity', 'about', 'yourself'
    }
    
    CONFIG_KEYWORDS = {
        'config', 'configuration', 'setting', 'option', 'why',
        'rationale', 'reason', 'choice', 'decision'
    }
    
    RELATIONSHIP_KEYWORDS = {
        'depends', 'uses', 'connects', 'manages', 'contains',
        'related', 'affects', 'impacts', 'breaks'
    }
    
    def __init__(self):
        self._sk = get_self_knowledge()
        self._graph = get_knowledge_graph()
    
    def reflect(
        self,
        query: str,
        max_contexts: int = 10,
        relevance_threshold: float = 0.1
    ) -> ReflectionResult:
        """
        Reflect on a query before answering.
        
        1. Analyze query intent
        2. Retrieve relevant knowledge
        3. Score relevance and freshness
        4. Decide if we have enough context
        5. Provide reasoning
        
        Args:
            query: The user's question/request
            max_contexts: Maximum contexts to return
            relevance_threshold: Minimum relevance score
        
        Returns:
            ReflectionResult with analysis and recommendations
        """
        import time
        start = time.time()
        
        query_lower = query.lower()
        
        # Step 1: Classify query intent
        intent = self._classify_intent(query_lower)
        
        # Step 2: Retrieve from self-knowledge
        raw_results = self._sk.search(query, k=max_contexts * 2)
        
        # Step 3: Score each result
        scored_contexts = []
        for entry in raw_results:
            relevance = self._score_relevance(query_lower, entry)
            freshness = self._score_freshness(entry)
            reliability = self._score_source_reliability(entry)
            
            if relevance >= relevance_threshold:
                scored_contexts.append(RetrievedContext(
                    entry=entry,
                    relevance_score=relevance,
                    freshness_score=freshness,
                    source_reliability=reliability,
                ))
        
        # Sort by combined score
        scored_contexts.sort(key=lambda x: x.combined_score, reverse=True)
        scored_contexts = scored_contexts[:max_contexts]
        
        # Step 4: Get graph context if query involves relationships
        graph_context = None
        if any(kw in query_lower for kw in self.RELATIONSHIP_KEYWORDS):
            graph_context = self._get_graph_context(query_lower)
        
        # Step 5: Decide and reason
        decision, confidence, reasoning = self._make_decision(
            query_lower, intent, scored_contexts, graph_context
        )
        
        # Step 6: Suggest actions if needed
        actions = self._suggest_actions(decision, intent, scored_contexts)
        
        elapsed = (time.time() - start) * 1000
        
        result = ReflectionResult(
            query=query,
            decision=decision,
            confidence=confidence,
            retrieved_contexts=scored_contexts,
            reasoning=reasoning,
            suggested_actions=actions,
            graph_context=graph_context,
            reflection_time_ms=elapsed,
        )
        
        logger.info(f"Reflection complete: {confidence.value} confidence, {len(scored_contexts)} contexts")
        return result
    
    def _classify_intent(self, query: str) -> str:
        """Classify the query intent."""
        query_words = set(query.split())
        
        # Check hardware first (more specific)
        if query_words & self.SYSTEM_KEYWORDS:
            return "hardware"
        if query_words & self.CONFIG_KEYWORDS:
            return "config"
        if query_words & self.RELATIONSHIP_KEYWORDS:
            return "relationship"
        if query_words & self.IDENTITY_KEYWORDS:
            return "identity"
        
        return "general"
    
    def _score_relevance(self, query: str, entry: KnowledgeEntry) -> float:
        """Score how relevant an entry is to the query."""
        score = 0.0
        query_words = set(query.lower().split())
        
        # Subject match
        subject_words = set(entry.subject.lower().split())
        subject_overlap = len(query_words & subject_words) / max(len(query_words), 1)
        score += subject_overlap * 0.4
        
        # Content match
        content_words = set(entry.content.lower().split())
        content_overlap = len(query_words & content_words) / max(len(query_words), 1)
        score += content_overlap * 0.3
        
        # Type bonus based on intent
        if "who" in query or "what" in query:
            if entry.type == KnowledgeType.IDENTITY:
                score += 0.2
        if "why" in query:
            if entry.type == KnowledgeType.CONFIG_RATIONALE:
                score += 0.2
        if any(hw in query for hw in ['cpu', 'memory', 'disk', 'gpu']):
            if entry.type == KnowledgeType.HARDWARE:
                score += 0.2
        
        # Tag match
        if entry.tags:
            tag_overlap = len(query_words & set(t.lower() for t in entry.tags))
            score += tag_overlap * 0.1
        
        return min(score, 1.0)
    
    def _score_freshness(self, entry: KnowledgeEntry) -> float:
        """Score how fresh/recent the entry is."""
        if not entry.created_at:
            return 0.5  # Unknown age
        
        try:
            created = datetime.fromisoformat(entry.created_at.replace('Z', '+00:00'))
            age_days = (datetime.now(created.tzinfo) - created).days
            
            # Decay: 1.0 for today, 0.5 after 30 days, 0.2 after 90 days
            if age_days <= 1:
                return 1.0
            elif age_days <= 7:
                return 0.9
            elif age_days <= 30:
                return 0.7
            elif age_days <= 90:
                return 0.5
            else:
                return 0.3
        except Exception:
            return 0.5
    
    def _score_source_reliability(self, entry: KnowledgeEntry) -> float:
        """Score the reliability of the knowledge source."""
        source = entry.source.lower() if entry.source else ""
        
        # Bootstrap/system sources are most reliable
        if source in ('bootstrap', 'system', 'deep_scan', 'profile'):
            return 1.0
        
        # User-taught is reliable
        if source in ('user', 'teach', 'user_taught'):
            return 0.9
        
        # Config learning is good
        if source in ('config', 'config_learning'):
            return 0.8
        
        # Inferred is less certain
        if source in ('inferred', 'auto'):
            return 0.6
        
        return 0.7  # Default
    
    def _get_graph_context(self, query: str) -> Optional[Dict]:
        """Extract relevant graph context for relationship queries."""
        # Find mentioned nodes
        all_nodes = self._graph.get_all_nodes()
        mentioned = []
        
        for node in all_nodes:
            # Check if node name appears in query
            node_name = node.split(':')[-1] if ':' in node else node
            if node_name.lower() in query:
                mentioned.append(node)
        
        if not mentioned:
            return None
        
        # Get relationships for mentioned nodes
        related = set()
        for node in mentioned:
            for rel in self._graph.get_outgoing(node):
                related.add(rel.target)
            for rel in self._graph.get_incoming(node):
                related.add(rel.source)
        
        # If asking about impact/breaks
        impact = None
        if any(w in query for w in ['break', 'fail', 'impact', 'affect']):
            if mentioned:
                impact = self._graph.impact_analysis(mentioned[0])
        
        return {
            "mentioned_nodes": mentioned,
            "related": list(related - set(mentioned)),
            "impact": impact,
        }
    
    # Keywords that indicate the query is about self/system knowledge
    SELF_KNOWLEDGE_KEYWORDS = {
        'halbert', 'system', 'config', 'hardware', 'host', 'hostname',
        'cpu', 'memory', 'disk', 'storage', 'network', 'service',
        'docker', 'container', 'linux', 'ubuntu', 'kernel', 'os',
        'user', 'you', 'your', 'yourself', 'this', 'machine', 'server',
        'running', 'installed', 'configured', 'setup', 'purpose', 'role'
    }
    
    # Keywords that indicate external/out-of-domain queries
    EXTERNAL_KEYWORDS = {
        'weather', 'stock', 'price', 'news', 'sports', 'movie',
        'restaurant', 'recipe', 'translate', 'currency', 'flight',
        'celebrity', 'politics', 'election', 'covid', 'pandemic'
    }
    
    def _make_decision(
        self,
        query: str,
        intent: str,
        contexts: List[RetrievedContext],
        graph_context: Optional[Dict]
    ) -> Tuple[RetrievalDecision, ConfidenceLevel, str]:
        """Make a decision about retrieval sufficiency."""
        
        query_lower = query.lower()
        # Strip punctuation for word matching
        import re
        query_words = set(re.findall(r'\b\w+\b', query_lower))
        
        # First: Check if query is clearly out-of-domain
        if query_words & self.EXTERNAL_KEYWORDS:
            return (
                RetrievalDecision.NO_MATCH,
                ConfidenceLevel.NONE,
                "This query is about external information outside my self-knowledge domain."
            )
        
        # Check if query has NO self-knowledge keywords AND no contexts found
        has_self_keywords = bool(query_words & self.SELF_KNOWLEDGE_KEYWORDS)
        
        if not contexts:
            # Check if it's a self-knowledge query at all
            if has_self_keywords:
                return (
                    RetrievalDecision.NEED_MORE,
                    ConfidenceLevel.NONE,
                    "No matching knowledge found. May need to scan system or learn new information."
                )
            else:
                return (
                    RetrievalDecision.NO_MATCH,
                    ConfidenceLevel.NONE,
                    "Query doesn't appear to be about self-knowledge or system configuration."
                )
        
        # Calculate aggregate scores
        avg_relevance = sum(c.relevance_score for c in contexts) / len(contexts)
        avg_combined = sum(c.combined_score for c in contexts) / len(contexts)
        top_score = contexts[0].combined_score if contexts else 0
        
        # High confidence: strong top match and good average
        if top_score >= 0.7 and avg_relevance >= 0.5:
            return (
                RetrievalDecision.SUFFICIENT,
                ConfidenceLevel.HIGH,
                f"Found {len(contexts)} highly relevant entries. Top match score: {top_score:.2f}"
            )
        
        # Medium confidence: decent matches
        if top_score >= 0.4 or len(contexts) >= 3:
            reasoning = f"Found {len(contexts)} partially relevant entries."
            if graph_context and graph_context.get('related'):
                reasoning += f" Graph shows {len(graph_context['related'])} related components."
            return (
                RetrievalDecision.SUFFICIENT,
                ConfidenceLevel.MEDIUM,
                reasoning
            )
        
        # Low confidence: weak matches
        if contexts:
            return (
                RetrievalDecision.NEED_MORE,
                ConfidenceLevel.LOW,
                f"Found {len(contexts)} entries but relevance is low (top: {top_score:.2f}). May need more specific query."
            )
        
        return (
            RetrievalDecision.AMBIGUOUS,
            ConfidenceLevel.LOW,
            "Query is ambiguous. Please be more specific about what system information you need."
        )
    
    def _suggest_actions(
        self,
        decision: RetrievalDecision,
        intent: str,
        contexts: List[RetrievedContext]
    ) -> List[str]:
        """Suggest actions based on reflection."""
        actions = []
        
        if decision == RetrievalDecision.NO_MATCH:
            actions.append("This query may not be about system self-knowledge")
            
        elif decision == RetrievalDecision.NEED_MORE:
            if intent == "hardware":
                actions.append("Consider running a deep system scan to update hardware knowledge")
            elif intent == "config":
                actions.append("Try teaching Halbert about this configuration")
            else:
                actions.append("Try a more specific query")
                
        elif decision == RetrievalDecision.AMBIGUOUS:
            actions.append("Rephrase query to be more specific")
            actions.append("Specify which component or aspect you're asking about")
        
        return actions


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

_reflector_instance: Optional[SelfReflector] = None

def get_reflector() -> SelfReflector:
    """Get the singleton SelfReflector instance."""
    global _reflector_instance
    if _reflector_instance is None:
        _reflector_instance = SelfReflector()
    return _reflector_instance


def reflect_before_answer(query: str, **kwargs) -> ReflectionResult:
    """Convenience function to reflect on a query."""
    return get_reflector().reflect(query, **kwargs)
