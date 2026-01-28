"""
Searching State Handler

Handles the SEARCHING state: execute RAG, memory, and web searches.
"""

from __future__ import annotations
import asyncio
import logging
from typing import AsyncIterator, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state_machine import AgentStateMachine

from ..states import AgentState
from ..events import StreamEvent

logger = logging.getLogger('halbert.agents.handlers.searching')


class SearchingHandler:
    """
    Handles the SEARCHING state.
    
    Executes parallel searches across:
    - RAG (document retrieval)
    - Memory (past interactions)
    - Web search (if enabled)
    """
    
    def __init__(self, agent: 'AgentStateMachine'):
        self.agent = agent
    
    async def handle(self) -> AsyncIterator[StreamEvent]:
        """Execute searching state logic."""
        ctx = self.agent.ctx
        ctx.loop_count += 1
        
        # Determine search query
        query = ctx.user_query
        if ctx.pending_tool and ctx.pending_tool.get("name") in ["search", "web_search"]:
            query = ctx.pending_tool.get("args", {}).get("query", query)
        
        logger.debug(f"Searching for: {query[:50]}...")
        
        # Build search tasks and emit scan_start events
        search_tasks = []
        
        # RAG search
        if self.agent.rag_service:
            yield StreamEvent.scan_start(ctx.session_id, "rag", query)
            search_tasks.append(("rag", self._search_rag(query)))
        
        # Memory search
        if self.agent.memory_service:
            yield StreamEvent.scan_start(ctx.session_id, "memory", query)
            search_tasks.append(("memory", self._search_memory(query)))
        
        # Web search (if tool was called)
        if ctx.pending_tool and ctx.pending_tool.get("name") == "web_search":
            if self.agent.tool_executor:
                yield StreamEvent.scan_start(ctx.session_id, "web", query)
                search_tasks.append(("web", self._search_web(query)))
        
        # Execute all searches in parallel
        results = await asyncio.gather(
            *[t[1] for t in search_tasks],
            return_exceptions=True
        )
        
        # Process results and emit scan_complete + context_loaded events
        total_results = 0
        for (source, _), result in zip(search_tasks, results):
            if isinstance(result, Exception):
                logger.warning(f"{source} search failed: {result}")
                yield StreamEvent.scan_complete(ctx.session_id, source, 0)
                continue
            
            result_count = len(result) if result else 0
            yield StreamEvent.scan_complete(ctx.session_id, source, result_count)
            
            if result:
                ctx.retrieved_context.extend(result)
                total_results += result_count
                
                # Emit context_loaded with source label
                source_labels = {
                    "rag": "Documents",
                    "memory": "Memory",
                    "web": "Web Results"
                }
                yield StreamEvent.context_loaded(
                    ctx.session_id,
                    source,
                    result_count,
                    0,  # Token count calculated later
                    label=source_labels.get(source, source)
                )
        
        # Add observation
        ctx.observations.append(f"Retrieved {total_results} results from search")
        
        # Clear pending tool
        ctx.pending_tool = None
        
        # Transition to OBSERVING
        yield self.agent._create_transition_event(AgentState.OBSERVING)
    
    async def _search_rag(self, query: str, limit: int = 5):
        """Search RAG index."""
        try:
            if hasattr(self.agent.rag_service, 'search'):
                return await self.agent.rag_service.search(query, limit=limit)
            return []
        except Exception as e:
            logger.error(f"RAG search error: {e}")
            return []
    
    async def _search_memory(self, query: str, limit: int = 3):
        """Search memory store."""
        try:
            if hasattr(self.agent.memory_service, 'recall'):
                return await self.agent.memory_service.recall(query, limit=limit)
            elif hasattr(self.agent.memory_service, 'search'):
                return await self.agent.memory_service.search(query, limit=limit)
            return []
        except Exception as e:
            logger.error(f"Memory search error: {e}")
            return []
    
    async def _search_web(self, query: str, limit: int = 5):
        """Execute web search via tool."""
        try:
            result = await self.agent.tool_executor.execute(
                "web_search",
                {"query": query, "num_results": limit},
                session_id=self.agent.ctx.session_id
            )
            if result.success:
                return [{"content": result.result, "source": "web"}]
            return []
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return []
