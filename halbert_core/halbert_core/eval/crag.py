# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
CRAG (Corrective RAG) Evaluator

Evaluates retrieved documents and decides if they're sufficient to answer
the query, or if corrective retrieval is needed.

Based on research4.md Part 11: CRAG (arXiv:2401.15884)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Optional, Any, TYPE_CHECKING
from enum import Enum
import logging
import re
import time

logger = logging.getLogger('halbert.eval.crag')


class CRAGAction(Enum):
    """Actions the CRAG evaluator can recommend."""
    CORRECT = "CORRECT"       # Documents are sufficient, proceed to response
    INCORRECT = "INCORRECT"   # Documents are not relevant, need different approach
    AMBIGUOUS = "AMBIGUOUS"   # Partially relevant, may need more retrieval


@dataclass
class CRAGResult:
    """Result of CRAG evaluation."""
    action: CRAGAction
    confidence: float  # 0.0 to 1.0
    reasoning: str
    should_retrieve_more: bool
    fallback_strategy: Optional[str] = None
    
    # Component scores
    relevance_score: float = 0.0
    completeness_score: float = 0.0
    freshness_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "should_retrieve_more": self.should_retrieve_more,
            "fallback_strategy": self.fallback_strategy,
            "relevance_score": self.relevance_score,
            "completeness_score": self.completeness_score,
            "freshness_score": self.freshness_score,
        }


