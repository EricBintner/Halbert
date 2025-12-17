"""
Self-Reflection Module

Sprint 3: Self-RAG inspired reflection before answering.

Enhanced with research from:
- Self-RAG (ICLR 2024): Reflection tokens for retrieve/critique decisions
- CRAG: Corrective RAG with CORRECT/INCORRECT/AMBIGUOUS decision flow
- Mem0: Quality + freshness + relevance scoring

Implements:
1. Reflection tokens (Retrieve, IsRel, IsSup, IsUse) for decision making
2. CRAG-style corrective evaluation (CORRECT/INCORRECT/AMBIGUOUS)
3. Multi-factor scoring (relevance * 0.6 + quality * 0.3 + freshness * 0.1)
4. Epistemic awareness (knows what it knows vs doesn't know)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .self_knowledge import KnowledgeEntry, KnowledgeType, get_self_knowledge
from .graph import KnowledgeGraph, RelationType, get_knowledge_graph

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Self-RAG Reflection Tokens (Research-based)
# ═══════════════════════════════════════════════════════════════════════════════

class ReflectionToken(str, Enum):
    """
    Self-RAG inspired reflection tokens.
    
    These represent the model's self-assessment at each stage:
    - RETRIEVE: Should we retrieve external knowledge?
    - IS_REL: Is the retrieved content relevant to the query?
    - IS_SUP: Is the response supported by the evidence?
    - IS_USE: Is the response useful/complete?
    """
    RETRIEVE_YES = "[Retrieve:Yes]"      # Retrieval needed
    RETRIEVE_NO = "[Retrieve:No]"        # No retrieval needed (parametric ok)
    IS_REL_YES = "[IsRel:Yes]"           # Retrieved content is relevant
    IS_REL_PARTIAL = "[IsRel:Partial]"   # Partially relevant
    IS_REL_NO = "[IsRel:No]"             # Not relevant
    IS_SUP_FULL = "[IsSup:Full]"         # Fully supported by evidence
    IS_SUP_PARTIAL = "[IsSup:Partial]"   # Partially supported
    IS_SUP_NO = "[IsSup:No]"             # Not supported
    IS_USE_YES = "[IsUse:Yes]"           # Response is useful
    IS_USE_PARTIAL = "[IsUse:Partial]"   # Partially useful
    IS_USE_NO = "[IsUse:No]"             # Not useful


class CRAGAction(str, Enum):
    """
    CRAG-style corrective actions based on retrieval evaluation.
    
    - CORRECT: High confidence, use retrieved docs directly
    - INCORRECT: Low confidence, need external search or more data
    - AMBIGUOUS: Mixed signals, combine internal + external sources
    """
    CORRECT = "correct"         # Retrieval is good, proceed
    INCORRECT = "incorrect"     # Retrieval failed, need fallback
    AMBIGUOUS = "ambiguous"     # Uncertain, combine sources


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
    """
    A piece of retrieved knowledge with CRAG-style scoring.
    
    Scoring formula (from CRAG research):
    combined = 0.6 * relevance + 0.3 * quality + 0.1 * freshness
    """
    entry: KnowledgeEntry
    relevance_score: float      # 0-1, how relevant to query
    freshness_score: float      # 0-1, how recent (CRAG: decay over time)
    source_reliability: float   # 0-1, quality/reliability of source
    combined_score: float = 0.0
    is_relevant: ReflectionToken = ReflectionToken.IS_REL_NO  # Self-RAG token
    
    def __post_init__(self):
        # CRAG-style weighted combination
        # combined = 0.6*similarity + 0.3*quality + 0.1*freshness
        self.combined_score = (
            self.relevance_score * 0.6 +
            self.source_reliability * 0.3 +
            self.freshness_score * 0.1
        )
        
        # Set Self-RAG relevance token
        if self.relevance_score >= 0.5:
            self.is_relevant = ReflectionToken.IS_REL_YES
        elif self.relevance_score >= 0.2:
            self.is_relevant = ReflectionToken.IS_REL_PARTIAL
        else:
            self.is_relevant = ReflectionToken.IS_REL_NO


@dataclass  
class ReflectionResult:
    """
    Result of self-reflection on a query.
    
    Enhanced with Self-RAG tokens and CRAG corrective actions.
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
    
    # Self-RAG reflection tokens
    retrieve_token: ReflectionToken = ReflectionToken.RETRIEVE_YES
    support_token: ReflectionToken = ReflectionToken.IS_SUP_NO
    utility_token: ReflectionToken = ReflectionToken.IS_USE_NO
    
    # CRAG corrective action
    crag_action: CRAGAction = CRAGAction.AMBIGUOUS
    
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
                    "is_relevant": ctx.is_relevant.value,
                }
                for ctx in self.retrieved_contexts
            ],
            "reasoning": self.reasoning,
            "suggested_actions": self.suggested_actions,
            "graph_context": self.graph_context,
            "reflection_time_ms": self.reflection_time_ms,
            # Self-RAG tokens
            "reflection_tokens": {
                "retrieve": self.retrieve_token.value,
                "support": self.support_token.value,
                "utility": self.utility_token.value,
            },
            # CRAG action
            "crag_action": self.crag_action.value,
        }
    
    def get_context_string(self, max_entries: int = 5) -> str:
        """Get formatted context string for LLM consumption."""
        if not self.retrieved_contexts:
            return "No relevant self-knowledge found for this query."
        
        # Include Self-RAG tokens in output for transparency
        lines = [f"[Self-Reflection: {self.confidence.value} confidence]"]
        lines.append(f"Tokens: {self.retrieve_token.value} {self.support_token.value} {self.utility_token.value}")
        lines.append(f"CRAG Action: {self.crag_action.value}")
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
        
        # Step 7: Compute Self-RAG reflection tokens
        retrieve_token, support_token, utility_token = self._compute_reflection_tokens(
            scored_contexts, decision, confidence
        )
        
        # Step 8: Determine CRAG corrective action
        crag_action = self._determine_crag_action(scored_contexts, confidence)
        
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
            retrieve_token=retrieve_token,
            support_token=support_token,
            utility_token=utility_token,
            crag_action=crag_action,
        )
        
        logger.info(f"Reflection complete: {confidence.value} confidence, CRAG={crag_action.value}, {len(scored_contexts)} contexts")
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
    
    def _compute_reflection_tokens(
        self,
        contexts: List[RetrievedContext],
        decision: RetrievalDecision,
        confidence: ConfidenceLevel
    ) -> Tuple[ReflectionToken, ReflectionToken, ReflectionToken]:
        """
        Compute Self-RAG reflection tokens based on retrieval results.
        
        Returns:
            Tuple of (retrieve_token, support_token, utility_token)
        """
        # Retrieve token: Did we need to retrieve?
        if decision == RetrievalDecision.NO_MATCH:
            retrieve_token = ReflectionToken.RETRIEVE_NO
        else:
            retrieve_token = ReflectionToken.RETRIEVE_YES
        
        # Support token: Is response supported by evidence?
        if not contexts:
            support_token = ReflectionToken.IS_SUP_NO
        else:
            # Count how many contexts are relevant
            relevant_count = sum(1 for c in contexts if c.is_relevant == ReflectionToken.IS_REL_YES)
            partial_count = sum(1 for c in contexts if c.is_relevant == ReflectionToken.IS_REL_PARTIAL)
            
            if relevant_count >= 2 or (relevant_count >= 1 and confidence == ConfidenceLevel.HIGH):
                support_token = ReflectionToken.IS_SUP_FULL
            elif relevant_count >= 1 or partial_count >= 2:
                support_token = ReflectionToken.IS_SUP_PARTIAL
            else:
                support_token = ReflectionToken.IS_SUP_NO
        
        # Utility token: Is the response useful?
        if confidence == ConfidenceLevel.HIGH:
            utility_token = ReflectionToken.IS_USE_YES
        elif confidence == ConfidenceLevel.MEDIUM:
            utility_token = ReflectionToken.IS_USE_PARTIAL
        else:
            utility_token = ReflectionToken.IS_USE_NO
        
        return retrieve_token, support_token, utility_token
    
    def _determine_crag_action(
        self,
        contexts: List[RetrievedContext],
        confidence: ConfidenceLevel
    ) -> CRAGAction:
        """
        Determine CRAG corrective action based on retrieval quality.
        
        CRAG Decision Flow:
        - CORRECT: High relevance scores → use retrieved docs directly
        - INCORRECT: Low relevance → need external search or more data
        - AMBIGUOUS: Mixed signals → combine internal + external sources
        """
        if not contexts:
            return CRAGAction.INCORRECT
        
        # Calculate aggregate quality metrics
        avg_combined = sum(c.combined_score for c in contexts) / len(contexts)
        top_score = contexts[0].combined_score
        
        # Count relevance distribution
        highly_relevant = sum(1 for c in contexts if c.relevance_score >= 0.5)
        partially_relevant = sum(1 for c in contexts if 0.2 <= c.relevance_score < 0.5)
        
        # CRAG decision thresholds
        if confidence == ConfidenceLevel.HIGH and top_score >= 0.6:
            return CRAGAction.CORRECT
        elif confidence == ConfidenceLevel.NONE or (top_score < 0.3 and highly_relevant == 0):
            return CRAGAction.INCORRECT
        elif highly_relevant >= 1 or (partially_relevant >= 2 and avg_combined >= 0.4):
            # Mixed signals - some relevant, some not
            if confidence == ConfidenceLevel.MEDIUM:
                return CRAGAction.CORRECT  # Good enough
            return CRAGAction.AMBIGUOUS
        else:
            return CRAGAction.AMBIGUOUS
    
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
