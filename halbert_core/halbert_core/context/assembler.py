"""
Context Assembler

Assembles context from multiple sources within token budget.
Based on research5.md Part 13.
"""

from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, TYPE_CHECKING

from .tokens import TokenCounter

if TYPE_CHECKING:
    pass

logger = logging.getLogger('halbert.context.assembler')


@dataclass
class AssembledContext:
    """Context assembled from multiple sources."""
    content: str
    sources: List[Dict[str, Any]]
    total_tokens: int
    truncated: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "sources": self.sources,
            "total_tokens": self.total_tokens,
            "truncated": self.truncated
        }


class ContextAssembler:
    """
    Assembles context from RAG, memory, discovery, and conversation.
    
    Features:
    - Token budget management
    - Priority-based allocation
    - Parallel retrieval
    - Graceful truncation
    
    Based on research4.md Part 20: Context Assembly.
    """
    
    # Default priority weights (higher = more budget)
    DEFAULT_PRIORITIES = {
        "conversation": 1.0,   # Highest priority
        "rag": 0.8,
        "memory": 0.7,
        "discovery": 0.6,
        "observations": 0.5,
    }
    
    def __init__(
        self,
        rag_service=None,
        memory_service=None,
        discovery_service=None,
        token_counter: TokenCounter = None,
        priorities: Dict[str, float] = None,
        clara_provider=None,
    ):
        """
        Initialize the context assembler.
        
        Args:
            rag_service: RAG search service
            memory_service: Memory recall service
            discovery_service: Discovery search service
            token_counter: Token counting utility
            priorities: Custom priority weights
            clara_provider: Optional CLaRa compression provider
        """
        self.rag = rag_service
        self.memory = memory_service
        self.discovery = discovery_service
        self.tokens = token_counter or TokenCounter()
        self.priorities = priorities or self.DEFAULT_PRIORITIES
        self._clara = clara_provider
        self._clara_threshold = 4000  # Compress if context > this many tokens
    
    async def assemble(
        self,
        query: str,
        conversation: List[Dict] = None,
        observations: List[str] = None,
        max_tokens: int = 8000,
        include_sources: List[str] = None,
        use_compression: bool = True,
    ) -> AssembledContext:
        """
        Assemble context within token budget.
        
        Args:
            query: User query for retrieval
            conversation: Conversation history
            observations: Tool execution observations
            max_tokens: Maximum tokens for assembled context
            include_sources: Specific sources to include (default: all)
            
        Returns:
            AssembledContext with combined content
        """
        sources = []
        total_tokens = 0
        truncated = False
        
        # Determine which sources to include
        active_sources = include_sources or list(self.priorities.keys())
        
        # Allocate budget
        budgets = self._allocate_budget(max_tokens, conversation, active_sources)
        
        logger.debug(f"Context budgets: {budgets}")
        
        # 1. Conversation history (highest priority, synchronous)
        if "conversation" in active_sources and conversation:
            conv_content, conv_tokens = self._format_conversation(
                conversation, budgets.get("conversation", 0)
            )
            if conv_content:
                sources.append({
                    "type": "conversation",
                    "content": conv_content,
                    "tokens": conv_tokens,
                    "items": len(conversation)
                })
                total_tokens += conv_tokens
        
        # 2. Parallel retrieval from external sources
        retrieval_tasks = []
        
        logger.info(f"Context assembly: rag={self.rag is not None}, memory={self.memory is not None}, discovery={self.discovery is not None}")
        logger.info(f"Active sources: {active_sources}, budgets: {budgets}")
        
        if "rag" in active_sources and self.rag:
            retrieval_tasks.append(("rag", self._retrieve_rag(query, budgets.get("rag", 0))))
        
        if "memory" in active_sources and self.memory:
            retrieval_tasks.append(("memory", self._retrieve_memory(query, budgets.get("memory", 0))))
        
        if "discovery" in active_sources and self.discovery:
            retrieval_tasks.append(("discovery", self._retrieve_discovery(query, budgets.get("discovery", 0))))
        
        # Execute retrieval in parallel
        if retrieval_tasks:
            results = await asyncio.gather(
                *[task for _, task in retrieval_tasks],
                return_exceptions=True
            )
            
            for (source_type, _), result in zip(retrieval_tasks, results):
                if isinstance(result, Exception):
                    logger.error(f"Retrieval error ({source_type}): {result}")
                    continue
                
                if result and result.get("content"):
                    sources.append({
                        "type": source_type,
                        "content": result["content"],
                        "tokens": result.get("tokens", 0),
                        "items": result.get("items", 0)
                    })
                    total_tokens += result.get("tokens", 0)
        
        # 3. Observations (synchronous)
        if "observations" in active_sources and observations:
            obs_content, obs_tokens = self._format_observations(
                observations, budgets.get("observations", 0)
            )
            if obs_content:
                sources.append({
                    "type": "observations",
                    "content": obs_content,
                    "tokens": obs_tokens,
                    "items": len(observations)
                })
                total_tokens += obs_tokens
        
        # Combine all sources
        combined = self._combine_sources(sources)
        
        # Check if we exceeded budget (shouldn't happen, but safety check)
        combined_tokens = self.tokens.count(combined)
        if combined_tokens > max_tokens:
            combined = self.tokens.truncate_to_limit(combined, max_tokens)
            truncated = True
            combined_tokens = max_tokens
        
        # Optional CLaRa compression for large contexts
        compressed = False
        if use_compression and combined_tokens > self._clara_threshold:
            compress_result = await self._compress_with_clara(combined, query)
            if compress_result:
                combined = compress_result["content"]
                combined_tokens = compress_result["tokens"]
                compressed = True
                sources.append({
                    "type": "compression",
                    "original_tokens": compress_result["original_tokens"],
                    "compressed_tokens": compress_result["tokens"],
                    "ratio": compress_result.get("ratio", 16.0),
                })
        
        result = AssembledContext(
            content=combined,
            sources=sources,
            total_tokens=combined_tokens,
            truncated=truncated
        )
        
        if compressed:
            logger.info(f"Context compressed: {sources[-1]['original_tokens']} -> {combined_tokens} tokens")
        
        return result
    
    def _allocate_budget(
        self,
        total: int,
        conversation: List[Dict] = None,
        active_sources: List[str] = None
    ) -> Dict[str, int]:
        """
        Allocate token budget to sources based on priorities.
        
        Adjusts ratios based on conversation length.
        """
        active = active_sources or list(self.priorities.keys())
        conv_len = len(conversation) if conversation else 0
        
        # Dynamic ratios based on conversation length
        if conv_len < 5:
            # Short conversation: more retrieval
            base_ratios = {
                "conversation": 0.10,
                "rag": 0.35,
                "memory": 0.20,
                "discovery": 0.25,
                "observations": 0.10
            }
        elif conv_len < 15:
            # Medium conversation: balanced
            base_ratios = {
                "conversation": 0.25,
                "rag": 0.30,
                "memory": 0.15,
                "discovery": 0.20,
                "observations": 0.10
            }
        else:
            # Long conversation: prioritize history
            base_ratios = {
                "conversation": 0.40,
                "rag": 0.25,
                "memory": 0.10,
                "discovery": 0.15,
                "observations": 0.10
            }
        
        # Filter to active sources and renormalize
        filtered_ratios = {k: v for k, v in base_ratios.items() if k in active}
        total_ratio = sum(filtered_ratios.values())
        
        if total_ratio > 0:
            normalized = {k: v / total_ratio for k, v in filtered_ratios.items()}
        else:
            normalized = {k: 1 / len(active) for k in active}
        
        return {k: int(total * v) for k, v in normalized.items()}
    
    def _format_conversation(
        self,
        conversation: List[Dict],
        max_tokens: int
    ) -> tuple[str, int]:
        """Format conversation history within budget."""
        if max_tokens <= 0:
            return "", 0
        
        lines = []
        tokens = 0
        header = "## Recent Conversation\n"
        header_tokens = self.tokens.count(header)
        
        # Work backwards from most recent
        for msg in reversed(conversation):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Truncate very long messages
            if len(content) > 1000:
                content = content[:1000] + "..."
            
            line = f"**{role}**: {content}"
            line_tokens = self.tokens.count(line) + 1  # +1 for newline
            
            if tokens + line_tokens + header_tokens > max_tokens:
                break
            
            lines.insert(0, line)
            tokens += line_tokens
        
        if not lines:
            return "", 0
        
        result = header + "\n".join(lines)
        return result, tokens + header_tokens
    
    def _format_observations(
        self,
        observations: List[str],
        max_tokens: int
    ) -> tuple[str, int]:
        """Format tool observations within budget."""
        if max_tokens <= 0 or not observations:
            return "", 0
        
        lines = ["## Tool Observations"]
        tokens = self.tokens.count(lines[0])
        
        for obs in observations:
            # Truncate long observations
            if len(obs) > 500:
                obs = obs[:500] + "..."
            
            line = f"- {obs}"
            line_tokens = self.tokens.count(line) + 1
            
            if tokens + line_tokens > max_tokens:
                break
            
            lines.append(line)
            tokens += line_tokens
        
        if len(lines) == 1:
            return "", 0
        
        return "\n".join(lines), tokens
    
    async def _retrieve_rag(self, query: str, max_tokens: int) -> Dict:
        """Retrieve and format RAG results."""
        logger.info(f"_retrieve_rag called with query='{query[:50]}...', max_tokens={max_tokens}")
        if max_tokens <= 0:
            logger.warning("_retrieve_rag: max_tokens <= 0, returning empty")
            return {}
        
        try:
            logger.info("Calling RAG search...")
            results = await self.rag.search(query, limit=5)
            logger.info(f"RAG search returned {len(results)} results")
            
            lines = ["## Relevant Documents"]
            tokens = self.tokens.count(lines[0])
            items = 0
            
            for doc in results:
                content = doc.get("content", "")[:500]
                source = doc.get("source", doc.get("metadata", {}).get("source", "unknown"))
                
                line = f"[{source}]: {content}"
                line_tokens = self.tokens.count(line) + 1
                
                if tokens + line_tokens > max_tokens:
                    break
                
                lines.append(line)
                tokens += line_tokens
                items += 1
            
            if items == 0:
                return {}
            
            return {
                "content": "\n".join(lines),
                "tokens": tokens,
                "items": items
            }
        except Exception as e:
            logger.error(f"RAG retrieval error: {e}")
            return {}
    
    async def _retrieve_memory(self, query: str, max_tokens: int) -> Dict:
        """Retrieve and format memory results."""
        if max_tokens <= 0:
            return {}
        
        try:
            results = await self.memory.recall(query, limit=5)
            
            lines = ["## Remembered Information"]
            tokens = self.tokens.count(lines[0])
            items = 0
            
            for mem in results:
                content = mem.get("content", "")
                mem_type = mem.get("type", "fact")
                
                line = f"- [{mem_type}] {content}"
                line_tokens = self.tokens.count(line) + 1
                
                if tokens + line_tokens > max_tokens:
                    break
                
                lines.append(line)
                tokens += line_tokens
                items += 1
            
            if items == 0:
                return {}
            
            return {
                "content": "\n".join(lines),
                "tokens": tokens,
                "items": items
            }
        except Exception as e:
            logger.error(f"Memory retrieval error: {e}")
            return {}
    
    async def _retrieve_discovery(self, query: str, max_tokens: int) -> Dict:
        """Retrieve and format discovery results."""
        if max_tokens <= 0:
            return {}
        
        try:
            results = await self.discovery.search(query, limit=5)
            
            lines = ["## System Knowledge"]
            tokens = self.tokens.count(lines[0])
            items = 0
            
            for disc in results:
                content = disc.get("content", disc.get("summary", ""))[:300]
                category = disc.get("category", "general")
                
                line = f"- [{category}] {content}"
                line_tokens = self.tokens.count(line) + 1
                
                if tokens + line_tokens > max_tokens:
                    break
                
                lines.append(line)
                tokens += line_tokens
                items += 1
            
            if items == 0:
                return {}
            
            return {
                "content": "\n".join(lines),
                "tokens": tokens,
                "items": items
            }
        except Exception as e:
            logger.error(f"Discovery retrieval error: {e}")
            return {}
    
    def _combine_sources(self, sources: List[Dict]) -> str:
        """
        Combine sources with position-aware ordering.
        
        Based on "Lost in the Middle" research (arxiv.org/abs/2307.03172):
        - LLMs attend best to START and END of context
        - Middle content receives ~60% attention vs ~90%+ at edges
        
        Structure:
        - START: Top RAG results, key memory facts (high salience)
        - MIDDLE: Lower-priority discovery, additional context
        - END: Recent conversation, observations (recency bias helps)
        """
        start_parts = []   # High-salience position (beginning)
        middle_parts = []  # Lower-salience position
        end_parts = []     # High-salience position (near query)
        
        for source in sources:
            source_type = source.get("type")
            content = source.get("content")
            if not content:
                continue
            
            if source_type == "rag":
                # Split RAG: top items at start, rest in middle
                lines = content.split("\n")
                if len(lines) > 3:
                    # First few lines (header + top results) go to start
                    start_parts.append("\n".join(lines[:4]))
                    if len(lines) > 4:
                        middle_parts.append("\n".join(lines[4:]))
                else:
                    start_parts.append(content)
                    
            elif source_type == "memory":
                # Memory facts are important - start position
                start_parts.append(content)
                
            elif source_type == "discovery":
                # Discovery context goes to middle
                middle_parts.append(content)
                
            elif source_type in ["conversation", "observations"]:
                # Recent conversation and observations at end (recency bias)
                end_parts.append(content)
                
            else:
                # Unknown sources go to middle
                middle_parts.append(content)
        
        # Combine in position-aware order
        all_parts = start_parts + middle_parts + end_parts
        return "\n\n".join(all_parts)
    
    async def _compress_with_clara(
        self,
        content: str,
        query: str
    ) -> Optional[Dict[str, Any]]:
        """
        Compress context using CLaRa if available.
        
        Args:
            content: Context content to compress
            query: User query for context-aware compression
            
        Returns:
            Dict with compressed content and stats, or None if unavailable
        """
        # Try to get CLaRa provider
        if self._clara is None:
            try:
                from ..model.clara_provider import get_clara_provider, clara_available
                if clara_available():
                    self._clara = get_clara_provider()
                else:
                    return None
            except ImportError:
                return None
        
        if not self._clara or not self._clara.config.enabled:
            return None
        
        try:
            # Split content into chunks for CLaRa (it expects a list of memories)
            chunks = content.split("\n\n")
            chunks = [c.strip() for c in chunks if c.strip()]
            
            if not chunks:
                return None
            
            original_tokens = self.tokens.count(content)
            
            result = self._clara.compress_memories(
                memories=chunks,
                query=query,
                max_new_tokens=256,
            )
            
            if result.get("success") and result.get("answer"):
                compressed_content = result["answer"]
                compressed_tokens = self.tokens.count(compressed_content)
                
                return {
                    "content": compressed_content,
                    "tokens": compressed_tokens,
                    "original_tokens": original_tokens,
                    "ratio": original_tokens / max(compressed_tokens, 1),
                }
            
            return None
            
        except Exception as e:
            logger.warning(f"CLaRa compression failed: {e}")
            return None