class CRAGEvaluator:
    """
    Corrective RAG evaluator.
    
    Evaluates retrieved documents and decides:
    - CORRECT: Documents are sufficient to answer the query
    - INCORRECT: Documents are not relevant, need different retrieval
    - AMBIGUOUS: Partially relevant, may need supplemental retrieval
    
    The evaluator uses:
    1. Semantic similarity between query and documents
    2. LLM-based completeness assessment
    3. Document freshness (if timestamps available)
    """
    
    # Thresholds for action determination
    CORRECT_THRESHOLD = 0.7
    INCORRECT_THRESHOLD = 0.3
    
    # Weights for combining scores
    RELEVANCE_WEIGHT = 0.4
    COMPLETENESS_WEIGHT = 0.4
    FRESHNESS_WEIGHT = 0.2
    
    def __init__(
        self,
        llm_client = None,
        embedding_service = None,
        correct_threshold: float = None,
        incorrect_threshold: float = None,
    ):
        """
        Initialize the CRAG evaluator.
        
        Args:
            llm_client: Client for LLM calls (for completeness assessment)
            embedding_service: Service for computing embeddings
            correct_threshold: Override threshold for CORRECT action
            incorrect_threshold: Override threshold for INCORRECT action
        """
        self.llm = llm_client
        self.embeddings = embedding_service
        
        if correct_threshold is not None:
            self.CORRECT_THRESHOLD = correct_threshold
        if incorrect_threshold is not None:
            self.INCORRECT_THRESHOLD = incorrect_threshold
    
    async def evaluate(
        self,
        query: str,
        documents: List[Dict],
        observations: List[str] = None,
        model_override: str = None,
        tier_override: str = None,
    ) -> CRAGResult:
        """
        Evaluate if documents can answer the query.
        
        Args:
            query: The user's query
            documents: Retrieved documents with 'content' field
            observations: Previous observations from tool execution
            model_override: Model pinned for this turn. Forwarded so a pin
                also governs CRAG's own LLM call — this evaluator shares the
                caller's LLM adapter, so without it a pinned cheap model
                would still let CRAG escalate to the specialist.
            tier_override: Tier pinned for this turn, same reasoning.
            
        Returns:
            CRAGResult with action recommendation
        """
        if not documents:
            logger.debug("CRAG: No documents to evaluate")
            return CRAGResult(
                action=CRAGAction.INCORRECT,
                confidence=0.0,
                reasoning="No documents retrieved",
                should_retrieve_more=True,
                fallback_strategy="expand_query"
            )
        
        # Score each document for relevance
        relevance_scores = []
        for doc in documents:
            score = await self._score_relevance(query, doc)
            relevance_scores.append(score)
        
        # Aggregate relevance
        relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0
        
        # Assess completeness (can documents answer the query?)
        completeness = await self._assess_completeness(
            query, documents, observations, model_override, tier_override
        )
        
        # Assess freshness
        freshness = self._assess_freshness(documents)
        
        # Weighted combination
        confidence = (
            relevance * self.RELEVANCE_WEIGHT +
            completeness * self.COMPLETENESS_WEIGHT +
            freshness * self.FRESHNESS_WEIGHT
        )
        
        # Determine action
        if confidence >= self.CORRECT_THRESHOLD:
            action = CRAGAction.CORRECT
            reasoning = f"High confidence ({confidence:.2f}): documents are relevant and complete"
            should_retrieve_more = False
            fallback = None
        elif confidence <= self.INCORRECT_THRESHOLD:
            action = CRAGAction.INCORRECT
            reasoning = f"Low confidence ({confidence:.2f}): documents not sufficiently relevant"
            should_retrieve_more = True
            # Choose fallback based on what's lacking
            if relevance < 0.2:
                fallback = "web_search"  # Try external search
            elif completeness < 0.3:
                fallback = "expand_query"  # Broaden the search
            else:
                fallback = "refine_query"  # More specific search
        else:
            action = CRAGAction.AMBIGUOUS
            reasoning = f"Medium confidence ({confidence:.2f}): documents partially relevant"
            should_retrieve_more = True
            fallback = "supplement"  # Add more context
        
        logger.info(
            f"CRAG evaluation: action={action.value}, confidence={confidence:.2f}, "
            f"relevance={relevance:.2f}, completeness={completeness:.2f}, freshness={freshness:.2f}"
        )
        
        return CRAGResult(
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            should_retrieve_more=should_retrieve_more,
            fallback_strategy=fallback,
            relevance_score=relevance,
            completeness_score=completeness,
            freshness_score=freshness,
        )
    
    async def _score_relevance(self, query: str, doc: Dict) -> float:
        """
        Score document relevance to query.
        
        Uses embeddings if available, otherwise keyword matching.
        """
        content = doc.get("content", "")
        if not isinstance(content, str) or not content:
            return 0.0
        
        # Truncate for efficiency
        content = content[:2000]
        
        # The retriever's own similarity score (SourcePrep cosine, carried in
        # metadata by the SEARCHING state) is the strongest signal we have
        # without an embedding service; keyword overlap can only lift it.
        retriever_score = self._retriever_score(doc)
        
        if self.embeddings:
            try:
                # Semantic similarity via embeddings
                query_emb = await self.embeddings.embed(query)
                doc_emb = await self.embeddings.embed(content)
                return max(retriever_score, self._cosine_similarity(query_emb, doc_emb))
            except Exception as e:
                logger.warning(f"Embedding failed, falling back to keyword: {e}")
        
        # Fallback: keyword overlap
        return max(retriever_score, self._keyword_similarity(query, content))
    
    @staticmethod
    def _retriever_score(doc: Dict) -> float:
        """Retriever similarity score from the doc or its metadata, clamped to 0-1."""
        raw = doc.get("score")
        if raw is None:
            meta = doc.get("metadata")
            if isinstance(meta, dict):
                raw = meta.get("score", meta.get("relevance"))
        try:
            score = float(raw)
        except (TypeError, ValueError):
            return 0.0
        if score != score:  # NaN
            return 0.0
        return min(1.0, max(0.0, score))
    
    async def _assess_completeness(
        self,
        query: str,
        documents: List[Dict],
        observations: List[str] = None,
        model_override: str = None,
        tier_override: str = None,
    ) -> float:
        """
        Assess if documents fully answer the query.
        
        Uses LLM if available, otherwise heuristic assessment.
        """
        if self.llm:
            try:
                return await self._llm_completeness_check(
                    query, documents, observations, model_override, tier_override
                )
            except Exception as e:
                logger.warning(f"LLM completeness check failed: {e}")
        
        # Fallback: heuristic based on content length and keyword coverage
        return self._heuristic_completeness(query, documents)
    
    async def _llm_completeness_check(
        self,
        query: str,
        documents: List[Dict],
        observations: List[str] = None,
        model_override: str = None,
        tier_override: str = None,
    ) -> float:
        """Use LLM to assess completeness."""
        # Build document summaries
        doc_summaries = "\n".join([
            f"- {doc.get('content', '')[:300]}..."
            for doc in documents[:5]
        ])
        
        obs_text = "\n".join(observations or []) or "(none)"
        
        prompt = f"""Evaluate if these documents can fully answer the question.

Question: {query}

Documents:
{doc_summaries}

Observations from tools:
{obs_text}

Rate completeness from 0.0 to 1.0:
- 1.0 = Documents fully answer the question
- 0.7 = Documents mostly answer, minor gaps
- 0.5 = Documents partially answer
- 0.3 = Documents barely relevant
- 0.0 = Documents don't help at all

Reply with just the number (e.g., "0.7")."""

        response = await self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model_override=model_override,
            tier_override=tier_override,
        )
        
        content = response.content if hasattr(response, 'content') else str(response)
        score = self._parse_completeness(content)
        logger.debug(
            "CRAG completeness raw reply (parsed=%.2f): %r",
            score, str(content)[:200],
        )
        return score
    
    _THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL | re.IGNORECASE)
    _PERCENT_RE = re.compile(r'(\d{1,3}(?:\.\d+)?)\s*%')
    # "0.8/1.0", "3 of 5", "0.5 out of 1.0" -> numerator / denominator
    _FRACTION_RE = re.compile(
        r'(\d+(?:\.\d+)?)\s*(?:/|\bout\s+of\b|\bof\b)\s*(\d+(?:\.\d+)?)',
        re.IGNORECASE,
    )
    _NUMBER_RE = re.compile(r'(?<![\w.])(\d+(?:\.\d*)?|\.\d+)(?![\w])')
    
    @classmethod
    def _parse_completeness(cls, content: Any) -> float:
        """Extract a 0-1 completeness score from an LLM reply.
        
        Models rarely reply with *just* the number: they wrap it in markdown,
        prefix it with reasoning or a ``<think>`` block, write ``0.8/1.0`` or
        ``80%``. The previous parser took the FIRST digit in the text, which
        turned "1 of 3 topics ... 0.3" into 1.0 and "0.\n" into 0.0.
        
        Strategy: strip think blocks, then take the LAST candidate that is a
        plausible score (percentage, fraction, or 0-1 float), since the final
        number is the model's answer. Unparseable -> neutral 0.5.
        """
        if content is None:
            return 0.5
        text = str(content)
        text = cls._THINK_RE.sub(' ', text)
        # An unterminated <think> block: keep only what follows the tag.
        if '<think>' in text.lower():
            idx = text.lower().rfind('<think>')
            text = text[idx + len('<think>'):]
        text = text.strip()
        if not text:
            return 0.5
        
        candidates: List[tuple] = []  # (position, score)
        
        for m in cls._PERCENT_RE.finditer(text):
            candidates.append((m.start(), float(m.group(1)) / 100.0))
        
        fraction_spans = []
        for m in cls._FRACTION_RE.finditer(text):
            num, den = float(m.group(1)), float(m.group(2))
            if den > 0 and num <= den:
                fraction_spans.append((m.start(), m.end()))
                candidates.append((m.start(), num / den))
        
        for m in cls._NUMBER_RE.finditer(text):
            if any(a <= m.start() < b for a, b in fraction_spans):
                continue
            if text[m.end():m.end() + 1] == '%':
                continue
            try:
                value = float(m.group(1))
            except ValueError:
                continue
            if 0.0 <= value <= 1.0:
                candidates.append((m.start(), value))
        
        if not candidates:
            return 0.5
        candidates.sort(key=lambda c: c[0])
        score = candidates[-1][1]
        return min(1.0, max(0.0, score))
    
    def _heuristic_completeness(self, query: str, documents: List[Dict]) -> float:
        """Heuristic completeness based on coverage."""
        if not documents:
            return 0.0
        
        # Extract query keywords
        query_words = self._tokenize(query)
        query_words -= {'the', 'a', 'an', 'is', 'are', 'what', 'how', 'why', 'when', 'where', 'who'}
        
        if not query_words:
            return 0.5
        
        # Check keyword coverage across documents
        all_content = " ".join(
            doc.get("content", "") for doc in documents if isinstance(doc.get("content"), str)
        ).lower()
        
        covered = sum(1 for word in query_words if word in all_content)
        coverage = covered / len(query_words)
        
        # Also consider total content length
        total_length = len(all_content)
        length_score = min(1.0, total_length / 1000)  # Cap at 1000 chars
        
        return (coverage * 0.7 + length_score * 0.3)
    
    def _assess_freshness(self, documents: List[Dict]) -> float:
        """
        Assess document freshness based on timestamps.
        
        Returns 1.0 if no timestamps (assume fresh), otherwise decay based on age.
        """
        now = time.time()
        freshness_scores = []
        
        for doc in documents:
            timestamp = doc.get("timestamp") or doc.get("created_at")
            if timestamp:
                if isinstance(timestamp, str):
                    # Try to parse ISO format
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        timestamp = dt.timestamp()
                    except:
                        timestamp = now  # Assume current if can't parse
                
                age_days = (now - timestamp) / 86400
                
                # Decay function: fresh within 7 days, gradual decay after
                if age_days < 7:
                    score = 1.0
                elif age_days < 30:
                    score = 0.9 - (age_days - 7) * 0.01
                elif age_days < 90:
                    score = 0.7 - (age_days - 30) * 0.005
                elif age_days < 365:
                    score = 0.4 - (age_days - 90) * 0.001
                else:
                    score = 0.2
                
                freshness_scores.append(max(0.1, score))
            else:
                freshness_scores.append(0.8)  # No timestamp, assume reasonably fresh
        
        return sum(freshness_scores) / len(freshness_scores) if freshness_scores else 0.8
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        try:
            import numpy as np
            a = np.array(a)
            b = np.array(b)
            
            dot = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            return float(dot / (norm_a * norm_b))
        except ImportError:
            # Fallback without numpy
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            return dot / (norm_a * norm_b)
    
    def _keyword_similarity(self, query: str, content: str) -> float:
        """Simple keyword-based similarity."""
        query_words = self._tokenize(query)
        content_words = self._tokenize(content)
        
        # Remove common words
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                     'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                     'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                     'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                     'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                     'through', 'during', 'before', 'after', 'above', 'below',
                     'between', 'under', 'again', 'further', 'then', 'once',
                     'here', 'there', 'when', 'where', 'why', 'how', 'all',
                     'each', 'few', 'more', 'most', 'other', 'some', 'such',
                     'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
                     'too', 'very', 'just', 'and', 'but', 'if', 'or', 'because',
                     'until', 'while', 'although', 'though', 'what', 'which',
                     'who', 'whom', 'this', 'that', 'these', 'those', 'am',
                     'it', 'its', 'i', 'me', 'my', 'myself', 'we', 'our',
                     'ours', 'ourselves', 'you', 'your', 'yours', 'yourself',
                     'he', 'him', 'his', 'himself', 'she', 'her', 'hers',
                     'herself', 'they', 'them', 'their', 'theirs', 'themselves'}
        
        query_words -= stopwords
        content_words -= stopwords
        
        if not query_words:
            return 0.5
        
        overlap = len(query_words & content_words)
        return overlap / len(query_words)
    
    _TOKEN_RE = re.compile(r'[a-z0-9_]+')
    
    @classmethod
    def _tokenize(cls, text: str) -> set:
        """Lower-case word tokens split on punctuation as well as whitespace.
        
        Retrieved docs contain tokens like ``file:host/etc/ssh/sshd_config`` or
        ``sshd_config.``; a whitespace-only split never matched them against
        the query token ``sshd_config`` (round-1 relevance was exactly 0.0).
        Both the whole whitespace token and its punctuation-split parts are
        kept so exact matches keep working.
        """
        lowered = text.lower()
        tokens = set(lowered.split())
        tokens.update(cls._TOKEN_RE.findall(lowered))
        return tokens
