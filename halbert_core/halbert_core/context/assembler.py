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
from ..agents.blocks import content_to_text

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
        "retrieval": 0.8,
        "memory": 0.7,
        "discovery": 0.6,
        "observations": 0.5,
    }

    def __init__(
        self,
        retrieval_service=None,
        memory_service=None,
        discovery_service=None,
        token_counter: TokenCounter = None,
        priorities: Dict[str, float] = None,
        extra_sources: Dict[str, Any] = None,
        rag_service=None,  # deprecated alias for retrieval_service
    ):
        """
        Initialize the context assembler.

        Args:
            retrieval_service: Retrieval search service (SourcePrepAdapter)
            memory_service: Memory recall service
            discovery_service: Discovery search service
            token_counter: Token counting utility
            priorities: Custom priority weights
            extra_sources: Additional source adapters keyed by source name
                (e.g. {"system_identity": adapter, "safety": adapter}).
                Each adapter must have an async search(query, limit) method.
            rag_service: Deprecated alias for retrieval_service (Phase 2).
        """
        # Backward compat: rag_service → retrieval_service
        if retrieval_service is None and rag_service is not None:
            retrieval_service = rag_service
        self.retrieval = retrieval_service
        self.memory = memory_service
        self.discovery = discovery_service
        self.tokens = token_counter or TokenCounter()
        self.priorities = priorities or self.DEFAULT_PRIORITIES
        self._compressor_threshold = 4000  # Compress if context > this many tokens
        self._extra_sources = extra_sources or {}
    
    async def assemble(
        self,
        query: str,
        conversation: List[Dict] = None,
        observations: List[str] = None,
        max_tokens: int = 8000,
        include_sources: List[str] = None,
        use_compression: bool = True,
        intake: Any = None,
    ) -> AssembledContext:
        """Assemble context within token budget.

        Args:
            query: User query for retrieval
            conversation: Conversation history
            observations: Tool execution observations
            max_tokens: Maximum tokens for assembled context
            include_sources: Specific sources to include (default: all)
            use_compression: Whether to apply compression cascade
            intake: Optional Phase 3 MessageIntake. When provided:
                - max_tokens is overridden by intake.context_budget.total
                - retrieval is gated by intake.needs_retrieval
                - per-category budgets from intake.context_budget override
                  the flat _allocate_budget ratios

        Returns:
            AssembledContext with combined content
        """
        sources = []
        total_tokens = 0
        truncated = False

        # Phase 3: Override max_tokens from intake budget if available
        if intake is not None and hasattr(intake, "context_budget"):
            max_tokens = intake.context_budget.total

        # Determine which sources to include
        active_sources = include_sources or list(self.priorities.keys())

        # Phase 3: Gate retrieval based on intake.needs_retrieval
        if intake is not None and not intake.needs_retrieval:
            active_sources = [s for s in active_sources if s != "retrieval"]

        # Allocate budget
        if intake is not None and hasattr(intake, "context_budget"):
            budgets = self._allocate_budget_from_intake(
                intake.context_budget, conversation, active_sources
            )
        else:
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
        
        logger.info(f"Context assembly: retrieval={self.retrieval is not None}, memory={self.memory is not None}, discovery={self.discovery is not None}")
        logger.info(f"Active sources: {active_sources}, budgets: {budgets}")

        if "retrieval" in active_sources and self.retrieval:
            retrieval_tasks.append(("retrieval", self._retrieve_retrieval(query, budgets.get("retrieval", 0))))
        
        if "memory" in active_sources and self.memory:
            retrieval_tasks.append(("memory", self._retrieve_memory(query, budgets.get("memory", 0))))
        
        if "discovery" in active_sources and self.discovery:
            retrieval_tasks.append(("discovery", self._retrieve_discovery(query, budgets.get("discovery", 0))))
        
        # Extra sources (Phase C: system_identity, self_knowledge, telemetry, safety)
        for source_name, adapter in self._extra_sources.items():
            if source_name in active_sources and adapter is not None:
                retrieval_tasks.append(
                    (source_name, self._retrieve_extra(query, budgets.get(source_name, 0), adapter, source_name))
                )
        
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
        
        # Optional compression for large contexts (Phase 72: compression cascade)
        compressed = False
        if use_compression and combined_tokens > self._compressor_threshold:
            compress_result = await self._compress_with_cascade(combined, query, sources)
            if compress_result:
                combined = compress_result["content"]
                combined_tokens = compress_result["tokens"]
                compressed = True
                sources.append({
                    "type": "compression",
                    "original_tokens": compress_result["original_tokens"],
                    "compressed_tokens": compress_result["tokens"],
                    "ratio": compress_result.get("ratio", 1.0),
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
                "retrieval": 0.35,
                "memory": 0.20,
                "discovery": 0.25,
                "observations": 0.10
            }
        elif conv_len < 15:
            # Medium conversation: balanced
            base_ratios = {
                "conversation": 0.25,
                "retrieval": 0.30,
                "memory": 0.15,
                "discovery": 0.20,
                "observations": 0.10
            }
        else:
            # Long conversation: prioritize history
            base_ratios = {
                "conversation": 0.40,
                "retrieval": 0.25,
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

    def _allocate_budget_from_intake(
        self,
        context_budget: Any,
        conversation: List[Dict] = None,
        active_sources: List[str] = None,
    ) -> Dict[str, int]:
        """Allocate token budget using per-category budgets from intake.

        Maps the ContextBudget fields to assembler source names and
        filters to active sources only.

        Args:
            context_budget: ContextBudget dataclass from intake.budget
            conversation: Conversation history (unused, for API compat)
            active_sources: Which sources to include

        Returns:
            Dict mapping source name → token budget
        """
        active = active_sources or list(self.priorities.keys())

        # Map ContextBudget fields to assembler source names
        budget_map = {
            "system_identity": context_budget.system_identity,
            "user_rules": context_budget.user_rules,
            "retrieval": context_budget.retrieval,
            "memory": context_budget.memory,
            "discovery": context_budget.discovery,
            "conversation": context_budget.conversation,
            "observations": context_budget.observations,
        }

        # Filter to active sources only
        return {k: v for k, v in budget_map.items() if k in active}

    def _format_conversation(
        self,
        conversation: List[Dict],
        max_tokens: int
    ) -> tuple[str, int]:
        """Format conversation history within budget.

        Uses hierarchical summarization for long conversations (Phase 72):
        - Last 6 messages kept as raw text
        - Older messages summarized via extractive summary
        """
        if max_tokens <= 0:
            return "", 0

        # Phase 72: Use conversation summarization for long chats
        try:
            from ..conversation.summarization import should_summarize, compress_conversation_history
            if should_summarize(conversation):
                compressed_msgs, summary = compress_conversation_history(conversation)
                if summary:
                    # Use compressed messages with summary prefix
                    conversation = compressed_msgs
        except ImportError:
            pass  # Fall back to simple truncation if summarization unavailable

        lines = []
        tokens = 0
        header = "## Recent Conversation\n"
        header_tokens = self.tokens.count(header)

        # Work backwards from most recent
        for msg in reversed(conversation):
            role = msg.get("role", "user")
            # content may be a string (legacy) or a list of content blocks (A1)
            content = content_to_text(msg.get("content", ""))

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
    
    async def _retrieve_retrieval(self, query: str, max_tokens: int) -> Dict:
        """Retrieve and format retrieval results (SourcePrep)."""
        logger.info(f"_retrieve_retrieval called with query='{query[:50]}...', max_tokens={max_tokens}")
        if max_tokens <= 0:
            logger.warning("_retrieve_retrieval: max_tokens <= 0, returning empty")
            return {}

        try:
            logger.info("Calling retrieval search...")
            results = await self.retrieval.search(query, limit=5)
            logger.info(f"Retrieval search returned {len(results)} results")
            
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
            logger.error(f"Retrieval error: {e}")
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
    
    async def _retrieve_extra(self, query: str, max_tokens: int, adapter: Any, source_name: str) -> Dict:
        """Retrieve and format results from an extra source adapter."""
        if max_tokens <= 0:
            return {}
        
        try:
            results = await adapter.search(query, limit=5)
            
            if not results:
                return {}
            
            lines = [f"## {source_name.replace('_', ' ').title()}"]
            tokens = self.tokens.count(lines[0])
            items = 0
            
            for item in results:
                content = item.get("content", "")[:500]
                line = f"- {content}"
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
            logger.error(f"Extra source ({source_name}) retrieval error: {e}")
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
            
            if source_type == "retrieval":
                # Split retrieval: top items at start, rest in middle
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
    
    async def _compress_with_cascade(
        self,
        content: str,
        query: str,
        sources: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Source-aware compression cascade (Phase 72 port from LinuxBrain).

        Applies different strategies per source type:
        - memories → LOD batch compression
        - rag/SourcePrep → light or skip (already compressed by SourcePrep LOD)
        - conversation → semantic compression (standard level)
        - observations → semantic compression (standard level)
        - other → semantic compression (standard level)

        Args:
            content: Combined context content to compress.
            query: User query for context-aware compression.
            sources: List of source dicts with 'type' and 'content' keys.

        Returns:
            Dict with compressed content and stats, or None if unavailable.
            Shape: {'content': str, 'tokens': int, 'original_tokens': int, 'ratio': float}
        """
        try:
            from ..compression.factory import create_compressor
        except ImportError:
            logger.debug("Compression package not available, skipping cascade")
            return None

        original_tokens = self.tokens.count(content)
        if original_tokens == 0:
            return None

        compressor = create_compressor()
        if not compressor.is_available():
            return None

        # Compress per-source for targeted strategy
        parts: List[str] = []
        for source in sources:
            source_type = source.get("type", "unknown")
            source_content = source.get("content", "")
            if not source_content:
                continue

            # Skip compression metadata sources
            if source_type == "compression":
                continue

            # Determine compression level per source type
            if source_type == "retrieval":
                # SourcePrep already compressed — light only
                level = "light"
            elif source_type == "memory":
                # Memories get standard compression
                # (LOD batch would need memory dicts with relevance/epistemic)
                level = "standard"
            elif source_type in ("conversation", "observations"):
                level = "standard"
            else:
                level = "standard"

            try:
                result = compressor.compress(source_content, level=level)
                parts.append(result.compressed)
            except Exception as e:
                logger.warning(f"Cascade compress failed for {source_type}: {e}")
                parts.append(source_content)  # Keep original on error

        combined = "\n\n".join(parts)
        combined_tokens = self.tokens.count(combined)

        if combined_tokens >= original_tokens:
            # No compression achieved
            return None

        return {
            "content": combined,
            "tokens": combined_tokens,
            "original_tokens": original_tokens,
            "ratio": round(original_tokens / max(combined_tokens, 1), 2),
        }
